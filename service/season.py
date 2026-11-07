"""Turn a partly observed season into a complete one, and compute the model's weather features from it. No web code.

The features are defined on the whole-season daily arrays in features.season_features. Days without a reading are filled:
  - after the last reading: the cell's 1991-2020 day-of-year average (normals);
  - in a gap of up to gap_interp_days between readings: temperature and PET interpolated, rain from the normals;
  - in longer gaps and before the first reading: the normals.

Averaging across years smooths the daily series, so threshold counts computed on it are wrong: the average July day has
over 1 mm of rain and 15 C, so every July-August day would count as warm and wet. That gives about 50 blight days against
16 in a real year, far outside the training range. So with counts="expected" each filled day adds its historical chance of
passing the threshold instead. Everything else uses the averages unchanged. outputs/live_season_replay.csv compares the two.
"""
from collections import namedtuple
from datetime import date

import numpy as np
import pandas as pd

from config import CROP, DATA
from features import FEATURES, season_features

FIRST_DOY, LAST_DOY = 60, 300  # The window the cached features and the models were built on.
DOYS = np.arange(FIRST_DOY, LAST_DOY + 1)
N_DAYS = len(DOYS)
VARS = ["tmean", "tmax", "precip", "pet"]
Season = namedtuple("Season", "cell_id year doy t tx p pet p_hot p_wet p_blight known_t known_tx known_p observed partial gap future last_doy")


def in_window(doy):
    return FIRST_DOY <= doy <= LAST_DOY


def load_normals(exclude_year=None, weather=None):
    """Per cell: day-of-year averages and threshold chances, 1991-2020. exclude_year serves the honest replay test."""
    w = weather if weather is not None else read_history()
    w = w[w.year != exclude_year] if exclude_year else w
    w = w.assign(hot=w.tmax_c >= 27, wet=w.precip_mm >= 1, blight=(w.tmean_c >= 15) & (w.precip_mm >= 1))
    g = w.groupby(["cell_id", "doy"])[["tmean_c", "tmax_c", "precip_mm", "pet_mm", "hot", "wet", "blight"]].mean()
    return {cell: {k: x[k].to_numpy() for k in x.columns} for cell, x in g.groupby(level="cell_id")}


def read_history():
    w = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet", columns=["cell_id", "date", "tmean_c", "tmax_c", "precip_mm", "pet_mm"],
                        filters=[("scenario", "==", "historical"), ("date", "<", pd.Timestamp("2021-01-01"))])
    w["date"] = pd.to_datetime(w["date"])
    w["year"], w["doy"] = w.date.dt.year, w.date.dt.dayofyear
    return w[w.doy.between(FIRST_DOY, LAST_DOY)]


def hargreaves_pet(tmean, tmax, tmin, lat, doy):
    """FAO-56 Hargreaves in mm/day. Reproduces the package's pet_mm to about 0.006 mm/day on 1991-2026."""
    phi, angle = np.radians(lat), 2 * np.pi * doy / 365
    dr, decl = 1 + 0.033 * np.cos(angle), 0.409 * np.sin(angle - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(decl), -1, 1))
    ra = 24 * 60 / np.pi * 0.082 * dr * (ws * np.sin(phi) * np.sin(decl) + np.cos(phi) * np.cos(decl) * np.sin(ws))
    return float(max(0.0023 * ra * 0.408 * (tmean + 17.8) * np.sqrt(max(tmax - tmin, 0.0)), 0.0))


def _fill(values, normal, max_gap):
    out = np.where(np.isnan(values), normal, values)
    known = np.where(~np.isnan(values))[0]
    if max_gap:
        for a, b in zip(known[:-1], known[1:]):
            if 1 < b - a <= max_gap + 1:
                out[a + 1:b] = np.interp(np.arange(a + 1, b), [a, b], [values[a], values[b]])
    return out


def assemble(cell_id, year, rows, normals, gap_interp_days=3):
    """rows: readings as dicts holding doy and any of VARS, inside the window. Missing values become None or NaN."""
    arr = {v: np.full(N_DAYS, np.nan) for v in VARS}
    for r in rows:
        for v in VARS:
            x = r.get(v)
            if x is not None:
                arr[v][r["doy"] - FIRST_DOY] = x
    read = np.array([False] * N_DAYS)
    read[[r["doy"] - FIRST_DOY for r in rows]] = True
    complete = read & ~np.isnan(np.column_stack([arr[v] for v in VARS])).any(axis=1)
    last = int(np.where(read)[0].max()) if read.any() else -1
    filled = ~read
    return Season(cell_id, year, DOYS, _fill(arr["tmean"], normals["tmean_c"], gap_interp_days), _fill(arr["tmax"], normals["tmax_c"], gap_interp_days), _fill(arr["precip"], normals["precip_mm"], 0),
                  _fill(arr["pet"], normals["pet_mm"], gap_interp_days), normals["hot"], normals["wet"], normals["blight"], ~np.isnan(arr["tmean"]), ~np.isnan(arr["tmax"]), ~np.isnan(arr["precip"]),
                  read, read & ~complete, filled & (np.arange(N_DAYS) < last), filled & (np.arange(N_DAYS) > last), int(DOYS[last]) if last >= 0 else None)


def day_counts(s):
    return dict(observed_days=int(s.observed.sum()), partial_days=int(s.partial.sum()), filled_days=int(s.gap.sum() + s.future.sum()), filled_gap_days=int(s.gap.sum()), filled_future_days=int(s.future.sum()),
                total_days=N_DAYS, last_observed_doy=s.last_doy)


def _stages(s, crop, sow_doy, mat_doy):
    """Index of sowing, the sensitive stage's start and end, and maturity: the same arithmetic as season_features."""
    c = CROP[crop]
    start, mat = int(sow_doy - FIRST_DOY), int(mat_doy - FIRST_DOY)
    end = int(np.searchsorted(s.doy, c["cutoff"]))
    gdd = np.cumsum(np.maximum(s.t - 5.0, 0.0)[start:end + 1]) if end >= start else np.zeros(1)
    return start, min(start + int(np.searchsorted(gdd, c["s0"])), mat), min(start + int(np.searchsorted(gdd, c["s1"])), mat), mat


def crop_features(s, crop, soil, counts="expected"):
    """The 16 weather features for this crop and soil."""
    f = dict(zip(FEATURES, (float(x) for x in season_features(s.doy, s.t, s.tx, s.p, s.pet, crop, soil))))
    if counts == "plain" or (not s.gap.any() and not s.future.any() and not s.partial.any()):
        return f
    a, i0, i1, h = _stages(s, crop, f["sow_doy"], f["mat_doy"])
    hot = np.where(s.known_tx, s.tx >= 27, s.p_hot)
    wet = np.where(s.known_p, s.p >= 1, s.p_wet)
    blight = np.where(s.known_t & s.known_p, (s.t >= 15) & (s.p >= 1), s.p_blight)
    jul_aug = (s.doy >= 182) & (s.doy <= 243)
    f.update(hot_sens=float(hot[i0:i1 + 1].sum()), hot_season=float(hot[a:h + 1].sum()), wet_postsow=float(wet[a:a + 14].sum()), blight_days=float(blight[jul_aug].sum()))
    return f


def filled_to_maturity(s, mat_doy):
    """Filled days up to this crop's estimated maturity. Zero means later weather can't change the estimate."""
    i = int(mat_doy - FIRST_DOY) + 1
    return int(s.gap[:i].sum() + s.future[:i].sum())


def doy_of(day):
    return day.timetuple().tm_yday if isinstance(day, date) else date.fromisoformat(day).timetuple().tm_yday
