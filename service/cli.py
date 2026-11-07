"""Control the mock broker and the backend. Run `python -m service.cli --help`, or `python -m service.cli start` for everything at once."""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

import httpx

from service.settings import BACKEND_PORT, BACKEND_URL, HOST, MOCK_PORT, MOCK_URL, PROJECT, WEATHER_CONTEXT

NOTIFY_URL = f"{BACKEND_URL}/notify"


def show(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def call(method, url, **kw):
    try:
        r = httpx.request(method, url, timeout=120.0, **kw)
    except httpx.HTTPError as e:
        sys.exit(f"Can't reach {url}: {e}. Is it running? Start it with: python -m service.cli start")
    if r.status_code >= 400:
        sys.exit(f"{method} {url} failed with {r.status_code}: {r.text[:800]}")
    return r.json() if r.content and "json" in r.headers.get("content-type", "") else {"status": r.status_code, "location": r.headers.get("location")}


def up(url):
    try:
        return httpx.get(url, timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def cmd_status(a):
    for name, url in (("backend", f"{a.backend}/health"), ("mock broker", f"{a.broker}/mock/status")):
        print(f"--- {name}: {url}")
        show(call("GET", url) if up(url) else {"status": "not running"})


def cmd_subscribe(a):
    from service.broker_client import subscription_body
    body = subscription_body(a.notify_url, a.context, a.types, a.accept, a.format, a.id, a.watch)
    if a.throttling:
        body["throttling"] = a.throttling
    headers = {"Content-Type": "application/ld+json"}
    if a.tenant:
        headers["NGSILD-Tenant"] = a.tenant
    if a.dry_run:
        return show(body)
    r = call("POST", f"{a.broker}/ngsi-ld/v1/subscriptions", content=json.dumps(body), headers=headers)
    print(f"Subscribed: {r.get('location')}")


def cmd_subs(a):
    show(call("GET", f"{a.broker}/ngsi-ld/v1/subscriptions"))


def cmd_unsubscribe(a):
    show(call("DELETE", f"{a.broker}/ngsi-ld/v1/subscriptions/{a.id}"))


def cmd_replay(a):
    spec = dict(cell_id=a.cell, year=a.year, start=a.start, end=a.end, scenario=a.scenario, days_per_second=a.speed, batch_size=a.batch_size, drop_every=a.drop_every, drop_dates=a.drop_date or [], duplicate_every=a.duplicate_every,
                shuffle_window=a.shuffle_window, include_pet=not a.no_pet)
    job = call("POST", f"{a.broker}/mock/replay", json=spec)
    print(f"Replay {job['job_id']}: {job['total']} days for {a.cell} {a.year}")
    if not a.wait:
        return show(job)
    while True:
        time.sleep(0.5)
        job = call("GET", f"{a.broker}/mock/replay/{job['job_id']}")
        print(f"\r{job['state']}: {job['sent']}/{job['total']} days, at {job['current_date']}, delivery failures {job['errors']}   ", end="", flush=True)
        if job["state"] == "finished" or job["state"].startswith(("failed", "stopped")):
            print()
            return


def cmd_jobs(a):
    show(call("GET", f"{a.broker}/mock/replay"))


def cmd_job_action(a):
    show(call("POST", f"{a.broker}/mock/replay/{a.job_id}/{a.command}"))


def cmd_send(a):
    show(call("POST", f"{a.broker}/mock/reading", json=dict(cell_id=a.cell, date=a.date, temperature=a.temperature, tmax=a.tmax, tmin=a.tmin, precipitation=a.precipitation, pet=a.pet)))


def cmd_inject(a):
    show(call("POST", f"{a.broker}/mock/inject", json=dict(kind=a.kind, cell_id=a.cell, date=a.date)))


def cmd_log(a):
    show(call("GET", f"{a.broker}/mock/log", params=dict(limit=a.limit)))


def cmd_entities(a):
    show(call("GET", f"{a.broker}/ngsi-ld/v1/entities", params=dict(type=a.type, limit=a.limit, options="keyValues")))


def cmd_reset_season(a):
    show(call("DELETE", f"{a.backend}/observations", params=dict(cell_id=a.cell, year=a.year)))


def cmd_observations(a):
    show(call("GET", f"{a.backend}/observations/status", params={k: v for k, v in dict(cell_id=a.cell, year=a.year).items() if v is not None}))


def cmd_predictions(a):
    rows = call("GET", f"{a.backend}/predictions", params={k: v for k, v in dict(cell_id=a.cell, year=a.year, crop=a.crop, parcel_id=a.parcel, latest=str(not a.history).lower(), limit=a.limit).items() if v is not None})["predictions"]
    for r in rows:
        print(f"{r['as_of_date']} {r['parcel_id']:<12} {r['crop']:<12} estimate {r['yield_t_ha']:.3f} t/ha, baseline {r['baseline_t_ha'] if r['baseline_t_ha'] is None else round(r['baseline_t_ha'], 3)}, observed {r['observed_days']}, filled {r['filled_days']} (gaps {r['filled_gap_days']}, ahead {r['filled_future_days']}), {r['model_name']}")
    print(f"{len(rows)} rows. These are model estimates, not measured yields.")


def serve(module, port, env=None):
    return subprocess.Popen([sys.executable, "-m", "uvicorn", module, "--host", HOST, "--port", str(port), "--log-level", "warning"], cwd=PROJECT, env={**os.environ, **(env or {})})


def wait_for(url, proc, seconds=60):
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            sys.exit(f"The process for {url} exited with code {proc.returncode}. Is its port already in use?")
        if up(url):
            return
        time.sleep(0.3)
    sys.exit(f"{url} didn't come up within {seconds} s.")


def cmd_start(a):
    """Backend, mock broker and a weather subscription between them, until Ctrl-C."""
    for url in (f"{BACKEND_URL}/health", f"{MOCK_URL}/mock/status"):
        if up(url):
            sys.exit(f"{url} is already running. Stop it first.")
    env = {"CB_URL": MOCK_URL} if a.writeback else {}
    procs = [serve("service.api:app", BACKEND_PORT, env), serve("service.mock_broker:app", MOCK_PORT)]
    if a.viewer:
        procs.append(subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(a.viewer_port), "--server.address", HOST, "--server.headless", "true"], cwd=PROJECT))

    def stop(*_):
        for p in procs:
            p.terminate()
        for p in procs:
            p.wait(timeout=10)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    try:
        wait_for(f"{BACKEND_URL}/health", procs[0])
        wait_for(f"{MOCK_URL}/mock/status", procs[1])
        a.broker, a.notify_url, a.accept, a.types, a.id, a.throttling, a.tenant, a.dry_run, a.context, a.watch = MOCK_URL, NOTIFY_URL, "application/json", None, None, 0, "", False, WEATHER_CONTEXT, None
        cmd_subscribe(a)
        print(f"Backend {BACKEND_URL}, mock broker {MOCK_URL}" + (f", viewer http://{HOST}:{a.viewer_port}" if a.viewer else "") + (", writing predictions back to the mock" if a.writeback else "") + ". Ctrl-C stops everything.")
        print("Try: python -m service.cli replay --cell GF0203 --year 2025 --speed 20 --wait")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


def parser():
    ap = argparse.ArgumentParser(prog="python -m service.cli", description=__doc__)
    ap.add_argument("--broker", default=os.environ.get("CB_URL") or MOCK_URL, help="Broker URL. Default: CB_URL, or the mock.")
    ap.add_argument("--backend", default=BACKEND_URL, help="Backend URL.")
    sub = ap.add_subparsers(dest="command", required=True)

    def add(name, fn, help_text):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(fn=fn)
        return p

    p = add("start", cmd_start, "Start the backend and mock broker and subscribe one to the other.")
    p.add_argument("--writeback", action="store_true", help="Write YieldPrediction entities back to the mock (sets CB_URL for the backend).")
    p.add_argument("--viewer", action="store_true", help="Also start the Streamlit viewer.")
    p.add_argument("--viewer-port", type=int, default=8503)
    p.add_argument("--format", default="normalized", choices=["normalized", "concise", "keyValues"])

    add("status", cmd_status, "Show backend and mock status.")
    p = add("subscribe", cmd_subscribe, "Create the weather subscription, on the mock or on a real broker (--broker).")
    p.add_argument("--notify-url", default=NOTIFY_URL)
    p.add_argument("--format", default="normalized", choices=["normalized", "concise", "keyValues"])
    p.add_argument("--accept", default="application/json", choices=["application/json", "application/ld+json"])
    p.add_argument("--types", nargs="*", help="Entity types to watch. Default WeatherObserved. YieldPrediction is refused.")
    p.add_argument("--id")
    p.add_argument("--context", default=os.environ.get("CB_WEATHER_CONTEXT", WEATHER_CONTEXT), help="@context URL. Must be the one the weather entities were created with, or the type won't match.")
    p.add_argument("--watch", nargs="*", help="watchedAttributes. Default none: every update notifies, so corrections arrive.")
    p.add_argument("--throttling", type=float, default=0)
    p.add_argument("--tenant", default=os.environ.get("CB_TENANT", ""))
    p.add_argument("--dry-run", action="store_true", help="Print the body without sending it.")
    add("subs", cmd_subs, "List subscriptions.")
    p = add("unsubscribe", cmd_unsubscribe, "Delete a subscription.")
    p.add_argument("id")

    p = add("replay", cmd_replay, "Replay real daily weather for a cell through the mock.")
    p.add_argument("--cell", required=True)
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--start", help="First date, YYYY-MM-DD. Default: start of the model window, day of year 60.")
    p.add_argument("--end", help="Last date. Default: end of the model window, day of year 300.")
    p.add_argument("--scenario", help="historical (up to 2026, the default there) or an SSP (2027 on, default ssp245).")
    p.add_argument("--speed", type=float, default=5.0, help="Days per second. 0 is as fast as the backend answers.")
    p.add_argument("--batch-size", type=int, default=1, help="Days in one notification.")
    p.add_argument("--drop-every", type=int, default=0, help="Hide every Nth day.")
    p.add_argument("--drop-date", action="append", help="Hide this date. Can repeat.")
    p.add_argument("--duplicate-every", type=int, default=0, help="Send every Nth day twice.")
    p.add_argument("--shuffle-window", type=int, default=0, help="Shuffle days inside windows of this size.")
    p.add_argument("--no-pet", action="store_true", help="Leave PET out, so the backend derives it.")
    p.add_argument("--wait", action="store_true", help="Show progress until it ends.")
    add("jobs", cmd_jobs, "List replays.")
    for name in ("pause", "resume", "stop"):
        p = add(name, cmd_job_action, f"{name.capitalize()} a replay.")
        p.add_argument("job_id")

    p = add("send", cmd_send, "Send one custom reading by hand.")
    p.add_argument("--cell", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--temperature", type=float, help="Daily mean, C.")
    p.add_argument("--tmax", type=float)
    p.add_argument("--tmin", type=float)
    p.add_argument("--precipitation", type=float, help="mm.")
    p.add_argument("--pet", type=float, help="mm. Left out, the backend derives it from temperature.")

    p = add("inject", cmd_inject, "Send a fault and show what the backend answered.")
    p.add_argument("kind", choices=["duplicate", "conflict", "out_of_order", "missing_day", "bad_batch", "yield_prediction", "not_json", "wrong_content_type", "no_data", "no_subscription_id", "bad_notified_at", "data_not_array"])
    p.add_argument("--cell", default="GF0203")
    p.add_argument("--date", default="2025-06-01")

    p = add("log", cmd_log, "Show what the mock delivered and what came back.")
    p.add_argument("--limit", type=int, default=20)
    p = add("entities", cmd_entities, "List entities held by the broker.")
    p.add_argument("--type", default="YieldPrediction")
    p.add_argument("--limit", type=int, default=5)
    p = add("reset-season", cmd_reset_season, "Clear one season from the backend, to replay it from the start.")
    p.add_argument("--cell", required=True)
    p.add_argument("--year", type=int, required=True)
    p = add("observations", cmd_observations, "Show observed and filled days per season.")
    p.add_argument("--cell")
    p.add_argument("--year", type=int)
    p = add("predictions", cmd_predictions, "Show estimates.")
    p.add_argument("--cell")
    p.add_argument("--year", type=int)
    p.add_argument("--crop")
    p.add_argument("--parcel")
    p.add_argument("--history", action="store_true", help="Every estimate through the season, not only the latest.")
    p.add_argument("--limit", type=int, default=30)
    return ap


def main():
    a = parser().parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
