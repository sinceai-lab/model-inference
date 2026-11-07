# Insights API

Read-only endpoints that give `apetit-ui` what the Streamlit viewer shows in **Risk and advice**, **Farm and fields**, **Map**, **All crops**, **Try the model** and **Can we trust this?**. They live in the same FastAPI app as the live backend (`service/api.py`, port 8600), so the UI keeps one upstream.

**The rule:** every number here comes from the same file or function that `app.py` and `map_tab.py` use, computed the same way, so a page in `apetit-ui` and the Streamlit tab always agree. The UI only formats and draws. If a figure needs arithmetic, the arithmetic belongs here, not in TypeScript.

**All data is synthetic.** Every response carries `basis`, so the UI can label it.

---

## 1. Where it lives

| File | Purpose |
|---|---|
| `service/insights.py` (new) | `Insights` class: loads `outputs/*.csv`, reloads when a file changes, and builds each response. No web code, so an MCP server can reuse it. |
| `service/insights_api.py` (new) | `APIRouter(prefix="/insights")` with the routes below. Included from `service/api.py` with one added line: `app.include_router(insights_router)`. |
| `service/api.py` | Only that `include_router` line, and `app.state.insights = Insights(app.state.live.engine)` in `lifespan`. `POST /predict/field` is unchanged. |
| `tests/test_insights.py` (new) | Checks each endpoint against the same pandas expression `app.py` uses (section 8). |

Imports come from `src/` exactly as `app.py` does: `advisor.{CONFIDENCE, STORIES, THEME_ORDER, advice, field_table, load_outputs, season_summary, themes}`, `backtest.metrics`, `config.OUT`. `i18n.py` is **not** imported, because it imports Streamlit. English text is produced by the small formatter in section 2.4, which copies the English branch of `i18n.num` and `i18n.eur`.

---

## 2. Shared conventions

Numbers in the JSON examples show the shape only. Some are copied from `outputs/`, others are made up.

### 2.1 Codes and labels

| Thing | Codes | English labels (as in `app.py`) |
|---|---|---|
| Region | `FI_SW`, `SE_SKANE` | Finland, Sweden |
| Crop | `pea`, `turnip_rape`, `potato`, `carrot`, `spinach` | Pea, Turnip rape, Potato, Carrot, Spinach |
| Climate story | `below_2c` (→ `ssp126`), `current_policies` (→ `ssp585`) | Below 2 °C, Hothouse |
| Cost scenario | `baseline`, `ssp126`, `ssp585` | Today's climate, Below 2 °C, Hothouse |
| Backtest | `loyo`, `forward` | Leave one season out, Predict 2022–2026 from earlier seasons |
| Region and crop pairs with advice | the 6 keys of `advisor.CONFIDENCE` | Sweden has pea only |

Finland and Sweden are separate operations. **No endpoint returns a figure that combines the two regions.** Totals are always per region.

### 2.2 `basis` block (on every response)

```jsonc
"basis": {
  "kind": "batch",                 // "batch": read from outputs/*.csv (written by src/run_all.py or src/build_map_data.py)
                                   // "model": computed at request time from cache/models.pkl and the weather cache (field tables, what-if)
                                   // never "live": in-season estimates stay on /predictions
  "label": "Scenario results, 2041–2060 against 1991–2020",   // plain-English caption the UI shows
  "model_version": "5cf88f338cb8", // sha256(models.pkl)[:12], same as /health models.version and YieldPrediction.modelVersion
  "sources": [{"file": "C2_detail_with_uncertainty.csv", "generated_at": "2026-11-07T15:26:59Z"}],  // file mtime, UTC; basenames only, never paths
  "stale_vs_model": false          // true when models.pkl is newer than any listed file: rerun the pipeline before trusting it
}
```

Each endpoint below lists its `sources`. Files in the challenge package (for example `transition_scenarios.csv`) are listed as `package/05_scenarios/transition_scenarios.csv`.

### 2.3 Units

Shares and changes are **fractions** (`0.057` = 5.7 %), except fields whose name ends in `_pct`, which keep the CSV's percent units (`mean_yield_change_pct: 0.567` means +0.567 %). Yields are t/ha, areas ha, money € a year unless the name says otherwise, days are days. Keys are snake_case, as in the rest of this service; `apetit-ui` camelCases them in its server.

### 2.4 Text

Plain-language sentences (advice rules, "why" lines, risk sentences) are returned as:

```jsonc
{"code": "bad_years", "template": "The model's chance of a bad year rises from {today} to {future}. ...", "values": {"today": [0.094, ".0%"], "future": [0.131, ".0%"]}, "text": "The model's chance of a bad year rises from 9% to 13%. ..."}
```

`text` is English, formatted with `format(value, spec)` and, for `"eur"`, `f"{'-' if v < 0 else ''}€{abs(v):,.0f}"`, matching `i18n` in English. `template` and `values` are kept so a Finnish UI can format them itself.

### 2.5 Errors

| Status | When | Body |
|---|---|---|
| 422 | Unknown or badly formed query parameter (wrong code, year out of range, extra parameter) | The existing `clear_422` shape: `{detail, missing, invalid}` |
| 404 | Valid codes but nothing there: a region and crop pair outside `CONFIDENCE`, unknown farm or parcel, a farm that doesn't grow the crop | `{detail}` |
| 503 | An outputs file is missing or has never loaded | `{detail: "outputs/C3_euro_risk.csv is missing. Run src/run_all.py.", file}` |

Unknown query parameters are refused (422), so the UI's whitelist and this one stay in step.

### 2.6 Caching and reload

- `Insights.frame(name)` holds one `DataFrame` per file with its `(st_mtime_ns, st_size)`. Each request does an `os.stat` (microseconds) and rereads the file only when the stamp changed, like `Engine.refresh` does for `models.pkl`.
- A file that fails to parse **keeps the last good copy** and is reported in `/insights/meta` as `load_error`. A file that has never loaded gives 503.
- `load_outputs()` from `advisor.py` is the source of the `results` dict that `advice`, `themes` and `season_summary` take. It reads nine files at once, so it's rebuilt whenever any of those nine change (the stamp is the tuple of the nine stamps).
- `field_table(predictor, farm, crop)` costs tens of milliseconds and reads the model. Its result is kept in an LRU of 1,024 entries keyed by `(engine.version, farm_id, crop)`, so a new `models.pkl` clears it in effect. It uses `engine.predictor`, the same `Predictor` that `/predict/field` already shares.
- Responses send `Cache-Control: max-age=60` and an `ETag` of the source stamps plus model version. The UI may revalidate with `If-None-Match` (304).
- Everything is computed in FastAPI's threadpool (plain `def` routes), like `/predict/field`.

---

## 3. Endpoint list

| Method and path | Feeds (Streamlit) | Feeds (apetit-ui) |
|---|---|---|
| `GET /insights/meta` | — | every insight page footer, Data & provenance |
| `GET /insights/options` | all selectors | all insight pages |
| `GET /insights/advice?region&crop&story` | Risk and advice; Map region panel | Risk & advice; Map climate panel |
| `GET /insights/policy` | Risk and advice → Policy costs | Risk & advice |
| `GET /insights/outlook?region&crop` | All crops → Forecast 2027–2031 | Outlook |
| `GET /insights/climate-risk?scenario` | All crops → Yield change by 2041–2060 | Outlook |
| `GET /insights/euro-risk` | All crops → Cost of replacing shortfalls | Outlook, Risk & advice |
| `GET /insights/farms?region&crop` | Map → farm dots and "Farms to contact first" | Map climate layer, Risk & advice |
| `GET /insights/soil-effects?region&crop` | Map legend, field colours, "why" | Map, Farm |
| `GET /insights/farms/{farm_id}?crop&story` | Farm and fields; Map farm panel | Farm → Climate outlook |
| `GET /insights/fields/{parcel_id}?crop&story` | Map field panel | Farm → field drawer |
| `POST /insights/what-if` | Try the model | Try the model |
| `GET /insights/trust?test` | Can we trust this? → headline, by crop, pea models, scorer | Model trust |
| `GET /insights/trust/seasons?region&crop&test[&farm_id]` | Can we trust this? → Season by season, Check a single farm | Model trust |
| `GET /insights/trust/live-replay?test` | README live table (not in Streamlit) | Model trust, Live season note |
| `GET /insights/trust/corrections` | Can we trust this? → How the yield data was cleaned | Model trust, Data & provenance |

`POST /predict/field` stays as it is and is documented in section 6.1.

---

## 4. Meta and options

### 4.1 `GET /insights/meta`

No parameters.

```jsonc
{
  "model_version": "5cf88f338cb8",
  "models_file_date": "2026-11-07T14:15:38Z",          // models.pkl mtime
  "model_load_error": null,                             // engine.load_error
  "files": [                                            // every file this API reads, in this order
    {"file": "C2_detail_with_uncertainty.csv", "generated_at": "2026-11-07T15:26:59Z", "rows": 18, "load_error": null, "stale_vs_model": false},
    ...
  ],
  "synthetic": true,
  "disclaimer": "All farms, fields and yields are synthetic (Apetit × Since AI 2026 package). These are not findings about real farms.",
  "basis": {...}
}
```

Files: `C1_forecast_comparison.csv`, `C2_detail_with_uncertainty.csv`, `C2_bad_year_check.csv`, `C3_euro_risk.csv`, `C3_irrigation_evidence.csv`, `C3_irrigation_se_within_farm.csv`, `advisor_drivers.csv`, `advisor_season_shift.csv`, `backtest_predictions.csv`, `backtest_pea_models.csv`, `backtest_summary.csv`, `live_season_replay.csv`, `map_farms.csv`, `map_soil_effects.csv`, `yield_corrections_log.csv`, and the package's `transition_scenarios.csv`, `farm_survey_fi.csv`, `foodhills_odlingsdata_se.csv` (read by `advisor.policy_paths` and `advisor.input_use`).

### 4.2 `GET /insights/options`

| Param | Values | Effect |
|---|---|---|
| `region` | `FI_SW`, `SE_SKANE` (optional) | adds `farms` for that region |
| `crop` | crop code (optional, needs `region`) | filters `farms` to growers of that crop |
| `farm_id` | `^[FS]\d{4}$` (optional) | adds `parcels` of that farm |

```jsonc
{
  "regions": [{"code": "FI_SW", "label": "Finland", "crops": ["pea", "turnip_rape", "potato", "carrot", "spinach"]},
              {"code": "SE_SKANE", "label": "Sweden", "crops": ["pea"]}],
  "crops": [{"code": "pea", "label": "Pea"}, ...],
  "stories": [{"code": "below_2c", "label": "Below 2 °C", "ssp": "ssp126", "blurb": "More policy costs, such as carbon and fuel."},
              {"code": "current_policies", "label": "Hothouse", "ssp": "ssp585", "blurb": "More physical risk in the field, though not for every crop."}],
  "advice_pairs": [{"region": "FI_SW", "crop": "turnip_rape", "confidence": "Medium"}, ...],   // advisor.CONFIDENCE, in its order
  "tests": [{"code": "loyo", "label": "Leave one season out"}, {"code": "forward", "label": "Predict 2022–2026 from earlier seasons"}],
  "weather_sets": [                                                                            // app.py WEATHER
    {"code": "history", "label": "Historical weather (1991–2026)", "scenario": "historical", "years": [1991, 2026]},
    {"code": "c1", "label": "SSP2-4.5, the C1 forecast seasons (2027–2031)", "scenario": "ssp245", "years": [2027, 2031]},
    {"code": "low", "label": "SSP1-2.6, low emissions (2041–2060)", "scenario": "ssp126", "years": [2041, 2060]},
    {"code": "middle", "label": "SSP2-4.5, middle emissions (2041–2060)", "scenario": "ssp245", "years": [2041, 2060]},
    {"code": "high", "label": "SSP5-8.5, high emissions (2041–2060)", "scenario": "ssp585", "years": [2041, 2060]}],
  "irrigation": [{"code": "usual", "label": "Farm's usual practice", "share": null, "regions": ["FI_SW", "SE_SKANE"]},
                 {"code": "irrigated", "label": "Irrigated", "share": 1.0, "regions": ["SE_SKANE"]},
                 {"code": "rainfed", "label": "Not irrigated", "share": 0.0, "regions": ["SE_SKANE"]}],
  "irrigation_note": "Only available for Sweden, where 167 farms switch practice. No Finnish farm does, so the effect can't be measured there.",
  "farms": ["F0001", "F0003", ...],               // only with region; sorted. Same rule as app.py: keys of predictor.farm_mean with this crop and the region's prefix (S = Sweden)
  "parcels": [{"parcel_id": "F0001-P01", "area_ha": 3.17, "soil": "clay", "drainage": "subsurface", "cell_id": "GF0104"}, ...],   // only with farm_id; predictor.parcels for the farm, in index order, as the Try tab lists them
  "basis": {"kind": "model", ...}
}
```

Errors: 422 for a bad code; 404 for an unknown `farm_id`.

---

## 5. Risk, advice and outlook

### 5.1 `GET /insights/advice?region=FI_SW&crop=turnip_rape&story=current_policies`

All three are required. `story` picks which story's actions and "why" lines are returned; the metrics, themes and season shift always cover both stories, as the Streamlit tab shows them side by side. Pair outside `CONFIDENCE` → 404.

Mirrors `app.py` lines 154–194 and `map_tab._region_panel` / `_why`.

```jsonc
{
  "region": "FI_SW", "crop": "turnip_rape", "story": "current_policies",
  "confidence": "Medium",                                          // CONFIDENCE[(region, crop)]
  "stories": [                                                     // one per story, below_2c first
    {"story": "below_2c", "label": "Below 2 °C", "ssp": "ssp126",
     "yield_change": -0.012,                                       // risk.mean_yield_change_pct / 100
     "yield_change_low": -0.031, "yield_change_high": 0.004,       // risk.change_min / 100, risk.change_max / 100 ("If one season is dropped")
     "bad_year_chance": 0.09,                                      // risk.p_bad_year ("Yield under 80% of normal")
     "added_import_cost_eur_yr": 12000.0},                         // C3 row ssp == story ssp: added_vs_todays_climate_eur_yr
    {"story": "current_policies", ...}],
  "bad_years_so_far": {"bad_year_chance_today": 0.076, "seen": 1, "seasons": 15},   // C2_bad_year_check: p_bad_today, round(observed_bad * seasons), int(seasons)
  "actions": [                                                     // advisor.advice(results, region, crop, story), in its order
    {"rule": "variety_warmth", "decision": "Variety work", "evidence": "Model estimate",
     "template": "...", "values": {"effect": [0.034, ".1%"]}, "text": "Warmer, shorter seasons cut this crop's yield by about 3.4% in the model. ..."}],
  "actions_note": "Draft rules for advisors to review, not proven recommendations. Each one shows the evidence behind it.",
  "themes": [                                                      // advisor.themes for each story, THEME_ORDER
    {"theme": "Warmth and season timing", "below_2c": -0.012, "current_policies": -0.034},
    {"theme": "Water", ...}, {"theme": "Warm, wet days", ...}],
  "themes_note": "Weather measures rise and fall together, so single measures can't be separated reliably. ...",
  "season_shift": [                                                // advisor.season_summary; "Warm enough to sow" omitted for SE_SKANE
    {"measure": "maturity", "label": "Reaches maturity", "unit": "days earlier than today", "below_2c": 7.7, "current_policies": 14.2},
    {"measure": "sowing", "label": "Warm enough to sow", ...}],
  "season_table": [                                                // rounded as app.py: 1, 1 and 2 decimals
    {"measure": "Days at 27 °C or above", "today": 2.5, "below_2c": 2.9, "current_policies": 5.1},
    {"measure": "Warm, wet days, July–August", ...},
    {"measure": "Drought stress, sensitive stage (0–1)", ...}],
  "season_note": "Calculated from daily weather using our assumed crop thresholds, so read the change rather than the dates. ...",
  "why": [                                                         // map_tab._why for the chosen story: largest theme, then soil spread
    {"code": "largest_theme", "text": "Largest modelled effect: warmth and season timing, -3.4%. ...", "template": "...", "values": {...}},
    {"code": "soil_spread", "text": "Soil moves it: -4.1% on sand, -2.0% on clay. ...", "template": "...", "values": {...}}],
  "basis": {"kind": "batch", "label": "Scenario results, 2041–2060 against 1991–2020", "sources": ["C2_detail_with_uncertainty.csv", "C3_euro_risk.csv", "C2_bad_year_check.csv", "advisor_drivers.csv", "advisor_season_shift.csv", "C3_irrigation_evidence.csv", "C3_irrigation_se_within_farm.csv", "map_soil_effects.csv", "package/05_scenarios/transition_scenarios.csv", ...]}
}
```

### 5.2 `GET /insights/policy`

No parameters. `advisor.policy_paths()` rows, as the three Streamlit policy charts draw them.

```jsonc
{
  "paths": [{"story": "below_2c", "year": 2025, "fertiliser_change": 0.0, "diesel_change": 0.0, "carbon_eur_t": 80.0}, ...],   // n_fertiliser_price_index - 1, diesel_price_index - 1, carbon_price_eur_t
  "inputs": [{"region": "FI_SW", "crop": "pea", "n_kg_ha": 45.0, "diesel_l_ha": 60.0}, ...],                                  // advisor.input_use(): median since 2021
  "note": "Illustrative price paths from the challenge package, not forecasts. Changes are against 2025.",
  "basis": {"kind": "batch", "label": "Illustrative package values", ...}
}
```

### 5.3 `GET /insights/outlook?region=FI_SW&crop=pea`

Both required. Pair not in `C1_forecast_comparison.csv` → 404. Mirrors `app.py` lines 378–387.

```jsonc
{
  "region": "FI_SW", "crop": "pea",
  "history": [{"year": 2012, "actual_t_ha": 3.41}, ...],          // backtest_predictions, test == "loyo", this pair: area-weighted mean of yield_t_ha by year
  "forecast": [{"year": 2027, "model_t_ha": 4.12, "baseline_t_ha": 3.95}, ...],   // C1_forecast_comparison: model_t_ha, package_baseline_t_ha
  "note": "Baseline here is the package's reference method: the farm's survey average since 2016, or a fixed 3.4 t/ha for Swedish peas. ...",
  "warning": "No answers are public for these tasks, so neither method can be scored here. ...",
  "basis": {"kind": "batch", "label": "Forecast 2027–2031, one supplied SSP2-4.5 weather run", "sources": ["C1_forecast_comparison.csv", "backtest_predictions.csv"]}
}
```

### 5.4 `GET /insights/climate-risk?scenario=ssp585`

`scenario` is `ssp126` or `ssp585` (required). Mirrors `app.py` lines 388–399. Rows sorted by `mean_yield_change_pct`, ascending, as the chart.

```jsonc
{
  "scenario": "ssp585", "story": "current_policies", "label": "Hothouse",
  "rows": [{"region": "FI_SW", "crop": "turnip_rape",
            "mean_yield_change_pct": -3.12, "change_min_pct": -4.0, "change_max_pct": -2.1,   // C2 detail: mean_yield_change_pct, change_min, change_max (percent units)
            "bad_year_chance": 0.14,                                                           // p_bad_year
            "baseline_change_pct": 0.0, "baseline_bad_year_chance": 0.10,                      // the package's "no change" baseline, as app.py
            "confidence": "Medium"}, ...],
  "note": "Dot: our estimate. Line: the range when each training season is left out in turn, which is not total uncertainty. ...",
  "basis": {"kind": "batch", "label": "Scenario results, 2041–2060 against 1991–2020", "sources": ["C2_detail_with_uncertainty.csv"]}
}
```

### 5.5 `GET /insights/euro-risk`

No parameters. Mirrors `app.py` lines 400–410, scenarios limited to `COST_SCENARIO` (baseline, ssp126, ssp585).

```jsonc
{
  "totals": [                                       // per region, never summed across regions
    {"region": "FI_SW", "baseline": 480000.0, "ssp126": 455000.0, "ssp585": 530000.0},    // sum of expected_cost_eur_yr by region and ssp
    {"region": "SE_SKANE", ...}],
  "by_crop": [{"region": "FI_SW", "crop": "carrot", "scenario": "baseline", "area_ha": 227, "price_eur_t": 290.0, "premium": 0.4, "baseline_t": 11909,
               "mean_shortfall_t": 457.0, "expected_cost_eur_yr": 52984.0, "bad_year_p90_cost_eur": 183488.0, "added_vs_todays_climate_eur_yr": 0.0}, ...],
  "note": "Expected € a year: shortfall against today's average × 2025 contract price × replacement premium. It counts only the premium, ... The Swedish figures are low confidence.",
  "basis": {"kind": "batch", "label": "Scenario results, 2041–2060, € a year", "sources": ["C3_euro_risk.csv"]}
}
```

---

## 6. Farms, fields and soil

### 6.1 `GET /insights/farms?region=FI_SW&crop=turnip_rape`

Both required (Sweden: pea only). Rows of `map_farms.csv` for the pair, sorted by `planned_dry_ha`, then `dry_ha`, descending, which is the "Farms to contact first" order. The first 8 are the ones the Streamlit map labels.

```jsonc
{
  "region": "FI_SW", "crop": "turnip_rape",
  "farms": [{"farm_id": "F0028", "lat": 61.11, "lon": 21.94,       // synthetic position: area-weighted field centre
             "n_fields": 34, "area_ha": 148.6, "dry_fields": 24, "dry_ha": 113.96, "dry_share": 0.767,   // dry = sand or fine sand
             "planned_fields": 14, "planned_ha": 63.8, "planned_dry_ha": 47.2,                             // planned for this crop in 2027–2028
             "change_below_2c": -0.0023, "change_current_policies": -0.0209}, ...],                        // from the farm's soil mix and the pooled soil figures
  "bands": {"edges": [-0.06, -0.04, -0.02, 0.02, 0.04, 0.06]},     // map_tab.EDGES, so the UI's legend uses the same breaks
  "note": "What the colour means: the model's estimated yield change, from the crop, the climate story and the field's soil. What it doesn't mean: that a place is safer or riskier. ...",
  "basis": {"kind": "batch", "label": "Scenario results, 2041–2060 against 1991–2020", "sources": ["map_farms.csv"]}
}
```

### 6.2 `GET /insights/soil-effects?region=FI_SW&crop=turnip_rape`

Both required. `map_soil_effects.csv` rows for the pair: one figure per soil, pooled across grid cells.

```jsonc
{
  "soils": [{"soil": "sand", "label": "sand", "n_fields": 40, "area_ha": 180.2, "droughty": true,
             "change_below_2c": -0.011, "change_current_policies": -0.041,
             "stress_today": 0.45, "stress_below_2c": 0.46, "stress_current_policies": 0.49}, ...],   // drought stress at the sensitive stage, 0–1
  "note": "These are region-wide figures for each soil, using water capacities we assumed. The soil map is only about 88% accurate.",
  "basis": {"kind": "batch", "sources": ["map_soil_effects.csv"]}
}
```

### 6.3 `GET /insights/farms/{farm_id}?crop=turnip_rape&story=current_policies`

`farm_id` `^[FS]\d{4}$`. `crop` required, `story` required. 404 if the farm doesn't grow the crop (not a key of `predictor.farm_mean`). This is the farm's story: the Farm and fields tab plus `map_tab._farm_panel`.

```jsonc
{
  "farm_id": "F0028", "region": "FI_SW", "crop": "turnip_rape", "story": "current_policies",
  "headline": {
    "yield_change": -0.0209,                     // map_farms change_<story>
    "yield_change_other_story": -0.0023,         // the other story, for the comparison sentence
    "region_yield_change": -0.0312,              // C2 risk for region, crop, story ssp: mean_yield_change_pct / 100
    "dry_share": 0.767, "dry_fields": 24, "n_fields": 34,
    "planned_fields": 14, "planned_dry_ha": 47.2,
    "usual_irrigated_share": 0.0},               // predictor.farm_irr[(farm, crop)], default 0
  "risk": {"code": "farm_risk", "text": "With this farm's soils, the model estimates -2.1% for this crop under Hothouse, against -0.2% under Below 2 °C. The whole region under Hothouse: -3.1%.", ...},
  "why": [                                       // map_tab._farm_panel lines, in order
    {"code": "dry_fields", "text": "24 of 34 fields are on sand or fine sand, which we assume hold the least water. Prioritise them in dry-season guidance.", ...},
    {"code": "planned", "text": "14 fields are planned for this crop in 2027–2028, 47 ha of it on sand or fine sand.", ...},   // only when planned_fields > 0
    {"code": "irrigation", "text": "This farm's usual irrigated share for this crop: 0%.", ...},
    {"code": "largest_theme", "text": "Largest modelled effect: ...", ...}],
  "yield_by_soil": [{"soil": "clay", "yield_today_t_ha": 2.31}, ...],   // field_table grouped by soil, mean yield_today, descending (Farm tab chart)
  "fields": [                                    // advisor.field_table, highest yield_today first
    {"parcel_id": "F0028-P07", "area_ha": 4.8, "soil": "fine_sand", "drainage": "subsurface", "droughty": true,
     "yield_today_t_ha": 2.11,                   // 2025 technology, usual irrigation, 1991–2020 weather mean
     "change_below_2c": -0.004, "change_current_policies": -0.019,       // this field's own grid cell (Farm tab table)
     "soil_change_below_2c": -0.001, "soil_change_current_policies": -0.016,   // pooled soil figure (Map colour); prefer this one
     "stress_today": 0.44, "last_grown": 2024, "next_planned": 2028}],   // null when none
  "fields_warning": "Use the field order as a starting point for discussion. The model was trained on farm averages, so differences between fields come mainly from the soil map, which is only about 88% accurate.",
  "fields_note": "Yields use 2025 technology and the farm's usual irrigation, averaged over 1991–2020 weather. Changes compare 2041–2060 with that average.",
  "actions": [...],                              // advisor.advice(region, crop, story): region-wide draft rules, same shape as 5.1
  "basis": {"kind": "model", "label": "Modelled for 2041–2060 against 1991–2020, 2025 technology", "sources": ["map_farms.csv", "map_soil_effects.csv", "C2_detail_with_uncertainty.csv"], ...}
}
```

### 6.4 `GET /insights/fields/{parcel_id}?crop=turnip_rape&story=current_policies`

`parcel_id` `^[FS]\d{4}-P\d{1,4}$`. 404 if the parcel's farm doesn't grow the crop. Mirrors `map_tab._field_panel`.

```jsonc
{
  "parcel_id": "F0028-P07", "farm_id": "F0028", "region": "FI_SW", "crop": "turnip_rape", "story": "current_policies",
  "soil": "fine_sand", "area_ha": 4.8, "droughty": true,
  "yield_change": -0.016,                        // pooled soil figure (soil_effects change_<story>)
  "region_yield_change": -0.0312,
  "yield_today_t_ha": 2.11,
  "stress_today": 0.45, "stress_future": 0.49,   // soil_effects stress_today, stress_<story>
  "local_yield_change": -0.019,                  // field_table change_<story>: this grid square only, shown as a caveat
  "risk": {"code": "field_risk", "text": "On fine sand the model estimates -1.6% for this crop under Hothouse. The whole region: -3.1%. Drought stress at the sensitive stage (0–1) goes from 0.45 to 0.49.", ...},
  "why": [{"code": "soil_map", ...}, {"code": "droughty", ...}, {"code": "planned", ...}],
  "local_note": "With only this grid square's weather run the same field shows -1.9%. Differences between squares are mostly weather noise, so trust the soil figure above.",
  "basis": {...}
}
```

---

## 7. Try the model (what-if)

### 7.1 Existing `POST /predict/field` (unchanged)

Request (strict, `extra="forbid"`):

```jsonc
{"parcel_id": "F0001-P01", "crop": "pea", "scenario": "historical", "year": 2018, "irrigation": null}
// scenario: historical | ssp126 | ssp245 | ssp585; irrigation: null (farm's usual share) or 0..1
```

Response:

```jsonc
{"parcel_id": "F0001-P01", "farm_id": "F0001", "cell_id": "GF0104", "crop": "pea", "scenario": "historical", "year": 2018,
 "yield_t_ha": 3.62, "baseline_t_ha": 3.28,          // baseline = farm average, same in any weather
 "usual_irrigation": 0.0, "irrigation": 0.0,
 "model_name": "models[pea]", "model_version": "5cf88f338cb8", "technology_year": 2018,   // long_models and 2025 after 2031
 "out_of_training_range": [{"field": "stress_sens", "value": 0.91, "training_min": 0.05, "training_max": 0.88}],
 "effects": {"Drought stress": -0.041, "This farm": 0.023, ...},   // log-scale contributions, as model.explain returns them
 "weather": {"sow_doy": 121.0, "mat_doy": 205.0, ...}}             // the 16 features
```

Errors: 404 unknown parcel, crop or no weather for that combination (for example any Swedish crop but pea, or ssp585 in 2028); 422 bad scenario, irrigation outside 0–1 or a missing field.

What it lacks for the Try page: the starting point (`base`) the "Why this number" chart starts from, the effects as percentages, the parcel's soil and area, the plain-language notes, and the fair held-out check. Those need either recomputation in the UI (not allowed) or a second source, so:

### 7.2 `POST /insights/what-if`

Same request body and validation as `/predict/field` (reuses `FieldRequest`), plus one rule from the Streamlit tab: `irrigation` must be null for a Finnish parcel (422, "Only available for Sweden ..."). Calls `engine.predict_field` and `engine.predictor.predict` once (the second only for `base`; both share the cached Predictor), so `prediction` is byte-for-byte what `/predict/field` returns.

```jsonc
{
  "prediction": { ...the /predict/field response... },
  "base_t_ha": 3.31,                                     // exp(base) from model.explain: an average field and season
  "vs_baseline": 0.104,                                  // pred / baseline - 1 ("+10.4% against the baseline"), null without a baseline
  "drivers": [{"driver": "Drought stress", "effect": -0.040}, ...],   // exp(effect) - 1, |effect| >= 0.001, ascending, as app.py
  "parcel": {"soil": "clay", "area_ha": 3.17, "region": "FI_SW"},
  "weather_table": [{"measure": "Sowing day of year", "value": 121.0}, ... 8 rows as app.py "Weather values used", rounded to 2],
  "notes": [                                             // app.py lines 349–355, same conditions
    {"code": "soil_map", "text": "Soil-map class: clay, 3.2 ha. The soil map is only about 88% accurate."},
    {"code": "usual_irrigation", "text": "This farm's usual irrigated share for this crop: 0%."},
    {"code": "tech_fixed", "text": "Technology is held at 2025, so differences between future seasons come from weather."},   // year > 2031
    {"code": "shared_response", "text": "This uses the shared weather response, the same as the risk results for 2041–2060."}, // year > 2031
    {"code": "irrigation_estimate", "text": "The modelled irrigation effect is an estimate. ..."}],                             // irrigation not null
  "fair_check": {                                        // only for scenario "historical" with a loyo held-out row for farm, crop, year; else null
    "actual_t_ha": 3.55, "model_t_ha": 3.48, "baseline_t_ha": 3.27,
    "text": "Fair check for the whole farm at its usual irrigation, with this season hidden from both methods: our model 3.48, baseline 3.27, actual 3.55 t/ha."},
  "actual_note": "This field, using the final model, which trained on this season",   // or "Future season, or the farm didn't report"
  "basis": {"kind": "model", "label": "What-if with the final trained model, a whole season's weather from the package", ...}
}
```

The Streamlit self-check line ("live predictions differ from the submitted C1 file by at most …") runs 60 predictions and is too slow per request. It moves to `/insights/trust` as `c1_self_check`, computed once per model version and cached.

Errors: as `/predict/field`.

---

## 8. Can we trust this?

### 8.1 `GET /insights/trust?test=loyo`

`test` is `loyo` or `forward` (required). Mirrors `app.py` lines 234–276.

```jsonc
{
  "test": "loyo",
  "headline": {                                     // backtest.metrics on backtest_predictions where test == loyo
    "production_error": {"model": 0.0417, "baseline": 0.1099},   // mape
    "yield_error_nrmse": {"model": 0.1067, "baseline": 0.1572}},  // nrmse
  "headline_note": "In both tests the model is given the actual weather of the season it predicts. So this shows how well it turns weather into yield, not how well anyone can forecast next year's weather.",
  "caveat": "Model settings were tuned on these same seasons, and the tests use farm averages rather than single fields, so real-world errors are likely to be larger.",
  "methods": [{"code": "baseline", "label": "Baseline: farm average", "text": "The farm's average yield for that crop across the training seasons. It knows the farm but ignores weather ..."},
              {"code": "model", "label": "Our model: weather-aware regression", "text": "Farm effect + technology trend + soil + irrigation + crop-stage weather ..."}],
  "by_crop": [                                      // app.py error_table(p): per region and crop, sorted by baseline production error descending
    {"region": "FI_SW", "crop": "pea", "seasons": 15, "baseline_production_error": 0.165, "model_production_error": 0.043,
     "baseline_yield_error": 0.217, "model_yield_error": 0.116, "improvement": 0.74}],
  "pea_models": [{"region": "FI_SW", "method": "regional_weather_response", "label": "Separate weather response", "production_error": 0.0428, "yield_error": 0.1162}, ...],   // backtest_pea_models, this test
  "pea_models_note": "Peas from both regions share one model. Long-range results use one weather response for both regions ...",
  "scorer": {"model": 71.1, "baseline": 38.1, "note": "Apetit told us this score doesn't affect their decision. ..."},   // metrics()["score"]
  "c1_self_check": {"max_diff_t_ha": 0.0004, "rows": 60},   // Predictor.check_against_submission(60), cached per model version
  "basis": {"kind": "batch", "label": "Held-out backtests on past seasons", "sources": ["backtest_predictions.csv", "backtest_pea_models.csv"]}
}
```

`headline` must equal `backtest_summary.csv` (`final_loyo`, `farm_mean_loyo`, and the `forward_2022_2026` rows); the test asserts it.

### 8.2 `GET /insights/trust/seasons?region=FI_SW&crop=pea&test=loyo[&farm_id=F0003]`

All but `farm_id` required. Mirrors `app.py` lines 279–308 (`to_long`).

```jsonc
{
  "region": "FI_SW", "crop": "pea", "test": "loyo",
  "seasons": [{"year": 2012, "actual_t_ha": 3.41, "baseline_t_ha": 3.39, "model_t_ha": 3.52,     // area-weighted by area_ha
               "baseline_miss": -0.006, "model_miss": 0.032}],                                     // pred / actual - 1
  "farms": ["F0003", "F0006", ...],                 // farms with held-out rows in this selection
  "farm": {"farm_id": "F0003", "seasons": [...same shape...], "note": "This farm has only one held-out season in this test. ..."},   // only with farm_id; note only when < 2 seasons
  "note": "The baseline stays nearly flat. The test of our model is whether it follows the good and bad seasons. ...",
  "basis": {...}
}
```

### 8.3 `GET /insights/trust/live-replay?test=loyo`

`test` required; optional `scope` (`all` or `REGION/crop`, default `all`). Rows of `live_season_replay.csv`, one per `known_until` date, with the three methods side by side. This is the evidence for "live estimates are no better than the farm average until about mid-June".

```jsonc
{
  "test": "loyo", "scope": "all",
  "points": [{"known_until": "06-15", "baseline_production_error": 0.1099, "estimate_production_error": 0.0976, "estimate_yield_error_nrmse": 0.1418, "share_of_seasons_beating_baseline": 0.643}, ...],   // "none" (no weather) first, "full" last
  "first_better": "06-15",                          // first date where the estimate's production error is below the baseline's
  "basis": {"kind": "batch", "label": "Replay of past seasons as if the weather arrived day by day", "sources": ["live_season_replay.csv"]}
}
```

### 8.4 `GET /insights/trust/corrections`

No parameters. `yield_corrections_log.csv` with the Streamlit summary sentence (`survey`, `erp`, `used` counts) and all rows (`record_key, field, old_value, new_value, rule, source, used_for_yield`).

---

## 9. What the Streamlit tabs show that `apetit-ui` lacked, and where it goes

| Streamlit | Content | Goes to |
|---|---|---|
| Risk and advice | two-story metrics, draft actions, themes, season shift, policy costs | new page **Risk & advice** (`/insights/advice`, `/insights/policy`) |
| All crops | C1 forecast, C2 changes, C3 € | new page **Outlook** (`/insights/outlook`, `/climate-risk`, `/euro-risk`) |
| Try the model | live what-if with drivers | new page **Try the model** (`POST /insights/what-if`) |
| Can we trust this? | backtests, season by season, pea models, cleaning log | new page **Model trust** (`/insights/trust*`) |
| Map: climate colouring, farms to contact first, region/farm/field panels with risk, why and actions | — | **Map**: a "Climate outlook 2041–2060" layer and side panel (`/insights/farms`, `/insights/advice`, `/insights/fields/{id}`) |
| Farm and fields: soil bars, field table with both stories, dry soils, irrigation share, farm story | — | **Farm**: a "Climate outlook" section (`/insights/farms/{id}`), a field drawer (`/insights/fields/{id}`), "Try this field" links to the Try page |

Not carried over: the language switch (the UI is English), the scorer as a headline (kept in an expander), and the Streamlit map's own basemap.

---

## 10. Tests (`tests/test_insights.py`)

- Every endpoint answers 200 for one valid pair per region and 404 or 422 for a bad code.
- `/insights/advice` actions equal `advisor.advice(load_outputs(), ...)` rule by rule, and `stories[*].yield_change` equals the C2 row / 100.
- `/insights/trust` headline equals `backtest_summary.csv`; `by_crop` equals `app.error_table` reimplemented from `backtest.metrics` (same code path, no Streamlit).
- `/insights/farms/{id}` `fields` equal `advisor.field_table` for that farm; `headline.yield_change` equals the `map_farms.csv` row.
- `POST /insights/what-if` `prediction` equals `POST /predict/field` for the same body.
- Touching an outputs file (rewrite with a changed value) changes the next response and its `generated_at`; a corrupted file keeps the old answer and shows `load_error` in `/insights/meta`.
- No response contains a filesystem path, and no response has a figure keyed by both regions at once.
