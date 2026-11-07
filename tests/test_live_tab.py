"""The tab has to survive with no backend, and show a season when there is one."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from streamlit.testing.v1 import AppTest

SCRIPT = """
import streamlit as st
import live_tab
live_tab.BACKEND = {url!r}
live_tab.render(lambda chart, name, area=st: area.altair_chart(chart), lambda chart, height=320: chart.properties(height=height), dict(pea="Pea"))
"""


def run(url, lang="en"):
    at = AppTest.from_string(SCRIPT.format(url=url), default_timeout=30)
    at.session_state["lang"] = lang
    return at.run()


def test_no_backend_shows_guidance_not_an_error():
    at = run("http://127.0.0.1:9")
    assert not at.exception and "isn't running" in at.warning[0].value and "service.cli start" in at.code[0].value


def test_no_backend_in_finnish():
    at = run("http://127.0.0.1:9", "fi")
    assert not at.exception and "ei ole käynnissä" in at.warning[0].value


ROW = dict(parcel_id="F1-P1", farm_id="F1", cell_id="GF0203", crop="pea", year=2025, status="declared", area_ha=2.0, yield_t_ha=3.5, baseline_t_ha=3.6, observed_days=100, partial_days=0, filled_days=141, filled_gap_days=1, filled_future_days=140, total_days=241,
           filled_to_maturity=30, out_of_training_range=[], label="estimate", model_name="models[pea]")
RESPONSES = {"/health": dict(status="ok", counters=dict(notifications=100), writeback=dict(enabled=False), last_notification=dict(received_at="2026-11-07T10:00:00Z")),
             "/observations/status": dict(seasons=[dict(cell_id="GF0203", year=2025, contract_parcels=1)], recent_rejected=[dict(received_at="t", entity_id="e", reason="bad")], counters={}),
             "/predictions": dict(predictions=[dict(ROW, as_of_date="2025-06-08"), dict(ROW, as_of_date="2025-06-09", yield_t_ha=3.4)])}


@pytest.fixture
def backend():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(RESPONSES[self.path.split("?")[0]]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_season_is_shown(backend):
    at = run(backend)
    assert not at.exception
    labels = {m.label: m.value for m in at.metric}
    assert labels["Estimate on 2025-06-09"] == "3.40 t/ha" and labels["Days observed"] == "100" and labels["Days filled"] == "141" and labels["Backend"] == "Running"
    assert any("missed regional production" in m.value for m in at.markdown)
