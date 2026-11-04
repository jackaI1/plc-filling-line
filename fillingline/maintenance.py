"""Small CMMS-style work-order ledger; demo records stay outside git."""
from datetime import datetime, timezone
import sqlite3


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Maintenance:
    def __init__(self, path):
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, asset TEXT NOT NULL, kind TEXT NOT NULL,
            issue TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
            opened_at TEXT NOT NULL, closed_at TEXT, resolution TEXT);
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, at TEXT NOT NULL, message TEXT NOT NULL);
        """)

    def open(self, asset, kind, issue):
        if asset not in {"CV-01", "FV-01", "Line-01"} or kind not in {"corrective", "preventive"}:
            raise ValueError("Choose a known asset and maintenance type")
        if not isinstance(issue, str) or not 1 <= len(issue.strip()) <= 300:
            raise ValueError("Describe the issue in 1–300 characters")
        with self.db:
            cursor = self.db.execute("INSERT INTO orders(asset,kind,issue,opened_at) VALUES (?,?,?,?)",
                                     (asset, kind, issue.strip(), now()))
        return cursor.lastrowid

    def close_order(self, ident, resolution):
        if type(ident) is not int or not isinstance(resolution, str) or not 1 <= len(resolution.strip()) <= 300:
            raise ValueError("Provide an order ID and 1–300 character resolution")
        with self.db:
            changed = self.db.execute("UPDATE orders SET status='closed',closed_at=?,resolution=? WHERE id=? AND status='open'",
                                      (now(), resolution.strip(), ident)).rowcount
        if not changed:
            raise ValueError("Open work order not found")

    def event(self, message):
        with self.db:
            self.db.execute("INSERT INTO events(at,message) VALUES (?,?)", (now(), message))

    def snapshot(self):
        return {"orders": [dict(row) for row in self.db.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100")],
                "events": [dict(row) for row in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 30")]}

    def close(self):
        self.db.close()
