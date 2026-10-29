"""Image helpers shared by the FDR generator: rubber-stamp seals, scans, signatures, QR codes, PAdES signing.

Everything produced is synthetic: fictional banks, fictional institutions, made-up numbers.
"""
import io
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import fitz
import imagehash
import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
PKI = ROOT / "pki"
PKI.mkdir(exist_ok=True)


def _font(size):
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
    return ImageFont.load_default()


def make_seal_master(text, color=(36, 52, 130), star=True, size=420):
    im = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    c = size // 2
    d.ellipse([10, 10, size - 10, size - 10], outline=color + (255,), width=12)
    d.ellipse([46, 46, size - 46, size - 46], outline=color + (255,), width=5)
    f = _font(30)
    text = f" {text} •" * 2
    n = len(text)
    for i, ch in enumerate(text):
        ang = 2 * math.pi * i / n - math.pi / 2
        x, y = c + (c - 30) * math.cos(ang) * 0.86, c + (c - 30) * math.sin(ang) * 0.86
        g = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
        ImageDraw.Draw(g).text((20, 20), ch, font=f, fill=color + (255,), anchor="mm")
        g = g.rotate(-math.degrees(ang) - 90, resample=Image.BICUBIC)
        im.alpha_composite(g, (int(x) - 20, int(y) - 20))
    if star:
        pts = []
        for k in range(10):
            r = 70 if k % 2 == 0 else 30
            a = math.pi * k / 5 - math.pi / 2
            pts.append((c + r * math.cos(a), c + r * math.sin(a)))
        d.polygon(pts, fill=color + (255,))
    else:
        d.rectangle([c - 60, c - 30, c + 60, c + 30], outline=color + (255,), width=6)
    return im


def scan(master, seed):
    """Simulate a rubber-stamp impression scanned on paper: rotation, ink density, blur, noise."""
    rnd = random.Random(seed)
    im = master.rotate(rnd.uniform(-4, 4), resample=Image.BICUBIC, expand=False)
    bg = Image.new("RGB", im.size, (250, 249, 244))
    bg.paste(im, (0, 0), im)
    px = bg.load()
    for _ in range(2500):
        x, y = rnd.randrange(im.width), rnd.randrange(im.height)
        v = rnd.randint(-28, 28)
        r, g, b = px[x, y]
        px[x, y] = (max(0, min(255, r + v)), max(0, min(255, g + v)), max(0, min(255, b + v)))
    bg = bg.filter(ImageFilter.GaussianBlur(rnd.uniform(0.6, 1.2)))
    return bg.resize((200, 200))


def signature_img(name, seed):
    rnd = random.Random(seed)
    im = Image.new("RGB", (360, 110), (255, 255, 255))
    d = ImageDraw.Draw(im)
    x, y = 14, 64
    pts = []
    for i in range(46):
        x += rnd.uniform(5, 9)
        y = 60 + 26 * math.sin(i / 2.2 + rnd.uniform(-.4, .4)) * rnd.uniform(.5, 1)
        pts.append((x, y))
    d.line(pts, fill=(20, 30, 90), width=3, joint="curve")
    return im


def qr_img(url):
    q = qrcode.QRCode(box_size=6, border=2)
    q.add_data(url)
    q.make()
    return q.make_image(fill_color="black", back_color="white").convert("RGB")


def _png(im):
    b = io.BytesIO()
    im.save(b, "PNG")
    b.seek(0)
    return ImageReader(b)


TITLES = {
    "fire_noc": ("FIRE SAFETY NO OBJECTION CERTIFICATE", "Divisional Fire Officer"),
    "building_completion": ("BUILDING COMPLETION CERTIFICATE", "Executive Engineer (Buildings)"),
    "lease_deed": ("LEASE DEED (REGISTERED) - SUMMARY OF REGISTRATION", "Sub-Registrar"),
    "fdr": ("FIXED DEPOSIT RECEIPT", "Branch Manager"),
    "affidavit": ("AFFIDAVIT - UNDERTAKING FOR AICTE APPROVAL", "Notary Public"),
    "faculty_list": ("FULL-TIME FACULTY DECLARATION", "Principal / Director"),
}
COLORS = {"fire_noc": "#8B1E1E", "building_completion": "#1E4D8B", "lease_deed": "#3D3D3D",
          "fdr": "#0F5A3A", "affidavit": "#3D3D3D", "faculty_list": "#24346E"}


def build_pdf(path, doc_type, issuer_name, lines, seal=None, sig=None, qr_url=None, rows=None,
              producer="ReportLab PDF Library - www.reportlab.com", footer=None):
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setProducer(producer)
    c.setCreator("Issuer records system")
    W, H = A4
    col = HexColor(COLORS[doc_type])
    c.setFillColor(col)
    c.rect(0, H - 72, W, 72, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 12.5)
    c.drawString(40, H - 36, issuer_name.upper())
    c.setFont("Helvetica", 8.5)
    c.drawString(40, H - 54, "SANDBOX ISSUER - SYNTHETIC DOCUMENT FOR TESTING - NOT A REAL CERTIFICATE")
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W / 2, H - 112, TITLES[doc_type][0])
    y = H - 150
    c.setFont("Helvetica", 10.5)
    for ln in lines:
        c.drawString(56, y, ln)
        y -= 21
    if rows:
        y -= 6
        c.setFont("Helvetica-Bold", 9.5)
        c.drawString(56, y, "S.No.   Name                         Faculty ID           Designation          Joined")
        y -= 16
        c.setFont("Helvetica", 9.5)
        for i, r in enumerate(rows, 1):
            c.drawString(56, y, f"{i:>3}.   {r['name']:<28} {r['id']:<20} {r['role']:<20} {r['joined']}")
            y -= 15
    if footer:
        c.setFont("Helvetica", 9)
        c.drawString(56, 250, footer)
    if qr_url:
        c.drawImage(_png(qr_img(qr_url)), 56, 96, 92, 92)
        c.setFont("Helvetica", 10.5)
        c.drawString(160, 150, f"Verify at: {qr_url}")
    if sig:
        c.drawImage(_png(sig), W - 250, 128, 150, 46)
    if seal:
        c.drawImage(_png(seal), W - 150, 92, 96, 96)
    c.setFont("Helvetica", 9.5)
    c.drawString(W - 250, 112, TITLES[doc_type][1])
    c.save()


def sign_pdf(src, dst, key, cert, ca):
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    signer = signers.SimpleSigner.load(key, cert, ca_chain_files=(ca,))
    with open(src, "rb") as inf:
        w = IncrementalPdfFileWriter(inf)
        meta = signers.PdfSignatureMetadata(field_name="IssuerSignature")
        with open(dst, "wb") as outf:
            signers.sign_pdf(w, meta, signer=signer, output=outf)


def overlay_edit(src, dst, old, new, fontname="Times-Roman", fontsize=11):
    """Forge by painting a white box over printed text and writing new text: the common manual edit."""
    doc = fitz.open(src)
    pg = doc[0]
    hits = pg.search_for(old)
    if not hits:
        raise ValueError(f"text not found: {old}")
    r = hits[0]
    pg.draw_rect(fitz.Rect(r.x0 - 1, r.y0 - 1, r.x1 + 14, r.y1 + 1), color=None, fill=(1, 1, 1))
    pg.insert_text((r.x0, r.y1 - 2), new, fontname=fontname, fontsize=fontsize, color=(0.07, 0.07, 0.07))
    if str(src) == str(dst):
        doc.save(dst, incremental=True, encryption=0)
    else:
        doc.save(dst)


def specimen_hash(master):
    return str(imagehash.phash(scan(master, seed=0)))
