"""Escrow money movements. Every function expects to run inside a transaction
that already holds a row lock on the SurveyRequest."""
import logging
from collections import Counter

from django.utils import timezone

from apps.core.exceptions import BusinessError

from .models import Escrow, Payout

logger = logging.getLogger(__name__)


def fund(survey_request, *, actor, method: str, reference: str = "") -> Escrow:
    if hasattr(survey_request, "escrow"):
        raise BusinessError("Escrow already funded.", code="already_funded")
    escrow = Escrow.objects.create(
        request=survey_request,
        amount=survey_request.total_price,
        method=method,
        reference=reference,
        funded_by=actor,
    )
    logger.info("escrow_funded", extra={"request_id": survey_request.pk, "amount": escrow.amount, "method": method})
    return escrow


def refund(survey_request) -> Escrow | None:
    escrow = getattr(survey_request, "escrow", None)
    if escrow is None:
        return None
    if escrow.status != Escrow.Status.FUNDED:
        raise BusinessError("Escrow is not refundable.", code="escrow_closed")
    escrow.status = Escrow.Status.REFUNDED
    escrow.closed_at = timezone.now()
    escrow.save(update_fields=["status", "closed_at"])
    logger.info("escrow_refunded", extra={"request_id": survey_request.pk, "amount": escrow.amount})
    return escrow


def release(survey_request, approved_units_by_surveyor: Counter) -> list[Payout]:
    """Split escrow into per-surveyor payouts minus platform commission."""
    escrow = survey_request.escrow
    if escrow.status != Escrow.Status.FUNDED:
        raise BusinessError("Escrow is not in funded state.", code="escrow_closed")

    payouts, total_fee, total_gross = [], 0, 0
    for surveyor_id, units in approved_units_by_surveyor.items():
        gross = units * survey_request.unit_price
        fee = gross * survey_request.commission_percent // 100
        payouts.append(
            Payout(
                escrow=escrow, surveyor_id=surveyor_id, units=units,
                gross_amount=gross, fee_amount=fee, net_amount=gross - fee,
            )
        )
        total_fee += fee
        total_gross += gross

    if total_gross != escrow.amount:
        # Completion requires every unit approved, so this indicates a bug: fail loudly.
        raise BusinessError("Payouts do not match escrow amount.", code="escrow_mismatch", http_status=500)

    Payout.objects.bulk_create(payouts)
    escrow.status = Escrow.Status.RELEASED
    escrow.platform_fee = total_fee
    escrow.closed_at = timezone.now()
    escrow.save(update_fields=["status", "platform_fee", "closed_at"])
    logger.info(
        "escrow_released",
        extra={"request_id": survey_request.pk, "payouts": len(payouts), "platform_fee": escrow.platform_fee},
    )
    return payouts
