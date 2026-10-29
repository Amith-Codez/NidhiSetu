"""CHECK engine: the rulebook in rules.yaml, applied to what the receipt claims."""
import yaml
from rapidfuzz import fuzz

from . import banks, config, db, read


def load():
    return yaml.safe_load(config.RULES_FILE.read_text())


def _r(rule, outcome, detail, field=None, fields=None, weight=0):
    f = (fields or {}).get(field) or {}
    title = rule.get("fail", rule["title"]) if outcome in (config.DISCREPANCY, "flag") else rule["title"]
    return {"engine": "CHECK", "code": rule["id"], "title": title, "outcome": outcome,
            "severity": rule["severity"], "weight": weight, "detail": detail, "rule_ref": rule["ref"],
            "evidence": {"page": f.get("page"), "bbox": f.get("bbox")} if f else {}}


def maturity_value(principal, rate, months):
    return principal * (1 + rate / 400) ** (months / 3)


def run(fields, required_amount=None, required_until=None, institution_id=None, instrument_id=None):
    v = lambda k: (fields.get(k) or {}).get("value")
    ok, bad = config.CONFIRMED, config.DISCREPANCY
    out = []
    for rule in load()["rules"]:
        k = rule["kind"]
        if k == "required_fields":
            missing = [f for f in rule["fields"] if v(f) in (None, "")]
            out.append(_r(rule, bad if missing else ok,
                          f"Missing or unreadable: {', '.join(missing)}." if missing else "All mandatory fields read."))
        elif k == "favour":
            fav = v("favour") or ""
            key = read.norm(rule["must_contain"])
            hit = key in read.norm(fav) or fuzz.partial_ratio(key, read.norm(fav)) >= 80  # OCR reads "AlCTE"
            out.append(_r(rule, ok if hit else bad, f"In favour of: \"{fav or 'not stated'}\".", "favour", fields))
        elif k == "lien":
            out.append(_r(rule, ok if v("lien") else bad,
                          "Receipt states the lien is marked." if v("lien") else "Receipt does not show a lien for AICTE.",
                          "lien", fields))
        elif k == "min_amount" and required_amount:
            a = v("amount_inr") or 0
            out.append(_r(rule, ok if a >= required_amount else bad,
                          f"Receipt {banks.inr(a)}; required {banks.inr(required_amount)}.", "amount_inr", fields))
        elif k == "covers_until" and required_until:
            m = v("maturity_date") or ""
            out.append(_r(rule, ok if m >= required_until else bad,
                          f"Matures {m or 'unknown'}; must run until {required_until}.", "maturity_date", fields))
        elif k == "ifsc":
            ifsc = v("ifsc") or ""
            bank = banks.bank_for(ifsc)
            named = (v("bank") or "").lower()
            if ifsc not in banks.BRANCHES:
                out.append(_r(rule, bad, f"{ifsc or 'No IFSC'} is not on the branch list.", "ifsc", fields))
            elif bank and named and not read.similar(bank["name"], named):
                out.append(_r(rule, bad, f"{ifsc} belongs to {bank['name']}, but the receipt names \"{v('bank')}\".",
                              "ifsc", fields))
            else:
                out.append(_r(rule, ok, f"{ifsc}: {bank['name']}, {banks.BRANCHES[ifsc]}.", "ifsc", fields))
        elif k == "duplicate" and v("fdr_no"):
            other = db.q1("SELECT id, institution_id, declared FROM instruments WHERE ifsc=? AND fdr_no=? AND id<? "
                          "AND institution_id<>? AND selfcheck=0 ORDER BY id LIMIT 1",
                          (v("ifsc"), v("fdr_no"), instrument_id or "~", institution_id or ""))
            theirs = (db.unj(other["declared"], {}) or {}).get("depositor", "") if other else ""
            if other and not read.similar(theirs, v("depositor")):
                out.append(_r(rule, bad, f"FDR {v('fdr_no')} is already registered as security for {other['institution_id']} "
                                         f"({other['id']}).", "fdr_no", fields))
            else:
                out.append(_r(rule, ok, "No other institution has pledged this FDR."))
        elif k == "maturity_math" and v("amount_inr") and v("rate") and v("period_months") and v("maturity_value"):
            expect = maturity_value(v("amount_inr"), v("rate"), v("period_months"))
            gap = abs(v("maturity_value") - expect) / expect * 100
            if gap > rule["tolerance_pct"]:
                out.append(_r(rule, "flag", f"At {v('rate')}% for {v('period_months')} months, {banks.inr(v('amount_inr'))} "
                                            f"grows to about {banks.inr(round(expect))}; the receipt prints "
                                            f"{banks.inr(v('maturity_value'))} ({gap:.1f}% off).",
                              "maturity_value", fields, weight=config.WEIGHTS["maturity_math"]))
            else:
                out.append(_r(rule, ok, f"Maturity value agrees with the rate and period (within {gap:.2f}%)."))
    return out
