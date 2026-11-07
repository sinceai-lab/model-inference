"""FastAPI routes over service.pipeline. Run: uvicorn service.api:app --host 127.0.0.1 --port 8600"""
import logging
import math
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

import service  # noqa: F401
from service.engine import REGIONS, SCENARIOS, UnknownInput
from service.insights import Insights
from service.insights_api import router as insights_router, what_if
from service.ngsi import PayloadError
from service.pipeline import LiveService

MAX_BODY = 10 * 1024 * 1024
logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


class FeatureRow(BaseModel):
    """One raw feature row, as the model takes it. Every field is required, because the model silently reads a missing value as average."""
    model_config = ConfigDict(extra="forbid")
    crop: str
    farm_id: str
    region: str
    year: int
    clay: float
    irr: float
    soil_clay: float
    soil_silt: float
    soil_fine_sand: float
    soil_sand: float
    soil_organic: float
    sow_doy: float
    mat_doy: float
    gdd_gap: float
    stress_early: float
    stress_sens: float
    stress_late: float
    hot_sens: float
    hot_season: float
    t_sens: float
    rain_postsow: float
    wet_postsow: float
    rain_preharv: float
    blight_days: float
    may_t: float
    rain_season: float
    pet_season: float
    model_set: str = Field("auto", pattern="^(auto|models|long_models)$")

    @field_validator("*")
    @classmethod
    def finite(cls, v):
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v

    @field_validator("region")
    @classmethod
    def known_region(cls, v):
        if v not in REGIONS:
            raise ValueError(f"must be one of {list(REGIONS)}")
        return v


class FieldRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parcel_id: str
    crop: str
    scenario: str
    year: int
    irrigation: Optional[float] = Field(None, ge=0, le=1)

    @field_validator("scenario")
    @classmethod
    def known_scenario(cls, v):
        if v not in SCENARIOS:
            raise ValueError(f"must be one of {list(SCENARIOS)}")
        return v


@asynccontextmanager
async def lifespan(app):
    app.state.live = LiveService()
    app.state.insights = Insights(app.state.live.engine)
    app.state.live.start()
    yield
    app.state.live.stop()


app = FastAPI(title="Apetit live season backend", lifespan=lifespan)
app.include_router(insights_router)


@app.exception_handler(RequestValidationError)
async def clear_422(request, exc):
    errors = exc.errors()
    missing = [".".join(str(x) for x in e["loc"][1:]) for e in errors if e["type"] == "missing"]
    other = [{"field": ".".join(str(x) for x in e["loc"][1:]), "problem": e["msg"], "value": e.get("input")} for e in errors if e["type"] != "missing"]
    text = "; ".join(filter(None, [f"Missing fields: {', '.join(missing)}" if missing else "", "; ".join(f"{e['field']}: {e['problem']}" for e in other)]))
    return JSONResponse(status_code=422, content=dict(detail=text, missing=missing, invalid=[dict(e, value=repr(e["value"])[:100]) for e in other]))


def live(request):
    return request.app.state.live


@app.post("/notify")
async def notify(request: Request):
    """NGSI-LD notification endpoint. A usable envelope gets 200 with a per-entity report; a bad entity doesn't affect the rest."""
    body = await request.body()
    if len(body) > MAX_BODY:
        return _problem(PayloadError(413, "Payload too large", f"Limit is {MAX_BODY} bytes."))
    try:
        return await run_in_threadpool(live(request).handle_notification, body, request.headers.get("content-type"), request.headers.get("link"))
    except PayloadError as e:
        return _problem(e)


def _problem(e):
    return JSONResponse(status_code=e.status, media_type="application/problem+json", content=dict(type="https://uri.etsi.org/ngsi-ld/errors/BadRequestData", title=e.title, detail=e.detail, status=e.status))


@app.post("/predict")
def predict(row: FeatureRow, request: Request):
    d = row.model_dump()
    kind = d.pop("model_set")
    try:
        result = live(request).engine.predict_row(d, kind)
    except UnknownInput as e:
        raise HTTPException(422, detail=str(e))
    return dict(result, label="prediction", flagged=bool(result["out_of_training_range"] or result["warnings"]))


@app.post("/predict/field")
def predict_field(req: FieldRequest, request: Request):
    try:
        return live(request).engine.predict_field(req.parcel_id, req.crop, req.scenario, req.year, req.irrigation)
    except UnknownInput as e:
        raise HTTPException(404, detail=str(e))


@app.post("/insights/what-if")
def insights_what_if(req: FieldRequest, request: Request):
    """POST /predict/field's response as `prediction`, plus what the Try page needs. See docs/INSIGHTS_API.md section 7.2."""
    return what_if(request, req)


@app.get("/predictions")
def predictions(request: Request, cell_id: Optional[str] = None, parcel_id: Optional[str] = None, farm_id: Optional[str] = None, crop: Optional[str] = None, year: Optional[int] = None,
                latest: bool = False, limit: int = Query(1000, ge=1, le=100000), include_features: bool = False):
    rows = live(request).store.predictions(cell_id, parcel_id, farm_id, crop, year, latest, limit)
    if not include_features:
        for r in rows:
            r.pop("features")
    return dict(count=len(rows), label="estimate", predictions=rows)


@app.get("/observations/status")
def observations_status(request: Request, cell_id: Optional[str] = None, year: Optional[int] = None):
    s = live(request)
    return dict(seasons=s.status(cell_id, year), recent_rejected=s.store.recent_rejected(), counters=s.store.counters())


@app.delete("/observations")
def delete_observations(request: Request, cell_id: str, year: int):
    """Clear one season so it can be replayed from the start. Local convenience for testing."""
    return live(request).store.delete_season(cell_id, year)


@app.get("/health")
def health(request: Request):
    return live(request).health()

