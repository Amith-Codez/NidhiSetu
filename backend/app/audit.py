"""Tamper-evident audit log: every entry stores the SHA-256 of the previous entry.

Changing or deleting any past row breaks every hash after it, which `verify_chain` reports.
"""
import hashlib
from datetime import datetime, timezone
from . import db

GENESIS = "0" * 64


def _digest(prev, ts, actor, action, subject, payload):
    raw = "|".join([prev, ts, actor, action, subject, payload]).encode()
    return hashlib.sha256(raw).hexdigest()


def log(actor, action, subject, payload=None):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    p = db.j(payload or {})
    with db.tx() as c:
        last = c.execute("SELECT hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last[0] if last else GENESIS
        h = _digest(prev, ts, actor, action, subject, p)
        c.execute("INSERT INTO audit(ts,actor,action,subject,payload,prev_hash,hash) VALUES(?,?,?,?,?,?,?)",
                  (ts, actor, action, subject, p, prev, h))
    return h


def verify_chain():
    rows = db.q("SELECT * FROM audit ORDER BY seq")
    prev = GENESIS
    for r in rows:
        expect = _digest(prev, r["ts"], r["actor"], r["action"], r["subject"], r["payload"])
        if r["prev_hash"] != prev or r["hash"] != expect:
            return {"ok": False, "entries": len(rows), "broken_at": r["seq"]}
        prev = r["hash"]
    return {"ok": True, "entries": len(rows), "head": prev}
