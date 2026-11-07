import json
import os
import re
import shutil

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from advisor import CONFIDENCE, STORIES, advice, field_table, load_outputs, themes
from backtest import metrics
from config import OUT
from service.insights import FILES, Insights

FIELD = dict(parcel_id="F0001-P01", crop="pea", scenario="historical", year=2018, irrigation=None)
SE_FIELD = dict(parcel_id="S0381-P01", crop="pea", scenario="ssp585", year=2050, irrigation=1.0)
GETS = ["/insights/meta", "/insights/options", "/insights/options?region=SE_SKANE&crop=pea", "/insights/options?farm_id=F0028", "/insights/policy", "/insights/euro-risk", "/insights/trust/corrections",
        "/insights/advice?region=FI_SW&crop=turnip_rape&story=current_policies", "/insights/advice?region=SE_SKANE&crop=pea&story=below_2c",
        "/insights/outlook?region=FI_SW&crop=pea", "/insights/outlook?region=SE_SKANE&crop=pea", "/insights/climate-risk?scenario=ssp126", "/insights/climate-risk?scenario=ssp585",
        "/insights/farms?region=FI_SW&crop=carrot", "/insights/farms?region=SE_SKANE&crop=pea", "/insights/soil-effects?region=FI_SW&crop=carrot", "/insights/soil-effects?region=SE_SKANE&crop=pea",
        "/insights/farms/F0028?crop=carrot&story=current_policies", "/insights/farms/S0381?crop=pea&story=below_2c", "/insights/fields/F0028-P18?crop=carrot&story=current_policies",
        "/insights/fields/S0381-P01?crop=pea&story=current_policies", "/insights/trust?test=loyo", "/insights/trust?test=forward", "/insights/trust/seasons?region=FI_SW&crop=pea&test=loyo&farm_id=F0003",
        "/insights/trust/seasons?region=SE_SKANE&crop=pea&test=forward", "/insights/trust/live-replay?test=loyo", "/insights/trust/live-replay?test=forward&scope=SE_SKANE/pea"]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("LIVE_DB", str(tmp_path_factory.mktemp("insights") / "api.sqlite"))
    mp.delenv("CB_URL", raising=False)
    from service.api import app
    with TestClient(app) as c:
        yield c
    mp.undo()


@pytest.fixture(scope="module")
def results():
    return load_outputs()


def get(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("url", GETS)
def test_every_endpoint_answers_with_a_basis_and_no_paths(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.text
    body = r.json()
    b = body["basis"]
    assert b["kind"] in ("batch", "model") and b["model_version"] and isinstance(b["stale_vs_model"], bool) and b["label"]
    assert all("/" not in s["file"] or s["file"].startswith("package/") for s in b["sources"])
    assert "/Users/" not in r.text and str(OUT) not in r.text
    assert r.headers["cache-control"] == "max-age=60" and r.headers["etag"]


def test_etag_answers_304(client):
    r = client.get("/insights/policy")
    assert client.get("/insights/policy", headers={"If-None-Match": r.headers["etag"]}).status_code == 304


@pytest.mark.parametrize("url", ["/insights/advice?region=XX&crop=pea&story=below_2c", "/insights/advice?region=FI_SW&crop=pea", "/insights/advice?region=FI_SW&crop=pea&story=below_2c&extra=1",
                                 "/insights/meta?x=1", "/insights/climate-risk?scenario=ssp245", "/insights/options?crop=pea", "/insights/options?farm_id=X1", "/insights/trust?test=kfold",
                                 "/insights/trust/live-replay?test=loyo&scope=../etc", "/insights/farms/F28?crop=pea&story=below_2c", "/insights/fields/F0028?crop=pea&story=below_2c",
                                 "/insights/farms?region=FI_SW&crop=kale"])
def test_bad_parameters_give_422(client, url):
    r = client.get(url)
    assert r.status_code == 422 and {"detail", "missing", "invalid"} <= set(r.json())


@pytest.mark.parametrize("url", ["/insights/advice?region=SE_SKANE&crop=carrot&story=below_2c", "/insights/farms?region=SE_SKANE&crop=potato", "/insights/options?region=SE_SKANE&crop=carrot",
                                 "/insights/options?farm_id=F9999", "/insights/farms/F9999?crop=pea&story=below_2c", "/insights/farms/S0381?crop=carrot&story=below_2c",
                                 "/insights/fields/F0001-P999?crop=pea&story=below_2c", "/insights/outlook?region=SE_SKANE&crop=spinach", "/insights/trust/seasons?region=FI_SW&crop=pea&test=loyo&farm_id=S0381",
                                 "/insights/trust/live-replay?test=loyo&scope=SE_SKANE/carrot"])
def test_nothing_there_gives_404(client, url):
    r = client.get(url)
    assert r.status_code == 404 and r.json()["detail"]


def test_results_equal_load_outputs(client, results):
    mine = client.app.state.insights.results()
    assert set(mine) == set(results)
    for k in results:
        pd.testing.assert_frame_equal(mine[k], results[k])


def test_advice_matches_advisor(client, results):
    for (region, crop) in CONFIDENCE:
        for story, ssp in STORIES.items():
            a = get(client, f"/insights/advice?region={region}&crop={crop}&story={story}")
            rules = advice(results, region, crop, story)
            assert [x["rule"] for x in a["actions"]] == [r["rule"] for r in rules]
            for x, r in zip(a["actions"], rules):
                assert x["template"] == r["text"] and x["decision"] == r["decision"] and "{" not in x["text"]
            risk = results["risk"].query("region == @region and crop == @crop and scenario == @ssp").iloc[0]
            s = next(s for s in a["stories"] if s["story"] == story)
            assert s["yield_change"] == pytest.approx(risk.mean_yield_change_pct / 100) and s["bad_year_chance"] == pytest.approx(risk.p_bad_year)
            th = themes(results, region, crop, ssp)
            assert [t[story] for t in a["themes"]] == pytest.approx(th.tolist())
            assert len(a["season_shift"]) == (1 if region == "SE_SKANE" else 2)


def test_advice_text_is_formatted_like_the_viewer(client):
    a = get(client, "/insights/advice?region=SE_SKANE&crop=pea&story=current_policies")
    irr = next(x for x in a["actions"] if x["rule"] == "irrigation")
    assert re.search(r"about \d+% more", irr["text"])
    cost = next(x for x in a["actions"] if x["rule"] == "input_costs")
    assert "€" in cost["text"] and cost["values"]["carbon"][1] == "eur"


def test_trust_headline_equals_backtest_summary(client):
    s = pd.read_csv(OUT / "backtest_summary.csv", index_col=0)
    for test, suffix in [("loyo", "loyo"), ("forward", "forward_2022_2026")]:
        h = get(client, f"/insights/trust?test={test}")["headline"]
        assert h["production_error"] == dict(model=s.loc[f"final_{suffix}", "mape"], baseline=s.loc[f"farm_mean_{suffix}", "mape"])
        assert h["yield_error_nrmse"] == dict(model=s.loc[f"final_{suffix}", "nrmse"], baseline=s.loc[f"farm_mean_{suffix}", "nrmse"])


def test_trust_by_crop_matches_error_table(client):
    p = pd.read_csv(OUT / "backtest_predictions.csv").query("test == 'loyo'")
    body = get(client, "/insights/trust?test=loyo")
    rows = {(r["region"], r["crop"]): r for r in body["by_crop"]}
    for (region, crop), g in p.groupby(["region", "crop"]):
        b, m = metrics(g.assign(pred=g.pred_baseline)), metrics(g.assign(pred=g.pred_model))
        r = rows[(region, crop)]
        assert (r["baseline_production_error"], r["model_production_error"], r["seasons"]) == (b["mape"], m["mape"], g.year.nunique())
        assert r["improvement"] == pytest.approx(1 - m["mape"] / b["mape"])
    errs = [r["baseline_production_error"] for r in body["by_crop"]]
    assert errs == sorted(errs, reverse=True)
    assert body["c1_self_check"]["rows"] == 60 and body["c1_self_check"]["max_diff_t_ha"] >= 0


def test_seasons_are_area_weighted(client):
    p = pd.read_csv(OUT / "backtest_predictions.csv").query("test == 'loyo' and region == 'FI_SW' and crop == 'pea'")
    s = get(client, "/insights/trust/seasons?region=FI_SW&crop=pea&test=loyo")["seasons"]
    q = p[p.year == s[0]["year"]]
    assert s[0]["actual_t_ha"] == pytest.approx(np.average(q.yield_t_ha, weights=q.area_ha))
    assert s[0]["model_miss"] == pytest.approx(s[0]["model_t_ha"] / s[0]["actual_t_ha"] - 1)


def test_outlook_and_climate_risk_follow_the_csvs(client):
    fc = pd.read_csv(OUT / "C1_forecast_comparison.csv").query("region == 'FI_SW' and crop == 'pea'")
    o = get(client, "/insights/outlook?region=FI_SW&crop=pea")
    assert [f["model_t_ha"] for f in o["forecast"]] == fc.model_t_ha.tolist() and [f["year"] for f in o["forecast"]] == fc.year.tolist()
    d = pd.read_csv(OUT / "C2_detail_with_uncertainty.csv").query("scenario == 'ssp585'").sort_values("mean_yield_change_pct")
    rows = get(client, "/insights/climate-risk?scenario=ssp585")["rows"]
    assert [(r["region"], r["crop"]) for r in rows] == list(zip(d.region, d.crop)) and [r["change_min_pct"] for r in rows] == d.change_min.tolist()


def test_euro_totals_stay_per_region(client):
    e = pd.read_csv(OUT / "C3_euro_risk.csv")
    body = get(client, "/insights/euro-risk")
    assert [t["region"] for t in body["totals"]] == ["FI_SW", "SE_SKANE"]
    for t in body["totals"]:
        for ssp in ("baseline", "ssp126", "ssp585"):
            assert t[ssp] == pytest.approx(e[(e.region == t["region"]) & (e.ssp == ssp)].expected_cost_eur_yr.sum())
    assert {r["scenario"] for r in body["by_crop"]} == {"baseline", "ssp126", "ssp585"}


def test_no_figure_combines_the_regions(client):
    for url in GETS:
        text = json.dumps(get(client, url))
        assert not re.search(r'"region":\s*"(all|both)', text), url
        assert '"scope": "all"' not in text or '"pooled": true' in text, url


def test_trust_has_each_region_separately(client):
    p = pd.read_csv(OUT / "backtest_predictions.csv").query("test == 'loyo' and region == 'SE_SKANE'")
    body = get(client, "/insights/trust?test=loyo")
    se = next(r for r in body["headline_by_region"] if r["region"] == "SE_SKANE")
    assert se["production_error"]["model"] == metrics(p.assign(pred=p.pred_model))["mape"] and body["headline"]["pooled"] is True


def test_farms_follow_contact_order(client):
    f = pd.read_csv(OUT / "map_farms.csv").query("region == 'FI_SW' and crop == 'carrot'").sort_values(["planned_dry_ha", "dry_ha"], ascending=False)
    body = get(client, "/insights/farms?region=FI_SW&crop=carrot")
    assert [r["farm_id"] for r in body["farms"]] == f.farm_id.tolist() and body["labelled"] == f.farm_id.head(8).tolist()
    assert body["bands"]["edges"] == [-0.06, -0.04, -0.02, 0.02, 0.04, 0.06]


def test_farm_story_matches_field_table_and_map_row(client):
    eng = client.app.state.live.engine
    table = field_table(eng.predictor, "F0028", "carrot")
    body = get(client, "/insights/farms/F0028?crop=carrot&story=current_policies")
    assert [f["parcel_id"] for f in body["fields"]] == table.parcel_id.tolist()
    assert [f["yield_today_t_ha"] for f in body["fields"]] == pytest.approx(table.yield_today.tolist())
    row = pd.read_csv(OUT / "map_farms.csv").query("crop == 'carrot' and farm_id == 'F0028'").iloc[0]
    assert body["headline"]["yield_change"] == row.change_current_policies and body["headline"]["yield_change_other_story"] == row.change_below_2c
    assert body["risk"]["text"].startswith("With this farm's soils, the model estimates -2.1%")
    assert [w["code"] for w in body["why"]] == ["dry_fields", "planned", "irrigation", "largest_theme"]
    soils = [s["yield_today_t_ha"] for s in body["yield_by_soil"]]
    assert soils == sorted(soils, reverse=True)


def test_field_panel_uses_the_soil_figure(client):
    e = pd.read_csv(OUT / "map_soil_effects.csv").query("region == 'FI_SW' and crop == 'carrot' and soil == 'sand'").iloc[0]
    body = get(client, "/insights/fields/F0028-P18?crop=carrot&story=current_policies")
    assert body["soil"] == "sand" and body["yield_change"] == e.change_current_policies and body["stress_future"] == e.stress_current_policies
    assert body["local_yield_change"] is not None and "grid square" in body["local_note"]["text"]


def test_what_if_prediction_equals_predict_field(client):
    for body in (FIELD, SE_FIELD):
        r = client.post("/insights/what-if", json=body)
        assert r.status_code == 200, r.text
        w = r.json()
        assert w["prediction"] == client.post("/predict/field", json=body).json()
        effects = [d["effect"] for d in w["drivers"]]
        assert effects == sorted(effects) and all(abs(x) >= 0.001 for x in effects)
        assert len(w["weather_table"]) == 8 and w["base_t_ha"] > 0
    w = client.post("/insights/what-if", json=FIELD).json()
    assert w["vs_baseline"] == pytest.approx(w["prediction"]["yield_t_ha"] / w["prediction"]["baseline_t_ha"] - 1)
    assert w["fair_check"] and w["fair_check"]["text"].startswith("Fair check") and w["actual_note"].startswith("This field")
    se = client.post("/insights/what-if", json=SE_FIELD).json()
    assert se["fair_check"] is None and {"tech_fixed", "shared_response", "irrigation_estimate"} <= {n["code"] for n in se["notes"]}


@pytest.mark.parametrize("change,status", [(dict(irrigation=1.0), 422), (dict(scenario="ssp999"), 422), (dict(extra=1), 422), (dict(parcel_id="F0001-P999"), 404), (dict(year=2035), 404)])
def test_what_if_errors(client, change, status):
    assert client.post("/insights/what-if", json=dict(FIELD, **change)).status_code == status


def test_reload_and_corrupt_file(tmp_path, engine):
    out = tmp_path / "outputs"
    shutil.copytree(OUT, out, ignore=shutil.ignore_patterns("*.json", "C1_yields*", "backtest_per_crop*"))
    ins = Insights(engine, out=out)
    first = ins.euro_risk()
    f = out / "C3_euro_risk.csv"
    e = pd.read_csv(f)
    e.loc[0, "expected_cost_eur_yr"] += 1000
    e.to_csv(f, index=False)
    os.utime(f, ns=(f.stat().st_mtime_ns + 10**9,) * 2)
    second = ins.euro_risk()
    assert second["totals"][0]["baseline"] == first["totals"][0]["baseline"] + 1000
    assert second["basis"]["sources"][0]["generated_at"] != first["basis"]["sources"][0]["generated_at"]
    f.write_text("garbage\n1\n")
    assert ins.euro_risk()["totals"] == second["totals"]
    meta = {m["file"]: m for m in ins.meta()["files"]}
    assert meta["C3_euro_risk.csv"]["load_error"] and "/" not in meta["C3_euro_risk.csv"]["load_error"]
    assert [m["file"] for m in ins.meta()["files"]][:len(FILES)] == FILES


def test_missing_file_gives_503(tmp_path, engine, monkeypatch):
    out = tmp_path / "outputs"
    out.mkdir()
    from service.api import app
    monkeypatch.setenv("LIVE_DB", str(tmp_path / "api.sqlite"))
    with TestClient(app) as c:
        c.app.state.insights = Insights(engine, out=out)
        r = c.get("/insights/euro-risk")
        assert r.status_code == 503 and r.json()["file"] == "C3_euro_risk.csv" and "/Users/" not in r.text
        assert c.get("/insights/meta").status_code == 200
