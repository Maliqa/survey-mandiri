from django.conf import settings
from django.db import models


class Escrow(models.Model):
    """Client money held by the platform until the survey is accepted."""

    class Status(models.TextChoices):
        FUNDED = "funded", "Dana ditahan"
        RELEASED = "released", "Dicairkan ke surveyor"
        REFUNDED = "refunded", "Dikembalikan ke client"

    class Method(models.TextChoices):
        DEMO = "demo", "Demo (tanpa pembayaran)"
        MANUAL_TRANSFER = "manual_transfer", "Transfer manual (diverifikasi admin)"

    request = models.OneToOneField("surveys.SurveyRequest", on_delete=models.PROTECT, related_name="escrow")
    amount = models.PositiveBigIntegerField()
    method = models.CharField(max_length=20, choices=Method.choices)
    reference = models.CharField(max_length=100, blank=True, help_text="Bank/payment reference")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.FUNDED, db_index=True)
    platform_fee = models.PositiveBigIntegerField(default=0)
    funded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    funded_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Escrow #{self.request_id} Rp{self.amount:,} [{self.status}]"


class Payout(models.Model):
    """Amount owed to a surveyor after a request is settled."""

    class Status(models.TextChoices):
        PENDING = "pending", "Menunggu transfer"
        PAID = "paid", "Sudah ditransfer"

    escrow = models.ForeignKey(Escrow, on_delete=models.PROTECT, related_name="payouts")
    surveyor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payouts")
    units = models.PositiveIntegerField()
    gross_amount = models.PositiveBigIntegerField()
    fee_amount = models.PositiveBigIntegerField()
    net_amount = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    transfer_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["escrow", "surveyor"], name="uniq_payout_per_escrow")]
