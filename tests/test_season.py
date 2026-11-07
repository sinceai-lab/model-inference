import numpy as np
import pandas as pd
import pytest

from config import DATA
from features import FEATURES, build, season_features
from service.season import DOYS, N_DAYS, _stages, assemble, crop_features, day_counts, read_history

CELL, YEAR = "GF0203", 2020


@pytest.fixture(scope="module")
def season_rows():
    w = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet", filters=[("cell_id", "==", CELL), ("scenario", "==", "historical")])
    w["date"] = pd.to_datetime(w.date)
    w = w[(w.date.dt.year == YEAR) & w.date.dt.dayofyear.between(60, 300)].assign(doy=lambda d: d.date.dt.dayofyear)
    return w.rename(columns=dict(tmean_c="tmean", tmax_c="tmax", precip_mm="precip", pet_mm="pet")).to_dict("records")


@pytest.mark.parametrize("crop", ["pea", "potato", "carrot", "spinach", "turnip_rape"])
@pytest.mark.parametrize("soil", ["clay", "sand"])
def test_a_fully_observed_season_gives_the_cached_features(season_rows, normals, crop, soil):
    f = build()
    want = f[(f.weather_set == "raw") & (f.scenario == "historical") & (f.cell_id == CELL) & (f.year == YEAR) & (f.crop == crop) & (f.soil == soil)].iloc[0]
    got = crop_features(assemble(CELL, YEAR, season_rows, normals[CELL]), crop, soil)
    assert [got[k] for k in FEATURES] == pytest.approx(want[FEATURES].to_numpy(dtype=float), abs=1e-9)


def test_stage_indexes_match_season_features(season_rows, normals):
    """_stages repeats a small part of season_features. If that function changes, the counts must follow."""
    rows = [r for r in season_rows if r["doy"] < 150]
    s = assemble(CELL, YEAR, rows, normals[CELL])
    for crop in ("pea", "potato", "carrot"):
        v = dict(zip(FEATURES, season_features(s.doy, s.t, s.tx, s.p, s.pet, crop, "clay")))
        a, i0, i1, h = _stages(s, crop, v["sow_doy"], v["mat_doy"])
        assert (s.doy[a], s.doy[h]) == (v["sow_doy"], v["mat_doy"])
        assert (s.tx[i0:i1 + 1] >= 27).sum() == v["hot_sens"] and (s.tx[a:h + 1] >= 27).sum() == v["hot_season"]
        assert s.t[i0:i1 + 1].mean() == pytest.approx(v["t_sens"])


def test_typical_season_counts_stay_realistic(normals):
    """A season with no readings must resemble an average real year, not an average day repeated."""
    s = assemble(CELL, YEAR, [], normals[CELL])
    history = read_history()
    h = history[(history.cell_id == CELL) & (history.year < 2021)]
    real_blight = h.assign(b=(h.tmean_c >= 15) & (h.precip_mm >= 1) & h.doy.between(182, 243)).groupby("year").b.sum().mean()
    plain = crop_features(s, "pea", "clay", counts="plain")
    expected = crop_features(s, "pea", "clay", counts="expected")
    assert plain["blight_days"] > 40 and expected["blight_days"] == pytest.approx(real_blight, abs=0.01)
    assert plain["wet_postsow"] == 8 and 2 < expected["wet_postsow"] < 5
    assert plain["hot_season"] == 0 and expected["hot_season"] > 0.5


def test_day_counts_and_gap_handling(normals):
    rows = [dict(doy=d, tmean=10.0, tmax=15.0, precip=2.0, pet=2.0) for d in (100, 101, 104, 120)]
    s = assemble(CELL, YEAR, rows, normals[CELL], gap_interp_days=3)
    c = day_counts(s)
    assert c["observed_days"] == 4 and c["filled_future_days"] == 300 - 120 and c["filled_gap_days"] == N_DAYS - 4 - 180 and c["observed_days"] + c["filled_days"] == N_DAYS
    assert s.t[102 - 60] == pytest.approx(10.0)  # A short gap is interpolated.
    assert s.t[110 - 60] == pytest.approx(normals[CELL]["tmean_c"][110 - 60])  # A long one uses the normals.
    assert s.p[102 - 60] == pytest.approx(normals[CELL]["precip_mm"][102 - 60])  # Rain is never interpolated.


def test_order_of_rows_does_not_matter(normals):
    rows = [dict(doy=int(d), tmean=9.0 + i % 5, tmax=14.0 + i % 5, precip=float(i % 3), pet=2.0) for i, d in enumerate(DOYS[40:90])]
    a, b = assemble(CELL, YEAR, rows, normals[CELL]), assemble(CELL, YEAR, rows[::-1], normals[CELL])
    assert np.array_equal(a.t, b.t) and crop_features(a, "pea", "clay") == crop_features(b, "pea", "clay")


def test_partial_day_uses_normals_for_the_missing_value(normals):
    s = assemble(CELL, YEAR, [dict(doy=150, precip=4.0)], normals[CELL])
    c = day_counts(s)
    assert c["partial_days"] == 1 and c["observed_days"] == 1
    assert s.p[90] == 4.0 and s.t[90] == pytest.approx(normals[CELL]["tmean_c"][90])
