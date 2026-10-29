"""CONFIRM engine: ask the bank, never the paper.

Channels, strongest first (the registry says which ones each bank supports):
  Tier 1  e-FDR digitally signed by the bank (PAdES, checked against the bank's certificate),
          or a QR code that opens an allow-listed bank domain
  Tier 2  the bank's term-deposit verification API (amount, dates, lien, status)
  Tier 3  a signed one-time confirmation link to the branch contact held in the registry
          (contact details printed on the receipt are never used)
Every confirmed field records its source and time, so the portal can show
"institution says" next to "bank confirms", as the PS requires.
"""
import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import fitz
import httpx

from . import config, db, read

HOST = urlparse(config.BANK_BASE).netloc
PKI = config.PKI

# Sandbox banks: fictional names and IFSC prefixes (production: banks onboarded by AICTE)
BANKS = {
    "XSNB": {"name": "Sandbox National Bank", "signing_ca": str(PKI / "bank-ca.pem"), "qr_domains": [HOST],
             "api": True, "contact": "td-confirm@xsnb.bank.sandbox", "sla_days": 2, "aa": True},
    "XSCB": {"name": "Specimen Commercial Bank", "signing_ca": None, "qr_domains": [HOST],
             "api": True, "contact": "deposits@xscb.bank.sandbox", "sla_days": 2, "aa": True},
    "XECB": {"name": "Example Urban Co-operative Bank", "signing_ca": None, "qr_domains": [],
             "api": True, "contact": "fd-desk@xecb.bank.sandbox", "sla_days": 3, "aa": False},
    "XMRB": {"name": "Model Rural Bank", "signing_ca": None, "qr_domains": [],
             "api": False, "contact": "branch-ops@xmrb.bank.sandbox", "sla_days": 5, "aa": False},
}

# Stands in for RBI's NEFT/RTGS IFSC list (production: the published list, refreshed monthly)
BRANCHES = {
    "XSNB0000101": "Sector 17, Chandigarh", "XSNB0000214": "Connaught Place, New Delhi",
    "XSNB0000307": "Kothrud, Pune", "XSNB0000412": "Janpath, Bhubaneswar",
    "XSCB0000913": "MG Road, Bengaluru", "XSCB0000927": "Salt Lake, Kolkata", "XSCB0000935": "Civil Lines, Jaipur",
    "XECB0000042": "Ameerpet, Hyderabad", "XECB0000058": "Sector 11, Gandhinagar",
    "XMRB0000005": "Rampur, Lucknow district", "XMRB0000011": "Anna Nagar, Chennai",
}


def bank_for(ifsc):
    return BANKS.get((ifsc or "")[:4])


def res(code, title, outcome, detail, tier, evidence=None, severity="hard", ref=None):
    return {"engine": "CONFIRM", "code": code, "title": title, "outcome": outcome, "detail": detail,
            "severity": severity, "weight": 0, "rule_ref": ref, "evidence": {"tier": tier, **(evidence or {})}}


def inr(x):
    if x is None:
        return "–"
    s = f"{x:,.2f}"
    whole, dec = s.split(".")
    digits = whole.replace(",", "")
    if len(digits) > 3:  # Indian grouping: 12,34,56,789
        head, tail = digits[:-3], digits[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        whole = f"{head},{tail}"
    return f"₹{whole}" + ("" if dec == "00" else f".{dec}")


# ---------------------------------------------------------------- Tier 1
def signature_check(path, bank):
    try:
        from pyhanko.keys import load_cert_from_pemder
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko_certvalidator import ValidationContext
    except Exception:
        return None, 0
    with open(path, "rb") as fh:
        try:
            sigs = PdfFileReader(fh).embedded_signatures
        except Exception:
            return None, 0
        if not sigs:
            return None, 0
        if not bank or not bank.get("signing_ca"):
            return res("sig_unknown", "Signed, but the registry has no certificate for this bank", config.DECLARED,
                       "The signature cannot be tied to a registered bank, so it is not counted.", 1), len(sigs)
        vc = ValidationContext(trust_roots=[load_cert_from_pemder(bank["signing_ca"])], allow_fetching=False)
        st = validate_pdf_signature(sigs[-1], vc)
        who = st.signing_cert.subject.native.get("common_name", "unknown") if st.signing_cert else "unknown"
        if st.bottom_line and st.coverage.name == "ENTIRE_FILE":
            return res("sig_valid", "Bank's digital signature is valid; file untouched since signing", config.CONFIRMED,
                       f"Signed by {who}; chain verified to the bank's registered certificate.", 1,
                       {"signer": who}), len(sigs)
        if st.intact and st.valid and st.trusted:
            return res("sig_modified", "File was changed after the bank signed it", config.DISCREPANCY,
                       f"The signature by {who} is genuine but covers an earlier version; content was added later.",
                       1, {"signer": who}), len(sigs)
        return res("sig_invalid", "Digital signature does not verify", config.DISCREPANCY,
                   f"Signer {who}; integrity intact: {st.intact}; trusted chain: {st.trusted}.", 1), len(sigs)


def qr_check(path, mime, bank):
    import cv2
    import numpy as np
    imgs = []
    if mime == "application/pdf":
        for pi, pg in enumerate(fitz.open(path)):
            pix = pg.get_pixmap(dpi=200)
            imgs.append((pi, np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3], 72 / 200))
    else:
        imgs.append((0, cv2.imread(path), 1.0))
    det = cv2.QRCodeDetector()
    allowed = set((bank or {}).get("qr_domains", []))
    for pi, img, sc in imgs:
        try:
            ok, decoded, pts, _ = det.detectAndDecodeMulti(img)
        except Exception:
            continue
        for k, url in enumerate(decoded if ok else []):
            if not url:
                continue
            q = pts[k]
            box = [float(q[:, 0].min() * sc), float(q[:, 1].min() * sc), float(q[:, 0].max() * sc), float(q[:, 1].max() * sc)]
            host = urlparse(url).netloc or url
            if host in allowed:
                return {"url": url, "trusted": True, "page": pi, "bbox": box}, None
            return {"url": url, "trusted": False}, res(
                "qr_untrusted", "QR code opens a website the bank does not use", config.DISCREPANCY,
                f"The QR opens {host}. The registry lists {', '.join(sorted(allowed)) or 'no QR domain'} for this bank. "
                "A look-alike verification page is how a fake receipt passes a quick phone scan.", 1,
                {"url": url, "page": pi, "bbox": box}, ref="Bank registry: allow-listed domains only")
    return None, None


# ---------------------------------------------------------------- Tier 2
def bank_lookup(ifsc, fdr_no):
    """Returns (record or None, error or None). None + None means the bank says: no such deposit."""
    try:
        r = httpx.get(f"{config.BANK_BASE}/api/v1/term-deposits/{ifsc}/{fdr_no}",
                      headers={"X-Api-Key": config.BANK_API_KEY}, timeout=8)
    except httpx.HTTPError as e:
        return None, type(e).__name__
    if r.status_code == 404:
        return None, None
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}"
    return r.json(), None


def compare(fields, rec, bank_name):
    """Field-by-field: paper vs bank. Returns (results, confirmed_fields)."""
    out, conf = [], {}
    v = lambda k: (fields.get(k) or {}).get("value")
    pairs = [("amount_inr", "amount", "Amount"), ("deposit_date", "deposit_date", "Date of deposit"),
             ("maturity_date", "maturity_date", "Maturity date")]
    diffs = []
    for fk, bk, label in pairs:
        conf[fk] = rec.get(bk)
        if v(fk) is not None and rec.get(bk) is not None and str(v(fk)) != str(rec.get(bk)) and \
                not (isinstance(v(fk), float) and abs(v(fk) - float(rec[bk])) < 1):
            shown = (inr(v(fk)), inr(rec[bk])) if fk == "amount_inr" else (v(fk), rec[bk])
            diffs.append((fk, label, *shown))
    conf["depositor"] = rec.get("depositor")
    if v("depositor") and rec.get("depositor") and not read.similar(v("depositor"), rec["depositor"]):
        diffs.append(("depositor", "Depositor", v("depositor"), rec["depositor"]))
    for fk, label, paper, bank in diffs:
        f = fields.get(fk) or {}
        out.append(res(f"bank_differs_{fk}", f"{label} on the receipt differs from the bank's record", config.DISCREPANCY,
                       f"Receipt shows {paper}; {bank_name} records {bank}.", 2,
                       {"page": f.get("page"), "bbox": f.get("bbox"), "paper": paper, "bank": bank},
                       ref="PS SIH26265: distinguish submitted from bank-confirmed"))
    conf["status"] = rec.get("status")
    if rec.get("status") == "CLOSED":
        out.append(res("bank_closed_early", "Deposit was closed early at the bank", config.DISCREPANCY,
                       f"{bank_name} closed this deposit on {rec.get('closed_on')}; the receipt still looks valid. "
                       "Paper checks find this only at maturity.", 2,
                       {"closed_on": rec.get("closed_on")}, ref="Deposit must stay in force for the prescribed period"))
    conf["lien"] = rec.get("lien_aicte")
    if not rec.get("lien_aicte"):
        f = fields.get("lien") or {}
        out.append(res("bank_no_lien", "Bank has no lien in AICTE's favour", config.DISCREPANCY,
                       f"{bank_name} shows the deposit free of any lien, so it can be withdrawn without AICTE's consent.",
                       2, {"page": f.get("page"), "bbox": f.get("bbox")},
                       ref="Affidavit: not to be encashed without AICTE's prior consent"))
    return out, conf


# ---------------------------------------------------------------- Tier 3
def make_token(instrument_id, bank_code):
    raw = f"{instrument_id}|{bank_code}|{datetime.now(timezone.utc).isoformat()}"
    return hmac.new(config.CONFIRM_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:24]


def tier3_request(instrument_id, bank_code, bank):
    token = make_token(instrument_id, bank_code)
    now = datetime.now(timezone.utc)
    with db.tx() as c:
        c.execute("INSERT INTO confirmations(token,instrument_id,bank_code,contact,state,created_at) VALUES(?,?,?,?,?,?)",
                  (token, instrument_id, bank_code, bank["contact"], "sent", now.isoformat(timespec="seconds")))
    due = (now + timedelta(days=bank["sla_days"])).date().isoformat()
    return res("t3_sent", "Confirmation request sent to the bank branch", config.DECLARED,
               f"A signed one-time link went to {bank['contact']} (from the bank registry, not from the receipt). "
               f"Answer due by {due}; no answer escalates to the Regional Officer.", 3,
               {"token": token, "contact": bank["contact"], "due": due}, severity="info")


# ---------------------------------------------------------------- run
def run(path, mime, fields, instrument_id):
    """Returns (results, bank_record_view, channel, signed_revisions)."""
    ifsc = (fields.get("ifsc") or {}).get("value")
    fdr_no = (fields.get("fdr_no") or {}).get("value")
    bank = bank_for(ifsc)
    out, view, channel = [], None, None
    sig, revs = signature_check(path, bank) if mime == "application/pdf" else (None, 0)
    if sig:
        out.append(sig)
        channel = "Tier 1 · e-FDR signature" if sig["code"] == "sig_valid" else None
    qr, bad = qr_check(path, mime, bank)
    if bad:
        out.append(bad)
    if not bank:
        out.append(res("bank_unknown", "Bank is not in the registry", config.DISCREPANCY,
                       f"IFSC {ifsc or '(missing)'} does not belong to any bank AICTE can verify with.", 0,
                       ref="Bank registry"))
        return out, view, channel, revs
    if bank["api"] and ifsc and fdr_no:
        rec, err = bank_lookup(ifsc, fdr_no)
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if err:
            out.append(res("bank_unreachable", "Bank service did not answer", config.DECLARED,
                           f"{bank['name']} API: {err}. The check is retried automatically.", 2, severity="info"))
        elif rec is None:
            f = fields.get("fdr_no") or {}
            out.append(res("bank_not_found", "Bank has no record of this deposit", config.DISCREPANCY,
                           f"{bank['name']} found no deposit {fdr_no} at {ifsc}. The receipt may be fabricated.", 2,
                           {"page": f.get("page"), "bbox": f.get("bbox")}, ref="PS SIH26265: verify through bank sources"))
        else:
            diffs, conf = compare(fields, rec, bank["name"])
            out += diffs
            view = {**conf, "source": f"{bank['name']} API", "ts": stamp}
            if not diffs:
                out.append(res("bank_confirmed", f"{bank['name']} confirms every field", config.CONFIRMED,
                               f"Amount {inr(rec['amount'])}, deposited {rec['deposit_date']}, matures {rec['maturity_date']}, "
                               f"lien marked to AICTE, status {rec['status'].lower()}.", 2, {"ts": stamp}))
                channel = channel or "Tier 2 · bank API"
    elif ifsc and fdr_no:
        out.append(tier3_request(instrument_id, ifsc[:4], bank))
    if qr and qr.get("trusted"):
        out.append(res("qr_trusted", "QR code opens the bank's own verification page", config.CONFIRMED,
                       f"{qr['url']}", 1, {"page": qr["page"], "bbox": qr["bbox"]}, severity="info"))
    return out, view, channel, revs
