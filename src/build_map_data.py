"""Precompute what the Map tab draws, and the evidence for what it may claim. Run from src/: python build_map_data.py
Add --natural-earth DIR (needs shapely and Natural Earth 10m land, lakes and countries GeoJSON) to rebuild the coastline and rerun the land checks."""
import argparse
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from advisor import STORIES, TECH_YEAR, field_table
from config import DATA, OUT, SOILS
from inference import Predictor

SOON = 2028  # The crop plan runs 2027-2031 and reaches nearly every field, so only the next two seasons separate farms.
BOX = {"FI_SW": (18.5, 58.8, 27.0, 63.2), "SE_SKANE": (9.5, 53.8, 17.5, 58.4)}  # Wider than any view, so the clip edge never shows.
FARM_COLS = ["area_ha", "soil_class_soilmap", "yield_today", "change_below_2c", "change_current_policies", "next_planned", "droughty_soil"]


def all_fields(p):
    """field_table for every farm and crop pair, so the map can't disagree with the Farm and fields tab."""
    rows = [field_table(p, farm, crop)[["parcel_id", *FARM_COLS]].assign(farm_id=farm, crop=crop) for farm, crop in p.farm_mean.index]
    d = pd.concat(rows, ignore_index=True)
    return d.merge(p.parcels[["lat", "lon", "cell_id", "region"]], left_on="parcel_id", right_index=True)


def soil_effects(d, p):
    """One figure per region, crop and soil. Pooling across grid cells removes the cell differences that evidence() shows are mostly weather noise."""
    out = []
    for (region, crop, soil), g in d.groupby(["region", "crop", "soil_class_soilmap"]):
        row = dict(region=region, crop=crop, soil=soil, n_fields=len(g), area_ha=g.area_ha.sum())
        row.update({s: np.average(g[s], weights=g.area_ha) for s in ["change_below_2c", "change_current_policies"]})
        cells = g.groupby("cell_id").area_ha.sum().rename("cell_area").reset_index()
        w = p.sets[(p.sets.crop == crop) & (p.sets.soil_class_soilmap == soil)].merge(cells, on="cell_id")
        for name, ssp in {"today": "baseline", **STORIES}.items():
            q = w[w.ssp == ssp]
            row["stress_" + name] = np.average(q.stress_sens, weights=q.cell_area)
        out.append(row)
    return pd.DataFrame(out)


def farms(d, effects):
    """One row per farm and crop. Yield change comes from the farm's soil mix and the pooled soil figures."""
    e = effects.set_index(["region", "crop", "soil"])
    d = d.join(e[["change_below_2c", "change_current_policies"]].rename(columns=lambda c: "pooled_" + c), on=["region", "crop", "soil_class_soilmap"])
    rows = []
    for (region, crop, farm), g in d.groupby(["region", "crop", "farm_id"]):
        a, planned = g.area_ha, g[g.next_planned <= SOON]
        rows.append(dict(region=region, crop=crop, farm_id=farm, lat=np.average(g.lat, weights=a), lon=np.average(g.lon, weights=a), n_fields=len(g), area_ha=a.sum(), dry_fields=int(g.droughty_soil.sum()), dry_ha=a[g.droughty_soil].sum(),
                         planned_fields=len(planned), planned_ha=planned.area_ha.sum(), planned_dry_ha=planned.area_ha[planned.droughty_soil].sum(),
                         change_below_2c=np.average(g.pooled_change_below_2c, weights=a), change_current_policies=np.average(g.pooled_change_current_policies, weights=a)))
    return pd.DataFrame(rows).assign(dry_share=lambda x: x.dry_ha / x.area_ha)


def moran(values, xy, k=6):
    """Are neighbours more alike than chance? About 0 means no spatial pattern."""
    z = (values - values.mean()) / values.std()
    neighbours = cKDTree(xy).query(xy, k=k + 1)[1][:, 1:]
    return float((z * z[neighbours].mean(axis=1)).mean())


def km(g):
    return np.c_[g.lat * 111, g.lon * 111 * np.cos(np.radians(g.lat.mean()))]


def evidence(d, f, p, draws=200, seed=7):
    """Weather noise against signal for grid-cell differences, the sand penalty, and spatial clustering. Years are resampled jointly across cells."""
    rng = np.random.default_rng(seed)
    by, ry = np.arange(1991, 2021), np.arange(2041, 2061)
    cells, soils, space = [], [], []
    for (region, crop), a in d.groupby(["region", "crop"]):
        mix = a.groupby(["cell_id", "soil_class_soilmap"]).area_ha.sum().rename("mix").reset_index().assign(crop=crop, region=region, farm_id="none", clay=30.0, irr=0.0)
        for s in SOILS:
            mix["soil_" + s] = (mix.soil_class_soilmap == s).astype(float)
        w = mix.merge(p.sets[(p.sets.crop == crop) & p.sets.ssp.isin(["baseline", *STORIES.values()])], on=["cell_id", "soil_class_soilmap", "crop"])
        w["y"] = np.exp(p.long_models[crop].predict_log(w, technology_year=TECH_YEAR))
        w["wy"] = w.y * w.mix
        keys = ["ssp", "run", "year"]
        by_cell = w.groupby(keys + ["cell_id"]).wy.sum().div(w.groupby(keys + ["cell_id"]).mix.sum()).unstack("cell_id")
        by_soil = w.groupby(keys + ["soil_class_soilmap"]).y.mean().unstack("soil_class_soilmap")
        centre = a.groupby("cell_id")[["lat", "lon"]].mean()

        def change(table, ssp, b, r):
            return pd.concat([table.loc[(ssp, "raw")].loc[r], table.loc[(ssp, "delta")].loc[b]]).mean() / table.loc[("baseline", "baseline")].loc[b].mean() - 1

        for story, ssp in STORIES.items():
            point = change(by_cell, ssp, by, ry)
            dev = point - point.mean()
            se = np.std([(lambda c: (c - c.mean()).to_numpy())(change(by_cell, ssp, rng.choice(by, 30), rng.choice(ry, 20))) for _ in range(draws)], axis=0)
            cells.append(dict(region=region, crop=crop, story=story, cells=len(dev), change_pct=point.mean() * 100, between_cell_sd_pct=dev.std() * 100, weather_noise_se_pct=se.mean() * 100,
                              signal_share=1 - (se ** 2).mean() / dev.var(), neighbour_similarity=moran(dev.to_numpy(), km(centre.loc[dev.index]), k=min(4, len(dev) - 1))))
            if {"sand", "clay"} <= set(by_soil.columns):
                gap = [(lambda c: c["sand"] - c["clay"])(change(by_soil, ssp, rng.choice(by, 30), rng.choice(ry, 20))) for _ in range(draws)]
                c = change(by_soil, ssp, by, ry)
                soils.append(dict(region=region, crop=crop, story=story, sand_pct=c["sand"] * 100, clay_pct=c["clay"] * 100, gap_pct=(c["sand"] - c["clay"]) * 100, gap_low_pct=np.percentile(gap, 5) * 100, gap_high_pct=np.percentile(gap, 95) * 100))
    for region, g in f.drop_duplicates("farm_id").groupby("region"):
        xy = km(g)
        for col in ["dry_share", "area_ha"]:
            chance = [moran(rng.permutation(g[col].to_numpy()), xy) for _ in range(draws)]
            space.append(dict(region=region, measure=col, farms=len(g), neighbour_similarity=moran(g[col].to_numpy(), xy), chance_high=np.percentile(chance, 97.5)))
    return {"map_evidence_grid_cells.csv": pd.DataFrame(cells), "map_evidence_sand_gap.csv": pd.DataFrame(soils), "map_evidence_farm_clustering.csv": pd.DataFrame(space)}


def natural_earth(folder):
    """Writes the simplified coastline, and prints how the synthetic positions sit against real land. The map uses no other geography."""
    import shapely
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union

    def read(name):
        with open(f"{folder}/ne_10m_{name}.geojson") as fh:
            return json.load(fh)["features"]

    features = []
    land = read("land")
    for region, bounds in BOX.items():
        b = box(*bounds)
        clip = unary_union([shape(x["geometry"]).buffer(0).intersection(b) for x in land if shape(x["geometry"]).intersects(b)]).simplify(0.004)
        features.append(dict(type="Feature", properties=dict(region=region), geometry=json.loads(json.dumps(mapping(shapely.set_precision(clip, 0.001))))))
    with open(OUT / "map_land.json", "w") as fh:
        json.dump(dict(type="FeatureCollection", features=features), fh, separators=(",", ":"))
    points = pd.read_csv(DATA / "01_master/parcels.csv")
    xy = shapely.points(points.lon, points.lat)
    points["region"] = np.where(points.farm_id.str.startswith("S"), "SE_SKANE", "FI_SW")
    all_land = unary_union([shape(x["geometry"]).buffer(0) for x in land if shape(x["geometry"]).intersects(box(10, 54, 26, 63))]).intersection(box(10, 54, 26, 63))
    lakes = unary_union([shape(x["geometry"]).buffer(0) for x in read("lakes") if shape(x["geometry"]).intersects(box(10, 54, 26, 63))])
    points["off_land"] = ~shapely.contains(all_land, xy)
    points["in_lake"] = shapely.contains(lakes, xy)
    print(points.groupby("region")[["off_land", "in_lake"]].sum())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--natural-earth")
    args = parser.parse_args()
    predictor = Predictor()
    fields = all_fields(predictor)
    effects = soil_effects(fields, predictor)
    farm_rows = farms(fields, effects)
    effects.round(5).to_csv(OUT / "map_soil_effects.csv", index=False)
    farm_rows.round({"lat": 5, "lon": 5, "area_ha": 2, "dry_ha": 2, "planned_ha": 2, "planned_dry_ha": 2, "change_below_2c": 5, "change_current_policies": 5, "dry_share": 4}).to_csv(OUT / "map_farms.csv", index=False)
    for name, table in evidence(fields, farm_rows, predictor).items():
        table.round(3).to_csv(OUT / name, index=False)
        print(name, table.round(2).to_string(), sep="\n")
    if args.natural_earth:
        natural_earth(args.natural_earth)
