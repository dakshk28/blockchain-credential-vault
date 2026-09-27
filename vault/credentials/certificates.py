"""Generate a branded certificate PDF with an embedded verification QR code.

reportlab's invariant mode makes the output deterministic for the same inputs, so the recorded
SHA-256 can be reproduced from the same data.
"""
from io import BytesIO
from pathlib import Path

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

DEFAULT_ACCENT = "#3b5bdb"


def _fit(c, text, font, size, max_width, minimum=10):
    while size > minimum and c.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def render_certificate(*, institution, recipient, title, programme, issue_date, credential_id, verify_url, expiry_date=None, logo_path: Path | None = None):
    buffer = BytesIO()
    width, height = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=(width, height), invariant=1)
    c.setTitle(f"{title} — {recipient}"); c.setAuthor(institution.name); c.setSubject(f"Credential {credential_id}")
    accent = colors.HexColor(institution.accent_color or DEFAULT_ACCENT)
    gold = colors.HexColor("#c99a2e")

    # Frame
    c.setFillColor(colors.HexColor("#fbfaf6")); c.rect(0, 0, width, height, stroke=0, fill=1)
    c.setStrokeColor(accent); c.setLineWidth(6); c.rect(22, 22, width - 44, height - 44)
    c.setStrokeColor(gold); c.setLineWidth(1.2); c.rect(34, 34, width - 68, height - 68)

    # Header: logo and institution
    top = height - 90
    if logo_path and logo_path.exists():
        c.drawImage(ImageReader(str(logo_path)), width / 2 - 30, top - 20, 60, 60, preserveAspectRatio=True, mask="auto")
        top -= 60
    c.setFillColor(accent); c.setFont("Helvetica-Bold", _fit(c, institution.name.upper(), "Helvetica-Bold", 20, width - 160))
    c.drawCentredString(width / 2, top - 10, institution.name.upper())

    c.setFillColor(colors.HexColor("#1f2937")); c.setFont("Times-Italic", 16)
    c.drawCentredString(width / 2, top - 55, "This is to certify that")
    c.setFont("Times-Bold", _fit(c, recipient, "Times-Bold", 36, width - 160))
    c.drawCentredString(width / 2, top - 100, recipient)
    c.setStrokeColor(gold); c.setLineWidth(1); c.line(width / 2 - 180, top - 110, width / 2 + 180, top - 110)
    c.setFont("Times-Italic", 16); c.drawCentredString(width / 2, top - 140, "has been awarded the")
    c.setFillColor(accent); c.setFont("Helvetica-Bold", _fit(c, title, "Helvetica-Bold", 26, width - 160))
    c.drawCentredString(width / 2, top - 175, title)
    c.setFillColor(colors.HexColor("#374151")); c.setFont("Helvetica", _fit(c, programme, "Helvetica", 15, width - 160))
    c.drawCentredString(width / 2, top - 200, programme)

    # Signatory and digital-seal note
    c.setStrokeColor(colors.HexColor("#9ca3af")); c.setLineWidth(.8); c.line(width / 2 - 110, 190, width / 2 + 110, 190)
    c.setFillColor(colors.HexColor("#4b5563")); c.setFont("Helvetica", 10); c.drawCentredString(width / 2, 176, "Authorised signatory")
    c.setFont("Helvetica-Oblique", 8.5); c.setFillColor(accent)
    c.drawCentredString(width / 2, 150, "Digitally signed (Ed25519) and fingerprinted (SHA-256) by the Academic Credential Vault")

    # Footer: dates, ID, QR
    c.setFont("Helvetica", 10); c.setFillColor(colors.HexColor("#4b5563"))
    c.drawString(70, 95, f"Date of issue: {issue_date:%d %B %Y}")
    if expiry_date:
        c.drawString(70, 80, f"Valid until: {expiry_date:%d %B %Y}")
    c.setFont("Courier-Bold", 11); c.drawString(70, 62, f"Credential ID: {credential_id}")
    c.setFont("Helvetica", 8); c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(70, 48, "Scan the QR code or visit the verification page to confirm authenticity and status.")

    qr = qrcode.QRCode(border=1, box_size=6); qr.add_data(verify_url); qr.make(fit=True)
    image = BytesIO(); qr.make_image().save(image, "PNG"); image.seek(0)
    c.drawImage(ImageReader(image), width - 170, 45, 100, 100)
    c.setFont("Helvetica", 7); c.drawCentredString(width - 120, 38, "Verify this credential")

    c.showPage(); c.save()
    return buffer.getvalue()
