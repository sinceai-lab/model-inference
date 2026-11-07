"""Regenerate docs/cb_handoff example rows and weather from the current models. Run after run_all.py."""
import numpy as np
import pandas as pd

from config import DATA, OUT, PROJECT, SOILS
from features import FEATURES, season_features
from inference import Predictor

HANDOFF = PROJECT / "docs/cb_handoff"
EXAMPLES = [("FI_SW", "pea"), ("SE_SKANE", "pea"), ("FI_SW", "turnip_rape"), ("FI_SW", "potato"), ("FI_SW", "carrot"), ("FI_SW", "spinach")]


def main():
    predictor = Predictor()
    submission = pd.read_csv(OUT / "C1_yields_2027_2031_submission.csv")
    rows, submitted = [], []
    for region, crop in EXAMPLES:
        s = submission[(submission.region == region) & (submission.crop == crop) & (submission.year == 2027)].iloc[0]
        r = predictor.predict(s.parcel_id, crop, "ssp245", 2027)
        w, p = r["weather"], r["parcel"]
        row = dict(model_file="cache/models.pkl", model_group="models", model_key=crop, parcel_id=s.parcel_id, cell_id=p.cell_id, farm_id=w.farm_id, region=w.region, year=int(w.year), clay=w.clay, irr=round(float(w.irr), 4))
        row.update({"soil_" + x: int(w["soil_" + x]) for x in SOILS})
        row.update({f: round(float(w[f]), 4) for f in FEATURES})
        rows.append(dict(row, expected_yield_t_ha=round(r["pred"], 3)))
        submitted.append(s.yield_t_ha_pred)
    table = pd.DataFrame(rows)
    table.to_csv(HANDOFF / "model_input_examples.csv", index=False)

    # Checks: the CSV reproduces the submission, and the weather file reproduces the first row's features.
    table = pd.read_csv(HANDOFF / "model_input_examples.csv")
    for i, row in table.iterrows():
        pred = float(np.exp(predictor.models[row.model_key].predict_log(table.iloc[[i]]))[0])
        assert abs(pred - submitted[i]) < 0.002, (row.parcel_id, pred, submitted[i])
        print(f"{row.model_key:12} {row.region:9} {row.parcel_id:11} {pred:.3f}")
    first = table.iloc[0]
    q = pd.read_parquet(DATA / "04_climate/weather_daily_1991_2060.parquet", columns=["cell_id", "date", "scenario", "tmean_c", "tmax_c", "precip_mm", "pet_mm"])
    q["date"] = pd.to_datetime(q.date)
    q = q[(q.cell_id == first.cell_id) & (q.scenario == "ssp245") & (q.date.dt.year == 2027)].assign(doy=lambda d: d.date.dt.dayofyear)
    q = q[q.doy.between(60, 300)].sort_values("date")
    q.drop(columns="doy").assign(date=q.date.dt.strftime("%Y-%m-%d")).to_csv(HANDOFF / "daily_weather_example.csv", index=False)
    soil = next(s for s in SOILS if first["soil_" + s] == 1)
    rebuilt = season_features(q.doy.to_numpy(), q.tmean_c.to_numpy(), q.tmax_c.to_numpy(), q.precip_mm.to_numpy(), q.pet_mm.to_numpy(), first.model_key, soil)
    assert max(abs(float(a) - first[f]) for a, f in zip(rebuilt, FEATURES)) < 0.001
    print("Rows and weather verified.")


if __name__ == "__main__":
    main()
