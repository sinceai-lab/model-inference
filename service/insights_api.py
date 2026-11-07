"""/insights/* routes over service.insights. Read-only except the what-if, which computes and writes nothing. See docs/INSIGHTS_API.md."""
import hashlib
import json
from functools import wraps
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from service.engine import UnknownInput
from service.insights import Invalid, MissingOutput, NotFound

router = APIRouter(prefix="/insights", tags=["insights"])
Region = Literal["FI_SW", "SE_SKANE"]
Crop = Literal["pea", "turnip_rape", "potato", "carrot", "spinach"]
Story = Literal["below_2c", "current_policies"]
Test = Literal["loyo", "forward"]
FARM, PARCEL, SCOPE = r"^[FS]\d{4}$", r"^[FS]\d{4}-P\d{1,4}$", r"^(all|(FI_SW|SE_SKANE)/[a-z_]{2,32})$"


def insights(request):
    return request.app.state.insights


def _only(request, allowed):
    """Unknown query parameters are refused, so apetit-ui's whitelist and this one stay in step."""
    extra = [k for k in request.query_params if k not in allowed]
    if extra:
        raise RequestValidationError([dict(type="extra_forbidden", loc=("query", k), msg="Extra inputs are not permitted", input=request.query_params[k]) for k in extra])


def _send(request, body):
    """JSON with a 60 s max-age and an ETag of the content, answering If-None-Match with 304."""
    data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
    tag = '"' + hashlib.sha256(data).hexdigest()[:20] + '"'
    headers = {"Cache-Control": "max-age=60", "ETag": tag}
    if request.headers.get("if-none-match") == tag:
        return Response(status_code=304, headers=headers)
    return Response(data, media_type="application/json", headers=headers)


def route(*allowed):
    def wrap(fn):
        @wraps(fn)
        def inner(request: Request, *a, **kw):
            _only(request, allowed)
            try:
                return _send(request, fn(request, *a, **kw))
            except NotFound as e:
                raise HTTPException(404, detail=str(e))
            except MissingOutput as e:
                return JSONResponse(status_code=503, content=dict(detail=str(e), file=e.file))
        return inner
    return wrap


@router.get("/meta")
@route()
def meta(request: Request):
    return insights(request).meta()


@router.get("/options")
@route("region", "crop", "farm_id")
def options(request: Request, region: Optional[Region] = None, crop: Optional[Crop] = None, farm_id: Optional[str] = Query(None, pattern=FARM)):
    if crop and not region:
        raise RequestValidationError([dict(type="missing", loc=("query", "region"), msg="Field required when crop is given", input=None)])
    return insights(request).options(region, crop, farm_id)


@router.get("/advice")
@route("region", "crop", "story")
def advice(request: Request, region: Region, crop: Crop, story: Story):
    return insights(request).advice(region, crop, story)


@router.get("/policy")
@route()
def policy(request: Request):
    return insights(request).policy()


@router.get("/outlook")
@route("region", "crop")
def outlook(request: Request, region: Region, crop: Crop):
    return insights(request).outlook(region, crop)


@router.get("/climate-risk")
@route("scenario")
def climate_risk(request: Request, scenario: Literal["ssp126", "ssp585"]):
    return insights(request).climate_risk(scenario)


@router.get("/euro-risk")
@route()
def euro_risk(request: Request):
    return insights(request).euro_risk()


@router.get("/farms")
@route("region", "crop")
def farms(request: Request, region: Region, crop: Crop):
    return insights(request).farms(region, crop)


@router.get("/soil-effects")
@route("region", "crop")
def soil_effects(request: Request, region: Region, crop: Crop):
    return insights(request).soil_effects(region, crop)


@router.get("/farms/{farm_id}")
@route("crop", "story")
def farm(request: Request, crop: Crop, story: Story, farm_id: str = Path(pattern=FARM)):
    return insights(request).farm(farm_id, crop, story)


@router.get("/fields/{parcel_id}")
@route("crop", "story")
def field(request: Request, crop: Crop, story: Story, parcel_id: str = Path(pattern=PARCEL)):
    return insights(request).field(parcel_id, crop, story)


@router.get("/trust")
@route("test")
def trust(request: Request, test: Test):
    return insights(request).trust(test)


@router.get("/trust/seasons")
@route("region", "crop", "test", "farm_id")
def trust_seasons(request: Request, region: Region, crop: Crop, test: Test, farm_id: Optional[str] = Query(None, pattern=FARM)):
    return insights(request).trust_seasons(region, crop, test, farm_id)


@router.get("/trust/live-replay")
@route("test", "scope")
def live_replay(request: Request, test: Test, scope: str = Query("all", pattern=SCOPE)):
    return insights(request).live_replay(test, scope)


@router.get("/trust/corrections")
@route()
def corrections(request: Request):
    return insights(request).corrections()


def what_if(request, req):
    """Registered from service.api, which owns FieldRequest. prediction is exactly what POST /predict/field returns."""
    _only(request, ())
    eng = request.app.state.live.engine
    try:
        prediction = eng.predict_field(req.parcel_id, req.crop, req.scenario, req.year, req.irrigation)
        return insights(request).what_if(prediction, req.parcel_id, req.crop, req.scenario, req.year, req.irrigation)
    except UnknownInput as e:
        raise HTTPException(404, detail=str(e))
    except Invalid as e:
        raise RequestValidationError([dict(type="value_error", loc=("body", e.field), msg=str(e), input=e.value)])
    except MissingOutput as e:
        return JSONResponse(status_code=503, content=dict(detail=str(e), file=e.file))
