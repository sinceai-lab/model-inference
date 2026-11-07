"""docs/cb_handoff is the contract for the broker teammate. tests/fixtures/cb_handoff holds a copy of its examples."""
import json
from pathlib import Path

import pandas as pd
import pytest
from conftest import SUB
from fastapi.testclient import TestClient

from service.mock_broker import Broker, create_app, weather_entity
from service.ngsi import parse_notification

FIXTURES = Path(__file__).parent / "fixtures" / "cb_handoff"
MODEL_COLUMNS = ["farm_id", "region", "year", "clay", "irr", "soil_clay", "soil_silt", "soil_fine_sand", "soil_sand", "soil_organic", "sow_doy", "mat_doy", "gdd_gap", "stress_early", "stress_sens", "stress_late", "hot_sens", "hot_season", "t_sens",
                 "rain_postsow", "wet_postsow", "rain_preharv", "blight_days", "may_t", "rain_season", "pet_season"]


def test_example_notification_parses(cells):
    n = parse_notification((FIXTURES / "notification_example.json").read_bytes(), "application/json", None, cells)
    assert n.subscription_id == "urn:ngsi-ld:Subscription:apetit-weather" and not n.rejected and not n.ignored
    r = n.readings[0]
    assert (r.cell_id, r.day, r.tmean, r.tmax, r.precip, r.pet, r.pet_source) == ("GF0104", "2027-06-15", 14.4, 21.3, 0.0, 4.62, "reported")


def test_example_notification_produces_estimates(live):
    r = live.handle_notification((FIXTURES / "notification_example.json").read_bytes(), "application/json")
    assert r["readings"]["new"] == 1 and r["predictions_written"] > 0 and r["prediction_errors"] == []


def test_evaporation_can_be_left_out(cells):
    doc = json.loads((FIXTURES / "notification_example.json").read_text())
    del doc["data"][0]["referenceEvapotranspiration"]
    r = parse_notification(json.dumps(doc), "application/json", None, cells).readings[0]
    assert r.pet_source == "hargreaves" and r.pet == pytest.approx(4.62, abs=0.5)


def test_mock_sends_the_contract_attributes():
    e = weather_entity("GF0104", "2027-06-15", 14.4, 21.3, None, 0.0, 4.62, lat=60.975, lon=22.625)
    want = json.loads((FIXTURES / "notification_example.json").read_text())["data"][0]
    assert {k: v for k, v in e.items() if k != "source"} == want


def test_example_daily_weather_gives_the_example_estimate(live):
    """The contract's full season, sent as contract entities, gives the contract's expected yield for its first row."""
    rows = pd.read_csv(FIXTURES / "model_input_examples.csv")
    first = rows.iloc[0]
    w = pd.read_csv(FIXTURES / "daily_weather_example.csv")
    entities = [weather_entity(r.cell_id, r.date, r.tmean_c, r.tmax_c, None, r.precip_mm, r.pet_mm) for r in w.itertuples()]
    live.handle_notification(json.dumps({"type": "Notification", "subscriptionId": SUB, "notifiedAt": "2027-11-01T00:00:00Z", "data": entities}), "application/json")
    p = live.store.predictions(parcel_id=first.parcel_id, crop=first.model_key, year=int(first.year), latest=True)
    assert len(p) == 1 and p[0]["filled_days"] == 0 and p[0]["yield_t_ha"] == pytest.approx(first.expected_yield_t_ha, abs=0.002)
    for k in ("sow_doy", "mat_doy", "stress_sens", "hot_season", "rain_preharv", "blight_days", "may_t", "rain_season", "pet_season"):
        assert p[0]["features"][k] == pytest.approx(first[k], abs=0.001)


@pytest.mark.parametrize("i", range(6))
def test_example_model_rows_match_through_predict(engine, i):
    r = pd.read_csv(FIXTURES / "model_input_examples.csv").iloc[i]
    row = dict(r[MODEL_COLUMNS], crop=r.model_key, year=int(r.year))
    assert engine.predict_row(row, r.model_group)["yield_t_ha"] == pytest.approx(r.expected_yield_t_ha, abs=0.002)


def test_example_subscription_is_accepted_once_its_placeholders_are_filled():
    """It carries @context, so it's sent as application/ld+json. Without one, a compliant broker refuses that content type."""
    body = (FIXTURES / "subscription_example.json").read_text().replace("BACKEND_HOST", "127.0.0.1")
    c = TestClient(create_app(Broker()))
    assert c.post("/ngsi-ld/v1/subscriptions", content=body, headers={"Content-Type": "application/ld+json"}).status_code == 201
    no_context = json.loads(body)
    del no_context["@context"]
    no_context["id"] += ":2"
    assert c.post("/ngsi-ld/v1/subscriptions", content=json.dumps(no_context), headers={"Content-Type": "application/ld+json"}).status_code == 400
