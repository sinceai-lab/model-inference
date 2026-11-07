"""Settings, all from the environment. Servers bind to 127.0.0.1 only, so the host isn't a setting."""
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
BACKEND_PORT = 8600
MOCK_PORT = 8601
BACKEND_URL = f"http://{HOST}:{BACKEND_PORT}"
MOCK_URL = f"http://{HOST}:{MOCK_PORT}"
# ETSI GS CIM 009 V1.9.1 core context, and the Smart Data Models one for weather terms.
CORE_CONTEXT = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.9.jsonld"
WEATHER_CONTEXT = "https://raw.githubusercontent.com/smart-data-models/dataModel.Weather/master/context.jsonld"


@dataclass
class Settings:
    db_path: Path = PROJECT / "service_data" / "live.sqlite"
    cb_url: str = ""  # Empty means predictions aren't written back to any broker.
    cb_tenant: str = ""
    cb_token: str = ""
    cb_context: str = CORE_CONTEXT
    fill_counts: str = "expected"  # "expected" or "plain". See service/season.py.
    gap_interp_days: int = 3


def load_settings():
    e = os.environ
    return Settings(db_path=Path(e.get("LIVE_DB", Settings.db_path)), cb_url=e.get("CB_URL", "").rstrip("/"), cb_tenant=e.get("CB_TENANT", ""), cb_token=e.get("CB_TOKEN", ""),
                    cb_context=e.get("CB_CONTEXT", CORE_CONTEXT), fill_counts=e.get("LIVE_FILL_COUNTS", "expected"), gap_interp_days=int(e.get("LIVE_GAP_INTERP_DAYS", 3)))
