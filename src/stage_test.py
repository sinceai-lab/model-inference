"""Do held-out seasons support changing an assumed crop-stage value? Writes outputs/stage_parameter_test.csv.

For each held-out season the value is chosen using other seasons only (earlier seasons in the forward test),
so a good result can't come from picking the value on the season being scored.
"""
import numpy as np
import pandas as pd

from backtest import evaluate, metrics
from config import DATA, MODEL_PARAMS, OUT, SOILS
from dataset import attach_features, yields
from features import CROP as FEATURE_CROP, FEATURES, season_features
from models import YieldModel

KEYS = ["farm_id", "crop", "year"]
# crop -> stage values tried, with the value used before the test first.
TESTS = {"pea": [dict(mat=m) for m in (750, 700, 790, 825, 850, 860, 900, 950)],
         "turnip_rape": [dict(s0=round(350 * s), s1=round(600 * s)) for s in (1, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5)]}


def weather():
    w = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet", columns=["cell_id", "date", "tmean_c", "tmax_c", "precip_mm", "pet_mm"], filters=[("scenario", "==", "historical")])
    w["date"] = pd.to_datetime(w["date"])
    w["year"], w["doy"] = w.date.dt.year, w.date.dt.dayofyear
    w = w[w.year.between(2012, 2026) & w.doy.between(60, 300)]
    return {k: {c: g[c].to_numpy() for c in ["doy", "tmean_c", "tmax_c", "precip_mm", "pet_mm"]} for k, g in w.groupby(["cell_id", "year"])}


def table(crop, values, y, declared, days):
    saved = FEATURE_CROP[crop]
    FEATURE_CROP[crop] = {**saved, **values}
    rows = [(cell, year, crop, soil) + tuple(float(v) for v in season_features(g["doy"], g["tmean_c"], g["tmax_c"], g["precip_mm"], g["pet_mm"], crop, soil))
            for (cell, year), g in days.items() if crop == "pea" or cell.startswith("GF") for soil in SOILS]
    FEATURE_CROP[crop] = saved
    f = pd.DataFrame(rows, columns=["cell_id", "year", "crop", "soil"] + FEATURES)
    t = y[y.crop == crop].merge(attach_features(declared[declared.crop == crop], f, KEYS), on=KEYS)
    return t.assign(region=np.where(t.farm_id.str.startswith("S"), "SE_SKANE", "FI_SW"))


def main():
    y, a = yields()
    declared, days = a[a.status == "declared"], weather()
    out = []
    for crop, tries in TESTS.items():
        tables = [table(crop, v, y, declared, days) for v in tries]
        make = lambda _, c=crop: YieldModel(alpha=MODEL_PARAMS[c][0], farm_scale=MODEL_PARAMS[c][1])

        def inner_error(t):
            m = metrics(evaluate(t.reset_index(drop=True), sorted(t.year.unique()), make))
            return m["mape"] + m["nrmse"]

        years = sorted(tables[0].year.unique())
        for test, outer, forward in [("loyo", years, False), ("forward", [v for v in years if v >= 2022], True)]:
            old, new, picks = [], [], []
            for year in outer:
                best = int(np.argmin([inner_error(t[t.year < year] if forward else t[t.year != year]) for t in tables]))
                picks.append(best)
                old.append(evaluate(tables[0].reset_index(drop=True), [year], make, forward=forward))
                new.append(evaluate(tables[best].reset_index(drop=True), [year], make, forward=forward))
            for region in tables[0].region.unique():
                for arm, p in (("old value", old), ("chosen on other seasons", new)):
                    p = pd.concat(p)
                    m = metrics(p[p.region == region])
                    out.append(dict(crop=crop, region=region, test=test, arm=arm, production_error=m["mape"], yield_error=m["nrmse"]))
            print(crop, test, "picked", [tries[i] for i in picks])
    out = pd.DataFrame(out)
    out.to_csv(OUT / "stage_parameter_test.csv", index=False)
    print(out.to_string())


if __name__ == "__main__":
    main()
