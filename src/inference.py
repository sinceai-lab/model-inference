"""Load the trained yield models and predict one parcel. Used by the viewer."""
import pickle

import numpy as np
import pandas as pd

from advisor import weather_sets
from config import CACHE, DATA, OUT, SOILS
from dataset import parcels_with_cells
from features import build


class Predictor:
    def __init__(self):
        with open(CACHE / "models.pkl", "rb") as fh:
            saved = pickle.load(fh)
        self.models, self.long_models, self.farm_irr, self.farm_mean = saved["models"], saved["long_models"], saved["farm_irr"], saved["farm_mean"]
        self.parcels = parcels_with_cells().set_index("parcel_id")
        f = build()
        self.sets = weather_sets(f)
        self.history = pd.read_csv(DATA / "03_farming/parcel_crop_history_and_plan.csv")
        self.weather = f[f.weather_set == "raw"].drop(columns="weather_set").rename(columns={"soil": "soil_class_soilmap"})

    def predict(self, parcel_id, crop, scenario, year, irrigation=None):
        """irrigation: share from 0 to 1, or None for the farm's usual share. Technology follows the year up to 2031, then stays at 2025."""
        p = self.parcels.loc[parcel_id]
        w = self.weather[(self.weather.cell_id == p.cell_id) & (self.weather.scenario == scenario) & (self.weather.year == year)
                         & (self.weather.crop == crop) & (self.weather.soil_class_soilmap == p.soil_class_soilmap)]
        if w.empty:
            raise ValueError(f"No weather for {crop} in {scenario} {year}")
        d = w.iloc[[0]].copy()
        d["farm_id"], d["region"], d["clay"] = p.farm_id, p.region, p.clay
        for s in SOILS:
            d["soil_" + s] = float(p.soil_class_soilmap == s)
        usual = float(self.farm_irr.get((p.farm_id, crop), 0.0))
        d["irr"] = usual if irrigation is None else irrigation
        technology = None if year <= 2031 else 2025
        if technology is not None:
            d["year"] = technology
        # Long-range seasons use the same shared weather response as the 2041-2060 risk tables.
        model = self.models[crop] if technology is None else self.long_models[crop]
        base, effects = model.explain(d)
        return dict(pred=float(np.exp(model.predict_log(d))[0]), base=float(np.exp(base)), effects=effects, usual_irrigation=usual,
                    baseline=float(self.farm_mean.get((p.farm_id, crop), np.nan)), weather=d.iloc[0], parcel=p)

    def check_against_submission(self, n=200):
        """Largest difference between live predictions and the submitted C1 file."""
        sub = pd.read_csv(OUT / "C1_yields_2027_2031_submission.csv").sample(n, random_state=1)
        return max(abs(self.predict(r.parcel_id, r.crop, "ssp245", r.year)["pred"] - r.yield_t_ha_pred) for r in sub.itertuples())
