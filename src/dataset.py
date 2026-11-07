"""Build farm x crop x year yields from the survey, ERP deliveries and the Swedish grower file.
Every yield correction or exclusion is written to outputs/yield_corrections_log.csv."""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from config import CROPS, DATA, DELIVERED_RATIO, OUT, SOILS
from features import FEATURES, build

ERP_MATERIAL = {"M100": "turnip_rape", "M110": "pea", "M111": "potato", "M112": "carrot", "M113": "spinach"}


def parcels_with_cells():
    p = pd.read_csv(DATA / "01_master/parcels.csv")
    cells = pd.read_csv(DATA / "01_master/climate_grid_cells.csv")
    # Nearest cell within the farm's own region; parcel centroids avoid the swapped farm_registry coordinates.
    p["region"] = np.where(p.farm_id.str.startswith("S"), "SE_SKANE", "FI_SW")
    p["cell_id"] = None
    for region, c in cells.groupby("region"):
        i = p.region == region
        p.loc[i, "cell_id"] = c.cell_id.to_numpy()[cKDTree(c[["lat", "lon"]].to_numpy()).query(p.loc[i, ["lat", "lon"]].to_numpy())[1]]
    p["clay"] = p.clay_pct_soilmap
    return p


def yields():
    log = []
    sv = pd.read_csv(DATA / "03_farming/farm_survey_fi.csv")
    med = sv.groupby("crop").yield_t_ha.transform("median")
    slip = sv.yield_t_ha > 3 * med
    for _, r in sv[slip].iterrows():
        log.append(dict(record_key=f"farm_survey:{r.survey_id}", field="yield_t_ha", old_value=r.yield_t_ha, new_value=round(r.yield_t_ha / 10, 3),
                        rule="above 3x crop median; treated as a x10 decimal slip", source="farm_survey_fi.csv"))
    sv.loc[slip, "yield_t_ha"] = sv.loc[slip, "yield_t_ha"] / 10
    s = sv[["farm_id", "crop", "year", "yield_t_ha", "irrigated"]].assign(source="survey", irrigated=lambda d: d.irrigated.astype(float))

    e = pd.read_csv(DATA / "02_raw_feeds/erp_purchase_lines_2021_2025.csv")
    e = e[e.material_id.isin(ERP_MATERIAL)].copy()
    e["crop"] = e.material_id.map(ERP_MATERIAL)
    e["year"] = e.posting_date.str[:4].astype(int)
    e["kg"] = np.where(e.uom == "TO", e.quantity * 1000, e.quantity)
    e.loc[e.movement_type == 122, "kg"] = -e.kg.abs()
    d = e.groupby(["supplier_id", "crop", "year"]).kg.sum().reset_index().rename(columns={"supplier_id": "farm_id"})

    fh = pd.read_csv(DATA / "03_farming/foodhills_odlingsdata_se.csv", sep=";", decimal=",")
    se = pd.DataFrame(dict(farm_id=fh.odlar_id, crop="pea", year=fh["skördeår"],
                           yield_t_ha=fh["levererad_mängd_ton"] / fh["areal_ha"] / DELIVERED_RATIO["pea"],  # assumes the Finnish pea ratio
                           irrigated=(fh.bevattnad == "ja").astype(float), source="foodhills"))

    ch = pd.read_csv(DATA / "03_farming/parcel_crop_history_and_plan.csv")
    p = parcels_with_cells()
    a = ch[ch.crop.isin(CROPS)].merge(p[["parcel_id", "area_ha", "soil_class_soilmap", "cell_id", "clay", "region"]], on="parcel_id")
    area = a[a.status == "declared"].groupby(["farm_id", "crop", "year"]).area_ha.sum().rename("area_ha").reset_index()

    d = d.merge(area, on=["farm_id", "crop", "year"]).merge(s[["farm_id", "crop", "year"]].assign(has=1), how="left", on=["farm_id", "crop", "year"])
    d = d[d.has.isna()]
    d["yield_t_ha"] = d.kg / 1000 / d.area_ha / d.crop.map(DELIVERED_RATIO)
    ref = s.groupby(["crop", "year"]).yield_t_ha.median().rename("ref").reset_index()
    d = d.merge(ref, on=["crop", "year"])
    bad = ~d.yield_t_ha.between(0.35 * d.ref, 2.2 * d.ref)
    for _, r in d[bad].iterrows():
        log.append(dict(record_key=f"erp_delivery:{r.farm_id}:{r.crop}:{r.year}", field="yield_t_ha", old_value=round(r.yield_t_ha, 3), new_value=np.nan,
                        rule="ERP-derived yield outside 0.35-2.2x crop-year median; excluded", source="erp_purchase_lines_2021_2025.csv"))
    d = d[~bad].assign(irrigated=np.nan, source="erp")[["farm_id", "crop", "year", "yield_t_ha", "irrigated", "source"]]
    OUT.mkdir(exist_ok=True)
    pd.DataFrame(log).to_csv(OUT / "yield_corrections_log.csv", index=False)
    y = pd.concat([s, d, se], ignore_index=True)
    return y, a


def attach_features(rows, f, keys):
    """Area-weighted features per key. rows must hold cell_id, soil_class_soilmap, area_ha, crop and year."""
    m = rows.merge(f.rename(columns={"soil": "soil_class_soilmap"}), on=["cell_id", "soil_class_soilmap", "crop", "year"])
    w = m.area_ha.to_numpy()[:, None]
    vals = pd.DataFrame(m[FEATURES].to_numpy() * w, columns=FEATURES)
    vals[keys] = m[keys].to_numpy()
    vals["area_ha"] = w[:, 0]
    for s in SOILS:
        vals["soil_" + s] = (m.soil_class_soilmap == s).to_numpy() * w[:, 0]
    vals["clay"] = m.clay.fillna(m.clay.median()).to_numpy() * w[:, 0]
    g = vals.groupby(keys, sort=False).sum(numeric_only=False)
    a = g.pop("area_ha")
    g = g.astype(float).div(a, axis=0)
    g["area_ha"] = a
    return g.reset_index()


def training():
    y, a = yields()
    f = build()
    h = f[(f.weather_set == "raw") & (f.scenario == "historical")].drop(columns=["weather_set", "scenario"])
    d = attach_features(a[a.status == "declared"], h, ["farm_id", "crop", "year"])
    t = y.merge(d, on=["farm_id", "crop", "year"])
    t["region"] = np.where(t.farm_id.str.startswith("S"), "SE_SKANE", "FI_SW")
    return t


if __name__ == "__main__":
    t = training()
    print(t.groupby(["region", "crop", "source"]).size().to_string())
    print(pd.read_csv(OUT / "yield_corrections_log.csv").groupby("rule").size().to_string())
    t.to_parquet(OUT.parent / "cache" / "training.parquet", index=False)
