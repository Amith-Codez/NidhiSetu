"""Storage layer. One codebase, two backends, chosen by DATABASE_URL:

  production / pilot:  postgresql+psycopg://...   (PostgreSQL 16)
  laptop demo:          sqlite:///data/nidhisetu.db (default, zero setup)
"""
import json
import os
import threading
from contextlib import contextmanager

from sqlalchemy import create_engine

from .config import DB_PATH

URL = os.environ.get("DATABASE_URL", f"sqlite:///{DB_PATH}")
IS_PG = URL.startswith("postgresql")
engine = create_engine(URL, pool_pre_ping=True, future=True,
                       connect_args={} if IS_PG else {"check_same_thread": False})
_lock = threading.RLock()
AUTO = "BIGSERIAL PRIMARY KEY" if IS_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS institutions(
      id TEXT PRIMARY KEY, name TEXT, region TEXT, trust TEXT, email TEXT, synthetic INTEGER DEFAULT 1)""",
    # one row per security deposit / FDR; declared = what the paper says, bank = what the bank confirmed
    """CREATE TABLE IF NOT EXISTS instruments(
      id TEXT PRIMARY KEY, institution_id TEXT, kind TEXT, bank_code TEXT, ifsc TEXT, fdr_no TEXT,
      amount REAL, deposit_date TEXT, maturity_date TEXT, required_amount REAL, required_until TEXT,
      declared TEXT, bank TEXT, verification TEXT, risk INTEGER, last_confirmed TEXT, channel TEXT,
      replaces TEXT, replaced_by TEXT, released INTEGER DEFAULT 0, selfcheck INTEGER DEFAULT 0,
      created_at TEXT, story TEXT)""",
    """CREATE TABLE IF NOT EXISTS documents(
      id TEXT PRIMARY KEY, instrument_id TEXT, filename TEXT, path TEXT, sha256 TEXT, mime TEXT,
      pages INTEGER, fields TEXT, created_at TEXT)""",
    f"""CREATE TABLE IF NOT EXISTS checks(
      id {AUTO}, instrument_id TEXT, document_id TEXT, engine TEXT, code TEXT, title TEXT, outcome TEXT,
      severity TEXT, weight INTEGER, detail TEXT, evidence TEXT, rule_ref TEXT, created_at TEXT)""",
    f"""CREATE TABLE IF NOT EXISTS events(
      id {AUTO}, instrument_id TEXT, ts TEXT, kind TEXT, actor TEXT, text TEXT)""",
    f"""CREATE TABLE IF NOT EXISTS alerts(
      id {AUTO}, instrument_id TEXT, kind TEXT, level TEXT, title TEXT, detail TEXT, due TEXT,
      state TEXT, created_at TEXT, key TEXT UNIQUE)""",
    f"""CREATE TABLE IF NOT EXISTS notifications(
      id {AUTO}, alert_id INTEGER, instrument_id TEXT, channel TEXT, recipient TEXT, subject TEXT, sent_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS releases(
      id TEXT PRIMARY KEY, instrument_id TEXT, grounds TEXT, state TEXT, requested_at TEXT,
      checklist TEXT, steps TEXT, letter TEXT)""",
    """CREATE TABLE IF NOT EXISTS confirmations(
      token TEXT PRIMARY KEY, instrument_id TEXT, bank_code TEXT, contact TEXT, state TEXT,
      created_at TEXT, answered_at TEXT, answer TEXT)""",
    f"""CREATE TABLE IF NOT EXISTS audit(
      seq {AUTO}, ts TEXT, actor TEXT, action TEXT, subject TEXT, payload TEXT, prev_hash TEXT, hash TEXT)""",
    "CREATE INDEX IF NOT EXISTS checks_inst ON checks(instrument_id)",
    "CREATE INDEX IF NOT EXISTS events_inst ON events(instrument_id)",
    "CREATE INDEX IF NOT EXISTS inst_fdr ON instruments(ifsc, fdr_no)",
]
TABLES = ("checks", "events", "notifications", "alerts", "releases", "confirmations", "audit", "documents",
          "instruments", "institutions")


def _sql(s):
    return s.replace("?", "%s") if IS_PG else s


class _Conn:
    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, args=()):
        return self.raw.exec_driver_sql(_sql(sql), tuple(args))


def init():
    with engine.begin() as c:
        for stmt in SCHEMA:
            c.exec_driver_sql(stmt)


init()


@contextmanager
def tx():
    with _lock, engine.begin() as raw:
        yield _Conn(raw)


def q(sql, args=()):
    with _lock, engine.connect() as raw:
        return [dict(r._mapping) for r in raw.exec_driver_sql(_sql(sql), tuple(args)).fetchall()]


def q1(sql, args=()):
    rows = q(sql, args)
    return rows[0] if rows else None


def j(x):
    return json.dumps(x, ensure_ascii=False, default=str)


def unj(s, default=None):
    if s is None:
        return default
    if isinstance(s, (dict, list)):
        return s
    try:
        return json.loads(s)
    except Exception:
        return default


def reset():
    with tx() as c:
        for t in TABLES:
            c.execute(f"DELETE FROM {t}")
        if not IS_PG:
            c.execute("DELETE FROM sqlite_sequence")


def backend_name():
    return "PostgreSQL" if IS_PG else "SQLite (demo mode)"
