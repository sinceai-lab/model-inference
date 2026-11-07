"""Predictions from cache/models.pkl, free of web code so an MCP server can reuse them. The model file is replaceable: it's
checked on every use and reloaded when it changes, and nothing here depends on its coefficients. Technology follows the
Predictor's rule: `models` with the season's year up to 2031, `long_models` with technology fixed at 2025 after that."""
import hashlib
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import service  # noqa: F401
from config import CACHE, CROPS, DATA, SOILS
from dataset import parcels_with_cells
from features import FEATURES
from inference import Predictor
from service.season import crop_features, day_counts, filled_to_maturity

LAST_NEAR_YEAR, TECH_YEAR = 2031, 2025
REGIONS = ("FI_SW", "SE_SKANE")
IN_RANGE_CHECKED = FEATURES + ["clay", "year"]
SCENARIOS = ("historical", "ssp126", "ssp245", "ssp585")


class UnknownInput(ValueError):
    """A parcel, crop or scenario the data doesn't have."""


def _clean(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Engine:
    def __init__(self, models_path=None, training_path=None):
        self.models_path, self.training_path = Path(models_path or CACHE / "models.pkl"), Path(training_path or CACHE / "training.parquet")
        self.stamp, self.load_error, self._predictor = None, None, None
        self.parcels = parcels_with_cells().set_index("parcel_id")
        h = pd.read_csv(DATA / "03_farming/parcel_crop_history_and_plan.csv")
        h = h[h.crop.isin(CROPS)].merge(self.parcels[["cell_id", "region", "soil_class_soilmap", "clay", "area_ha"]], left_on="parcel_id", right_index=True)
        self.plans = dict(tuple(h.groupby(["cell_id", "year"])))
        self.refresh()
        if self.stamp is None:
            raise RuntimeError(self.load_error)

    def refresh(self):
        """Reload when the file changed. A broken replacement keeps the last good models and is reported by /health."""
        st = self.models_path.stat()
        stamp = (st.st_mtime_ns, st.st_size)
        if stamp == self.stamp:
            return
        try:
            data = self.models_path.read_bytes()
            saved = pickle.loads(data)
            models, long_models, farm_irr, farm_mean = saved["models"], saved["long_models"], saved["farm_irr"], saved["farm_mean"]
        except Exception as e:
            self.load_error = f"Couldn't load {self.models_path}: {e}"
            return
        self.models, self.long_models, self.farm_irr, self.farm_mean = models, long_models, farm_irr, farm_mean
        self.version, self.stamp, self.load_error, self._predictor = hashlib.sha256(data).hexdigest()[:12], stamp, None, None
        self.ranges = self._training_ranges()

    def _training_ranges(self):
        """(low, high) per crop and region from the training table, or mean +/- 4 SD from the model if it's gone."""
        ranges = {}
        if self.training_path.exists():
            t = pd.read_parquet(self.training_path)
            for key, g in t.groupby(["crop", "region"]):
                ranges[key] = {c: (float(g[c].min()), float(g[c].max())) for c in IN_RANGE_CHECKED}
        for crop, m in self.models.items():
            for region in REGIONS:
                ranges.setdefault((crop, region), {c: (float(m.mu[c] - 4 * m.sd[c]), float(m.mu[c] + 4 * m.sd[c])) for c in FEATURES})
        return ranges

    def info(self):
        return dict(path=str(self.models_path), version=self.version, crops=sorted(self.models), load_error=self.load_error)

    def choose(self, crop, year, kind="auto"):
        """(model, its name, the year its trend term should see)."""
        if kind == "auto":
            kind = "models" if year <= LAST_NEAR_YEAR else "long_models"
        return (self.models[crop], f"models[{crop}]", year) if kind == "models" else (self.long_models[crop], f"long_models[{crop}]", TECH_YEAR)

    def flags(self, row, crop):
        """Values outside what this crop's model saw in training. They're reported, not blocked, as the model can still compute them."""
        out = []
        for c, (low, high) in self.ranges.get((crop, row["region"]), {}).items():
            if c in row and not low <= row[c] <= high:
                out.append(dict(field=c, value=round(float(row[c]), 3), training_min=round(low, 3), training_max=round(high, 3)))
        return out

    def predict_row(self, row, kind="auto"):
        """row: farm_id, region, crop, year, clay, irr, soil_* and the 16 weather features."""
        self.refresh()
        row, crop = dict(row), row["crop"]
        if crop not in self.models:
            raise UnknownInput(f"Unknown crop {crop!r}. Known: {sorted(self.models)}.")
        model, name, tech = self.choose(crop, row["year"], kind)
        flags = self.flags(row, crop)
        d = pd.DataFrame([row])
        d["year"] = tech
        y = float(np.exp(model.predict_log(d))[0])
        soil_sum = sum(row["soil_" + s] for s in SOILS)
        warnings = [] if abs(soil_sum - 1) < 1e-6 else [f"soil_* values add up to {soil_sum:g}, not 1"]
        if row["farm_id"] not in model.farms:
            warnings.append(f"Farm {row['farm_id']} wasn't in training, so no farm effect is applied")
        if not 0 <= row["irr"] <= 1:
            warnings.append(f"irr {row['irr']:g} is outside 0 to 1")
        return dict(yield_t_ha=y, model_name=name, model_version=self.version, technology_year=tech, out_of_training_range=flags, warnings=warnings)

    @property
    def predictor(self):
        """The viewer's Predictor, sharing this engine's models. Loaded on first use, as it reads the whole feature cache."""
        if self._predictor is None:
            p = Predictor()
            p.models, p.long_models, p.farm_irr, p.farm_mean = self.models, self.long_models, self.farm_irr, self.farm_mean
            self._predictor = p
        return self._predictor

    def predict_field(self, parcel_id, crop, scenario, year, irrigation=None):
        """An existing parcel with a whole season's weather from the feature cache. Not an in-season estimate."""
        self.refresh()
        if parcel_id not in self.parcels.index:
            raise UnknownInput(f"Unknown parcel {parcel_id!r}.")
        if crop not in self.models:
            raise UnknownInput(f"Unknown crop {crop!r}. Known: {sorted(self.models)}.")
        if scenario not in SCENARIOS:
            raise UnknownInput(f"Unknown scenario {scenario!r}. Known: {list(SCENARIOS)}.")
        try:
            r = self.predictor.predict(parcel_id, crop, scenario, year, irrigation)
        except ValueError as e:
            raise UnknownInput(f"{e} for parcel {parcel_id}. Features exist for historical 1991-2026, ssp245 2027-2031 and every SSP 2041-2060, and Swedish cells only have pea.") from e
        w = r["weather"]
        p = self.parcels.loc[parcel_id]
        row = dict(region=p.region, clay=float(p.clay), year=year, **{f: float(w[f]) for f in FEATURES})
        _, name, tech = self.choose(crop, year)
        return dict(parcel_id=parcel_id, farm_id=p.farm_id, cell_id=p.cell_id, crop=crop, scenario=scenario, year=year, yield_t_ha=r["pred"], baseline_t_ha=_clean(r["baseline"]), usual_irrigation=r["usual_irrigation"],
                    irrigation=r["usual_irrigation"] if irrigation is None else irrigation, model_name=name, model_version=self.version, technology_year=tech, out_of_training_range=self.flags(row, crop),
                    effects={k: float(v) for k, v in r["effects"].items()}, weather={f: float(w[f]) for f in FEATURES})

    def plan_for(self, cell_id, year):
        """Parcels in this cell with a contract crop declared or planned this season."""
        return self.plans.get((cell_id, year))

    def predict_cell(self, season, counts="expected"):
        """Estimates for every planned contract crop in the cell, with the season as far as it's known."""
        self.refresh()
        plan = self.plan_for(season.cell_id, season.year)
        if plan is None:
            return []
        days = day_counts(season)
        as_of = (pd.Timestamp(season.year, 1, 1) + pd.Timedelta(days=int(season.last_doy) - 1)).date().isoformat()
        stamp = now()
        out = []
        for crop, g in plan.groupby("crop"):
            if crop not in self.models:
                continue
            model, name, tech = self.choose(crop, season.year)
            feats = {soil: crop_features(season, crop, soil, counts) for soil in g.soil_class_soilmap.unique()}
            d = g[["parcel_id", "farm_id", "region", "clay", "status"]].copy()
            for s in SOILS:
                d["soil_" + s] = (g.soil_class_soilmap == s).astype(float)
            for f in FEATURES:
                d[f] = g.soil_class_soilmap.map(lambda soil: feats[soil][f])
            d["irr"] = [float(self.farm_irr.get((a, crop), 0.0)) for a in d.farm_id]
            d["year"] = tech
            ys = np.exp(model.predict_log(d))
            ranges = self.ranges.get((crop, g.region.iloc[0]), {})
            for r, y in zip(d.to_dict("records"), ys):
                f = {k: r[k] for k in FEATURES}
                flags = [k for k in FEATURES if k in ranges and not ranges[k][0] <= f[k] <= ranges[k][1]]
                out.append(dict(parcel_id=r["parcel_id"], farm_id=r["farm_id"], cell_id=season.cell_id, crop=crop, year=season.year, as_of_date=as_of, status=r["status"], area_ha=float(g.area_ha[g.parcel_id == r["parcel_id"]].iloc[0]),
                                yield_t_ha=float(y), baseline_t_ha=_clean(float(self.farm_mean.get((r["farm_id"], crop), float("nan")))), model_name=name, model_version=self.version, technology_year=tech, label="estimate",
                                filled_to_maturity=filled_to_maturity(season, f["mat_doy"]), mat_doy=f["mat_doy"], sow_doy=f["sow_doy"], features=f, out_of_training_range=flags, computed_at=stamp, **{k: days[k] for k in ("observed_days", "partial_days", "filled_days", "filled_gap_days", "filled_future_days", "total_days")}))
        return out

