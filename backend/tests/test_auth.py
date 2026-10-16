import pytest
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import SurveyorProfile, User

from .conftest import PASSWORD, auth, make_png

pytestmark = pytest.mark.django_db


def test_register_client_and_login_returns_role(api):
    res = api.post(
        "/api/v1/auth/register/client",
        {"email": "New@Client.id", "password": PASSWORD, "phone": "081234567890", "client_type": "caleg", "organization": "Tim A"},
        format="json",
    )
    assert res.status_code == 201, res.data
    assert res.data["email"] == "new@client.id"

    res = api.post("/api/v1/auth/login", {"email": "new@client.id", "password": PASSWORD}, format="json")
    assert res.status_code == 200
    assert res.data["user"]["role"] == "client"
    assert RefreshToken(res.data["refresh"])["role"] == "client"


def test_register_rejects_weak_password_and_duplicate_email(api, client_user):
    res = api.post(
        "/api/v1/auth/register/client",
        {"email": client_user.email, "password": "12345678", "phone": "081234567890", "client_type": "leasing", "organization": "X"},
        format="json",
    )
    assert res.status_code == 400
    assert res.data["error"]["code"] == "validation_error"
    assert "email" in res.data["error"]["details"]


def test_register_surveyor_is_pending_and_stores_only_nik_last4(api):
    res = api.post(
        "/api/v1/auth/register/surveyor",
        {
            "email": "sv@test.id", "password": PASSWORD, "phone": "081234567890", "full_name": "Sv One",
            "nik": "3201234567890123", "city": "Sukabumi", "latitude": -6.92, "longitude": 106.93,
            "id_document": make_png(name="ktp.png"), "selfie": make_png(name="me.png"),
        },
        format="multipart",
    )
    assert res.status_code == 201, res.data
    profile = SurveyorProfile.objects.get(user__email="sv@test.id")
    assert profile.status == SurveyorProfile.Status.PENDING
    assert profile.nik_last4 == "0123"
    assert "ktp" not in profile.id_document.name  # client filename discarded


def test_register_surveyor_rejects_non_image(api):
    from django.core.files.uploadedfile import SimpleUploadedFile

    fake = SimpleUploadedFile("ktp.png", b"not an image", content_type="image/png")
    res = api.post(
        "/api/v1/auth/register/surveyor",
        {
            "email": "sv2@test.id", "password": PASSWORD, "phone": "081234567890", "full_name": "Sv",
            "nik": "3201234567890123", "city": "Bogor", "latitude": -6.6, "longitude": 106.8,
            "id_document": fake, "selfie": make_png(),
        },
        format="multipart",
    )
    assert res.status_code == 400
    assert "id_document" in res.data["error"]["details"]


def test_unverified_surveyor_cannot_see_jobs(admin_user):
    from .conftest import make_surveyor

    user = make_surveyor(admin_user, "pending@test.id", "Bogor", -6.6, 106.8, verified=False)
    res = auth(user).get("/api/v1/jobs/available")
    assert res.status_code == 403
    assert res.data["error"]["code"] == "forbidden"


def test_logout_blacklists_refresh_token(api, client_user):
    login = api.post("/api/v1/auth/login", {"email": client_user.email, "password": PASSWORD}, format="json").data
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {login['access']}")
    assert api.post("/api/v1/auth/logout", {"refresh": login["refresh"]}, format="json").status_code == 204
    res = api.post("/api/v1/auth/refresh", {"refresh": login["refresh"]}, format="json")
    assert res.status_code == 401


def test_kyc_documents_admin_only(client_user, surveyor_jkt, admin_user):
    pk = surveyor_jkt.surveyor_profile.pk
    assert auth(client_user).get(f"/api/v1/admin/surveyors/{pk}/id-document").status_code == 403
    res = auth(admin_user).get(f"/api/v1/admin/surveyors/{pk}/id-document")
    assert res.status_code == 200
    assert res["Cache-Control"] == "private, no-store"


def test_health_is_public(api):
    res = api.get("/api/health")
    assert res.status_code == 200 and res.data["db"] is True
    assert "X-Request-ID" in res
