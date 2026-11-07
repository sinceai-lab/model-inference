# Connecting the Context Broker

For the broker owner. **`docs/cb_handoff/README.md` is the contract** for what the broker sends and what the models need, and this page doesn't replace it. This page adds how the backend treats the data, what it writes back, and how to switch from the mock to a real broker. Where the two differ, the difference is listed under [Differences from the handoff examples](#differences-from-the-handoff-examples).

Checked against ETSI GS CIM 009 V1.9.1 (2025-07) and the Smart Data Models `WeatherObserved` schema. **Nothing has been tested against a real broker yet**, only against the mock in `service/mock_broker.py`. All data is synthetic.

## What the broker sends

One `WeatherObserved` entity per grid cell per day, posted to `POST /notify` on the backend (port 8600).

| What | Attribute | Unit (`unitCode`) | Status | Model column |
|---|---|---|---|---|
| Grid cell | `cellId`, or in the entity id | `GF0104` style | Required | `cell_id` |
| Day | `dateObserved` | ISO date or date-time | Required | `date` |
| Mean temperature, daily | `temperature` | °C (`CEL`) | Required | `tmean_c` |
| Maximum temperature, daily | `temperatureMax` | °C (`CEL`) | Required | `tmax_c` |
| Rain, daily total | `precipitation` | mm (`MMT`) | Required | `precip_mm` |
| Potential evaporation, daily total | `referenceEvapotranspiration` | mm (`MMT`) | Preferred | `pet_mm` |

"Required" means the estimate needs it to be fully based on observations. The parser still accepts a reading with some of these missing, as described under [What happens to imperfect data](#what-happens-to-imperfect-data).

The backend also accepts these, so existing data can be sent as it is:

| Attribute | Notes |
|---|---|
| `temperatureMin` | Improves the evaporation estimate when `referenceEvapotranspiration` is absent |
| `airTemperatureTSA` | The Smart Data Models aggregate. `maxOverTime`, `minOverTime`, and either `avgOverTime` (common schema) or `averageValue` (`WeatherObserved` spec), as the two sources name it differently |
| `location` | GeoJSON Point, used to find the cell when there's no `cellId` |
| `KEL`, `FAH`, `CMT`, `MTR` | Other units are converted. Any other `unitCode` rejects the entity rather than risk a wrong value. No `unitCode` means °C or mm |

**Against Smart Data Models:** `temperature` and `precipitation` (L/m², the same as mm) are in `WeatherObserved`. `temperatureMax`, `cellId` and `referenceEvapotranspiration` aren't, so they're our own attributes. The schema also requires `location`, which `notification_example.json` leaves out, so include it if your broker validates against the schema. `temperature` there means a reading, not a daily mean, so values must be aggregated to the day before they're sent.

**Representations:** normalized, concise and keyValues/simplified are all accepted, as `application/json` or `application/ld+json`, with `@context` in the body or a `Link` header. Remote contexts are recorded but not fetched. Attribute names are resolved through inline context terms, then the last segment of an expanded URI (`https://smartdatamodels.org/dataModel.Weather/precipitation` becomes `precipitation`). `application/geo+json` notifications are refused.

## Evaporation (PET) if the broker lacks it

Leave `referenceEvapotranspiration` out and the backend estimates it per day with FAO-56 Hargreaves, from temperature and the cell's latitude. On the package's 1991–2026 weather this reproduces `pet_mm` to about 0.006 mm/day, because the package computes it that way. Real weather won't be that close.

| Broker sends | PET used | `pet_source` |
|---|---|---|
| `referenceEvapotranspiration` | As sent | `reported` |
| `temperature`, `temperatureMax`, `temperatureMin` | Hargreaves | `hargreaves` |
| `temperature`, `temperatureMax` | Hargreaves, taking the minimum as 2 × mean − max | `hargreaves` |
| Less than that | The cell's 1991–2020 average for that day (mean error about 0.28 mm/day), and the day counts as partial | none |

## How a location maps to a cell

There are 84 cells on a 0.25° grid, in `data/01_master/climate_grid_cells.csv` of the challenge package. The backend looks in this order:

1. A `cellId` attribute (`gridCell` and `refGridCell` also work). An unknown ID rejects the entity.
2. A cell ID inside the entity id, such as `urn:ngsi-ld:WeatherObserved:GF0104`.
3. The nearest cell to a `location` Point, if within 0.18° (half the grid's diagonal). Further away rejects the entity.

Parcels map to cells the same way, by nearest cell, so a cell's reading updates all of its parcels.

## Subscription

`docs/cb_handoff/subscription_example.json`, with the two changes we recommend below:

```json
{
  "id": "urn:ngsi-ld:Subscription:apetit-weather",
  "type": "Subscription",
  "description": "Daily weather for the Apetit yield backend",
  "entities": [{"type": "WeatherObserved"}],
  "notification": {
    "format": "normalized",
    "endpoint": {"uri": "http://BACKEND_HOST:8600/notify", "accept": "application/json"}
  },
  "@context": "THE_CONTEXT_YOUR_WEATHER_ENTITIES_USE"
}
```

Send it as `POST /ngsi-ld/v1/subscriptions` with `Content-Type: application/ld+json`. The expected answer is 201 with a `Location` header. `python -m service.cli subscribe --dry-run` prints the body, and `--watch dateObserved` adds the `watchedAttributes` of the handoff example.

- **Watch weather only.** Don't include `YieldPrediction`. The CLI refuses to, and the backend ignores those entities if they arrive anyway.
- **Don't set `throttling` or `timeInterval`.** Each can drop days, which then get filled with typical weather. Per the spec, each update should give its own notification.
- **Update all of a day's attributes at once.** A notification holds the entity as it stands, so a date updated apart from its values would store the previous day's values under the new date. A later update corrects it only if a notification fires for it.

### Handoff examples

`docs/cb_handoff` is the contract. Two details differ on purpose: the backend accepts partial readings and reports what it filled, and `POST /predict` requires `soil_clay` even though the model doesn't read it.

`tests/test_handoff_contract.py` runs the examples, using a copy in `tests/fixtures/cb_handoff`.

## Notification

`docs/cb_handoff/notification_example.json`, in full:

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
    "temperature": {"type": "Property", "value": 14.4, "unitCode": "CEL"},
    "temperatureMax": {"type": "Property", "value": 21.3, "unitCode": "CEL"},
    "precipitation": {"type": "Property", "value": 0.0, "unitCode": "MMT"},
    "referenceEvapotranspiration": {"type": "Property", "value": 4.62, "unitCode": "MMT"}
  }]
}
```

The same reading in keyValues:

```json
{"id": "urn:ngsi-ld:WeatherObserved:GF0104", "type": "WeatherObserved", "dateObserved": "2027-06-15T00:00:00Z", "cellId": "GF0104", "temperature": 14.4, "temperatureMax": 21.3, "precipitation": 0.0, "referenceEvapotranspiration": 4.62}
```

`subscriptionId`, `notifiedAt` and `data` are required. The backend answers 200 with a per-entity report whenever the envelope is usable, even if every entity in it was bad, so one bad reading can't get the subscription marked as failed.

## What happens to imperfect data

| Case | What happens | Reported as |
|---|---|---|
| Not JSON, or `NaN` in the JSON | Refused, nothing stored | 400, and in `recent_rejected` |
| No `subscriptionId`, `notifiedAt` or `data`, or `data` isn't an array | Refused, nothing stored | 400, and in `recent_rejected` |
| Other content type | Refused, nothing stored | 415 |
| Body over 10 MB | Refused, nothing stored | 413 |
| Bad entity in a batch: bad date, unit, cell, non-numeric or implausible value, maximum below mean | That entity is dropped and the rest are kept | 200, `rejected` with reason and index |
| Other entity type, including `YieldPrediction` and `WeatherForecast` | Ignored, never treated as an observation | 200, `ignored` |
| Exact duplicate | Ignored, no recomputation or write-back | `readings.duplicate` |
| Same day, different values | The notification with the latest `notifiedAt` wins, and estimates are recomputed. Attributes it doesn't carry keep their stored values | `readings.corrected` |
| Same day, different values, older `notifiedAt` than what's stored | Ignored | `readings.stale` |
| Out-of-order days | Stored by date. The whole season is recomputed, so arrival order doesn't change the final estimate. The estimate is dated by the latest day received | `readings.new` |
| Missing days up to the latest reading | Filled: up to 3 days in a row get interpolated temperature and PET with typical rain, longer gaps get typical weather | `filled_gap_days` |
| Days after the latest reading | Filled with the cell's 1991–2020 day-of-year averages | `filled_future_days` |
| Missing values on a day | The day is kept and the missing value filled from typical weather | `partial_days` |
| Day outside the season window | Stored, no recomputation | `readings.out_of_season` |
| Cell with no contract crop that season | Stored, no estimates | `predictions_written: 0` |
| Estimate calculation fails | The reading is kept, and the next notification tries again | 200, `prediction_errors` |

`GET /observations/status` shows observed and filled days per season, missing days and recent rejects.

### Threshold counts on filled days

Averaging across years smooths out the daily weather, so counting threshold days on the averages goes wrong. The average July day is warm with over 1 mm of rain, so most July–August days would count as warm and wet: about 50 against about 16 in a real year, which is far outside what the model trained on. The averages are still used for temperature, rain and PET, but for hot, wet and warm-wet day counts each filled day adds its historical chance of passing the threshold. Setting `LIVE_FILL_COUNTS=plain` turns this off, and `outputs/live_season_replay.csv` compares both.

## What the backend writes back

Off unless `CB_URL` is set. Estimates are sent in the background with `POST /ngsi-ld/v1/entityOperations/upsert?options=update`, retrying on failure, so a slow or absent broker never holds up a notification. There's one entity per parcel, crop and season, holding the current estimate. The history stays in `GET /predictions`.

| Attribute | Meaning |
|---|---|
| `id` | `urn:ngsi-ld:YieldPrediction:<parcel>:<crop>:<year>` |
| `type` | `YieldPrediction` |
| `refParcel`, `refGridCell` | Relationships to `urn:ngsi-ld:AgriParcel:<parcel>` and `urn:ngsi-ld:ClimateGridCell:<cell>` |
| `cropName`, `seasonYear` | What it predicts |
| `estimatedYield` | t/ha in `unitText`, with `observedAt` set to the latest weather day |
| `baselineYield` | Farm average in t/ha, if the farm has one |
| `predictionLabel` | Always `estimate` |
| `modelName`, `modelVersion` | Such as `models[pea]`, and the start of the hash of `cache/models.pkl` |
| `observedDays`, `filledDays`, `filledGapDays`, `filledFutureDays` | Of the 241 days in the window |
| `asOfDate`, `computedAt` | Latest weather day used, and when it was calculated |

**Loop prevention:** the backend only writes `YieldPrediction` and only reacts to weather types, and a duplicate reading writes nothing. If a subscription on `YieldPrediction` is created by mistake, the notifications are ignored and it ends after one round. `tests/test_mock_broker.py` tests this.

## Switching from the mock to the real broker

1. Create your weather entities as in the table above.
2. Start the backend without the mock, setting `CB_URL` only if you want estimates written back:
   ```bash
   CB_URL=http://YOUR_BROKER:1026 uvicorn service.api:app --host 127.0.0.1 --port 8600
   ```
   `CB_TENANT`, `CB_TOKEN` (sent as a bearer token) and `CB_CONTEXT` (the `@context` of `YieldPrediction`, by default the NGSI-LD core context) are optional.
3. Create the subscription on your broker:
   ```bash
   python -m service.cli --broker http://YOUR_BROKER:1026 subscribe --id urn:ngsi-ld:Subscription:apetit-weather --notify-url http://BACKEND_HOST:8600/notify --context YOUR_CONTEXT_URL
   ```
4. Publish one day's weather, then check it arrived:
   ```bash
   python -m service.cli status
   python -m service.cli observations --cell GF0104
   python -m service.cli predictions --cell GF0104
   ```

The code needs no change. **One thing goes beyond a URL:** the backend binds to 127.0.0.1, so a broker in Docker or on another machine can't reach it until that's opened up (question 1).

The mock speaks the same `/ngsi-ld/v1` paths and enforces the same `@context` rules. It doesn't evaluate `q` or `geoQ`, doesn't support `timeInterval`, doesn't resolve contexts, keeps its state in memory, and treats a watched attribute as changed whenever an update includes it. A real broker's behaviour on those points is untested.

## Open questions for the broker owner

1. **Network:** where does the broker run? `http://127.0.0.1:8600/notify` won't work from inside Docker or from another machine, so the backend needs a reachable address.
2. **Which broker and version?** Orion-LD, Scorpio or Stellio, and which NGSI-LD version. Any tenant or authentication?
3. **`@context`:** which one will the entities use? The subscription has to use the same one, or `WeatherObserved` won't match.
4. **`watchedAttributes`:** does an update that repeats `dateObserved` with new values fire a notification on your broker? If not, leave it out so corrections arrive.
5. **Evaporation:** can the broker supply it, or should the backend always estimate it?
6. **Location:** will entities carry our cell IDs, or real coordinates? Coordinates must fall within 0.18° of a cell.
7. **Entity ids:** one entity per cell updated daily, or one per day? Both parse. With one per cell, days are only safe if each update fires its own notification and all of a day's attributes change together.
8. **Daily values:** who aggregates hourly sensors to daily mean, maximum and total? Which day does a value belong to, and in which time zone? The backend uses the date as written in `dateObserved`, without converting it.
9. **Backfill:** can the broker replay days from 1 March when a subscription starts? If not, the days before it are filled with typical weather.
10. **Representation:** normalized, concise or keyValues? All work, and the example uses normalized.
11. **Predictions:** do you want `YieldPrediction` entities written back, and are the attribute names above acceptable? They aren't from a Smart Data Model.
