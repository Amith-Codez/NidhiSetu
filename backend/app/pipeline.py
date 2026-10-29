"""Check one receipt end to end: READ -> CHECK -> CONFIRM (bank) -> DETECT -> DECIDE."""
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import fitz
from PIL import Image

from . import audit, banks, config, db, forensics, read, rules

logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
PROGRESS = {}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _step(doc_id, stage, text, t0):
    PROGRESS.setdefault(doc_id, []).append({"stage": stage, "text": text, "ms": int((time.perf_counter() - t0) * 1000)})


def event(instrument_id, kind, text, actor="system", ts=None):
    with db.tx() as c:
        c.execute("INSERT INTO events(instrument_id,ts,kind,actor,text) VALUES(?,?,?,?,?)",
                  (instrument_id, ts or now(), kind, actor, text))


def render_pages(path, mime, doc_id):
    out = []
    if mime == "application/pdf":
        for i, pg in enumerate(fitz.open(path)):
            name = f"{doc_id}-p{i}.png"
            pg.get_pixmap(matrix=fitz.Matrix(2, 2)).save(str(config.RENDERS / name))
            out.append({"name": name, "w": pg.rect.width, "h": pg.rect.height})
    else:
        im = Image.open(path).convert("RGB")
        name = f"{doc_id}-p0.png"
        im.save(config.RENDERS / name)
        out.append({"name": name, "w": im.width, "h": im.height})
    return out


def decide(results):
    hard_bad = [r for r in results if r["outcome"] == config.DISCREPANCY and r["severity"] == "hard"]
    confirmed = any(r["code"] in ("bank_confirmed", "sig_valid") for r in results)
    soft = sum(r["weight"] for r in results if r["severity"] == "soft" and r["outcome"] == "flag")
    verification = config.DISCREPANCY if hard_bad else config.CONFIRMED if confirmed else config.DECLARED
    return verification, min(100, soft + (70 if hard_bad else 0))


def save_checks(instrument_id, document_id, results, replace=True):
    with db.tx() as c:
        if replace:
            c.execute("DELETE FROM checks WHERE instrument_id=?", (instrument_id,))
        for r in results:
            c.execute("INSERT INTO checks(instrument_id,document_id,engine,code,title,outcome,severity,weight,detail,"
                      "evidence,rule_ref,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                      (instrument_id, document_id, r["engine"], r["code"], r["title"], r["outcome"], r["severity"],
                       r.get("weight", 0), r["detail"], db.j(r.get("evidence") or {}), r.get("rule_ref"), now()))


def process(instrument_id, document_id, actor="system"):
    t0 = time.perf_counter()
    PROGRESS[document_id] = []
    doc = db.q1("SELECT * FROM documents WHERE id=?", (document_id,))
    inst = db.q1("SELECT * FROM instruments WHERE id=?", (instrument_id,))
    path, mime = doc["path"], doc["mime"]

    r = read.run(path, mime)
    fields = r["fields"]
    _step(document_id, "READ", f"{'Fixed deposit receipt' if r['is_fdr'] else 'Not an FDR'}: {len(fields)} fields read"
                               + (" by OCR" if r["kind"] == "image" else ""), t0)

    results = rules.run(fields, inst["required_amount"], inst["required_until"], inst["institution_id"], instrument_id)
    failed = sum(1 for x in results if x["outcome"] == config.DISCREPANCY)
    _step(document_id, "CHECK", f"{len(results)} rules applied" + (f", {failed} failed" if failed else ", all passed"), t0)

    conf, view, channel, revs = banks.run(path, mime, fields, instrument_id)
    results += conf
    head = next((x for x in conf if x["severity"] == "hard" and x["outcome"] == config.DISCREPANCY), None) or \
        next((x for x in conf if x["code"] in ("bank_confirmed", "sig_valid", "t3_sent", "bank_unreachable")), None)
    _step(document_id, "CONFIRM", head["title"] if head else "No bank channel available", t0)

    det = forensics.pdf_forensics(path, fields, revs) if mime == "application/pdf" else []
    if mime != "application/pdf":
        hot = forensics.ela_hotspot(Image.open(path).convert("RGB"))
        if hot:
            det.append(forensics.finding("ela_hotspot", "One area of the photo was pasted in",
                                         f"Error level {hot['z']:.0f}x the rest of the image.",
                                         {"page": 0, "bbox": hot["bbox"]}))
    results += det
    _step(document_id, "DETECT", f"{len(det)} tampering sign(s)" if det else "No tampering signs", t0)

    verification, risk = decide(results)
    declared = {k: f["value"] for k, f in fields.items()}
    v = lambda k: (view or {}).get(k) if verification == config.CONFIRMED and view else declared.get(k)
    with db.tx() as c:
        c.execute("UPDATE documents SET fields=?, pages=? WHERE id=?", (db.j(fields), len(r["pages"]), document_id))
        c.execute("UPDATE instruments SET declared=?, bank=?, verification=?, risk=?, channel=?, bank_code=?, ifsc=?, "
                  "fdr_no=?, amount=?, deposit_date=?, maturity_date=?, last_confirmed=? WHERE id=?",
                  (db.j(declared), db.j(view), verification, risk, channel, (declared.get("ifsc") or "")[:4],
                   declared.get("ifsc"), declared.get("fdr_no"), v("amount_inr") or declared.get("amount_inr"),
                   v("deposit_date") or declared.get("deposit_date"), v("maturity_date") or declared.get("maturity_date"),
                   (view or {}).get("ts"), instrument_id))
    save_checks(instrument_id, document_id, results)
    render_pages(path, mime, document_id)
    _step(document_id, "DECIDE", f"{verification} (risk {risk})", t0)
    event(instrument_id, "verified", f"Checked: {verification.lower()}" + (f" via {channel}" if channel else ""), actor)
    audit.log(actor, "instrument.checked", instrument_id, {"document": document_id, "verification": verification,
                                                           "risk": risk, "channel": channel})
    return {"verification": verification, "risk": risk, "ms": int((time.perf_counter() - t0) * 1000)}


def add_document(instrument_id, src_path, filename):
    from . import storage
    ext = Path(filename).suffix.lower() or ".pdf"
    mime = "application/pdf" if ext == ".pdf" else "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    local, sha = storage.put(src_path, ext)
    doc_id = "DOC-" + sha[:10].upper()
    with db.tx() as c:
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        c.execute("INSERT INTO documents(id,instrument_id,filename,path,sha256,mime,created_at) VALUES(?,?,?,?,?,?,?)",
                  (doc_id, instrument_id, filename, local, sha, mime, now()))
    audit.log("institution", "document.uploaded", doc_id, {"instrument": instrument_id, "sha256": sha})
    return doc_id
