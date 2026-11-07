"""Viewer: compare the baseline with our yield model, and try the trained model. Run: streamlit run app.py"""
import sys
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from backtest import metrics  # noqa: E402
from config import OUT  # noqa: E402
from inference import Predictor  # noqa: E402

BLUE, ORANGE, RED, GRAY = "#2a78d6", "#eb6834", "#e34948", "#52514e"
INK, MUTED, GRID, AXIS = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = alt.Scale(domain=["Actual", "Baseline", "Our model"], range=[GRAY, ORANGE, BLUE])
REGION = {"FI_SW": "Finland", "SE_SKANE": "Sweden"}
CROP = {"pea": "Pea", "turnip_rape": "Turnip rape", "potato": "Potato", "carrot": "Carrot", "spinach": "Spinach"}
TEST = {"Leave one season out": "loyo", "Predict 2022–2026 from earlier seasons": "forward"}
WEATHER = {"Historical weather (1991–2026)": ("historical", range(1991, 2027)),
           "SSP2-4.5, the C1 forecast seasons (2027–2031)": ("ssp245", range(2027, 2032)),
           "SSP1-2.6, low emissions (2041–2060)": ("ssp126", range(2041, 2061)),
           "SSP2-4.5, middle emissions (2041–2060)": ("ssp245", range(2041, 2061)),
           "SSP5-8.5, high emissions (2041–2060)": ("ssp585", range(2041, 2061))}

st.set_page_config(page_title="Apetit yield model viewer", layout="wide")


@st.cache_resource(show_spinner="Loading the trained models")
def predictor():
    return Predictor()


@st.cache_data
def load(name):
    return pd.read_csv(OUT / name)


def label(region, crop):
    return f"{REGION[region]}, {CROP[crop].lower()}"


def style(chart, height=320):
    return (chart.properties(height=height).configure_view(stroke=None, fill="#fcfcfb")
            .configure_axis(gridColor=GRID, domainColor=AXIS, tickColor=AXIS, labelColor=MUTED, titleColor=MUTED, labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelColor=INK, titleColor=MUTED, orient="top", labelFontSize=13, symbolStrokeWidth=3).configure(background="#fcfcfb"))


def season_chart(long, y_title="Yield (t/ha)"):
    """Lines per series, with a season-wide hover readout."""
    wide = long.pivot_table(index="year", columns="series", values="value").reset_index()
    x = alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0))
    base = alt.Chart(long).encode(x=x, y=alt.Y("value:Q", title=y_title, scale=alt.Scale(zero=False)), color=alt.Color("series:N", scale=SERIES, title=None))
    hover = alt.selection_point(fields=["year"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    tips = [alt.Tooltip("year:O", title="Season")] + [alt.Tooltip(f"{c}:Q", format=".2f") for c in wide.columns if c != "year"]
    lines = base.mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round") + base.mark_circle(size=70, opacity=1, stroke="#fcfcfb", strokeWidth=2)
    rule = alt.Chart(wide).mark_rule(color=AXIS, size=28).encode(x=x, opacity=alt.condition(hover, alt.value(0.35), alt.value(0)), tooltip=tips).add_params(hover)
    return style(alt.layer(rule, lines))


def error_table(p):
    rows = []
    for (region, crop), g in p.groupby(["region", "crop"]):
        b, m = metrics(g.assign(pred=g.pred_baseline)), metrics(g.assign(pred=g.pred_model))
        rows.append({"Region and crop": label(region, crop), "Seasons": g.year.nunique(), "Baseline production error": b["mape"], "Our model production error": m["mape"],
                     "Baseline yield error": b["nrmse"], "Our model yield error": m["nrmse"], "Improvement": 1 - m["mape"] / b["mape"]})
    return pd.DataFrame(rows).sort_values("Baseline production error", ascending=False)


held_out = load("backtest_predictions.csv")
tab_compare, tab_season, tab_try, tab_future = st.tabs(["Baseline vs our model", "Season by season", "Try the model", "Future risk"])

# ---------------------------------------------------------------- 1
with tab_compare:
    st.title("Does weather make yield forecasts better?")
    st.markdown("Both methods predict the yield of a contract crop on a farm for a season **they did not see in training**. "
                "The data is synthetic, so these results say nothing about real Apetit farms.")
    left, right = st.columns(2)
    with left:
        st.subheader("Baseline: farm average")
        st.markdown("The farm's average yield for that crop across the training seasons. It knows the farm but **ignores weather**, so it predicts about the same number every season.")
    with right:
        st.subheader("Our model: weather-aware regression")
        st.markdown("Farm effect + technology trend + soil + irrigation + crop-stage weather (drought, heat, rain at sowing and harvest). It uses **no same-season farm inputs**, because those aren't known in advance.")
    test_name = st.radio("How to test", list(TEST), horizontal=True, help="Leave one season out uses later seasons to predict earlier ones. Predicting forward only uses the past, so it's closer to real forecasting.")
    p = held_out[held_out.test == TEST[test_name]]
    mb, mm = metrics(p.assign(pred=p.pred_baseline)), metrics(p.assign(pred=p.pred_model))
    a, b, c = st.columns(3)
    a.metric("Regional production error", f"{mm['mape']:.1%}", f"{mm['mape'] - mb['mape']:+.1%} vs baseline {mb['mape']:.1%}", delta_color="inverse")
    b.metric("Farm-level yield error (nRMSE)", f"{mm['nrmse']:.3f}", f"{mm['nrmse'] - mb['nrmse']:+.3f} vs baseline {mb['nrmse']:.3f}", delta_color="inverse")
    c.metric("Scorer-style C1 score", f"{mm['score']:.1f}", f"{mm['score'] - mb['score']:+.1f} vs baseline {mb['score']:.1f}")
    st.warning("**Don't read the score as our real C1 result.** It applies the official formula to farm-level rows, while the hidden answers are per parcel and noisier. Model settings were also tuned on these seasons, so expect the real score to be lower.")
    st.subheader("Regional production error, by crop")
    st.caption("Average gap between predicted and actual total production per season. Shorter is better.")
    t = error_table(p)
    bars = t.melt(id_vars="Region and crop", value_vars=["Baseline production error", "Our model production error"], var_name="m", value_name="error")
    bars["series"] = bars.m.map({"Baseline production error": "Baseline", "Our model production error": "Our model"})
    order = t["Region and crop"].tolist()
    chart = alt.Chart(bars).mark_bar(size=14, cornerRadiusEnd=4).encode(
        y=alt.Y("Region and crop:N", sort=order, title=None, axis=alt.Axis(labelColor=INK, labelLimit=180)), yOffset=alt.YOffset("series:N", sort=["Baseline", "Our model"]),
        x=alt.X("error:Q", title="Production error", axis=alt.Axis(format=".0%"), scale=alt.Scale(domainMax=float(bars.error.max()) * 1.12)), color=alt.Color("series:N", scale=SERIES, title=None, legend=alt.Legend(values=["Baseline", "Our model"])),
        tooltip=[alt.Tooltip("Region and crop:N"), alt.Tooltip("series:N", title="Method"), alt.Tooltip("error:Q", format=".1%", title="Error")])
    labels = chart.mark_text(align="left", dx=5, fontSize=12).encode(text=alt.Text("error:Q", format=".1%"), color=alt.value(GRAY))
    st.altair_chart(style(chart + labels, 380), use_container_width=True)
    st.dataframe(t.style.format({"Baseline production error": "{:.1%}", "Our model production error": "{:.1%}", "Baseline yield error": "{:.3f}", "Our model yield error": "{:.3f}", "Improvement": "{:.0%}"}), hide_index=True, width="stretch")
    with st.expander("How the yield data was cleaned"):
        log = load("yield_corrections_log.csv")
        st.markdown(f"{(log.new_value.notna()).sum()} survey yields were corrected as ×10 slips and {(log.new_value.isna()).sum()} delivery-based yields were excluded as implausible. Every change is listed with its rule.")
        st.dataframe(log, hide_index=True, width="stretch")

# ---------------------------------------------------------------- 2
with tab_season:
    st.title("Season by season")
    st.markdown("The **baseline stays nearly flat**. The test of our model is whether it follows the good and bad seasons. Every point below is a prediction for a season held out of training.")
    pairs = [(r, c) for r, c in held_out[["region", "crop"]].drop_duplicates().sort_values(["region", "crop"]).itertuples(index=False)]
    f1, f2 = st.columns(2)
    pair = f1.selectbox("Region and crop", pairs, format_func=lambda x: label(*x), index=pairs.index(("FI_SW", "pea")))
    test2 = f2.selectbox("Test", list(TEST), key="test2")
    g = held_out[(held_out.test == TEST[test2]) & (held_out.region == pair[0]) & (held_out.crop == pair[1])]

    def to_long(d):
        rows = {}
        for year, q in d.groupby("year"):
            w = q.area_ha
            rows[year] = {"Actual": np.average(q.yield_t_ha, weights=w), "Baseline": np.average(q.pred_baseline, weights=w), "Our model": np.average(q.pred_model, weights=w)}
        return pd.DataFrame(rows).T.rename_axis("year").reset_index().melt("year", var_name="series", value_name="value")

    st.subheader(f"{label(*pair)}: area-weighted average yield")
    long = to_long(g)
    st.altair_chart(season_chart(long), use_container_width=True)
    wide = long.pivot(index="year", columns="series", values="value")
    wide["Baseline miss"], wide["Our model miss"] = wide.Baseline / wide.Actual - 1, wide["Our model"] / wide.Actual - 1
    st.dataframe(wide.reset_index().rename(columns={"year": "Season"}).style.format({"Actual": "{:.2f}", "Baseline": "{:.2f}", "Our model": "{:.2f}", "Baseline miss": "{:+.1%}", "Our model miss": "{:+.1%}"}), hide_index=True, width="stretch")
    st.subheader("Check a single farm")
    farms = sorted(g.farm_id.unique())
    farm = st.selectbox(f"Farm ({len(farms)} with data)", farms)
    fg = g[g.farm_id == farm]
    if fg.year.nunique() < 2:
        st.info("This farm has only one held-out season in this test. Pick another farm or the other test to see a line.")
    st.altair_chart(season_chart(to_long(fg)), use_container_width=True)
    st.caption("A single farm has more random variation than a regional average, and some seasons are missing where the farm didn't report.")

# ---------------------------------------------------------------- 3
with tab_try:
    st.title("Try the model")
    st.markdown("Pick a field, a crop and a season's weather. This runs the **final trained model live**, and shows why it landed on that number.")
    P = predictor()
    c1, c2, c3 = st.columns(3)
    region = c1.selectbox("Region", list(REGION), format_func=REGION.get)
    crops = ["pea"] if region == "SE_SKANE" else list(CROP)
    crop = c2.selectbox("Crop", crops, format_func=CROP.get)
    keys = [k for k in P.farm_mean.index if k[1] == crop and (k[0].startswith("S") == (region == "SE_SKANE"))]
    farm_t = c3.selectbox("Farm", sorted(k[0] for k in keys))
    c4, c5, c6, c7 = st.columns([1, 2, 1, 2])
    plots = P.parcels[P.parcels.farm_id == farm_t]
    parcel = c4.selectbox("Field", plots.index.tolist())
    wname = c5.selectbox("Weather", list(WEATHER))
    scenario, years = WEATHER[wname]
    year = c6.selectbox("Season", list(years), index=len(years) - 1)
    # Finnish farms never switch practice, so the model has no valid irrigation effect to show there.
    irr_name = c7.selectbox("Irrigation", ["Farm's usual practice", "Irrigated", "Not irrigated"] if region == "SE_SKANE" else ["Farm's usual practice"],
                            help="Only available for Sweden, where 167 farms switch practice. No Finnish farm does, so the effect can't be measured there.")
    r = P.predict(parcel, crop, scenario, year, {"Farm's usual practice": None, "Irrigated": 1.0, "Not irrigated": 0.0}[irr_name])
    a, b, c = st.columns(3)
    a.metric("Our model", f"{r['pred']:.2f} t/ha")
    a.caption(f"{r['pred'] / r['baseline'] - 1:+.1%} against the baseline")
    b.metric("Baseline: farm average", f"{r['baseline']:.2f} t/ha")
    b.caption("The same for any weather")
    obs = held_out[(held_out.test == "loyo") & (held_out.farm_id == farm_t) & (held_out.crop == crop) & (held_out.year == year)] if scenario == "historical" else pd.DataFrame()
    if len(obs):
        c.metric("Actual for this farm", f"{obs.yield_t_ha.iloc[0]:.2f} t/ha")
        c.caption(f"Held-out model prediction: {obs.pred_model.iloc[0]:.2f} t/ha; held-out baseline: {obs.pred_baseline.iloc[0]:.2f} t/ha")
    else:
        c.metric("Actual for this farm", "Not available")
        c.caption("Future season, or the farm didn't report")
    notes = [f"Soil-map class: {r['parcel'].soil_class_soilmap.replace('_', ' ')}, {r['parcel'].area_ha:.1f} ha. The soil map is only about 88% accurate.", f"This farm's usual irrigated share for this crop: {r['usual_irrigation']:.0%}."]
    if year > 2031:
        notes.append("Technology is held at 2025, so this shows the effect of weather only.")
    if scenario == "historical":
        notes.append("The farm-level comparison uses a season the model did not train on. The main figure comes from the final model, which did see this season, so use the Season by season tab to judge accuracy.")
    if irr_name != "Farm's usual practice":
        notes.append("The modelled irrigation effect is an estimate. It averages about the measured +6% for Sweden, but misses individual seasons and can turn slightly negative in very wet seasons, which is an artifact.")
    st.markdown("\n".join("- " + n for n in notes))
    st.subheader("Why this number")
    e = r["effects"]
    e = (np.exp(e) - 1).rename("effect").reset_index().rename(columns={"index": "driver"})
    e = e[e.effect.abs() >= 0.001].sort_values("effect")
    st.caption(f"Each bar is that driver's percentage effect, starting from {r['base']:.2f} t/ha for an average field and season. The effects multiply to give the model's result.")
    bar = alt.Chart(e).mark_bar(size=18, cornerRadiusEnd=4).encode(
        y=alt.Y("driver:N", sort=e.driver.tolist()[::-1], title=None, axis=alt.Axis(labelColor=INK, labelLimit=220)), x=alt.X("effect:Q", title="Effect on yield", axis=alt.Axis(format="+.0%"), scale=alt.Scale(domain=[min(0.0, float(e.effect.min()) * 1.25), max(0.0, float(e.effect.max()) * 1.25)])),
        color=alt.condition("datum.effect >= 0", alt.value(BLUE), alt.value(RED)), tooltip=[alt.Tooltip("driver:N", title="Driver"), alt.Tooltip("effect:Q", title="Effect", format="+.1%")])
    text = bar.mark_text(align=alt.expr("datum.effect >= 0 ? 'left' : 'right'"), dx=alt.expr("datum.effect >= 0 ? 5 : -5"), color=GRAY, fontSize=12).encode(text=alt.Text("effect:Q", format="+.1%"), color=alt.value(GRAY))
    rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=AXIS).encode(x="x:Q")
    st.altair_chart(style(bar + rule + text, max(220, 30 * len(e) + 60)), use_container_width=True)
    with st.expander("Weather values used"):
        w = r["weather"]
        st.dataframe(pd.DataFrame({"Measure": ["Sowing day of year", "Maturity day of year", "Drought stress, sensitive stage (0–1)", "Heat days at 27 °C or above, sensitive stage", "Rain in 14 days after sowing (mm)", "Rain in 10 days before harvest (mm)", "Warm, wet days, July–August", "May mean temperature (°C)"],
                                   "Value": [w.sow_doy, w.mat_doy, w.stress_sens, w.hot_sens, w.rain_postsow, w.rain_preharv, w.blight_days, w.may_t]}).round(2), hide_index=True, width="stretch")
    st.caption(f"Self-check: live predictions differ from the submitted C1 file by at most {P.check_against_submission(60):.4f} t/ha on a sample of 60 rows (the file is rounded to 3 decimals).")

# ---------------------------------------------------------------- 4
with tab_future:
    st.title("Future risk")
    st.warning("**No answers are public for these tasks, so neither method can be scored here.** The first two tabs show how far the model can be trusted on past seasons. These charts are the model's estimates, not measured accuracy.")
    st.subheader("Forecast 2027–2031, against the package's reference baseline")
    fc = load("C1_forecast_comparison.csv")
    fpairs = [(r_, c_) for r_, c_ in fc[["region", "crop"]].drop_duplicates().itertuples(index=False)]
    fp = st.selectbox("Region and crop", fpairs, format_func=lambda x: label(*x), key="fp", index=fpairs.index(("FI_SW", "pea")))
    q = fc[(fc.region == fp[0]) & (fc.crop == fp[1])]
    hist = held_out[(held_out.test == "loyo") & (held_out.region == fp[0]) & (held_out.crop == fp[1])]
    hist = hist.groupby("year").apply(lambda d: np.average(d.yield_t_ha, weights=d.area_ha), include_groups=False).rename("value").reset_index().assign(series="Actual")
    long_f = pd.concat([hist, q.rename(columns={"model_t_ha": "value"})[["year", "value"]].assign(series="Our model"), q.rename(columns={"package_baseline_t_ha": "value"})[["year", "value"]].assign(series="Baseline")], ignore_index=True)
    st.altair_chart(season_chart(long_f), use_container_width=True)
    st.caption("Baseline here is the package's reference method: the farm's survey average since 2016, or a fixed 3.4 t/ha for Swedish peas. It varies slightly between years only because the planted fields change. Our model reacts to one supplied weather realisation for 2027–2031.")
    st.subheader("Yield change by 2041–2060, against 1991–2020")
    sc = st.selectbox("Climate scenario", ["ssp126", "ssp245", "ssp585"], index=2, format_func={"ssp126": "SSP1-2.6, low emissions", "ssp245": "SSP2-4.5, middle emissions", "ssp585": "SSP5-8.5, high emissions"}.get)
    d = load("C2_detail_with_uncertainty.csv")
    d = d[d.scenario == sc].assign(name=lambda x: [label(a_, b_) for a_, b_ in zip(x.region, x.crop)]).sort_values("mean_yield_change_pct")
    enc_y = alt.Y("name:N", sort=d.name.tolist(), title=None, axis=alt.Axis(labelColor=INK, labelLimit=180))
    span = alt.Chart(d).mark_rule(color=BLUE, strokeWidth=2, opacity=0.4).encode(y=enc_y, x=alt.X("change_min:Q", title="Change in mean yield (%). Zero is the package's “no change” baseline"), x2="change_max:Q")
    dot = alt.Chart(d).mark_circle(size=110, color=BLUE, opacity=1, stroke="#fcfcfb", strokeWidth=2).encode(y=enc_y, x="mean_yield_change_pct:Q", tooltip=[alt.Tooltip("name:N", title="Crop"), alt.Tooltip("mean_yield_change_pct:Q", format="+.1f", title="Change %"), alt.Tooltip("change_min:Q", format="+.1f", title="Low %"), alt.Tooltip("change_max:Q", format="+.1f", title="High %"), alt.Tooltip("p_bad_year:Q", format=".0%", title="Bad-year chance")])
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=ORANGE, strokeWidth=2).encode(x="x:Q")
    st.altair_chart(style(zero + span + dot, 280), use_container_width=True)
    st.caption("Dot: our estimate. Line: the range when each training season is left out in turn, which is not total uncertainty. Orange: the baseline of no change. Swedish peas (9 seasons) and Finnish peas are low confidence.")
    table = d[["name", "mean_yield_change_pct", "change_min", "change_max", "p_bad_year"]].assign(baseline_change=0.0, baseline_bad=0.10).rename(columns={"name": "Region and crop", "mean_yield_change_pct": "Our change %", "change_min": "Low %", "change_max": "High %", "p_bad_year": "Our bad-year chance", "baseline_change": "Baseline change %", "baseline_bad": "Baseline bad-year chance"})
    st.dataframe(table.style.format({"Our change %": "{:+.1f}", "Low %": "{:+.1f}", "High %": "{:+.1f}", "Our bad-year chance": "{:.0%}", "Baseline change %": "{:.1f}", "Baseline bad-year chance": "{:.0%}"}), hide_index=True, width="stretch")
    st.subheader("Cost of replacing shortfalls with imports")
    euros = load("C3_euro_risk.csv")
    totals = euros.groupby(["region", "ssp"]).expected_cost_eur_yr.sum().unstack("ssp")[["baseline", "ssp126", "ssp245", "ssp585"]].rename(index=REGION, columns={"baseline": "Today's climate", "ssp126": "SSP1-2.6", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}).rename_axis("Region").reset_index()
    fmt = {c_: "€{:,.0f}" for c_ in totals.columns if c_ != "Region"}
    st.dataframe(totals.style.format(fmt), hide_index=True, width="stretch")
    st.caption("Expected € a year: shortfall against today's average × 2025 contract price × replacement premium. It counts only the premium, and excludes import emissions, lost margin and price shocks. The Swedish figures are low confidence.")
    with st.expander("By crop"):
        st.dataframe(euros.assign(region=euros.region.map(REGION), crop=euros.crop.map(CROP)), hide_index=True, width="stretch")
