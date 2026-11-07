"""Parse NGSI-LD notifications (ETSI GS CIM 009 V1.9.1, clauses 5.3.1, 4.5.2-4.5.4, 4.7.3) into daily readings. No web code.

Handles normalized, concise and keyValues/simplified entities, application/json and application/ld+json bodies, and @context in the
body, on the entity or in a Link header. Remote contexts are recorded but never fetched: attribute names are resolved through inline
context terms, then by the last segment of an expanded URI, then through the alias table below. A bad envelope raises PayloadError.
A bad entity goes to `rejected` and the rest of the batch carries on.
"""
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
from scipy.spatial import cKDTree

from config import DATA
from service.season import doy_of, hargreaves_pet

WEATHER_TYPES = {"WeatherObserved"}
PREDICTION_TYPE = "YieldPrediction"
CONTEXT_REL = "http://www.w3.org/ns/json-ld#context"
JSON_TYPES = {"application/json", "application/ld+json"}
MAX_CELL_DISTANCE_DEG = 0.18  # Half the diagonal of the 0.25 degree grid.
FIRST_YEAR, LAST_YEAR = 1991, 2060

ALIASES = {"tmean": ["temperature", "tmean_c", "tmean", "airTemperature", "temperatureMean", "averageTemperature", "airTemperatureAvg"],
           "tmax": ["temperatureMax", "tmax_c", "tmax", "maxTemperature", "airTemperatureMax"], "tmin": ["temperatureMin", "tmin_c", "tmin", "minTemperature", "airTemperatureMin"],
           "precip": ["precipitation", "precip_mm", "precip", "rainfall"], "pet": ["referenceEvapotranspiration", "evapotranspiration", "potentialEvapotranspiration", "et0", "pet_mm", "pet"]}
TSA = {"tmean": ["avgOverTime", "averageValue"], "tmax": ["maxOverTime"], "tmin": ["minOverTime"]}
DATE_NAMES = ["dateObserved", "date", "observationDate"]
CELL_NAMES = ["cellId", "cell_id", "gridCell", "refGridCell", "refClimateGridCell"]
CELL_RE = re.compile(r"\b(G[FS]\d{4})\b")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}(?::?\d{2})?)?)?$")
TEMP = {None: lambda x: x, "CEL": lambda x: x, "KEL": lambda x: x - 273.15, "FAH": lambda x: (x - 32) / 1.8}
DEPTH = {None: lambda x: x, "MMT": lambda x: x, "CMT": lambda x: x * 10, "MTR": lambda x: x * 1000}
UNITS = dict(tmean=TEMP, tmax=TEMP, tmin=TEMP, precip=DEPTH, pet=DEPTH)
LIMITS = dict(tmean=(-60, 60), tmax=(-60, 65), tmin=(-70, 60), precip=(0, 500), pet=(0, 30))


class PayloadError(Exception):
    """The whole notification is unusable. status is 400, 413 or 415."""
    def __init__(self, status, title, detail):
        super().__init__(detail)
        self.status, self.title, self.detail = status, title, detail


class EntityError(ValueError):
    pass


@dataclass
class Reading:
    cell_id: str
    day: str
    tmean: float = None
    tmax: float = None
    tmin: float = None
    precip: float = None
    pet: float = None
    pet_source: str = None
    entity_id: str = None
    warnings: list = field(default_factory=list)


@dataclass
class Notification:
    id: str
    subscription_id: str
    notified_at: str
    content_type: str
    context: list
    readings: list
    rejected: list
    ignored: list


class CellMap:
    """Resolves an entity to a grid cell: explicit attribute, then the entity id, then nearest cell to its location."""
    def __init__(self, cells=None):
        c = cells if cells is not None else pd.read_csv(DATA / "01_master/climate_grid_cells.csv")
        self.ids = c.cell_id.to_numpy()
        self.lat = dict(zip(c.cell_id, c.lat))
        self.tree = cKDTree(c[["lat", "lon"]].to_numpy())

    def nearest(self, lat, lon):
        dist, i = self.tree.query([lat, lon])
        if dist > MAX_CELL_DISTANCE_DEG:
            raise EntityError(f"location ({lat}, {lon}) is {dist:.2f} degrees from the nearest grid cell, limit {MAX_CELL_DISTANCE_DEG}")
        return str(self.ids[i])


def short_name(key, inline=None):
    """Compact a term through inline @context mappings, and an expanded URI to its last segment."""
    mapped = (inline or {}).get(key, key)
    if isinstance(mapped, dict):
        mapped = mapped.get("@id", key)
    return re.split(r"[#/:]", str(mapped))[-1]


def inline_terms(context):
    """Term definitions from an inline @context. URL entries have no terms here, as they aren't fetched."""
    items = context if isinstance(context, list) else [context]
    terms = {}
    for item in items:
        if isinstance(item, dict):
            terms.update(item)
    return terms


def link_context(header):
    """The @context URL from a Link header, if any."""
    for part in (header or "").split(","):
        m = re.match(r'\s*<([^>]*)>(.*)', part)
        if m and CONTEXT_REL in m.group(2):
            return m.group(1)
    return None


def plain(raw):
    """(value, unitCode, observedAt) of an attribute in any representation. Multi-attributes use the default instance, else the first."""
    if isinstance(raw, list) and raw and all(isinstance(x, dict) and ("value" in x or "object" in x) for x in raw):
        raw = next((x for x in raw if "datasetId" not in x), raw[0])
    if isinstance(raw, dict):
        unit, seen = raw.get("unitCode"), raw.get("observedAt")
        for k in ("value", "@value", "object"):
            if k in raw:
                inner = raw[k]
                return (inner["@value"] if isinstance(inner, dict) and "@value" in inner else inner), unit, seen
    return raw, None, None


def _number(name, raw, unit):
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise EntityError(f"{name} is not a number: {raw!r}")
    if unit not in UNITS[name]:
        raise EntityError(f"{name} has unsupported unitCode {unit!r}")
    value = float(UNITS[name][unit](raw))
    low, high = LIMITS[name]
    if not low <= value <= high:
        raise EntityError(f"{name} {value:g} is outside the plausible range {low} to {high}")
    return value


def _day(raw):
    value, _, seen = plain(raw)
    m = DATE_RE.match(value) if isinstance(value, str) else None
    if not m:
        raise EntityError(f"date is not ISO 8601: {value!r}")
    try:
        day = date.fromisoformat(m.group(1))
    except ValueError as e:
        raise EntityError(f"date is not valid: {value!r}") from e
    if not FIRST_YEAR <= day.year <= LAST_YEAR:
        raise EntityError(f"year {day.year} is outside {FIRST_YEAR}-{LAST_YEAR}")
    return day.isoformat()


def _cell(attrs, entity_id, cells, warnings):
    from_attr = next((plain(attrs[n])[0] for n in CELL_NAMES if n in attrs), None)
    if from_attr is not None:
        m = CELL_RE.search(str(from_attr))
        if not m or m.group(1) not in cells.lat:
            raise EntityError(f"unknown grid cell {from_attr!r}")
        return m.group(1)
    m = CELL_RE.search(entity_id or "")
    if m and m.group(1) in cells.lat:
        return m.group(1)
    geo = plain(attrs["location"])[0] if "location" in attrs else None
    if isinstance(geo, dict) and geo.get("type") == "Point" and len(geo.get("coordinates") or []) >= 2:
        lon, lat = geo["coordinates"][:2]
        if isinstance(lon, (int, float)) and isinstance(lat, (int, float)):
            return cells.nearest(lat, lon)
        raise EntityError("location coordinates aren't numbers")
    if m:
        raise EntityError(f"unknown grid cell {m.group(1)!r}")
    raise EntityError("no grid cell: expected a cellId attribute, a cell in the entity id, or a Point location")


def parse_entity(entity, terms, cells):
    """One entity to one Reading. Raises EntityError with a reason a person can act on."""
    entity_terms = {**terms, **inline_terms(entity.get("@context", []))}
    attrs = {short_name(k, entity_terms): v for k, v in entity.items() if k not in ("id", "type", "@context", "@id", "@type")}
    entity_id = entity.get("id")
    warnings = []
    cell = _cell(attrs, entity_id, cells, warnings)
    values, seen = {}, None
    for name, names in ALIASES.items():
        hit = next((n for n in names if n in attrs), None)
        if hit:
            raw, unit, at = plain(attrs[hit])
            values[name] = _number(name, raw, unit)
            seen = seen or at
    if "airTemperatureTSA" in attrs:
        tsa, unit, at = plain(attrs["airTemperatureTSA"])
        seen = seen or at
        if isinstance(tsa, dict):
            for name, keys in TSA.items():
                raw = next((plain(tsa[k])[0] for k in keys if k in tsa), None)
                if values.get(name) is None and raw is not None:
                    values[name] = _number(name, raw, unit)
    name_date = next((n for n in DATE_NAMES if n in attrs), None)
    if name_date:
        day = _day(attrs[name_date])
    elif seen:
        day = _day(seen)
    else:
        raise EntityError("no date: expected dateObserved, or observedAt on an attribute")
    r = Reading(cell, day, values.get("tmean"), values.get("tmax"), values.get("tmin"), values.get("precip"), values.get("pet"), entity_id=entity_id, warnings=warnings)
    if r.tmean is None and r.tmax is not None and r.tmin is not None:
        r.tmean = (r.tmax + r.tmin) / 2
    if r.tmean is None and r.precip is None and r.tmax is None:
        raise EntityError("no usable weather values: expected temperature or precipitation")
    if r.tmax is not None and r.tmean is not None and r.tmax < r.tmean:
        raise EntityError(f"tmax {r.tmax:g} is below tmean {r.tmean:g}")
    if r.tmin is not None and r.tmean is not None and r.tmin > r.tmean:
        raise EntityError(f"tmin {r.tmin:g} is above tmean {r.tmean:g}")
    if r.pet is not None:
        r.pet_source = "reported"
    elif r.tmean is not None and r.tmax is not None:
        tmin = r.tmin if r.tmin is not None else 2 * r.tmean - r.tmax
        r.pet, r.pet_source = hargreaves_pet(r.tmean, r.tmax, tmin, cells.lat[cell], doy_of(day)), "hargreaves"
    return r


def entity_type(entity):
    kinds = entity.get("type", entity.get("@type"))
    return [short_name(k) for k in (kinds if isinstance(kinds, list) else [kinds]) if k]


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def parse_notification(body, content_type, link_header, cells, weather_types=WEATHER_TYPES):
    media = (content_type or "").split(";")[0].strip().lower()
    if media not in JSON_TYPES:
        raise PayloadError(415, "Unsupported media type", f"Content-Type must be application/json or application/ld+json, not {media or 'missing'!r}.")
    try:
        doc = json.loads(body, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as e:
        raise PayloadError(400, "Invalid JSON", f"The body isn't valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise PayloadError(400, "Not a notification", "The body must be a JSON object.")
    if doc.get("type", "Notification") != "Notification":
        raise PayloadError(400, "Not a notification", f"type must be Notification, not {doc.get('type')!r}.")
    missing = [k for k in ("subscriptionId", "notifiedAt", "data") if k not in doc]
    if missing:
        raise PayloadError(400, "Not a notification", f"Missing required members: {', '.join(missing)}.")
    if not isinstance(doc["subscriptionId"], str) or not doc["subscriptionId"]:
        raise PayloadError(400, "Not a notification", "subscriptionId must be a non-empty string.")
    if not isinstance(doc["data"], list):
        raise PayloadError(400, "Not a notification", "data must be an array of entities. FeatureCollection notifications aren't supported.")
    try:
        notified_at = pd.Timestamp(doc["notifiedAt"])
        notified_at = (notified_at if notified_at.tzinfo else notified_at.tz_localize("UTC")).tz_convert("UTC").isoformat(timespec="microseconds")
    except (ValueError, TypeError) as e:
        raise PayloadError(400, "Not a notification", f"notifiedAt isn't a valid timestamp: {doc['notifiedAt']!r}.") from e
    body_context = doc.get("@context")
    context = [c for c in (body_context if isinstance(body_context, list) else [body_context]) if c] + ([link_context(link_header)] if link_context(link_header) else [])
    terms = inline_terms(body_context) if body_context else {}
    result = Notification(doc.get("id"), doc["subscriptionId"], notified_at, media, [c if isinstance(c, str) else "(inline)" for c in context], [], [], [])
    for i, entity in enumerate(doc["data"]):
        if not isinstance(entity, dict):
            result.rejected.append(dict(index=i, entity_id=None, reason="entity is not a JSON object", excerpt=repr(entity)[:300]))
            continue
        kinds = entity_type(entity)
        if not kinds:
            result.rejected.append(dict(index=i, entity_id=entity.get("id"), reason="entity has no type", excerpt=json.dumps(entity)[:300]))
        elif not set(kinds) & set(weather_types):
            # Includes our own YieldPrediction: storing or reacting to it could start a notification loop.
            result.ignored.append(dict(index=i, entity_id=entity.get("id"), type=kinds[0]))
        else:
            try:
                result.readings.append(parse_entity(entity, terms, cells))
            except (EntityError, TypeError, AttributeError, KeyError) as e:
                result.rejected.append(dict(index=i, entity_id=entity.get("id"), reason=str(e), excerpt=json.dumps(entity)[:300]))
    return result

