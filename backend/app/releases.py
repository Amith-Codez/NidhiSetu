"""Release / refund of a security deposit: conditions first, two officials, a letter to the bank.

Requested (institution) -> Scrutinised (dealing hand) -> Recommended (Section Officer)
-> Approved (competent authority, never the same person who recommended) -> Discharged
(letter to the bank to remove AICTE's lien). Every step is written to the audit ledger.
"""
import hashlib
from datetime import date

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from . import audit, banks, config, db, lifecycle, pipeline

FLOW = [("scrutinise", "Requested", "Scrutinised", "Dealing hand"),
        ("recommend", "Scrutinised", "Recommended", "Section Officer"),
        ("approve", "Recommended", "Approved", "Competent authority"),
        ("discharge", "Approved", "Discharged", "Regulation Bureau")]
GROUNDS = {"term_completed": "Deposit term completed",
           "closure_approved": "Closure of the institution approved by AICTE",
           "replaced": "Replaced by a new, bank-confirmed FDR",
           "excess": "Deposit exceeds the amount now required"}


def checklist(inst, grounds, dues=False):
    m = lifecycle.maturity(inst)
    open_disc = inst["verification"] == config.DISCREPANCY
    items = [
        {"item": "Grounds allow release", "ok": grounds != "term_completed" or bool(m and m <= date.today()),
         "note": GROUNDS.get(grounds, grounds)},
        {"item": "No open discrepancy on this deposit", "ok": not open_disc,
         "note": "Bank and receipt agree" if not open_disc else "Resolve the discrepancy first"},
        {"item": "No dues pending with AICTE", "ok": not dues, "note": "Checked against fee records" if not dues else "Dues found"},
        {"item": "Deposit confirmed by the bank before release", "ok": inst["verification"] == config.CONFIRMED,
         "note": inst["channel"] or "Not confirmed"},
    ]
    return items


def start(instrument_id, grounds, actor="institution", dues=False, ts=None):
    inst = db.q1("SELECT * FROM instruments WHERE id=?", (instrument_id,))
    rid = "REL-" + hashlib.sha1(f"{instrument_id}{grounds}".encode()).hexdigest()[:6].upper()
    items = checklist(inst, grounds, dues)
    steps = [{"state": "Requested", "by": actor, "role": "Institution", "ts": ts or pipeline.now(),
              "note": GROUNDS.get(grounds, grounds)}]
    with db.tx() as c:
        c.execute("DELETE FROM releases WHERE id=?", (rid,))
        c.execute("INSERT INTO releases(id,instrument_id,grounds,state,requested_at,checklist,steps) VALUES(?,?,?,?,?,?,?)",
                  (rid, instrument_id, grounds, "Requested", ts or pipeline.now(), db.j(items), db.j(steps)))
    pipeline.event(instrument_id, "release", f"Release requested: {GROUNDS.get(grounds, grounds).lower()}", actor, ts)
    audit.log(actor, "release.requested", rid, {"instrument": instrument_id, "grounds": grounds})
    return rid


def advance(rid, action, actor, note="", ts=None):
    rel = db.q1("SELECT * FROM releases WHERE id=?", (rid,))
    if not rel:
        raise ValueError("No such release request")
    steps = db.unj(rel["steps"], [])
    if action == "return":
        steps.append({"state": "Returned", "by": actor, "role": "Officer", "ts": ts or pipeline.now(), "note": note})
        with db.tx() as c:
            c.execute("UPDATE releases SET state='Returned', steps=? WHERE id=?", (db.j(steps), rid))
        audit.log(actor, "release.returned", rid, {"note": note})
        return "Returned"
    step = next((f for f in FLOW if f[0] == action), None)
    if not step or rel["state"] != step[1]:
        raise ValueError(f"Cannot {action} a request that is {rel['state'].lower()}")
    if action == "scrutinise" and not all(i["ok"] for i in db.unj(rel["checklist"], [])) and not note:
        raise ValueError("A condition is not met; record a reason to proceed")
    if action == "approve":
        recommender = next((s["by"] for s in steps if s["state"] == "Recommended"), None)
        if recommender == actor:
            raise ValueError("The official who recommended cannot also approve (maker-checker)")
    steps.append({"state": step[2], "by": actor, "role": step[3], "ts": ts or pipeline.now(), "note": note})
    letter = rel["letter"]
    if action == "discharge":
        letter = discharge_letter(rel["instrument_id"], rid, steps)
    with db.tx() as c:
        c.execute("UPDATE releases SET state=?, steps=?, letter=? WHERE id=?", (step[2], db.j(steps), letter, rid))
        if action == "discharge":
            c.execute("UPDATE instruments SET released=1 WHERE id=?", (rel["instrument_id"],))
            c.execute("UPDATE alerts SET state='closed' WHERE instrument_id=?", (rel["instrument_id"],))
    pipeline.event(rel["instrument_id"], "release", f"Release {step[2].lower()} by {step[3].lower()}", actor, ts)
    h = audit.log(actor, f"release.{step[2].lower()}", rid, {"note": note})
    return {"state": step[2], "hash": h, "letter": letter}


def discharge_letter(instrument_id, rid, steps):
    inst = db.q1("SELECT i.*, n.name AS inst_name FROM instruments i JOIN institutions n ON n.id=i.institution_id "
                 "WHERE i.id=?", (instrument_id,))
    bank = banks.bank_for(inst["ifsc"]) or {"name": "the bank"}
    name = f"{rid}-discharge.pdf"
    c = canvas.Canvas(str(config.LETTERS / name), pagesize=A4)
    W, H = A4
    c.setFillColor(HexColor("#1A0E3D"))
    c.rect(0, H - 64, W, 64, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, H - 34, "REGULATION BUREAU · SECURITY DEPOSIT CELL")
    c.setFont("Helvetica", 8.5)
    c.drawString(40, H - 50, "SANDBOX DEMO LETTER - SYNTHETIC DATA - NOT AN AICTE COMMUNICATION")
    c.setFillColor(HexColor("#111111"))
    y = H - 110
    for ln in [f"Ref: {rid}                                   Date: {date.today().strftime('%d-%m-%Y')}", "",
               "To", f"The Branch Manager, {bank['name']}", f"IFSC {inst['ifsc']} ({banks.BRANCHES.get(inst['ifsc'], '')})", "",
               f"Subject: Removal of lien on FDR No. {inst['fdr_no']}", "",
               f"The security deposit of {banks.inr(inst['amount'])} held by {inst['inst_name']}",
               f"under FDR No. {inst['fdr_no']} has been approved for release.",
               "You are requested to remove the lien marked in favour of the Member Secretary, AICTE,",
               "and to confirm the removal through the verification service.", "",
               "Approval trail:"]:
        c.setFont("Helvetica-Bold" if ln.startswith("Subject") else "Helvetica", 10.5)
        c.drawString(56, y, ln)
        y -= 18
    c.setFont("Helvetica", 9.5)
    for s in steps:
        c.drawString(70, y, f"{s['state']:<13} {s['role']:<22} {s['by']:<22} {s['ts'][:16].replace('T', ' ')}")
        y -= 15
    c.save()
    return name
