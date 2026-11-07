"""The Live season tab: reads the backend over HTTP and refreshes itself, and keeps working when the backend is down."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from config import OUT
from i18n import num, t

BACKEND = os.environ.get("LIVE_BACKEND_URL", "http://127.0.0.1:8600")
BLUE, ORANGE, LIGHT = "#2a78d6", "#eb6834", "#c3c2b7"
CUTS = [("05-01", (5, 1)), ("05-15", (5, 15)), ("06-01", (6, 1)), ("06-15", (6, 15)), ("07-01", (7, 1)), ("07-15", (7, 15)), ("08-01", (8, 1)), ("08-15", (8, 15)), ("09-01", (9, 1))]


def fetch(path, **params):
    """JSON from the backend, or None if it can't be reached or answers badly."""
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        with urllib.request.urlopen(f"{BACKEND}{path}{'?' + query if query else ''}", timeout=3) as r:
            return json.load(r)
    except (urllib.error.URLError, OSError, ValueError):
        return None


@st.cache_data(ttl=300, show_spinner=False)
def accuracy_table():
    path = OUT / "live_season_replay.csv"
    return pd.read_csv(path) if path.exists() else None


def accuracy_note(region, crop, as_of):
    """The fair test's result at the latest test date on or before this one."""
    a = accuracy_table()
    if a is None or f"{region}/{crop}" not in set(a.scope):
        return st.caption(t("There's no accuracy test for this crop and region yet. Run: python -m service.replay_eval"))
    day = pd.Timestamp(as_of)
    cut = next((name for name, (m, d) in reversed(CUTS) if (day.month, day.day) >= (m, d)), "none")
    if (day.month, day.day) >= (10, 27):
        cut = "full"
    rows = a[(a.test == "loyo") & (a.scope == f"{region}/{crop}") & (a.known_until == cut)].set_index("method").production_error
    model, base = rows.get("estimate"), rows.get("baseline_farm_average")
    st.markdown(t("On past seasons, with later days hidden and each season left out of training, the estimate at about this date missed regional production by {model}. The farm average missed by {base}.", model=num(model, ".1%"), base=num(base, ".1%")))
    if model >= base - 0.002:
        st.warning(t("**At this point it's no better than the farm average**, so don't rely on it yet."))


def weighted(rows, value):
    return np.average(rows[value], weights=rows.area_ha)


def trajectory_chart(rows, style):
    """Area-weighted estimate per date, with the farm-average baseline for comparison."""
    known = rows[rows.baseline_t_ha.notna()]
    g = known.groupby("as_of_date").apply(lambda d: pd.Series({t("Estimate"): weighted(d, "yield_t_ha"), t("Baseline"): weighted(d, "baseline_t_ha")}), include_groups=False).reset_index()
    long = g.melt("as_of_date", var_name="series", value_name="value").assign(as_of_date=lambda d: pd.to_datetime(d.as_of_date))
    scale = alt.Scale(domain=[t("Estimate"), t("Baseline")], range=[BLUE, ORANGE])
    return style(alt.Chart(long).mark_line(strokeWidth=2, strokeCap="round").encode(x=alt.X("as_of_date:T", title=t("Date of latest reading")), y=alt.Y("value:Q", title=t("Yield (t/ha)"), scale=alt.Scale(zero=False)), color=alt.Color("series:N", scale=scale, title=None),
                                                                                  tooltip=[alt.Tooltip("as_of_date:T", title=t("Date of latest reading")), alt.Tooltip("series:N", title=t("Method")), alt.Tooltip("value:Q", title=t("Yield (t/ha)"), format=".2f")]), 300)


def days_chart(rows, style):
    """How the season splits into observed and filled days as readings arrive."""
    g = rows.groupby("as_of_date")[["observed_days", "filled_gap_days", "filled_future_days"]].first().reset_index().assign(as_of_date=lambda d: pd.to_datetime(d.as_of_date))
    names = {"observed_days": t("Observed"), "filled_gap_days": t("Filled, in gaps"), "filled_future_days": t("Filled, still ahead")}
    long = g.melt("as_of_date", var_name="kind", value_name="days").assign(kind=lambda d: d.kind.map(names))
    scale = alt.Scale(domain=list(names.values()), range=[BLUE, ORANGE, LIGHT])
    return style(alt.Chart(long).mark_area().encode(x=alt.X("as_of_date:T", title=t("Date of latest reading")), y=alt.Y("days:Q", stack=True, title=t("Days")), color=alt.Color("kind:N", scale=scale, title=None, sort=list(names.values())), order=alt.Order("kind:N"),
                                                   tooltip=[alt.Tooltip("as_of_date:T", title=t("Date of latest reading")), alt.Tooltip("kind:N", title=t("Days")), alt.Tooltip("days:Q", title=t("Days"), format="d")]), 180)


def show_status(health):
    a, b, c, d = st.columns(4)
    counters = health.get("counters", {})
    a.metric(t("Backend"), t("Running") if health.get("status") == "ok" else t("Needs attention"))
    b.metric(t("Notifications"), f"{counters.get('notifications', 0):,}".replace(",", " "))
    c.metric(t("Rejected entries"), counters.get("entities_rejected", 0) + counters.get("notifications_refused", 0))
    writeback = health.get("writeback", {})
    d.metric(t("Written back to broker"), f"{writeback.get('written', 0):,}".replace(",", " ") if writeback.get("enabled") else t("Off"))
    last = health.get("last_notification")
    if last:
        st.caption(t("Last reading received") + f": {last.get('received_at')}")


def show_season(season, draw, style, crop_names):
    rows = fetch("/predictions", cell_id=season["cell_id"], year=season["year"], limit=100000)
    if rows is None or not rows.get("predictions"):
        st.info(t("The live data couldn't be read. Trying again shortly."))
        return
    all_rows = pd.DataFrame(rows["predictions"])
    crops = sorted(all_rows.crop.unique())
    crop = st.selectbox(t("Crop"), crops, format_func=lambda x: t(crop_names.get(x, x)), key="live_crop")
    d = all_rows[all_rows.crop == crop]
    as_of = d.as_of_date.max()
    latest = d[d.as_of_date == as_of]
    now = latest.iloc[0]
    a, b, c, e = st.columns(4)
    a.metric(t("Estimate on {date}", date=as_of), f"{num(weighted(latest, 'yield_t_ha'))} t/ha")
    a.caption(t("Area-weighted average of {n} fields", n=len(latest)))
    known = latest[latest.baseline_t_ha.notna()]
    b.metric(t("Baseline: farm average"), f"{num(weighted(known, 'baseline_t_ha'))} t/ha" if len(known) else "–")
    c.metric(t("Days observed"), int(now.observed_days))
    c.caption(t("of {total} in the season window", total=int(now.total_days)))
    e.metric(t("Days filled"), int(now.filled_days))
    e.caption(t("{gaps} in gaps, {ahead} still ahead", gaps=int(now.filled_gap_days), ahead=int(now.filled_future_days)))
    st.progress(min(int(now.observed_days) / int(now.total_days), 1.0), text=t("Latest reading covers {share} of the season window", share=num(1 - int(now.filled_future_days) / int(now.total_days), ".0%")))
    st.subheader(t("How reliable is this at this point in the season?"))
    region = "SE_SKANE" if season["cell_id"].startswith("GS") else "FI_SW"
    accuracy_note(region, crop, as_of)
    if season["year"] <= 2026:
        st.caption(t("This is a past season, and the final model trained on it, so this replay flatters the estimate. The accuracy above is the fair test."))
    st.subheader(t("The estimate through the season"))
    if len(d.as_of_date.unique()) > 1 and len(known):
        draw(trajectory_chart(d, style), f"live_trajectory_{crop}")
        st.subheader(t("Observed and filled days"))
        draw(days_chart(d, style), f"live_days_{crop}")
    st.subheader(t("Fields, latest estimate"))
    status_name = {"declared": t("Declared"), "planned": t("Planned")}
    table = latest.assign(status=latest.status.map(status_name), flags=latest.out_of_training_range.map(lambda x: ", ".join(x)))[["parcel_id", "farm_id", "status", "area_ha", "yield_t_ha", "baseline_t_ha", "filled_to_maturity", "flags"]]
    st.dataframe(table.rename(columns={"parcel_id": t("Field"), "farm_id": t("Farm"), "status": t("Status"), "area_ha": t("Area (ha)"), "yield_t_ha": t("Estimate (t/ha)"), "baseline_t_ha": t("Baseline (t/ha)"), "filled_to_maturity": t("Days filled before maturity"), "flags": t("Outside training range")}).round(2), hide_index=True, width="stretch")


@st.fragment(run_every="3s")
def live_panel(draw, style, crop_names):
    health = fetch("/health")
    if health is None:
        st.warning(t("The live backend isn't running, so there's nothing to show. The rest of the viewer works as usual. To start it with the mock broker:"))
        st.code("python -m service.cli start\npython -m service.cli replay --cell GF0203 --year 2025 --speed 20", language="bash")
        return
    show_status(health)
    status = fetch("/observations/status")
    seasons = (status or {}).get("seasons", [])
    if not seasons:
        st.info(t("No weather has arrived yet. To replay a past season through the mock broker:"))
        st.code("python -m service.cli replay --cell GF0203 --year 2025 --speed 20", language="bash")
        return
    usable = [s for s in seasons if s["contract_parcels"] > 0]
    if not usable:
        st.info(t("The backend has weather, but no contract crop is planned in these cells and seasons. Plans cover 2012–2031."))
        return
    by_key = {f"{s['cell_id']}|{s['year']}": s for s in usable}
    key = st.selectbox(t("Grid cell and season"), list(by_key), format_func=lambda k: t("{cell}, {year} ({n} fields)", cell=by_key[k]["cell_id"], year=by_key[k]["year"], n=by_key[k]["contract_parcels"]), key="live_season")
    show_season(by_key[key], draw, style, crop_names)
    rejected = (status or {}).get("recent_rejected", [])
    if rejected:
        with st.expander(t("Recently rejected data")):
            st.dataframe(pd.DataFrame(rejected)[["received_at", "entity_id", "reason"]].rename(columns={"received_at": t("Time"), "entity_id": t("Entity"), "reason": t("Reason")}), hide_index=True, width="stretch")


def render(draw, style, crop_names):
    st.title(t("Live season"))
    st.markdown(t("Estimates for the running season, updated each time a weather reading arrives from the context broker. Days without a reading are filled with typical weather for that grid cell, so **every number here is an estimate**, not a measured yield."))
    live_panel(draw, style, crop_names)
