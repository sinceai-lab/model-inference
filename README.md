# Apetit Track C: climate risk to farming

Forecasts contract-crop yields for 2027–2031, estimates 2041–2060 yield risk by climate scenario, and converts the risk to euros. All data is synthetic, so results must not be presented as Apetit's actual figures or as facts about real farms.

**Status:** working first version. The submission files pass format checks, but C1 and C2 have no public answer key, so their true scores are unknown.

## Run it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd src
python features.py   # crop-stage weather features
python dataset.py    # clean yields and corrections log
python backtest.py   # per-crop model comparison
python stage_test.py # optional: held-out test of the crop-stage values
python run_all.py    # submissions, risk tables and checks
```

To open the viewer, run this from the project folder after `run_all.py`:

```bash
streamlit run app.py
```

It is built for Apetit's farming team and advisors, following the Q&A session (branch `inference-v2-QA-suggestions`):

| Tab | Purpose |
|---|---|
| **Risk and advice** | Two futures for a crop, what drives the change, how the season shifts, policy costs and draft actions |
| **Farm and fields** | One farm's fields compared by soil, modelled yield and crop plan |
| **All crops** | The 2027–2031 forecast, every crop's yield change and the replacement cost |
| **Try the model** | Runs the trained model live for any field and season, and shows why it landed on that number |
| **Can we trust this?** | The baseline against our model on held-out seasons |

Trained models are saved in `cache/models.pkl`, and `src/inference.py` loads them. The advice rules and field table are in `src/advisor.py`, which doesn't depend on Streamlit, so other front ends can call the same functions.

The selector at the top right switches between English (default) and Finnish. Translations are in `i18n.py`, with the English text as the key: wrap new text in `t("...")` and add its Finnish line there, or it shows in English. The Finnish was not written by a native speaker, so have one check it before showing it to others.

The code expects the package in the sibling folder `APETIT_CLIMATE_NATURE_NAVIGATOR_2026`. Set `APETIT_PACKAGE` to use another path. A full clean rerun gave byte-identical C1 and C2 files.

## What is in this repository

Code, submission files, result tables and research notes (`docs/CLAUDE_insights_abstract.md`, written before the Track C work began). The challenge data package is **not** included: download it separately and place it next to this folder. `.venv/` and `cache/`, including the trained models, are also left out; the steps above rebuild them.

## Outputs (`outputs/`)

| File | Content |
|---|---|
| `C1_yields_2027_2031_submission.csv` | Task C1 submission |
| `C2_climate_yield_risk_submission.csv` | Task C2 submission |
| `C2_detail_with_uncertainty.csv` | C2 with leave-one-season-out ranges and sensitivity runs |
| `C2_bad_year_check.csv` | Bad-year method compared with observed history |
| `C3_euro_risk.csv` | Replacement cost per region, crop and scenario |
| `C3_irrigation_evidence.csv`, `C3_irrigation_se_within_farm.csv` | Irrigation effect and where it can be measured |
| `advisor_drivers.csv`, `advisor_season_shift.csv` | What drives each yield change, and how the season shifts per scenario |
| `backtest_pea_models.csv` | Separate and shared pea weather responses on held-out seasons |
| `yield_corrections_log.csv` | Every yield correction or exclusion, with its rule |
| `stage_parameter_test.csv` | Held-out test of the changed crop-stage values |
| `model_coefficients.csv` | Weather, soil and trend effects per crop (standardised) |
| `backtest_summary.csv`, `backtest_per_crop_grid.csv` | Model performance |
| `climate_extremes_check.csv` | Rainfall variability, history against scenarios |

## Method

1. **Yields.** One row per farm, crop and year, from three sources:
   * Finnish survey, with 18 yields corrected as ×10 decimal slips.
   * ERP deliveries for farms that didn't respond, divided by the measured delivered-to-yield ratio. A unit price far from the fixed contract price identifies 31 quantity slips, which are corrected, and shipment weights confirm each one. 12 repeat postings are removed, and 11 returns aren't subtracted because the goods were harvested.
   * The Swedish grower file. It assumes the Finnish pea delivered-to-yield ratio.
2. **Weather features.** For each grid cell, year, crop and soil: sowing date, crop stages from growing degree days, a soil-water balance, drought stress by stage, heat days, rain after sowing and before harvest, blight-favourable days and May temperature.
3. **Model.** One penalised regression per crop: `log(yield) = farm effect + trend + soil + irrigation + weather`. It uses no same-year farm inputs, because those aren't known for future seasons.
4. **Long-range risk.** Parcels are held at the 2025 mix, with 2025 technology and current irrigation. Future years combine the supplied 2041–2060 weather with 1991–2020 weather shifted by the package's climate signals, because only one realisation per scenario is supplied. Bad-year probabilities add the season error the model can't explain.
5. **Euro risk.** Shortfall against today's average × 2025 contract price × replacement premium.

## Results

### Backtest

Scores use the official formula on farm-level rows, not the hidden parcel-level truth. **Expect a lower real score**, especially for parcel-level error.

| Test | Scorer-style score | Aggregate error | Parcel-style error |
|---|---:|---:|---:|
| Farm average, leave one year out | 38.1 | 11.0 % | 0.157 |
| Final model, leave one year out | 71.1 | 4.2 % | 0.107 |
| Final model, forward 2022–2026 | 71.9 | 4.0 % | 0.106 |

Settings were chosen using the same seasons, so these figures are optimistic. Pea maturity and turnip rape's sensitive stage were set from these seasons too. When those values are chosen without the season being scored (`stage_test.py`), production error is 3.3–4.5 % for those crops instead of 2.1–4.5 %, against 5.1–7.4 % before the change.

### 2041–2060 yield change against 1991–2020

| Region and crop | SSP1-2.6 | SSP2-4.5 | SSP5-8.5 | Range at SSP5-8.5 | Confidence |
|---|---:|---:|---:|---:|---|
| Finland, turnip rape | −1.7 % | −2.8 % | −4.0 % | −5.7 to −2.6 | Medium |
| Finland, spinach | −0.8 % | −2.3 % | −3.7 % | −6.2 to −2.7 | Low to medium: few farms |
| Finland, potato | +1.4 % | −0.2 % | −1.5 % | −3.6 to +0.6 | Low to medium: few farms |
| Finland, carrot | +0.1 % | −0.4 % | −1.3 % | −4.3 to +0.7 | Low: few farms |
| Finland, pea | +0.6 % | +0.7 % | +1.5 % | −1.8 to +3.3 | Low: sign changes with model choice |
| Sweden, pea | +5.4 % | +5.2 % | +5.0 % | +1.4 to +6.4 | Low: 9 seasons |

Confidence labels are our judgment. Ranges only show sensitivity to dropping one training season, not total uncertainty.

### Euro risk: replacing shortfalls with imports

| Region | Today's climate | SSP1-2.6 | SSP2-4.5 | SSP5-8.5 |
|---|---:|---:|---:|---:|
| Finland, € a year | 257,000 | 252,000 | 291,000 | 326,000 |
| Sweden, € a year (low confidence) | 157,000 | 88,000 | 99,000 | 112,000 |

* Of the €69,000 a year Finland adds under SSP5-8.5, spinach accounts for €47,000 and potato for €13,000.
* Normal weather variation already costs more than climate change adds, even under the highest scenario.
* Turnip rape shows the largest yield decline but a small cost, because its replacement premium is only 8 %.

### Irrigation

Only Swedish peas can measure this, because 167 farms there switch between irrigating and not.

* **Average uplift:** about 6 % within the same farm.
* **By season:** 15 % in 2021, 13 % in 2023 and 10 % in 2026, against −0.1 % to 6 % in the other six seasons.
* **Finland:** no farm switches, so the effect can't be separated from the farm. Irrigated farms' higher yields may have other causes.

## What Apetit asked for (Q&A session)

* They judge usefulness to their work, not the auto-scorer, which came from SinceAI and doesn't affect their decision.
* The main users are the farming team, advisors and farmers. Management and sustainability staff come second.
* Farmers want graphs and advice rather than data. Their stated gap is knowing what to do about a risk.
* Their decisions include sowing and harvest timing, staggering pea sowing by up to a month, and variety trials.
* They care most about a hothouse future and staying below 2 °C, including policy costs in the latter.
* Finland and Sweden are separate operations and no peas move between them, so the earlier hedge analysis was dropped.

## Limits

* **Advice rules are drafts.** They are written rules triggered by model results, and advisors should review them. Sowing dates and varieties aren't in the data, so neither can be recommended from it.
* **Backtests use known weather.** Both tests give the model the actual weather of the season it predicts, so they don't measure forecasting with unknown weather.
* **Driver effects aren't causes.** Weather measures are correlated, so the advice page only reads them as three grouped themes.
* **Field differences.** Models train on farm averages, so differences between fields rest mainly on the soil map.
* **Sowing estimate.** It uses temperature alone and is capped at 10 April. Roughly a quarter of historical pea years hit the cap in Finland and over 70% in Sweden, so the shift is a minimum and isn't shown for Swedish peas.
* **Policy prices.** The carbon, fertiliser and diesel paths are the package's illustrative values, not forecasts.
* **Assumed parameters.** Soil water capacities, crop stage thresholds and maturity values are our assumptions, not package values. Held-out seasons support changing two: pea maturity (750 to 850 degree days) and turnip rape's sensitive stage (350–600 to 455–780). Soil water and the three small crops' stages showed no consistent gain, so they stay as assumed. Season error and bad-year rates are measured with the two tuned values, so they may be slightly low.
* **Limited history.** There are 15 Finnish and 9 Swedish seasons, with weather largely shared within a region. Small crops have few farms.
* **Heat extrapolation.** Hot days in the potato and carrot seasons in south-west Finland rise from about 3.5 to 11–12 a year under SSP5-8.5. A mostly linear response fitted to cooler seasons may understate damage. How far this leaves the training range has only been checked for Swedish peas so far.
* **Bad-year rates.** Modelled rates are above observed for peas and turnip rape (for example 13 % against 7 % for Finnish peas). They are based on few seasons.
* **Swedish delivered ratio.** The file has no reported yields to compare, so the Finnish pea ratio can't be tested there. It changes Swedish yield levels by up to 2.5 %, not the percentage changes.
* **Swedish signal.** The climate signals file has no regional split, so the same signals are applied to both regions.
* **Not modelled.** CO2 fertilisation and adaptation are not in the data. Water availability for irrigation is not assessed.
* **Euro risk.** Uses 2025 prices and counts only the premium paid on replaced volume. It excludes replacement-import emissions, lost margin, price shocks and what Apetit still pays farmers after a poor crop.
* **Expert review.** No review workflow exists yet. The corrections log is ready to feed one.

## Microsoft path

Weather and farm files can load into a Fabric Lakehouse as bronze tables, with features and clean yields as silver and risk tables as gold. The scripts can run as Fabric notebooks. Corrections log approvals could run through Power Apps, and results could appear in Power BI.
