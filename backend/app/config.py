"""Central settings for NidhiSetu, the security deposit / FDR portal (PS SIH26265)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
RENDERS = DATA / "renders"
LETTERS = DATA / "letters"
PKI = ROOT / "pki"
DB_PATH = DATA / "nidhisetu.db"
RULES_FILE = ROOT / "app" / "rules.yaml"
FRONTEND_DIST = ROOT.parent / "frontend" / "dist"

for p in (DATA, UPLOADS, RENDERS, LETTERS, PKI):
    p.mkdir(parents=True, exist_ok=True)

# Bank sandbox: stands in for a bank's term-deposit verification service
BANK_BASE = os.environ.get("NIDHI_BANK_BASE", "http://127.0.0.1:8200")
BANK_API_KEY = os.environ.get("NIDHI_BANK_KEY", "sandbox-aicte-regulation-bureau")
CONFIRM_SECRET = os.environ.get("NIDHI_CONFIRM_SECRET", "local-demo-secret-change-me")

# What the bank says decides the verification status; the paper only proposes values.
CONFIRMED = "Confirmed by bank"
DECLARED = "Declared, awaiting bank"
DISCREPANCY = "Discrepancy found"

# Lifecycle buckets, worded as in the PS: active, expiring, matured, renewed, released, pending
ACTIVE, EXPIRING, MATURED, RENEWED, RELEASING, RELEASED, PENDING = (
    "Active", "Expiring", "Matured", "Renewed", "Release in progress", "Released", "Pending verification")

# Alert schedule (days relative to maturity); configurable without code changes
REMIND_BEFORE = [90, 60, 30, 7]
GRACE_DAYS = 15          # after maturity, time to submit a renewal or a release request
ESCALATE_RO_AFTER = 15   # days overdue -> Regional Officer
ESCALATE_RB_AFTER = 30   # days overdue -> Regulation Bureau
RECONFIRM_EVERY = 90     # days between automatic bank re-confirmations of an active deposit

# Soft signals add up to a 0-100 risk score; hard facts (bank says otherwise) set the status directly
WEIGHTS = {"pdf_overlay_edit": 35, "field_font_mismatch": 25, "post_issue_edit": 15, "editor_software": 8,
           "incremental_saves": 6, "ela_hotspot": 25, "maturity_math": 20, "qr_untrusted": 45}
