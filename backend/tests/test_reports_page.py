import pytest
from django.test import Client as BrowserClient

from apps.surveys import reporting
from apps.surveys.models import SurveyRequest

from .conftest import auth, caleg_payload, leasing_payload, report_payload
from .test_survey_flow import create_and_pay

pytestmark = pytest.mark.django_db(transaction=True)


def _request_with_report(client_user, surveyor, payload=None, **report_kw):
    rid = create_and_pay(client_user, payload or leasing_payload())
    s = auth(surveyor)
    aid = s.post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json").data["id"]
    rep = s.post(f"/api/v1/assignments/{aid}/reports", report_payload(**report_kw), format="multipart").data
    return rid, rep


def test_owner_gets_signed_links_others_do_not(client_user, surveyor_jkt):
    from apps.accounts.models import Role, User

    rid, _ = _request_with_report(client_user, surveyor_jkt)
    res = auth(client_user).get(f"/api/v1/requests/{rid}/report-link")
    assert res.status_code == 200
    assert "/laporan/" in res.data["url"] and res.data["pdf_url"].endswith("/pdf")

    other = User.objects.create_user("o@test.id", "Str0ng!Passw0rd", role=Role.CLIENT, phone="081200000009")
    assert auth(other).get(f"/api/v1/requests/{rid}/report-link").status_code == 404
    assert auth(surveyor_jkt).get(f"/api/v1/requests/{rid}/report-link").status_code == 403


def test_report_page_html_shows_flags_and_photo(client_user, surveyor_jkt):
    rid, rep = _request_with_report(client_user, surveyor_jkt, is_mock_location=True)
    sr = SurveyRequest.objects.get(pk=rid)
    token = reporting.make_token(sr)
    browser = BrowserClient()
    page = browser.get(f"/laporan/{token}/")
    assert page.status_code == 200
    html = page.content.decode()
    assert sr.title in html
    assert "Terdeteksi lokasi palsu" in html
    assert f"/laporan/{token}/foto/{rep['id']}" in html
    assert page["X-Robots-Tag"] == "noindex, nofollow"

    photo = browser.get(f"/laporan/{token}/foto/{rep['id']}")
    assert photo.status_code == 200


def test_report_pdf_is_valid_pdf(client_user, surveyor_jkt):
    rid, _ = _request_with_report(client_user, surveyor_jkt)
    token = reporting.make_token(SurveyRequest.objects.get(pk=rid))
    res = BrowserClient().get(f"/laporan/{token}/pdf?download=1")
    assert res.status_code == 200
    assert res["Content-Type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert "attachment" in res["Content-Disposition"]


def test_token_cannot_open_other_requests_photo(client_user, surveyor_jkt):
    rid1, _ = _request_with_report(client_user, surveyor_jkt)
    _, rep2 = _request_with_report(client_user, surveyor_jkt, payload=caleg_payload(quantity=1), color=(9, 9, 9))
    token1 = reporting.make_token(SurveyRequest.objects.get(pk=rid1))
    assert BrowserClient().get(f"/laporan/{token1}/foto/{rep2['id']}").status_code == 404


def test_tampered_and_expired_tokens_rejected(client_user, surveyor_jkt, settings):
    rid, _ = _request_with_report(client_user, surveyor_jkt)
    token = reporting.make_token(SurveyRequest.objects.get(pk=rid))
    browser = BrowserClient()
    assert browser.get(f"/laporan/{token[:-2]}xx/").status_code == 404

    # Pretend the token was issued 4 days ago (default validity is 72 h).
    import time
    from unittest import mock

    with mock.patch("django.core.signing.time.time", return_value=time.time() - 4 * 86400):
        old_token = reporting.make_token(SurveyRequest.objects.get(pk=rid))
    assert browser.get(f"/laporan/{old_token}/").status_code == 404


def test_report_page_without_reports(client_user):
    rid = create_and_pay(client_user, leasing_payload())
    token = reporting.make_token(SurveyRequest.objects.get(pk=rid))
    page = BrowserClient().get(f"/laporan/{token}/")
    assert page.status_code == 200
    assert "Belum ada laporan" in page.content.decode()
    assert BrowserClient().get(f"/laporan/{token}/pdf").content.startswith(b"%PDF")


def test_admin_pages_render_with_thumbnails(client_user, surveyor_jkt, admin_user):
    rid, rep = _request_with_report(client_user, surveyor_jkt, is_mock_location=True)
    browser = BrowserClient()
    browser.force_login(admin_user)
    base = "/admin/"
    lst = browser.get(f"{base}surveys/report/?flagged=yes", secure=True)
    assert lst.status_code == 200
    body = lst.content.decode()
    assert f"/api/v1/reports/{rep['id']}/photo" in body and "Terdeteksi lokasi palsu" in body
    assert browser.get(f"{base}surveys/report/{rep['id']}/change/", secure=True).status_code == 200
    detail = browser.get(f"{base}surveys/surveyrequest/{rid}/change/", secure=True).content.decode()
    assert "/laporan/" in detail
    assert browser.get(f"{base}accounts/surveyorprofile/{surveyor_jkt.surveyor_profile.pk}/change/", secure=True).status_code == 200
    # Session-authenticated admin can load the private photo used by the thumbnails.
    assert browser.get(f"/api/v1/reports/{rep['id']}/photo", secure=True).status_code == 200
