import json

import pytest
from conftest import SUB, concise, key_values, normalized, notification

from service.ngsi import PayloadError, parse_notification

LINK = '<https://example.org/context.jsonld>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'


def parse(cells, data, content_type="application/json", link=None, **extra):
    return parse_notification(notification(data, **extra), content_type, link, cells)


@pytest.mark.parametrize("make", [normalized, concise, key_values], ids=["normalized", "concise", "keyValues"])
@pytest.mark.parametrize("media", ["application/json", "application/ld+json", "application/ld+json; charset=utf-8"])
def test_each_representation_gives_the_same_reading(cells, make, media):
    n = parse(cells, [make()], media)
    assert n.subscription_id == SUB and not n.rejected
    r = n.readings[0]
    assert (r.cell_id, r.day, r.tmean, r.tmax, r.tmin, r.precip, r.pet, r.pet_source) == ("GF0203", "2025-06-01", 14.0, 20.0, 8.0, 1.2, 3.1, "reported")


def test_context_from_link_header_and_body(cells):
    assert parse(cells, [normalized()], link=LINK).context == ["https://example.org/context.jsonld"]
    n = parse(cells, [normalized()], "application/ld+json", **{"@context": ["https://example.org/a.jsonld", "https://example.org/b.jsonld"]})
    assert n.context == ["https://example.org/a.jsonld", "https://example.org/b.jsonld"]


def test_expanded_attribute_names_and_inline_context(cells):
    e = key_values()
    expanded = {"https://smartdatamodels.org/dataModel.Weather/precipitation" if k == "precipitation" else "https://uri.etsi.org/ngsi-ld/default-context/temperature" if k == "temperature" else k: v for k, v in e.items()}
    expanded["type"] = "https://smartdatamodels.org/dataModel.Weather/WeatherObserved"
    r = parse(cells, [expanded]).readings[0]
    assert r.precip == 1.2 and r.tmean == 14.0
    aliased = {k: v for k, v in e.items() if k != "precipitation"}
    aliased["rain_today"] = 7.5
    r = parse(cells, [aliased], "application/ld+json", **{"@context": [{"rain_today": "https://smartdatamodels.org/dataModel.Weather/precipitation"}, "https://example.org/c.jsonld"]}).readings[0]
    assert r.precip == 7.5


def test_type_as_list_and_multi_attribute(cells):
    e = normalized()
    e["type"] = ["Thing", "WeatherObserved"]
    e["precipitation"] = [{"type": "Property", "value": 9.0, "datasetId": "urn:ngsi-ld:Dataset:radar"}, {"type": "Property", "value": 2.0}]
    assert parse(cells, [e]).readings[0].precip == 2.0


@pytest.mark.parametrize("value,expected", [("2025-06-01", "2025-06-01"), ("2025-06-01T23:30:00+02:00", "2025-06-01"), ("2016-11-30T07:00:00.00Z", "2016-11-30")])
def test_dates_keep_the_day_as_written(cells, value, expected):
    assert parse(cells, [dict(key_values(), dateObserved=value)]).readings[0].day == expected


def test_date_from_observed_at_when_no_date_observed(cells):
    e = {k: v for k, v in normalized().items() if k != "dateObserved"}
    e["temperature"]["observedAt"] = "2025-06-03T12:00:00Z"
    assert parse(cells, [e]).readings[0].day == "2025-06-03"


def test_units_are_converted(cells):
    e = normalized()
    e["temperature"] = {"type": "Property", "value": 287.15, "unitCode": "KEL"}
    e["airTemperatureTSA"] = {"type": "Property", "value": {"maxOverTime": 68.0, "minOverTime": 46.4}, "unitCode": "FAH"}
    e["precipitation"] = {"type": "Property", "value": 0.5, "unitCode": "CMT"}
    r = parse(cells, [e]).readings[0]
    assert r.tmean == pytest.approx(14.0) and r.tmax == pytest.approx(20.0) and r.tmin == pytest.approx(8.0) and r.precip == 5.0


def test_cell_from_id_or_location(cells):
    e = {k: v for k, v in key_values().items() if k != "cellId"}
    assert parse(cells, [e]).readings[0].cell_id == "GF0203"
    # The first grid row is at 60.725 N, 21.625 E.
    no_cell_in_id = dict(e, id="urn:ngsi-ld:WeatherObserved:station-7", location={"type": "Point", "coordinates": [21.63, 60.73]})
    assert parse(cells, [no_cell_in_id]).readings[0].cell_id == "GF0000"
    far = dict(no_cell_in_id, location={"type": "Point", "coordinates": [10.0, 40.0]})
    assert "from the nearest grid cell" in parse(cells, [far]).rejected[0]["reason"]


def test_tsa_with_averagevalue_as_in_the_smart_data_models_spec(cells):
    e = {k: v for k, v in key_values().items() if k != "temperature"}
    e["airTemperatureTSA"] = {"averageValue": 13.0, "maxOverTime": 18.0, "minOverTime": 7.0}
    r = parse(cells, [e]).readings[0]
    assert (r.tmean, r.tmax, r.tmin) == (13.0, 18.0, 7.0)


def test_pet_is_derived_when_the_broker_has_none(cells):
    """2010-06-02 in GF0000 is 12.1 / 18.6 / 5.7 C, with pet_mm 4.04 in the package."""
    e = dict(key_values("GF0000", "2010-06-02", 12.1, 18.6, 5.7, 0.0))
    del e["referenceEvapotranspiration"]
    r = parse(cells, [e]).readings[0]
    assert r.pet_source == "hargreaves" and r.pet == pytest.approx(4.04, abs=0.02)
    e["airTemperatureTSA"] = {"avgOverTime": 12.1, "maxOverTime": 18.6}
    assert parse(cells, [e]).readings[0].pet == pytest.approx(4.04, abs=0.05)


def test_partial_readings_are_kept(cells):
    r = parse(cells, [{"id": "urn:x:GF0203", "type": "WeatherObserved", "dateObserved": "2025-06-01", "precipitation": 3.0}]).readings[0]
    assert r.precip == 3.0 and r.tmean is None and r.pet is None


@pytest.mark.parametrize("change,reason", [
    (dict(temperature="warm"), "not a number"), (dict(temperature=True), "not a number"), (dict(temperature=200), "plausible range"), (dict(precipitation=-1), "plausible range"),
    (dict(dateObserved="soon"), "ISO 8601"), (dict(dateObserved="2025-13-45"), "not valid"), (dict(dateObserved="1800-06-01"), "outside"), (dict(cellId="GX0000"), "unknown grid cell"),
    (dict(temperature={"value": 14, "unitCode": "BTU"}), "unitCode"), (dict(airTemperatureTSA={"avgOverTime": 14, "maxOverTime": 10}), "below tmean"),
])
def test_bad_entity_loses_only_itself(cells, change, reason):
    n = parse(cells, [key_values(day="2025-06-02"), dict(key_values(), **change), key_values(day="2025-06-03")])
    assert [r.day for r in n.readings] == ["2025-06-02", "2025-06-03"]
    assert len(n.rejected) == 1 and n.rejected[0]["index"] == 1 and reason in n.rejected[0]["reason"]


def test_non_objects_missing_type_and_empty_values_are_rejected(cells):
    n = parse(cells, ["text", 5, None, {"id": "urn:x:1"}, {"id": "urn:x:GF0203", "type": "WeatherObserved", "dateObserved": "2025-06-01"}, key_values()])
    assert len(n.readings) == 1 and len(n.rejected) == 5


def test_other_types_are_ignored_not_stored(cells):
    n = parse(cells, [{"id": "urn:ngsi-ld:YieldPrediction:a", "type": "YieldPrediction", "estimatedYield": 3}, {"id": "urn:ngsi-ld:WeatherForecast:b", "type": "WeatherForecast", "temperature": 3}])
    assert not n.readings and not n.rejected and [i["type"] for i in n.ignored] == ["YieldPrediction", "WeatherForecast"]


@pytest.mark.parametrize("body,status", [
    ("{not json", 400), ("[1, 2]", 400), ('{"type": "Notification", "temperature": NaN, "subscriptionId": "s", "notifiedAt": "2025-01-01T00:00:00Z", "data": []}', 400),
    (json.dumps({"type": "Notification", "notifiedAt": "2025-01-01T00:00:00Z", "data": []}), 400), (json.dumps({"type": "Notification", "subscriptionId": "s", "data": []}), 400),
    (json.dumps({"type": "Notification", "subscriptionId": "s", "notifiedAt": "2025-01-01T00:00:00Z"}), 400), (json.dumps({"type": "Notification", "subscriptionId": "s", "notifiedAt": "whenever", "data": []}), 400),
    (json.dumps({"type": "Other", "subscriptionId": "s", "notifiedAt": "2025-01-01T00:00:00Z", "data": []}), 400), (json.dumps({"type": "Notification", "subscriptionId": "s", "notifiedAt": "2025-01-01T00:00:00Z", "data": {"type": "FeatureCollection"}}), 400),
])
def test_bad_envelopes(cells, body, status):
    with pytest.raises(PayloadError) as e:
        parse_notification(body, "application/json", None, cells)
    assert e.value.status == status


@pytest.mark.parametrize("media", ["text/plain", "application/geo+json", None])
def test_other_media_types_are_refused(cells, media):
    with pytest.raises(PayloadError) as e:
        parse_notification(notification([]), media, None, cells)
    assert e.value.status == 415
