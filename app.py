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
from i18n import CHART_LOCALE, LANGUAGES, eur, lang, num, t  # noqa: E402
from inference import Predictor  # noqa: E402

BLUE, ORANGE, RED, GRAY = "#2a78d6", "#eb6834", "#e34948", "#52514e"
INK, MUTED, GRID, AXIS = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"
REGION = {"FI_SW": "Finland", "SE_SKANE": "Sweden"}
CROP = {"pea": "Pea", "turnip_rape": "Turnip rape", "potato": "Potato", "carrot": "Carrot", "spinach": "Spinach"}
TEST = {"loyo": "Leave one season out", "forward": "Predict 2022–2026 from earlier seasons"}
WEATHER = {"history": ("Historical weather (1991–2026)", "historical", range(1991, 2027)),
           "c1": ("SSP2-4.5, the C1 forecast seasons (2027–2031)", "ssp245", range(2027, 2032)),
           "low": ("SSP1-2.6, low emissions (2041–2060)", "ssp126", range(2041, 2061)),
           "middle": ("SSP2-4.5, middle emissions (2041–2060)", "ssp245", range(2041, 2061)),
           "high": ("SSP5-8.5, high emissions (2041–2060)", "ssp585", range(2041, 2061))}
IRRIGATION = {"usual": ("Farm's usual practice", None), "irrigated": ("Irrigated", 1.0), "rainfed": ("Not irrigated", 0.0)}
SCENARIO = {"ssp126": "SSP1-2.6, low emissions", "ssp245": "SSP2-4.5, middle emissions", "ssp585": "SSP5-8.5, high emissions"}
COST_SCENARIO = {"baseline": "Today's climate", "ssp126": "SSP1-2.6", "ssp245": "SSP2-4.5", "ssp585": "SSP5-8.5"}

st.set_page_config(page_title=t("Apetit yield model viewer"), layout="wide")


@st.cache_resource(show_spinner=False)
def predictor():
    return Predictor()


@st.cache_data
def load(name):
    return pd.read_csv(OUT / name)


def keep_selections():
    """Changing language relabels every widget, which would otherwise reset it to its default."""
    for key in list(st.session_state.keys()):
        st.session_state[key] = st.session_state[key]


def label(region, crop):
    return f"{t(REGION[region])}, {t(CROP[crop]).lower()}"


def series_scale():
    return alt.Scale(domain=[t("Actual"), t("Baseline"), t("Our model")], range=[GRAY, ORANGE, BLUE])


def style(chart, height=320):
    return (chart.properties(height=height, usermeta={"embedOptions": {"formatLocale": CHART_LOCALE[lang()]}}).configure_view(stroke=None, fill="#fcfcfb")
            .configure_axis(gridColor=GRID, domainColor=AXIS, tickColor=AXIS, labelColor=MUTED, titleColor=MUTED, labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelColor=INK, titleColor=MUTED, orient="top", labelFontSize=13, symbolStrokeWidth=3).configure(background="#fcfcfb"))


def season_chart(long):
    """Lines per series, with a season-wide hover readout."""
    long = long.assign(series=long.series.map(t))
    wide = long.pivot_table(index="year", columns="series", values="value").reset_index()
    x = alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0))
    base = alt.Chart(long).encode(x=x, y=alt.Y("value:Q", title=t("Yield (t/ha)"), scale=alt.Scale(zero=False)), color=alt.Color("series:N", scale=series_scale(), title=None))
    hover = alt.selection_point(fields=["year"], nearest=True, on="pointerover", clear="pointerout", empty=False)
    tips = [alt.Tooltip("year:O", title=t("Season"))] + [alt.Tooltip(f"{c}:Q", format=".2f") for c in wide.columns if c != "year"]
    lines = base.mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round") + base.mark_circle(size=70, opacity=1, stroke="#fcfcfb", strokeWidth=2)
    rule = alt.Chart(wide).mark_rule(color=AXIS, size=28).encode(x=x, opacity=alt.condition(hover, alt.value(0.35), alt.value(0)), tooltip=tips).add_params(hover)
    return style(alt.layer(rule, lines))


def show(table, formats=None):
    """Table with translated headers. Formats are number specs, or functions for anything else."""
    cells = {t(c): (f if callable(f) else lambda v, s=f: num(v, s)) for c, f in (formats or {}).items()}
    st.dataframe(table.rename(columns=t).style.format(cells, na_rep="–"), hide_index=True, width="stretch")


def error_table(p):
    rows = []
    for (region, crop), g in p.groupby(["region", "crop"]):
        b, m = metrics(g.assign(pred=g.pred_baseline)), metrics(g.assign(pred=g.pred_model))
        rows.append({"Region and crop": label(region, crop), "Seasons": g.year.nunique(), "Baseline production error": b["mape"], "Our model production error": m["mape"],
                     "Baseline yield error": b["nrmse"], "Our model yield error": m["nrmse"], "Improvement": 1 - m["mape"] / b["mape"]})
    return pd.DataFrame(rows).sort_values("Baseline production error", ascending=False)


# Defaults go through session state: a widget can't have both a default argument and a value restored by keep_selections.
for key, default in {"season_pair": ("FI_SW", "pea"), "future_pair": ("FI_SW", "pea"), "future_scenario": "ssp585"}.items():
    st.session_state.setdefault(key, default)
_, language = st.columns([5, 1])
language.selectbox("Language / Kieli", list(LANGUAGES), format_func=LANGUAGES.get, key="lang", on_change=keep_selections)

held_out = load("backtest_predictions.csv")
tab_compare, tab_season, tab_try, tab_future = st.tabs([t("Baseline vs our model"), t("Season by season"), t("Try the model"), t("Future risk")])

# ---------------------------------------------------------------- 1
with tab_compare:
    st.title(t("Does weather make yield forecasts better?"))
    st.markdown(t("Both methods predict the yield of a contract crop on a farm for a season **they did not see in training**. The data is synthetic, so these results say nothing about real Apetit farms."))
    left, right = st.columns(2)
    with left:
        st.subheader(t("Baseline: farm average"))
        st.markdown(t("The farm's average yield for that crop across the training seasons. It knows the farm but **ignores weather**, so it predicts about the same number every season."))
    with right:
        st.subheader(t("Our model: weather-aware regression"))
        st.markdown(t("Farm effect + technology trend + soil + irrigation + crop-stage weather (drought, heat, rain at sowing and harvest). It uses **no same-season farm inputs**, because those aren't known in advance."))
    test = st.radio(t("How to test"), list(TEST), format_func=lambda x: t(TEST[x]), horizontal=True, key="compare_test", help=t("Leave one season out uses later seasons to predict earlier ones. Predicting forward only uses the past, so it's closer to real forecasting."))
    p = held_out[held_out.test == test]
    mb, mm = metrics(p.assign(pred=p.pred_baseline)), metrics(p.assign(pred=p.pred_model))
    a, b, c = st.columns(3)
    a.metric(t("Regional production error"), num(mm["mape"], ".1%"), t("{delta} vs baseline {base}", delta=num(mm["mape"] - mb["mape"], "+.1%"), base=num(mb["mape"], ".1%")), delta_color="inverse")
    b.metric(t("Farm-level yield error (nRMSE)"), num(mm["nrmse"], ".3f"), t("{delta} vs baseline {base}", delta=num(mm["nrmse"] - mb["nrmse"], "+.3f"), base=num(mb["nrmse"], ".3f")), delta_color="inverse")
    c.metric(t("Scorer-style C1 score"), num(mm["score"], ".1f"), t("{delta} vs baseline {base}", delta=num(mm["score"] - mb["score"], "+.1f"), base=num(mb["score"], ".1f")))
    st.warning(t("**Don't read the score as our real C1 result.** It applies the official formula to farm-level rows, while the hidden answers are per parcel and noisier. Model settings were also tuned on these seasons, so expect the real score to be lower."))
    st.subheader(t("Regional production error, by crop"))
    st.caption(t("Average gap between predicted and actual total production per season. Shorter is better."))
    errors = error_table(p)
    bars = errors.melt(id_vars="Region and crop", value_vars=["Baseline production error", "Our model production error"], var_name="m", value_name="error")
    bars["series"] = bars.m.map({"Baseline production error": t("Baseline"), "Our model production error": t("Our model")})
    order = errors["Region and crop"].tolist()
    chart = alt.Chart(bars).mark_bar(size=14, cornerRadiusEnd=4).encode(
        y=alt.Y("Region and crop:N", sort=order, title=None, axis=alt.Axis(labelColor=INK, labelLimit=180)), yOffset=alt.YOffset("series:N", sort=[t("Baseline"), t("Our model")]),
        x=alt.X("error:Q", title=t("Production error"), axis=alt.Axis(format=".0%"), scale=alt.Scale(domainMax=float(bars.error.max()) * 1.12)), color=alt.Color("series:N", scale=series_scale(), title=None, legend=alt.Legend(values=[t("Baseline"), t("Our model")])),
        tooltip=[alt.Tooltip("Region and crop:N", title=t("Region and crop")), alt.Tooltip("series:N", title=t("Method")), alt.Tooltip("error:Q", format=".1%", title=t("Error"))])
    labels = chart.mark_text(align="left", dx=5, fontSize=12).encode(text=alt.Text("error:Q", format=".1%"), color=alt.value(GRAY))
    st.altair_chart(style(chart + labels, 380), use_container_width=True)
    show(errors, {"Baseline production error": ".1%", "Our model production error": ".1%", "Baseline yield error": ".3f", "Our model yield error": ".3f", "Improvement": ".0%"})
    with st.expander(t("How the yield data was cleaned")):
        log = load("yield_corrections_log.csv")
        st.markdown(t("{fixed} survey yields were corrected as ×10 slips and {excluded} delivery-based yields were excluded as implausible. Every change is listed with its rule.", fixed=log.new_value.notna().sum(), excluded=log.new_value.isna().sum()))
        show(log.assign(rule=log.rule.map(t)).rename(columns={"record_key": "Record", "field": "Data field", "old_value": "Old value", "new_value": "New value", "rule": "Rule", "source": "Source"}), {"Old value": ".2f", "New value": ".2f"})

# ---------------------------------------------------------------- 2
with tab_season:
    st.title(t("Season by season"))
    st.markdown(t("The **baseline stays nearly flat**. The test of our model is whether it follows the good and bad seasons. Every point below is a prediction for a season held out of training."))
    pairs = [(r, c) for r, c in held_out[["region", "crop"]].drop_duplicates().sort_values(["region", "crop"]).itertuples(index=False)]
    f1, f2 = st.columns(2)
    pair = f1.selectbox(t("Region and crop"), pairs, format_func=lambda x: label(*x), key="season_pair")
    test2 = f2.selectbox(t("Test"), list(TEST), format_func=lambda x: t(TEST[x]), key="season_test")
    g = held_out[(held_out.test == test2) & (held_out.region == pair[0]) & (held_out.crop == pair[1])]

    def to_long(d):
        rows = {}
        for year, q in d.groupby("year"):
            w = q.area_ha
            rows[year] = {"Actual": np.average(q.yield_t_ha, weights=w), "Baseline": np.average(q.pred_baseline, weights=w), "Our model": np.average(q.pred_model, weights=w)}
        return pd.DataFrame(rows).T.rename_axis("year").reset_index().melt("year", var_name="series", value_name="value")

    st.subheader(t("{name}: area-weighted average yield", name=label(*pair)))
    long = to_long(g)
    st.altair_chart(season_chart(long), use_container_width=True)
    wide = long.pivot(index="year", columns="series", values="value")
    wide["Baseline miss"], wide["Our model miss"] = wide.Baseline / wide.Actual - 1, wide["Our model"] / wide.Actual - 1
    show(wide.reset_index().rename(columns={"year": "Season"}), {"Actual": ".2f", "Baseline": ".2f", "Our model": ".2f", "Baseline miss": "+.1%", "Our model miss": "+.1%"})
    st.subheader(t("Check a single farm"))
    farms = sorted(g.farm_id.unique())
    farm = st.selectbox(t("Farm ({n} with data)", n=len(farms)), farms, key="season_farm")
    fg = g[g.farm_id == farm]
    if fg.year.nunique() < 2:
        st.info(t("This farm has only one held-out season in this test. Pick another farm or the other test to see a line."))
    st.altair_chart(season_chart(to_long(fg)), use_container_width=True)
    st.caption(t("A single farm has more random variation than a regional average, and some seasons are missing where the farm didn't report."))

# ---------------------------------------------------------------- 3
with tab_try:
    st.title(t("Try the model"))
    st.markdown(t("Pick a field, a crop and a season's weather. This runs the **final trained model live**, and shows why it landed on that number."))
    with st.spinner(t("Loading the trained models")):
        P = predictor()
    c1, c2, c3 = st.columns(3)
    region = c1.selectbox(t("Region"), list(REGION), format_func=lambda x: t(REGION[x]), key="try_region")
    crops = ["pea"] if region == "SE_SKANE" else list(CROP)
    crop = c2.selectbox(t("Crop"), crops, format_func=lambda x: t(CROP[x]), key="try_crop")
    keys = [k for k in P.farm_mean.index if k[1] == crop and (k[0].startswith("S") == (region == "SE_SKANE"))]
    farm_t = c3.selectbox(t("Farm"), sorted(k[0] for k in keys), key="try_farm")
    c4, c5, c6, c7 = st.columns([1, 2, 1, 2])
    plots = P.parcels[P.parcels.farm_id == farm_t]
    parcel = c4.selectbox(t("Field"), plots.index.tolist(), key="try_parcel")
    weather = c5.selectbox(t("Weather"), list(WEATHER), format_func=lambda x: t(WEATHER[x][0]), key="try_weather")
    _, scenario, years = WEATHER[weather]
    if st.session_state.get("try_year") not in years:
        st.session_state.try_year = years[-1]
    year = c6.selectbox(t("Season"), list(years), key="try_year")
    # Finnish farms never switch practice, so the model has no valid irrigation effect to show there.
    irrigation = c7.selectbox(t("Irrigation"), list(IRRIGATION) if region == "SE_SKANE" else ["usual"], format_func=lambda x: t(IRRIGATION[x][0]), key="try_irrigation",
                              help=t("Only available for Sweden, where 167 farms switch practice. No Finnish farm does, so the effect can't be measured there."))
    r = P.predict(parcel, crop, scenario, year, IRRIGATION[irrigation][1])
    a, b, c = st.columns(3)
    a.metric(t("Our model"), f"{num(r['pred'])} t/ha")
    a.caption(t("{pct} against the baseline", pct=num(r["pred"] / r["baseline"] - 1, "+.1%")))
    b.metric(t("Baseline: farm average"), f"{num(r['baseline'])} t/ha")
    b.caption(t("The same for any weather"))
    obs = held_out[(held_out.test == "loyo") & (held_out.farm_id == farm_t) & (held_out.crop == crop) & (held_out.year == year)] if scenario == "historical" else pd.DataFrame()
    if len(obs):
        c.metric(t("Actual for this farm"), f"{num(obs.yield_t_ha.iloc[0])} t/ha")
        c.caption(t("Held-out model prediction: {model} t/ha; held-out baseline: {base} t/ha", model=num(obs.pred_model.iloc[0]), base=num(obs.pred_baseline.iloc[0])))
    else:
        c.metric(t("Actual for this farm"), t("Not available"))
        c.caption(t("Future season, or the farm didn't report"))
    notes = [t("Soil-map class: {soil}, {area} ha. The soil map is only about 88% accurate.", soil=t(r["parcel"].soil_class_soilmap.replace("_", " ")), area=num(r["parcel"].area_ha, ".1f")), t("This farm's usual irrigated share for this crop: {share}.", share=num(r["usual_irrigation"], ".0%"))]
    if year > 2031:
        notes.append(t("Technology is held at 2025, so this shows the effect of weather only."))
    if scenario == "historical":
        notes.append(t("The farm-level comparison uses a season the model did not train on. The main figure comes from the final model, which did see this season, so use the Season by season tab to judge accuracy."))
    if irrigation != "usual":
        notes.append(t("The modelled irrigation effect is an estimate. It averages about the measured +6% for Sweden, but misses individual seasons and can turn slightly negative in very wet seasons, which is an artifact."))
    st.markdown("\n".join("- " + n for n in notes))
    st.subheader(t("Why this number"))
    e = r["effects"]
    e = (np.exp(e) - 1).rename("effect").reset_index().rename(columns={"index": "driver"})
    e = e[e.effect.abs() >= 0.001].sort_values("effect").assign(driver=lambda x: x.driver.map(t))
    st.caption(t("Each bar is that driver's percentage effect, starting from {base} t/ha for an average field and season. The effects multiply to give the model's result.", base=num(r["base"])))
    bar = alt.Chart(e).mark_bar(size=18, cornerRadiusEnd=4).encode(
        y=alt.Y("driver:N", sort=e.driver.tolist()[::-1], title=None, axis=alt.Axis(labelColor=INK, labelLimit=220)), x=alt.X("effect:Q", title=t("Effect on yield"), axis=alt.Axis(format="+.0%"), scale=alt.Scale(domain=[min(0.0, float(e.effect.min()) * 1.25), max(0.0, float(e.effect.max()) * 1.25)])),
        color=alt.condition("datum.effect >= 0", alt.value(BLUE), alt.value(RED)), tooltip=[alt.Tooltip("driver:N", title=t("Driver")), alt.Tooltip("effect:Q", title=t("Effect"), format="+.1%")])
    text = bar.mark_text(align=alt.expr("datum.effect >= 0 ? 'left' : 'right'"), dx=alt.expr("datum.effect >= 0 ? 5 : -5"), color=GRAY, fontSize=12).encode(text=alt.Text("effect:Q", format="+.1%"), color=alt.value(GRAY))
    rule = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=AXIS).encode(x="x:Q")
    st.altair_chart(style(bar + rule + text, max(220, 30 * len(e) + 60)), use_container_width=True)
    with st.expander(t("Weather values used")):
        w = r["weather"]
        show(pd.DataFrame({"Measure": [t(m) for m in ["Sowing day of year", "Maturity day of year", "Drought stress, sensitive stage (0–1)", "Heat days at 27 °C or above, sensitive stage", "Rain in 14 days after sowing (mm)", "Rain in 10 days before harvest (mm)", "Warm, wet days, July–August", "May mean temperature (°C)"]],
                           "Value": [w.sow_doy, w.mat_doy, w.stress_sens, w.hot_sens, w.rain_postsow, w.rain_preharv, w.blight_days, w.may_t]}).round(2), {"Value": "g"})
    st.caption(t("Self-check: live predictions differ from the submitted C1 file by at most {diff} t/ha on a sample of 60 rows (the file is rounded to 3 decimals).", diff=num(P.check_against_submission(60), ".4f")))

# ---------------------------------------------------------------- 4
with tab_future:
    st.title(t("Future risk"))
    st.warning(t("**No answers are public for these tasks, so neither method can be scored here.** The first two tabs show how far the model can be trusted on past seasons. These charts are the model's estimates, not measured accuracy."))
    st.subheader(t("Forecast 2027–2031, against the package's reference baseline"))
    fc = load("C1_forecast_comparison.csv")
    fpairs = [(r_, c_) for r_, c_ in fc[["region", "crop"]].drop_duplicates().itertuples(index=False)]
    fp = st.selectbox(t("Region and crop"), fpairs, format_func=lambda x: label(*x), key="future_pair")
    q = fc[(fc.region == fp[0]) & (fc.crop == fp[1])]
    hist = held_out[(held_out.test == "loyo") & (held_out.region == fp[0]) & (held_out.crop == fp[1])]
    hist = hist.groupby("year").apply(lambda d: np.average(d.yield_t_ha, weights=d.area_ha), include_groups=False).rename("value").reset_index().assign(series="Actual")
    long_f = pd.concat([hist, q.rename(columns={"model_t_ha": "value"})[["year", "value"]].assign(series="Our model"), q.rename(columns={"package_baseline_t_ha": "value"})[["year", "value"]].assign(series="Baseline")], ignore_index=True)
    st.altair_chart(season_chart(long_f), use_container_width=True)
    st.caption(t("Baseline here is the package's reference method: the farm's survey average since 2016, or a fixed 3.4 t/ha for Swedish peas. It varies slightly between years only because the planted fields change. Our model reacts to one supplied weather realisation for 2027–2031."))
    st.subheader(t("Yield change by 2041–2060, against 1991–2020"))
    sc = st.selectbox(t("Climate scenario"), list(SCENARIO), format_func=lambda x: t(SCENARIO[x]), key="future_scenario")
    d = load("C2_detail_with_uncertainty.csv")
    d = d[d.scenario == sc].assign(name=lambda x: [label(a_, b_) for a_, b_ in zip(x.region, x.crop)]).sort_values("mean_yield_change_pct")
    enc_y = alt.Y("name:N", sort=d.name.tolist(), title=None, axis=alt.Axis(labelColor=INK, labelLimit=180))
    span = alt.Chart(d).mark_rule(color=BLUE, strokeWidth=2, opacity=0.4).encode(y=enc_y, x=alt.X("change_min:Q", title=t("Change in mean yield (%). Zero is the package's “no change” baseline")), x2="change_max:Q")
    dot = alt.Chart(d).mark_circle(size=110, color=BLUE, opacity=1, stroke="#fcfcfb", strokeWidth=2).encode(y=enc_y, x="mean_yield_change_pct:Q", tooltip=[alt.Tooltip("name:N", title=t("Crop")), alt.Tooltip("mean_yield_change_pct:Q", format="+.1f", title=t("Change %")), alt.Tooltip("change_min:Q", format="+.1f", title=t("Low %")), alt.Tooltip("change_max:Q", format="+.1f", title=t("High %")), alt.Tooltip("p_bad_year:Q", format=".0%", title=t("Bad-year chance"))])
    zero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color=ORANGE, strokeWidth=2).encode(x="x:Q")
    st.altair_chart(style(zero + span + dot, 280), use_container_width=True)
    st.caption(t("Dot: our estimate. Line: the range when each training season is left out in turn, which is not total uncertainty. Orange: the baseline of no change. Swedish peas (9 seasons) and Finnish peas are low confidence."))
    table = d[["name", "mean_yield_change_pct", "change_min", "change_max", "p_bad_year"]].assign(baseline_change=0.0, baseline_bad=0.10).rename(columns={"name": "Region and crop", "mean_yield_change_pct": "Our change %", "change_min": "Low %", "change_max": "High %", "p_bad_year": "Our bad-year chance", "baseline_change": "Baseline change %", "baseline_bad": "Baseline bad-year chance"})
    show(table, {"Our change %": "+.1f", "Low %": "+.1f", "High %": "+.1f", "Our bad-year chance": ".0%", "Baseline change %": ".1f", "Baseline bad-year chance": ".0%"})
    st.subheader(t("Cost of replacing shortfalls with imports"))
    euros = load("C3_euro_risk.csv")
    totals = euros.groupby(["region", "ssp"]).expected_cost_eur_yr.sum().unstack("ssp")[list(COST_SCENARIO)].rename(index=lambda x: t(REGION[x]), columns=COST_SCENARIO).rename_axis("Region").reset_index()
    show(totals, {c_: eur for c_ in totals.columns if c_ != "Region"})
    st.caption(t("Expected € a year: shortfall against today's average × 2025 contract price × replacement premium. It counts only the premium, and excludes import emissions, lost margin and price shocks. The Swedish figures are low confidence."))
    with st.expander(t("By crop")):
        show(euros.assign(region=euros.region.map(lambda x: t(REGION[x])), crop=euros.crop.map(lambda x: t(CROP[x])), ssp=euros.ssp.map(lambda x: t(COST_SCENARIO[x])))
             .rename(columns={"region": "Region", "crop": "Crop", "ssp": "Scenario", "area_ha": "Area (ha)", "price_eur_t": "Contract price (€/t)", "premium": "Replacement premium", "baseline_t": "Baseline production (t)", "mean_shortfall_t": "Average shortfall (t)",
                              "expected_cost_eur_yr": "Expected cost (€/year)", "bad_year_p90_cost_eur": "Bad-year cost, 90th percentile (€)", "added_vs_todays_climate_eur_yr": "Added against today's climate (€/year)"}),
             {"Area (ha)": ",.0f", "Contract price (€/t)": ",.0f", "Replacement premium": ".0%", "Baseline production (t)": ",.0f", "Average shortfall (t)": ",.0f", "Expected cost (€/year)": eur, "Bad-year cost, 90th percentile (€)": eur, "Added against today's climate (€/year)": eur})
