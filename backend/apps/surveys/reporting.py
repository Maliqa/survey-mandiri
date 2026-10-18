"""Shareable survey report: signed links, HTML context and PDF rendering.

Access model: a report page is opened through a signed, expiring token
(``/laporan/<token>/``). The token is issued only to the request's owner (API)
or to staff (admin), so the page can be opened in any browser, forwarded to a
credit committee, or printed, without exposing the private photo endpoints.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import timedelta
from xml.sax.saxutils import escape

from django.conf import settings
from django.core import signing
from django.urls import reverse
from django.utils import timezone

from apps.core.geo import haversine_km

from .models import Report, SurveyRequest

SALT = "survey-report-page"
MAX_PDF_PHOTOS = 200


def link_ttl() -> timedelta:
    return timedelta(hours=settings.REPORT_LINK_HOURS)


def make_token(sr: SurveyRequest) -> str:
    return signing.dumps({"r": str(sr.public_id)}, salt=SALT, compress=True)


def load_request(token: str) -> SurveyRequest:
    """Raises signing.BadSignature / SignatureExpired / SurveyRequest.DoesNotExist."""
    data = signing.loads(token, salt=SALT, max_age=link_ttl())
    return SurveyRequest.objects.select_related("client", "escrow").get(public_id=data["r"])


def report_urls(sr: SurveyRequest, request=None) -> dict:
    token = make_token(sr)
    page = reverse("report-page", kwargs={"token": token})
    pdf = reverse("report-pdf", kwargs={"token": token})
    build = request.build_absolute_uri if request is not None else (lambda p: p)
    return {
        "url": build(page),
        "pdf_url": build(pdf),
        "expires_at": (timezone.now() + link_ttl()).isoformat(),
    }


@dataclass
class ReportRow:
    report: Report
    distance_m: int | None
    maps_url: str
    answers: list[tuple[str, str]]
    flag_labels: list[str]


FLAG_LABELS = dict(Report.Flag.choices)

DETAIL_VALUE_LABELS = {
    "credit_worthiness": "Kelayakan kredit",
    "business_location": "Lokasi usaha",
    "customer_verification": "Verifikasi nasabah",
    "new": "Produk baru",
    "used": "Produk bekas",
    "market_research": "Riset pasar",
    "feedback": "Feedback konsumen",
}


def display_cities(sr: SurveyRequest) -> str:
    return ", ".join(c.title() for c in (sr.target_cities or []))


def _rows(sr: SurveyRequest) -> list[ReportRow]:
    rows = []
    qs = sr.reports.select_related("surveyor__surveyor_profile").order_by("captured_at")
    for r in qs:
        distance = None
        if sr.latitude is not None and sr.longitude is not None:
            distance = round(haversine_km(sr.latitude, sr.longitude, r.latitude, r.longitude) * 1000)
        answers = [(str(k), str(v)) for k, v in (r.answers or {}).items()] if isinstance(r.answers, dict) else []
        rows.append(
            ReportRow(
                report=r,
                distance_m=distance,
                maps_url=f"https://www.google.com/maps?q={r.latitude:.6f},{r.longitude:.6f}",
                answers=answers,
                flag_labels=[FLAG_LABELS.get(f, f) for f in (r.flags or [])],
            )
        )
    return rows


def build_context(sr: SurveyRequest, token: str) -> dict:
    rows = _rows(sr)
    live = [row for row in rows if row.report.status != Report.Status.REJECTED]
    details = sr.details if isinstance(sr.details, dict) else {}
    detail_items = [
        (label, DETAIL_VALUE_LABELS.get(str(details[key]), details[key]))
        for key, label in [
            ("purpose", "Tujuan"),
            ("applicant_ref", "No. referensi aplikasi"),
            ("electoral_district", "Dapil"),
            ("target_demographic", "Target responden"),
            ("product_name", "Produk"),
            ("condition", "Kondisi produk"),
            ("research_type", "Jenis riset"),
        ]
        if details.get(key)
    ]
    points = [
        {"lat": row.report.latitude, "lon": row.report.longitude, "label": row.report.respondent_label or f"#{row.report.pk}",
         "flagged": bool(row.report.flags)}
        for row in live
    ]
    return {
        "sr": sr,
        "token": token,
        "organization": sr.client.organization or sr.client.email,
        "rows": rows,
        "live_count": len(live),
        "flagged_count": sum(1 for row in live if row.report.flags),
        "rejected_count": len(rows) - len(live),
        "surveyors": sorted({row.report.surveyor.surveyor_profile.full_name for row in live}),
        "detail_items": detail_items,
        "questions": details.get("questions") or [],
        "points": points,
        "target": {"lat": sr.latitude, "lon": sr.longitude} if sr.latitude is not None else None,
        "cities": display_cities(sr),
        "generated_at": timezone.localtime(),
        "expires_hours": settings.REPORT_LINK_HOURS,
        "pdf_url": reverse("report-pdf", kwargs={"token": token}) if token else "",
    }


# ---- PDF -------------------------------------------------------------------------------------

def _photo_flowable(report: Report, max_w: float, max_h: float):
    from PIL import Image as PILImage
    from reportlab.platypus import Image

    try:
        with report.photo.open("rb") as fh, PILImage.open(fh) as img:
            img = img.convert("RGB")
            img.thumbnail((900, 900))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=72)
            w, h = img.size
    except (OSError, ValueError):
        return None
    scale = min(max_w / w, max_h / h)
    buf.seek(0)
    return Image(buf, width=w * scale, height=h * scale)


def render_pdf(sr: SurveyRequest) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ctx = build_context(sr, token="")
    brand = colors.HexColor("#0B6E4F")
    red = colors.HexColor("#C5221F")
    muted = colors.HexColor("#5B6560")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=17, textColor=brand, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8.5, textColor=muted, leading=11)
    right = ParagraphStyle("right", parent=small, alignment=TA_RIGHT)
    flag = ParagraphStyle("flag", parent=body, textColor=red, fontName="Helvetica-Bold")

    def p(text, style=body):
        return Paragraph(escape(str(text)), style)

    def kv_table(items, col=(48 * mm, 122 * mm)):
        t = Table([[p(k, small), p(v)] for k, v in items], colWidths=col)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#E3E8E5")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    story = []
    header = Table(
        [[Paragraph("<b>SURVEY MANDIRI</b>", ParagraphStyle("b", parent=body, textColor=brand, fontSize=11)),
          p(f"Laporan Survei #{sr.pk} • {str(sr.public_id)[:8].upper()}", right)]],
        colWidths=(85 * mm, 85 * mm),
    )
    story += [header, Spacer(1, 4 * mm), Paragraph(escape(sr.title), h1),
              p(f"{sr.get_category_display()} • {ctx['organization']} • Status: {sr.get_status_display()}", small),
              Spacer(1, 4 * mm)]

    summary = [
        ("Laporan diterima", f"{ctx['live_count']} dari {sr.quantity} unit"),
        ("Ditandai mencurigakan", str(ctx["flagged_count"])),
        ("Surveyor", ", ".join(ctx["surveyors"]) or "-"),
        ("Kota target", display_cities(sr)),
        ("Deadline", sr.deadline.strftime("%d-%m-%Y")),
    ]
    if sr.address:
        summary.append(("Alamat target", sr.address))
    if sr.latitude is not None:
        summary.append(("Titik target", f"{sr.latitude:.6f}, {sr.longitude:.6f}"))
    summary += [(label, value) for label, value in ctx["detail_items"]]
    story += [Paragraph("Ringkasan", h2), kv_table(summary)]
    if sr.description:
        story += [Spacer(1, 2 * mm), p(sr.description, small)]

    story.append(Paragraph("Hasil per unit", h2))
    if not ctx["rows"]:
        story.append(p("Belum ada laporan.", small))

    for i, row in enumerate(ctx["rows"], start=1):
        r = row.report
        info = [
            ("Surveyor", r.surveyor.surveyor_profile.full_name),
            ("Waktu foto", timezone.localtime(r.captured_at).strftime("%d-%m-%Y %H:%M")),
            ("Lokasi GPS", f"{r.latitude:.6f}, {r.longitude:.6f} (±{r.gps_accuracy_m:.0f} m)"),
        ]
        if row.distance_m is not None:
            info.append(("Jarak ke titik target", f"{row.distance_m:,} m".replace(",", ".")))
        if r.city:
            info.append(("Kota", r.city))
        info.append(("Status", r.get_status_display()))
        info += [(q, a) for q, a in row.answers]
        if r.notes:
            info.append(("Catatan", r.notes))
        if r.rejection_reason:
            info.append(("Alasan ditolak", r.rejection_reason))

        block = [Paragraph(f"Unit {i}: {escape(r.respondent_label or f'Laporan #{r.pk}')}", h2)]
        if row.flag_labels:
            block.append(Paragraph("[!] " + escape(" • ".join(row.flag_labels)), flag))
        photo = _photo_flowable(r, 70 * mm, 80 * mm) if i <= MAX_PDF_PHOTOS else None
        details_tbl = kv_table(info, col=(32 * mm, 66 * mm))
        if photo is not None:
            grid = Table([[photo, details_tbl]], colWidths=(72 * mm, 98 * mm))
            grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            block.append(grid)
        else:
            block.append(details_tbl)
        block.append(Paragraph(f'<link href="{row.maps_url}" color="#1967D2">Buka lokasi di Google Maps</link>', small))
        story.append(KeepTogether(block))

    if len(ctx["rows"]) > MAX_PDF_PHOTOS:
        story.append(p(f"Foto hanya dilampirkan untuk {MAX_PDF_PHOTOS} unit pertama. Lihat versi web untuk semua foto.", small))

    story += [
        Spacer(1, 6 * mm),
        p("Foto diambil langsung dari kamera aplikasi (bukan galeri). Lokasi GPS, waktu pengambilan, deteksi GPS palsu, "
          "dan foto duplikat diperiksa otomatis oleh sistem.", small),
        p(f"Dibuat {ctx['generated_at'].strftime('%d-%m-%Y %H:%M')} WIB oleh Survey Mandiri.", small),
    ]

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(muted)
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Halaman {doc.page}")
        canvas.drawString(20 * mm, 10 * mm, f"Survey Mandiri • Laporan #{sr.pk}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"Laporan Survei #{sr.pk} - {sr.title}", author="Survey Mandiri",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
