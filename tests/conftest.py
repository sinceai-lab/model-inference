import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import service  # noqa: E402,F401
from service.engine import Engine  # noqa: E402
from service.ngsi import CellMap  # noqa: E402
from service.pipeline import LiveService  # noqa: E402
from service.season import load_normals  # noqa: E402
from service.settings import Settings  # noqa: E402

SUB = "urn:ngsi-ld:Subscription:test"
NOTIFIED = "2025-07-01T06:00:00Z"


@pytest.fixture(scope="session")
def engine():
    return Engine()


@pytest.fixture(scope="session")
def normals():
    return load_normals()


@pytest.fixture(scope="session")
def cells():
    return CellMap()


@pytest.fixture
def live(tmp_path, engine, normals, cells):
    s = LiveService(Settings(db_path=tmp_path / "live.sqlite"), engine=engine, normals=normals, cells=cells)
    yield s
    s.store.close()


def notification(data, **extra):
    return json.dumps({"id": "urn:ngsi-ld:Notification:1", "type": "Notification", "subscriptionId": SUB, "notifiedAt": NOTIFIED, "data": data, **extra})


def normalized(cell="GF0203", day="2025-06-01", t=14.0, tx=20.0, tn=8.0, rain=1.2, pet=3.1):
    return {"id": f"urn:ngsi-ld:WeatherObserved:{cell}", "type": "WeatherObserved", "dateObserved": {"type": "Property", "value": {"@type": "DateTime", "@value": f"{day}T00:00:00Z"}},
            "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [23.1, 60.9]}}, "temperature": {"type": "Property", "value": t, "unitCode": "CEL"},
            "airTemperatureTSA": {"type": "Property", "value": {"avgOverTime": t, "maxOverTime": tx, "minOverTime": tn}, "unitCode": "CEL"}, "precipitation": {"type": "Property", "value": rain, "unitCode": "MMT"},
            "referenceEvapotranspiration": {"type": "Property", "value": pet, "unitCode": "MMT"}, "cellId": {"type": "Property", "value": cell}}


def key_values(cell="GF0203", day="2025-06-01", t=14.0, tx=20.0, tn=8.0, rain=1.2, pet=3.1):
    return {"id": f"urn:ngsi-ld:WeatherObserved:{cell}", "type": "WeatherObserved", "dateObserved": f"{day}T00:00:00Z", "location": {"type": "Point", "coordinates": [23.1, 60.9]}, "temperature": t,
            "airTemperatureTSA": {"avgOverTime": t, "maxOverTime": tx, "minOverTime": tn}, "precipitation": rain, "referenceEvapotranspiration": pet, "cellId": cell}


def concise(cell="GF0203", day="2025-06-01", t=14.0, tx=20.0, tn=8.0, rain=1.2, pet=3.1):
    return {"id": f"urn:ngsi-ld:WeatherObserved:{cell}", "type": "WeatherObserved", "dateObserved": {"@type": "DateTime", "@value": f"{day}T00:00:00Z"}, "location": {"type": "Point", "coordinates": [23.1, 60.9]}, "temperature": {"value": t, "unitCode": "CEL"},
            "airTemperatureTSA": {"value": {"avgOverTime": t, "maxOverTime": tx, "minOverTime": tn}, "unitCode": "CEL"}, "precipitation": {"value": rain, "unitCode": "MMT"}, "referenceEvapotranspiration": {"value": pet, "unitCode": "MMT"}, "cellId": cell}
