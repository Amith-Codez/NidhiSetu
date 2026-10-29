"""Core behaviour of NidhiSetu. Run: .venv/bin/python -m pytest -q"""
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import pytest  # noqa: E402

from app import banks, config, db, lifecycle, read, releases, rules  # noqa: E402


def test_indian_grouping():
    assert banks.inr(2500000) == "₹25,00,000"
    assert banks.inr(116840000) == "₹11,68,40,000"


def test_maturity_arithmetic_quarterly():
    assert round(rules.maturity_value(2500000, 7.1, 60)) == 3554367


def test_ocr_tolerant_matching():
    assert read.similar("Sandbox National Bank", "SandboxNational Bank")
    assert not read.similar("Sample Educational Trust", "Example Vidya Trust")


def test_painted_over_value_wins(tmp_path):
    import fdrgen
    r = fdrgen.record("XECB0000042", "77100000000001", "T Trust (T College)", 250000, "2024-01-15", 60)
    p = fdrgen.receipt(tmp_path / "r.pdf", r, seed=1)
    fdrgen.docgen.overlay_edit(p, p, "2,50,000.00", "25,00,000.00")
    f = read.run(str(p), "application/pdf")["fields"]
    assert f["amount_inr"]["value"] == 2500000.0 and f["amount_inr"]["covered"] == "2,50,000.00"


def test_lifecycle_stages():
    t = date.today()
    row = lambda d, **k: {"maturity_date": (t + timedelta(days=d)).isoformat(), "verification": config.CONFIRMED, **k}
    assert lifecycle.state(row(400)) == config.ACTIVE
    assert lifecycle.state(row(30)) == config.EXPIRING
    assert lifecycle.state(row(-1)) == config.MATURED
    assert lifecycle.state(row(400, verification=config.DECLARED)) == config.PENDING
    assert lifecycle.state(row(-1, replaced_by="X")) == config.RENEWED
    assert lifecycle.state(row(-1, released=1)) == config.RELEASED


def test_release_needs_two_different_officials():
    with db.tx() as c:
        c.execute("INSERT INTO institutions(id,name,region,trust,email) VALUES('I1','Inst','Central','T','e')")
        c.execute("INSERT INTO instruments(id,institution_id,kind,ifsc,fdr_no,amount,maturity_date,verification,channel,created_at) "
                  "VALUES('F1','I1','FDR','XSNB0000101','1',1000,?,?,?,?)",
                  ((date.today() - timedelta(days=5)).isoformat(), config.CONFIRMED, "Tier 2 · bank API", "2026-01-01"))
    rid = releases.start("F1", "term_completed")
    releases.advance(rid, "scrutinise", "Clerk")
    releases.advance(rid, "recommend", "Officer A")
    with pytest.raises(ValueError, match="maker-checker"):
        releases.advance(rid, "approve", "Officer A")
    assert releases.advance(rid, "approve", "Officer B")["state"] == "Approved"
