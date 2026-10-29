"""NidhiSetu API: the security deposit / FDR portal for AICTE's Regulation Bureau (PS SIH26265)."""
import csv
import io
import shutil
import tempfile
import threading
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit, banks, config, db, lifecycle, pipeline, releases, rules

app = FastAPI(title="NidhiSetu", version="1.0", description="Security deposit / FDR lifecycle portal")
SAMPLES = config.DATA / "samples"


def _rel_map():
    return {r["instrument_id"]: r for r in db.q("SELECT * FROM releases")}


def _rows(where="i.selfcheck=0", args=()):
    rows = db.q("SELECT i.*, n.name AS inst_name, n.region FROM instruments i JOIN institutions n ON n.id=i.institution_id "
                f"WHERE {where} ORDER BY i.maturity_date", args)
    rel = _rel_map()
    tops = defaultdict(list)
    for c in db.q("SELECT instrument_id, title, outcome, severity FROM checks WHERE outcome=? "
                  "ORDER BY CASE engine WHEN 'CONFIRM' THEN 0 ELSE 1 END, id", (config.DISCREPANCY,)):
        tops[c["instrument_id"]].append(c["title"])
    out = []
    for r in rows:
        st = lifecycle.state(r, rel.get(r["id"]))
        m = lifecycle.maturity(r)
        days = (m - date.today()).days if m else None
        bank = banks.bank_for(r["ifsc"]) or {}
        nxt = ("Resolve: " + tops[r["id"]][0]) if r["verification"] == config.DISCREPANCY and tops[r["id"]] else \
            "Waiting for the bank to confirm" if st == config.PENDING else \
            f"Renewal or release overdue by {-days} days" if st == config.MATURED else \
            f"Matures in {days} days: renewal due" if st == config.EXPIRING else \
            f"Release: {rel[r['id']]['state'].lower()}" if st == config.RELEASING else \
            f"Replaced by {r['replaced_by']}" if st == config.RENEWED else \
            "Released; lien removed" if st == config.RELEASED else "In force, confirmed by the bank"
        out.append({"id": r["id"], "institution_id": r["institution_id"], "institution": r["inst_name"],
                    "region": r["region"], "bank": bank.get("name", "Unknown bank"), "ifsc": r["ifsc"],
                    "fdr_no": r["fdr_no"], "amount": r["amount"], "maturity_date": r["maturity_date"],
                    "deposit_date": r["deposit_date"], "days": days, "state": st, "verification": r["verification"],
                    "risk": r["risk"] or 0, "next": nxt, "channel": r["channel"], "story": r["story"]})
    return out


@app.get("/api/health")
def health():
    try:
        up = httpx.get(f"{config.BANK_BASE}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        up = False
    from . import storage
    return {"ok": True, "database": db.backend_name(), "storage": storage.backend_name(),
            "bank_service": "up" if up else "unreachable"}


@app.get("/api/overview")
def overview():
    rows = _rows()
    in_force = [r for r in rows if r["state"] not in (config.RELEASED, config.RENEWED)]
    counts = Counter(r["state"] for r in rows)
    ver = Counter(r["verification"] for r in in_force)
    today = date.today()
    months = []
    for k in range(12):
        y, m = today.year + (today.month - 1 + k) // 12, (today.month - 1 + k) % 12 + 1
        key = f"{y}-{m:02d}"
        hit = [r for r in in_force if (r["maturity_date"] or "").startswith(key)]
        months.append({"month": key, "count": len(hit), "value": sum(r["amount"] or 0 for r in hit)})
    alerts = Counter(a["level"] for a in db.q("SELECT level FROM alerts WHERE state='open'"))
    order = {config.DISCREPANCY: 0}
    attention = sorted([r for r in in_force if r["verification"] == config.DISCREPANCY or
                        r["state"] in (config.MATURED, config.PENDING, config.EXPIRING)],
                       key=lambda r: (order.get(r["verification"], 1), r["days"] if r["days"] is not None else 9999))[:7]
    recent = db.q("SELECT e.*, n.name AS inst_name FROM events e JOIN instruments i ON i.id=e.instrument_id "
                  "JOIN institutions n ON n.id=i.institution_id WHERE i.selfcheck=0 ORDER BY e.ts DESC, e.id DESC LIMIT 7")
    return {"counts": {s: counts.get(s, 0) for s in (config.ACTIVE, config.EXPIRING, config.MATURED, config.RENEWED,
                                                      config.RELEASING, config.RELEASED, config.PENDING)},
            "verification": {k: ver.get(k, 0) for k in (config.CONFIRMED, config.DECLARED, config.DISCREPANCY)},
            "in_force": len(in_force), "value": sum(r["amount"] or 0 for r in in_force),
            "confirmed_value": sum(r["amount"] or 0 for r in in_force if r["verification"] == config.CONFIRMED),
            "institutions": len({r["institution_id"] for r in in_force}), "months": months,
            "alerts": dict(alerts), "attention": attention, "recent": recent,
            "releases": dict(Counter(r["state"] for r in db.q("SELECT state FROM releases")))}


@app.get("/api/instruments")
def instruments(state: str = "", q: str = ""):
    rows = _rows()
    if state:
        rows = [r for r in rows if r["state"] == state or r["verification"] == state]
    if q:
        t = q.lower()
        rows = [r for r in rows if t in f"{r['institution']} {r['id']} {r['fdr_no']} {r['bank']} {r['region']}".lower()]
    return rows


@app.get("/api/instruments/{iid}")
def instrument(iid: str):
    r = db.q1("SELECT * FROM instruments WHERE id=?", (iid,))
    if not r:
        raise HTTPException(404, "No such instrument")
    inst = db.q1("SELECT * FROM institutions WHERE id=?", (r["institution_id"],))
    rel = db.q1("SELECT * FROM releases WHERE instrument_id=?", (iid,))
    doc = db.q1("SELECT * FROM documents WHERE instrument_id=? ORDER BY created_at DESC LIMIT 1", (iid,))
    renders, size = [], None
    if doc:
        renders = [{"name": p.name} for p in sorted(config.RENDERS.glob(f"{doc['id']}-p*.png"))]
        if doc["mime"] == "application/pdf":
            import fitz
            rc = fitz.open(doc["path"])[0].rect
            size = [rc.width, rc.height]
        else:
            from PIL import Image
            size = list(Image.open(doc["path"]).size)
    bank = banks.bank_for(r["ifsc"])
    chain = []
    cur = r
    while cur and cur.get("replaces"):
        cur = db.q1("SELECT id, fdr_no, amount, maturity_date FROM instruments WHERE id=?", (cur["replaces"],))
        if cur:
            chain.append(cur)
            cur = db.q1("SELECT * FROM instruments WHERE id=?", (cur["id"],))
    return {**{k: r[k] for k in ("id", "kind", "ifsc", "fdr_no", "amount", "deposit_date", "maturity_date", "required_amount",
                                 "required_until", "verification", "risk", "last_confirmed", "channel", "replaces",
                                 "replaced_by", "story")},
            "state": lifecycle.state(r, rel), "institution": inst,
            "bank": {"code": (r["ifsc"] or "")[:4], **(bank or {"name": "Unknown bank"}),
                     "branch": banks.BRANCHES.get(r["ifsc"])},
            "declared": db.unj(r["declared"], {}), "bank_view": db.unj(r["bank"]),
            "fields": db.unj(doc["fields"], {}) if doc else {},
            "document": {"id": doc["id"], "filename": doc["filename"], "sha256": doc["sha256"], "renders": renders, "size": size,
                         "created_at": doc["created_at"]} if doc else None,
            "checks": [{**c, "evidence": db.unj(c["evidence"], {})} for c in
                       db.q("SELECT * FROM checks WHERE instrument_id=? ORDER BY id", (iid,))],
            "events": db.q("SELECT * FROM events WHERE instrument_id=? ORDER BY ts DESC, id DESC", (iid,)),
            "alerts": db.q("SELECT * FROM alerts WHERE instrument_id=? ORDER BY id DESC", (iid,)),
            "release": {**rel, "checklist": db.unj(rel["checklist"], []), "steps": db.unj(rel["steps"], [])} if rel else None,
            "history": chain,
            "confirmations": db.q("SELECT token, contact, state, created_at, answered_at FROM confirmations "
                                  "WHERE instrument_id=?", (iid,))}


@app.post("/api/instruments/{iid}/reverify")
def reverify(iid: str):
    doc = db.q1("SELECT id FROM documents WHERE instrument_id=? ORDER BY created_at DESC LIMIT 1", (iid,))
    if not doc:
        raise HTTPException(404, "No receipt on file")
    return pipeline.process(iid, doc["id"], actor="officer")


class Grounds(BaseModel):
    grounds: str = "term_completed"


@app.post("/api/instruments/{iid}/release")
def start_release(iid: str, body: Grounds):
    if db.q1("SELECT id FROM releases WHERE instrument_id=?", (iid,)):
        raise HTTPException(409, "A release request already exists for this deposit")
    return {"id": releases.start(iid, body.grounds)}


@app.get("/api/releases")
def list_releases():
    out = []
    for r in db.q("SELECT r.*, i.fdr_no, i.amount, i.ifsc, n.name AS inst_name, n.region FROM releases r "
                  "JOIN instruments i ON i.id=r.instrument_id JOIN institutions n ON n.id=i.institution_id ORDER BY r.requested_at DESC"):
        out.append({**r, "checklist": db.unj(r["checklist"], []), "steps": db.unj(r["steps"], []),
                    "bank": (banks.bank_for(r["ifsc"]) or {}).get("name"), "grounds_text": releases.GROUNDS.get(r["grounds"], r["grounds"])})
    return out


class Step(BaseModel):
    actor: str
    note: str = ""


@app.post("/api/releases/{rid}/{action}")
def release_step(rid: str, action: str, body: Step):
    try:
        return releases.advance(rid, action, body.actor, body.note)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/letters/{name}")
def letter(name: str):
    p = config.LETTERS / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/pdf")


@app.get("/api/alerts")
def alerts(state: str = "open"):
    return db.q("SELECT a.*, i.fdr_no, i.amount, n.name AS inst_name, n.region FROM alerts a "
                "JOIN instruments i ON i.id=a.instrument_id JOIN institutions n ON n.id=i.institution_id "
                "WHERE (?='' OR a.state=?) ORDER BY a.created_at DESC, a.id DESC", (state, state))


@app.post("/api/alerts/{aid}/ack")
def ack(aid: int):
    with db.tx() as c:
        c.execute("UPDATE alerts SET state='acknowledged' WHERE id=?", (aid,))
    audit.log("officer", "alert.acknowledged", str(aid))
    return {"ok": True}


@app.get("/api/notifications")
def notifications(limit: int = 40):
    return db.q("SELECT n.*, a.level FROM notifications n LEFT JOIN alerts a ON a.id=n.alert_id ORDER BY n.id DESC LIMIT ?",
                (limit,))


class Monitor(BaseModel):
    reconfirm_all: bool = False


@app.post("/api/monitor/run")
def monitor(body: Monitor):
    return lifecycle.run(actor="officer", reconfirm_all=body.reconfirm_all)


@app.get("/api/calendar")
def calendar():
    rows = [r for r in _rows() if r["state"] not in (config.RELEASED, config.RENEWED) and r["maturity_date"]]
    today = date.today()
    horizon = (today + timedelta(days=400)).isoformat()
    soon = sorted([r for r in rows if r["maturity_date"] <= horizon], key=lambda r: r["maturity_date"])
    return {"rows": soon, "overdue": [r for r in rows if r["days"] is not None and r["days"] < 0]}


@app.get("/api/banks")
def bank_registry():
    rows = _rows()
    out = []
    for code, b in banks.BANKS.items():
        mine = [r for r in rows if (r["ifsc"] or "").startswith(code)]
        out.append({"code": code, "name": b["name"], "signed_efdr": bool(b["signing_ca"]), "qr_domains": b["qr_domains"],
                    "api": b["api"], "contact": b["contact"], "sla_days": b["sla_days"], "aa": b["aa"],
                    "branches": [{"ifsc": k, "branch": v} for k, v in banks.BRANCHES.items() if k.startswith(code)],
                    "deposits": len(mine), "confirmed": sum(1 for r in mine if r["verification"] == config.CONFIRMED)})
    return out


@app.get("/api/audit")
def audit_log(limit: int = 80):
    return db.q("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))


@app.get("/api/audit/verify")
def audit_verify():
    return audit.verify_chain()


@app.get("/api/rules")
def rulebook():
    return {"text": config.RULES_FILE.read_text(), "parsed": rules.load()}


@app.get("/api/eval")
def evaluation():
    p = config.DATA / "eval" / "results.json"
    return JSONResponse(content=__import__("json").loads(p.read_text()) if p.exists() else {})


# ---------------------------------------------------------------- self-check upload (institution or officer)
def _selfcheck(src, filename):
    iid = "SELF-" + __import__("uuid").uuid4().hex[:6].upper()
    with db.tx() as c:
        c.execute("INSERT OR IGNORE INTO institutions(id,name,region,trust,email) VALUES('SELF','Self-check upload','—','—','—')"
                  if not db.IS_PG else "INSERT INTO institutions(id,name,region,trust,email) VALUES('SELF','Self-check upload','—','—','—') ON CONFLICT DO NOTHING")
        c.execute("INSERT INTO instruments(id,institution_id,kind,selfcheck,verification,created_at) VALUES(?,?,?,?,?,?)",
                  (iid, "SELF", "FDR", 1, config.DECLARED, pipeline.now()))
    doc = pipeline.add_document(iid, src, filename)
    threading.Thread(target=pipeline.process, args=(iid, doc, "institution"), daemon=True).start()
    return {"instrument_id": iid, "document_id": doc}


@app.post("/api/verify")
async def verify(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".pdf", ".jpg", ".jpeg", ".png"):
        raise HTTPException(415, "Upload a PDF, JPG or PNG of the fixed deposit receipt.")
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as t:
        shutil.copyfileobj(file.file, t)
    if Path(t.name).stat().st_size > 25 * 1024 * 1024:
        raise HTTPException(413, "The file is larger than 25 MB.")
    return _selfcheck(t.name, file.filename)


@app.get("/api/samples")
def samples():
    return [{"name": p.name, "label": p.stem.split("__", 1)[-1].replace("_", " ")} for p in sorted(SAMPLES.glob("*"))]


@app.post("/api/samples/{name}/verify")
def sample_verify(name: str):
    p = SAMPLES / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return _selfcheck(str(p), p.name)


@app.get("/api/documents/{doc_id}/progress")
def progress(doc_id: str):
    return pipeline.PROGRESS.get(doc_id, [])


@app.get("/api/documents/{doc_id}/file")
def doc_file(doc_id: str):
    d = db.q1("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404)
    return FileResponse(d["path"], media_type=d["mime"], filename=d["filename"])


@app.get("/api/renders/{name}")
def render(name: str):
    p = config.RENDERS / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


# ---------------------------------------------------------------- Tier 3: the bank branch answers
@app.get("/api/confirmations/{token}")
def confirmation(token: str):
    c = db.q1("SELECT * FROM confirmations WHERE token=?", (token,))
    if not c:
        raise HTTPException(404)
    i = db.q1("SELECT i.*, n.name AS inst_name FROM instruments i JOIN institutions n ON n.id=i.institution_id WHERE i.id=?",
              (c["instrument_id"],))
    d = db.unj(i["declared"], {})
    return {"token": token, "state": c["state"], "bank": (banks.BANKS.get(c["bank_code"]) or {}).get("name"),
            "contact": c["contact"], "institution": i["inst_name"], "fdr_no": i["fdr_no"], "ifsc": i["ifsc"],
            "amount": d.get("amount_inr"), "maturity_date": d.get("maturity_date"), "deposit_date": d.get("deposit_date")}


class Answer(BaseModel):
    answer: str
    note: str = ""


@app.post("/api/confirmations/{token}/answer")
def answer(token: str, body: Answer):
    c = db.q1("SELECT * FROM confirmations WHERE token=?", (token,))
    if not c or c["state"] != "sent":
        raise HTTPException(409, "This link has already been used")
    yes = body.answer == "yes"
    ts = pipeline.now()
    bank = banks.BANKS.get(c["bank_code"], {})
    with db.tx() as cx:
        cx.execute("UPDATE confirmations SET state=?, answered_at=?, answer=? WHERE token=?",
                   ("confirmed" if yes else "denied", ts, body.note, token))
        cx.execute("UPDATE instruments SET verification=?, channel=?, last_confirmed=?, risk=? WHERE id=?",
                   (config.CONFIRMED if yes else config.DISCREPANCY, "Tier 3 · branch confirmation" if yes else None, ts,
                    0 if yes else 100, c["instrument_id"]))
    pipeline.save_checks(c["instrument_id"], None, [banks.res(
        "t3_yes" if yes else "t3_no", f"{bank.get('name')} branch {'confirmed' if yes else 'denied'} this deposit",
        config.CONFIRMED if yes else config.DISCREPANCY, body.note or ("Confirmed by the branch through the signed link."
                                                                         if yes else "The branch says it did not issue this FDR."), 3)],
        replace=False)
    pipeline.event(c["instrument_id"], "bank", f"Branch {'confirmed' if yes else 'denied'} the deposit (Tier 3)", c["contact"])
    h = audit.log(c["contact"], "bank.answered", c["instrument_id"], {"answer": body.answer})
    return {"ok": True, "hash": h}


# ---------------------------------------------------------------- demo control: the bank closes a deposit early
@app.post("/api/demo/bank-closes/{iid}")
def demo_close(iid: str):
    i = db.q1("SELECT ifsc, fdr_no FROM instruments WHERE id=?", (iid,))
    r = httpx.post(f"{config.BANK_BASE}/admin/close/{i['ifsc']}/{i['fdr_no']}", timeout=5)
    return {"ok": r.status_code == 200}


# ---------------------------------------------------------------- reports
REPORTS = {"pending-verification": lambda r: r["state"] == config.PENDING,
           "upcoming-maturity": lambda r: r["days"] is not None and 0 <= r["days"] <= 90,
           "overdue": lambda r: r["state"] == config.MATURED,
           "discrepancies": lambda r: r["verification"] == config.DISCREPANCY,
           "all": lambda r: True}


@app.get("/api/reports/{kind}.csv")
def report(kind: str):
    if kind not in REPORTS:
        raise HTTPException(404)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Instrument", "Institution", "Region", "Bank", "IFSC", "FDR No.", "Amount (INR)", "Deposit date",
                "Maturity date", "Days to maturity", "Lifecycle", "Verification", "Next action"])
    for r in _rows():
        if REPORTS[kind](r):
            w.writerow([r["id"], r["institution"], r["region"], r["bank"], r["ifsc"], r["fdr_no"], r["amount"],
                        r["deposit_date"], r["maturity_date"], r["days"], r["state"], r["verification"], r["next"]])
    audit.log("officer", "report.exported", kind)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="nidhisetu-{kind}-{date.today()}.csv"'})


# ---------------------------------------------------------------- the console (single-page app)
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", response_class=HTMLResponse)
    def spa(path: str):
        f = config.FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
