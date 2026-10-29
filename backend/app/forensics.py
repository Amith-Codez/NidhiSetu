"""DETECT engine: signs that an FDR file was altered after the bank produced it.

Every finding carries evidence (page + box, or the measured value) so an officer can see why.
These are SOFT signals: they raise a risk score and can send a document to manual review,
but on their own they never mark a document as forged.
"""
import hashlib
import io
import re
from collections import Counter
from datetime import datetime

import fitz
import numpy as np
from PIL import Image, ImageChops

from . import config

EDITORS = re.compile(r"photoshop|gimp|canva|ilovepdf|smallpdf|pixlr|paint|sejda|pdfescape", re.I)
KEY_FIELDS = ("amount_inr", "maturity_date", "deposit_date", "fdr_no", "maturity_value", "favour")


def finding(code, title, detail, evidence=None, weight=None, outcome="flag"):
    return {"engine": "DETECT", "code": code, "title": title, "detail": detail, "outcome": outcome,
            "severity": "soft", "weight": config.WEIGHTS.get(code, 0) if weight is None else weight,
            "evidence": evidence or {}}


def _pdf_date(s):
    if not s:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})", s)
    return datetime(int(m[1]), int(m[2]), int(m[3])).date() if m else None


def pdf_forensics(path, fields, signed_revisions=0):
    out = []
    raw = open(path, "rb").read()
    doc = fitz.open(path)
    meta = doc.metadata or {}
    producer = f"{meta.get('producer', '')} {meta.get('creator', '')}".strip()

    if EDITORS.search(producer):
        out.append(finding("editor_software", "Saved by an image or PDF editor",
                           f"PDF producer is \"{producer}\". Genuine issuer files come from the issuer's system.",
                           {"producer": producer}))

    created, modified = _pdf_date(meta.get("creationDate")), _pdf_date(meta.get("modDate"))
    issue = (fields.get("deposit_date") or {}).get("value")
    if modified and issue and modified.isoformat() > issue and created and modified > created:
        out.append(finding("post_issue_edit", "File changed after the issue date",
                           f"Created {created}, modified {modified}; the document says it was issued {issue}.",
                           {"created": str(created), "modified": str(modified), "issued": issue}))

    eof = raw.count(b"%%EOF")
    extra = eof - 1 - signed_revisions
    if extra > 0:
        out.append(finding("incremental_saves", "Edited and saved again after it was made",
                           f"{extra} later revision(s) appended to the file.", {"revisions": eof}))

    # A white box painted over printed text, with new text on top: the classic manual edit.
    for pi, pg in enumerate(doc):
        spans = [s for b in pg.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
                 if s["text"].strip()]
        for d in pg.get_drawings():
            fill = d.get("fill")
            if not fill or min(fill) < 0.97 or d.get("type") not in ("f", "fs"):
                continue
            r = d["rect"]
            if r.width < 15 or r.height < 6 or r.width > pg.rect.width * 0.8:
                continue
            covered = [s for s in spans if fitz.Rect(s["bbox"]).intersects(r)]
            if covered:
                fonts_here = Counter((s["font"], round(s["size"])) for s in spans).most_common(1)[0][0]
                on_top = [s["text"].strip() for s in covered if (s["font"], round(s["size"])) != fonts_here]
                hidden = [s["text"].strip() for s in covered if (s["font"], round(s["size"])) == fonts_here]
                detail = ("A white box was painted over printed text and new text written on top. "
                          + (f"Hidden underneath: \"{' '.join(hidden)[:70]}\". " if hidden else "")
                          + (f"Shown on top: \"{' '.join(on_top)[:40]}\"." if on_top else ""))
                out.append(finding("pdf_overlay_edit", "White patch painted over text", detail,
                                   {"page": pi, "bbox": [r.x0, r.y0, r.x1, r.y1], "hidden": hidden, "on_top": on_top}))
                break

        # Key field printed in a different font from the rest of the page
        fonts = Counter((s["font"], round(s["size"])) for s in spans)
        body_font = fonts.most_common(1)[0][0] if fonts else None
        for f in KEY_FIELDS:
            fv = fields.get(f)
            if not fv or fv.get("page") != pi or not fv.get("raw"):
                continue
            for s in spans:
                if fv["raw"][:6] and fv["raw"][:6] in s["text"]:
                    if body_font and (s["font"], round(s["size"])) != body_font and s["font"] != "Helvetica-Bold":
                        out.append(finding("field_font_mismatch", "Key value printed in a different font",
                                           f"\"{s['text'].strip()}\" uses {s['font']} {s['size']:.1f}pt; "
                                           f"the page uses {body_font[0]} {body_font[1]}pt.",
                                           {"page": pi, "bbox": list(s["bbox"])}))
                    break
    return out


def embedded_images(path):
    """Yield (page, bbox, PIL image, sha256 of raw bytes) for each image placed on the pages."""
    doc = fitz.open(path)
    for pi, pg in enumerate(doc):
        for info in pg.get_images(full=True):
            xref = info[0]
            try:
                data = doc.extract_image(xref)["image"]
                rects = pg.get_image_rects(xref)
                im = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:
                continue
            bbox = list(rects[0]) if rects else None
            yield pi, bbox, im, hashlib.sha256(data).hexdigest()


def ela_hotspot(img, quality=90, block=32):
    """Error level analysis: re-save as JPEG and find a block that changes far more than the rest."""
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    diff = np.asarray(ImageChops.difference(img, Image.open(buf)).convert("L"), dtype=np.float32)
    h, w = diff.shape
    scores = []
    for y in range(0, h - block, block):
        for x in range(0, w - block, block):
            scores.append((diff[y:y + block, x:x + block].mean(), x, y))
    if not scores:
        return None
    vals = np.array([s[0] for s in scores])
    med = np.median(vals)
    mad = max(np.median(np.abs(vals - med)), 0.35)
    best = max(scores)
    z = (best[0] - med) / mad
    return {"z": float(z), "bbox": [best[1], best[2], best[1] + block, best[2] + block], "size": [w, h]} if z > 12 else None
