"""The mock's NGSI-LD behaviour, loop prevention, and an end-to-end replay across two real server processes."""
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from service.broker_client import NgsiLdBrokerClient, WritebackWorker, prediction_entity, subscription_body
from service.mock_broker import Broker, create_app, plan_days, represent, weather_entity
from service.settings import BACKEND_PORT, BACKEND_URL, MOCK_PORT, MOCK_URL, PROJECT

LD = {"Content-Type": "application/ld+json"}


class RecordingHttp:
    """Stands in for the broker's HTTP client: hands every notification to a function."""
    def __init__(self, handler=None):
        self.sent, self.handler = [], handler

    def post(self, url, content=None, headers=None):
        self.sent.append(dict(url=url, body=content, headers=headers))
        status, payload = self.handler(url, content, headers) if self.handler else (200, {})
        return httpx.Response(status, json=payload)


@pytest.fixture
def mock():
    http = RecordingHttp()
    b = Broker(http=http)
    return TestClient(create_app(b)), b, http


def subscribe(c, **overrides):
    body = dict(subscription_body("http://backend.test/notify"), **overrides)
    r = c.post("/ngsi-ld/v1/subscriptions", content=json.dumps(body), headers=LD)
    assert r.status_code == 201 and r.headers["location"].startswith("/ngsi-ld/v1/subscriptions/")
    return r.headers["location"].rsplit("/", 1)[1]


def test_subscription_is_refused_for_loop_prone_types():
    with pytest.raises(ValueError, match="YieldPrediction"):
        subscription_body("http://x/notify", types=["WeatherObserved", "YieldPrediction"])


def test_context_rules_are_the_same_as_a_real_broker(mock):
    c, _, _ = mock
    body = subscription_body("http://x/notify")
    assert c.post("/ngsi-ld/v1/subscriptions", content=json.dumps({k: v for k, v in body.items() if k != "@context"}), headers=LD).status_code == 400
    assert c.post("/ngsi-ld/v1/subscriptions", content=json.dumps(body), headers={"Content-Type": "application/json"}).status_code == 400
    assert c.post("/ngsi-ld/v1/subscriptions", content=json.dumps(body), headers=dict(LD, Link="<http://c>; rel=\"http://www.w3.org/ns/json-ld#context\"")).status_code == 400
    assert c.post("/ngsi-ld/v1/subscriptions", content="x", headers={"Content-Type": "text/plain"}).status_code == 415


@pytest.mark.parametrize("change", [dict(type="Other"), dict(entities=None), dict(notification={"format": "normalized"}), dict(timeInterval=60)])
def test_bad_subscriptions(mock, change):
    c, _, _ = mock
    assert c.post("/ngsi-ld/v1/subscriptions", content=json.dumps(dict(subscription_body("http://x/notify"), **change)), headers=LD).status_code == 400


def test_upsert_status_codes_and_read_back(mock):
    c, _, _ = mock
    e = {"id": "urn:ngsi-ld:Thing:1", "type": "Thing", "size": {"type": "Property", "value": 1}, "@context": "http://c"}
    r = c.post("/ngsi-ld/v1/entityOperations/upsert", content=json.dumps([e]), headers=LD)
    assert r.status_code == 201 and r.json() == ["urn:ngsi-ld:Thing:1"]
    assert c.post("/ngsi-ld/v1/entityOperations/upsert", content=json.dumps([e]), headers=LD).status_code == 204
    assert c.post("/ngsi-ld/v1/entityOperations/upsert", content="[]", headers=LD).status_code == 400
    partial = c.post("/ngsi-ld/v1/entityOperations/upsert", content=json.dumps([e, {"@context": "http://c"}]), headers=LD)
    assert partial.status_code == 207 and partial.json()["errors"]
    assert c.get("/ngsi-ld/v1/entities", params=dict(type="Thing", options="keyValues")).json()[0]["size"] == 1


def test_notification_shape_follows_the_subscription(mock):
    c, b, http = mock
    subscribe(c, id="urn:ngsi-ld:Subscription:a")
    subscribe(c, id="urn:ngsi-ld:Subscription:b", notification={"format": "keyValues", "endpoint": {"uri": "http://b.test/n", "accept": "application/ld+json"}})
    b.publish([weather_entity("GF0203", "2025-06-01", 14.0, 20.0, 8.0, 1.0, 3.0, 60.9, 23.1)], wait=True)
    first, second = http.sent
    assert 'rel="http://www.w3.org/ns/json-ld#context"' in first["headers"]["Link"] and first["headers"]["Content-Type"] == "application/json"
    n = json.loads(first["body"])
    assert set(n) == {"id", "type", "subscriptionId", "notifiedAt", "data"} and n["type"] == "Notification" and n["data"][0]["temperature"]["type"] == "Property"
    assert second["headers"]["Content-Type"] == "application/ld+json" and "Link" not in second["headers"]
    n = json.loads(second["body"])
    assert "@context" in n and n["data"][0]["temperature"] == 14.0


def test_represent_concise():
    e = weather_entity("GF0203", "2025-06-01", 14.0, 20.0, 8.0, 1.0, 3.0, 60.9, 23.1)
    e["refDevice"] = dict(type="Relationship", object="urn:d")
    out = represent(e, "concise")
    assert out["temperature"] == {"unitCode": "CEL", "value": 14.0} and out["location"]["type"] == "Point" and out["cellId"] == "GF0203" and out["refDevice"] == {"object": "urn:d"}


def test_throttling_loses_days_as_a_real_broker_would(mock):
    c, b, http = mock
    subscribe(c, throttling=60)
    for d in ("2025-06-01", "2025-06-02"):
        b.publish([weather_entity("GF0203", d, 14.0, 20.0, 8.0, 1.0, 3.0)], wait=True)
    assert len(http.sent) == 1 and b.log[-1]["status"] == "throttled"


def test_replay_needs_a_subscription(mock):
    c, _, _ = mock
    r = c.post("/mock/replay", json=dict(cell_id="GF0203", year=2025))
    assert r.status_code == 409 and "subscribe" in r.json()["detail"]


def test_replay_controls_and_faults(mock):
    c, b, http = mock
    subscribe(c)
    job = c.post("/mock/replay", json=dict(cell_id="GF0203", year=2024, start="2024-06-01", end="2024-06-10", days_per_second=0)).json()
    for _ in range(100):
        if c.get(f"/mock/replay/{job['job_id']}").json()["state"] == "finished":
            break
        time.sleep(0.05)
    assert [json.loads(s["body"])["data"][0]["dateObserved"]["value"]["@value"][:10] for s in http.sent] == [f"2024-06-{d:02d}" for d in range(1, 11)]
    http.sent.clear()
    slow = c.post("/mock/replay", json=dict(cell_id="GF0203", year=2024, start="2024-06-01", end="2024-06-30", days_per_second=2)).json()["job_id"]
    c.post(f"/mock/replay/{slow}/pause")
    time.sleep(0.6)
    assert c.get(f"/mock/replay/{slow}").json()["state"] == "paused"
    c.post(f"/mock/replay/{slow}/stop")
    time.sleep(0.2)
    assert c.get(f"/mock/replay/{slow}").json()["state"] == "stopped"
    assert c.post("/mock/replay", json=dict(cell_id="GX0000", year=2024)).status_code == 404


def test_plan_days_applies_faults():
    from service.mock_broker import ReplaySpec
    days = [dict(day=f"2024-06-{d:02d}") for d in range(1, 11)]
    assert len(plan_days(days, ReplaySpec(cell_id="c", year=2024, drop_every=2))) == 5
    assert len(plan_days(days, ReplaySpec(cell_id="c", year=2024, duplicate_every=5))) == 12
    assert [d["day"] for d in plan_days(days, ReplaySpec(cell_id="c", year=2024, drop_dates=["2024-06-03"]))].count("2024-06-03") == 0
    shuffled = plan_days(days, ReplaySpec(cell_id="c", year=2024, shuffle_window=5))
    assert shuffled != days and sorted(d["day"] for d in shuffled) == [d["day"] for d in days]


def wire(live):
    """A mock whose notifications go straight into the backend's logic."""
    def to_backend(url, body, headers):
        try:
            return 200, live.handle_notification(body, headers.get("Content-Type"), headers.get("Link"))
        except Exception as e:
            return getattr(e, "status", 500), dict(title=str(e))
    http = RecordingHttp(to_backend)
    return Broker(http=http), http


def test_a_broker_subscription_on_predictions_cannot_loop(live):
    """Even if someone subscribes the backend to its own YieldPrediction entities on the broker, it ends after one round."""
    b, http = wire(live)
    c = TestClient(create_app(b))
    subscribe(c, id="urn:ngsi-ld:Subscription:all", entities=[{"type": "WeatherObserved"}, {"type": "YieldPrediction"}])
    b.publish([weather_entity("GF0203", "2025-06-01", 14.0, 20.0, 8.0, 1.0, 3.0)], wait=True)
    made = live.store.totals()["predictions"]
    assert made > 0 and len(http.sent) == 1
    worker = WritebackWorker(live.store, BrokerAdapter(c), "http://ctx")
    assert worker.drain() and worker.written == made
    deadline = time.time() + 5
    while time.time() < deadline and len(http.sent) < 2:
        time.sleep(0.02)
    time.sleep(0.2)
    counters = live.store.counters()
    assert counters["entities_ignored"] == made and counters["readings_new"] == 1 and live.store.totals()["predictions"] == made and len(http.sent) == 2
    assert worker.drain() and worker.written == made  # Nothing new to send.


class BrokerAdapter:
    enabled = True
    url = "test"

    def __init__(self, client):
        self.real = NgsiLdBrokerClient("http://testserver", http=client)

    def upsert(self, entities):
        return self.real.upsert(entities)


def test_prediction_entity_shape(live):
    live.handle_notification(json.dumps({"type": "Notification", "subscriptionId": "s", "notifiedAt": "2025-06-01T00:00:00Z", "data": [{"id": "urn:x:GF0203", "type": "WeatherObserved", "dateObserved": "2025-06-01", "temperature": 14.0, "temperatureMax": 20.0, "precipitation": 1.0}]}), "application/json")
    p = live.store.unsynced(1)[0]
    e = prediction_entity(p, "http://ctx")
    assert e["type"] == "YieldPrediction" and e["id"] == f"urn:ngsi-ld:YieldPrediction:{p['parcel_id']}:{p['crop']}:2025"
    assert e["modelName"]["value"] == p["model_name"] and e["observedDays"]["value"] == 1 and e["filledDays"]["value"] == 240 and e["predictionLabel"]["value"] == "estimate" and e["@context"] == ["http://ctx"] and e["computedAt"]["value"]["@value"]


def test_client_only_writes_predictions():
    with pytest.raises(ValueError):
        NgsiLdBrokerClient("http://x", http=RecordingHttp()).upsert([{"id": "a", "type": "WeatherObserved"}])


def test_writeback_failure_keeps_rows_for_retry_and_never_touches_notify(live):
    class Down:
        enabled, url = True, "http://down"

        def upsert(self, entities):
            raise httpx.ConnectError("no broker")
    live.handle_notification(json.dumps({"type": "Notification", "subscriptionId": "s", "notifiedAt": "2025-06-01T00:00:00Z", "data": [{"id": "urn:x:GF0203", "type": "WeatherObserved", "dateObserved": "2025-06-01", "temperature": 14.0, "precipitation": 1.0}]}), "application/json")
    w = WritebackWorker(live.store, Down(), "http://ctx")
    assert w.drain() is False and "no broker" in w.last_error and live.store.count_unsynced() > 0


def _free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


@pytest.fixture(scope="module")
def servers(tmp_path_factory):
    if not (_free(BACKEND_PORT) and _free(MOCK_PORT)):
        pytest.skip(f"Ports {BACKEND_PORT} and {MOCK_PORT} are in use")
    env = dict(os.environ, LIVE_DB=str(tmp_path_factory.mktemp("e2e") / "e2e.sqlite"), CB_URL=MOCK_URL)
    procs = [subprocess.Popen([sys.executable, "-m", "uvicorn", m, "--host", "127.0.0.1", "--port", str(p), "--log-level", "warning"], cwd=PROJECT, env=env) for m, p in (("service.api:app", BACKEND_PORT), ("service.mock_broker:app", MOCK_PORT))]
    try:
        for url in (f"{BACKEND_URL}/health", f"{MOCK_URL}/mock/status"):
            for _ in range(200):
                try:
                    if httpx.get(url, timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.1)
            else:
                pytest.fail(f"{url} didn't start")
        yield
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(timeout=10)


def test_end_to_end_replay_through_the_mock(servers):
    """Subscribe, replay part of a season with faults, and read estimates from the backend and the broker."""
    for fmt, accept in (("normalized", "application/json"), ):
        body = subscription_body(f"{BACKEND_URL}/notify", fmt=fmt, accept=accept)
        assert httpx.post(f"{MOCK_URL}/ngsi-ld/v1/subscriptions", content=json.dumps(body), headers=LD).status_code == 201
    spec = dict(cell_id="GF0203", year=2025, start="2025-05-01", end="2025-05-30", days_per_second=0, drop_dates=["2025-05-10", "2025-05-11"], duplicate_every=7, shuffle_window=4, include_pet=False)
    job = httpx.post(f"{MOCK_URL}/mock/replay", json=spec).json()
    assert job["total"] == 28 + 4
    for _ in range(600):
        job = httpx.get(f"{MOCK_URL}/mock/replay/{job['job_id']}").json()
        if job["state"] == "finished":
            break
        time.sleep(0.1)
    assert job["state"] == "finished" and job["errors"] == 0
    s = httpx.get(f"{BACKEND_URL}/observations/status", params=dict(cell_id="GF0203", year=2025)).json()
    season, counters = s["seasons"][0], s["counters"]
    assert season["observed_days"] == 28 and season["duplicates"] == 4 and season["pet_derived_days"] == 28 and season["last_date"] == "2025-05-30"
    assert 130 in season["missing_doys_before_last"] and season["observed_days"] + season["filled_days"] == 241 and counters["readings_new"] == 28
    p = httpx.get(f"{BACKEND_URL}/predictions", params=dict(cell_id="GF0203", year=2025, latest="true")).json()["predictions"]
    assert len(p) == season["contract_parcels"] and all(x["as_of_date"] == "2025-05-30" and x["observed_days"] == 28 and x["label"] == "estimate" for x in p)
    for _ in range(100):
        h = httpx.get(f"{BACKEND_URL}/health").json()["writeback"]
        if h["pending"] == 0:
            break
        time.sleep(0.1)
    assert h["written"] > 0 and h["last_error"] is None
    r = httpx.get(f"{MOCK_URL}/ngsi-ld/v1/entities", params=dict(type="YieldPrediction", limit=1000))
    assert int(r.headers["NGSILD-Results-Count"]) == len(p)
    assert httpx.get(f"{MOCK_URL}/mock/status").json()["entities"]["YieldPrediction"] == len(p)
    bad = httpx.post(f"{MOCK_URL}/mock/inject", json=dict(kind="bad_batch", cell_id="GF0203", date="2025-05-30"))
    assert bad.json()["outcomes"][0]["status"] == 200 and len(bad.json()["outcomes"][0]["response"]["rejected"]) == 7
    assert httpx.post(f"{MOCK_URL}/mock/inject", json=dict(kind="not_json", cell_id="GF0203", date="2025-05-30")).json()["outcomes"][0]["status"] == 400
    assert httpx.post(f"{MOCK_URL}/mock/reading", json=dict(cell_id="GF0203", date="2025-05-31", temperature=12.0, tmax=18.0, tmin=6.0, precipitation=0.0)).json()["outcomes"][0]["response"]["readings"]["new"] == 1


