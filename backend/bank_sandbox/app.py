"""Bank sandbox: stands in for a bank's term-deposit verification service.

Fictional banks only. Run:  uvicorn bank_sandbox.app:app --port 8200
  GET  /api/v1/term-deposits/{ifsc}/{fdr_no}   Tier 2 lookup (needs X-Api-Key), as a bank API would answer
  GET  /v/{ifsc}/{fdr_no}                        the page a receipt's QR code opens
  POST /admin/close/{ifsc}/{fdr_no}              demo control: the depositor closes the FD early
"""
import json
import os
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

RECORDS = Path(os.environ.get("NIDHI_BANK_RECORDS", Path(__file__).resolve().parent / "records.json"))
NO_API = {"XMRB"}  # the rural bank has no API: Tier 3 (branch confirmation) only
KEY = "sandbox-aicte-regulation-bureau"
app = FastAPI(title="Bank sandbox (synthetic)")


def _load():
    return json.loads(RECORDS.read_text()) if RECORDS.exists() else {}


def _save(d):
    RECORDS.write_text(json.dumps(d, indent=1))


@app.get("/health")
def health():
    return {"ok": True, "deposits": len(_load())}


@app.get("/api/v1/term-deposits/{ifsc}/{fdr_no}")
def lookup(ifsc: str, fdr_no: str, x_api_key: str = Header(default="")):
    if ifsc[:4] in NO_API:
        raise HTTPException(501, "This bank offers no verification API")
    if x_api_key != KEY:
        raise HTTPException(401, "Unknown caller")
    rec = _load().get(f"{ifsc}|{fdr_no}")
    if not rec:
        raise HTTPException(404, "No such term deposit")
    return rec


@app.get("/v/{ifsc}/{fdr_no}", response_class=HTMLResponse)
def qr_page(ifsc: str, fdr_no: str):
    rec = _load().get(f"{ifsc}|{fdr_no}")
    body = (f"<p>Deposit <b>{fdr_no}</b> at {ifsc}: <b>{rec['status'].lower()}</b>, matures {rec['maturity_date']}.</p>"
            if rec else "<p><b>No such deposit.</b></p>")
    return f"<html><body style='font-family:sans-serif;padding:24px'><h3>Bank sandbox · deposit check</h3>{body}" \
           f"<p style='color:#777'>Synthetic data for testing.</p></body></html>"


@app.post("/admin/close/{ifsc}/{fdr_no}")
def close_early(ifsc: str, fdr_no: str):
    d = _load()
    rec = d.get(f"{ifsc}|{fdr_no}")
    if not rec:
        raise HTTPException(404)
    rec.update(status="CLOSED", closed_on=date.today().isoformat(), lien_aicte=False)
    _save(d)
    return {"ok": True}
