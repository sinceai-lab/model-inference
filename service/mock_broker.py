"""Mock context broker with full control for the user. It speaks the same NGSI-LD as a real broker on /ngsi-ld/v1 (subscriptions, entities,
batch upsert) and applies the same @context rules, so the backend can't tell the difference. Control lives on /mock. Run through
`python -m service.cli start`, or: uvicorn service.mock_broker:app --host 127.0.0.1 --port 8601. State is in memory.
"""
import json
import queue
import random
import re
import threading
import time
import uuid
from collections import deque
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import httpx
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict

import service  # noqa: F401
from config import DATA
from service.settings import CORE_CONTEXT

CONTEXT_REL = "http://www.w3.org/ns/json-ld#context"
FORMATS = {"normalized", "concise", "keyValues", "simplified"}
SKIP = {"id", "type", "@context"}
MALFORMED = ["not_json", "wrong_content_type", "no_data", "no_subscription_id", "bad_notified_at", "data_not_array"]
SEQUENCES = ["duplicate", "conflict", "out_of_order", "missing_day"]
OTHER = ["bad_batch", "yield_prediction"]


class ProblemError(Exception):
    def __init__(self, status, kind, title, detail=""):
        self.status, self.kind, self.title, self.detail = status, kind, title, detail


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def to_normalized(entity):
    """Store every entity in normalized form, however it arrived."""
    out = {}
    for k, v in entity.items():
        if k in SKIP:
            out[k] = v
        elif isinstance(v, dict) and v.get("type") in ("Property", "Relationship", "GeoProperty"):
            out[k] = v
        elif isinstance(v, dict) and "object" in v:
            out[k] = dict(v, type="Relationship")
        elif isinstance(v, dict) and "value" in v:
            out[k] = dict(v, type="Property")
        elif isinstance(v, dict) and v.get("type") in ("Point", "Polygon", "LineString"):
            out[k] = dict(type="GeoProperty", value=v)
        else:
            out[k] = dict(type="Property", value=v)
    return out


def represent(entity, fmt):
    """A stored entity in the subscription's format."""
    if fmt == "normalized":
        return {k: v for k, v in entity.items() if k != "@context"}
    out = {}
    for k, v in entity.items():
        if k == "@context":
            continue
        if k in SKIP:
            out[k] = v
            continue
        inner = v.get("object") if v.get("type") == "Relationship" else v.get("value")
        extras = {x: y for x, y in v.items() if x not in ("type", "value", "object")}
        if fmt == "concise" and extras:
            out[k] = dict(extras, **({"object": inner} if v.get("type") == "Relationship" else {"value": inner}))
        elif fmt == "concise" and v.get("type") == "Relationship":
            out[k] = {"object": inner}
        else:
            out[k] = inner
    return out


def weather_entity(cell_id, day, tmean=None, tmax=None, tmin=None, precip=None, pet=None, lat=None, lon=None, per_day_id=False):
    """A daily reading as a normalized WeatherObserved entity, with the attributes of the broker handoff contract."""
    def prop(value, unit=None):
        return dict(type="Property", value=value, **({"unitCode": unit} if unit else {}))
    e = {"id": f"urn:ngsi-ld:WeatherObserved:{cell_id}" + (f":{day}" if per_day_id else ""), "type": "WeatherObserved", "dateObserved": prop({"@type": "DateTime", "@value": f"{day}T00:00:00Z"}),
         "cellId": prop(cell_id), "source": prop("mock-broker")}
    if lat is not None:
        e["location"] = dict(type="GeoProperty", value=dict(type="Point", coordinates=[lon, lat]))
    if tmean is not None:
        e["temperature"] = prop(tmean, "CEL")
    if tmax is not None:
        e["temperatureMax"] = prop(tmax, "CEL")
    if tmin is not None:
        e["temperatureMin"] = prop(tmin, "CEL")
    if precip is not None:
        e["precipitation"] = prop(precip, "MMT")
    if pet is not None:
        e["referenceEvapotranspiration"] = prop(pet, "MMT")
    return e


class ReplayJob(threading.Thread):
    def __init__(self, broker, job_id, spec, days):
        super().__init__(daemon=True, name=f"replay-{job_id}")
        self.broker, self.job_id, self.spec, self.days = broker, job_id, spec, days
        self.run_gate, self.halted = threading.Event(), threading.Event()
        self.run_gate.set()
        self.sent, self.state, self.current, self.errors, self.finished_at = 0, "running", None, 0, None
        self.started_at = stamp()

    def info(self):
        return dict(job_id=self.job_id, state=self.state, sent=self.sent, total=len(self.days), current_date=self.current, errors=self.errors, started_at=self.started_at, finished_at=self.finished_at, spec=self.spec)

    def run(self):
        delay = 1.0 / self.spec["days_per_second"] if self.spec["days_per_second"] > 0 else 0
        size = max(self.spec["batch_size"], 1)
        try:
            for i in range(0, len(self.days), size):
                if not self.run_gate.is_set():
                    self.state = "paused"
                    self.run_gate.wait()
                if self.halted.is_set():
                    self.state = "stopped"
                    return
                self.state = "running"
                group = self.days[i:i + size]
                t0 = time.time()
                self.errors += self.broker.publish([weather_entity(**d, per_day_id=size > 1) for d in group], wait=True, kind="replay")
                self.sent += len(group)
                self.current = group[-1]["day"]
                if delay:
                    time.sleep(max(0.0, delay * len(group) - (time.time() - t0)))
            self.state = "finished"
        except Exception as e:
            self.state = f"failed: {e}"
        finally:
            self.finished_at = stamp()


class Broker:
    def __init__(self, http=None, weather=None, cells=None):
        self.http = http or httpx.Client(timeout=30.0)
        self.subs, self.entities, self.jobs, self.log = {}, {}, {}, deque(maxlen=500)
        self.lock = threading.RLock()
        self.queue = queue.Queue()
        self.cells = cells if cells is not None else pd.read_csv(DATA / "01_master/climate_grid_cells.csv").set_index("cell_id")
        self.weather = weather  # Optional frame for tests, otherwise read from the package per request.
        threading.Thread(target=self._dispatch_loop, daemon=True, name="dispatch").start()

    # ---------------------------------------------------------------- Broker behaviour
    def add_subscription(self, body):
        if not isinstance(body, dict) or body.get("type") != "Subscription":
            raise ProblemError(400, "BadRequestData", "type must be Subscription")
        if not body.get("entities") and not body.get("watchedAttributes"):
            raise ProblemError(400, "BadRequestData", "A subscription needs entities or watchedAttributes")
        n = body.get("notification")
        uri = n.get("endpoint", {}).get("uri") if isinstance(n, dict) else None
        if not uri:
            raise ProblemError(400, "BadRequestData", "notification.endpoint.uri is required")
        if n.get("format", "normalized") not in FORMATS:
            raise ProblemError(400, "BadRequestData", f"notification.format must be one of {sorted(FORMATS)}")
        if "timeInterval" in body:
            raise ProblemError(400, "OperationNotSupported", "The mock doesn't do periodic notifications, and they would lose days. Don't use timeInterval")
        sid = body.get("id") or f"urn:ngsi-ld:Subscription:{uuid.uuid4().hex}"
        with self.lock:
            if sid in self.subs:
                raise ProblemError(409, "AlreadyExists", f"Subscription {sid} already exists")
            self.subs[sid] = dict(body, id=sid, **{"isActive": body.get("isActive", True), "status": "active"}, notification=dict(n, timesSent=0, timesFailed=0), _last_sent=0.0)
        return sid

    def _matches(self, sub, entity, changed):
        if not sub.get("isActive", True):
            return False
        watched = sub.get("watchedAttributes")
        if watched and not set(watched) & changed:
            return False
        selectors = sub.get("entities")
        if not selectors:
            return True
        for s in selectors:
            if s.get("type") and s["type"] != entity.get("type"):
                continue
            if s.get("id") and s["id"] != entity.get("id"):
                continue
            if s.get("idPattern") and not re.fullmatch(s["idPattern"], entity.get("id", "")):
                continue
            return True
        return False

    def upsert(self, entities, replace=True, kind="upsert", wait=False):
        """Store entities and notify matching subscriptions. (created ids, failures to deliver)."""
        created = []
        with self.lock:
            for e in entities:
                n = to_normalized(e)
                if n["id"] not in self.entities:
                    created.append(n["id"])
                    self.entities[n["id"]] = n
                elif replace:
                    self.entities[n["id"]] = n
                else:
                    self.entities[n["id"]].update(n)
            batch = [(dict(self.entities[e["id"]]), set(e) - SKIP) for e in entities]
        return created, self._notify(batch, kind, wait)

    def publish(self, entities, wait=False, kind="upsert"):
        return self.upsert(entities, kind=kind, wait=wait)[1]

    def _notify(self, batch, kind, wait):
        """Send to each subscription the entities it matches. wait=True delivers in order on this thread."""
        with self.lock:
            subs = list(self.subs.values())
        failures = 0
        for sub in subs:
            matching = [e for e, changed in batch if self._matches(sub, e, changed)]
            if not matching:
                continue
            throttle = sub.get("throttling", 0)
            if throttle and time.time() - sub["_last_sent"] < throttle:
                self.log.append(dict(at=stamp(), subscription=sub["id"], kind=kind, status="throttled", entities=len(matching)))
                continue
            sub["_last_sent"] = time.time()
            if wait:
                failures += self._deliver(sub, matching, kind)
            else:
                self.queue.put((sub, matching, kind))
        return failures

    def _dispatch_loop(self):
        while True:
            sub, matching, kind = self.queue.get()
            self._deliver(sub, matching, kind)

    def _deliver(self, sub, entities, kind):
        n = sub["notification"]
        fmt = n.get("format", "normalized")
        doc = {"id": f"urn:ngsi-ld:Notification:{uuid.uuid4().hex}", "type": "Notification", "subscriptionId": sub["id"], "notifiedAt": stamp(), "data": [represent(e, fmt) for e in entities]}
        accept = n["endpoint"].get("accept", "application/json")
        context = sub.get("@context") or CORE_CONTEXT
        headers = {"Content-Type": accept}
        if accept == "application/ld+json":
            doc["@context"] = context
        else:
            url = context[0] if isinstance(context, list) else context
            headers["Link"] = f'<{url}>; rel="{CONTEXT_REL}"; type="application/ld+json"'
        return self.send_raw(sub, json.dumps(doc), headers, kind, len(entities))

    def send_raw(self, sub, body, headers, kind, count=1):
        """POST to the subscriber and record the outcome. Returns 1 on failure, 0 on success."""
        n = sub["notification"]
        entry = dict(at=stamp(), subscription=sub["id"], kind=kind, entities=count)
        try:
            r = self.http.post(n["endpoint"]["uri"], content=body, headers=headers)
            entry.update(status=r.status_code, response=_short_response(r))
            ok = r.status_code < 300
        except httpx.HTTPError as e:
            entry.update(status="unreachable", error=str(e)[:200])
            ok = False
        self.log.append(entry)
        n["timesSent"] += 1
        n["timesFailed"] += 0 if ok else 1
        n["lastNotification" if ok else "lastFailure"] = entry["at"]
        return 0 if ok else 1

    # ---------------------------------------------------------------- Control
    def read_days(self, cell_id, start, end, scenario, include_pet=True):
        if cell_id not in self.cells.index:
            raise HTTPException(404, f"Unknown cell {cell_id}.")
        lat, lon = float(self.cells.loc[cell_id, "lat"]), float(self.cells.loc[cell_id, "lon"])
        if self.weather is not None:
            w = self.weather
            w = w[(w.cell_id == cell_id) & (w.scenario == scenario) & (w.date >= pd.Timestamp(start)) & (w.date <= pd.Timestamp(end))]
        else:
            w = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet", filters=[("cell_id", "==", cell_id), ("scenario", "==", scenario), ("date", ">=", pd.Timestamp(start)), ("date", "<=", pd.Timestamp(end))])
        if w.empty:
            raise HTTPException(404, f"No {scenario} weather for {cell_id} from {start} to {end}. Historical covers 1991-2026, the SSPs 2027-2060.")
        return [dict(cell_id=cell_id, day=pd.Timestamp(r.date).date().isoformat(), tmean=float(r.tmean_c), tmax=float(r.tmax_c), tmin=float(r.tmin_c), precip=float(r.precip_mm), pet=float(r.pet_mm) if include_pet else None, lat=lat, lon=lon)
                for r in w.sort_values("date").itertuples()]

    def require_weather_subscription(self):
        probe = dict(id="urn:ngsi-ld:WeatherObserved:probe", type="WeatherObserved")
        if not any(self._matches(s, probe, {"temperature", "precipitation", "dateObserved"}) for s in self.subs.values()):
            raise HTTPException(409, "No subscription matches WeatherObserved, so nothing would be sent. Run: python -m service.cli subscribe")


def _short_response(r):
    try:
        d = r.json()
    except ValueError:
        return r.text[:200]
    if isinstance(d, dict):
        return {k: d[k] for k in ("readings", "rejected", "predictions_written", "title", "detail", "ignored") if k in d}
    return d


class ReplaySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell_id: str
    year: int
    start: Optional[str] = None
    end: Optional[str] = None
    scenario: Optional[str] = None
    days_per_second: float = 5.0
    batch_size: int = 1
    drop_every: int = 0
    drop_dates: List[str] = []
    duplicate_every: int = 0
    shuffle_window: int = 0
    include_pet: bool = True
    seed: int = 1


class CustomReading(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cell_id: str
    date: str
    temperature: Optional[float] = None
    tmax: Optional[float] = None
    tmin: Optional[float] = None
    precipitation: Optional[float] = None
    pet: Optional[float] = None


class Injection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    cell_id: str = "GF0203"
    date: str = "2025-06-01"
    scenario: Optional[str] = None


def scenario_for(year, scenario=None):
    return scenario or ("historical" if year <= 2026 else "ssp245")


def plan_days(days, spec):
    """Apply the requested faults to a replay's days."""
    rng = random.Random(spec.seed)
    if spec.drop_dates:
        days = [d for d in days if d["day"] not in set(spec.drop_dates)]
    if spec.drop_every > 1:
        days = [d for i, d in enumerate(days, 1) if i % spec.drop_every]
    if spec.shuffle_window > 1:
        shuffled = []
        for i in range(0, len(days), spec.shuffle_window):
            part = days[i:i + spec.shuffle_window]
            rng.shuffle(part)
            shuffled += part
        days = shuffled
    if spec.duplicate_every > 1:
        days = [x for i, d in enumerate(days, 1) for x in ([d, d] if i % spec.duplicate_every == 0 else [d])]
    return days


def inject(b, spec):
    """Send a fault to every weather subscriber. Each step's outcome is returned, as the backend reported it."""
    if spec.kind not in MALFORMED + SEQUENCES + OTHER:
        raise HTTPException(422, f"Unknown kind {spec.kind!r}. Choose from {MALFORMED + SEQUENCES + OTHER}.")
    b.require_weather_subscription()
    first = date.fromisoformat(spec.date)
    scenario = scenario_for(first.year, spec.scenario)
    days = b.read_days(spec.cell_id, first, first + timedelta(days=2), scenario)
    if spec.kind in SEQUENCES:
        before = len(b.log)
        if spec.kind == "duplicate":
            order = [days[0], days[0]]
        elif spec.kind == "conflict":
            order = [days[0], dict(days[0], tmean=days[0]["tmean"] + 3.0, tmax=days[0]["tmax"] + 3.0)]
        elif spec.kind == "out_of_order":
            order = [days[2], days[0], days[1]]
        else:
            order = [days[0], days[2]]
        for d in order:
            b.publish([weather_entity(**d)], wait=True, kind=f"inject:{spec.kind}")
        return dict(kind=spec.kind, sent=[d["day"] for d in order], outcomes=list(b.log)[before:])
    good = weather_entity(**days[0])
    probe = dict(id="urn:ngsi-ld:WeatherObserved:probe", type="WeatherObserved")
    subs = [s for s in b.subs.values() if b._matches(s, probe, {"temperature"})]
    envelope = lambda data: {"id": f"urn:ngsi-ld:Notification:{uuid.uuid4().hex}", "type": "Notification", "subscriptionId": subs[0]["id"], "notifiedAt": stamp(), "data": data}
    headers = {"Content-Type": "application/json"}
    if spec.kind == "not_json":
        body = '{"type": "Notification", "data": ['
    elif spec.kind == "wrong_content_type":
        body, headers = json.dumps(envelope([good])), {"Content-Type": "text/plain"}
    elif spec.kind == "no_data":
        d = envelope([good])
        del d["data"]
        body = json.dumps(d)
    elif spec.kind == "no_subscription_id":
        d = envelope([good])
        del d["subscriptionId"]
        body = json.dumps(d)
    elif spec.kind == "bad_notified_at":
        body = json.dumps(dict(envelope([good]), notifiedAt="yesterday-ish"))
    elif spec.kind == "data_not_array":
        body = json.dumps(dict(envelope([good]), data=good))
    elif spec.kind == "yield_prediction":
        body = json.dumps(envelope([{"id": f"urn:ngsi-ld:YieldPrediction:X:pea:{first.year}", "type": "YieldPrediction", "estimatedYield": dict(type="Property", value=3.0)}]))
    else:
        cell = spec.cell_id
        no_date = {k: v for k, v in good.items() if k != "dateObserved"}
        body = json.dumps(envelope([good, "not an object", {"id": "urn:x:no-type"}, no_date, dict(good, temperature=dict(type="Property", value="warm")), dict(good, cellId=dict(type="Property", value="GX9999")),
                                    dict(good, temperature=dict(type="Property", value=20, unitCode="XXX")), dict(good, precipitation=dict(type="Property", value=-5), id=f"urn:ngsi-ld:WeatherObserved:{cell}:neg")]))
    before = len(b.log)
    for s in subs:
        b.send_raw(s, body, headers, f"inject:{spec.kind}")
    return dict(kind=spec.kind, outcomes=list(b.log)[before:])


async def _read_json(request):
    """The content rules of ETSI GS CIM 009 clause 6.3.5, as a real broker enforces them."""
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media not in ("application/json", "application/ld+json"):
        raise ProblemError(415, "UnsupportedMediaType", "Content-Type must be application/json or application/ld+json")
    try:
        doc = json.loads(await request.body())
    except ValueError as e:
        raise ProblemError(400, "InvalidRequest", "Body isn't valid JSON", str(e))
    items = doc if isinstance(doc, list) else [doc]
    has_context = [isinstance(x, dict) and "@context" in x for x in items]
    if media == "application/ld+json":
        if "link" in request.headers:
            raise ProblemError(400, "BadRequestData", "A Link header isn't allowed with application/ld+json")
        if not all(has_context):
            raise ProblemError(400, "BadRequestData", "application/ld+json needs @context in the body of every item")
    elif any(has_context):
        raise ProblemError(400, "BadRequestData", "application/json can't carry @context in the body: use a Link header")
    return doc


def create_app(b=None):
    app = FastAPI(title="Mock NGSI-LD broker")
    state = {"broker": b}

    def get():
        if state["broker"] is None:
            state["broker"] = Broker()
        return state["broker"]

    @app.exception_handler(ProblemError)
    async def problem(request, e):
        return JSONResponse(status_code=e.status, media_type="application/problem+json", content=dict(type=f"https://uri.etsi.org/ngsi-ld/errors/{e.kind}", title=e.title, detail=e.detail))

    # ---------------------------------------------------------------- NGSI-LD
    @app.post("/ngsi-ld/v1/subscriptions")
    @app.post("/ngsi-ld/v1/subscriptions/")
    async def create_subscription(request: Request):
        sid = get().add_subscription(await _read_json(request))
        return Response(status_code=201, headers={"Location": f"/ngsi-ld/v1/subscriptions/{sid}"})

    @app.get("/ngsi-ld/v1/subscriptions")
    def list_subscriptions():
        return JSONResponse([_public(s) for s in get().subs.values()])

    @app.get("/ngsi-ld/v1/subscriptions/{sub_id}")
    def read_subscription(sub_id: str):
        sub = get().subs.get(sub_id)
        if not sub:
            raise ProblemError(404, "ResourceNotFound", f"No subscription {sub_id}")
        return JSONResponse(_public(sub))

    @app.delete("/ngsi-ld/v1/subscriptions/{sub_id}")
    def delete_subscription(sub_id: str):
        if get().subs.pop(sub_id, None) is None:
            raise ProblemError(404, "ResourceNotFound", f"No subscription {sub_id}")
        return Response(status_code=204)

    @app.post("/ngsi-ld/v1/entityOperations/upsert")
    async def upsert(request: Request, options: str = "replace"):
        doc = await _read_json(request)
        if not isinstance(doc, list) or not doc or any(x is None for x in doc):
            raise ProblemError(400, "BadRequestData", "The body must be a non-empty array of entities")
        good = [x for x in doc if isinstance(x, dict) and x.get("id") and x.get("type")]
        errors = [dict(entityId=x.get("id") if isinstance(x, dict) else None, error=dict(type="BadRequestData", title="An entity needs id and type")) for x in doc if not (isinstance(x, dict) and x.get("id") and x.get("type"))]
        created, _ = get().upsert(good, replace=options != "update") if good else ([], 0)
        if errors:
            return JSONResponse(status_code=207, content=dict(success=[x["id"] for x in good], errors=errors))
        return JSONResponse(status_code=201, content=created) if created else Response(status_code=204)

    @app.post("/ngsi-ld/v1/entities")
    @app.post("/ngsi-ld/v1/entities/")
    async def create_entity(request: Request):
        doc = await _read_json(request)
        if not isinstance(doc, dict) or not doc.get("id") or not doc.get("type"):
            raise ProblemError(400, "BadRequestData", "An entity needs id and type")
        if doc["id"] in get().entities:
            raise ProblemError(409, "AlreadyExists", f"Entity {doc['id']} already exists")
        get().upsert([doc])
        return Response(status_code=201, headers={"Location": f"/ngsi-ld/v1/entities/{doc['id']}"})

    @app.get("/ngsi-ld/v1/entities")
    def list_entities(type: Optional[str] = None, id: Optional[str] = None, limit: int = 20, offset: int = 0, options: str = ""):
        fmt = "keyValues" if "keyValues" in options or "simplified" in options else "concise" if "concise" in options else "normalized"
        rows = [e for e in get().entities.values() if (type is None or e["type"] == type) and (id is None or e["id"] in id.split(","))]
        return JSONResponse([represent(e, fmt) for e in rows[offset:offset + limit]], headers={"NGSILD-Results-Count": str(len(rows))})

    @app.get("/ngsi-ld/v1/entities/{entity_id}")
    def read_entity(entity_id: str, options: str = ""):
        e = get().entities.get(entity_id)
        if not e:
            raise ProblemError(404, "ResourceNotFound", f"No entity {entity_id}")
        return JSONResponse(represent(e, "keyValues" if "keyValues" in options else "normalized"))

    # ---------------------------------------------------------------- Control
    @app.post("/mock/replay")
    def start_replay(spec: ReplaySpec):
        b = get()
        b.require_weather_subscription()
        # The model's window is day of year 60-300, which starts on 29 February in a leap year.
        start = spec.start or (date(spec.year, 1, 1) + timedelta(days=59)).isoformat()
        end = spec.end or (date(spec.year, 1, 1) + timedelta(days=299)).isoformat()
        days = plan_days(b.read_days(spec.cell_id, start, end, scenario_for(spec.year, spec.scenario), spec.include_pet), spec)
        job_id = uuid.uuid4().hex[:8]
        job = ReplayJob(b, job_id, dict(spec.model_dump(), start=start, end=end, scenario=scenario_for(spec.year, spec.scenario)), days)
        b.jobs[job_id] = job
        job.start()
        return job.info()

    @app.get("/mock/replay")
    def list_replays():
        return [j.info() for j in get().jobs.values()]

    def job_of(job_id):
        job = get().jobs.get(job_id)
        if not job:
            raise HTTPException(404, f"No replay {job_id}.")
        return job

    @app.get("/mock/replay/{job_id}")
    def read_replay(job_id: str):
        return job_of(job_id).info()

    @app.post("/mock/replay/{job_id}/{action}")
    def control_replay(job_id: str, action: str):
        job = job_of(job_id)
        if action == "pause":
            job.run_gate.clear()
        elif action == "resume":
            job.run_gate.set()
        elif action == "stop":
            job.halted.set()
            job.run_gate.set()
        else:
            raise HTTPException(422, "Action must be pause, resume or stop.")
        return job.info()

    @app.post("/mock/reading")
    def send_reading(r: CustomReading):
        b = get()
        b.require_weather_subscription()
        if r.cell_id not in b.cells.index:
            raise HTTPException(404, f"Unknown cell {r.cell_id}.")
        lat, lon = float(b.cells.loc[r.cell_id, "lat"]), float(b.cells.loc[r.cell_id, "lon"])
        before = len(b.log)
        b.publish([weather_entity(r.cell_id, r.date, r.temperature, r.tmax, r.tmin, r.precipitation, r.pet, lat, lon)], wait=True, kind="reading")
        return dict(outcomes=list(b.log)[before:])

    @app.post("/mock/inject")
    def send_fault(spec: Injection):
        return inject(get(), spec)

    @app.get("/mock/log")
    def read_log(limit: int = 50):
        return list(get().log)[-limit:]

    @app.get("/mock/status")
    def status():
        b = get()
        by_type = {}
        for e in b.entities.values():
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        return dict(status="ok", subscriptions=[_public(s) for s in b.subs.values()], entities=by_type, jobs=[j.info() for j in b.jobs.values()], log_entries=len(b.log))

    @app.post("/mock/reset")
    def reset():
        b = get()
        for j in b.jobs.values():
            j.halted.set()
            j.run_gate.set()
        b.subs.clear(), b.entities.clear(), b.jobs.clear(), b.log.clear()
        return dict(status="reset")

    return app


def _public(sub):
    return {k: v for k, v in sub.items() if not k.startswith("_")}


app = create_app()
