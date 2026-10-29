"""READ engine: pull every field off a fixed deposit receipt and remember where it sits on the page.

Digital PDFs: text and positions come straight from the PDF (PyMuPDF).
Scans and phone photos: RapidOCR (ONNX, CPU) reads the image.
The values read here are only what the paper *claims*; the bank decides what is true.
"""
import io
import re
from datetime import datetime

import fitz
from PIL import Image

LABELS = {"bank": "Bank", "branch": "Branch", "ifsc": "IFSC", "fdr_no": "FDR No.", "depositor": "Depositor",
          "favour": "In Favour of", "lien": "Lien Marked", "amount_inr": "Amount (INR)", "rate": "Rate of Interest",
          "deposit_date": "Date of Deposit", "period_months": "Period", "maturity_date": "Maturity Date",
          "maturity_value": "Maturity Value (INR)", "auto_renewal": "Auto Renewal", "verify_url": "Verify at"}
REQUIRED = ["bank", "ifsc", "fdr_no", "depositor", "favour", "amount_inr", "deposit_date", "maturity_date"]
FDR_WORDS = ["FIXED DEPOSIT", "TERM DEPOSIT", "FDR NO", "MATURITY"]
_ocr = None


def _ocr_engine():
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr = RapidOCR()
    return _ocr


def norm(s):
    """Compare text the way a person would: case, spacing and punctuation ignored (OCR drops spaces)."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def similar(a, b, at_least=85):
    from rapidfuzz import fuzz
    return fuzz.ratio(norm(a), norm(b)) >= at_least


def parse_date(s):
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_inr(s):
    m = re.search(r"\d[\d,]*(?:\.\d+)?", s)
    return float(m.group(0).replace(",", "")) if m else None


def typed(field, raw):
    if field in ("deposit_date", "maturity_date"):
        return parse_date(raw)
    if field in ("amount_inr", "maturity_value"):
        return parse_inr(raw)
    if field == "rate":
        m = re.search(r"\d+(?:\.\d+)?", raw)
        return float(m.group(0)) if m else None
    if field == "period_months":
        m = re.search(r"\d+", raw)
        return int(m.group(0)) if m else None
    if field in ("lien", "auto_renewal"):
        return raw.strip().lower().startswith("yes")
    if field == "ifsc":
        m = re.search(r"[A-Z]{4}0[A-Z0-9]{6}", raw.upper().replace(" ", ""))
        return m.group(0) if m else raw.strip()
    if field == "fdr_no":
        return re.sub(r"\s", "", raw)
    return raw.strip()


def load_pages(path, mime):
    """Return pages: [{'text', 'lines':[{'text','bbox'}], 'size':(w,h)}] and the kind ('pdf' or 'image')."""
    pages = []
    if mime == "application/pdf":
        for pg in fitz.open(path):
            lines = [{"text": "".join(s["text"] for s in ln["spans"]).strip(), "bbox": list(ln["bbox"])}
                     for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", [])]
            lines = [ln for ln in lines if ln["text"]]
            if sum(len(ln["text"]) for ln in lines) < 20:  # a scanned PDF: OCR the rendered page
                pix = pg.get_pixmap(dpi=150)
                lines = _ocr_lines(Image.open(io.BytesIO(pix.tobytes("png"))), 72 / 150)
            pages.append({"text": "\n".join(ln["text"] for ln in lines), "lines": lines,
                          "size": (pg.rect.width, pg.rect.height)})
        return pages, "pdf"
    img = Image.open(path).convert("RGB")
    lines = _ocr_lines(img, 1.0)
    return [{"text": "\n".join(ln["text"] for ln in lines), "lines": lines, "size": img.size}], "image"


def _ocr_lines(img, scale):
    import numpy as np
    result, _ = _ocr_engine()(np.array(img))
    lines = [{"text": t, "bbox": [min(p[0] for p in b) * scale, min(p[1] for p in b) * scale,
                                  max(p[0] for p in b) * scale, max(p[1] for p in b) * scale]}
             for b, t, _c in result or []]
    lines.sort(key=lambda ln: (round(ln["bbox"][1] / 6), ln["bbox"][0]))
    return lines


def _label_re(label):
    parts = [re.escape(ch) for ch in re.sub(r"[\s.:()]", "", label)]
    return re.compile(r"\s*" + r"[\s.:()]*".join(parts) + r"[\s.:()]*", re.I)


def extract(pages):
    """Label-based extraction. If a label appears twice (text painted over text), the later,
    visible one wins: what a person reads is what the receipt claims."""
    out = {}
    for pi, pg in enumerate(pages):
        for ln in pg["lines"]:
            for field, label in LABELS.items():
                m = _label_re(label).match(ln["text"])
                if m:
                    raw = ln["text"][m.end():].lstrip(" :.-").strip()
                    if raw:
                        out[field] = {"raw": raw, "value": typed(field, raw), "page": pi, "bbox": ln["bbox"]}
                        top = _painted_over(pg["lines"], ln)
                        if top and typed(field, top["text"]) not in (None, ""):
                            out[field].update(raw=top["text"], value=typed(field, top["text"]), covered=raw,
                                              bbox=[ln["bbox"][0], ln["bbox"][1], max(ln["bbox"][2], top["bbox"][2]), ln["bbox"][3]])
    return out


def _painted_over(lines, ln):
    """Text written on the same baseline over a field's value (a genuine receipt has one text per line)."""
    y0, y1 = ln["bbox"][1], ln["bbox"][3]
    for o in lines:
        if o is ln or o["bbox"][0] < ln["bbox"][0] + 40:
            continue
        overlap = min(y1, o["bbox"][3]) - max(y0, o["bbox"][1])
        if overlap > 0.5 * (y1 - y0):
            return o
    return None


def run(path, mime):
    pages, kind = load_pages(path, mime)
    text = "\n".join(p["text"] for p in pages)
    squashed = re.sub(r"[^A-Z0-9]", "", text.upper())
    is_fdr = sum(1 for w in FDR_WORDS if re.sub(r"[^A-Z0-9]", "", w) in squashed) >= 2
    fields = extract(pages)
    return {"is_fdr": is_fdr, "kind": kind, "pages": pages, "text": text, "fields": fields,
            "missing": [f for f in REQUIRED if f not in fields]}
