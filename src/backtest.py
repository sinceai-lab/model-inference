"""Honest backtests. Scorer-style metrics; farm-level rows stand in for parcels, so nRMSE is indicative."""
import numpy as np
import pandas as pd

from config import OUT
from models import YieldModel, groups


def prep(t, mask=None):
    t = t.copy()
    tr = t if mask is None else t[mask]
    fm = tr.groupby("farm_id").irrigated.mean()
    t["irr_fm"] = t.farm_id.map(fm)
    fallback = tr.groupby(["region", "crop"]).irrigated.mean().rename("irr_g").reset_index()
    t = t.merge(fallback, on=["region", "crop"], how="left")
    t["irr"] = t.irr_fm.fillna(t.irr_g).fillna(0.0)
    return t


def metrics(p):
    p = p.assign(prod_t=p.yield_t_ha * p.area_ha, prod_p=p.pred * p.area_ha)
    agg = p.groupby(["region", "crop", "year"])[["prod_t", "prod_p"]].sum()
    mape = (abs(agg.prod_p - agg.prod_t) / agg.prod_t).groupby(level=["region", "crop"]).mean()
    nr = p.groupby("crop").apply(lambda g: np.sqrt(((g.pred - g.yield_t_ha) ** 2).mean()) / g.yield_t_ha.mean(), include_groups=False)
    overall_mape, overall_nr = float((abs(agg.prod_p - agg.prod_t) / agg.prod_t).mean()), float(nr.mean())
    score = 100 * (0.6 * max(0, 1 - overall_mape / 0.15) + 0.4 * max(0, 1 - overall_nr / 0.35))
    return dict(score=round(score, 1), mape=round(overall_mape, 4), nrmse=round(overall_nr, 4), by_mape=mape.round(3).to_dict(), by_nr=nr.round(3).to_dict())


def evaluate(t, years, make, forward=False):
    rows = []
    for y in years:
        train_mask = (t.year < y) if forward else (t.year != y)
        d = prep(t, mask=train_mask)
        tr, te = d[train_mask.to_numpy()], d[(d.year == y).to_numpy()]
        for c, g in groups(tr).items():
            q = te[te.crop == c]
            if q.empty or len(g) < 30:
                continue
            q = q[q.farm_id.isin(g.farm_id)]
            if q.empty:
                continue
            # Observed same-year irrigation is allowed in training only.
            gt = g.assign(irr=g.irrigated.fillna(g.irr))
            pred = make(c).fit(gt).predict_log(q) if make(c) is not None else None
            if pred is None:
                fm = gt.groupby("farm_id").yield_t_ha.mean()
                rows.append(q.assign(pred=q.farm_id.map(fm)))
            else:
                rows.append(q.assign(pred=np.exp(pred)))
    return pd.concat(rows, ignore_index=True)


def calibration_slope(p):
    """Slope of observed on predicted season anomalies, out of sample. Above 1 means the penalty shrank the weather response."""
    g = p.assign(lo=np.log(p.yield_t_ha), lp=np.log(p.pred)).groupby(["region", "year"])[["lo", "lp"]].mean()
    g = g - g.groupby(level="region").transform("mean")
    return float((g.lo * g.lp).sum() / (g.lp ** 2).sum())


if __name__ == "__main__":
    t = pd.read_parquet(OUT.parent / "cache" / "training.parquet").reset_index(drop=True)
    yrs = sorted(t.year.unique())
    rows = []
    for crop in sorted(t.crop.unique()):
        q = t[t.crop == crop].reset_index(drop=True)
        fm = metrics(evaluate(q, yrs, lambda c: None))
        rows.append(dict(crop=crop, model="farm_mean", alpha=np.nan, farm_scale=np.nan, n=len(q), mape=fm["mape"], nrmse=fm["nrmse"], slope=np.nan))
        for a in (3, 10, 30, 100, 300):
            for s in (1, 3, 6):
                m = (lambda a, s: (lambda c: YieldModel(alpha=a, farm_scale=s)))(a, s)
                p = evaluate(q, yrs, m)
                r = metrics(p)
                f = metrics(evaluate(q, [y for y in yrs if y >= 2022], m, forward=True))
                rows.append(dict(crop=crop, model="ridge", alpha=a, farm_scale=s, n=len(q), mape=r["mape"], nrmse=r["nrmse"], slope=round(calibration_slope(p), 3),
                                 forward_mape=f["mape"], forward_nrmse=f["nrmse"]))
    d = pd.DataFrame(rows)
    d["crop_score"] = 100 * (0.6 * (1 - d.mape / 0.15).clip(lower=0) + 0.4 * (1 - d.nrmse / 0.35).clip(lower=0))
    d.to_csv(OUT / "backtest_per_crop_grid.csv", index=False)
    pd.set_option("display.width", 200)
    print(d[d.model == "farm_mean"].round(3).to_string())
    print(d[d.model == "ridge"].sort_values("crop_score", ascending=False).groupby("crop").head(3).sort_values(["crop", "crop_score"], ascending=[True, False]).round(3).to_string())
