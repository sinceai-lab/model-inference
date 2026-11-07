"""Write predictions back to a context broker. Off unless CB_URL is set. Sends only YieldPrediction entities, and refuses subscriptions on
anything but weather types, so writing back can't trigger the backend. No web framework code, only an HTTP client."""
import json
import logging
import threading

import httpx

from service.ngsi import PREDICTION_TYPE, WEATHER_TYPES
from service.settings import WEATHER_CONTEXT

log = logging.getLogger("service.broker")
TIMEOUT = 10.0


def prediction_entity(p, context):
    """A prediction row as a normalized NGSI-LD entity. The id has no date: the entity holds the current estimate, and /predictions holds the history."""
    def prop(value, **extra):
        return dict(type="Property", value=value, **extra)
    observed_at = p["as_of_date"] + "T00:00:00Z"
    return {"id": f"urn:ngsi-ld:{PREDICTION_TYPE}:{p['parcel_id']}:{p['crop']}:{p['year']}", "type": PREDICTION_TYPE, "refParcel": dict(type="Relationship", object=f"urn:ngsi-ld:AgriParcel:{p['parcel_id']}"),
            "refGridCell": dict(type="Relationship", object=f"urn:ngsi-ld:ClimateGridCell:{p['cell_id']}"), "cropName": prop(p["crop"]), "seasonYear": prop(p["year"]), "predictionLabel": prop(p["label"]),
            "estimatedYield": prop(round(p["yield_t_ha"], 3), unitText="t/ha", observedAt=observed_at), 
            "modelName": prop(p["model_name"]), "modelVersion": prop(p["model_version"]), "observedDays": prop(p["observed_days"]), "filledDays": prop(p["filled_days"]), "filledGapDays": prop(p["filled_gap_days"]),
            "filledFutureDays": prop(p["filled_future_days"]), "asOfDate": prop({"@type": "Date", "@value": p["as_of_date"]}), "computedAt": prop({"@type": "DateTime", "@value": p["computed_at"]}),
            **({"baselineYield": prop(round(p["baseline_t_ha"], 3), unitText="t/ha")} if p["baseline_t_ha"] is not None else {}), "@context": [context]}


class NullBrokerClient:
    enabled = False
    url = None

    def upsert(self, entities):
        return 0


class NgsiLdBrokerClient:
    """Speaks the same NGSI-LD to the mock and to a real broker, so switching is a change of URL."""
    enabled = True

    def __init__(self, url, tenant="", token="", http=None):
        self.url = url.rstrip("/")
        self.headers = {"Content-Type": "application/ld+json"}
        if tenant:
            self.headers["NGSILD-Tenant"] = tenant
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.http = http or httpx.Client(timeout=TIMEOUT)

    def upsert(self, entities):
        wrong = {e["type"] for e in entities} - {PREDICTION_TYPE}
        if wrong:
            raise ValueError(f"The backend only writes {PREDICTION_TYPE}, not {sorted(wrong)}")
        r = self.http.post(f"{self.url}/ngsi-ld/v1/entityOperations/upsert", params={"options": "update"}, content=json.dumps(entities), headers=self.headers)
        if r.status_code == 207:
            raise RuntimeError(f"Broker rejected some entities: {r.text[:500]}")
        r.raise_for_status()
        return len(entities)

    def subscribe(self, notify_url, context=WEATHER_CONTEXT, types=None, accept="application/json", fmt="normalized", sub_id=None):
        return create_subscription(self.url, subscription_body(notify_url, context, types, accept, fmt, sub_id), self.headers, self.http)


def subscription_body(notify_url, context=WEATHER_CONTEXT, types=None, accept="application/json", fmt="normalized", sub_id=None, watched=None):
    """The subscription this backend needs: weather entities only, never its own predictions."""
    types = list(types or sorted(WEATHER_TYPES))
    if PREDICTION_TYPE in types:
        raise ValueError(f"Refusing to subscribe to {PREDICTION_TYPE}: that would feed predictions back into the backend")
    body = {"type": "Subscription", "description": "Daily weather for yield estimates", "entities": [{"type": t} for t in types],
            "notification": {"format": fmt, "endpoint": {"uri": notify_url, "accept": accept}}, "@context": context}
    if sub_id:
        body["id"] = sub_id
    if watched:
        body["watchedAttributes"] = list(watched)
    return body


def create_subscription(broker_url, body, headers=None, http=None):
    client = http or httpx.Client(timeout=TIMEOUT)
    r = client.post(f"{broker_url.rstrip('/')}/ngsi-ld/v1/subscriptions", content=json.dumps(body), headers={"Content-Type": "application/ld+json", **{k: v for k, v in (headers or {}).items() if k != "Content-Type"}})
    r.raise_for_status()
    return r.headers.get("Location", "")


def make_client(settings):
    return NgsiLdBrokerClient(settings.cb_url, settings.cb_tenant, settings.cb_token) if settings.cb_url else NullBrokerClient()


class WritebackWorker(threading.Thread):
    """Drains unsent predictions in the background, so a slow or absent broker never holds up a notification."""
    def __init__(self, store, client, context, batch=200, retry_seconds=10):
        super().__init__(daemon=True, name="writeback")
        self.store, self.client, self.context, self.batch, self.retry = store, client, context, batch, retry_seconds
        self.wake, self.halt = threading.Event(), threading.Event()
        self.last_error, self.written = None, 0

    def drain(self):
        """Send everything pending. True if nothing failed."""
        while not self.halt.is_set():
            rows = self.store.unsynced(self.batch)
            if not rows:
                return True
            try:
                self.written += self.client.upsert([prediction_entity(p, self.context) for p in rows])
            except Exception as e:
                self.last_error = str(e)[:500]
                log.warning("Write-back failed, will retry: %s", self.last_error)
                return False
            self.store.mark_synced(rows)
            self.last_error = None
        return True

    def run(self):
        while not self.halt.is_set():
            self.wake.wait(timeout=self.retry)
            self.wake.clear()
            if not self.halt.is_set():
                self.drain()

    def stop(self):
        self.halt.set()
        self.wake.set()
