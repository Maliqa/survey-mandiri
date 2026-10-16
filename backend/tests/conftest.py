import io
import uuid
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import ClientType, Role, SurveyorProfile, User

PASSWORD = "Str0ng!Passw0rd"


def make_png(color=(10, 120, 60), name="photo.png") -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@pytest.fixture
def api():
    return APIClient()


def auth(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin@test.id", PASSWORD)


@pytest.fixture
def client_user(db):
    return User.objects.create_user(
        "client@test.id", PASSWORD, role=Role.CLIENT, client_type=ClientType.LEASING, organization="PT Leasing", phone="081234567890"
    )


def make_surveyor(admin, email, city, lat, lon, verified=True) -> User:
    user = User.objects.create_user(email, PASSWORD, role=Role.SURVEYOR, phone="081298765432")
    profile = SurveyorProfile(user=user, full_name=email.split("@")[0], nik_last4="1234", city=city, latitude=lat, longitude=lon)
    profile.id_document = make_png(name="id.png")
    profile.selfie = make_png(name="selfie.png")
    profile.save()
    if verified:
        profile.verify(admin)
    return user


@pytest.fixture
def surveyor_jkt(admin_user):
    return make_surveyor(admin_user, "jkt@test.id", "Jakarta Selatan", -6.2615, 106.8106)


@pytest.fixture
def surveyor_jkt2(admin_user):
    return make_surveyor(admin_user, "jkt2@test.id", "Kota Jakarta Selatan", -6.27, 106.82)


@pytest.fixture
def surveyor_bdg(admin_user):
    return make_surveyor(admin_user, "bdg@test.id", "Bandung", -6.9175, 107.6191)


def leasing_payload(**overrides):
    payload = {
        "category": "leasing",
        "title": "Survey kelayakan kredit motor",
        "description": "Cek rumah dan usaha pemohon.",
        "details": {"purpose": "credit_worthiness", "applicant_ref": "APP-001"},
        "quantity": 1,
        "target_cities": ["Jakarta Selatan"],
        "address": "Jl. Kemang Raya 10",
        "latitude": -6.2600,
        "longitude": 106.8130,
        "deadline": str(timezone.localdate() + timedelta(days=7)),
    }
    payload.update(overrides)
    return payload


def caleg_payload(quantity=3, **overrides):
    payload = {
        "category": "caleg",
        "title": "Survey elektabilitas Dapil 1",
        "description": "Survei door-to-door.",
        "details": {"electoral_district": "DKI 1", "questions": ["Pilihan Anda?"]},
        "quantity": quantity,
        "target_cities": ["Jakarta Selatan"],
        "deadline": str(timezone.localdate() + timedelta(days=14)),
    }
    payload.update(overrides)
    return payload


def report_payload(lat=-6.2601, lon=106.8131, color=(10, 120, 60), **overrides):
    payload = {
        "client_uuid": str(uuid.uuid4()),
        "respondent_label": "R-1",
        "answers": '{"q1": "A"}',
        "notes": "Rumah sesuai alamat",
        "photo": make_png(color),
        "latitude": lat,
        "longitude": lon,
        "gps_accuracy_m": 8.5,
        "city": "Jakarta Selatan",
        "captured_at": (timezone.now() - timedelta(minutes=10)).isoformat(),
        "is_mock_location": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def pricing(db):
    """Transactional tests flush the seeded rates, so (re)create them here.

    Caleg min is lowered to 1 so tests can use tiny quantities.
    """
    from apps.surveys.models import PricingRate

    for category, label, price, min_u in [("leasing", "kunjungan", 150_000, 1), ("caleg", "responden", 50_000, 1), ("product", "responden", 40_000, 1)]:
        PricingRate.objects.update_or_create(
            category=category, defaults={"unit_label": label, "unit_price": price, "min_units": min_u, "is_active": True}
        )
