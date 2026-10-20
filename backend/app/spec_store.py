"""Saved scans of the 10-table supplier duplicate model (SQLite, one row per scan, result stored gzip-compressed)."""
import gzip
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.getenv("SCAN_DB", Path(__file__).resolve().parent.parent / "data" / "scans.db"))


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
        summary TEXT NOT NULL, result BLOB NOT NULL, entity TEXT NOT NULL DEFAULT 'supplier', source TEXT NOT NULL DEFAULT 'reports')""")
    cols = {r["name"] for r in c.execute("PRAGMA table_info(scans)")}
    for col, ddl in (("entity", "TEXT NOT NULL DEFAULT 'supplier'"), ("source", "TEXT NOT NULL DEFAULT 'reports'")):
        if col not in cols:
            c.execute(f"ALTER TABLE scans ADD COLUMN {col} {ddl}")
    c.execute("""CREATE TABLE IF NOT EXISTS decisions (
        scan_id INTEGER NOT NULL, group_id TEXT NOT NULL, decision TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
        decided_at TEXT NOT NULL, PRIMARY KEY (scan_id, group_id))""")
    return c


def _summary(result: dict) -> dict:
    st = result["stats"]
    return {"suppliers": st["suppliers"], "eligible": st["eligible"], "groups": st["groups"], "byTier": st["byTier"],
            "ml": bool(result.get("model")), "conditions": st.get("conditions", []), "files": [f["file"] for f in result.get("files", []) if f.get("role")]}


def _row(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "name": r["name"], "createdAt": r["created_at"], "status": r["status"], "entity": r["entity"], "source": r["source"],
            **json.loads(r["summary"])}


def save_scan(result: dict, name: str = "", entity: str = "supplier", source: str = "reports") -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    with closing(_conn()) as c, c:
        cur = c.execute("INSERT INTO scans (name, created_at, status, summary, result, entity, source) VALUES (?,?,?,?,?,?,?)",
                        (name.strip() or f"{entity.title()} scan {now.replace('T', ' ')}", now, "COMPLETED", json.dumps(_summary(result)),
                         gzip.compress(json.dumps({**result, "entity": entity}).encode("utf8")), entity, source))
        row = c.execute("SELECT * FROM scans WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row(row)


def list_scans(entity: str | None = None) -> list[dict]:
    with closing(_conn()) as c:
        q, args = "SELECT id,name,created_at,status,summary,entity,source FROM scans", ()
        if entity:
            q, args = q + " WHERE entity=?", (entity,)
        return [_row(r) for r in c.execute(q + " ORDER BY id DESC", args)]


def get_scan(scan_id: int) -> tuple[dict, dict] | None:
    """(scan row, full result) or None."""
    with closing(_conn()) as c:
        r = c.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
    return (_row(r), json.loads(gzip.decompress(r["result"]))) if r else None


DECISIONS = ("Confirmed as duplicate", "Not a duplicate", "Deferred")


def get_decisions(scan_id: int) -> dict[str, dict]:
    with closing(_conn()) as c:
        return {r["group_id"]: {"decision": r["decision"], "comment": r["comment"], "decidedAt": r["decided_at"]}
                for r in c.execute("SELECT * FROM decisions WHERE scan_id=?", (scan_id,))}


def set_decision(scan_id: int, group_id: str, decision: str, comment: str = "") -> dict | None:
    """Record (or, with an empty decision, clear) the reviewer decision of a group; None when the scan does not exist."""
    with closing(_conn()) as c, c:
        if not c.execute("SELECT 1 FROM scans WHERE id=?", (scan_id,)).fetchone():
            return None
        if not decision:
            c.execute("DELETE FROM decisions WHERE scan_id=? AND group_id=?", (scan_id, group_id))
            return {}
        if decision not in DECISIONS:
            raise ValueError(f"Decision must be one of: {', '.join(DECISIONS)}.")
        now = datetime.now().isoformat(timespec="seconds")
        c.execute("INSERT INTO decisions VALUES (?,?,?,?,?) ON CONFLICT(scan_id, group_id) DO UPDATE SET "
                  "decision=excluded.decision, comment=excluded.comment, decided_at=excluded.decided_at",
                  (scan_id, group_id, decision, comment.strip(), now))
    return {"decision": decision, "comment": comment.strip(), "decidedAt": now}


def delete_scan(scan_id: int) -> bool:
    with closing(_conn()) as c, c:
        c.execute("DELETE FROM decisions WHERE scan_id=?", (scan_id,))
        return c.execute("DELETE FROM scans WHERE id=?", (scan_id,)).rowcount > 0
