import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.files import random_upload_path


class Category(models.TextChoices):
    LEASING = "leasing", "Leasing"
    CALEG = "caleg", "Caleg"
    PRODUCT = "product", "Produk"


class PricingRate(models.Model):
    """Platform-set price per survey unit (one visit / one respondent)."""

    category = models.CharField(max_length=16, choices=Category.choices, unique=True)
    unit_label = models.CharField(max_length=50, default="unit", help_text="e.g. responden, kunjungan")
    unit_price = models.PositiveIntegerField(help_text="IDR per unit, paid by client")
    min_units = models.PositiveIntegerField(default=1)
    max_units = models.PositiveIntegerField(default=10_000)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.get_category_display()}: Rp{self.unit_price:,}/{self.unit_label}"


class SurveyRequest(models.Model):
    class Status(models.TextChoices):
        QUOTED = "quoted", "Penawaran harga"
        AWAITING_PAYMENT = "awaiting_payment", "Menunggu pembayaran"
        OPEN = "open", "Di-broadcast"
        ASSIGNED = "assigned", "Semua unit diambil"
        IN_REVIEW = "in_review", "Menunggu review client"
        COMPLETED = "completed", "Selesai"
        CANCELLED = "cancelled", "Dibatalkan"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="survey_requests")
    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=150)
    description = models.TextField(max_length=4000)
    # Category-specific structured fields (validated by serializer per category).
    details = models.JSONField(default=dict, blank=True)

    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    target_cities = models.JSONField(default=list, help_text="Normalized city names")
    address = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    deadline = models.DateField()

    # Price snapshot at quote time, so later rate changes never affect this deal.
    unit_price = models.PositiveIntegerField()
    total_price = models.PositiveBigIntegerField()
    commission_percent = models.PositiveSmallIntegerField(validators=[MaxValueValidator(90)])

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUOTED, db_index=True)
    claimed_units = models.PositiveIntegerField(default=0)
    broadcast_at = models.DateTimeField(null=True, blank=True)
    review_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(claimed_units__lte=models.F("quantity")), name="claimed_lte_quantity"),
        ]

    @property
    def remaining_units(self) -> int:
        return self.quantity - self.claimed_units

    @property
    def surveyor_unit_earning(self) -> int:
        return self.unit_price - (self.unit_price * self.commission_percent // 100)

    def __str__(self) -> str:
        return f"#{self.pk} {self.title} [{self.status}]"


class JobOffer(models.Model):
    """A broadcast of a request to one matching verified surveyor."""

    request = models.ForeignKey(SurveyRequest, on_delete=models.CASCADE, related_name="offers")
    surveyor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_offers")
    distance_km = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["request", "surveyor"], name="uniq_offer")]


class Assignment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Aktif"
        WITHDRAWN = "withdrawn", "Mundur"
        DONE = "done", "Selesai"

    request = models.ForeignKey(SurveyRequest, on_delete=models.CASCADE, related_name="assignments")
    surveyor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assignments")
    units = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    accepted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accepted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "surveyor"],
                condition=~Q(status="withdrawn"),
                name="uniq_live_assignment",
            )
        ]


class Report(models.Model):
    """One completed survey unit, with anti-fraud evidence."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Dikirim"
        APPROVED = "approved", "Disetujui"
        REJECTED = "rejected", "Ditolak"

    class Flag(models.TextChoices):
        FAR_FROM_TARGET = "far_from_target", "Lokasi jauh dari titik target"
        DUPLICATE_PHOTO = "duplicate_photo", "Foto sudah pernah dipakai"
        MOCK_LOCATION = "mock_location", "Terdeteksi lokasi palsu (mock GPS)"
        LOW_GPS_ACCURACY = "low_gps_accuracy", "Akurasi GPS rendah"
        OUTSIDE_TARGET_CITY = "outside_target_city", "Di luar kota target"

    # Generated on the device: makes offline retries idempotent.
    client_uuid = models.UUIDField(unique=True)
    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name="reports")
    request = models.ForeignKey(SurveyRequest, on_delete=models.PROTECT, related_name="reports")
    surveyor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports")

    respondent_label = models.CharField(max_length=100, blank=True, help_text="Non-identifying label")
    answers = models.JSONField(default=dict, blank=True)
    notes = models.TextField(max_length=2000, blank=True)
    photo = models.ImageField(upload_to=random_upload_path("private/reports"))
    photo_sha256 = models.CharField(max_length=64, db_index=True)

    latitude = models.FloatField(validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.FloatField(validators=[MinValueValidator(-180), MaxValueValidator(180)])
    gps_accuracy_m = models.FloatField(validators=[MinValueValidator(0)])
    city = models.CharField(max_length=100, blank=True)
    captured_at = models.DateTimeField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    flags = models.JSONField(default=list, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [models.Index(fields=["request", "status"])]
