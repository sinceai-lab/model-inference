# Context Broker handoff: what the yield models need

**The broker sends one thing: daily weather per grid cell, as NGSI-LD `WeatherObserved` notifications.** The backend does the rest: it stores the days, calculates the season features, adds the field details and calls the model.

```text
Context Broker ── daily weather (NGSI-LD) ──> POST /notify on the backend
                                                │ stores the day
                                                │ calculates 16 season features
                                                │ adds farm, soil and irrigation
                                                ▼
                                   cache/models.pkl ──> yield prediction (t/ha)
```

The data is synthetic. Status: the example notification passes the backend's parser, but nothing here has been tested against a real broker.

## What the broker must send

One reading per grid cell per day.

| What | Attribute | Unit (`unitCode`) | Required? | Model data column |
|---|---|---|---|---|
| Grid cell | `cellId`, or in the entity id | `GF0104` style | One of these three | `cell_id` |
| Location | `location`, a GeoJSON point (longitude, latitude) | Degrees | Include it: the Smart Data Models schema requires it | Used to find `cell_id` |
| Day | `dateObserved` | ISO date | Yes | `date` |
| Mean temperature | `temperature` | °C (`CEL`) | Needed for full accuracy | `tmean_c` |
| Maximum temperature | `temperatureMax` | °C (`CEL`) | Needed for full accuracy | `tmax_c` |
| Rain, daily total | `precipitation` | mm (`MMT`) | Needed for full accuracy | `precip_mm` |
| Potential evaporation, daily total | `referenceEvapotranspiration` | mm (`MMT`) | Preferred | `pet_mm` |

- **Partial readings:** the backend accepts them, fills what's missing and reports it, so one missing value doesn't lose a day.
- **Custom attributes:** `cellId`, `temperatureMax` and `referenceEvapotranspiration` aren't part of the Smart Data Models `WeatherObserved` schema, so they're extra attributes on the entity.
- **Grid cells:** the 84 valid IDs and their locations are in `data/01_master/climate_grid_cells.csv` in the challenge package. If an entity has no cell ID, its `location` must fall within range of a cell.
- **Season coverage:** the models use day of year 60–300, which is 1 March to 27 October (29 February to 26 October in a leap year). Send every day from 1 March if possible. Gaps of up to 3 days get interpolated temperature and evaporation, and other missing days get typical weather for that cell. Both are reported, and early-season predictions rely mostly on typical weather.
- **Evaporation:** if it's left out, the backend estimates it from temperature and latitude (Hargreaves). This needs `temperatureMax`.
- **Temperature periods:** values must be daily. Hourly sensor readings need aggregating first, because a single reading isn't a mean or a maximum.

### Examples in this folder

| File | What it is |
|---|---|
| `notification_example.json` | One notification, as the backend expects to receive it |
| `subscription_example.json` | A sample subscription; replace `BACKEND_HOST` and `@context` |
| `daily_weather_example.csv` | A full season for one cell (241 days), as flat values to send |

Example notification:

```json
{
  "id": "urn:ngsi-ld:Notification:example-0001",
  "type": "Notification",
  "subscriptionId": "urn:ngsi-ld:Subscription:apetit-weather",
  "notifiedAt": "2027-06-16T06:00:00Z",
  "data": [{
    "id": "urn:ngsi-ld:WeatherObserved:GF0104",
    "type": "WeatherObserved",
    "dateObserved": {"type": "Property", "value": {"@type": "DateTime", "@value": "2027-06-15T00:00:00Z"}},
    "cellId": {"type": "Property", "value": "GF0104"},
    "location": {"type": "GeoProperty", "value": {"type": "Point", "coordinates": [22.625, 60.975]}},
    "temperature": {"type": "Property", "value": 14.4, "unitCode": "CEL"},
    "temperatureMax": {"type": "Property", "value": 21.3, "unitCode": "CEL"},
    "precipitation": {"type": "Property", "value": 0.0, "unitCode": "MMT"},
    "referenceEvapotranspiration": {"type": "Property", "value": 4.62, "unitCode": "MMT"}
  }]
}
```

### Subscription rules

- **Content type:** send it as `POST /ngsi-ld/v1/subscriptions` with `Content-Type: application/ld+json`. Its `@context` must be the one your weather entities use, or `WeatherObserved` won't match.
- **Don't watch only `dateObserved`:** a correction to a day's values doesn't change the date, so it might never fire. The example leaves `watchedAttributes` out.
- **Don't set `throttling` or `timeInterval`:** each can drop days, which then get filled with typical weather.
- **Update a day's attributes together:** a notification holds the entity as it stands, so a new date sent apart from its values would pair them wrongly.

## Which model infers what

All models are in one file, `cache/models.pkl`, rebuilt by `src/run_all.py`. It isn't in the repo. Each model predicts `log(yield)`, which is converted back to t/ha.

| Crop | Regions | Key, 2027–2031 | Key, after 2031 | Example result |
|---|---|---|---|---|
| Pea | Finland and Sweden, one shared model | `models["pea"]` | `long_models["pea"]` | 4.056 (Finland), 2.801 (Sweden) |
| Turnip rape | Finland | `models["turnip_rape"]` | `long_models["turnip_rape"]` | 1.056 |
| Potato | Finland | `models["potato"]` | `long_models["potato"]` | 22.025 |
| Carrot | Finland | `models["carrot"]` | `long_models["carrot"]` | 65.849 |
| Spinach | Finland | `models["spinach"]` | `long_models["spinach"]` | 25.162 |

## What each model receives

The backend builds this row, and the broker doesn't send it. `model_input_examples.csv` has one complete row per model, plus Swedish pea. Each row was checked: loaded from the CSV and run through the saved model, it matches the submitted C1 prediction to within 0.002 t/ha. `python build_handoff_examples.py` in `src/` regenerates and rechecks them after retraining, so these predictions change whenever the models do, while the broker format doesn't.

| Column | Meaning | Comes from |
|---|---|---|
| `farm_id` | Farm | `parcels.csv` |
| `region` | `FI_SW` or `SE_SKANE` | Farm ID |
| `year` | Season, for the technology trend | Notification date |
| `clay` | Clay % | `parcels.csv` |
| `irr` | Irrigated share, 0 to 1 | Farm's history for that crop |
| `soil_silt`, `soil_fine_sand`, `soil_sand`, `soil_organic` | Soil type, 0 or 1. Clay soil is all zeros | `parcels.csv` |
| `sow_doy`, `mat_doy`, `gdd_gap` | Estimated sowing and maturity | Daily weather |
| `stress_early`, `stress_sens`, `stress_late` | Drought stress by crop stage | Daily weather and soil |
| `hot_sens`, `hot_season`, `t_sens` | Heat | Daily weather |
| `rain_postsow`, `wet_postsow`, `rain_preharv`, `rain_season` | Rain at key times | Daily weather |
| `blight_days`, `may_t`, `pet_season` | Warm wet days, May temperature, season evaporation | Daily weather |

The CSV also has reference columns the model doesn't read: `model_file`, `model_group`, `model_key`, `parcel_id`, `cell_id`, `soil_clay` and `expected_yield_t_ha`.

`daily_weather_example.csv` is the weather behind the first CSV row. Running it through `season_features()` in `src/features.py` reproduces that row's 16 weather features.

To reproduce a prediction, from `src/`:

```python
import pickle, numpy as np, pandas as pd

models = pickle.load(open("../cache/models.pkl", "rb"))["models"]
rows = pd.read_csv("../docs/cb_handoff/model_input_examples.csv")
row = rows.iloc[[0]]
print(np.exp(models[row.model_key.iloc[0]].predict_log(row))[0])  # about 4.056 t/ha
```

## Questions for the broker owner

1. **Network:** where does the broker run? `http://127.0.0.1:8600/notify` won't work from inside Docker or from another machine, so the backend will need a reachable address.
2. **Evaporation:** can the broker supply it, or should the backend always estimate it?
3. **Location:** will entities carry our cell IDs, or real coordinates? Coordinates must fall within range of our grid.
4. **Entity ids:** one entity per cell updated daily, or one per day? The parser accepts both, but a single daily entity relies on one notification per update.
5. **Backfill:** can the broker replay days from 1 March when a subscription starts?
6. **Representation and context:** the backend accepts normalized and keyValues/concise entities. Which will the broker send, and with which `@context`?
7. **Predictions:** should the backend write `YieldPrediction` entities back to the broker? If so, subscriptions must watch `WeatherObserved` only, to prevent notification loops.
