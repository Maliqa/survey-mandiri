from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

from apps.core.files import random_upload_path
from apps.core.geo import normalize_city

phone_validator = RegexValidator(r"^\+?62\d{8,13}$|^0\d{9,13}$", "Use an Indonesian phone number.")


class Role(models.TextChoices):
    CLIENT = "client", "Client"
    SURVEYOR = "surveyor", "Surveyor"
    ADMIN = "admin", "Admin"


class ClientType(models.TextChoices):
    LEASING = "leasing", "Leasing"
    CALEG = "caleg", "Caleg"
    PRODUCT = "product", "Produk"
    OTHER = "other", "Lainnya"


class EmailUserManager(UserManager):
    """Email is the login identifier; username is kept equal to it for Django admin."""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        extra_fields.pop("username", None)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.update(is_staff=True, is_superuser=True, role=Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, validators=[phone_validator])
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CLIENT, db_index=True)
    # Only meaningful for clients.
    client_type = models.CharField(max_length=16, choices=ClientType.choices, blank=True)
    organization = models.CharField(max_length=150, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = EmailUserManager()

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        self.username = self.email
        super().save(*args, **kwargs)

    @property
    def is_verified_surveyor(self) -> bool:
        return (
            self.role == Role.SURVEYOR
            and hasattr(self, "surveyor_profile")
            and self.surveyor_profile.status == SurveyorProfile.Status.VERIFIED
        )


class SurveyorProfile(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu verifikasi"
        VERIFIED = "verified", "Terverifikasi"
        REJECTED = "rejected", "Ditolak"
        SUSPENDED = "suspended", "Ditangguhkan"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="surveyor_profile")
    full_name = models.CharField(max_length=150)
    # Store only the last 4 digits; the full NIK lives on the ID photo (private storage).
    nik_last4 = models.CharField(max_length=4, validators=[RegexValidator(r"^\d{4}$")])
    id_document = models.ImageField(upload_to=random_upload_path("private/id_docs"))
    selfie = models.ImageField(upload_to=random_upload_path("private/selfies"))

    city = models.CharField(max_length=100, help_text="Domicile city/regency")
    city_normalized = models.CharField(max_length=100, db_index=True, editable=False)
    service_cities = models.JSONField(default=list, blank=True, help_text="Extra normalized cities served")
    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    service_radius_km = models.PositiveIntegerField(default=25, validators=[MaxValueValidator(300)])

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="verified_surveyors"
    )

    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    completed_units = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.city_normalized = normalize_city(self.city)
        self.service_cities = sorted({normalize_city(c) for c in self.service_cities if c})
        super().save(*args, **kwargs)

    def served_cities(self) -> set[str]:
        return {self.city_normalized, *self.service_cities}

    def verify(self, admin_user: User) -> None:
        self.status = self.Status.VERIFIED
        self.rejection_reason = ""
        self.verified_at = timezone.now()
        self.verified_by = admin_user
        self.save(update_fields=["status", "rejection_reason", "verified_at", "verified_by"])

    def reject(self, admin_user: User, reason: str) -> None:
        self.status = self.Status.REJECTED
        self.rejection_reason = reason[:255]
        self.verified_by = admin_user
        self.save(update_fields=["status", "rejection_reason", "verified_by"])

    def __str__(self) -> str:
        return f"{self.full_name} ({self.get_status_display()})"
