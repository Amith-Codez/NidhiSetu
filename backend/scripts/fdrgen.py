"""Synthetic fixed deposit receipts from the sandbox banks, and the forgeries seen in real cases.

usage: python scripts/fdrgen.py pki      (create the sandbox bank CA, the e-FDR signing certificate and bank seals)
"""
import datetime as dt
import random
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docgen  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import banks, rules  # noqa: E402

PKI = ROOT / "pki"
COLORS = {"XSNB": "#0F4C81", "XSCB": "#7A2E14", "XECB": "#2F5D35", "XMRB": "#5A4A12"}
SEAL_RGB = {"XSNB": (15, 76, 129), "XSCB": (122, 46, 20), "XECB": (47, 93, 53), "XMRB": (90, 74, 18)}


# ---------------------------------------------------------------- PKI for the sandbox banks
def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sandbox Bank Network (synthetic)"),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _key(path):
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    return k


def make_pki():
    now = dt.datetime.now(dt.timezone.utc)
    ca_key = _key(PKI / "bank-ca.key")
    ca = (x509.CertificateBuilder().subject_name(_name("Sandbox Bank Root CA")).issuer_name(_name("Sandbox Bank Root CA"))
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    (PKI / "bank-ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    k = _key(PKI / "XSNB.key")
    cert = (x509.CertificateBuilder().subject_name(_name("Sandbox National Bank - e-FDR Signing")).issuer_name(ca.subject)
            .public_key(k.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=1825))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.EMAIL_PROTECTION]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    (PKI / "XSNB.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    for code, b in banks.BANKS.items():
        docgen.make_seal_master(b["name"].upper(), SEAL_RGB[code], star=code in ("XSNB", "XECB")).save(PKI / f"{code}-seal.png")
    print("sandbox bank PKI and seals ready in", PKI)


# ---------------------------------------------------------------- receipts
def d(iso):
    return dt.date.fromisoformat(iso).strftime("%d-%m-%Y")


def receipt(path, r, seed=1, qr_url="auto", sign=None, favour_text=None, lien_text=None, maturity_value=None):
    """Draw a receipt from a record r (same keys as the bank's record). Returns the path."""
    code = r["ifsc"][:4]
    bank = banks.BANKS.get(code, {"name": r.get("bank_name", "Unknown Bank")})
    W, H = A4
    tmp = Path(str(path) + ".tmp.pdf") if sign else Path(path)
    c = canvas.Canvas(str(tmp), pagesize=A4)
    c.setProducer("Core banking deposit module")
    c.setCreator("Branch deposit desk")
    col = HexColor(COLORS.get(code, "#333333"))
    c.setFillColor(col)
    c.rect(0, H - 70, W, 70, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, H - 34, r.get("bank_name", bank["name"]).upper())
    c.setFont("Helvetica", 8.5)
    c.drawString(40, H - 52, "SANDBOX BANK - SYNTHETIC DOCUMENT FOR TESTING - NOT A REAL DEPOSIT")
    c.setFillColor(HexColor("#111111"))
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W / 2, H - 108, "FIXED DEPOSIT RECEIPT (TERM DEPOSIT ADVICE)")
    c.setStrokeColor(HexColor("#C8C8C8"))
    c.rect(44, H - 470, W - 88, 340, fill=0, stroke=1)
    mv = maturity_value if maturity_value is not None else round(rules.maturity_value(r["amount"], r["rate"], r["months"]), 2)
    lines = [
        f"Bank: {r.get('bank_name', bank['name'])}",
        f"Branch: {banks.BRANCHES.get(r['ifsc'], r.get('branch', 'Main Branch'))}",
        f"IFSC: {r['ifsc']}",
        f"FDR No.: {r['fdr_no']}",
        f"Depositor: {r['depositor']}",
        f"In Favour of: {favour_text or 'Member Secretary, AICTE, New Delhi'}",
        f"Lien Marked: {lien_text or 'Yes - in favour of Member Secretary, AICTE'}",
        f"Amount (INR): {banks.inr(r['amount']).replace('₹', '')}.00" if float(r['amount']).is_integer() else f"Amount (INR): {r['amount']}",
        f"Rate of Interest: {r['rate']:.2f}% p.a., compounded quarterly",
        f"Date of Deposit: {d(r['deposit_date'])}",
        f"Period: {r['months']} months",
        f"Maturity Date: {d(r['maturity_date'])}",
        f"Maturity Value (INR): {banks.inr(mv).replace('₹', '')}",
        f"Auto Renewal: {'Yes' if r.get('auto_renew') else 'No'}",
    ]
    y = H - 156
    c.setFont("Helvetica", 10.5)
    for ln in lines:
        c.drawString(60, y, ln)
        y -= 22
    c.setFont("Helvetica", 8.5)
    c.setFillColor(HexColor("#555555"))
    c.drawString(60, H - 492, "This receipt is not transferable. Premature withdrawal needs the written consent of the lien holder.")
    c.setFillColor(HexColor("#111111"))
    if qr_url == "auto" and not bank.get("qr_domains"):
        qr_url = None  # this bank prints no QR on its receipts
    if qr_url:
        url = f"http://{banks.HOST}/v/{r['ifsc']}/{r['fdr_no']}" if qr_url == "auto" else qr_url
        c.drawImage(docgen._png(docgen.qr_img(url)), 60, 110, 92, 92)
        c.setFont("Helvetica", 10.5)
        c.drawString(164, 160, f"Verify at: {url}")
    c.drawImage(docgen._png(docgen.signature_img("manager", seed)), W - 260, 140, 150, 46)
    seal = PKI / f"{code}-seal.png"
    if seal.exists():
        from PIL import Image
        c.drawImage(docgen._png(docgen.scan(Image.open(seal).convert("RGBA"), seed)), W - 152, 100, 96, 96)
    c.setFont("Helvetica", 9.5)
    c.drawString(W - 260, 124, "Authorised Signatory")
    c.save()
    if sign:
        docgen.sign_pdf(tmp, path, str(PKI / "XSNB.key"), str(PKI / "XSNB.pem"), str(PKI / "bank-ca.pem"))
        tmp.unlink()
    return path


def phone_scan(pdf_path, jpg_path, seed=3):
    """A photographed paper receipt: slight rotation, shadow, JPEG noise."""
    import fitz
    from PIL import Image, ImageEnhance, ImageFilter
    pix = fitz.open(pdf_path)[0].get_pixmap(dpi=130)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    rnd = random.Random(seed)
    im = im.rotate(rnd.uniform(-1.5, 1.5), expand=True, fillcolor=(236, 233, 226))
    im = ImageEnhance.Brightness(im).enhance(0.96).filter(ImageFilter.GaussianBlur(0.5))
    im.save(jpg_path, "JPEG", quality=82)
    return jpg_path


def record(ifsc, fdr_no, depositor, amount, deposit_date, months, rate=7.1, status="ACTIVE", lien=True, auto_renew=False):
    dep = dt.date.fromisoformat(deposit_date)
    y, m = dep.year + (dep.month - 1 + months) // 12, (dep.month - 1 + months) % 12 + 1
    mat = dt.date(y, m, min(dep.day, 28))
    return {"ifsc": ifsc, "fdr_no": fdr_no, "depositor": depositor, "amount": float(amount), "rate": rate, "months": months,
            "deposit_date": dep.isoformat(), "maturity_date": mat.isoformat(), "status": status, "lien_aicte": lien,
            "auto_renew": auto_renew, "closed_on": None,
            "maturity_value": round(rules.maturity_value(float(amount), rate, months), 2)}


if __name__ == "__main__" and sys.argv[1:] == ["pki"]:
    make_pki()
