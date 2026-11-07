# Apetit × Since AI 2026: research handoff

**Written:** 2026-11-07, by Claude (Opus 5.5), from a research conversation with the team.
**Purpose:** give another AI agent the context needed to continue without re-deriving it.
**Status:** research only. Nothing has been built, and the team has not chosen a final track.

## How to read this file

Each claim has one of these origins. Do not treat a lower level as a higher one.

| Label | Meaning |
|---|---|
| **[DOC]** | Stated in the package docs, the brief or the briefing transcript |
| **[RUN]** | Measured by running code on the data in this session |
| **[EST]** | A calculation or estimate from this session; indicative, not validated |
| **[OPINION]** | Claude's judgment; challenge it if the evidence points elsewhere |

Check anything that matters against the source files. The package docs are the authority, especially `docs/TASKS_AND_SCORING.md` and `docs/METHODOLOGY.md`.

---

## 1. Situation

### Team and constraints

* **Team:** 4 technical people (one semi-senior AI profile, the others software developers) and 1 project manager.
* **Time:** a 36-hour hackathon. The brief dates the event 6–8 Nov 2026 in Turku.
* **Deadline:** not in the package. It is in the event guide (`sinceai.ai/hackathon-2026/guide`). **Confirm it.**
* **Team's concern:** they found the problem hard to grasp and the data sparse, complex and contaminated. They have been looking closely at which tracks have the lowest data complexity.
* **Unknown:** which language-model API and credits are available. The team had not answered this.

### Paths

Package root: `/Users/dncampo/Downloads/SinceAI/Apetit_SinceAI2026/APETIT_CLIMATE_NATURE_NAVIGATOR_2026/`

The parent folder also holds:

* `Apetit_x_SinceAI_2026_Challenge_Brief_EN_FINAL_2026-11-04.pdf` and `.docx`
* `The Apetit transcript 37min.txt`, the machine transcript of the briefing. It garbles names; for example, Minna's surname is wrong. It also cuts off mid-sentence at the end.

### Contacts [DOC]

* **Apetit:** Jani Kielenniva (CIO), jani.kielenniva@apetit.fi; Minna Päällysaho (sustainability specialist), minna.paallysaho@apetit.fi
* **Questions:** use the challenge Discord channel first, because answers are shared with all teams.
* **Live session:** 10:00–12:00 on the day after the briefing. This should be 7 Nov, but confirm on Discord.

---

## 2. The problem

### In plain terms

Apetit wants a tool that shows which actions to take to cut its emissions and nature impact, what they cost, and why the numbers can be trusted. This explanation worked for the team:

| Step | Household analogy | Apetit |
|---|---|---|
| 1. Collect | Gather receipts | Purchases, meters, fuel, transport, farm surveys |
| 2. Clean | Fix typos | Unit slips, duplicates, bad readings |
| 3. Total | Work out spending | Tonnes of CO2e: mostly amount × emission factor |
| 4. Set a goal | "Spend 20 % less" | SBTi reduction rates |
| 5. Choose | Best cuts for least pain | Pick from the 30 listed levers |

Steps 4 and 5 are what Apetit actually values. The formulas and factors are supplied, so the team does not need to invent climate science.

### Company [DOC]

* A Finnish food company with two businesses: edible vegetable oils (rapeseed crushed at Kantvik) and frozen foods (Säkylä; a pizza plant at Pudasjärvi).
* About 150 Finnish contract vegetable growers.
* Foodhills (Bjuv, Sweden), with about 300 pea growers, was acquired on 27 Nov 2025.
* Most emissions come from farming and purchased goods.
* Committed in December 2025 to set SBTi near-term targets within 24 months.

### What the briefing adds beyond the docs [DOC, transcript]

* **The pain:** the inventory is built by hand in Excel from fragmented systems. Minna looks up road routes in Google Maps and sea distances on a harbour-distance site.
* **The strongest statement:** time spent on reporting "brings nothing". Also: "no one wins any prizes" for a GHG inventory; it must be "good enough". The inventory is still needed for targets.
* **Base year:** a change above about 5 % triggers recalculation. Being able to recalculate is a real requirement, and 2025 was given as an example base year.
* **Traceability is a named pain point:** undocumented assumptions make it very hard to fix mistakes found years later.
* **Regulation:** Apetit says no regulation currently requires it to calculate this. It follows the GHG Protocol voluntarily. The EU agricultural policy is not a focus, though teams may include it.
* **Report format:** not strict; GHG Protocol categories.
* **Calculation approach:** mostly kg and tonnes. Spend-based factors are only for minor items, such as chemicals.
* **Supplier data:** real suppliers rarely provide PCFs, and Apetit needs the "right level", not exact figures. Anomalies in supplier data are worth detecting.
* **External data:** allowed if it helps ("use any source"). State assumptions and licences.
* **Technology:** Azure, Fabric and Dynamics are preferred but not required.
* **Scope:** you do not need to use all the data. "One track is enough", and one amazing track beats many.
* **Openness:** Apetit does not know what is possible and asked teams to surprise them.

### Discrepancy between sources

The brief says the platform "utilizes already automated Group-wide GHG emissions calculation data". The briefing describes manual Excel work, and Track A exists to automate it. Treat the automation as a goal, not as something that exists. This could be confirmed with Apetit.

### Guiding question [DOC]

> How can AI help us to understand, prioritize and quantify climate and nature impacts across the value chain, and turn sustainability data into actionable decisions while taking into consideration different future climate scenarios?

### Important rule

All data is **synthetic**. Do not present results as Apetit's actual emissions or as facts about real farms. Conclusions about method transfer to the real company; absolute numbers do not.

---

## 3. What the jury expects

### Rubric [DOC]

| Criterion | Weight | Full marks |
|---|---:|---|
| Usefulness for decisions | 30 % | Actionable next week: priorities, € and t figures, actions with owners |
| Sound reasoning | 25 % | Correct GHG Protocol, SBTi, SBTN and scenario logic; assumptions stated; method changes not presented as reductions |
| Traceability and expert review | 25 % | Numbers link to records and factors; corrections logged; a human approves before publication |
| Reliability | 10 % | Auto-scores where applicable; robust to planted issues |
| Technical quality | 10 % | Runs end to end from the raw package; reproducible; fits or maps onto Microsoft |

Auto-scores are evidence for the jury, not the verdict. The number of tracks covered is not what is judged.

### Submission [DOC]

1. Code repository with a README that reproduces results from the unzipped package.
2. CSV files for the auto-scored tasks attempted, using the names in `tasks/templates/`.
3. A short demo and slides: problem → approach → evidence → what Apetit should do.
4. A one-page method note: sources, assumptions, limitations, how expert review works.

The brief also asks for a "working AI solution and documentation with usage instructions".

### AI approaches suggested by the brief [DOC]

RAG on frameworks, agents for data validation and recommendations, ML for scenario and risk modelling, knowledge graphs, geospatial AI, explainable AI, NLP, and digital twin or scenario simulation. These are suggestions, and the jury does not require any particular technology.

---

## 4. The tracks

| Track | Task | Plain meaning | Scoring |
|---|---|---|---|
| **A** Data → inventory | A1 | Find and classify errors in 2025 records | Auto + jury |
| | A2 | Calculate the 2025 GHG inventory with an audit trail | Auto + jury |
| **B** Pathways | B1 | SBTi targets and pathway (FLAG, base-year recalculation) | Jury |
| | B2 | Marginal abatement cost curve and action portfolio | Jury |
| **C** Climate risk | C1 | Yields per parcel, 2027–2031 | Auto |
| | C2 | 2041–2060 yield risk by climate scenario | Auto |
| | C3 | Translate C2 into € risk and adaptation options | Jury |
| **D** Nature (SBTN) | D1 | Catchment P and N loads and priority rank | Auto |
| | D2 | Value-chain screening, including imports | Jury |
| **E** Copilot | E | Answer questions, with evidence | Numeric auto + jury |

"Inventory" means a **greenhouse gas inventory**: the yearly emissions report by source. It is not a data catalogue or stock of goods.

One-sentence versions that worked for the team:

* **A:** turns messy records into one trustworthy annual emissions report, with every number traceable to its source.
* **B:** a planning tool where you try combinations of actions and see which reach the climate goal, and at what cost.
* **C:** predicts how changing weather affects Apetit's crops, converts that to money at risk, and shows which actions protect the harvest.
* **D:** shows where farming harms nature most, mainly fertiliser reaching lakes and rivers, weighted by how fragile those waters are.
* **E:** a chat assistant that answers questions about the data and shows where each answer came from.

### Task A1 [DOC]

* **Score:** 100 × F1 × (0.75 + 0.25 × type accuracy). Matching is on `record_key`.
* **Submit:** `table, record_key, issue_type, confidence, explanation`. Only 2025 records score.
* **18 valid issue types:** `unit_error, duplicate_record, currency_error, material_mismatch, decimal_shift, missing_record, meter_spike, wrong_gas_code, certificate_mismatch, soil_misreport, outlier_implausible, area_mismatch, coordinate_swap, pcf_unit_error, pcf_stale_period, total_mismatch, missing_leg, mode_mislabel`
* **`soil_misreport`:** at least 30 % of a farm's crop area for that year is on truly organic soil while the survey says "Mineral soil". True soil is hidden, so use the soil map and other evidence.
* **Several issues on a record:** any of the types counts as correct.

Record key formats:

| Table | Key |
|---|---|
| `erp_purchase_lines` | `erp:{doc_no}:{line_no}` |
| `energy_meter_readings` (incl. missing months) | `energy:{site_id}:{YYYY-MM}:{carrier}` |
| `fuel_deliveries` | `fuel:{delivery_id}` |
| `goo_cancellations` | `goo:{site_id}:{year}` |
| `refrigerant_service_log` | `refrigerant:{event_id}` |
| `waste_transfer_notes` | `waste:{transfer_note}` |
| `travel_bookings` | `travel:{booking_id}`; flag the later rows of a duplicate |
| `commuting_survey` | `commute:{response_id}` |
| `shipments` (missing legs) | `ship:{ref_doc}:{ef_id}`, using the missing leg's factor |
| `farm_survey` | `farm_survey:{survey_id}` |
| `farm_registry` | `farm:{farm_id}` |
| `supplier_pcfs` | `pcf:{supplier_id}:{material_id}:{year}` |
| `draft_report_summary` | `report:{year}:{line}` |

### Task A2 [DOC, code]

Each line earns `max(0, 1 − |error| / 5 %)`. Weights from `tools/ccn_tools/score.py`:

| Line | Weight | Line | Weight |
|---|---:|---|---:|
| `scope1_total` | 15 % | `cat03_fuel_energy` | 4 % |
| `scope2_location_total` | 3 % | `cat04_upstream_transport` | 8 % |
| `scope2_market_total` | 12 % | `cat05_waste` | 4 % |
| `scope3_total` | 20 % | `cat06_business_travel` | 2 % |
| `cat01_purchased_goods_services` | 20 % | `cat07_employee_commuting` | 2 % |
| `cat02_capital_goods` | 3 % | `cat09_downstream_transport` | 4 % |
| `cat11_use_of_sold_products` | 1.5 % | `cat12_end_of_life` | 1.5 % |

The audit trail is required for the jury: each number traces to source records, each correction has a logged reason, and each factor has a recorded source. Suggested correction row [DOC]: `record_key, field, old_value, new_value, rule_or_model, evidence, proposed_by, approved_by, timestamp`.

### Task B: what the jury wants [DOC]

* Base year and recalculation logic (grain-trade divestment, Foodhills, Pudasjärvi, Kantvik steam). Show both a recalculated 2019 base and a 2025 base; 2025 needs a structural adjustment because Foodhills is in scope for December only.
* A FLAG / non-FLAG split. Apetit must set a FLAG target as a food processor.
* Minimum rates: Scope 1+2 4.2 %/yr linear, Scope 3 non-FLAG 2.5 %/yr, FLAG 3.03 %/yr.
* V1.3.1 versus V2 timing. V2 is effective 1 Feb 2027; V1.3.1 is usable until end-2027; V2 is mandatory for new and renewed targets from 31 Jan 2028.
* Coverage: under V2, every Scope 3 category of at least 5 % of Scope 3 must be covered.
* A pathway under at least two transition scenarios: BAU drivers plus levers by start year and ramp, and the gap to target each year.
* A cost curve with honest uncertainty and co-benefits for water, nutrients and biodiversity.
* Measurement improvements (L27) and structural changes are not reductions.
* Category 10 should be screened and its exclusion justified.
* Lever figures are design estimates. **Recompute them from your inventory.**

### Task C [DOC]

* **C1:** 12,064 parcel-year rows. Score: 60 % aggregate production MAPE by region × crop × year (none at 15 %) and 40 % parcel nRMSE (none at 0.35). Weather for 2027–2031 is one `ssp245` realisation.
* **C2:** 18 rows of region × crop × SSP. Submit `mean_yield_change_pct` against 1991–2020 and `p_bad_year` (share of years below 80 % of the 1991–2020 mean). Score: 70 % yield-change MAE (none at 5 points), 30 % `p_bad_year` MAE (none at 0.1). The truth is a Monte Carlo over the truth model, using the 2025 parcel mix and current management.
* **C3:** for example, shortfall volume × contract price × replacement premium, plus the emissions of replacement imports and the value of adaptation.
* **The truth yield model responds to:** drought in sensitive stages (reduced by irrigation), heat days at flowering, waterlogging after sowing on clay, rain at harvest, season length, potato late blight, and pollen beetle on turnip rape.
* **Yield structure:** `Ypot × technology trend × farm skill × soil suitability × W(weather) × pests × N response × organic factor × noise`.
* **Hedge to quantify:** in 2026 Finnish peas had a record year while Swedish peas were hit by heat and drought.

C1 rows by crop [RUN]: FI carrot 189, pea 2,024, potato 287, spinach 301, turnip rape 4,716; SE pea 4,547.

### Task D [DOC]

`priority = (P / median(P) + 0.5 × N / median(N)) × state_weight × p_sensitivity`

* **state_weight:** good 1.0, moderate 1.2, poor 1.5, bad 1.8.
* **Estimate:** P and N that Apetit-contract parcels deliver to receiving waters in 2025.
* **Score:** 10 % Spearman, 10 % top-5 overlap, 40 % MAE of log10(P), 40 % MAE of log10(N); none at 0.15, a factor of 1.4.
* **Loss drivers:** soil-P test, clay, slope, erosion-prone crops, rainfall, buffer strips, catch crops, drainage, N surplus. Delivery decays with distance to water, then catchment retention applies.
* **Calibration:** monitored outlet loads at 15 catchments for 2019–2025 **include non-contract farmland and natural background**. True loads for 6 dev catchments are public and excluded from the test score.
* **D2:** SBTN Step 1a materiality screening on land use, water use, nutrient pollution, GHG and pesticides. It should be built so real geospatial layers can be added later.

### Task E [DOC]

34 questions in `tasks/E_questions.csv`. Answers without evidence (record keys, file and row, standard and section) get no rubric credit. The default numeric tolerance in the scorer is 3 %.

| IDs | Topic |
|---|---|
| E01, E13 | Säkylä combustion and refrigerant emissions, 2025 |
| E02, E03 | Scope 2 after GoO reconciliation; Kantvik location-based |
| E04, E05 | Imported rapeseed emissions; rapeseed share of category 1 |
| E06, E21 | FLAG share of total; FLAG target for 2032 |
| E07, E08 | Peat share of Finnish contract emissions; farms at least 30 % organic |
| E09 | Kantvik biogenic CO2 |
| E10, E11 | Säkylä electricity after meter fixes; renewable share |
| E12 | Group water consumption 2024 following GRI 303 |
| E14, E15 | Sea-leg transport emissions; soy protein isolate net tonnes |
| E16, E17 | Finnish pea and turnip rape footprints including peat |
| E18, E19 | Change in Finnish and Swedish pea deliveries, 2025 to 2026 |
| E20 | Scope 1+2 target for 2032 |
| E30–E39 | Rubric questions on FLAG, rates, base year, GoOs, EUDR, ESRS E3, removals, SBTN, measurement changes |
| E90–E92 | Dev questions with public answers |

---

## 5. Data map

### Files per track

● needed  ○ useful, optional  ◐ used through Track A's output  – not needed
**These marks are [OPINION]**, from the docs, calculator code and question list. There is no official mapping.

| File (under `data/`) | A | B | C | D | E |
|---|:-:|:-:|:-:|:-:|:-:|
| **01_master** | | | | | |
| `sites` | ● | ○ | – | – | ● |
| `materials` | ● | ● | – | ● | ● |
| `suppliers` | ○ | ○ | – | ○ | ○ |
| `emission_factor_library` | ● | ● | – | – | ● |
| `farm_registry` | ● | ○ | ● | ● | ● |
| `parcels.csv` | ● | ● | ● | ● | ● |
| `climate_grid_cells` | – | – | ● | ○ | – |
| **02_raw_feeds** | | | | | |
| `erp_purchase_lines` | ● | ◐ | ○ | ● | ● |
| `energy_meter_readings`, `fuel_deliveries`, `fuel_stock_changes` | ● | ◐ | – | – | ● |
| `refrigerant_service_log`, `heat_supplier_factors` | ● | ◐ | – | – | ● |
| `goo_cancellations`, `goo_registry_statement` | ● | ◐ | – | – | ● |
| `supplier_pcfs/*.json` (44 files) | ● | ◐ | – | – | ◐ |
| `shipments` | ● | ◐ | – | – | ● |
| `sales_volumes` | ● | ● | – | – | ◐ |
| `frozen_warehousing`, `waste_transfer_notes`, `wastewater_third_party` | ● | ◐ | – | – | ◐ |
| `travel_bookings`, `commuting_survey_2025`, `headcount` | ● | ◐ | – | – | ◐ |
| `capex_projects` (cross-check only) | ○ | ○ | – | – | – |
| `water_balance` | – | – | – | ○ | ● |
| **03_farming** | | | | | |
| `farm_survey_fi` | ● | ◐ | ● | ● | ● |
| `foodhills_odlingsdata_se` | – | ● | ● | ● | ● |
| `parcel_crop_history_and_plan` | ● | ○ | ● | ● | ● |
| `current_calculator_footprints` | ○ | – | – | – | ○ |
| **04_climate** | | | | | |
| `weather_daily_1991_2060.parquet` | – | – | ● | ○ | – |
| `weather_monthly_1991_2060`, `climate_change_signals` | – | – | ○ | ○ | – |
| **05_scenarios** | | | | | |
| `decarbonisation_levers` | – | ● | ○ | ○ | ○ |
| `transition_scenarios` | – | ● | ● | – | – |
| `structural_events` | ● | ● | – | – | ● |
| `published_inventory_history` | ○ | ● | – | – | ○ |
| `contract_prices_and_replacement_premiums` | – | ○ | ● | – | – |
| `draft_report_summary_2025` (planted errors) | ● | – | – | – | – |
| **06_nature** | | | | | |
| `catchments.csv`, `monitored_catchment_loads` | – | – | – | ● | – |
| `origin_state_of_nature_indicative` | – | ○ | – | ● | ○ |
| `parcels.geojson`, `catchments.geojson` (maps) | – | – | – | ○ | – |
| **07_frameworks and sample** | | | | | |
| `framework_digest.md` | ○ | ● | – | ● | ● |
| `source_registry` | ○ | ○ | ○ | ○ | ○ |
| `00_apetit_original/ApetitGroup_sample_data.xlsx` (context only) | ○ | ○ | – | – | – |

`tasks/templates` has a submission file for each auto-scored task. `tasks/dev` has answer keys for A1 (2023–2024), A2 (2023 and 2024), D1 (6 catchments) and E (3 questions). **C has no answer key**, so backtest on history.

### Sizes [RUN]

| File | Rows |
|---|---:|
| `weather_daily_1991_2060.parquet` (32 MB) | 4,234,104 |
| `parcel_crop_history_and_plan.csv` (12 MB) | 284,260 |
| `weather_monthly_1991_2060.csv` (6 MB) | 139,104 |
| `parcels.csv` / `parcels.geojson` | 14,213 |
| `shipments.csv` | 11,617 |
| `erp_purchase_lines_2021_2025.csv` | 7,427 |
| `travel_bookings.csv` | 3,532 |
| `farm_survey_fi.csv` | 3,437 |
| `foodhills_odlingsdata_se.csv` | 2,683 |
| `farm_registry.csv` | 680 |

### Linking the data

* **Fields to catchments:** `parcels.csv` already has `catchment_id` and `farm_id`. **No spatial join is needed.**
* **Farms to weather:** there is no direct key. Match each farm or parcel to the nearest cell in `climate_grid_cells`.
* **Crops to fields:** `parcel_crop_history_and_plan` (`status` is `declared` for 2012–2026, `planned` for 2027–2031).
* **Shipments to purchases:** inbound `ref_doc` = ERP `doc_no`.
* **Contract deliveries:** ERP `supplier_id` = `farm_id`, for materials M100 turnip rape, M110 pea, M111 potato, M112 carrot and M113 spinach.
* **No Swedish grower lines appear in ERP** [RUN]. Swedish deliveries come from `foodhills_odlingsdata_se`.

### Format notes

* `foodhills_odlingsdata_se.csv` uses `;` and a decimal comma, with Swedish headers.
* `uom = TO` means tonnes and is legitimate for vessel lots. `uom = EUR` marks spend items.
* FX rates in `factors.py`: SEK 11.4 and USD 1.08 per EUR.
* Weather `scenario` values: `historical` (1991–2026), `ssp126`, `ssp245`, `ssp585` (2027–2060).
* The transition scenario file has only the years 2025, 2027, 2030, 2035, 2040, 2045 and 2050.

---

## 6. Findings from running the code

### Baselines on the dev keys [RUN]

| Baseline | Result |
|---|---|
| A1 rules | Score 52.17; precision 0.798, recall 0.395, F1 0.528, type accuracy 0.949 |
| A2 naive | 2023: 25.54; 2024: 23.24 |
| D1 contract area × state | Score 12.0; Spearman 0.37, top-5 overlap 0.80, log10 P MAE 0.149, log10 N MAE 0.176 |

A1 baseline recall by type:

| Recall | Types |
|---|---|
| 0.0 | `area_mismatch, certificate_mismatch, material_mismatch, missing_leg, soil_misreport, wrong_gas_code` |
| Low | `currency_error` 0.167 |
| Partial | `duplicate_record` 0.625, `decimal_shift` 0.667, `unit_error` 0.739, `meter_spike` 0.75 |
| 1.0 | `missing_record, outlier_implausible` |

### Uncleaned data versus truth, 2024 [RUN]

| Line | Naive t | True t | Error |
|---|---:|---:|---:|
| `scope1_total` | 136,573 | 6,400 | +2,034 % |
| Fugitive refrigerants | 131,438 | 1,094 | +11,920 % |
| Combustion | 5,136 | 5,306 | −3.2 % |
| `scope2_location_total` | 27,427 | 1,123 | +2,342 % |
| `scope2_market_total` | 356,924 | 63 | +567,076 % |
| Category 1 | 165,741 | 172,085 | −3.7 % |
| Category 2 | 2,260 | 802 | +182 % |
| Category 3 | 21,211 | 1,670 | +1,170 % |
| Category 4 | 4,335 | 4,381 | −1.1 % |
| Category 5 | 2,680 | 2,701 | −0.8 % |
| Category 6 | 139 | 137 | +1.8 % |
| Category 7 | 6,816 | 308 | +2,114 % |
| Category 9 | 4,771 | 4,771 | 0.0 % |
| Category 11 | 1,839 | 1,839 | 0.0 % |
| Category 12 | 1,869 | 1,869 | 0.0 % |
| `scope3_total` | 211,661 | 190,562 | +11.1 % |
| Biogenic CO2 memo | 678,183 | 10,532 | +6,340 % |

**Insight:** the damage is concentrated in a few lines. Category 1 looks close, but that may hide offsetting errors and missing peat emissions. This has not been checked.

### 2025 naive results and the draft report [RUN]

Naive 2025: Scope 1 132,163; Scope 2 location 72,460; Scope 2 market 1,117,417; category 1 17,476,763; Scope 3 17,534,593. Category 1 is about 100 times the 2024 true value.

`draft_report_summary_2025.csv`:

* Scope 1 and Scope 2 market **exactly match** the naive run.
* Its Scope 3 line is 71,534,593, which is 17,534,593 with transposed digits.
* Its total of 18,784,173 equals the sum using the *correct* 17,534,593.

So the draft reads like an uncleaned run plus a typing error, and it fails a simple sum check. **This is a strong demo opening.** [OPINION]

### Planted issues

781 planted in total [DOC]. Public dev labels, 2023–2024 (201 rows, 200 unique keys) [RUN]:

| Table | Issue types and counts |
|---|---|
| `erp_purchase_lines` | `unit_error` 28, `duplicate_record` 20, `currency_error` 18, `decimal_shift` 12, `material_mismatch` 12 |
| `farm_survey` | `soil_misreport` 33, `area_mismatch` 18, `decimal_shift` 6, `outlier_implausible` 2 |
| `energy_meter_readings` | `missing_record` 6, `unit_error` 6, `meter_spike` 4 |
| `travel_bookings` | `duplicate_record` 12 |
| `shipments` | `missing_leg` 8 |
| `waste_transfer_notes` | `unit_error` 6 |
| `fuel_deliveries` | `unit_error` 4 |
| `goo_cancellations` | `certificate_mismatch` 2 |
| `refrigerant_service_log` | `unit_error` 2, `wrong_gas_code` 2 |

**Hidden-test risk:** five issue types have **no** public examples: `coordinate_swap`, `pcf_unit_error`, `pcf_stale_period`, `total_mismatch`, `mode_mislabel`. Four tables also have no dev labels: commuting, farm registry, supplier PCFs and the draft report. A model trained only on dev labels will miss them, so write rules for them.

Evidence already seen for those types [RUN]:

* **`commuting_survey_2025`:** `one_way_km` has a median of 17.2 and a max of 56,300. Modes include non-canonical labels (`Car`, `henkilöauto`, `auto`, `linja-auto`). `linja-auto` means bus, but the calculator treats unknown modes as car, so normalise them.
* **`farm_registry`:** 3 Finnish rows have latitude below longitude, which suggests swapped coordinates.
* **`refrigerant_service_log`:** the max `kg_added` is 85,150 kg, which is implausible.
* **PCF stale periods and unit errors:** all 44 files declare `kilogram`, so unit errors must be found from values, for example by comparing with the other year or the library factor. Not yet examined further.

### Peat soils: probably the central finding [EST]

2025 Finnish contract area on the five crops: about 7,950 ha, of which about 390 ha (about 5 %) is organic on the soil map.

| Crop | Organic ha | Share |
|---|---:|---:|
| Turnip rape | 239 | 5 % |
| Pea | 124 | 6 % |
| Spinach | 24 | 7 % |
| Carrot | 3 | 1 % |
| Potato | 0 | 0 % |

* **Emissions:** 29 t CO2/ha plus 13 kg N2O-N/ha (about 5.6 t CO2e/ha) gives about 34.6 t CO2e/ha, so about **13,500 t CO2e**. That is about twice 2024 Scope 1+2 (6,463 t).
* **Per kg:** on a pea field yielding 3 t/ha, peat adds about 11.5 kg CO2e/kg. The Apetit sample's median pea footprint is about 0.27 kg CO2e/kg.
* **Reporting gap:** in 2025, 4 of 283 survey rows report organic soil. 27 of 356 Finnish farms are at least 30 % organic on the map.
* **Current practice** excludes this: `current_calculator_footprints.csv` assumes mineral soil.
* **Lever link:** L11 lists 8,500 t at about €11/t, which is a design estimate.

**Caveats:** the soil map is only about 88 % accurate by design. The figure does not correct for map errors, for survey rows that already report organic soil, or for delivered kg allocation. The docs call the peat result the intended lesson, not a statement about Apetit's real growers. Route flagged farms to an expert; do not accuse them of misreporting.

### Yield model feasibility [RUN, with caveats]

A quick test: gradient boosting, Finland only, trained on years up to 2022, tested on 2023–2026, using May–August monthly weather from the nearest cell.

| Crop | Train / test rows | Parcel nRMSE, farm mean → model | Aggregate MAPE, farm mean → model |
|---|---:|---:|---:|
| Turnip rape | 1,348 / 654 | 0.206 → 0.144 | 12.8 % → 6.5 % |
| Pea | 694 / 343 | 0.212 → 0.164 | 15.8 % → 11.3 % |
| Potato | 85 / 48 | 0.134 → 0.119 | 6.6 % → 6.4 % |
| Spinach | 108 / 44 | 0.143 → 0.147 | 10.2 % → 10.4 % |
| Carrot | 63 / 32 | 0.132 → 0.138 | 8.5 % → 8.8 % |

**This is a feasibility signal, not a benchmark, and it is optimistic:**

* It used same-year farm inputs (N, sprays, irrigation) that are not known for 2027–2031.
* It only removed yields above 3× the crop median and did not fix other survey errors or swapped coordinates.
* The test covers only four years and uses farm-level survey rows, not the C1 parcel scoring.
* It did not cover Sweden, which is 38 % of C1 rows and has no parcel-level training yields.
* Daily-weather features built on crop stages should do better, since the truth model works that way.

FI yields clearly vary by season [RUN]. For example, pea was 2.00 t/ha in 2014 and 3.99 in 2026, and turnip rape 0.94 in 2014 and 1.77 in 2026. Mean yield per hectare for Swedish peas: 2.78 in 2021, 3.81 in 2022, 3.09 in 2026.

### Climate signal, south-west Finland, May–August [RUN]

| Period | Mean T °C | Precip mm | Days ≥ 27 °C per year |
|---|---:|---:|---:|
| Historical 1991–2020 | 14.86 | 239 | 3.5 |
| `ssp126` 2041–2060 | 15.24 | 267 | 2.7 |
| `ssp245` 2041–2060 | 16.20 | 245 | 7.0 |
| `ssp585` 2041–2060 | 17.28 | 243 | 13.5 |

These come from one weather realisation per scenario, while the C2 truth uses a Monte Carlo ensemble. Build your own variation, for example with stochastic resampling. The dataset models no CO2 fertilisation and no adaptation.

### Other checks [RUN]

* **All CSV files:** no fully duplicated rows. Nulls occur only in optional fields, such as `p_test_mgl_latest` (17.7 %), `lot_id`, `reference_doc`, `wbs_element` and `contract_crops` (3.4 %).
* **Shipments:** `tkm` equals `t × km` on every row.
* **Lever costs:** all 27 stated costs reproduce as `(capex / lifetime + opex) / abatement`, with no discounting.
* **Capex:** 2025 ERP capex (€10.33 m) matches `capex_projects` 2025 (€10.326 m). The calculator uses ERP, so `capex_projects` is a cross-check.
* **Carbon price:** the `fragmented_world` path is not always rising. Whether this is intended has not been checked.
* **Emission factors:** 73 of 84 are `calibrated_synthetic` and 11 are `partner_supplied`.
* **Suppliers:** 86 in total, of which 24 provide PCFs.
* **Materials:** no material in `materials.csv` is flagged as EUDR commodity; 4 are flagged SBTN high-impact.

### Top 2024 line items in Scope 3, naive [RUN]

Most of the largest items are rapeseed lines (M101, M102, M104; M103 and M107 use supplier PCFs and their product type was not checked), plus cheese (M133, EF-CHEESE-EU, 12,570 t) and contract turnip rape (11,116 t). Naive results for categories 3 and 7 in this list are contaminated, so re-rank after cleaning.

---

## 7. Accounting rules and traps [DOC unless marked]

### Boundary

* Operational control.
* Grain trade: divested 31 May 2022, and outside the canonical 2021–2025 inventory. It is in the published history, so **published figures are not comparable as they stand**.
* **Foodhills in 2025:** Bjuv operations from December 2025 only. **Swedish farm emissions are not in the 2025 inventory**; they are in full from 2026.
* Pudasjärvi closure and the Kantvik biosteam sale are future changes. Use them in Track B, not in the 2025 inventory.

### Traps

| Trap | Correct handling |
|---|---|
| Credit notes (movement 122) | Legitimate; net against receipts |
| Vessel lots (`uom = TO`) | Legitimate; do not flag |
| Seasonal meter peaks | Legitimate; do not flag |
| Ammonia (R717) | GWP 0; a safety issue, not a CO2e issue |
| GoOs | **The registry overrides the internal log.** A GoO counts only if vintage equals consumption year. Cap at site consumption. The leased head office has no GoO coverage |
| Supplier PCFs | Valid for a year only if the reference period covers it and values are per kg |
| Biogenic CO2 | A memo item, not in Scope 1 |
| Refrigerant top-ups | Treated as same-year emissions |
| Fuels | Consumption = deliveries − stock change; convert using NCV |
| Water | GRI 303 does not count reused water as withdrawal (E12) |
| Biological N fixation by peas | Not an N input |
| Categories 11 and 12 | Method choices differ from the Apetit sample. Discuss them; do not copy |
| Apetit sample workbook | **Not the answer**; copying scores poorly. Apetit said not to focus on it |
| Levers L05, L26, L27 | Structural or measurement changes, **not reductions** |
| Spend to supplier-specific data | Not an emission reduction (E39) |
| Removals from catch crops | Optional under LSR; must be monitored, traceable, with reversals accounted for |
| Soy protein isolate | HS 3504 is not in EUDR Annex I, though soy beans, oil and meal are. Screen HS codes, not names. Rapeseed is not a relevant commodity |

### Contract-farm footprint per hectare

| Source | Formula | FLAG? |
|---|---|---|
| Fertiliser manufacture | N × 3.7 (or 0.9 low-carbon) + P × 1.6 + (2.2 × P) × 0.5 | No |
| Direct N2O | (N_min × 0.016 + (N_man + N_res) × 0.006) × 44/28 × 273 | Yes |
| Indirect N2O | [(N_min × 0.05 + N_man × 0.21) × 0.014 + (N_min + N_man + N_res) × 0.24 × 0.011] × 44/28 × 273 | Yes |
| Diesel | litres × (2.10 FI or 2.45 SE + 0.61 WTT) | No |
| Liming | t × 0.44 t CO2/t | Yes |
| Drained organic soil | 29.0 t CO2/ha (20.9 grass) + 13 kg N2O-N/ha | Yes |
| Pesticides | 8 kg CO2e per pass | No |
| Electricity | (kWh/t × yield + 180 if irrigated) × grid factor | No |

Allocation: farm emissions ÷ delivered kg. Rejections stay with the delivered product. Commodity FLAG shares come from `flag_share` in the factor library.

### Code pitfalls in `tools/ccn_tools` [RUN, read from code]

* `naive_canonical` uses the **internal** GoO log and does no cleaning. Replace it. The registry file has a different schema (`consumption_year`, `beneficiary_site`, `mwh`, production period dates), so derive the vintage from the production period.
* `naive_farm_footprints` trusts reported soil, labels everything `FI_SW`, and fills non-respondents with the crop-year median of respondents.
* `farm_footprint_per_ha` defaults to a grid factor of 0.03 (the 2024 value; 2025 is 0.026) and always uses the 2.10 diesel factor. METHODOLOGY gives 2.45 for Sweden, while `factors.py` has an unused `diesel_ttw_fossil` of 2.66. **Check this before modelling Swedish farms.**
* The calculator applies the short-haul flight factor to all flights.
* `compute_inventory` needs the canonical tables in METHODOLOGY §2.
* `score_d1` on the **dev** key computes the true rank from loads only, without state weight or sensitivity, so the dev rank part does not fully match the hidden formula.
* The A2 dev files differ in length: 2023 has 21 rows and 2024 has 19, because of purchased heat lines. Check the 2025 template's 19 rows against what you produce.
* `reference_calculator` treats a missing heat supplier factor as 0.

### Framework facts [DOC, `data/07_frameworks/framework_digest.md`, status 3 Nov 2026]

* **FLAG:** mandatory for food production and processing. Requires a deforestation commitment. FLAG covers on-farm N2O and CH4, drained organic soils, liming, land-use change and soil carbon. Fertiliser manufacture, farm diesel and processing are non-FLAG.
* **Long term:** at least −90 % for Scope 1+2 and Scope 3 by 2050; FLAG −72 % by 2050.
* **GHG Protocol LSR:** v1.1 June 2026, effective 1 Jan 2027.
* **SBTN:** Step 1a materiality, 1b value chain, 2 prioritise (pressure × state), 3 targets, 4 act, 5 track. SBTN 2.0 launched October 2026; V1 valid until April 2027.
* **ESRS:** after the Omnibus, the scope is over 1,000 employees and over €450 m turnover, so Apetit is expected to report voluntarily.
* **ESRS E3:** water stress means Aqueduct baseline "high" or above, or WEI+ of at least 40 %.
* **EUDR:** applies from 30 Dec 2026. **ETS2:** postponed to 2028. **CBAM:** definitive phase from 2026 covers fertilisers.
* Verify against originals in `source_registry.csv` before citing. Framework PDFs can be indexed locally for RAG but must not be republished.

---

## 8. Reference data for Track B and C

### Levers [DOC: design estimates; recompute]

| ID | Lever | 2030 t | €/t | Confidence |
|---|---|---:|---:|---|
| L01 | Biogas to eliminate LNG/LPG back-up at Säkylä | 1,650 | 118 | high |
| L02 | Electric forklifts and yard vehicles | 160 | 44 | high |
| L03 | Replace R404A cold store | 700 | 50 | high |
| L04 | Refrigerant leak detection | 220 | 168 | medium |
| L05 | Kantvik steam from partner (**structural**) | 0 | – | high |
| L06 | Kantvik heat recovery | 300 | 0 | medium |
| L07 | Bjuv natural gas to biogas | 1,300 | 114 | medium |
| L08 | Low-carbon N fertiliser | 2,100 | 124 | medium |
| L09 | Precision N and soil testing | 900 | 133 | medium |
| L10 | Catch crops | 600 | 233 | low |
| L11 | **Shift area off drained peat soils** | 8,500 | 11 | medium |
| L12 | Rewetting pilot | 1,200 | 250 | low |
| L13 | **Rapeseed supplier engagement** | 14,000 | 32 | medium |
| L14 | Origin optimisation, imported rapeseed | 6,500 | 58 | medium |
| L15 | More Finnish rapeseed | 2,500 | 208 | low |
| L16 | Pizza recipe: less cheese and meat | 4,200 | 29 | medium |
| L17 | Soy protein isolate → faba bean | 380 | 237 | medium |
| L18 | rPET 50 % bottles | 550 | 164 | high |
| L19 | Down-gauged frozen film | 450 | 67 | medium |
| L20 | HVO100 trucking | 3,200 | 203 | high |
| L21 | Modal shift for imported seed | 400 | −125 | medium |
| L22 | −18 °C to −15 °C cold chain | 700 | −43 | low |
| L23 | Reduce intake rejection | 300 | −167 | medium |
| L24 | Irrigation scheduling, drip | 120 | 500 | medium |
| L25 | Supplier renewable electricity | 1,300 | 38 | low |
| L26 | Pudasjärvi closure (**structural**) | 0 | – | high |
| L27 | Supplier-specific data (**measurement**) | 0 | – | high |
| L28 | Business travel policy | 40 | −500 | high |
| L29 | Commuting bus, EV charging | 60 | 383 | low |
| L30 | Biowaste to biogas | 150 | −67 | medium |

Full fields, including capex, opex, start year, ramp, co-benefits and trade-offs, are in `decarbonisation_levers.csv`.

### Structural events [DOC]

| Date | Event | Relevance |
|---|---|---|
| 2021-07-01 | Kantvik biosteam plant operating | Scope 2 → Scope 1 (biogenic) |
| 2022-03-10, 2022-05-31 | Baltic and Finnish grain trade sold | Base-year recalculation, category 1 |
| 2023-07-01 | Säkylä energy solution | Scope 2 → Scope 1; LPG back-up 2023–24 |
| 2025-11-27 | Foodhills acquired | Base-year recalculation; about 300 growers enter FLAG |
| 2025-12-01 | SBTi commitment | Targets within 24 months |
| 2026-04-13 | Pudasjärvi closure decided | Scope 1/2 fall, category 1 rises |
| 2026-06-30 | Kantvik biosteam sale announced; closes early 2027 | Biogenic Scope 1 → Scope 2 steam |

### Published history, t CO2e [DOC]

| Year | Scope 1 | Scope 2 market | Scope 3 | Restated | Note |
|---:|---:|---:|---:|---:|---|
| 2019 | 1,247 | 21,860 | 294,108 | | Includes grain trade |
| 2021 | 1,680 | 8,336 | 272,424 | | Includes grain trade |
| 2022 | 1,602 | 5,129 | 201,016 | 186,430 | Divested 31 May 2022 |
| 2023 | 4,229 | 3,174 | 260,931 | 237,886 | LPG back-up |
| 2024 | 6,251 | 63 | 238,410 | | |

The synthetic 2024 truth is Scope 1 6,400, Scope 2 market 63, Scope 3 190,562. It intentionally differs from the published figures.

### Transition scenarios, illustrative [DOC]

| Scenario | SSP proxy | Carbon price €/t, 2030 → 2050 | Electricity €/MWh, 2030 → 2050 | N-fertiliser index, 2030 → 2050 |
|---|---|---:|---:|---:|
| `net_zero_2050` | ssp126 | 160 → 650 | 64.5 → 80.0 | 1.149 → 1.450 |
| `below_2c` | ssp126 | 120 → 380 | 63.3 → 71.5 | 1.125 → 1.284 |
| `low_demand` | ssp126 | 140 → 460 | 63.9 → 74.0 | 1.137 → 1.333 |
| `delayed_transition` | ssp245 | 85 → 600 | 68.2 → 78.4 | 1.103 → 1.419 |
| `fragmented_world` | ssp245 | 75 → 150 | 61.8 → 64.2 | 1.097 → 1.143 |
| `ndcs` | ssp245 | 100 → 185 | 62.6 → 65.3 | 1.112 → 1.164 |
| `current_policies` | ssp585 | 82 → 100 | 62.1 → 62.6 | 1.101 → 1.112 |

### Contract prices, 2025 €/t, and import replacement premium [DOC]

Pea 420 (premium 55 %), pea_SE 410 (55 %), potato 230 (45 %), carrot 290 (40 %), spinach 380 (60 %), turnip rape 470 (8 %).

---

## 9. Complexity assessment [OPINION]

These percentages are rough estimates, not measurements. 100 % is the most complex.

| Rank | Track | Data complexity | Reason |
|---:|---|:--:|---|
| 1 | **A Inventory** | 100 % | Most files, most planted errors, oddities that look like errors |
| 2 | **E Copilot** | 90 % | Spans almost everything, but much easier once A exists |
| 3 | **C Climate risk** | 60 % | Large weather data and some cleaning, but real yields to learn from |
| 4 | **D Nature** | 60 % | Plain tables, but few answers to check against and no published loss coefficients |
| 5 | **B Pathways** | 30 % | Small, tidy files; about 80 % if you count its dependency on A |

**Dependencies:**

* B needs A's line-level output. The public 2024 key has only category totals, with no FLAG split or line items, so it is not a real substitute.
* E is much easier on top of A.
* **C and D1 are the only tasks that can be built without Track A.** They still need to clean the farm survey and farm registry.
* D2 needs clean ERP volumes.
* C is probably easier to validate than D, because it has years of real yields rather than 6 answers.

---

## 10. Recommended direction [OPINION: not yet accepted by the team]

**Build A → B as the core, with E as the interface.** Add C only if ahead at about hour 20. Apetit's central complaint is that reporting alone brings nothing, so an inventory on its own misses the point, but credible decisions need a clean baseline.

| Path | Tracks | Pros | Cons |
|---|---|---|---|
| Audit-ready inventory | A + E | Safest; strong auto-scores | Closest to what Apetit calls wasted effort |
| **Decision Navigator** | **A → B + E, optional C** | **Answers Apetit's real question** | **Most integration work** |
| Field-level risk and nature | C + D | Visual; independent of A; avoids the messiest data | Recommendations lack an inventory and pathway behind them |

**Worth reconsidering:** the team cares about data complexity. C + D, or C alone, avoids most of the messy corporate feeds. The brief calls farming-focused climate risk an "important part", so a very strong Track C is a legitimate choice. A strong Track C could include C3 and a usable € risk view.

**Possible differentiator:** use the parcel to link peat emissions, nutrient runoff into sensitive catchments and yield risk. The output is a ranked list of farms for advisers to contact, which is the "act next week" output the jury rewards. A first version can be a simple peat ranking with no ML.

### Where AI helps

| Job | Method | Guardrail |
|---|---|---|
| Find errors | Rules plus anomaly detection; a language model explains and proposes fixes | Human approves |
| Calculate | **Deterministic code, not AI** | Versioned factors; reproducible |
| Answer questions | Agent with SQL and calculator tools; RAG over frameworks | Refuses answers without evidence |
| Forecast yields | Gradient boosting on agronomic features | Year-block backtests; SHAP |
| Long-term risk | Yield model on scenario weather with simulated variation | Show uncertainty ranges |
| Pathways | Simulator and portfolio optimiser | Separate real, structural and measurement changes |
| Nature | Export-coefficient model calibrated to monitored loads | State that it is a screening tool |

Skip a full knowledge graph and digital twin; a simple lineage table gives most of the benefit.

**"AI service" means** a hosted language model called through an API, such as Azure OpenAI, Claude or OpenAI. Only the copilot and written explanations need it; rules, calculations and pathways run locally.

**Microsoft mapping** [DOC, `docs/AZURE_FABRIC_QUICKSTART.md`]: treat `02_raw_feeds` as bronze, canonical tables as silver and inventory lines as gold, in a Fabric Lakehouse. Use Azure AI Search for RAG, Foundry Agent Service for agents, Power Apps or Power BI for approvals. Hackathon access is unconfirmed, so build with anything and explain the mapping.

### Proposed team split

| Person | Owns |
|---|---|
| Developer 1 | Cleaning rules, correction log, inventory, tested against answer keys |
| Developer 2 | Targets, pathways, action cost comparison |
| Developer 3 | App: review and approve screen, links to source records, charts |
| AI profile | Copilot, written error explanations, farm priority list |
| Project manager | Learns the rules, acts as the "Apetit expert", asks Apetit questions, owns slides, method note and scoring checklist |

### Proposed timeline

| Hours | Work |
|---|---|
| 0–2 | Agree scope, run the scorer, collect questions |
| 2–12 | Cleaning rules, correction log, inventory validated on 2023 and 2024 |
| 2–16 | In parallel, if chosen: yield or nutrient model |
| 12–24 | Base-year logic, FLAG split, recalculated levers, pathways, cost curve |
| 20–30 | Copilot and review screen with approve/reject, source links, map |
| 30–36 | **Feature freeze:** clean-run test, CSVs, method note, slides, rehearsal |

Time has passed since this plan was drafted. Re-base it on the actual remaining time.

### Demo story

1. The draft report is wrong, and the agent shows why.
2. An expert approves the fixes.
3. Every number traces back to its source.
4. The cost curve shows the gap to target and the cheapest way to close it.
5. A copilot answer cites its evidence.
6. The tool shows which farms to call on Monday.

### Suggested first task

Build one thin end-to-end slice for refrigerants: detect errors, log corrections, calculate, trace to source. It is a small table with clear errors, and the pattern can then be copied. The team has not yet taken up this offer.

---

## 11. Open questions

**For the team:**

1. Which track or combination will they commit to?
2. Which language-model API and credits are available?
3. How much of the 36 hours remains, and what is the exact deadline?

**For Apetit:**

1. Would they use a 2019 or a 2025 base year?
2. Who would act on farm-level recommendations?
3. Do teams get Microsoft access?
4. Is the "already automated" GHG calculation in the brief real or a target?

---

## 12. Running the tools

```bash
pip install pandas pyarrow numpy   # plus scikit-learn, scipy, openpyxl as needed
cd tools
python -m ccn_tools     # runs baselines and scores them on dev keys
python quickstart.py    # guided tour

python -m ccn_tools.score A1 --submission my_issues.csv --key ../tasks/dev/A1_dev_issue_labels_2023_2024.csv
python -m ccn_tools.score A2 --submission my_2024.csv --key ../tasks/dev/A2_dev_inventory_2024.csv
python -m ccn_tools.score D1 --submission my_d1.csv --key ../tasks/dev/D1_dev_catchments_2025.csv
python -m ccn_tools.score E  --submission my_answers.csv --key ../tasks/dev/E_dev_answers.csv
```

* `python -m ccn_tools` writes to `outputs/` in the package root. It reproduced the documented baseline scores in this session.
* The system Python on this Mac had none of these libraries, and PDF rendering needs poppler. This session used a scratch virtual environment and a copy of the tools, so the package itself was not modified by the runs. This file is the only thing added to the package.

### Licences [DOC]

* Package data is CC BY 4.0 and code is MIT. Attribution: "Apetit Climate & Nature Navigator synthetic dataset, Since AI ry 2026 (CC BY 4.0)".
* The Apetit workbook is **not** CC BY.
* Free to add: WRI Aqueduct 4.0, SYKE, Luke, FMI, Fingrid, Statistics Finland, GFW, ERA5.
* Check terms first: NGFS, Paituli, Finnish Food Authority parcels, ENCORE, Agribalyse, FAOSTAT.
* Do not redistribute: EXIOBASE, NHM BII, IBAT/KBA, Climate Guide website content.

---

## 13. Limits of this research

**Read in full:** `START_HERE.md`, the Word copy of the brief, the transcript, `docs/*.md`, `framework_digest.md`, `E_questions.csv`, and the Python tools except `__init__.py` and `__main__.py`.

**Not read:**

* `START_HERE.html` (too large; the markdown version was read instead)
* The brief's PDF. It wouldn't open, and it was not compared with the Word copy
* `MANIFEST.json`, `tools/quickstart.ipynb`, `README.md`, the licence files
* `docs/.npp-md-preview.html`, which looks like an editor preview file

**Partly reviewed:**

* The Excel workbook: sheet names and first rows only
* Data files: structure, nulls, exact duplicates and selected value checks. **This was not a row-by-row error audit.** A table with no known issues may still contain some
* PCF JSON: units and structure only, not values or stale periods
* `foodhills_odlingsdata_se`: no planted-issue labels exist, and it was not examined for errors

**Not done:**

* No cleaning pipeline, model, nutrient estimate, pathway or cost curve was built
* No A2 score above the naive baseline was achieved, so how close a cleaned inventory can get to truth is untested
* Tolerances and hidden-test behaviour are known only from the docs and `score.py`

**Corrections made during the conversation.** Earlier statements that should not be repeated:

1. "Track B can start from the 2024 answer key": false. It has only totals.
2. "Track D requires map processing": false. `parcels.csv` already links fields to catchments. The hard part is estimating loads.
3. "Track C's inputs are clean": false. The survey has planted errors, and some farm coordinates look swapped.
