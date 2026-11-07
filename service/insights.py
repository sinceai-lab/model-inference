"""Read-only insights for apetit-ui, from the same outputs files and src/ functions as app.py and map_tab.py, so the
numbers match the Streamlit viewer. Free of web code so an MCP server can reuse it. See docs/INSIGHTS_API.md."""
import math
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import service  # noqa: F401
from advisor import CONFIDENCE, STORIES, THEME_ORDER, advice, field_table, input_use, policy_paths, season_summary, themes
from backtest import metrics
from config import DATA, OUT

REGION = {"FI_SW": "Finland", "SE_SKANE": "Sweden"}
CROP = {"pea": "Pea", "turnip_rape": "Turnip rape", "potato": "Potato", "carrot": "Carrot", "spinach": "Spinach"}
REGION_CROPS = {"FI_SW": list(CROP), "SE_SKANE": ["pea"]}
STORY = {"below_2c": "Below 2 °C", "current_policies": "Hothouse"}
BLURB = {"below_2c": "More policy costs, such as carbon and fuel.", "current_policies": "More physical risk in the field, though not for every crop."}
SCENARIO = {ssp: story for story, ssp in STORIES.items()}
COST_SCENARIO = {"baseline": "Today's climate", **{ssp: STORY[story] for ssp, story in SCENARIO.items()}}
TEST = {"loyo": "Leave one season out", "forward": "Predict 2022–2026 from earlier seasons"}
WEATHER = {"history": ("Historical weather (1991–2026)", "historical", (1991, 2026)), "c1": ("SSP2-4.5, the C1 forecast seasons (2027–2031)", "ssp245", (2027, 2031)),
           "low": ("SSP1-2.6, low emissions (2041–2060)", "ssp126", (2041, 2060)), "middle": ("SSP2-4.5, middle emissions (2041–2060)", "ssp245", (2041, 2060)),
           "high": ("SSP5-8.5, high emissions (2041–2060)", "ssp585", (2041, 2060))}
IRRIGATION = {"usual": ("Farm's usual practice", None, ["FI_SW", "SE_SKANE"]), "irrigated": ("Irrigated", 1.0, ["SE_SKANE"]), "rainfed": ("Not irrigated", 0.0, ["SE_SKANE"])}
IRRIGATION_NOTE = "Only available for Sweden, where 167 farms switch practice. No Finnish farm does, so the effect can't be measured there."
PEA_METHOD = {"baseline": "Baseline", "regional_weather_response": "Separate weather response", "shared_weather_response": "Shared weather response"}
EDGES = [-0.06, -0.04, -0.02, 0.02, 0.04, 0.06]  # map_tab.EDGES
DRY = ("sand", "fine_sand")
WEATHER_TABLE = [("Sowing day of year", "sow_doy"), ("Maturity day of year", "mat_doy"), ("Drought stress, sensitive stage (0–1)", "stress_sens"), ("Heat days at 27 °C or above, sensitive stage", "hot_sens"),
                 ("Rain in 14 days after sowing (mm)", "rain_postsow"), ("Rain in 10 days before harvest (mm)", "rain_preharv"), ("Warm, wet days, July–August", "blight_days"), ("May mean temperature (°C)", "may_t")]

FILES = ["C1_forecast_comparison.csv", "C2_detail_with_uncertainty.csv", "C2_bad_year_check.csv", "C3_euro_risk.csv", "C3_irrigation_evidence.csv", "C3_irrigation_se_within_farm.csv", "advisor_drivers.csv",
         "advisor_season_shift.csv", "backtest_predictions.csv", "backtest_pea_models.csv", "backtest_summary.csv", "live_season_replay.csv", "map_farms.csv", "map_soil_effects.csv", "yield_corrections_log.csv"]
PACKAGE_FILES = {"package/05_scenarios/transition_scenarios.csv": "05_scenarios/transition_scenarios.csv", "package/03_farming/farm_survey_fi.csv": "03_farming/farm_survey_fi.csv",
                 "package/03_farming/foodhills_odlingsdata_se.csv": "03_farming/foodhills_odlingsdata_se.csv"}
RESULT_FILES = {"risk": "C2_detail_with_uncertainty.csv", "drivers": "advisor_drivers.csv", "shift": "advisor_season_shift.csv", "cost": "C3_euro_risk.csv", "bad_check": "C2_bad_year_check.csv",
                "irrigation": "C3_irrigation_evidence.csv", "irrigation_seasons": "C3_irrigation_se_within_farm.csv"}
# Columns each file must have, so a truncated or garbled file is refused instead of half-read.
COLUMNS = {"C1_forecast_comparison.csv": ["region", "crop", "year", "model_t_ha", "package_baseline_t_ha"],
           "C2_detail_with_uncertainty.csv": ["region", "crop", "scenario", "mean_yield_change_pct", "p_bad_year", "change_min", "change_max"],
           "C2_bad_year_check.csv": ["region", "crop", "seasons", "observed_bad", "p_bad_today"],
           "C3_euro_risk.csv": ["region", "crop", "ssp", "expected_cost_eur_yr", "added_vs_todays_climate_eur_yr"],
           "C3_irrigation_evidence.csv": ["region", "crop", "within_farm_uplift_pct"], "C3_irrigation_se_within_farm.csv": ["year", "uplift_pct"],
           "advisor_drivers.csv": ["region", "crop", "ssp", "driver", "effect"], "advisor_season_shift.csv": ["region", "ssp", "sow_doy", "mat_doy", "crop"],
           "backtest_predictions.csv": ["farm_id", "crop", "region", "year", "area_ha", "yield_t_ha", "pred_model", "pred_baseline", "test"],
           "backtest_pea_models.csv": ["test", "region", "method", "production_error", "yield_error"], "backtest_summary.csv": ["mape", "nrmse"],
           "live_season_replay.csv": ["test", "known_until", "scope", "method", "production_error"],
           "map_farms.csv": ["region", "crop", "farm_id", "lat", "lon", "change_below_2c", "change_current_policies"],
           "map_soil_effects.csv": ["region", "crop", "soil", "change_below_2c", "change_current_policies", "stress_today"],
           "yield_corrections_log.csv": ["record_key", "field", "old_value", "new_value", "rule", "source", "used_for_yield"]}

SCENARIO_LABEL = "Scenario results, 2041–2060 against 1991–2020"
DRAFT_NOTE = "Draft rules for advisors to review, not proven recommendations. Each one shows the evidence behind it."
COLOUR_NOTE = ("What the colour means: the model's estimated yield change, from the crop, the climate story and the field's soil. What it doesn't mean: that a place is safer or riskier. "
               "In this data, neighbouring farms are no more alike than random ones, and differences between weather-grid squares are mostly noise from a single simulated weather run, so the colour leaves them out. "
               "The soil map is only about 88% accurate, soil water capacities are our assumption, and irrigation is not part of the colour.")
DISCLAIMER = "All farms, fields and yields are synthetic (Apetit × Since AI 2026 package). These are not findings about real farms."


class MissingOutput(Exception):
    """An outputs file is missing or has never loaded."""

    def __init__(self, file):
        super().__init__(f"outputs/{file} is missing or unreadable. Run src/run_all.py.")
        self.file = file


class NotFound(LookupError):
    """Valid codes, but nothing there."""


class Invalid(ValueError):
    """A request value that passes its type but breaks a rule, for example irrigation on a Finnish parcel."""

    def __init__(self, field, message, value=None):
        super().__init__(message)
        self.field, self.value = field, value


def _iso(ns):
    return datetime.fromtimestamp(ns / 1e9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scrub(text):
    """Drop directories from paths in error text, keeping the file name."""
    return None if text is None else re.sub(r"(?:[A-Za-z]:)?(?:/[^/\s'\":]+)+/([^/\s'\":]+)", r"\1", str(text))


def clean(x):
    """Plain JSON values: numpy scalars to Python, NaN to null."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(float(x)) else float(x)
    if x is pd.NA or x is pd.NaT:
        return None
    return x


def fmt(value, spec):
    """English branch of i18n.num and i18n.eur."""
    if spec is None:
        return str(value)
    if spec == "eur":
        return f"{'-' if value < 0 else ''}€{abs(value):,.0f}"
    return format(value, spec)


def sentence(code, template, **values):
    return dict(code=code, template=template, values={k: [clean(v), s] for k, (v, s) in values.items()}, text=template.format(**{k: fmt(v, s) for k, (v, s) in values.items()}))


def _rule(r):
    return dict(rule=r["rule"], decision=r["decision"], evidence=r["evidence"], **sentence(r["rule"], r["text"], **r["values"]))


def _soil(name):
    return name.replace("_", " ")


def _int_or_none(v):
    return None if pd.isna(v) else int(v)


class Insights:
    def __init__(self, engine, out=None, data=None):
        self.engine, self.out, self.data = engine, Path(out or OUT), Path(data or DATA)
        self.lock = threading.RLock()
        self.frames, self.errors = {}, {}  # name -> (stamp, DataFrame); name -> last load error
        self._package, self._results, self._fields, self._c1 = (None, None), (None, None), OrderedDict(), {}

    # ------------------------------------------------------------ files
    def path(self, name):
        return self.data / PACKAGE_FILES[name] if name in PACKAGE_FILES else self.out / name

    def stamp(self, name):
        try:
            s = self.path(name).stat()
            return s.st_mtime_ns, s.st_size
        except OSError:
            return None

    def frame(self, name):
        """The file's DataFrame, reread only when its stamp changes. A file that fails to load keeps the last good copy."""
        stamp = self.stamp(name)
        with self.lock:
            held = self.frames.get(name)
            if held and held[0] == stamp:
                return held[1]
            if stamp is None:
                self.errors[name] = "File is missing."
            else:
                try:
                    df = pd.read_csv(self.path(name))
                    lacking = [c for c in COLUMNS.get(name, []) if c not in df.columns]
                    if lacking:
                        raise ValueError(f"Missing columns: {', '.join(lacking)}")
                    self.frames[name], self.errors[name] = (stamp, df), None
                    return df
                except Exception as e:
                    self.errors[name] = scrub(f"Couldn't load {name}: {e}")
            if held:
                return held[1]
            raise MissingOutput(name)

    def package(self):
        """advisor.policy_paths() and advisor.input_use(), reread when a package file changes."""
        stamp = tuple(self.stamp(n) for n in PACKAGE_FILES)
        with self.lock:
            if self._package[0] != stamp:
                try:
                    self._package = (stamp, (policy_paths(), input_use()))
                    for n in PACKAGE_FILES:
                        self.errors[n] = None
                except Exception as e:
                    for n in PACKAGE_FILES:
                        self.errors[n] = scrub(f"Couldn't load the package's price and input files: {e}")
                    if self._package[1] is None:
                        raise MissingOutput("package/05_scenarios/transition_scenarios.csv")
            return self._package[1]

    def results(self):
        """Same dict as advisor.load_outputs(), built from the cached frames."""
        frames = {k: self.frame(f) for k, f in RESULT_FILES.items()}
        policy, inputs = self.package()
        stamp = tuple(id(f) for f in frames.values()) + (id(policy),)
        with self.lock:
            if self._results[0] != stamp:
                self._results = (stamp, dict(frames, policy=policy, inputs=inputs))
            return self._results[1]

    def basis(self, kind, label, files):
        self.engine.refresh()
        models = self.engine.stamp[0] if self.engine.stamp else None
        sources, stale = [], False
        for f in files:
            stamp = self.stamp(f)
            sources.append(dict(file=f, generated_at=_iso(stamp[0]) if stamp else None))
            if f not in PACKAGE_FILES and stamp and models and stamp[0] < models:
                stale = True
        return dict(kind=kind, label=label, model_version=self.engine.version, sources=sources, stale_vs_model=stale)

    # ------------------------------------------------------------ helpers
    @property
    def predictor(self):
        self.engine.refresh()
        with self.lock:
            return self.engine.predictor

    def fields_of(self, farm, crop):
        """advisor.field_table, kept per model version."""
        key = (self.engine.version, farm, crop)
        with self.lock:
            if key in self._fields:
                self._fields.move_to_end(key)
                return self._fields[key]
        table = field_table(self.predictor, farm, crop)
        with self.lock:
            self._fields[key] = table
            while len(self._fields) > 1024:
                self._fields.popitem(last=False)
        return table

    def _pair(self, region, crop):
        if (region, crop) not in CONFIDENCE:
            raise NotFound(f"No climate results for {crop} in {region}. Pairs with results: {', '.join(f'{r}/{c}' for r, c in CONFIDENCE)}.")

    def _risk(self, region, crop, ssp):
        return self.results()["risk"].query("region == @region and crop == @crop and scenario == @ssp").iloc[0]

    def _effects(self, region, crop):
        return self.frame("map_soil_effects.csv").query("region == @region and crop == @crop").set_index("soil")

    def _why(self, results, region, crop, story, effects):
        theme = themes(results, region, crop, STORIES[story])
        top = theme.abs().idxmax()
        col = "change_" + story
        worst, best = effects[col].idxmin(), effects[col].idxmax()
        return [sentence("largest_theme", "Largest modelled effect: {theme}, {effect}. Weather measures overlap, so read this as a theme, not a proven cause.", theme=(top.lower(), None), effect=(theme[top], "+.1%")),
                sentence("soil_spread", "Soil moves it: {worst} on {worst_soil}, {best} on {best_soil}. These are region-wide figures for each soil, using water capacities we assumed.",
                         worst=(effects.loc[worst, col], "+.1%"), worst_soil=(_soil(worst), None), best=(effects.loc[best, col], "+.1%"), best_soil=(_soil(best), None))]

    def _farm_ids(self, region, crop=None):
        prefix = region == "SE_SKANE"
        return sorted({k[0] for k in self.engine.farm_mean.index if (crop is None or k[1] == crop) and k[0].startswith("S") == prefix})

    def _grows(self, farm, crop):
        if (farm, crop) not in self.engine.farm_mean.index:
            raise NotFound(f"Farm {farm} doesn't grow {crop}, or isn't in the model.")

    # ------------------------------------------------------------ meta and options
    def meta(self):
        self.engine.refresh()
        st = self.engine.models_path.stat() if self.engine.models_path.exists() else None
        models = self.engine.stamp[0] if self.engine.stamp else None
        files = []
        for f in FILES + list(PACKAGE_FILES):
            rows = None
            try:
                rows = len(self.frame(f)) if f in FILES else None
                if f not in FILES:
                    self.package()
            except MissingOutput:
                pass
            stamp = self.stamp(f)
            files.append(dict(file=f, generated_at=_iso(stamp[0]) if stamp else None, rows=rows, load_error=self.errors.get(f),
                              stale_vs_model=bool(f in FILES and stamp and models and stamp[0] < models)))
        return dict(model_version=self.engine.version, models_file_date=_iso(st.st_mtime_ns) if st else None, model_load_error=scrub(self.engine.load_error), files=files,
                    synthetic=True, disclaimer=DISCLAIMER, basis=self.basis("batch", "Files behind the insight pages", FILES))

    def options(self, region=None, crop=None, farm_id=None):
        out = dict(regions=[dict(code=r, label=REGION[r], crops=REGION_CROPS[r]) for r in REGION], crops=[dict(code=c, label=CROP[c]) for c in CROP],
                   stories=[dict(code=s, label=STORY[s], ssp=ssp, blurb=BLURB[s]) for s, ssp in STORIES.items()],
                   advice_pairs=[dict(region=r, crop=c, confidence=v) for (r, c), v in CONFIDENCE.items()], tests=[dict(code=k, label=v) for k, v in TEST.items()],
                   weather_sets=[dict(code=k, label=v[0], scenario=v[1], years=list(v[2])) for k, v in WEATHER.items()],
                   irrigation=[dict(code=k, label=v[0], share=v[1], regions=v[2]) for k, v in IRRIGATION.items()], irrigation_note=IRRIGATION_NOTE)
        if region:
            if crop and crop not in REGION_CROPS[region]:
                raise NotFound(f"{REGION[region]} has no {crop} contracts in the model. Crops there: {', '.join(REGION_CROPS[region])}.")
            out["farms"] = self._farm_ids(region, crop)
        if farm_id:
            p = self.engine.parcels[self.engine.parcels.farm_id == farm_id]
            if p.empty:
                raise NotFound(f"Unknown farm {farm_id!r}.")
            out["parcels"] = [dict(parcel_id=i, area_ha=r.area_ha, soil=r.soil_class_soilmap, drainage=r.drainage, cell_id=r.cell_id) for i, r in p.iterrows()]
        out["basis"] = self.basis("model", "Choices the model and its files cover", [])
        return clean(out)

    # ------------------------------------------------------------ risk, advice and outlook
    def advice(self, region, crop, story):
        self._pair(region, crop)
        res = self.results()
        stories = []
        for name, ssp in STORIES.items():
            risk = self._risk(region, crop, ssp)
            added = res["cost"].query("region == @region and crop == @crop and ssp == @ssp").iloc[0].added_vs_todays_climate_eur_yr
            stories.append(dict(story=name, label=STORY[name], ssp=ssp, yield_change=risk.mean_yield_change_pct / 100, yield_change_low=risk.change_min / 100, yield_change_high=risk.change_max / 100,
                                bad_year_chance=risk.p_bad_year, added_import_cost_eur_yr=added))
        seen = res["bad_check"].query("region == @region and crop == @crop").iloc[0]
        theme = {name: themes(res, region, crop, ssp) for name, ssp in STORIES.items()}
        seasons = {name: season_summary(res, region, crop, ssp) for name, ssp in STORIES.items()}
        measures = [("maturity", "Reaches maturity", "maturity_days_earlier")] + ([] if region == "SE_SKANE" else [("sowing", "Warm enough to sow", "sowing_days_earlier")])
        first = seasons["below_2c"]
        table = [("Days at 27 °C or above", "hot_days_today", "hot_days", 1), ("Warm, wet days, July–August", "wet_days_today", "wet_days", 1), ("Drought stress, sensitive stage (0–1)", "stress_today", "stress", 2)]
        return clean(dict(
            region=region, crop=crop, story=story, confidence=CONFIDENCE[(region, crop)], stories=stories,
            bad_years_so_far=dict(bad_year_chance_today=seen.p_bad_today, seen=round(seen.observed_bad * seen.seasons), seasons=int(seen.seasons)),
            actions=[_rule(r) for r in advice(res, region, crop, story)], actions_note=DRAFT_NOTE,
            themes=[dict(theme=th, **{name: theme[name][th] for name in STORIES}) for th in THEME_ORDER],
            themes_note="Weather measures rise and fall together, so single measures can't be separated reliably. That's why they're grouped into themes. The effects are the model's estimates, not proven causes.",
            season_shift=[dict(measure=m, label=lab, unit="days earlier than today", **{name: seasons[name][k] for name in STORIES}) for m, lab, k in measures],
            season_table=[dict(measure=lab, today=round(first[now], n), **{name: round(seasons[name][then], n) for name in STORIES}) for lab, now, then, n in table],
            season_note="Calculated from daily weather using our assumed crop thresholds, so read the change rather than the dates. Sowing is estimated from temperature alone and capped at 10 April, so its shift is a minimum, and real sowing also depends on the soil. It isn't shown for Swedish peas, where most years hit that cap.",
            why=self._why(res, region, crop, story, self._effects(region, crop)),
            basis=self.basis("batch", SCENARIO_LABEL, list(RESULT_FILES.values()) + ["map_soil_effects.csv"] + list(PACKAGE_FILES))))

    def policy(self):
        res = self.results()
        p = res["policy"]
        inputs = res["inputs"].reset_index()
        return clean(dict(paths=[dict(story=r.scenario, label=STORY[r.scenario], year=int(r.year), fertiliser_change=r.n_fertiliser_price_index - 1, diesel_change=r.diesel_price_index - 1, carbon_eur_t=r.carbon_price_eur_t) for r in p.itertuples()],
                          inputs=[dict(region=r.region, crop=r.crop, n_kg_ha=r.n_mineral_kg_ha, diesel_l_ha=r.diesel_l_ha) for r in inputs.itertuples()],
                          note="Illustrative price paths from the challenge package, not forecasts. Changes are against 2025.",
                          basis=self.basis("batch", "Illustrative package values", list(PACKAGE_FILES))))

    def outlook(self, region, crop):
        fc = self.frame("C1_forecast_comparison.csv")
        q = fc[(fc.region == region) & (fc.crop == crop)]
        if q.empty:
            raise NotFound(f"No 2027–2031 forecast for {crop} in {region}.")
        held = self.frame("backtest_predictions.csv")
        h = held[(held.test == "loyo") & (held.region == region) & (held.crop == crop)]
        hist = h.groupby("year").apply(lambda d: np.average(d.yield_t_ha, weights=d.area_ha), include_groups=False)
        return clean(dict(region=region, crop=crop, history=[dict(year=int(y), actual_t_ha=v) for y, v in hist.items()],
                          forecast=[dict(year=int(r.year), model_t_ha=r.model_t_ha, baseline_t_ha=r.package_baseline_t_ha) for r in q.itertuples()],
                          note="Baseline here is the package's reference method: the farm's survey average since 2016, or a fixed 3.4 t/ha for Swedish peas. It varies slightly between years only because the planted fields change. Our model reacts to one supplied weather realisation for 2027–2031.",
                          warning="No answers are public for these tasks, so neither method can be scored here. The Can we trust this? page shows how the model did on past seasons. These charts are the model's estimates, not measured accuracy.",
                          basis=self.basis("batch", "Forecast 2027–2031, one supplied SSP2-4.5 weather run", ["C1_forecast_comparison.csv", "backtest_predictions.csv"])))

    def climate_risk(self, scenario):
        d = self.frame("C2_detail_with_uncertainty.csv")
        d = d[d.scenario == scenario].sort_values("mean_yield_change_pct")
        rows = [dict(region=r.region, crop=r.crop, mean_yield_change_pct=r.mean_yield_change_pct, change_min_pct=r.change_min, change_max_pct=r.change_max, bad_year_chance=r.p_bad_year,
                     baseline_change_pct=0.0, baseline_bad_year_chance=0.10, confidence=CONFIDENCE.get((r.region, r.crop))) for r in d.itertuples()]
        return clean(dict(scenario=scenario, story=SCENARIO[scenario], label=STORY[SCENARIO[scenario]], rows=rows,
                          note="Dot: our estimate. Line: the range when each training season is left out in turn, which is not total uncertainty. Zero is the package's baseline of no change. Swedish peas (9 seasons), Finnish peas and carrot are low confidence.",
                          basis=self.basis("batch", SCENARIO_LABEL, ["C2_detail_with_uncertainty.csv"])))

    def euro_risk(self):
        e = self.frame("C3_euro_risk.csv")
        totals = e.groupby(["region", "ssp"]).expected_cost_eur_yr.sum().unstack("ssp")[list(COST_SCENARIO)]
        e = e[e.ssp.isin(COST_SCENARIO)]
        cols = ["area_ha", "price_eur_t", "premium", "baseline_t", "mean_shortfall_t", "expected_cost_eur_yr", "bad_year_p90_cost_eur", "added_vs_todays_climate_eur_yr"]
        return clean(dict(totals=[dict(region=r, **{s: totals.loc[r, s] for s in COST_SCENARIO}) for r in totals.index], scenarios=[dict(code=k, label=v) for k, v in COST_SCENARIO.items()],
                          by_crop=[dict(region=r.region, crop=r.crop, scenario=r.ssp, **{c: getattr(r, c) for c in cols}) for r in e.itertuples()],
                          note="Expected € a year: shortfall against today's average × 2025 contract price × replacement premium. It counts only the premium, and excludes import emissions, lost margin, price shocks and what Apetit still pays farmers after a poor crop, which isn't in the data. The Swedish figures are low confidence.",
                          basis=self.basis("batch", "Scenario results, 2041–2060, € a year", ["C3_euro_risk.csv"])))

    # ------------------------------------------------------------ farms, fields and soil
    def farms(self, region, crop):
        self._pair(region, crop)
        f = self.frame("map_farms.csv").query("region == @region and crop == @crop").sort_values(["planned_dry_ha", "dry_ha"], ascending=False)
        cols = ["farm_id", "lat", "lon", "n_fields", "area_ha", "dry_fields", "dry_ha", "dry_share", "planned_fields", "planned_ha", "planned_dry_ha", "change_below_2c", "change_current_policies"]
        return clean(dict(region=region, crop=crop, farms=[{c: getattr(r, c) for c in cols} for r in f.itertuples()], labelled=f.farm_id.head(8).tolist(), bands=dict(edges=EDGES),
                          order_note="Most hectares planned for this crop in 2027–2028 on sand or fine sand first.", note=COLOUR_NOTE,
                          basis=self.basis("batch", SCENARIO_LABEL, ["map_farms.csv"])))

    def soil_effects(self, region, crop):
        self._pair(region, crop)
        e = self._effects(region, crop)
        cols = ["n_fields", "area_ha", "change_below_2c", "change_current_policies", "stress_today", "stress_below_2c", "stress_current_policies"]
        return clean(dict(region=region, crop=crop, soils=[dict(soil=s, label=_soil(s), droughty=s in DRY, **{c: r[c] for c in cols}) for s, r in e.iterrows()],
                          note="These are region-wide figures for each soil, using water capacities we assumed. The soil map is only about 88% accurate.",
                          basis=self.basis("batch", SCENARIO_LABEL, ["map_soil_effects.csv"])))

    def farm(self, farm_id, crop, story):
        self._grows(farm_id, crop)
        region = "SE_SKANE" if farm_id.startswith("S") else "FI_SW"
        self._pair(region, crop)
        res = self.results()
        rows = self.frame("map_farms.csv").query("region == @region and crop == @crop and farm_id == @farm_id")
        if rows.empty:
            raise NotFound(f"No map row for farm {farm_id} and {crop}.")
        row, other = rows.iloc[0], "below_2c" if story == "current_policies" else "current_policies"
        table, effects = self.fields_of(farm_id, crop), self._effects(region, crop)
        regional = self._risk(region, crop, STORIES[story]).mean_yield_change_pct / 100
        irr = float(self.engine.farm_irr.get((farm_id, crop), 0.0))
        droughty = int(table.droughty_soil.sum())
        why = [sentence("dry_fields", "{n} of {total} fields are on sand or fine sand, which we assume hold the least water. Prioritise them in dry-season guidance.", n=(droughty, "d"), total=(len(table), "d")) if droughty
               else sentence("dry_fields", "None of the {total} fields are on sand or fine sand, the soils we assume hold the least water.", total=(len(table), "d"))]
        if row.planned_fields:
            why.append(sentence("planned", "{n} fields are planned for this crop in 2027–2028, {area} ha of it on sand or fine sand.", n=(int(row.planned_fields), "d"), area=(row.planned_dry_ha, ".0f")))
        why.append(sentence("irrigation", "This farm's usual irrigated share for this crop: {share}.", share=(irr, ".0%")))
        why.append(self._why(res, region, crop, story, effects)[0])
        by_soil = table.groupby("soil_class_soilmap").yield_today.mean().sort_values(ascending=False)
        return clean(dict(
            farm_id=farm_id, region=region, crop=crop, story=story,
            headline=dict(yield_change=row["change_" + story], yield_change_other_story=row["change_" + other], region_yield_change=regional, dry_share=row.dry_share, dry_fields=int(row.dry_fields), n_fields=int(row.n_fields),
                          planned_fields=int(row.planned_fields), planned_dry_ha=row.planned_dry_ha, usual_irrigated_share=irr),
            risk=sentence("farm_risk", "With this farm's soils, the model estimates {change} for this crop under {story}, against {other} under {other_story}. The whole region under {story}: {regional}.",
                          change=(row["change_" + story], "+.1%"), story=(STORY[story], None), other=(row["change_" + other], "+.1%"), other_story=(STORY[other], None), regional=(regional, "+.1%")),
            why=why, yield_by_soil=[dict(soil=s, label=_soil(s), yield_today_t_ha=v) for s, v in by_soil.items()],
            fields=[self._field_row(r, effects) for r in table.itertuples()],
            fields_warning="Use the field order as a starting point for discussion. The model was trained on farm averages, so differences between fields come mainly from the soil map, which is only about 88% accurate.",
            fields_note="Yields use 2025 technology and the farm's usual irrigation, averaged over 1991–2020 weather. Changes compare 2041–2060 with that average.",
            actions=[_rule(r) for r in advice(res, region, crop, story)], actions_note=DRAFT_NOTE,
            basis=self.basis("model", "Modelled for 2041–2060 against 1991–2020, 2025 technology", ["map_farms.csv", "map_soil_effects.csv", "C2_detail_with_uncertainty.csv"])))

    @staticmethod
    def _field_row(r, effects):
        return dict(parcel_id=r.parcel_id, area_ha=r.area_ha, soil=r.soil_class_soilmap, drainage=r.drainage, droughty=bool(r.droughty_soil), yield_today_t_ha=r.yield_today,
                    change_below_2c=r.change_below_2c, change_current_policies=r.change_current_policies,
                    soil_change_below_2c=effects.loc[r.soil_class_soilmap, "change_below_2c"], soil_change_current_policies=effects.loc[r.soil_class_soilmap, "change_current_policies"],
                    stress_today=r.stress_today, last_grown=_int_or_none(r.last_grown), next_planned=_int_or_none(r.next_planned))

    def field(self, parcel_id, crop, story):
        if parcel_id not in self.engine.parcels.index:
            raise NotFound(f"Unknown parcel {parcel_id!r}.")
        farm_id = self.engine.parcels.loc[parcel_id].farm_id
        self._grows(farm_id, crop)
        region = "SE_SKANE" if farm_id.startswith("S") else "FI_SW"
        self._pair(region, crop)
        table, effects = self.fields_of(farm_id, crop), self._effects(region, crop)
        hit = table[table.parcel_id == parcel_id]
        if hit.empty:
            raise NotFound(f"No modelled yield for {parcel_id} and {crop}.")
        f = next(hit.itertuples())
        soil = f.soil_class_soilmap
        change, regional = effects.loc[soil, "change_" + story], self._risk(region, crop, STORIES[story]).mean_yield_change_pct / 100
        today, future = effects.loc[soil, "stress_today"], effects.loc[soil, "stress_" + story]
        why = [sentence("soil_map", "Soil-map class: {soil}, {area} ha. The soil map is only about 88% accurate.", soil=(_soil(soil), None), area=(f.area_ha, ".1f"))]
        if f.droughty_soil:
            why.append(sentence("droughty", "We assume this soil holds the least water. Prioritise this field in dry-season guidance."))
        why.append(sentence("planned", "Planned for this crop: {year}", year=(int(f.next_planned), "d")) if pd.notna(f.next_planned) else sentence("planned", "Not planned for this crop"))
        local = getattr(f, "change_" + story)
        return clean(dict(
            parcel_id=parcel_id, farm_id=farm_id, region=region, crop=crop, story=story, soil=soil, area_ha=f.area_ha, drainage=f.drainage, droughty=bool(f.droughty_soil),
            yield_change=change, region_yield_change=regional, yield_today_t_ha=f.yield_today, stress_today=today, stress_future=future, local_yield_change=local,
            last_grown=_int_or_none(f.last_grown), next_planned=_int_or_none(f.next_planned),
            risk=sentence("field_risk", "On {soil} the model estimates {change} for this crop under {story}. The whole region: {regional}. Drought stress at the sensitive stage (0–1) goes from {today} to {future}.",
                          soil=(_soil(soil), None), change=(change, "+.1%"), story=(STORY[story], None), regional=(regional, "+.1%"), today=(today, ".2f"), future=(future, ".2f")),
            why=why,
            local_note=sentence("local", "With only this grid square's weather run the same field shows {local}. Differences between squares are mostly weather noise, so trust the soil figure above.", local=(local, "+.1%")),
            basis=self.basis("model", "Modelled for 2041–2060 against 1991–2020, 2025 technology", ["map_soil_effects.csv", "C2_detail_with_uncertainty.csv"])))

    # ------------------------------------------------------------ what-if
    def what_if(self, prediction, parcel_id, crop, scenario, year, irrigation):
        """prediction is engine.predict_field's response for the same request; this adds what the Try page needs."""
        region = self.engine.parcels.loc[parcel_id].region
        if irrigation is not None and region != "SE_SKANE":
            raise Invalid("irrigation", IRRIGATION_NOTE, irrigation)
        r = self.predictor.predict(parcel_id, crop, scenario, year, irrigation)
        e = (np.exp(r["effects"]) - 1)
        e = e[e.abs() >= 0.001].sort_values()
        p, w, farm = r["parcel"], r["weather"], prediction["farm_id"]
        notes = [sentence("soil_map", "Soil-map class: {soil}, {area} ha. The soil map is only about 88% accurate.", soil=(_soil(p.soil_class_soilmap), None), area=(p.area_ha, ".1f")),
                 sentence("usual_irrigation", "This farm's usual irrigated share for this crop: {share}.", share=(r["usual_irrigation"], ".0%"))]
        if year > 2031:
            notes.append(sentence("tech_fixed", "Technology is held at 2025, so differences between future seasons come from weather."))
            notes.append(sentence("shared_response", "This uses the shared weather response, the same as the risk results for 2041–2060."))
        if irrigation is not None:
            notes.append(sentence("irrigation_estimate", "The modelled irrigation effect is an estimate. In past seasons it averages about the measured +6% for Sweden, but it misses individual seasons and can turn negative, down to about -7%, mostly on organic and silt soils, which is an artifact."))
        fair, files = None, []
        if scenario == "historical":
            held = self.frame("backtest_predictions.csv")
            files = ["backtest_predictions.csv"]
            obs = held[(held.test == "loyo") & (held.farm_id == farm) & (held.crop == crop) & (held.year == year)]
            if len(obs):
                o = obs.iloc[0]
                fair = dict(actual_t_ha=o.yield_t_ha, model_t_ha=o.pred_model, baseline_t_ha=o.pred_baseline,
                            **sentence("fair_check", "Fair check for the whole farm at its usual irrigation, with this season hidden from both methods: our model {model}, baseline {base}, actual {actual} t/ha.",
                                       model=(o.pred_model, ".2f"), base=(o.pred_baseline, ".2f"), actual=(o.yield_t_ha, ".2f")))
        baseline = prediction["baseline_t_ha"]
        return clean(dict(
            prediction=prediction, base_t_ha=r["base"], vs_baseline=None if baseline is None else prediction["yield_t_ha"] / baseline - 1,
            drivers=[dict(driver=k, effect=v) for k, v in e.items()],
            drivers_note="Each bar is that driver's percentage effect, starting from the base yield for an average field and season. The effects multiply to give the model's result. Weather measures overlap, so single bars can partly cancel each other out.",
            parcel=dict(soil=p.soil_class_soilmap, area_ha=p.area_ha, region=region, drainage=p.drainage),
            weather_table=[dict(measure=m, value=round(float(w[k]), 2)) for m, k in WEATHER_TABLE], notes=notes, fair_check=fair,
            actual_note="This field, using the final model, which trained on this season" if fair else "Future season, or the farm didn't report",
            basis=self.basis("model", "What-if with the final trained model, a whole season's weather from the package", files)))

    # ------------------------------------------------------------ can we trust this?
    def c1_self_check(self):
        """Predictor.check_against_submission(60), once per model version."""
        version = self.engine.version
        if version not in self._c1:
            self._c1 = {version: float(self.predictor.check_against_submission(60))}
        return dict(max_diff_t_ha=self._c1[version], rows=60, note="Live predictions against the submitted C1 file on a sample of 60 rows (the file is rounded to 3 decimals).")

    def _held(self, test):
        h = self.frame("backtest_predictions.csv")
        return h[h.test == test]

    def trust(self, test):
        p = self._held(test)
        mb, mm = metrics(p.assign(pred=p.pred_baseline)), metrics(p.assign(pred=p.pred_model))
        by_crop = []
        for (region, crop), g in p.groupby(["region", "crop"]):
            b, m = metrics(g.assign(pred=g.pred_baseline)), metrics(g.assign(pred=g.pred_model))
            by_crop.append(dict(region=region, crop=crop, label=f"{REGION[region]}, {CROP[crop].lower()}", seasons=g.year.nunique(), baseline_production_error=b["mape"], model_production_error=m["mape"],
                                baseline_yield_error=b["nrmse"], model_yield_error=m["nrmse"], improvement=1 - m["mape"] / b["mape"]))
        by_crop.sort(key=lambda r: r["baseline_production_error"], reverse=True)
        pea = self.frame("backtest_pea_models.csv").query("test == @test")
        return clean(dict(
            test=test, label=TEST[test],
            headline=dict(production_error=dict(model=mm["mape"], baseline=mb["mape"]), yield_error_nrmse=dict(model=mm["nrmse"], baseline=mb["nrmse"]), pooled=True,
                          note="An error measure averaged over every region and crop season, as in the viewer. It is not a total; the per-region figures are below."),
            headline_by_region=[self._region_headline(p, r) for r in REGION],
            headline_note="In both tests the model is given the actual weather of the season it predicts. So this shows how well it turns weather into yield, not how well anyone can forecast next year's weather.",
            caveat="Model settings were tuned on these same seasons, and the tests use farm averages rather than single fields, so real-world errors are likely to be larger.",
            methods=[dict(code="baseline", label="Baseline: farm average", text="The farm's average yield for that crop across the training seasons. It knows the farm but ignores weather, so it predicts about the same number every season."),
                     dict(code="model", label="Our model: weather-aware regression", text="Farm effect + technology trend + soil + irrigation + crop-stage weather (drought, heat, rain at sowing and harvest). It uses no same-season farm inputs, because those aren't known in advance.")],
            by_crop=by_crop, by_crop_note="Average gap between predicted and actual total production per season. Shorter is better.",
            pea_models=[dict(region=r.region, method=r.method, label=PEA_METHOD.get(r.method, r.method), production_error=r.production_error, yield_error=r.yield_error) for r in pea.itertuples()],
            pea_models_note="Peas from both regions share one model. Long-range results use one weather response for both regions, because 9 Swedish seasons can't support a separate one. The 2027–2031 forecast keeps separate responses.",
            scorer=dict(model=mm["score"], baseline=mb["score"], note=f"Apetit told us this score doesn't affect their decision. On this test, the official formula gives our model {mm['score']:.1f} and the baseline {mb['score']:.1f}. It's applied to farm-level rows while the hidden answers are per field, so expect the real score to be lower."),
            c1_self_check=self.c1_self_check(),
            basis=self.basis("batch", "Held-out backtests on past seasons", ["backtest_predictions.csv", "backtest_pea_models.csv"])))

    @staticmethod
    def _region_headline(p, region):
        g = p[p.region == region]
        b, m = metrics(g.assign(pred=g.pred_baseline)), metrics(g.assign(pred=g.pred_model))
        return dict(region=region, label=REGION[region], production_error=dict(model=m["mape"], baseline=b["mape"]), yield_error_nrmse=dict(model=m["nrmse"], baseline=b["nrmse"]))

    @staticmethod
    def _seasons(d):
        rows = []
        for year, q in d.groupby("year"):
            w = q.area_ha
            a, b, m = np.average(q.yield_t_ha, weights=w), np.average(q.pred_baseline, weights=w), np.average(q.pred_model, weights=w)
            rows.append(dict(year=int(year), actual_t_ha=a, baseline_t_ha=b, model_t_ha=m, baseline_miss=b / a - 1, model_miss=m / a - 1))
        return rows

    def trust_seasons(self, region, crop, test, farm_id=None):
        p = self._held(test)
        g = p[(p.region == region) & (p.crop == crop)]
        if g.empty:
            raise NotFound(f"No held-out seasons for {crop} in {region}.")
        farms = sorted(g.farm_id.unique())
        out = dict(region=region, crop=crop, test=test, seasons=self._seasons(g), farms=farms,
                   note="The baseline stays nearly flat. The test of our model is whether it follows the good and bad seasons. Every point is a prediction for a season held out of training.")
        if farm_id:
            if farm_id not in farms:
                raise NotFound(f"Farm {farm_id} has no held-out {crop} seasons in this test.")
            fg = g[g.farm_id == farm_id]
            out["farm"] = dict(farm_id=farm_id, seasons=self._seasons(fg), note="This farm has only one held-out season in this test. Pick another farm or the other test to see a line." if fg.year.nunique() < 2 else None,
                               caveat="A single farm has more random variation than a regional average, and some seasons are missing where the farm didn't report.")
        out["basis"] = self.basis("batch", "Held-out backtests on past seasons", ["backtest_predictions.csv"])
        return clean(out)

    def live_replay(self, test, scope="all"):
        r = self.frame("live_season_replay.csv")
        r = r[(r.test == test) & (r.scope == scope)]
        if r.empty:
            raise NotFound(f"No live replay for scope {scope!r}. Scopes: all, or REGION/crop.")
        points, first = [], None
        for known, g in r.groupby("known_until", sort=False):
            m = g.set_index("method")
            b, est, plain = m.loc["baseline_farm_average"], m.loc["estimate"], m.loc["estimate_plain_counts"] if "estimate_plain_counts" in m.index else None
            points.append(dict(known_until=known, baseline_production_error=b.production_error, baseline_yield_error_nrmse=b.yield_error_nrmse, estimate_production_error=est.production_error,
                               estimate_yield_error_nrmse=est.yield_error_nrmse, share_of_seasons_beating_baseline=est.share_of_seasons_beating_baseline,
                               plain_counts_production_error=None if plain is None else plain.production_error, region_crop_seasons=est.region_crop_seasons, farm_seasons=est.farm_seasons))
            if first is None and est.production_error < b.production_error:
                first = known
        scopes = list(dict.fromkeys(self.frame("live_season_replay.csv").query("test == @test").scope))
        return clean(dict(test=test, scope=scope, pooled=scope == "all", scopes=scopes, points=points, first_better=first,
                          note="Replays past seasons as if the weather arrived day by day, with the rest of the season filled from normals. 'none' is no weather at all, 'full' the whole season.",
                          basis=self.basis("batch", "Replay of past seasons as if the weather arrived day by day", ["live_season_replay.csv"])))

    def corrections(self):
        log = self.frame("yield_corrections_log.csv")
        survey, erp, used = int((log.source == "farm_survey_fi.csv").sum()), int((log.source != "farm_survey_fi.csv").sum()), int(log.used_for_yield.sum())
        cols = ["record_key", "field", "old_value", "new_value", "rule", "source", "used_for_yield"]
        return clean(dict(survey=survey, erp=erp, used=used,
                          summary=sentence("corrections", "{survey} survey yields were corrected as ×10 slips, and {erp} ERP delivery lines were corrected, kept or excluded. {used} of these changes affect a training yield; the others fall on farms that use their survey answer. Every change is listed with its rule.",
                                           survey=(survey, "d"), erp=(erp, "d"), used=(used, "d")),
                          rows=[{c: getattr(r, c) for c in cols} for r in log.itertuples()],
                          basis=self.basis("batch", "Data cleaning log from the pipeline", ["yield_corrections_log.csv"])))
