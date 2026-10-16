"""Create demo accounts so customers can try the app immediately.

    python manage.py seed_demo --password 'DemoPass#2026'

Idempotent: existing accounts are left untouched.
"""
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from PIL import Image

from apps.accounts.models import ClientType, Role, SurveyorProfile, User

SURVEYORS = [
    # email, name, city, lat, lon
    ("surveyor.jakarta@demo.surveymandiri.id", "Budi Santoso", "Jakarta Selatan", -6.2615, 106.8106),
    ("surveyor.bandung@demo.surveymandiri.id", "Siti Rahma", "Bandung", -6.9175, 107.6191),
    ("surveyor.sukabumi@demo.surveymandiri.id", "Asep Hidayat", "Sukabumi", -6.9277, 106.9300),
]
CLIENTS = [
    ("leasing@demo.surveymandiri.id", ClientType.LEASING, "PT Demo Finance"),
    ("caleg@demo.surveymandiri.id", ClientType.CALEG, "Tim Pemenangan Demo"),
    ("produk@demo.surveymandiri.id", ClientType.PRODUCT, "Demo Brand Indonesia"),
]


def _placeholder_png(color: str) -> ContentFile:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "PNG")
    return ContentFile(buf.getvalue(), name="placeholder.png")


class Command(BaseCommand):
    help = "Seed demo admin, client and verified surveyor accounts."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for all demo accounts")
        parser.add_argument("--admin-email", default="admin@demo.surveymandiri.id")

    @transaction.atomic
    def handle(self, *args, password: str, admin_email: str, **opts):
        admin, created = User.objects.get_or_create(
            email=admin_email, defaults={"username": admin_email, "role": Role.ADMIN, "is_staff": True, "is_superuser": True, "phone": "081200000000"}
        )
        if created:
            admin.set_password(password)
            admin.save()
        self.stdout.write(f"admin    {admin.email} ({'created' if created else 'exists'})")

        for email, ctype, org in CLIENTS:
            user, created = User.objects.get_or_create(
                email=email, defaults={"username": email, "role": Role.CLIENT, "client_type": ctype, "organization": org, "phone": "081211111111"}
            )
            if created:
                user.set_password(password)
                user.save()
            self.stdout.write(f"client   {email} ({'created' if created else 'exists'})")

        for i, (email, name, city, lat, lon) in enumerate(SURVEYORS):
            user, created = User.objects.get_or_create(
                email=email, defaults={"username": email, "role": Role.SURVEYOR, "phone": f"08130000000{i}"}
            )
            if created:
                user.set_password(password)
                user.save()
                profile = SurveyorProfile(
                    user=user, full_name=name, nik_last4=f"{1000 + i}", city=city,
                    latitude=lat, longitude=lon, service_radius_km=50,
                )
                profile.id_document.save("id.png", _placeholder_png("gray"), save=False)
                profile.selfie.save("selfie.png", _placeholder_png("silver"), save=False)
                profile.save()
                profile.verify(admin)
            self.stdout.write(f"surveyor {email} ({'created' if created else 'exists'})")
