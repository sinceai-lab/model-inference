"""Shared paths and assumptions. Crop and soil parameters are our assumptions, not package values."""
import os
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PACKAGE = Path(os.environ.get("APETIT_PACKAGE", PROJECT.parent / "APETIT_CLIMATE_NATURE_NAVIGATOR_2026"))
DATA = PACKAGE / "data"
TASKS = PACKAGE / "tasks"
OUT = PROJECT / "outputs"
CACHE = PROJECT / "cache"

CROPS = ["pea", "potato", "carrot", "spinach", "turnip_rape"]
SOILS = ["clay", "silt", "fine_sand", "sand", "organic"]
# Plant-available water (mm). Assumed: the package describes a soil bucket model but not its values.
AWC_MM = {"clay": 150.0, "silt": 180.0, "fine_sand": 130.0, "sand": 80.0, "organic": 220.0}
# Assumed agronomy: sowing threshold (C), sensitive stage (GDD base 5), maturity (GDD), latest harvest (day of year).
# Pea maturity (was 750) and turnip rape's sensitive stage (was 350-600) come from held-out seasons: see src/stage_test.py.
# The other values aren't supported or contradicted by the tests, so they stay as assumed.
CROP = {
    "pea": dict(sow_t=6.0, s0=400, s1=600, mat=850, cutoff=245),
    "turnip_rape": dict(sow_t=6.0, s0=455, s1=780, mat=1000, cutoff=258),
    "potato": dict(sow_t=8.0, s0=400, s1=800, mat=1200, cutoff=265),
    "carrot": dict(sow_t=8.0, s0=500, s1=1000, mat=1300, cutoff=275),
    "spinach": dict(sow_t=6.0, s0=200, s1=400, mat=500, cutoff=240),
}
# Delivered kg / reported yield: the median across farms that answered the survey, on 1,424 farm-years of 2021-2025 ERP lines after cleaning.
DELIVERED_RATIO = {"pea": 0.975, "potato": 0.965, "carrot": 0.974, "spinach": 0.978, "turnip_rape": 1.0}
# Chosen per crop from outputs/backtest_per_crop_grid.csv (leave-one-year-out; slope close to 1).
MODEL_PARAMS = {"pea": (100, 6), "turnip_rape": (100, 6), "potato": (3, 3), "carrot": (30, 6), "spinach": (100, 6)}
