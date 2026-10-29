"""Seed the demo: fictional institutions, their security-deposit FDRs at every lifecycle stage,
the matching records at the sandbox banks, and the real-case fraud patterns.

Needs the bank sandbox running (uvicorn bank_sandbox.app:app --port 8200).
usage: python scripts/seed_demo.py
"""
import json
import random
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fdrgen  # noqa: E402
from app import audit, config, db, lifecycle, pipeline, releases  # noqa: E402
docgen = fdrgen.docgen

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "bank_sandbox" / "records.json"
DOCS = config.DATA / "demo_docs"
SAMPLES = config.DATA / "samples"
T = date.today()
rnd = random.Random(26265)

REGIONS = ["Northern", "North-West", "Western", "South-West", "Southern", "South-Central", "Eastern", "Central"]
NAMES = ["Sample College of Engineering", "Model Institute of Technology", "Test School of Management",
         "Prototype Polytechnic", "Specimen College of Pharmacy", "Illustrative School of Architecture",
         "Reference Institute of Technology", "Example College of Engineering", "Demo Institute of Management",
         "Placeholder Polytechnic", "Pilot College of Pharmacy", "Mock Institute of Technology",
         "Sample Institute of Management", "Model College of Engineering", "Test Institute of Technology",
         "Prototype College of Pharmacy", "Specimen Institute of Technology", "Illustrative College of Engineering",
         "Reference School of Management", "Example Polytechnic", "Demo College of Engineering",
         "Placeholder Institute of Technology", "Pilot School of Architecture", "Mock College of Engineering"]
TRUSTS = ["Educational Trust", "Education Society", "Shiksha Samiti", "Vidya Trust"]
IFSC = {"XSNB": ["XSNB0000101", "XSNB0000214", "XSNB0000307", "XSNB0000412"],
        "XSCB": ["XSCB0000913", "XSCB0000927", "XSCB0000935"], "XECB": ["XECB0000042", "XECB0000058"],
        "XMRB": ["XMRB0000005", "XMRB0000011"]}


def ago(days):
    return (T - timedelta(days=days)).isoformat()


def ts(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def months_back(maturity_in_days, months):
    """Deposit date such that a `months` deposit matures `maturity_in_days` from today."""
    mat = T + timedelta(days=maturity_in_days)
    total = mat.year * 12 + (mat.month - 1) - months
    return date(total // 12, total % 12 + 1, min(mat.day, 28)).isoformat()


def main():
    db.reset()
    for d in (config.UPLOADS, config.RENDERS, config.LETTERS, DOCS, SAMPLES):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    insts = []
    with db.tx() as c:
        for k, name in enumerate(NAMES):
            iid = f"INS-{k + 1:03d}"
            trust = f"{name.split()[0]} {TRUSTS[k % 4]}"
            region = REGIONS[k % 8]
            c.execute("INSERT INTO institutions(id,name,region,trust,email) VALUES(?,?,?,?,?)",
                      (iid, name, region, trust, f"principal@{iid.lower()}.edu.sandbox"))
            insts.append({"id": iid, "name": name, "trust": trust, "region": region})
    records, plan, n = {}, [], [0]

    def add(inst, bank, maturity_in, months=60, amount=None, required=None, story=None, status="ACTIVE",
            lien=True, sign=None, paper=None, bank_amount=None, register=True, closed_on=None):
        n[0] += 1
        ifsc = rnd.choice(IFSC[bank])
        fdr_no = f"{rnd.choice(['501', '502', '660', '771'])}{rnd.randint(10**10, 10**11 - 1)}"
        amount = amount or rnd.choice([1000000, 1500000, 2500000, 3500000])
        dep = months_back(maturity_in, months)
        rec = fdrgen.record(ifsc, fdr_no, f"{inst['trust']} ({inst['name']})", bank_amount or amount, dep, months,
                            rate=rnd.choice([6.8, 7.0, 7.1, 7.25, 7.5]), status=status, lien=lien)
        rec["closed_on"] = closed_on
        if register:
            records[f"{ifsc}|{fdr_no}"] = rec
        iid = f"FDR-{n[0]:04d}"
        plan.append({"id": iid, "inst": inst, "rec": {**rec, "amount": float(amount)}, "bank_rec": rec, "required": required or amount,
                     "sign": bank == "XSNB" if sign is None else sign, "story": story, "paper": paper or {}})
        return iid

    g = insts
    # active, bank-confirmed deposits across the four banks
    active = [add(g[k], ["XSNB", "XSCB", "XECB"][k % 3], rnd.randint(140, 1500)) for k in range(14)]
    # approaching maturity: reminders at 90 / 60 / 30 / 7 days
    exp = [add(g[14], "XSNB", 82), add(g[15], "XSCB", 41), add(g[16], "XECB", 24), add(g[17], "XSNB", 5)]
    # matured with no renewal: action due, escalated to RO, escalated to RB
    mat = [add(g[18], "XSCB", -6), add(g[19], "XECB", -19), add(g[20], "XSNB", -44)]
    # renewed: an old deposit and its bank-confirmed replacement
    old_new = [(add(g[k], "XSNB", -60 - 30 * k, status="RENEWED"), add(g[k], "XSNB", 1765 - 30 * k)) for k in (1, 4, 7)]
    # releases at three stages (term completed)
    rel = [add(g[k], "XSCB", -12 - k) for k in (9, 11, 13)]
    # rural bank without an API: Tier 3 branch confirmation
    t3 = [add(g[21], "XMRB", 900), add(g[22], "XMRB", 1300)]
    # the real-case patterns
    fake = add(g[23], "XSNB", 1200, register=False, sign=False,
               story="Receipt the bank never issued (pattern of the Chandigarh MC case, 2026)")
    altered = add(g[2], "XECB", 1100, amount=2500000, bank_amount=250000, paper={"overlay": ("2,50,000.00", "25,00,000.00")},
                  story="Amount raised on the paper from ₹2.5 lakh to ₹25 lakh with a white patch")
    closed = add(g[5], "XSCB", 700, story="Deposit closed early at the bank; paper still looks valid (pattern of the Panchkula MC case, 2026)")
    dup_src = active[3]
    dup = add(g[8], "XSNB", 1000, sign=False, story="Same FDR already pledged by another institution")
    nolien = add(g[10], "XECB", 1400, lien=False, paper={"favour": "Example Vidya Trust"},
                 story="Drawn in favour of the trust, no lien for AICTE")
    demo = add(g[12], "XSNB", 1600, story="Use this one in the live demo: let the bank close it, then run the monitor")

    # the duplicate pledges the same receipt as dup_src
    src = next(p for p in plan if p["id"] == dup_src)
    dp = next(p for p in plan if p["id"] == dup)
    records.pop(f"{dp['rec']['ifsc']}|{dp['rec']['fdr_no']}", None)
    dp["rec"] = {**src["rec"], "depositor": f"{g[8]['trust']} ({g[8]['name']})"}
    RECORDS.write_text(json.dumps(records, indent=1))

    for p in plan:
        r = p["rec"]
        path = DOCS / f"{p['id']}.pdf"
        base = p["bank_rec"] if "overlay" in p["paper"] else r  # a forger edits a real, smaller receipt
        fdrgen.receipt(path, base, seed=int(p["id"][-4:]) * 7, sign=p["sign"], favour_text=p["paper"].get("favour"),
                       lien_text="No" if p["paper"].get("favour") else None)
        if "overlay" in p["paper"]:
            docgen.overlay_edit(path, path, *p["paper"]["overlay"])
        with db.tx() as c:
            c.execute("INSERT INTO instruments(id,institution_id,kind,required_amount,required_until,verification,created_at,story) "
                      "VALUES(?,?,?,?,?,?,?,?)", (p["id"], p["inst"]["id"], "FDR", p["required"], r["maturity_date"],
                                                   config.DECLARED, ts(400), p["story"]))
        pipeline.event(p["id"], "submitted", f"FDR uploaded by {p['inst']['name']}", "institution", ts(380))
        doc = pipeline.add_document(p["id"], str(path), f"{p['id']}.pdf")
        pipeline.process(p["id"], doc, actor="system")
        with db.tx() as c:  # seeded history: checked the day after upload, last bank check some weeks ago
            c.execute("UPDATE events SET ts=? WHERE instrument_id=? AND kind='verified'", (ts(379), p["id"]))
            c.execute("UPDATE instruments SET last_confirmed=? WHERE id=? AND last_confirmed IS NOT NULL",
                      (ts(rnd.randint(8, 70)), p["id"]))
        print(p["id"], p["inst"]["id"], db.q1("SELECT verification FROM instruments WHERE id=?", (p["id"],))["verification"])

    # renewed chains
    for old, new in old_new:
        with db.tx() as c:
            c.execute("UPDATE instruments SET replaced_by=? WHERE id=?", (new, old))
            c.execute("UPDATE instruments SET replaces=? WHERE id=?", (old, new))
        pipeline.event(old, "renewed", f"Replaced by {new}, confirmed by the bank", "institution", ts(40))
    # releases at three stages
    r1 = releases.start(rel[0], "term_completed", "Principal (institution)", ts=ts(9))
    r2 = releases.start(rel[1], "term_completed", "Principal (institution)", ts=ts(20))
    releases.advance(r2, "scrutinise", "A. Verma (Dealing hand)", "All conditions met", ts=ts(17))
    releases.advance(r2, "recommend", "S. Iyer (Section Officer)", "Recommended for release", ts=ts(14))
    r3 = releases.start(rel[2], "term_completed", "Principal (institution)", ts=ts(35))
    releases.advance(r3, "scrutinise", "A. Verma (Dealing hand)", "All conditions met", ts=ts(31))
    releases.advance(r3, "recommend", "S. Iyer (Section Officer)", "Recommended", ts=ts(28))
    releases.advance(r3, "approve", "Dr. R. Menon (Competent authority)", "Approved", ts=ts(25))
    releases.advance(r3, "discharge", "Regulation Bureau", "Lien removal letter sent", ts=ts(24))
    # one Tier 3 request is past the bank's SLA
    with db.tx() as c:
        c.execute("UPDATE confirmations SET created_at=? WHERE instrument_id=?", (ts(8), t3[1]))
    # the early closure: confirmed months ago, closed at the bank since then
    rec = json.loads(RECORDS.read_text())
    cp = next(p for p in plan if p["id"] == closed)
    rec[f"{cp['rec']['ifsc']}|{cp['rec']['fdr_no']}"].update(status="CLOSED", closed_on=ago(41), lien_aicte=False)
    RECORDS.write_text(json.dumps(rec, indent=1))
    with db.tx() as c:
        c.execute("UPDATE instruments SET last_confirmed=? WHERE id=?", (ts(95), closed))
    print("monitor:", lifecycle.run(actor="monitor"))

    # sample receipts for the Verify page
    samples = {
        "01__Genuine_e-FDR_digitally_signed": (active[0], {}),
        "02__Receipt_the_bank_never_issued": (fake, {}),
        "03__Amount_raised_with_a_white_patch": (altered, {}),
        "04__Deposit_closed_early_at_the_bank": (closed, {}),
        "05__Already_pledged_by_another_college": (dup, {}),
        "06__No_lien_for_AICTE": (nolien, {}),
        "07__QR_opens_a_look-alike_site": (active[1], {"qr": "http://xscb-fd-verify.in/check"}),
    }
    for name, (iid, opt) in samples.items():
        src = DOCS / f"{iid}.pdf"
        if "qr" in opt:
            p = next(p for p in plan if p["id"] == iid)
            fake_rec = {**p["rec"], "fdr_no": p["rec"]["fdr_no"][:-3] + "999"}
            fdrgen.receipt(SAMPLES / f"{name}.pdf", fake_rec, seed=7, qr_url=opt["qr"])
        else:
            shutil.copyfile(src, SAMPLES / f"{name}.pdf")
    fdrgen.phone_scan(DOCS / f"{active[2]}.pdf", SAMPLES / "08__Genuine_receipt_phone_photo.jpg")
    audit.log("system", "demo.seeded", "sandbox", {"instruments": len(plan), "demo_instrument": demo})
    print("seeded", len(plan), "instruments; demo instrument", demo)


if __name__ == "__main__":
    main()
