"""Browser-facing report pages, authorised by a signed link (no login needed)."""
import logging

from django.core import signing
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from . import reporting
from .models import Report, SurveyRequest

logger = logging.getLogger(__name__)


def _request_or_404(token: str) -> SurveyRequest:
    try:
        return reporting.load_request(token)
    except signing.SignatureExpired:
        raise Http404("Link laporan sudah kedaluwarsa. Minta link baru dari aplikasi.")
    except (signing.BadSignature, SurveyRequest.DoesNotExist, KeyError):
        raise Http404("Link laporan tidak valid.")


def _private(response):
    response["Cache-Control"] = "private, max-age=300"
    response["X-Robots-Tag"] = "noindex, nofollow"
    response["Referrer-Policy"] = "no-referrer"  # don't leak the token to map tiles / Google Maps
    return response


@require_GET
def report_page(request, token: str):
    sr = _request_or_404(token)
    return _private(render(request, "surveys/report_page.html", reporting.build_context(sr, token)))


@require_GET
def report_pdf(request, token: str):
    sr = _request_or_404(token)
    pdf = reporting.render_pdf(sr)
    logger.info("report_pdf_generated", extra={"request_id": sr.pk, "bytes": len(pdf)})
    response = HttpResponse(pdf, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") == "1" else "inline"
    response["Content-Disposition"] = f'{disposition}; filename="laporan-survei-{sr.pk}.pdf"'
    return _private(response)


@require_GET
def report_photo(request, token: str, report_id: int):
    sr = _request_or_404(token)
    report = get_object_or_404(Report, pk=report_id, request=sr)
    return _private(FileResponse(report.photo.open("rb")))
