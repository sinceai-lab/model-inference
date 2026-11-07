# Project guide

For people and AI agents picking up this repository. It explains what's here, how to run it, how to change it safely, and how to go back to the last working version.

**What this is:** the climate risk track of the Apetit × Since AI 2026 hackathon. Yield models for contract crops, a viewer for Apetit's farming team and advisors, and a backend that turns FIWARE Context Broker weather notifications into live season estimates.

**All data is synthetic.** Never present results as facts about Apetit or real farms.

## Versions

Each version is a branch that can be run or rolled back to. Later versions may drop functionality if that's what it takes to keep something working.

| Version | Branch | Commit | What it adds | Tested state |
|---|---|---|---|---|
| v1 | None here; use the commit | `61465a5` | Pipeline, first viewer, English and Finnish | Runs, but predates Apetit's feedback |
| v2 | `inference-v2-QA-suggestions` | `9f9383a` | Viewer rebuilt around Apetit's Q&A: advice, farm pages, trust tab | Reviewed and tested |
| v3 | `inference-v3` | Latest on the branch | Data fixes, crop-stage fixes, live backend and mock broker, Map tab, broker handoff | Tests pass; **not yet run against a real broker** |

Inside v3, each feature is a separate merge commit:

| Commit | Feature |
|---|---|
| `4701306` | Data cleaning and crop-stage values |
| `db20c27` | Live season backend and mock broker |
| `50ed4b5` | Map tab |

### Going back

```bash
git checkout inference-v2-QA-suggestions       # run an earlier version
git checkout 61465a5                           # v1, which has no branch in the team repo
git revert -m 1 50ed4b5                        # remove one feature from the current branch, here the map
```

After changing version or reverting, rerun the pipeline, because `cache/` isn't versioned and files in `outputs/` depend on the models. A revert of the data cleaning also leaves later regenerated outputs behind, so rerun before trusting any figure.

### Saving a new version

1. Create a branch from the latest working one, such as `inference-v4`. Build features on `feature/...` branches, using a `git worktree` for each so parallel work can't collide.
2. Merge with `git merge --no-ff`, so each feature can be reverted alone.
3. Rerun the pipeline and tests (see below).
4. Add a row to the table above, then push: `git push -u team inference-v4`.

**Remotes:** `team` is the shared repo, https://github.com/sinceai-lab/model-inference, where work now happens. In a fresh clone it's called `origin`.

## Setup

Developed on Python 3.9; other versions are untested. Clone the repo, and put the **whole** unzipped challenge package next to it. It isn't in this repo, because part of it isn't openly licensed, so never commit it.

```text
parent-folder/
├── model-inference/                       this repo (any folder name)
└── APETIT_CLIMATE_NATURE_NAVIGATOR_2026/  data/, tasks/ and tools/ are all needed
```

Set `APETIT_PACKAGE` to use another location.

```bash
python3 -m venv .venv && source .venv/bin/activate   # check first: python3 --version
pip install -r requirements.txt -r requirements-service.txt
cd src
python features.py          # weather features; writes to cache/
python dataset.py           # clean yields and corrections log
python run_all.py           # trains the models and writes outputs/
python build_map_data.py    # Map tab data
cd ..
```

`python backtest.py` (hyperparameter grid) and `python stage_test.py` (crop-stage values) in `src/` are optional and only needed when reviewing those settings.

## Running things

**Viewer:**

```bash
streamlit run app.py            # http://localhost:8501
```

**Live backend, mock broker and viewer together:**

```bash
python -m service.cli start --writeback --viewer    # backend 8600, mock 8601, viewer 8503
python -m service.cli replay --cell GF0203 --year 2025 --speed 20 --wait
python -m service.cli predictions --cell GF0203 --year 2025 --crop pea
python -m service.cli inject bad_batch              # --help lists the other controls
```

Then open the **Live season** tab.

**Tests:**

```bash
python -m pytest tests          # the end-to-end test needs ports 8600 and 8601 free
```

**Predict from a feature row without the backend,** from `src/`:

```python
import pickle, numpy as np, pandas as pd
models = pickle.load(open("../cache/models.pkl", "rb"))["models"]
rows = pd.read_csv("../docs/cb_handoff/model_input_examples.csv")
print(np.exp(models["pea"].predict_log(rows.iloc[[0]]))[0])
```

## How it fits together

```text
Challenge package ──> features.py + dataset.py ──> run_all.py ──> cache/models.pkl + outputs/*.csv
                                                                       │
             ┌─────────────────────────────────────────────────────────┤
             ▼                                                         ▼
      app.py (viewer)                              service/ (backend, called over HTTP)
      reads outputs/ and runs some                 receives weather, stores it, recalculates
      models directly in its own process           season features, predicts
             ▲                                                         ▲
             └──── live_tab.py reads the backend ──────────────────────┤
                                                                       │ NGSI-LD notifications
                                              mock broker now, real Context Broker later
```

| Path | Purpose |
|---|---|
| `app.py` | The viewer and most of its tabs |
| `map_tab.py`, `live_tab.py` | Map and Live season tabs |
| `i18n.py` | Translations and number formats |
| `src/config.py` | Paths, assumed crop and soil values, model settings |
| `src/features.py` | Daily weather to 16 season features |
| `src/dataset.py` | Yields from the three sources; corrections log |
| `src/models.py` | `YieldModel`: Ridge regression on log yield |
| `src/backtest.py` | Held-out tests and scoring |
| `src/run_all.py` | Trains final models and writes all results |
| `src/inference.py` | `Predictor`: live prediction for a field |
| `src/advisor.py` | Advice rules and field table, free of Streamlit |
| `src/build_map_data.py`, `src/build_handoff_examples.py` | Regenerate map data and broker examples |
| `service/` | Backend, parser, storage, mock broker and CLI |
| `tests/` | Backend and contract tests |
| `docs/cb_handoff/` | **The contract for the Context Broker owner** |
| `docs/CB_INTEGRATION.md` | Backend detail and steps to switch from the mock to a real broker |
| `docs/MAP_ASSESSMENT.md` | What a map can honestly show |
| `docs/CLAUDE_insights_abstract.md` | Early research notes; predates the track C work and includes Apetit contacts' work emails |
| `README.md` | Method, results and limits |

### The models

There's one Ridge regression per crop, saved in `cache/models.pkl`: `models` for up to 2031 and `long_models` for later years. Pea combines Finland and Sweden; `long_models["pea"]` shares one weather response between them. `README.md` has the method and `docs/cb_handoff/README.md` lists every input.

## What Apetit asked for

They judge usefulness to their farming team, advisors and farmers. The auto-scorer doesn't affect their decision. Farmers want graphs and advice, and their stated gap is knowing what to do about a risk. They care most about a hothouse future and staying below 2 °C. Finland and Sweden are separate operations. `README.md` has the detail, and the source is the Q&A recording outside this repo.

## Current results

Held-out regional production error, against 11.0% for the farm average in the leave-one-season-out test.

| Test | Our model |
|---|---:|
| Leave one season out | 4.2% |
| Forward 2022–2026 | 4.0% |

**These are optimistic in three ways:**
- The model is given the actual weather of the season it predicts.
- Settings were chosen on the same seasons. Pea and turnip rape stage values were tested blind, giving about 4.4%, 3.9% (Swedish pea) and 3.3%.
- Tests use farm averages, not single fields.

**Live season estimates** are no better than the farm average until about mid-June (`README.md` has the table). Present them as a mid-season tool.

## Changing things safely

### Rules for every change
- **Text:** wrap viewer text in `t("...")` and add its Finnish line to `i18n.py`, or it silently shows in English. Format numbers with `num()` and `eur()`. Have a Finnish speaker check new text.
- **Charts:** use `draw()` in `app.py`, not `st.altair_chart`. Streamlit otherwise swaps data under a live chart and can leave it blank. Give Altair selections a fixed `name`.
- **Widgets:** give each one a `key`, and use language-neutral codes as options, so selections survive a language change. Defaults go through `st.session_state.setdefault`, not `index=`.
- **Advice:** rules are in `advice()` in `src/advisor.py`. Each must state its evidence and follow from it. Don't name single weather drivers as causes, because they're correlated; use the three themes.
- **Honest claims:** check on-screen numbers against `outputs/`. Label modelled, assumed and illustrative values.
- **Don't commit:** the challenge package, `cache/`, `.venv/`, `.scratch/` or `service_data/`.

### After changing data, features or model settings
Rerun in this order, then the tests:

```bash
cd src
python features.py && python dataset.py && python run_all.py && python build_map_data.py && python build_handoff_examples.py
cd ..
cp docs/cb_handoff/*.json docs/cb_handoff/*.csv tests/fixtures/cb_handoff/
python -m service.replay_eval      # refreshes outputs/live_season_replay.csv
python -m pytest tests
```

Then update figures in `README.md`, this guide and `docs/cb_handoff/README.md`. Commit `outputs/` only when results are meant to change, to avoid merge conflicts.

### Common traps
| Symptom | Cause |
|---|---|
| Viewer shows old advice or an error about models | Restart Streamlit: `src/` modules and cached models aren't reloaded |
| `Port 8501 is already in use` | The old server hasn't released the port yet; wait a moment |
| Features look stale | They're cached by crop settings; rerun `features.py` after changing `features.py` itself |
| Language change returns to the first tab | Known Streamlit limit, because it tracks tabs by label |
| Streamlit `AppTest` fails in Finnish after changing a dropdown | A test tool limit; set `session_state` before a fresh run instead |

## Connecting the real Context Broker

The broker sends daily weather per grid cell as NGSI-LD `WeatherObserved`, and the backend does the rest. `docs/cb_handoff/README.md` is the contract, with examples; `docs/CB_INTEGRATION.md` has the switching steps. Nothing has run against a real broker yet.

**The most likely blocker:** the backend binds to `127.0.0.1`, so a broker in Docker or on another machine can't reach it until that changes.

## Known limits

- **Advice:** draft rules written without an agronomist; have an advisor review them. Sowing date and variety aren't in the data, so neither can be recommended.
- **Crop-stage values:** pea and turnip rape values were tuned on the same seasons, and an advisor should sanity-check them. Other crop and soil values are assumptions.
- **Pea model choice:** after the crop-stage fix, the shared weather response used for long-range pea tests worse than the separate one (forward test: Sweden 4.0% against 2.1%, Finland 5.6% against 4.5%). It's kept because 9 Swedish seasons are thin for a separate long-range response. This needs a fresh decision.
- **Risk figures:** season error, bad-year rates and euro risk use the tuned values, so they may be slightly low.
- **Weather step at 2027:** the supplied scenario weather turns cooler than recent years, so forecasts can show a step that isn't real.
- **Swedish pea:** relies on Finland's delivered-to-yield ratio, which can't be tested.
- **Map:** risk has almost no geographic pattern in this data. It's a way into a farm, not a map of where risk sits. Positions are synthetic, and clicks are slower without a GPU.
- **Costs:** the premium on replaced volume only. Excludes emissions, lost margin, price shocks and payments to farmers after a poor crop.
- **Finnish:** not checked by a native speaker.

## Next steps

Not started:
- Connect the real broker, then answer the questions in `docs/CB_INTEGRATION.md`.
- Add a soil-by-climate chart for advisors. It's the clearest honest finding.
- Try a live map replay, showing farms updating as a season arrives. First check that one season's weather varies enough across the map.
- Add an MCP server over `src/advisor.py` and the backend, and combine model inferences with Context Broker data to answer questions.
