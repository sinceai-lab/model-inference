"""Crop-stage weather features per cell x year x crop x soil, for observed and scenario weather.

weather_set: 'raw' is the supplied weather. 'delta' shifts 1991-2020 by the package's 2041-2060 monthly
signals, which gives 30 extra future-climate years because only one realisation per SSP is supplied.
"""
import hashlib

import numpy as np
import pandas as pd

from config import CACHE, CROP, CROPS, DATA, SOILS, AWC_MM

FEATURES = ["sow_doy", "mat_doy", "gdd_gap", "stress_early", "stress_sens", "stress_late", "hot_sens", "hot_season",
            "t_sens", "rain_postsow", "wet_postsow", "rain_preharv", "blight_days", "may_t", "rain_season", "pet_season"]


def season_features(doy, t, tx, p, pet, crop, soil):
    c = CROP[crop]
    gdd_day = np.maximum(t - 5.0, 0.0)
    roll = np.convolve(t, np.ones(5) / 5, mode="valid")
    ok = np.where((roll >= c["sow_t"]) & (doy[:len(roll)] >= 100))[0]
    s = int(ok[0]) if len(ok) else int(np.searchsorted(doy, 150))
    end = int(np.searchsorted(doy, c["cutoff"]))
    gdd = np.cumsum(gdd_day[s:end + 1]) if end >= s else np.zeros(1)
    i0, i1 = np.searchsorted(gdd, c["s0"]), np.searchsorted(gdd, c["s1"])
    m = np.searchsorted(gdd, c["mat"])
    matured = m < len(gdd)
    m = min(m, len(gdd) - 1)
    # Soil bucket, full on 1 April.
    awc, sw = AWC_MM[soil], AWC_MM[soil]
    apr1 = int(np.searchsorted(doy, 91))
    stress = np.ones(len(t))
    for d in range(apr1, min(s + m + 1, len(t))):
        sw = min(awc, sw + p[d])
        f = min(1.0, sw / (0.5 * awc))
        aet = pet[d] * f
        sw = max(0.0, sw - aet)
        stress[d] = 1.0 - f
    a, b, h = s + min(i0, m), s + min(i1, m), s + m
    win = lambda x, lo, hi: x[lo:hi + 1] if hi >= lo else x[lo:lo + 1]
    rain_post = p[s:s + 14]
    jul_aug = (doy >= 182) & (doy <= 243)
    return (doy[s], doy[h], 0.0 if matured else (c["mat"] - gdd[-1]) / c["mat"],
            win(stress, s, a).mean(), win(stress, a, b).mean(), win(stress, b, h).mean(),
            float((win(tx, a, b) >= 27).sum()), float((win(tx, s, h) >= 27).sum()), win(t, a, b).mean(),
            rain_post.sum(), float((rain_post >= 1).sum()), p[max(h - 10, 0):h + 1].sum(),
            float(((t >= 15) & (p >= 1) & jul_aug).sum()), t[(doy >= 121) & (doy <= 151)].mean(),
            win(p, s, h).sum(), win(pet, s, h).sum())


def _rows(w, cell, set_name, scenario, crops):
    rows = []
    for year, g in w.groupby("year"):
        arr = {k: g[k].to_numpy() for k in ["doy", "tmean_c", "tmax_c", "precip_mm", "pet_mm"]}
        for crop in crops:
            for soil in SOILS:
                v = season_features(arr["doy"], arr["tmean_c"], arr["tmax_c"], arr["precip_mm"], arr["pet_mm"], crop, soil)
                rows.append((cell, set_name, scenario, int(year), crop, soil) + tuple(float(x) for x in v))
    return rows


def build(force=False):
    # The name carries the crop and soil settings, so changing them can't reuse stale features.
    path = CACHE / f"weather_features_{hashlib.md5(repr((CROP, AWC_MM)).encode()).hexdigest()[:8]}.parquet"
    if path.exists() and not force:
        return pd.read_parquet(path)
    CACHE.mkdir(exist_ok=True)
    cells = pd.read_csv(DATA / "01_master/climate_grid_cells.csv")
    sig = pd.read_csv(DATA / "04_climate/climate_change_signals.csv")
    w = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet",
                        columns=["cell_id", "date", "tmean_c", "tmax_c", "precip_mm", "pet_mm", "scenario"])
    w["date"] = pd.to_datetime(w["date"])
    w["year"], w["doy"], w["month"] = w.date.dt.year, w.date.dt.dayofyear, w.date.dt.month
    keep = (w.scenario == "historical") | ((w.scenario == "ssp245") & w.year.between(2027, 2031)) | (w.scenario.isin(["ssp126", "ssp245", "ssp585"]) & w.year.between(2041, 2060))
    w = w[keep & w.doy.between(60, 300)]
    rows = []
    for cell, g in w.groupby("cell_id"):
        crops = ["pea"] if cell.startswith("GS") else CROPS
        for scenario, q in g.groupby("scenario"):
            rows += _rows(q, cell, "raw", scenario, crops)
        base = g[(g.scenario == "historical") & g.year.between(1991, 2020)]
        for scenario, s in sig.groupby("scenario"):
            d = base.merge(s[["month", "delta_tmean_c", "precip_factor"]], on="month")
            t0 = d.tmean_c.to_numpy()
            d["tmean_c"] = t0 + d.delta_tmean_c
            d["tmax_c"] = d.tmax_c + d.delta_tmean_c
            d["precip_mm"] = d.precip_mm * d.precip_factor
            d["pet_mm"] = d.pet_mm * (d.tmean_c + 17.8).clip(lower=1) / np.maximum(t0 + 17.8, 1)  # Hargreaves temperature term
            rows += _rows(d.sort_values("date"), cell, "delta", scenario, crops)
    f = pd.DataFrame(rows, columns=["cell_id", "weather_set", "scenario", "year", "crop", "soil"] + FEATURES)
    f.to_parquet(path, index=False)
    return f


if __name__ == "__main__":
    f = build(force=True)
    print(f.shape)
    print(f[(f.weather_set == "raw") & (f.scenario == "historical")].groupby("crop")[FEATURES].mean().round(2).T.to_string())
