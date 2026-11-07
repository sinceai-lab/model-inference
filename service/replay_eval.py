"""Honest test of the in-season estimate: replay past seasons with later days hidden, on models that didn't train on that season.

Follows src/backtest.py row for row: farm x crop x year rows, area-weighted features, leave-one-season-out and forward tests, the
farm average as baseline. The only change is that the weather features come from weather known up to a date, then filled as in
live use. The normals also leave out the tested year. Run: python -m service.replay_eval
"""
import sys
import time
from datetime import date

import numpy as np
import pandas as pd

import service  # noqa: F401
from backtest import metrics, prep
from config import CROPS, DATA, MODEL_PARAMS, OUT, CACHE
from dataset import attach_features, parcels_with_cells
from features import FEATURES
from models import YieldModel, groups
from service.season import FIRST_DOY, LAST_DOY, assemble, crop_features, load_normals, read_history

# Each cut means: weather known up to and including this day. "none" is typical weather only, "full" the whole season.
CUTS = [("none", None), ("05-01", (5, 1)), ("05-15", (5, 15)), ("06-01", (6, 1)), ("06-15", (6, 15)), ("07-01", (7, 1)), ("07-15", (7, 15)), ("08-01", (8, 1)), ("08-15", (8, 15)), ("09-01", (9, 1)), ("full", (10, 27))]
FILLS = {"estimate": "expected", "estimate_plain_counts": "plain"}


def declared_rows():
    h = pd.read_csv(DATA / "03_farming/parcel_crop_history_and_plan.csv")
    p = parcels_with_cells()
    a = h[h.crop.isin(CROPS)].merge(p[["parcel_id", "area_ha", "soil_class_soilmap", "cell_id", "clay", "region"]], on="parcel_id")
    return a[a.status == "declared"]


def daily_weather(years, cells):
    w = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet", columns=["cell_id", "date", "tmean_c", "tmax_c", "precip_mm", "pet_mm"], filters=[("scenario", "==", "historical")])
    w["date"] = pd.to_datetime(w["date"])
    w["year"], w["doy"] = w.date.dt.year, w.date.dt.dayofyear
    w = w[w.year.isin(years) & w.cell_id.isin(cells) & w.doy.between(FIRST_DOY, LAST_DOY)]
    return {k: g.sort_values("doy").rename(columns=dict(tmean_c="tmean", tmax_c="tmax", precip_mm="precip", pet_mm="pet")) for k, g in w.groupby(["cell_id", "year"])}


def cut_features(rows, weather, normals, year, cut, counts):
    """Feature table for one season and cut, in the shape attach_features expects."""
    out = []
    limit = date(year, *cut).timetuple().tm_yday if cut else 0
    for cell, g in rows.drop_duplicates(["cell_id", "crop", "soil_class_soilmap"]).groupby("cell_id"):
        w = weather[(cell, year)]
        s = assemble(cell, year, w[w.doy <= limit].to_dict("records"), normals[cell])
        for crop, soil in zip(g.crop, g.soil_class_soilmap):
            out.append(dict(cell_id=cell, year=year, crop=crop, soil=soil, **crop_features(s, crop, soil, counts)))
    return pd.DataFrame(out)


def fit_all(t, years, forward):
    """Per test season: its held-out rows with the training-only irrigation share, and models and farm averages fitted without it."""
    fits = {}
    for y in years:
        mask = (t.year < y) if forward else (t.year != y)
        d = prep(t, mask=mask)
        tr, te = d[mask.to_numpy()], d[(d.year == y).to_numpy()]
        fits[y] = {}
        for crop, g in groups(tr).items():
            q = te[te.crop == crop]
            if q.empty or len(g) < 30:
                continue
            q = q[q.farm_id.isin(g.farm_id)]
            if q.empty:
                continue
            gt = g.assign(irr=g.irrigated.fillna(g.irr))
            a, sc = MODEL_PARAMS[crop]
            fits[y][crop] = (q, YieldModel(alpha=a, farm_scale=sc).fit(gt), gt.groupby("farm_id").yield_t_ha.mean())
    return fits


def season_errors(p):
    """Production error per region, crop and season."""
    agg = p.assign(a=p.yield_t_ha * p.area_ha, b=p.pred * p.area_ha).groupby(["region", "crop", "year"])[["a", "b"]].sum()
    return (agg.b - agg.a).abs() / agg.a


def score(p, cut, test, method, rows, base_errors=None):
    def add(scope, g, err):
        m = metrics(g)
        wins = float("nan") if base_errors is None else float((err < base_errors.reindex(err.index)).mean())
        rows.append(dict(test=test, known_until=cut, scope=scope, method=method, production_error=m["mape"], yield_error_nrmse=m["nrmse"], share_of_seasons_beating_baseline=round(wins, 3), region_crop_seasons=len(err), farm_seasons=len(g)))
    errors = season_errors(p)
    add("all", p, errors)
    for (region, crop), g in p.groupby(["region", "crop"]):
        add(f"{region}/{crop}", g, errors.loc[(region, crop)].to_frame("e").assign(region=region, crop=crop).set_index(["region", "crop"], append=True).reorder_levels(["region", "crop", "year"]).e)


def main():
    start = time.time()
    t = pd.read_parquet(CACHE / "training.parquet").reset_index(drop=True)
    a = declared_rows()
    keys = ["farm_id", "crop", "year"]
    all_years = sorted(t.year.unique())
    history = read_history()
    weather = daily_weather(all_years, set(a.cell_id))
    normals = {y: load_normals(exclude_year=y if y <= 2020 else None, weather=history) for y in all_years}
    print(f"weather loaded {time.time() - start:.0f}s", flush=True)
    table = {}
    for y in all_years:
        rows = a[a.year == y]
        for cut_name, cut in CUTS:
            for fill, counts in FILLS.items():
                f = cut_features(rows, weather, normals[y], y, cut, counts)
                table[(y, cut_name, fill)] = attach_features(rows, f, keys)[keys + FEATURES]
        print(y, f"{time.time() - start:.0f}s", flush=True)
    results = []
    for test, tested, forward in [("loyo", all_years, False), ("forward", [y for y in all_years if y >= 2022], True)]:
        fits = fit_all(t, tested, forward)
        known = {y: {c: q.drop(columns=FEATURES) for c, (q, _, _) in by.items()} for y, by in fits.items()}
        base = pd.concat([q.assign(pred=q.farm_id.map(fm)) for by in fits.values() for q, _, fm in by.values()], ignore_index=True)
        base_errors = season_errors(base)
        for cut_name, _ in CUTS:
            score(base, cut_name, test, "baseline_farm_average", results)
            for fill in FILLS:
                preds = []
                for y, by in fits.items():
                    for crop, (q, model, _) in by.items():
                        d = known[y][crop].merge(table[(y, cut_name, fill)], on=keys, how="left", validate="1:1")
                        assert d[FEATURES].notna().all().all() and len(d) == len(q)
                        preds.append(d.assign(pred=np.exp(model.predict_log(d))))
                score(pd.concat(preds, ignore_index=True), cut_name, test, fill, results, base_errors)
    out = pd.DataFrame(results)
    out.to_csv(OUT / "live_season_replay.csv", index=False)
    pd.set_option("display.width", 220)
    print(out[out.scope == "all"].pivot_table(index=["test", "known_until"], columns="method", values=["production_error", "yield_error_nrmse", "share_of_seasons_beating_baseline"], sort=False).round(3).to_string())


if __name__ == "__main__":
    sys.exit(main())
