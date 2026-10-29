"""Measure NidhiSetu on a labelled set of genuine and forged receipts, and simulate early closures.

Uses its own database and its own bank sandbox (port 8201), so the demo data is untouched.
usage: python scripts/evaluate.py [per_type]     -> data/eval/results.json
"""
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval"
EVAL.mkdir(parents=True, exist_ok=True)
(EVAL / "eval.db").unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{EVAL / 'eval.db'}"
os.environ["NIDHI_BANK_BASE"] = "http://127.0.0.1:8201"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import fdrgen  # noqa: E402
from app import config, db, pipeline  # noqa: E402

PER = int(sys.argv[1]) if len(sys.argv) > 1 else 10
DOCS = EVAL / "docs"
shutil.rmtree(DOCS, ignore_errors=True)
DOCS.mkdir(parents=True)
RECS = EVAL / "records.json"
rnd = random.Random(91)
BANKS = ["XSNB", "XSCB", "XECB"]
IFSCS = {"XSNB": "XSNB0000214", "XSCB": "XSCB0000913", "XECB": "XECB0000042"}
GROUPS = {
    "genuine_pdf": ("Genuine receipt (PDF)", "genuine"), "genuine_photo": ("Genuine receipt, phone photo", "genuine"),
    "not_issued": ("Receipt the bank never issued", "forged"), "amount_raised": ("Amount raised with a white patch", "forged"),
    "maturity_extended": ("Maturity date pushed later", "forged"), "closed_early": ("Closed early at the bank", "forged"),
    "duplicate": ("Already pledged by another college", "forged"), "no_lien": ("No lien for AICTE", "forged"),
    "lookalike_qr": ("QR opens a look-alike site", "forged"), "fake_branch": ("IFSC of a branch that does not exist", "forged"),
}


def rec(k, bank):
    return fdrgen.record(IFSCS[bank], f"77{rnd.randint(10**11, 10**12 - 1)}", f"Eval Trust {k} (Eval College {k})",
                         rnd.choice([1000000, 1500000, 2500000]), f"20{rnd.randint(22, 25)}-0{rnd.randint(1, 9)}-1{rnd.randint(0, 9)}",
                         rnd.choice([60, 84, 96]), rate=rnd.choice([6.8, 7.1, 7.5]))


def main():
    records, cases = {}, []
    for g in GROUPS:
        for k in range({"genuine_pdf": 4 * PER, "genuine_photo": 2 * PER}.get(g, PER)):
            bank = BANKS[k % 3]
            r = rec(f"{g}-{k}", bank)
            path = DOCS / f"{g}-{k}.pdf"
            sign = bank == "XSNB"
            if g in ("genuine_pdf", "genuine_photo", "closed_early", "duplicate"):
                records[f"{r['ifsc']}|{r['fdr_no']}"] = dict(r)
                fdrgen.receipt(path, r, seed=k, sign=sign)
                if g == "closed_early":
                    records[f"{r['ifsc']}|{r['fdr_no']}"].update(status="CLOSED", closed_on="2026-08-01", lien_aicte=False)
                if g == "duplicate":  # the original is pledged first by its own college
                    cases.append(("_pledge", r, path, f"ORIG-{k}"))
                    other = {**r, "depositor": f"Other Trust {k} (Other College {k})"}
                    path = DOCS / f"{g}-{k}-copy.pdf"
                    fdrgen.receipt(path, other, seed=k + 50, sign=False)
            elif g == "amount_raised":
                records[f"{r['ifsc']}|{r['fdr_no']}"] = dict(r)
                fdrgen.receipt(path, r, seed=k, sign=False)
                old = fdrgen.banks.inr(r["amount"]).replace("₹", "") + ".00"
                fdrgen.docgen.overlay_edit(path, path, old, fdrgen.banks.inr(r["amount"] * 10).replace("₹", "") + ".00")
            elif g == "maturity_extended":
                records[f"{r['ifsc']}|{r['fdr_no']}"] = dict(r)
                fdrgen.receipt(path, r, seed=k, sign=False)
                old = fdrgen.d(r["maturity_date"])
                fdrgen.docgen.overlay_edit(path, path, old, old[:-4] + str(int(old[-4:]) + 3))
            elif g == "not_issued":
                fdrgen.receipt(path, r, seed=k, sign=False)
            elif g == "no_lien":
                records[f"{r['ifsc']}|{r['fdr_no']}"] = {**r, "lien_aicte": False}
                fdrgen.receipt(path, r, seed=k, sign=False, favour_text=r["depositor"].split(" (")[0], lien_text="No")
            elif g == "lookalike_qr":
                fdrgen.receipt(path, r, seed=k, sign=False, qr_url="http://bank-fd-verify.in/check")
            elif g == "fake_branch":
                fdrgen.receipt(path, {**r, "ifsc": IFSCS[bank][:-3] + "999"}, seed=k, sign=False)
            if g == "genuine_photo":
                path = fdrgen.phone_scan(path, DOCS / f"{g}-{k}.jpg", seed=k)
            cases.append((g, r, path, f"{g}-{k}"))
    RECS.write_text(json.dumps(records))
    env = {**os.environ, "NIDHI_BANK_RECORDS": str(RECS)}
    bank = subprocess.Popen([sys.executable, "-m", "uvicorn", "bank_sandbox.app:app", "--port", "8201", "--log-level", "warning"],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:8201/health")
                break
            except Exception:
                time.sleep(0.2)
        with db.tx() as c:
            c.execute("INSERT INTO institutions(id,name,region,trust,email) VALUES('EVAL','Eval','—','—','—')")
            c.execute("INSERT INTO institutions(id,name,region,trust,email) VALUES('EVAL-B','Eval B','—','—','—')")
        results = {g: [] for g in GROUPS}
        for g, r, path, cid in cases:
            iid = f"E-{cid}" if g != "_pledge" else f"A-{cid}"
            with db.tx() as c:
                c.execute("INSERT INTO instruments(id,institution_id,kind,required_amount,required_until,verification,created_at) "
                          "VALUES(?,?,?,?,?,?,?)", (iid, "EVAL" if g == "_pledge" else "EVAL-B", "FDR", r["amount"],
                                                    r["maturity_date"], config.DECLARED, pipeline.now()))
            doc = pipeline.add_document(iid, str(path), path.name)
            out = pipeline.process(iid, doc)
            if g == "_pledge":
                continue
            fired = sorted({c["code"] for c in db.q("SELECT code FROM checks WHERE instrument_id=? AND outcome IN (?,?)",
                                                     (iid, config.DISCREPANCY, "flag"), )})
            results[g].append({"verification": out["verification"], "ms": out["ms"], "signals": fired})
            print(f"{cid:22} {out['verification']:24} {out['ms']:5} ms  {', '.join(fired)}")
    finally:
        bank.terminate()

    groups, caught, forged, alarms, genuine, ms_pdf, ms_photo = [], 0, 0, 0, 0, [], []
    for g, (label, kind) in GROUPS.items():
        rows = results[g]
        if kind == "genuine":
            ok = sum(1 for x in rows if x["verification"] == config.CONFIRMED)
            genuine += len(rows)
            alarms += sum(1 for x in rows if x["verification"] == config.DISCREPANCY)
            metric = "confirmed by the bank"
        else:
            ok = sum(1 for x in rows if x["verification"] == config.DISCREPANCY)
            forged += len(rows)
            caught += ok
            metric = "caught"
        (ms_photo if g == "genuine_photo" else ms_pdf).extend(x["ms"] for x in rows)
        sig = {}
        for x in rows:
            for s in x["signals"]:
                sig[s] = sig.get(s, 0) + 1
        groups.append({"group": g, "label": label, "kind": kind, "n": len(rows), "ok": ok, "metric": metric,
                       "signals": sig, "median_ms": int(statistics.median(x["ms"] for x in rows)),
                       "multi_signal": sum(1 for x in rows if len(x["signals"]) >= 2)})

    # Early closure: when is it found? Paper-only checking finds it at maturity; NidhiSetu at the next quarterly re-check.
    sim = random.Random(7)
    paper, ours = [], []
    for _ in range(10000):
        term = sim.choice([60, 84, 96]) * 30.4
        closed_at = sim.uniform(0, term)
        paper.append(term - closed_at)
        ours.append(sim.uniform(0, config.RECONFIRM_EVERY))
    q = lambda a, p: sorted(a)[int(len(a) * p)]
    out = {"documents": genuine + forged, "genuine": genuine, "forged": forged, "caught": caught, "false_alarms": alarms,
           "median_ms_pdf": int(statistics.median(ms_pdf)), "median_ms_photo": int(statistics.median(ms_photo)),
           "multi_signal_types": sum(1 for g in groups if g["kind"] == "forged" and g["multi_signal"] == g["n"]),
           "groups": groups,
           "closure_simulation": {"deposits": 10000, "recheck_days": config.RECONFIRM_EVERY,
                                  "paper_median_days": int(statistics.median(paper)), "paper_p90_days": int(q(paper, .9)),
                                  "ours_median_days": int(statistics.median(ours)), "ours_max_days": config.RECONFIRM_EVERY}}
    (EVAL / "results.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "groups"}, indent=1))


if __name__ == "__main__":
    main()
