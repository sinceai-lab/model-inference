"""Inputs for the farming team's advice page. Free of Streamlit, so other front ends can call the same functions."""
import numpy as np
import pandas as pd

from config import DATA, OUT, SOILS
from models import _term_group

# Apetit asked for two stories. The pairing comes from physical_pathway_proxy in transition_scenarios.csv.
STORIES = {"below_2c": "ssp126", "current_policies": "ssp585"}
TECH_YEAR = 2025
WARMTH, WATER, WET = "Warmth and season timing", "Water", "Warm, wet days"
THEME_ORDER = [WARMTH, WATER, WET]
THEMES = {"Heat": WARMTH, "May temperature": WARMTH, "Season timing": WARMTH, "Drought stress": WATER, "Season rain and evaporation": WATER, "Rain after sowing": WATER,
          "Rain before harvest": WATER, "Irrigation": WATER, "Warm, wet days": WET}
MEASURED, MODEL, ASSUMED = "Measured in the data", "Model estimate", "Weather calculation using assumed crop values"
EXPERT, ILLUSTRATIVE, GAP = "From the Q&A with Apetit", "Illustrative package values", "Data gap"
CONFIDENCE = {("FI_SW", "turnip_rape"): "Medium", ("FI_SW", "spinach"): "Low to medium: few farms", ("FI_SW", "potato"): "Low to medium: few farms", ("FI_SW", "carrot"): "Low: few farms",
              ("FI_SW", "pea"): "Low: sign changes with model choice", ("SE_SKANE", "pea"): "Low: 9 seasons"}
SEASON_MEASURES = ["sow_doy", "mat_doy", "stress_sens", "stress_late", "hot_season", "blight_days", "rain_preharv"]


def weather_sets(f):
    """1991-2020 as today's climate; each scenario is its 20 supplied years plus 30 shifted historical years."""
    return pd.concat([
        f[(f.weather_set == "raw") & (f.scenario == "historical") & f.year.between(1991, 2020)].assign(run="baseline", ssp="baseline"),
        f[(f.weather_set == "raw") & f.scenario.isin(["ssp126", "ssp245", "ssp585"]) & f.year.between(2041, 2060)].assign(run="raw", ssp=lambda d: d.scenario),
        f[f.weather_set == "delta"].assign(run="delta", ssp=lambda d: d.scenario),
    ]).rename(columns={"soil": "soil_class_soilmap"})


def _with_weather(fields, sets, crop):
    return fields[fields.crop == crop].merge(sets[sets.crop == crop], on=["cell_id", "soil_class_soilmap", "crop"])


def _weighted(d, values, keys):
    return values.mul(d.area_ha, axis=0).groupby([d[k] for k in keys]).sum().div(d.groupby(keys).area_ha.sum(), axis=0)


def driver_changes(models, mix, sets):
    """Each driver's yield effect in a scenario, relative to today's climate. Fields and technology are held fixed."""
    rows = []
    for crop, model in models.items():
        d = _with_weather(mix, sets, crop).assign(year=TECH_YEAR).reset_index(drop=True)
        coef = pd.Series(model.m.coef_[:len(model.cols)], index=model.cols)
        effects = (model._x(d).reindex(columns=model.cols, fill_value=0.0) * coef).T.groupby(_term_group).sum().T
        means = _weighted(d, effects, ["region", "ssp"])
        for region, g in means.groupby(level="region"):
            today = g.xs("baseline", level="ssp").iloc[0]
            for ssp, row in g.droplevel("region").iterrows():
                if ssp != "baseline":
                    rows += [dict(region=region, crop=crop, ssp=ssp, driver=k, effect=np.exp(v) - 1) for k, v in (row - today).items()]
    out = pd.DataFrame(rows)
    return out[out.effect.abs() > 1e-9].round(5)


def season_shift(mix, sets):
    """Area-weighted season dates and stresses per climate, using the assumed crop thresholds in config.py."""
    rows = []
    for crop in mix.crop.unique():
        d = _with_weather(mix, sets, crop).reset_index(drop=True)
        rows.append(_weighted(d, d[SEASON_MEASURES], ["region", "ssp"]).reset_index().assign(crop=crop))
    return pd.concat(rows, ignore_index=True).round(3)


def policy_paths():
    """Illustrative carbon and input price paths for the two stories."""
    t = pd.read_csv(DATA / "05_scenarios/transition_scenarios.csv")
    return t[t.scenario.isin(STORIES)][["scenario", "year", "carbon_price_eur_t", "n_fertiliser_price_index", "diesel_price_index"]]


def input_use():
    """Median fertiliser and diesel per hectare since 2021, as exposure to those prices."""
    s = pd.read_csv(DATA / "03_farming/farm_survey_fi.csv")
    fi = s[s.year >= 2021].groupby("crop")[["n_mineral_kg_ha", "diesel_l_ha"]].median().round(1)
    h = pd.read_csv(DATA / "03_farming/foodhills_odlingsdata_se.csv", sep=";", decimal=",")
    h = h[h["skördeår"] >= 2021]
    se = pd.DataFrame(dict(n_mineral_kg_ha=[h["kvävegiva_kg_ha"].median()], diesel_l_ha=[h["diesel_l_ha"].median()]), index=["pea"]).round(1)
    return pd.concat({"FI_SW": fi, "SE_SKANE": se}, names=["region", "crop"])


def load_outputs():
    return dict(risk=pd.read_csv(OUT / "C2_detail_with_uncertainty.csv"), drivers=pd.read_csv(OUT / "advisor_drivers.csv"), shift=pd.read_csv(OUT / "advisor_season_shift.csv"), cost=pd.read_csv(OUT / "C3_euro_risk.csv"),
                bad_check=pd.read_csv(OUT / "C2_bad_year_check.csv"), irrigation=pd.read_csv(OUT / "C3_irrigation_evidence.csv"), irrigation_seasons=pd.read_csv(OUT / "C3_irrigation_se_within_farm.csv"),
                policy=policy_paths(), inputs=input_use())


def themes(outputs, region, crop, ssp):
    """Weather drivers are correlated and offset each other, so only their themes are safe to read as a story."""
    d = outputs["drivers"]
    d = d[(d.region == region) & (d.crop == crop) & (d.ssp == ssp)]
    return np.expm1(np.log1p(d.effect).groupby(d.driver.map(THEMES)).sum()).reindex(THEME_ORDER, fill_value=0.0)


def season_summary(outputs, region, crop, ssp):
    """Changes against today's climate. Sowing is capped at 10 April by an assumption, so its shift is a lower bound."""
    s = outputs["shift"]
    s = s[(s.region == region) & (s.crop == crop)].set_index("ssp")
    now, then = s.loc["baseline"], s.loc[ssp]
    return dict(maturity_days_earlier=now.mat_doy - then.mat_doy, sowing_days_earlier=now.sow_doy - then.sow_doy, hot_days_today=now.hot_season, hot_days=then.hot_season,
                wet_days_today=now.blight_days, wet_days=then.blight_days, stress_today=now.stress_sens, stress=then.stress_sens)


def advice(outputs, region, crop, story):
    """Draft rules for advisors to review. Each returns its decision, its text template, the values and the evidence behind it."""
    ssp = STORIES[story]
    risk = outputs["risk"].query("region == @region and crop == @crop and scenario == @ssp").iloc[0]
    cost = outputs["cost"].query("region == @region and crop == @crop and ssp == @ssp").iloc[0]
    theme, season = themes(outputs, region, crop, ssp), season_summary(outputs, region, crop, ssp)
    rules = []

    def add(rule, decision, text, evidence, **values):
        rules.append(dict(rule=rule, decision=decision, text=text, evidence=evidence, values=values))

    if theme[WARMTH] <= -0.01:
        add("variety_warmth", "Variety work", "Warmer, shorter seasons cut this crop's yield by about {effect} in the model. Include season length and heat tolerance in variety work for this crop.", MODEL, effect=(-theme[WARMTH], ".1%"))
    if season["maturity_days_earlier"] >= 5:
        add("calendar", "Sowing and harvest calendar", "The crop reaches maturity about {days} days earlier. Review the sowing guidance and harvest capacity dates before this becomes routine.", ASSUMED, days=(season["maturity_days_earlier"], ".0f"))
    if region == "FI_SW" and crop == "pea":
        add("pea_stagger", "Sowing and harvest calendar", "Pea sowing can be staggered by up to about a month so that fields don't all ripen together. Check that the same gap still spreads the harvest in warmer seasons.", EXPERT)
    if theme[WATER] >= 0.01:
        add("water_offset", "Risk planning", "Water measures add back about {effect} in the model, even though season rain falls or stays flat, because a shorter season loses less water overall. Keep drought plans in place rather than counting on it.", MODEL, effect=(theme[WATER], ".1%"))
    if crop == "potato" and season["wet_days"] - season["wet_days_today"] >= 2:
        add("disease", "Crop protection guidance", "Warm, wet days rise from {today} to {future} a year, which can favour blight. Review the disease guidance for potato.", ASSUMED, today=(season["wet_days_today"], ".0f"), future=(season["wet_days"], ".0f"))
    seen = outputs["bad_check"].query("region == @region and crop == @crop").iloc[0]
    if risk.p_bad_year - seen.p_bad_today >= 0.02:
        add("bad_years", "Contract planning", "The model's chance of a bad year rises from {today} to {future}. Bad seasons so far: {seen} of {seasons}, so use this to discuss contract area buffers, not to set them.", MODEL,
            today=(seen.p_bad_today, ".0%"), future=(risk.p_bad_year, ".0%"), seen=(round(seen.observed_bad * seen.seasons), "d"), seasons=(int(seen.seasons), "d"))
    if cost.added_vs_todays_climate_eur_yr >= 10000:
        add("replacement_cost", "Replacement buying", "Replacing shortfalls with imports could add about {cost} a year. Review the buying plan for this crop first.", MODEL, cost=(cost.added_vs_todays_climate_eur_yr, "eur"))
    if region == "SE_SKANE":
        i = outputs["irrigation"].query("region == @region and crop == @crop").iloc[0]
        top = outputs["irrigation_seasons"].sort_values("uplift_pct", ascending=False).head(2)
        add("irrigation", "Water planning", "On farms that switch practice, irrigated peas yield about {uplift} more, and the gap is largest in poor seasons such as {year1} ({gap1}) and {year2} ({gap2}). These can't be predicted, so water access has to be arranged beforehand, and its availability checked.", MEASURED,
            uplift=(i.within_farm_uplift_pct / 100, ".0%"), year1=(int(top.year.iloc[0]), "d"), gap1=(top.uplift_pct.iloc[0] / 100, "+.0%"), year2=(int(top.year.iloc[1]), "d"), gap2=(top.uplift_pct.iloc[1] / 100, "+.0%"))
    else:
        add("irrigation_gap", "Data to collect", "No Finnish farm switches between irrigating and not, so the data can't show what irrigation is worth here. If it's being considered, a small on-farm trial would answer it.", GAP)
    p = outputs["policy"].query("scenario == @story and year == 2050").iloc[0]
    use = outputs["inputs"].loc[(region, crop)]
    costs = {"below_2c": "By 2050 this scenario has fertiliser at {fertiliser}, diesel at {diesel} and carbon at {carbon} a tonne. This crop uses about {n} kg of nitrogen and {fuel} l of diesel per hectare, so include this in contract price talks.",
             "current_policies": "Policy adds little in this scenario: by 2050 fertiliser is at {fertiliser}, nearly all of it by 2027, with diesel at {diesel} and carbon at {carbon} a tonne. This crop uses about {n} kg of nitrogen and {fuel} l of diesel per hectare."}
    add("input_costs", "Costs and contract prices", costs[story], ILLUSTRATIVE,
        fertiliser=(p.n_fertiliser_price_index - 1, "+.0%"), diesel=(p.diesel_price_index - 1, "+.0%"), carbon=(float(p.carbon_price_eur_t), "eur"), n=(use.n_mineral_kg_ha, ".0f"), fuel=(use.diesel_l_ha, ".0f"))
    add("record_data", "Data to collect", "Sowing date and variety aren't recorded in the data, so we can't say which sowing date or variety does best. Adding both to the farm survey would make that possible.", GAP)
    return rules


def field_table(predictor, farm_id, crop):
    """One row per field of a farm: modelled yield today and in each story, soil exposure and crop plan."""
    fields = predictor.parcels[predictor.parcels.farm_id == farm_id].reset_index().assign(crop=crop)
    for s in SOILS:
        fields["soil_" + s] = (fields.soil_class_soilmap == s).astype(float)
    fields["irr"] = float(predictor.farm_irr.get((farm_id, crop), 0.0))
    d = _with_weather(fields, predictor.sets[predictor.sets.ssp.isin(["baseline", *STORIES.values()])], crop)
    d["y"] = np.exp(predictor.long_models[crop].predict_log(d, technology_year=TECH_YEAR))
    means = d.groupby(["parcel_id", "ssp"])[["y", "stress_sens"]].mean().unstack("ssp")
    out = fields.set_index("parcel_id")[["area_ha", "soil_class_soilmap", "drainage"]].copy()
    out["yield_today"] = means[("y", "baseline")]
    out["stress_today"] = means[("stress_sens", "baseline")]
    for story, ssp in STORIES.items():
        out["change_" + story] = means[("y", ssp)] / means[("y", "baseline")] - 1
    h = predictor.history[(predictor.history.farm_id == farm_id) & (predictor.history.crop == crop)]
    out["last_grown"] = h[h.status == "declared"].groupby("parcel_id").year.max()
    out["next_planned"] = h[h.status == "planned"].groupby("parcel_id").year.min()
    out["droughty_soil"] = out.soil_class_soilmap.isin(["sand", "fine_sand"])
    return out.sort_values("yield_today", ascending=False).reset_index()
