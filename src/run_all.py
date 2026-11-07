"""End to end: fit final models, write the C1 and C2 submissions, the euro risk tables and diagnostics."""
import pickle
import sys

import numpy as np
import pandas as pd

from backtest import evaluate, metrics, prep
from config import CACHE, CROPS, DATA, MODEL_PARAMS, OUT, PACKAGE, SOILS, TASKS
from dataset import parcels_with_cells, training
from features import FEATURES, build
from models import YieldModel

SEED = 20261107
BAD = 0.8
TECH_YEAR = 2025


def make(crop, se_interactions=True):
    a, s = MODEL_PARAMS[crop]
    return YieldModel(alpha=a, farm_scale=s, se_interactions=se_interactions)


def add_parcel_columns(d):
    for s in SOILS:
        d["soil_" + s] = (d.soil_class_soilmap == s).astype(float)
    d["clay"] = d.clay.fillna(d.clay.median())
    return d


def main():
    OUT.mkdir(exist_ok=True)
    t = training().reset_index(drop=True)
    f = build()
    parcels = parcels_with_cells()
    prices = pd.read_csv(DATA / "05_scenarios/contract_prices_and_replacement_premiums.csv")
    price25 = prices[prices.year == 2025].set_index("item")

    # Out-of-sample seasons with the final settings.
    years = sorted(t.year.unique())
    oof = pd.concat([evaluate(t[t.crop == c].reset_index(drop=True), years, lambda _: make(c)) for c in CROPS], ignore_index=True)
    forward = pd.concat([evaluate(t[t.crop == c].reset_index(drop=True), [y for y in years if y >= 2022], lambda _: make(c), forward=True) for c in CROPS], ignore_index=True)
    base = evaluate(t, years, lambda _: None)
    base_forward = evaluate(t, [y for y in years if y >= 2022], lambda _: None, forward=True)
    diag = {"farm_mean_loyo": metrics(base), "farm_mean_forward_2022_2026": metrics(base_forward), "final_loyo": metrics(oof), "final_forward_2022_2026": metrics(forward)}
    keys = ["farm_id", "crop", "region", "year", "area_ha", "yield_t_ha", "source"]
    held_out = pd.concat([
        oof[keys + ["pred"]].rename(columns={"pred": "pred_model"}).merge(base[keys[:4] + ["pred"]].rename(columns={"pred": "pred_baseline"}), on=keys[:4]).assign(test="loyo"),
        forward[keys + ["pred"]].rename(columns={"pred": "pred_model"}).merge(base_forward[keys[:4] + ["pred"]].rename(columns={"pred": "pred_baseline"}), on=keys[:4]).assign(test="forward"),
    ])
    held_out.round(4).to_csv(OUT / "backtest_predictions.csv", index=False)
    pd.DataFrame({k: {m: v[m] for m in ("score", "mape", "nrmse")} for k, v in diag.items()}).T.to_csv(OUT / "backtest_summary.csv")
    print(pd.DataFrame({k: {m: v[m] for m in ("score", "mape", "nrmse")} for k, v in diag.items()}).T.to_string())
    print("LOYO MAPE by region and crop:", diag["final_loyo"]["by_mape"])

    # Unexplained season-level error, used for bad-year probabilities and euro risk.
    agg = oof.assign(p_o=oof.yield_t_ha * oof.area_ha, p_p=oof.pred * oof.area_ha).groupby(["region", "crop", "year"])[["p_o", "p_p"]].sum()
    oof_area = oof.groupby(["region", "crop", "year"]).area_ha.sum()
    resid = np.log(agg.p_o / agg.p_p)
    sigma = resid.groupby(level=["region", "crop"]).std()

    final_data = prep(t)
    final_data = final_data.assign(irr=final_data.irrigated.fillna(final_data.irr))
    models = {c: make(c).fit(final_data[final_data.crop == c]) for c in CROPS}
    farm_irr = final_data.groupby(["farm_id", "crop"]).irr.mean()

    pd.DataFrame({c: m.coefficients() for c, m in models.items()}).round(4).to_csv(OUT / "model_coefficients.csv")

    with open(CACHE / "models.pkl", "wb") as fh:
        pickle.dump(dict(models=models, farm_irr=farm_irr, farm_mean=final_data.groupby(["farm_id", "crop"]).yield_t_ha.mean()), fh)

    # ---------- C1
    tpl = pd.read_csv(TASKS / "templates/C1_yields_2027_2031_submission.csv")
    raw = f[f.weather_set == "raw"].drop(columns=["weather_set"])
    q = tpl.merge(parcels[["parcel_id", "cell_id", "soil_class_soilmap", "clay"]], on="parcel_id", how="left")
    q = q.merge(raw[raw.scenario == "ssp245"].drop(columns="scenario").rename(columns={"soil": "soil_class_soilmap"}), on=["cell_id", "soil_class_soilmap", "crop", "year"], how="left")
    q = add_parcel_columns(q)
    q["irr"] = [farm_irr.get((a, b), 0.0) for a, b in zip(q.farm_id, q.crop)]
    q["pred"] = np.nan
    for c, m in models.items():
        i = q.crop == c
        q.loc[i, "pred"] = np.exp(m.predict_log(q[i]))
    assert q.pred.notna().all() and len(q) == len(tpl)
    sub = tpl.copy()
    sub["yield_t_ha_pred"] = q.pred.round(3).to_numpy()
    sub.to_csv(OUT / "C1_yields_2027_2031_submission.csv", index=False)
    print(sub.assign(prod=sub.area_ha * sub.yield_t_ha_pred).groupby(["region", "crop", "year"]).apply(lambda g: g["prod"].sum() / g.area_ha.sum(), include_groups=False).unstack("year").round(2).to_string())

    # Forecasts next to the package's reference baseline (farm historical mean, no weather).
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PACKAGE / "tools"))
    from ccn_tools.baselines import c1_climatology
    ref = c1_climatology(dict(farm_survey=pd.read_csv(DATA / "03_farming/farm_survey_fi.csv")), tpl)
    fc = sub.assign(ref=ref.yield_t_ha_pred.to_numpy())
    fc = fc.assign(prod_m=fc.yield_t_ha_pred * fc.area_ha, prod_r=fc.ref * fc.area_ha).groupby(["region", "crop", "year"])[["prod_m", "prod_r", "area_ha"]].sum()
    pd.DataFrame(dict(model_t_ha=fc.prod_m / fc.area_ha, package_baseline_t_ha=fc.prod_r / fc.area_ha)).round(3).reset_index().to_csv(OUT / "C1_forecast_comparison.csv", index=False)

    # ---------- C2: 2025 contract-parcel mix, 2025 technology, current irrigation
    ch = pd.read_csv(DATA / "03_farming/parcel_crop_history_and_plan.csv")
    mix = ch[(ch.year == 2025) & ch.crop.isin(CROPS)].merge(parcels[["parcel_id", "area_ha", "cell_id", "soil_class_soilmap", "clay", "region"]], on="parcel_id")
    mix = add_parcel_columns(mix.drop(columns="year"))
    mix["irr"] = [farm_irr.get((a, b), 0.0) for a, b in zip(mix.farm_id, mix.crop)]
    sets = pd.concat([
        f[(f.weather_set == "raw") & (f.scenario == "historical") & f.year.between(1991, 2020)].assign(run="baseline", ssp="baseline"),
        f[(f.weather_set == "raw") & f.scenario.isin(["ssp126", "ssp245", "ssp585"]) & f.year.between(2041, 2060)].assign(run="raw", ssp=lambda d: d.scenario),
        f[f.weather_set == "delta"].assign(run="delta", ssp=lambda d: d.scenario),
    ]).rename(columns={"soil": "soil_class_soilmap"})

    def annual(model_by_crop, irr_override=None):
        out = []
        for c, m in model_by_crop.items():
            d = mix[mix.crop == c].merge(sets[sets.crop == c], on=["cell_id", "soil_class_soilmap", "crop"])
            if irr_override is not None:
                d["irr"] = irr_override
            d["y"] = np.exp(m.predict_log(d, technology_year=TECH_YEAR))
            d["prod"] = d.y * d.area_ha
            g = d.groupby(["region", "crop", "run", "ssp", "year"]).agg(prod=("prod", "sum"), area=("area_ha", "sum")).reset_index()
            g["y"] = g["prod"] / g.area
            out.append(g)
        return pd.concat(out, ignore_index=True)

    def risk_table(a, sig):
        rows = []
        for (reg, crop), g in a.groupby(["region", "crop"]):
            b = g[g.run == "baseline"].y.mean()
            s = sig.get((reg, crop), 0.0)
            for ssp, h in g[g.run != "baseline"].groupby("ssp"):
                r = h.y / b
                pb = pd.Series(np.where(s > 0, _phi((np.log(BAD) - np.log(r)) / max(s, 1e-6)), (r < BAD).astype(float)))
                rows.append(dict(region=reg, crop=crop, scenario=ssp, period="2041-2060", mean_yield_change_pct=100 * (r.mean() - 1), p_bad_year=pb.mean(),
                                 change_raw_pct=100 * (h[h.run == "raw"].y.mean() / b - 1), change_delta_pct=100 * (h[h.run == "delta"].y.mean() / b - 1)))
        return pd.DataFrame(rows)

    # Long-range work shares one weather response across regions: 9 Swedish seasons cannot support Sweden-only effects.
    long_models = {c: make(c, se_interactions=False).fit(final_data[final_data.crop == c]) for c in CROPS}
    a = annual(long_models)
    risk = risk_table(a, sigma)
    sens = risk_table(annual({"pea": models["pea"]}), sigma)[["region", "crop", "scenario", "mean_yield_change_pct"]].rename(columns={"mean_yield_change_pct": "change_with_se_specific_response"})
    risk = risk.merge(sens, on=["region", "crop", "scenario"], how="left")

    # Uncertainty: refit leaving out one season at a time.
    jack = []
    for y in years:
        data = final_data[final_data.year != y]
        jm = {c: make(c, se_interactions=False).fit(data[data.crop == c]) for c in CROPS}
        jack.append(risk_table(annual(jm), sigma)[["region", "crop", "scenario", "mean_yield_change_pct"]].assign(left_out=y))
    jack = pd.concat(jack)
    band = jack.groupby(["region", "crop", "scenario"]).mean_yield_change_pct.agg(change_min="min", change_max="max").reset_index()
    risk = risk.merge(band, on=["region", "crop", "scenario"])

    tpl2 = pd.read_csv(TASKS / "templates/C2_climate_yield_risk_submission.csv")[["region", "crop", "scenario", "period"]]
    c2 = tpl2.merge(risk, on=["region", "crop", "scenario", "period"], how="left")
    assert c2.mean_yield_change_pct.notna().all() and len(c2) == 18
    c2[["region", "crop", "scenario", "period"]].assign(mean_yield_change_pct=c2.mean_yield_change_pct.round(2), p_bad_year=c2.p_bad_year.round(3)).to_csv(OUT / "C2_climate_yield_risk_submission.csv", index=False)
    c2.round(3).to_csv(OUT / "C2_detail_with_uncertainty.csv", index=False)
    pd.set_option("display.width", 200)
    print(c2.drop(columns="period").round(2).to_string())

    # Check the bad-year method against what actually happened.
    chk = []
    for (reg, crop), g in agg.groupby(level=["region", "crop"]):
        area = oof_area.loc[(reg, crop)]
        y_o = (g.p_o.droplevel(["region", "crop"]) / area)
        y_p = (g.p_p.droplevel(["region", "crop"]) / area)
        y_o, y_p = y_o / y_o.mean(), y_p / y_p.mean()
        s = sigma[(reg, crop)]
        chk.append(dict(region=reg, crop=crop, seasons=len(g), observed_bad=float((y_o < BAD).mean()), modelled_bad=float(_phi((np.log(BAD) - np.log(y_p)) / s).mean()), season_error_sigma=round(s, 3)))
    chk = pd.DataFrame(chk).round(3)
    chk.to_csv(OUT / "C2_bad_year_check.csv", index=False)
    print(chk.to_string())

    # ---------- C3: euro risk = shortfall x contract price x replacement premium
    def euro(a_):
        rng = np.random.default_rng(SEED)  # same draws per call, so scenario differences are not sampling noise
        rows = []
        for (reg, crop), g in a_.groupby(["region", "crop"]):
            item = "pea_SE" if reg == "SE_SKANE" else crop
            price, prem = price25.loc[item, "contract_price_eur_t"], price25.loc[item, "replacement_import_premium_frac"]
            area = g.area.iloc[0]
            base_y = g[g.run == "baseline"].y.mean()
            s = sigma.get((reg, crop), 0.0)
            for ssp, h in g.groupby("ssp"):
                noise = np.exp(rng.normal(0, s, (5000, len(h))) - s ** 2 / 2)
                short_t = np.maximum(0, base_y - h.y.to_numpy() * noise) * area
                cost = short_t * price * prem
                rows.append(dict(region=reg, crop=crop, ssp=ssp, area_ha=round(area), price_eur_t=price, premium=prem, baseline_t=round(base_y * area), mean_shortfall_t=short_t.mean(), expected_cost_eur_yr=cost.mean(), bad_year_p90_cost_eur=np.quantile(cost.ravel(), 0.9)))
        return pd.DataFrame(rows)

    e = euro(a)
    bl = e[e.ssp == "baseline"].set_index(["region", "crop"]).expected_cost_eur_yr
    e["added_vs_todays_climate_eur_yr"] = e.expected_cost_eur_yr - [bl[(r, c)] for r, c in zip(e.region, e.crop)]
    money = ["baseline_t", "mean_shortfall_t", "expected_cost_eur_yr", "bad_year_p90_cost_eur", "added_vs_todays_climate_eur_yr"]
    e[money] = e[money].round(0)
    e.to_csv(OUT / "C3_euro_risk.csv", index=False)
    tot = e.groupby(["region", "ssp"])[["mean_shortfall_t", "expected_cost_eur_yr", "added_vs_todays_climate_eur_yr"]].sum().round(0)
    print(e.to_string())
    print(tot.to_string())

    # Adaptation: irrigation can only be measured where farms switch, which is Swedish peas.
    obs = t[t.source.isin(["survey", "foodhills"])].assign(ly=lambda d: np.log(d.yield_t_ha))
    obs["ly_w"] = obs.ly - obs.groupby(["farm_id", "crop"]).ly.transform("mean")
    obs["ly_w"] = obs.ly_w - obs.groupby(["region", "crop", "year"]).ly_w.transform("mean")
    kinds = obs.groupby(["region", "crop", "farm_id"]).irrigated.nunique().gt(1).groupby(level=["region", "crop"]).agg(["sum", "size"]).rename(columns={"sum": "farms_that_switch", "size": "farms"})
    crude = obs.groupby(["region", "crop", "irrigated"]).yield_t_ha.mean().unstack().rename(columns={0.0: "mean_yield_rainfed", 1.0: "mean_yield_irrigated"})
    irr = kinds.join(crude)
    se = obs[(obs.region == "SE_SKANE") & (obs.groupby("farm_id").irrigated.transform("nunique") > 1)]
    gap = se.groupby(["year", "irrigated"]).ly_w.mean().unstack()
    gap_y = (gap[1.0] - gap[0.0])
    se_means = se.groupby("year").yield_t_ha.mean().rename("season_mean_yield")
    gap_t = pd.concat([gap_y.rename("irrigated_uplift_log"), se_means], axis=1)
    gap_t["uplift_pct"] = 100 * (np.exp(gap_t.irrigated_uplift_log) - 1)
    gap_t.round(3).to_csv(OUT / "C3_irrigation_se_within_farm.csv")
    irr["within_farm_uplift_pct"] = np.nan
    irr.loc[("SE_SKANE", "pea"), "within_farm_uplift_pct"] = 100 * (np.exp(se[se.irrigated == 1].ly_w.mean() - se[se.irrigated == 0].ly_w.mean()) - 1)
    irr["evidence"] = np.where(irr.farms_that_switch > 0, "within-farm comparison", "not measurable: no farm switches; between-farm gap is confounded")
    irr.round(3).to_csv(OUT / "C3_irrigation_evidence.csv")
    print(irr.round(3).to_string())
    print(gap_t.round(3).to_string())
    print("Corr season mean yield vs uplift:", round(gap_t.season_mean_yield.corr(gap_t.uplift_pct), 3))

    # Are future scenario years as extreme as history? May-July rainfall and water stress.
    w = pd.read_csv(DATA / "04_climate/weather_monthly_1991_2060.csv")
    cells = pd.read_csv(DATA / "01_master/climate_grid_cells.csv")[["cell_id", "region"]]
    mj = w[w.month.isin([5, 6, 7])].merge(cells, on="cell_id").groupby(["region", "scenario", "year", "cell_id"]).precip_mm.sum().groupby(level=["region", "scenario", "year"]).mean().reset_index()
    ext = []
    for (reg, sc), g in mj.groupby(["region", "scenario"]):
        for lo, hi in ([(1991, 2020), (2012, 2026)] if sc == "historical" else [(2027, 2040), (2041, 2060)]):
            q = g[g.year.between(lo, hi)].precip_mm
            ext.append(dict(region=reg, scenario=sc, period=f"{lo}-{hi}", mean_mm=q.mean(), sd_mm=q.std(), cv=q.std() / q.mean(), min_mm=q.min()))
    ext = pd.DataFrame(ext).round(2)
    ext.to_csv(OUT / "climate_extremes_check.csv", index=False)
    print(ext.to_string())

    # Two-region hedge for peas, observed seasons.
    pea = t[t.crop == "pea"].assign(prod=lambda d: d.yield_t_ha * d.area_ha).groupby(["year", "region"]).agg(prod=("prod", "sum"), area=("area_ha", "sum"))
    y = (pea["prod"] / pea.area).unstack().dropna()
    w = pea.area.unstack().loc[y.index].mean()
    w = w / w.sum()
    both = y["FI_SW"] * w["FI_SW"] + y["SE_SKANE"] * w["SE_SKANE"]
    hedge = dict(seasons=len(y), correlation=y["FI_SW"].corr(y["SE_SKANE"]), cv_fi=y["FI_SW"].std() / y["FI_SW"].mean(), cv_se=y["SE_SKANE"].std() / y["SE_SKANE"].mean(), cv_combined=both.std() / both.mean(),
                 worst_vs_mean_fi=y["FI_SW"].min() / y["FI_SW"].mean(), worst_vs_mean_se=y["SE_SKANE"].min() / y["SE_SKANE"].mean(), worst_vs_mean_combined=both.min() / both.mean())
    pd.Series(hedge).round(3).to_csv(OUT / "C3_pea_hedge.csv", header=["value"])
    print(y.round(2).T.to_string())
    print(pd.Series(hedge).round(3).to_string())


def _phi(x):
    from scipy.stats import norm
    return norm.cdf(x)


if __name__ == "__main__":
    main()
