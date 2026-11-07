"""Notification in, stored readings and fresh estimates out. Holds the backend's logic with no web code, so an MCP server can call it too."""
import logging
import threading

from service.broker_client import WritebackWorker, make_client
from service.engine import Engine, UnknownInput  # noqa: F401
from service.ngsi import CellMap, PayloadError, parse_notification
from service.season import assemble, day_counts, DOYS, in_window, load_normals, doy_of
from service.settings import load_settings
from service.store import Store, now

log = logging.getLogger("service.pipeline")


class LiveService:
    def __init__(self, settings=None, engine=None, normals=None, cells=None, client=None):
        self.settings = settings or load_settings()
        self.store = Store(self.settings.db_path)
        self.engine, self.normals, self.cells = engine or Engine(), normals or load_normals(), cells or CellMap()
        self.client = client or make_client(self.settings)
        self.writeback = WritebackWorker(self.store, self.client, self.settings.cb_context) if self.client.enabled else None
        self.lock = threading.RLock()  # Readings and the estimates they lead to stay consistent per notification.
        self.started_at = now()

    def start(self):
        if self.writeback:
            self.writeback.start()
            self.writeback.wake.set()

    def stop(self):
        if self.writeback:
            self.writeback.stop()

    def handle_notification(self, body, content_type=None, link_header=None):
        """Parse, store and recompute. Raises PayloadError if the envelope is unusable. See docs/CB_INTEGRATION.md for each case."""
        store = self.store
        try:
            n = parse_notification(body, content_type, link_header, self.cells)
        except PayloadError as e:
            store.bump("notifications_refused")
            store.add_rejected(None, None, f"{e.title}: {e.detail}", repr(body[:300]))
            raise
        outcomes = dict(new=0, duplicate=0, corrected=0, stale=0, out_of_season=0)
        changed = set()
        with self.lock:
            with store.tx():
                for r in n.readings:
                    outcome = store.save_reading(r, n.subscription_id, n.notified_at)
                    outcomes[outcome] += 1
                    if in_window(doy_of(r.day)):
                        if outcome in ("new", "corrected"):
                            changed.add((r.cell_id, int(r.day[:4])))
                    else:
                        outcomes["out_of_season"] += 1
                for bad in n.rejected:
                    store.add_rejected(n.subscription_id, bad["entity_id"], bad["reason"], bad["excerpt"])
                store.bump("notifications")
                for k, v in outcomes.items():
                    store.bump("readings_" + k, v)
                store.bump("entities_rejected", len(n.rejected))
                store.bump("entities_ignored", len(n.ignored))
                store.set_meta("last_notification", dict(id=n.id, subscription_id=n.subscription_id, notified_at=n.notified_at, received_at=now(), content_type=n.content_type, context=n.context))
            predictions, errors = 0, []
            for cell, year in sorted(changed):
                try:
                    predictions += self.recompute(cell, year)
                except Exception as e:  # The readings are safe: report it and let the next notification try again.
                    log.exception("Recompute failed for %s %s", cell, year)
                    store.bump("recompute_errors")
                    errors.append(dict(cell_id=cell, year=year, error=str(e)))
        if predictions and self.writeback:
            self.writeback.wake.set()
        return dict(notification_id=n.id, subscription_id=n.subscription_id, readings=outcomes, rejected=[dict(entity_id=b["entity_id"], index=b["index"], reason=b["reason"]) for b in n.rejected],
                    ignored=n.ignored, seasons_recomputed=[dict(cell_id=c, year=y) for c, y in sorted(changed)], predictions_written=predictions, prediction_errors=errors)

    def season_of(self, cell_id, year):
        return assemble(cell_id, year, self.store.season(cell_id, year), self.normals[cell_id], self.settings.gap_interp_days)

    def recompute(self, cell_id, year):
        season = self.season_of(cell_id, year)
        if season.last_doy is None:
            return 0
        preds = self.engine.predict_cell(season, self.settings.fill_counts)
        self.store.save_predictions(preds)
        return len(preds)

    def status(self, cell_id=None, year=None):
        """What's stored per cell and season, and how much of the season would be filled."""
        rows = []
        for s in self.store.seasons(cell_id, year):
            cell, season_year = s["cell_id"], s["year"]
            days = day_counts(self.season_of(cell, season_year))
            read = {r["doy"] for r in self.store.season(cell, season_year)}
            last = days["last_observed_doy"]
            missing = [int(d) for d in DOYS if last is not None and d < last and d not in read]
            plan = self.engine.plan_for(cell, season_year)
            rows.append(dict(s, **days, label="estimate", missing_doys_before_last=missing, contract_parcels=0 if plan is None else int(plan.parcel_id.nunique())))
        return rows

    def health(self):
        wb = self.writeback
        self.engine.refresh()
        degraded = bool(self.engine.load_error or (wb and wb.last_error))
        return dict(status="degraded" if degraded else "ok", started_at=self.started_at, models=self.engine.info(), store=dict(path=str(self.settings.db_path), **self.store.totals()), counters=self.store.counters(),
                    last_notification=self.store.get_meta("last_notification"), fill_counts=self.settings.fill_counts,
                    writeback=dict(enabled=self.client.enabled, url=self.client.url, written=wb.written if wb else 0, last_error=wb.last_error if wb else None, pending=self.store.count_unsynced() if wb else 0))
