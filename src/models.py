"""Yield models: log(yield) = farm effect + trend + weather response. No same-year farm inputs are used,
because those are not known for 2027-2031."""
import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge

from config import SOILS
from features import FEATURES

STRESS = ["stress_early", "stress_sens", "stress_late"]
BASE_YEAR = 2020


TERM_GROUPS = [("stress_", "Drought stress"), ("hot_", "Heat"), ("t_sens", "Heat"), ("rain_postsow", "Rain after sowing"), ("wet_postsow", "Rain after sowing"),
               ("rain_preharv", "Rain before harvest"), ("rain_season", "Season rain and evaporation"), ("pet_season", "Season rain and evaporation"),
               ("sow_doy", "Season timing"), ("mat_doy", "Season timing"), ("gdd_gap", "Season timing"), ("blight_days", "Warm, wet days"), ("may_t", "May temperature"),
               ("soil_", "Soil"), ("clay", "Soil"), ("irr", "Irrigation"), ("trend", "Technology trend"), ("is_se", "Region")]


def _term_group(term):
    if term.endswith("_irr"):
        return "Irrigation"
    return next(label for prefix, label in TERM_GROUPS if term.startswith(prefix))


class YieldModel:
    def __init__(self, alpha=30.0, gbm_weight=0.0, use_weather=True, farm_scale=3.0, se_interactions=True):
        self.alpha, self.gbm_weight, self.use_weather, self.farm_scale, self.se_interactions = alpha, gbm_weight, use_weather, farm_scale, se_interactions

    def _x(self, d):
        x = pd.DataFrame(index=d.index)
        x["trend"] = (d.year - BASE_YEAR) / 10.0
        for s in SOILS[1:]:
            x["soil_" + s] = d["soil_" + s]
        x["clay"] = (d.clay - 30) / 30.0
        x["irr"] = d.irr
        x["is_se"] = (d.region == "SE_SKANE").astype(float)
        if self.use_weather:
            for c in FEATURES:
                z = (d[c] - self.mu[c]) / self.sd[c]
                x[c] = z
                x[c + "_se"] = z * x["is_se"] if self.pooled else 0.0
                x[c + "_sq"] = np.minimum(z, 3) ** 2 if c in STRESS + ["hot_sens", "rain_preharv", "rain_postsow"] else 0.0
            for c in STRESS:
                x[c + "_irr"] = x[c] * d.irr
        return x.fillna(0.0)

    def fit(self, d):
        d = d.copy()
        self.mu, self.sd = d[FEATURES].mean(), d[FEATURES].std().replace(0, 1)
        self.pooled = d.region.nunique() > 1 and self.se_interactions
        self.farms = {f: i for i, f in enumerate(sorted(d.farm_id.unique()))}
        self.fm_irr = d.groupby("farm_id").irr.mean()
        self.global_irr = d.irr.mean()
        x = self._x(d)
        self.cols = x.columns
        self.x_mean = x.mean()
        farm = sp.csr_matrix((np.full(len(d), self.farm_scale), (np.arange(len(d)), d.farm_id.map(self.farms))), shape=(len(d), len(self.farms)))
        X = sp.hstack([sp.csr_matrix(x.to_numpy()), farm]).tocsr()
        y = np.log(d.yield_t_ha.to_numpy())
        self.m = Ridge(alpha=self.alpha, fit_intercept=True).fit(X, y)
        if self.gbm_weight > 0:
            r = y - self.m.predict(X)
            self.gb_cols = FEATURES + ["soil_" + s for s in SOILS[1:]] + ["irr"]
            self.gb = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=120, min_samples_leaf=60, l2_regularization=5.0).fit(d[self.gb_cols], r)
        return self

    def predict_log(self, d, technology_year=None):
        d = d.copy()
        if technology_year is not None:
            d["year"] = technology_year
        x = self._x(d).reindex(columns=self.cols, fill_value=0.0)
        idx = d.farm_id.map(self.farms)
        n = len(self.farms)
        known = idx.notna().to_numpy()
        farm = sp.csr_matrix((np.full(known.sum(), self.farm_scale), (np.where(known)[0], idx[known].astype(int))), shape=(len(d), n))
        out = self.m.predict(sp.hstack([sp.csr_matrix(x.to_numpy()), farm]).tocsr())
        if self.gbm_weight > 0:
            out = out + self.gbm_weight * self.gb.predict(d[self.gb_cols])
        return out

    def explain(self, d):
        """For one row: average-season log yield, and each term's log-yield effect. They sum to predict_log (no GBM)."""
        x = self._x(d).reindex(columns=self.cols, fill_value=0.0).iloc[0]
        coef = pd.Series(self.m.coef_[:len(self.cols)], index=self.cols)
        effects = (coef * (x - self.x_mean)).groupby(_term_group).sum()
        i = self.farms.get(d.farm_id.iloc[0])
        effects["This farm"] = float(self.m.coef_[len(self.cols) + i] * self.farm_scale) if i is not None else 0.0
        return float(self.m.intercept_ + coef @ self.x_mean), effects

    def coefficients(self):
        return pd.Series(self.m.coef_[:len(self.cols)], index=self.cols)


def groups(t):
    """One model per crop. Peas are pooled across Finland and Sweden to give the weather response more seasons."""
    return {c: t[t.crop == c] for c in t.crop.unique()}
