import json
import pickle
import shutil

import numpy as np
import pandas as pd
import pytest
from conftest import SUB, concise, key_values, normalized, notification
from fastapi.testclient import TestClient

from config import CACHE
from features import FEATURES
from service.engine import Engine
from service.pipeline import LiveService
from service.settings import Settings

ROW = dict(crop="pea", farm_id="F0001", region="FI_SW", year=2027, clay=30, irr=0, soil_clay=1, soil_silt=0, soil_fine_sand=0, soil_sand=0, soil_organic=0, sow_doy=115, mat_doy=205, gdd_gap=0, stress_early=.2, stress_sens=.35, stress_late=.4, hot_sens=0,
           hot_season=2, t_sens=16, rain_postsow=15, wet_postsow=4, rain_preharv=25, blight_days=14, may_t=10, rain_season=170, pet_season=330)
# models.pkl is replaceable. The pinned value below belongs to this file, so it's only checked against this file.
KNOWN_MODELS, KNOWN_VALUE = "4be9d9e102c3", 3.285


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.delenv("CB_URL", raising=False)
    from service.api import app
    with TestClient(app) as c:
        yield c


def post(client, data, content_type="application/json", **headers):
    return client.post("/notify", content=notification(data), headers={"Content-Type": content_type, **headers})


def test_predict_matches_the_model_directly(client):
    r = client.post("/predict", json=ROW)
    assert r.status_code == 200
    with open(CACHE / "models.pkl", "rb") as fh:
        models = pickle.load(fh)["models"]
    d = pd.DataFrame([{k: v for k, v in ROW.items() if k != "crop"}])
    assert r.json()["yield_t_ha"] == pytest.approx(float(np.exp(models["pea"].predict_log(d))[0]))
    assert r.json()["model_name"] == "models[pea]" and r.json()["technology_year"] == 2027


def test_predict_reproduces_the_known_value(client, engine):
    if engine.version != KNOWN_MODELS:
        pytest.skip(f"models.pkl has been replaced ({engine.version}), so the pinned value no longer applies")
    assert round(client.post("/predict", json=ROW).json()["yield_t_ha"], 3) == KNOWN_VALUE


@pytest.mark.parametrize("field", ["farm_id", "region", "year", "clay", "irr", "soil_clay", "soil_organic", "crop"] + FEATURES)
def test_predict_rejects_each_missing_field(client, field):
    r = client.post("/predict", json={k: v for k, v in ROW.items() if k != field})
    assert r.status_code == 422 and r.json()["missing"] == [field] and field in r.json()["detail"]


def test_predict_lists_every_missing_field(client):
    r = client.post("/predict", json=dict(crop="pea"))
    assert r.status_code == 422 and len(r.json()["missing"]) == 26 and r.json()["detail"].startswith("Missing fields:")


@pytest.mark.parametrize("change,word", [(dict(clay="heavy"), "clay"), (dict(region="Mars"), "region"), (dict(crop="kale"), "kale"), (dict(extra_thing=1), "extra_thing"), (dict(model_set="newest"), "model_set")])
def test_predict_rejects_bad_values(client, change, word):
    r = client.post("/predict", json=dict(ROW, **change))
    assert r.status_code == 422 and word in json.dumps(r.json())


def test_predict_rejects_nan_rather_than_treating_it_as_average(client):
    r = client.post("/predict", content=json.dumps(dict(ROW, may_t=float("nan"))), headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_predict_flags_values_outside_training_range(client):
    ok = client.post("/predict", json=dict(ROW, year=2025)).json()
    assert ok["out_of_training_range"] == [] and ok["flagged"] is False
    r = client.post("/predict", json=dict(ROW, year=2025, blight_days=50, may_t=30)).json()
    assert {f["field"] for f in r["out_of_training_range"]} == {"blight_days", "may_t"} and r["flagged"] is True
    assert r["out_of_training_range"][0]["training_max"] < 50


def test_predict_flags_unknown_farm_and_odd_soil(client):
    r = client.post("/predict", json=dict(ROW, year=2025, farm_id="F9999", soil_clay=0)).json()
    assert r["flagged"] and any("F9999" in w for w in r["warnings"]) and any("soil_" in w for w in r["warnings"])


def test_predict_uses_long_models_after_2031(client):
    r = client.post("/predict", json=dict(ROW, year=2050)).json()
    assert r["model_name"] == "long_models[pea]" and r["technology_year"] == 2025
    with open(CACHE / "models.pkl", "rb") as fh:
        long_pea = pickle.load(fh)["long_models"]["pea"]
    d = pd.DataFrame([{k: v for k, v in ROW.items() if k != "crop"}]).assign(year=2025)
    assert r["yield_t_ha"] == pytest.approx(float(np.exp(long_pea.predict_log(d))[0]))


def test_predict_field_matches_the_predictor(client, engine):
    body = dict(parcel_id="F0001-P01", crop="pea", scenario="ssp245", year=2027)
    r = client.post("/predict/field", json=body).json()
    assert r["yield_t_ha"] == pytest.approx(engine.predictor.predict("F0001-P01", "pea", "ssp245", 2027)["pred"]) and r["cell_id"] == "GF0104" and r["baseline_t_ha"] > 0


@pytest.mark.parametrize("body,code", [(dict(parcel_id="NOPE", crop="pea", scenario="historical", year=2020), 404), (dict(parcel_id="F0001-P01", crop="kale", scenario="historical", year=2020), 404),
                                       (dict(parcel_id="F0001-P01", crop="pea", scenario="ssp999", year=2020), 422), (dict(parcel_id="F0001-P01", crop="pea", scenario="ssp585", year=2028), 404), (dict(crop="pea"), 422)])
def test_predict_field_errors(client, body, code):
    assert client.post("/predict/field", json=body).status_code == code


def test_notify_stores_and_predicts_in_every_representation(client):
    for i, make in enumerate((normalized, concise, key_values)):
        r = post(client, [make(day=f"2025-06-0{i + 1}")], "application/ld+json" if i else "application/json")
        assert r.status_code == 200 and r.json()["readings"]["new"] == 1 and r.json()["predictions_written"] > 0
    preds = client.get("/predictions", params=dict(cell_id="GF0203", year=2025, crop="pea", latest="true")).json()
    assert preds["label"] == "estimate" and preds["count"] > 0
    p = preds["predictions"][0]
    assert p["as_of_date"] == "2025-06-03" and p["observed_days"] == 3 and p["label"] == "estimate" and p["model_name"] == "models[pea]" and p["observed_days"] + p["filled_days"] == 241
    assert p["filled_gap_days"] == 92 and p["filled_future_days"] == 146


def test_notify_returns_problem_for_bad_envelope(client):
    r = client.post("/notify", content="{nope", headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.headers["content-type"].startswith("application/problem+json") and r.json()["title"] == "Invalid JSON"
    assert client.post("/notify", content=notification([]), headers={"Content-Type": "text/plain"}).status_code == 415
    status = client.get("/observations/status").json()
    assert status["counters"]["notifications_refused"] == 2 and status["recent_rejected"][0]["reason"]


def test_bad_entity_in_a_batch_keeps_the_good_ones(client):
    r = post(client, [key_values(day="2025-06-01"), {"id": "urn:x:GF0203", "type": "WeatherObserved", "dateObserved": "nope", "temperature": 1}, "junk", key_values(day="2025-06-02")]).json()
    assert r["readings"]["new"] == 2 and len(r["rejected"]) == 2 and r["predictions_written"] > 0
    assert client.get("/observations/status", params=dict(cell_id="GF0203", year=2025)).json()["seasons"][0]["observed_days"] == 2


def test_duplicate_is_ignored_and_does_not_recompute(client):
    post(client, [key_values()])
    before = client.get("/predictions", params=dict(cell_id="GF0203", year=2025, limit=5)).json()["predictions"][0]["computed_at"]
    r = post(client, [key_values()]).json()
    assert r["readings"]["duplicate"] == 1 and r["predictions_written"] == 0 and r["seasons_recomputed"] == []
    assert client.get("/predictions", params=dict(cell_id="GF0203", year=2025, limit=5)).json()["predictions"][0]["computed_at"] == before
    assert client.get("/observations/status", params=dict(cell_id="GF0203")).json()["seasons"][0]["duplicates"] == 1


def test_batch_recomputes_each_season_once(live, monkeypatch):
    calls = []
    original = live.recompute
    monkeypatch.setattr(live, "recompute", lambda c, y: calls.append((c, y)) or original(c, y))
    live.handle_notification(notification([key_values(day=f"2025-06-{d:02d}") for d in range(1, 11)]), "application/json")
    assert calls == [("GF0203", 2025)]


def test_correction_replaces_and_stale_is_ignored(live):
    new = lambda t, at: live.handle_notification(json.dumps({"type": "Notification", "subscriptionId": SUB, "notifiedAt": at, "data": [key_values(t=t, tx=t + 5)]}), "application/json")["readings"]
    assert new(14.0, "2025-06-02T00:00:00Z")["new"] == 1
    assert new(16.0, "2025-06-03T00:00:00Z")["corrected"] == 1
    assert new(12.0, "2025-06-02T12:00:00Z")["stale"] == 1
    assert live.store.season("GF0203", 2025)[0]["tmean"] == 16.0 and live.store.season("GF0203", 2025)[0]["revisions"] == 1


def test_partial_update_merges_with_what_is_stored(live):
    live.handle_notification(notification([key_values()]), "application/json")
    r = live.handle_notification(json.dumps({"type": "Notification", "subscriptionId": SUB, "notifiedAt": "2025-08-01T00:00:00Z", "data": [{"id": "urn:x:GF0203", "type": "WeatherObserved", "dateObserved": "2025-06-01", "precipitation": 8.0}]}), "application/json")
    row = live.store.season("GF0203", 2025)[0]
    assert r["readings"]["corrected"] == 1 and row["precip"] == 8.0 and row["tmean"] == 14.0 and row["pet"] == 3.1


def latest(live, crop="pea"):
    return {p["parcel_id"]: p["yield_t_ha"] for p in live.store.predictions("GF0203", year=2025, crop=crop, latest=True, limit=1000)}


def test_arrival_order_does_not_change_the_final_estimate(tmp_path, engine, normals, cells):
    days = [key_values(day=f"2025-06-{d:02d}", t=10.0 + d % 7, tx=16.0 + d % 7, tn=5.0, rain=float(d % 4)) for d in range(1, 21)]
    shuffled = list(days)
    np.random.default_rng(3).shuffle(shuffled)
    results = []
    for name, order in (("a", days), ("b", shuffled)):
        s = LiveService(Settings(db_path=tmp_path / f"{name}.sqlite"), engine=engine, normals=normals, cells=cells)
        for d in order:
            s.handle_notification(notification([d]), "application/json")
        results.append(latest(s))
        assert s.store.predictions("GF0203", year=2025, crop="pea", latest=True, limit=1)[0]["as_of_date"] == "2025-06-20"
        s.store.close()
    assert results[0] == pytest.approx(results[1])


def test_missing_days_are_filled_and_reported(live):
    live.handle_notification(notification([key_values(day=d) for d in ("2025-06-01", "2025-06-02", "2025-06-05", "2025-06-20")]), "application/json")
    s = live.status("GF0203", 2025)[0]
    assert s["observed_days"] == 4 and s["filled_gap_days"] == 92 + 16 and s["filled_future_days"] == 300 - 171 and s["observed_days"] + s["filled_days"] == 241
    assert 154 in s["missing_doys_before_last"] and 171 not in s["missing_doys_before_last"]


def test_out_of_season_reading_is_stored_without_recompute(live):
    r = live.handle_notification(notification([key_values(day="2025-01-15", t=-3.0, tx=0.0, tn=-6.0)]), "application/json")
    assert r["readings"]["new"] == 1 and r["readings"]["out_of_season"] == 1 and r["predictions_written"] == 0
    assert live.status("GF0203", 2025)[0]["in_window_days"] == 0


def test_cell_without_contract_crops_stores_but_predicts_nothing(live):
    r = live.handle_notification(notification([key_values(cell="GF0203", day="2045-06-01")]), "application/json")
    assert r["readings"]["new"] == 1 and r["predictions_written"] == 0


def test_observations_survive_a_restart(tmp_path, engine, normals, cells):
    path = tmp_path / "durable.sqlite"
    a = LiveService(Settings(db_path=path), engine=engine, normals=normals, cells=cells)
    a.handle_notification(notification([key_values()]), "application/json")
    n = a.store.totals()["predictions"]
    a.store.close()
    b = LiveService(Settings(db_path=path), engine=engine, normals=normals, cells=cells)
    assert b.store.totals() == dict(observations=1, predictions=n, rejected=0) and b.handle_notification(notification([key_values()]), "application/json")["readings"]["duplicate"] == 1
    b.store.close()


def test_failed_recompute_keeps_the_reading(live, monkeypatch):
    monkeypatch.setattr(live.engine, "predict_cell", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = live.handle_notification(notification([key_values()]), "application/json")
    assert r["prediction_errors"][0]["error"] == "boom" and live.store.totals()["observations"] == 1


def test_estimate_on_a_full_season_matches_the_direct_prediction(live, engine):
    from service.season import assemble
    w = pd.read_parquet(__import__("config").DATA / "04_climate/weather_daily_1991_2060.parquet", filters=[("cell_id", "==", "GF0203"), ("scenario", "==", "historical")])
    w["date"] = pd.to_datetime(w.date)
    w = w[(w.date.dt.year == 2025) & w.date.dt.dayofyear.between(60, 300)].sort_values("date")
    data = [key_values(day=str(r.date.date()), t=r.tmean_c, tx=r.tmax_c, tn=r.tmin_c, rain=r.precip_mm, pet=r.pet_mm) for r in w.itertuples()]
    live.handle_notification(notification(data), "application/json")
    p = live.store.predictions("GF0203", year=2025, crop="pea", latest=True, limit=1)[0]
    assert p["filled_days"] == 0 and p["filled_to_maturity"] == 0
    assert p["yield_t_ha"] == pytest.approx(engine.predictor.predict(p["parcel_id"], "pea", "historical", 2025)["pred"], rel=1e-9)
    assert assemble("GF0203", 2025, live.store.season("GF0203", 2025), live.normals["GF0203"]).last_doy == 300


def test_models_file_is_replaceable(tmp_path, monkeypatch):
    path = tmp_path / "models.pkl"
    shutil.copy(CACHE / "models.pkl", path)
    e = Engine(models_path=path)
    first = e.version
    row = {k: v for k, v in ROW.items()}
    before = e.predict_row(row)["yield_t_ha"]
    with open(path, "rb") as fh:
        saved = pickle.load(fh)
    saved["models"]["pea"].m.intercept_ += np.log(2)
    with open(path, "wb") as fh:
        pickle.dump(saved, fh)
    after = e.predict_row(row)
    assert after["model_version"] != first and after["yield_t_ha"] == pytest.approx(before * 2)
    path.write_bytes(b"broken")
    still = e.predict_row(row)
    assert still["yield_t_ha"] == pytest.approx(before * 2) and "Couldn't load" in e.info()["load_error"]


def test_health_and_delete(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["models"]["version"] and h["writeback"]["enabled"] is False
    post(client, [key_values()])
    assert client.delete("/observations", params=dict(cell_id="GF0203", year=2025)).json()["observations"] == 1
    assert client.get("/predictions", params=dict(cell_id="GF0203")).json()["count"] == 0


