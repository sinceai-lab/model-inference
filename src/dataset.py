"""Build farm x crop x year yields from the survey, ERP deliveries and the Swedish grower file.
Every yield correction or exclusion is written to outputs/yield_corrections_log.csv."""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from config import CROPS, DATA, DELIVERED_RATIO, OUT, SOILS
from features import FEATURES, build

ERP_MATERIAL = {"M100": "turnip_rape", "M110": "pea", "M111": "potato", "M112": "carrot", "M113": "spinach"}
# Unit price against the crop-year median -> what happened to the quantity.
QUANTITY_SLIPS = {1000.0: "unit price 1000x the crop-year contract price; tonnes keyed as kg, quantity x1000",
                  10.0: "unit price 10x the crop-year contract price; decimal slip, quantity x10",
                  0.1: "unit price 0.1x the crop-year contract price; decimal slip, quantity /10"}


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


def clean_erp():
    """Contract-crop lines with kg per line, plus the log of every line changed or left out.

    The contract price is fixed per crop and year, so a unit price 1000, 10 or 0.1 times the median shows a slip in
    the quantity. Prices use no yield data, so the rule can't leak yields from a test season.
    """
    e = pd.read_csv(DATA / "02_raw_feeds/erp_purchase_lines_2021_2025.csv", dtype={"doc_no": str})
    e = e[e.material_id.isin(ERP_MATERIAL)].copy()
    e["crop"] = e.material_id.map(ERP_MATERIAL)
    e["year"] = e.posting_date.str[:4].astype(int)
    e["kg"] = np.where(e.uom == "TO", e.quantity * 1000, e.quantity)
    price = e.net_amount / e.quantity
    ratio = price / price.groupby([e.crop, e.year]).transform("median")
    slip = pd.Series(1.0, index=e.index)
    for factor in QUANTITY_SLIPS:
        slip[ratio.between(0.98 * factor, 1.02 * factor)] = factor
    e["kg"] = e.kg * slip

    def entry(r, new, rule):
        return dict(record_key=f"erp:{r.doc_no}:{r.line_no}", field="quantity", old_value=r.quantity, new_value=new, rule=rule,
                    source="erp_purchase_lines_2021_2025.csv", farm_crop_year=(r.supplier_id, r.crop, r.year))

    log = [entry(r, round(r.kg, 3), QUANTITY_SLIPS[f]) for r, f in zip(e[slip != 1].itertuples(), slip[slip != 1])]
    e = e.sort_values(["posting_date", "doc_no"])
    # The same goods receipt posted again: identical farm, material, quantity, amount and lot, within days.
    duplicate = (e.movement_type == 101) & e.duplicated(["supplier_id", "material_id", "quantity", "net_amount", "lot_id"])
    log += [entry(r, np.nan, "repeat posting of the same goods receipt (same lot, quantity and amount); excluded") for r in e[duplicate].itertuples()]
    # Returned goods were still harvested, so the yield counts them. Across the survey overlap, gross deliveries match reported yields; net ones fall short.
    returns = e.movement_type == 122
    log += [entry(r, np.nan, "return to supplier is a legitimate credit, but the goods were harvested; not subtracted from the yield") for r in e[returns].itertuples()]
    return e[~duplicate & ~returns], log


def yields():
    log = []
    sv = pd.read_csv(DATA / "03_farming/farm_survey_fi.csv")
    med = sv.groupby("crop").yield_t_ha.transform("median")
    slip = sv.yield_t_ha > 3 * med
    for _, r in sv[slip].iterrows():
        log.append(dict(record_key=f"farm_survey:{r.survey_id}", field="yield_t_ha", old_value=r.yield_t_ha, new_value=round(r.yield_t_ha / 10, 3),
                        rule="above 3x crop median; treated as a x10 decimal slip", source="farm_survey_fi.csv", used_for_yield=True))
    sv.loc[slip, "yield_t_ha"] = sv.loc[slip, "yield_t_ha"] / 10
    s = sv[["farm_id", "crop", "year", "yield_t_ha", "irrigated"]].assign(source="survey", irrigated=lambda d: d.irrigated.astype(float))

    e, erp_log = clean_erp()
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
    used = set(zip(d.farm_id, d.crop, d.year))
    log += [{k: v for k, v in r.items() if k != "farm_crop_year"} | {"used_for_yield": r["farm_crop_year"] in used} for r in erp_log]
    d = d.assign(irrigated=np.nan, source="erp")[["farm_id", "crop", "year", "yield_t_ha", "irrigated", "source"]]
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
