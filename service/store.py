"""SQLite store for daily observations and predictions. One connection behind a lock: writes are short and local."""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from service.season import in_window, doy_of

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (cell_id TEXT, date TEXT, year INT, doy INT, in_window INT, tmean REAL, tmax REAL, tmin REAL, precip REAL, pet REAL, pet_source TEXT, entity_id TEXT, subscription_id TEXT,
    notified_at TEXT, received_at TEXT, revisions INT DEFAULT 0, duplicates INT DEFAULT 0, PRIMARY KEY (cell_id, date));
CREATE INDEX IF NOT EXISTS obs_season ON observations (cell_id, year);
CREATE TABLE IF NOT EXISTS predictions (parcel_id TEXT, crop TEXT, year INT, as_of_date TEXT, farm_id TEXT, cell_id TEXT, status TEXT, area_ha REAL, yield_t_ha REAL, baseline_t_ha REAL, model_name TEXT, model_version TEXT,
    technology_year INT, label TEXT, observed_days INT, partial_days INT, filled_days INT, filled_gap_days INT, filled_future_days INT, total_days INT, filled_to_maturity INT, sow_doy REAL, mat_doy REAL, features TEXT,
    out_of_training_range TEXT, computed_at TEXT, synced_at TEXT, PRIMARY KEY (parcel_id, crop, year, as_of_date));
CREATE INDEX IF NOT EXISTS pred_cell ON predictions (cell_id, year, crop);
CREATE INDEX IF NOT EXISTS pred_sync ON predictions (synced_at);
CREATE TABLE IF NOT EXISTS rejected (id INTEGER PRIMARY KEY, received_at TEXT, subscription_id TEXT, entity_id TEXT, reason TEXT, excerpt TEXT);
CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INT);
CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT);
"""
PRED_COLS = ["parcel_id", "crop", "year", "as_of_date", "farm_id", "cell_id", "status", "area_ha", "yield_t_ha", "baseline_t_ha", "model_name", "model_version", "technology_year", "label", "observed_days", "partial_days",
             "filled_days", "filled_gap_days", "filled_future_days", "total_days", "filled_to_maturity", "sow_doy", "mat_doy", "features", "out_of_training_range", "computed_at"]
OBS_VALUES = ["tmean", "tmax", "tmin", "precip", "pet"]


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(SCHEMA)

    def tx(self):
        return _Tx(self)

    def close(self):
        self.db.close()

    def bump(self, name, by=1):
        if by:
            with self.lock:
                self.db.execute("INSERT INTO counters VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = value + excluded.value", (name, by))

    def counters(self):
        with self.lock:
            return {r["name"]: r["value"] for r in self.db.execute("SELECT * FROM counters")}

    def set_meta(self, name, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (name, json.dumps(value)))

    def get_meta(self, name):
        with self.lock:
            r = self.db.execute("SELECT value FROM meta WHERE name = ?", (name,)).fetchone()
        return json.loads(r["value"]) if r else None

    def save_reading(self, r, subscription_id, notified_at):
        """Returns new, duplicate, corrected or stale. See "What happens to imperfect data" in docs/CB_INTEGRATION.md."""
        with self.lock:
            old = self.db.execute("SELECT * FROM observations WHERE cell_id = ? AND date = ?", (r.cell_id, r.day)).fetchone()
            if old is None:
                doy = doy_of(r.day)
                self.db.execute("INSERT INTO observations (cell_id, date, year, doy, in_window, tmean, tmax, tmin, precip, pet, pet_source, entity_id, subscription_id, notified_at, received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (r.cell_id, r.day, int(r.day[:4]), doy, int(in_window(doy)), r.tmean, r.tmax, r.tmin, r.precip, r.pet, r.pet_source, r.entity_id, subscription_id, notified_at, now()))
                return "new"
            merged = {k: getattr(r, k) if getattr(r, k) is not None else old[k] for k in OBS_VALUES}
            if all(merged[k] is None and old[k] is None or (merged[k] is not None and old[k] is not None and abs(merged[k] - old[k]) < 1e-9) for k in OBS_VALUES):
                self.db.execute("UPDATE observations SET duplicates = duplicates + 1 WHERE cell_id = ? AND date = ?", (r.cell_id, r.day))
                return "duplicate"
            if notified_at < old["notified_at"]:
                return "stale"
            self.db.execute("UPDATE observations SET tmean=?, tmax=?, tmin=?, precip=?, pet=?, pet_source=?, entity_id=?, subscription_id=?, notified_at=?, received_at=?, revisions = revisions + 1 WHERE cell_id=? AND date=?",
                            (merged["tmean"], merged["tmax"], merged["tmin"], merged["precip"], merged["pet"], r.pet_source if r.pet is not None else old["pet_source"], r.entity_id, subscription_id, notified_at, now(), r.cell_id, r.day))
            return "corrected"

    def season(self, cell_id, year):
        """In-window readings as dicts."""
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM observations WHERE cell_id = ? AND year = ? AND in_window = 1 ORDER BY doy", (cell_id, year))]

    def seasons(self, cell_id=None, year=None):
        where, args = _where(cell_id=cell_id, year=year)
        with self.lock:
            return [dict(r) for r in self.db.execute(f"SELECT cell_id, year, COUNT(*) AS stored_days, SUM(in_window) AS in_window_days, MIN(date) AS first_date, MAX(date) AS last_date, SUM(duplicates) AS duplicates, SUM(revisions) AS corrections, "
                                                     f"SUM(pet_source = 'hargreaves') AS pet_derived_days, MAX(received_at) AS last_received_at FROM observations {where} GROUP BY cell_id, year ORDER BY year DESC, cell_id", args)]

    def add_rejected(self, subscription_id, entity_id, reason, excerpt):
        with self.lock:
            self.db.execute("INSERT INTO rejected (received_at, subscription_id, entity_id, reason, excerpt) VALUES (?,?,?,?,?)", (now(), subscription_id, entity_id, reason, excerpt))
            self.db.execute("DELETE FROM rejected WHERE id < (SELECT MAX(id) - 1000 FROM rejected)")

    def recent_rejected(self, limit=20):
        with self.lock:
            return [dict(r) for r in self.db.execute("SELECT * FROM rejected ORDER BY id DESC LIMIT ?", (limit,))]

    def save_predictions(self, preds):
        rows = [tuple(json.dumps(p[c]) if c in ("features", "out_of_training_range") else p[c] for c in PRED_COLS) for p in preds]
        with self.lock:
            self.db.executemany(f"INSERT OR REPLACE INTO predictions ({','.join(PRED_COLS)}) VALUES ({','.join('?' * len(PRED_COLS))})", rows)

    def predictions(self, cell_id=None, parcel_id=None, farm_id=None, crop=None, year=None, latest=False, limit=1000):
        where, args = _where(cell_id=cell_id, parcel_id=parcel_id, farm_id=farm_id, crop=crop, year=year)
        q = f"SELECT * FROM predictions {where}"
        if latest:
            q = f"SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY parcel_id, crop, year ORDER BY as_of_date DESC) AS rn FROM predictions {where}) WHERE rn = 1"
        with self.lock:
            rows = self.db.execute(q + " ORDER BY as_of_date DESC, parcel_id, crop LIMIT ?", args + [limit]).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d.pop("rn", None)
            d["features"], d["out_of_training_range"] = json.loads(d["features"]), json.loads(d["out_of_training_range"])
            out.append(d)
        return out

    def unsynced(self, limit=200):
        """The latest estimate of each parcel, crop and season still to send. Older ones are superseded."""
        with self.lock:
            rows = self.db.execute("SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY parcel_id, crop, year ORDER BY as_of_date DESC) AS rn FROM predictions WHERE synced_at IS NULL) WHERE rn = 1 LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def mark_synced(self, preds):
        with self.lock, self.tx():
            self.db.executemany("UPDATE predictions SET synced_at = ? WHERE parcel_id = ? AND crop = ? AND year = ? AND (as_of_date < ? OR (as_of_date = ? AND computed_at <= ?))",
                                [(now(), p["parcel_id"], p["crop"], p["year"], p["as_of_date"], p["as_of_date"], p["computed_at"]) for p in preds])

    def count_unsynced(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) AS n FROM predictions WHERE synced_at IS NULL").fetchone()["n"]

    def totals(self):
        with self.lock:
            return dict(observations=self.db.execute("SELECT COUNT(*) AS n FROM observations").fetchone()["n"], predictions=self.db.execute("SELECT COUNT(*) AS n FROM predictions").fetchone()["n"],
                        rejected=self.db.execute("SELECT COUNT(*) AS n FROM rejected").fetchone()["n"])

    def delete_season(self, cell_id, year):
        with self.lock, self.tx():
            a = self.db.execute("DELETE FROM observations WHERE cell_id = ? AND year = ?", (cell_id, year)).rowcount
            b = self.db.execute("DELETE FROM predictions WHERE cell_id = ? AND year = ?", (cell_id, year)).rowcount
        return dict(observations=a, predictions=b)


def _where(**filters):
    used = {k: v for k, v in filters.items() if v is not None}
    return ("WHERE " + " AND ".join(f"{k} = ?" for k in used) if used else ""), list(used.values())


class _Tx:
    """A transaction that holds the lock. Nesting joins the outer one."""
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        self.store.lock.acquire()
        self.outer = self.store.db.in_transaction
        if not self.outer:
            self.store.db.execute("BEGIN")

    def __exit__(self, kind, value, tb):
        try:
            if not self.outer:
                self.store.db.execute("ROLLBACK" if kind else "COMMIT")
        finally:
            self.store.lock.release()
