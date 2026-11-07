"""Map tab: an advisor's way in to a farm. Colour comes from crop, soil and climate story, never from location, because
docs/MAP_ASSESSMENT.md shows location carries no signal in this data. Precomputed by src/build_map_data.py."""
import json
import math

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from advisor import CONFIDENCE, STORIES, advice, themes
from config import DATA, OUT
from i18n import num, t

REGION = {"FI_SW": "Finland", "SE_SKANE": "Sweden"}
CROP = {"turnip_rape": "Turnip rape", "pea": "Pea", "potato": "Potato", "carrot": "Carrot", "spinach": "Spinach"}
STORY = {"current_policies": "Hothouse", "below_2c": "Below 2 °C"}
DRAINAGE = {"subsurface": "Subsurface drains", "open_ditch": "Open ditch"}

# Diverging, red for falling yields and blue for rising, with a gray middle. Each arm passes the ordinal check in dataviz/validate_palette.js on the land colour.
EDGES = [-0.06, -0.04, -0.02, 0.02, 0.04, 0.06]
CLASSES = ["#8f1d1d", "#d9423f", "#f09a90", "#e8e7e0", "#86b6ef", "#2a78d6", "#104281"]
LAND, SEA, GRID, RING, INK = [252, 252, 251], [226, 230, 230], [150, 149, 140, 110], [82, 81, 78], [11, 11, 11]
HEIGHT, WIDTH = 620, 820
ALL = ""
NO_BASEMAP = 'data:application/json,{"version":8,"sources":{},"layers":[]}'  # Without a style Streamlit fetches a Carto basemap, which needs internet and adds real towns and roads.
GRID_BOX = {"FI_SW": ([60.6, 61.6], [21.2, 23.8]), "SE_SKANE": ([55.3, 56.9], [12.5, 14.6])}  # Lat and lon range shown for a whole region: the weather grid and its coast.
LIVE = "map_live_"  # Selection widgets. They refuse writes, so keep_selections in app.py skips this prefix.


def _rgb(hex_colour, alpha=255):
    return [int(hex_colour[i:i + 2], 16) for i in (1, 3, 5)] + [alpha]


def _band(change):
    return int(np.digitize(change, EDGES))


def _pct(value, spec="+.1%"):
    return num(value, spec)


def _soil(name):
    return t(name.replace("_", " "))


@st.cache_data(show_spinner=False)
def _farms():
    return pd.read_csv(OUT / "map_farms.csv")


@st.cache_data(show_spinner=False)
def _soil_effects():
    return pd.read_csv(OUT / "map_soil_effects.csv")


@st.cache_resource(show_spinner=False)
def _land():
    with open(OUT / "map_land.json") as fh:
        return json.load(fh)


@st.cache_resource(show_spinner=False)
def _polygons():
    """Parcel outlines by farm. Shared rather than copied, because there are 14,213 of them."""
    with open(DATA / "06_nature/parcels.geojson") as fh:
        features = json.load(fh)["features"]
    out = {}
    for f in features:
        out.setdefault(f["properties"]["farm_id"], {})[f["properties"]["parcel_id"]] = f["geometry"]["coordinates"][0]
    return out


@st.cache_data(show_spinner=False)
def _grid(region):
    c = pd.read_csv(DATA / "01_master/climate_grid_cells.csv").query("region == @region")
    return [{"polygon": [[x - .125, y - .125], [x + .125, y - .125], [x + .125, y + .125], [x - .125, y + .125]]} for x, y in zip(c.lon, c.lat)]


def _fit(lats, lons, zoom_cap=14.0):
    """Centre and zoom that show the given points, using a mid-size chart as the reference."""
    lat0, lat1, lon0, lon1 = min(lats), max(lats), min(lons), max(lons)
    y = (lat0 + lat1) / 2
    wide = max(lon1 - lon0, 0.005) * 1.1
    tall = max(lat1 - lat0, 0.003) * 1.1 / math.cos(math.radians(y))
    return pdk.ViewState(latitude=y, longitude=(lon0 + lon1) / 2, zoom=min(zoom_cap, math.log2(min(WIDTH * 360 / (512 * wide), HEIGHT * 360 / (512 * tall)))), pitch=0, bearing=0)


def _background(region):
    x0, y0, x1, y1 = 0, 40, 40, 75
    land = {"type": "FeatureCollection", "features": [f for f in _land()["features"] if f["properties"]["region"] == region]}
    return [pdk.Layer("PolygonLayer", id="sea", data=[{"polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}], get_polygon="polygon", get_fill_color=SEA, stroked=False, pickable=False),
            pdk.Layer("GeoJsonLayer", id="land", data=land, get_fill_color=LAND, stroked=False, filled=True, pickable=False),
            pdk.Layer("PolygonLayer", id="grid", data=_grid(region), get_polygon="polygon", filled=False, stroked=True, get_line_color=GRID, line_width_units="'pixels'", get_line_width=1, pickable=False)]


def _labels(rows, layer_id, size):
    return pdk.Layer("TextLayer", id=layer_id, data=rows, get_position="[lon, lat]", get_text="label", get_size=size, size_units="'pixels'", get_color=INK, character_set="'auto'", font_family="'system-ui, sans-serif'", font_weight=600,
                     get_text_anchor="'middle'", get_alignment_baseline="'top'", get_pixel_offset=[0, 12], background=True, get_background_color=[252, 252, 251, 200], background_padding=[2, 0], pickable=False)


def _farm_dots(farms, story, top):
    rows = []
    for r in farms.itertuples():
        change = getattr(r, "change_" + story)
        rows.append(dict(farm_id=r.farm_id, lat=r.lat, lon=r.lon, radius=130 * math.sqrt(r.area_ha), colour=_rgb(CLASSES[_band(change)], 235),
                         tip=t("<b>Farm {farm}</b><br>Yield change: {change}<br>On sand or fine sand: {dry} ha, {share}<br>Click to open", farm=r.farm_id, change=_pct(change), dry=num(r.dry_ha, ".0f"), share=_pct(r.dry_share, ".0%"))))
    layers = [pdk.Layer("ScatterplotLayer", id="farms", data=rows, get_position="[lon, lat]", get_radius="radius", radius_min_pixels=3, radius_max_pixels=14, get_fill_color="colour", stroked=True, get_line_color=RING, line_width_min_pixels=1, pickable=True)]
    shown = farms[farms.farm_id.isin(top)]
    labels = [dict(lat=r.lat, lon=r.lon, label=r.farm_id) for r in shown.itertuples()]
    return layers + [pdk.Layer("TextLayer", id="top_farms", data=labels, get_position="[lon, lat]", get_text="label", get_size=12, size_units="'pixels'", get_color=INK, get_pixel_offset=[0, -18], character_set="'auto'", font_family="'system-ui, sans-serif'", font_weight=600, background=True, get_background_color=[252, 252, 251, 215], background_padding=[3, 1], pickable=False)]


def _field_rows(table, polygons, effects, story, selected):
    labelled = table.parcel_id if len(table) <= 30 else table[table.droughty_soil].nlargest(20, "area_ha").parcel_id
    rows, labelled = [], set(labelled) | {selected}
    for r in table.itertuples():
        change = effects.loc[r.soil_class_soilmap, "change_" + story]
        ring = polygons[r.parcel_id]
        lons, lats = zip(*ring[:-1])
        planned = t("Planned for this crop: {year}", year=int(r.next_planned)) if pd.notna(r.next_planned) else t("Not planned for this crop")
        rows.append(dict(parcel_id=r.parcel_id, polygon=ring, lat=sum(lats) / len(lats), lon=sum(lons) / len(lons), colour=_rgb(CLASSES[_band(change)], 215), selected=r.parcel_id == selected,
                         label=_soil(r.soil_class_soilmap) if r.parcel_id in labelled else "",
                         tip=t("<b>Field {field}</b><br>{soil}, {area} ha<br>Yield change on this soil: {change}<br>{planned}", field=r.parcel_id, soil=_soil(r.soil_class_soilmap), area=num(r.area_ha, ".1f"), change=_pct(change), planned=planned)))
    return rows


def _pick(key):
    """Runs before the script reruns, so the farm and field selectors can take the clicked value."""
    objects = (st.session_state.get(key) or {}).get("selection", {}).get("objects", {})
    for field in objects.get("fields", []):
        st.session_state.map_field = field["parcel_id"]
        return
    for farm in objects.get("farms", []):
        st.session_state.map_farm, st.session_state.map_field = farm["farm_id"], ALL


def _pick_row(key, ids, target):
    rows = (st.session_state.get(key) or {}).get("selection", {}).get("rows", [])
    if rows:
        st.session_state[target] = ids[rows[0]]
        if target == "map_farm":
            st.session_state.map_field = ALL


def _reset():
    st.session_state.map_farm, st.session_state.map_field = ALL, ALL


def _legend(values, unit_label):
    counts = pd.Series([_band(v) for v in values]).value_counts()
    p = lambda v: _pct(v, "+.0%")
    names = [t("{x} or lower", x=p(EDGES[0])), t("{low} to {high}", low=p(EDGES[0]), high=p(EDGES[1])), t("{low} to {high}", low=p(EDGES[1]), high=p(EDGES[2])), t("About flat, {low} to {high}", low=p(EDGES[2]), high=p(EDGES[3])),
             t("{low} to {high}", low=p(EDGES[3]), high=p(EDGES[4])), t("{low} to {high}", low=p(EDGES[4]), high=p(EDGES[5])), t("{x} or higher", x=p(EDGES[5]))]
    items = "".join(f'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:9px;white-space:nowrap;color:{"#0b0b0b" if counts.get(i, 0) else "#898781"}"><span style="width:13px;height:13px;border-radius:7px;border:1px solid #52514e;background:{c};display:inline-block"></span>{n} <b>{counts.get(i, 0)}</b></span>'
                    for i, (c, n) in enumerate(zip(CLASSES, names)))
    st.markdown(f'<div style="font-size:12px;line-height:1.9"><div style="color:#52514e">{t("Estimated yield change, 2041–2060 against 1991–2020. Number of {unit} in each band:", unit=unit_label)}</div>{items}</div>', unsafe_allow_html=True)


def _actions(results, region, crop, story, filled):
    st.markdown(f"**{t('What to do (draft)')}**")
    st.caption(t("**Draft rules for advisors to review, not proven recommendations.** Each one shows the evidence behind it."))
    rules = advice(results, region, crop, story)

    def show(rule):
        with st.container(border=True):
            st.markdown(f"**{t(rule['decision'])}**")
            st.markdown(filled(rule))
            st.caption(t("Evidence: {kind}", kind=t(rule["evidence"])))

    for rule in rules[:2]:
        show(rule)
    with st.expander(t("All draft actions ({n})", n=len(rules))):
        for rule in rules[2:]:
            show(rule)


def _why(results, region, crop, story, effects):
    theme = themes(results, region, crop, STORIES[story])
    top = theme.abs().idxmax()
    worst, best = effects["change_" + story].idxmin(), effects["change_" + story].idxmax()
    return [t("Largest modelled effect: {theme}, {effect}. Weather measures overlap, so read this as a theme, not a proven cause.", theme=t(top).lower(), effect=_pct(theme[top])),
            t("Soil moves it: {worst} on {worst_soil}, {best} on {best_soil}. These are region-wide figures for each soil, using water capacities we assumed.", worst=_pct(effects.loc[worst, "change_" + story]), worst_soil=_soil(worst), best=_pct(effects.loc[best, "change_" + story]), best_soil=_soil(best))]


def _bullets(lines):
    st.markdown("\n".join("- " + line for line in lines))


def _region_panel(results, region, crop, story, effects, filled):
    ssp = STORIES[story]
    risk = results["risk"].query("region == @region and crop == @crop and scenario == @ssp").iloc[0]
    seen = results["bad_check"].query("region == @region and crop == @crop").iloc[0]
    st.subheader(f"{t(REGION[region])}, {t(CROP[crop]).lower()}: {t(STORY[story])}")
    a, b = st.columns(2)
    a.metric(t("Yield change"), _pct(risk.mean_yield_change_pct / 100))
    b.metric(t("Bad-year chance"), _pct(risk.p_bad_year, ".0%"), help=t("Yield under 80% of normal. Today's climate: {today}. Seen so far: {seen} of {seasons} seasons", today=_pct(seen.p_bad_today, ".0%"), seen=round(seen.observed_bad * seen.seasons), seasons=int(seen.seasons)))
    st.caption(t("Confidence in the yield change: {level}", level=t(CONFIDENCE[(region, crop)])))
    st.markdown(f"**{t('Why')}**")
    _bullets(_why(results, region, crop, story, effects))
    _actions(results, region, crop, story, filled)


def _farm_panel(results, predictor, region, crop, story, row, table, effects, filled):
    change = getattr(row, "change_" + story)
    st.subheader(t("Farm {farm}", farm=row.farm_id))
    a, b = st.columns(2)
    a.metric(t("Yield change"), _pct(change), help=t("From this farm's soil mix and the region-wide figure for each soil."))
    b.metric(t("On sand or fine sand"), _pct(row.dry_share, ".0%"), help=t("Share of the farm's field area on the soils we assume hold the least water."))
    regional = results["risk"].query("region == @region and crop == @crop and scenario == @STORIES[@story]").iloc[0].mean_yield_change_pct / 100
    st.markdown(f"**{t('The risk')}**")
    other = "below_2c" if story == "current_policies" else "current_policies"
    st.markdown(t("With this farm's soils, the model estimates {change} for this crop under {story}, against {other} under {other_story}. The whole region under {story}: {regional}.", change=_pct(change), story=t(STORY[story]), other=_pct(getattr(row, "change_" + other)), other_story=t(STORY[other]), regional=_pct(regional)))
    st.markdown(f"**{t('Why')}**")
    droughty = int(table.droughty_soil.sum())
    lines = [t("{n} of {total} fields are on sand or fine sand, which we assume hold the least water. Prioritise them in dry-season guidance.", n=droughty, total=len(table)) if droughty else t("None of the {total} fields are on sand or fine sand, the soils we assume hold the least water.", total=len(table))]
    if row.planned_fields:
        lines.append(t("{n} fields are planned for this crop in 2027–2028, {area} ha of it on sand or fine sand.", n=int(row.planned_fields), area=num(row.planned_dry_ha, ".0f")))
    lines.append(t("This farm's usual irrigated share for this crop: {share}.", share=_pct(float(predictor.farm_irr.get((row.farm_id, crop), 0.0)), ".0%")))
    lines.append(_why(results, region, crop, story, effects)[0])
    _bullets(lines)
    _actions(results, region, crop, story, filled)


def _field_panel(results, region, crop, story, field, effects, filled):
    soil = field.soil_class_soilmap
    st.subheader(t("Field {field}", field=field.parcel_id))
    change, regional = effects.loc[soil, "change_" + story], results["risk"].query("region == @region and crop == @crop and scenario == @STORIES[@story]").iloc[0].mean_yield_change_pct / 100
    a, b = st.columns(2)
    a.metric(t("Yield change"), _pct(change), help=t("Region-wide figure for this crop on this soil."))
    b.metric(t("Yield today (t/ha)"), num(field.yield_today))
    st.markdown(f"**{t('The risk')}**")
    st.markdown(t("On {soil} the model estimates {change} for this crop under {story}. The whole region: {regional}. Drought stress at the sensitive stage (0–1) goes from {today} to {future}.", soil=_soil(soil), change=_pct(change), story=t(STORY[story]), regional=_pct(regional), today=num(effects.loc[soil, "stress_today"]), future=num(effects.loc[soil, "stress_" + story])))
    st.markdown(f"**{t('Why')}**")
    lines = [t("Soil-map class: {soil}, {area} ha. The soil map is only about 88% accurate.", soil=_soil(soil), area=num(field.area_ha, ".1f"))]
    if field.droughty_soil:
        lines.append(t("We assume this soil holds the least water. Prioritise this field in dry-season guidance."))
    lines.append(t("Planned for this crop: {year}", year=int(field.next_planned)) if pd.notna(field.next_planned) else t("Not planned for this crop"))
    _bullets(lines)
    st.caption(t("With only this grid square's weather run the same field shows {local}. Differences between squares are mostly weather noise, so trust the soil figure above.", local=_pct(getattr(field, "change_" + story))))
    _actions(results, region, crop, story, filled)


def _farm_table(farms, story, key):
    order = farms.sort_values(["planned_dry_ha", "dry_ha"], ascending=False)
    ids = order.farm_id.tolist()
    table = order.assign(change=order["change_" + story])[["farm_id", "n_fields", "area_ha", "dry_ha", "dry_share", "planned_dry_ha", "change"]].rename(columns={
        "farm_id": t("Farm"), "n_fields": t("Fields"), "area_ha": t("Area (ha)"), "dry_ha": t("On sand or fine sand (ha)"), "dry_share": t("Share of area"), "planned_dry_ha": t("Planned 2027–2028 on sand or fine sand (ha)"), "change": t("Yield change")})
    style = table.style.format({t("Area (ha)"): lambda v: num(v, ".0f"), t("On sand or fine sand (ha)"): lambda v: num(v, ".0f"), t("Share of area"): lambda v: _pct(v, ".0%"), t("Planned 2027–2028 on sand or fine sand (ha)"): lambda v: num(v, ".0f"), t("Yield change"): _pct})
    st.subheader(t("Farms to contact first"))
    st.caption(t("Most hectares planned for this crop in 2027–2028 on sand or fine sand first. Click a row to open the farm. This table holds everything the map shows."))
    st.dataframe(style, hide_index=True, width="stretch", height=300, on_select=lambda: _pick_row(key, ids, "map_farm"), selection_mode="single-row", key=key)


def _field_table(table, effects, story, key):
    order = table.sort_values("area_ha", ascending=False)
    ids = order.parcel_id.tolist()
    shown = pd.DataFrame({t("Field"): order.parcel_id, t("Soil"): order.soil_class_soilmap.map(_soil), t("Area (ha)"): order.area_ha, t("Drainage"): order.drainage.map(lambda x: t(DRAINAGE[x])), t("Yield change"): order.soil_class_soilmap.map(effects["change_" + story]),
                          t("Yield today (t/ha)"): order.yield_today, t("Drought stress today (0–1)"): order.stress_today, t("Last grown"): order.last_grown.astype("Int64").astype(str).replace("<NA>", "–"), t("Next planned"): order.next_planned.astype("Int64").astype(str).replace("<NA>", "–")})
    style = shown.style.format({t("Area (ha)"): lambda v: num(v, ".1f"), t("Yield change"): _pct, t("Yield today (t/ha)"): num, t("Drought stress today (0–1)"): num})
    st.subheader(t("This farm's fields"))
    st.caption(t("Click a row to open the field. This table holds everything the map shows."))
    st.dataframe(style, hide_index=True, width="stretch", height=300, on_select=lambda: _pick_row(key, ids, "map_field"), selection_mode="single-row", key=key)


@st.fragment
def render(predictor, results, fields_of, filled):
    """Controls, map, plain-language panel and table. A fragment, so a click reruns this tab and not the whole page."""
    _polygons()  # Loaded with the page, so the first click on a farm isn't the slow one.
    for key, default in {"map_region": "FI_SW", "map_crop": "turnip_rape", "map_story": "current_policies", "map_farm": ALL, "map_field": ALL}.items():
        st.session_state.setdefault(key, default)
    st.header(t("Map: which farms to talk to first"))
    st.markdown(t("For advisors planning who to contact. Each dot is a contract farm, coloured by the model's estimated yield change for this crop on that farm's soils. Pick a climate story, then click a farm to see its fields, the risk and the draft actions."))
    st.warning(t("**All farms, fields and positions are synthetic.** They aren't real farms or places, and some fields even fall in lakes or the sea. That's why the map shows only a simplified coastline, with no roads or towns."))

    a, b, c, d, e = st.columns([1, 1, 1.25, 1, 1])
    region = a.selectbox(t("Region"), list(REGION), format_func=lambda x: t(REGION[x]), key="map_region", on_change=_reset)
    crops = ["pea"] if region == "SE_SKANE" else list(CROP)
    if st.session_state.map_crop not in crops:
        st.session_state.map_crop = crops[0]
    crop = b.selectbox(t("Crop"), crops, format_func=lambda x: t(CROP[x]), key="map_crop", on_change=_reset)
    story = c.radio(t("Climate story"), list(STORY), format_func=lambda x: t(STORY[x]), horizontal=True, key="map_story")

    farms = _farms().query("region == @region and crop == @crop").sort_values(["planned_dry_ha", "dry_ha"], ascending=False)
    effects = _soil_effects().query("region == @region and crop == @crop").set_index("soil")
    if st.session_state.map_farm not in farms.farm_id.tolist():
        st.session_state.map_farm, st.session_state.map_field = ALL, ALL

    farm = d.selectbox(t("Farm"), [ALL] + farms.farm_id.tolist(), format_func=lambda x: x or t("All farms"), key="map_farm", on_change=lambda: st.session_state.update(map_field=ALL))
    table = fields_of(farm, crop) if farm else None
    if farm and st.session_state.map_field not in table.parcel_id.tolist():
        st.session_state.map_field = ALL
    if farm:
        field = e.selectbox(t("Field"), [ALL] + table.parcel_id.tolist(), format_func=lambda x: x or t("All fields"), key="map_field")
    else:
        st.session_state.map_field = ALL
        field = ALL

    left, right = st.columns([5, 3], gap="medium")
    with left:
        if farm:
            rows = _field_rows(table, _polygons()[farm], effects, story, field)
            row = farms[farms.farm_id == farm].iloc[0]
            lats = [p[1] for r in rows for p in r["polygon"]]
            lons = [p[0] for r in rows for p in r["polygon"]]
            near = farms[(farms.farm_id != farm) & farms.lat.between(min(lats) - .12, max(lats) + .12) & farms.lon.between(min(lons) - .2, max(lons) + .2)]
            neighbours = [dict(farm_id=r.farm_id, lat=r.lat, lon=r.lon, tip=t("<b>Farm {farm}</b><br>Click to open", farm=r.farm_id)) for r in near.itertuples()]
            layers = _background(region) + [
                pdk.Layer("ScatterplotLayer", id="farms", data=neighbours, get_position="[lon, lat]", get_radius=1, radius_min_pixels=6, radius_max_pixels=6, get_fill_color=[195, 194, 183, 200], stroked=True, get_line_color=RING, line_width_min_pixels=1, pickable=True),
                pdk.Layer("PolygonLayer", id="fields", data=rows, get_polygon="polygon", get_fill_color="colour", stroked=True, get_line_color=RING, line_width_units="'pixels'", get_line_width=1, pickable=True),
                pdk.Layer("PolygonLayer", id="selected_field", data=[r for r in rows if r["selected"]], get_polygon="polygon", filled=False, stroked=True, get_line_color=INK, line_width_units="'pixels'", get_line_width=3, pickable=False),
                _labels([r for r in rows if r["label"]], "field_labels", 11)]
            view, key = _fit(lats, lons), f"{LIVE}deck_farm"
            _legend([effects.loc[s, "change_" + story] for s in table.soil_class_soilmap], t("fields"))
            size_note = t("Coloured shapes: this farm's fields, with soil labels on up to 20 of the largest on sand or fine sand in big farms. Gray dots: nearby farms. Field outlines are synthetic and some overlap.")
        else:
            top = farms.farm_id.head(8).tolist()
            layers = _background(region) + _farm_dots(farms, story, top)
            view, key = _fit(*GRID_BOX[region]), f"{LIVE}deck_region"
            _legend(farms["change_" + story], t("farms"))
            size_note = t("Dot size: the farm's field area. Labelled: the 8 farms at the top of the table below. Thin squares: the weather grid, about 15 × 28 km. We have no finer weather.")
        st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style=NO_BASEMAP, map_provider=None, tooltip={"html": "{tip}", "style": {"backgroundColor": "#fcfcfb", "color": "#0b0b0b", "fontSize": "13px", "border": "1px solid #c3c2b7"}}),
                        height=HEIGHT, use_container_width=True, key=key, on_select=lambda: _pick(key), selection_mode="single-object")
        st.caption(size_note)
        st.markdown(t("**What the colour means:** the model's estimated yield change, from the crop, the climate story and the field's soil.") + " " + t("**What it doesn't mean:** that a place is safer or riskier. In this data, neighbouring farms are no more alike than random ones, and differences between weather-grid squares are mostly noise from a single simulated weather run, so the colour leaves them out. The soil map is only about 88% accurate, soil water capacities are our assumption, and irrigation is not part of the colour."))
    with right:
        if farm:
            st.button(t("Back to all farms"), on_click=_reset)
        if field:
            _field_panel(results, region, crop, story, table[table.parcel_id == field].iloc[0], effects, filled)
        elif farm:
            _farm_panel(results, predictor, region, crop, story, row, table, effects, filled)
        else:
            _region_panel(results, region, crop, story, effects, filled)
    if farm:
        _field_table(table, effects, story, f"{LIVE}table_{farm}")
    else:
        _farm_table(farms, story, f"{LIVE}table_{region}_{crop}")
