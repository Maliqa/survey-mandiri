"""Survey request lifecycle (the business core).

QUOTED -> AWAITING_PAYMENT -> OPEN <-> ASSIGNED -> IN_REVIEW -> COMPLETED
   \\------------- \\------------ \\--> CANCELLED (only while nothing is claimed)

Every state change locks the SurveyRequest row (select_for_update) so two
surveyors accepting at the same moment can never over-claim units.
"""
import logging
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import SurveyorProfile
from apps.core.exceptions import BusinessError
from apps.core.geo import haversine_km, normalize_city
from apps.payments import services as escrow_service

from .models import Assignment, JobOffer, PricingRate, Report, SurveyRequest

logger = logging.getLogger(__name__)
S = SurveyRequest.Status

CLOCK_SKEW = timedelta(minutes=5)
LOW_ACCURACY_M = 100


def _biz() -> dict:
    return settings.BUSINESS


def _locked(request_id: int) -> SurveyRequest:
    return SurveyRequest.objects.select_for_update().get(pk=request_id)


def _require(sr: SurveyRequest, *allowed: str) -> None:
    if sr.status not in allowed:
        raise BusinessError(
            f"Not allowed while request is '{sr.status}'.", code="invalid_state"
        )


# --- Pricing -------------------------------------------------------------------
def get_rate(category: str) -> PricingRate:
    rate = PricingRate.objects.filter(category=category, is_active=True).first()
    if rate is None:
        raise BusinessError("No active pricing for this category.", code="pricing_unavailable", http_status=422)
    return rate


def quote(category: str, quantity: int) -> dict:
    rate = get_rate(category)
    if not rate.min_units <= quantity <= rate.max_units:
        raise BusinessError(
            f"Quantity must be between {rate.min_units} and {rate.max_units}.",
            code="quantity_out_of_range",
            http_status=422,
        )
    return {
        "category": category,
        "quantity": quantity,
        "unit_label": rate.unit_label,
        "unit_price": rate.unit_price,
        "total_price": rate.unit_price * quantity,
    }


# --- Client actions --------------------------------------------------------------
@transaction.atomic
def create_request(client, data: dict) -> SurveyRequest:
    q = quote(data["category"], data["quantity"])
    sr = SurveyRequest.objects.create(
        client=client,
        unit_price=q["unit_price"],
        total_price=q["total_price"],
        commission_percent=_biz()["COMMISSION_PERCENT"],
        target_cities=sorted({normalize_city(c) for c in data.pop("target_cities")}),
        **data,
    )
    logger.info("request_created", extra={"request_id": sr.pk, "client_id": client.pk, "total": sr.total_price})
    return sr


@transaction.atomic
def approve_quote(request_id: int) -> SurveyRequest:
    sr = _locked(request_id)
    _require(sr, S.QUOTED)
    sr.status = S.AWAITING_PAYMENT
    sr.save(update_fields=["status", "updated_at"])
    return sr


@transaction.atomic
def fund_and_broadcast(request_id: int, *, actor, method: str, reference: str = "") -> SurveyRequest:
    sr = _locked(request_id)
    _require(sr, S.AWAITING_PAYMENT)
    escrow_service.fund(sr, actor=actor, method=method, reference=reference)
    sr.status = S.OPEN
    sr.broadcast_at = timezone.now()
    sr.save(update_fields=["status", "broadcast_at", "updated_at"])

    from .tasks import broadcast_request  # local import: avoid circular import

    transaction.on_commit(lambda: broadcast_request.delay(sr.pk))
    return sr


@transaction.atomic
def cancel_request(request_id: int) -> SurveyRequest:
    sr = _locked(request_id)
    _require(sr, S.QUOTED, S.AWAITING_PAYMENT, S.OPEN)
    if sr.claimed_units > 0:
        raise BusinessError("Cannot cancel: surveyors already took this job.", code="already_claimed")
    escrow_service.refund(sr)
    sr.status = S.CANCELLED
    sr.cancelled_at = timezone.now()
    sr.save(update_fields=["status", "cancelled_at", "updated_at"])
    logger.info("request_cancelled", extra={"request_id": sr.pk})
    return sr


@transaction.atomic
def reject_report(report_id: int, *, reason: str) -> Report:
    report = Report.objects.select_related("request").get(pk=report_id)
    sr = _locked(report.request_id)
    _require(sr, S.OPEN, S.ASSIGNED, S.IN_REVIEW)
    if report.status != Report.Status.SUBMITTED:
        raise BusinessError("Only submitted reports can be rejected.", code="invalid_state")
    report.status = Report.Status.REJECTED
    report.rejection_reason = reason[:255]
    report.save(update_fields=["status", "rejection_reason"])
    if sr.status == S.IN_REVIEW:
        # A unit is open again; the surveyor must redo it.
        sr.status = S.ASSIGNED
        sr.review_started_at = None
        sr.save(update_fields=["status", "review_started_at", "updated_at"])
    logger.info("report_rejected", extra={"report_id": report.pk, "request_id": sr.pk})
    return report


@transaction.atomic
def complete_request(request_id: int) -> SurveyRequest:
    sr = _locked(request_id)
    _require(sr, S.IN_REVIEW)
    live = sr.reports.filter(status=Report.Status.SUBMITTED)
    units = Counter(live.values_list("surveyor_id", flat=True))
    if sum(units.values()) != sr.quantity:
        raise BusinessError("Report count does not match quantity.", code="incomplete_reports")

    live.update(status=Report.Status.APPROVED)
    sr.assignments.filter(status=Assignment.Status.ACTIVE).update(status=Assignment.Status.DONE)
    escrow_service.release(sr, units)
    for surveyor_id, n in units.items():
        SurveyorProfile.objects.filter(user_id=surveyor_id).update(completed_units=F("completed_units") + n)

    sr.status = S.COMPLETED
    sr.completed_at = timezone.now()
    sr.save(update_fields=["status", "completed_at", "updated_at"])
    logger.info("request_completed", extra={"request_id": sr.pk})
    return sr


# --- Broadcast / matching --------------------------------------------------------
def matching_surveyors(sr: SurveyRequest):
    """Verified surveyors who serve a target city, or whose radius covers the pin."""
    targets = set(sr.target_cities)
    profiles = SurveyorProfile.objects.filter(status=SurveyorProfile.Status.VERIFIED).select_related("user")
    for p in profiles.iterator():
        distance = None
        if sr.latitude is not None and sr.longitude is not None:
            distance = haversine_km(sr.latitude, sr.longitude, p.latitude, p.longitude)
        city_match = bool(targets & p.served_cities())
        radius_match = distance is not None and distance <= p.service_radius_km
        if city_match or radius_match:
            yield p.user, distance


def broadcast(request_id: int) -> int:
    sr = SurveyRequest.objects.get(pk=request_id)
    if sr.status not in (S.OPEN, S.ASSIGNED):
        return 0
    offers = [
        JobOffer(request=sr, surveyor=user, distance_km=round(d, 2) if d is not None else None)
        for user, d in matching_surveyors(sr)
        if user.pk != sr.client_id
    ]
    created = JobOffer.objects.bulk_create(offers, ignore_conflicts=True)
    logger.info("request_broadcast", extra={"request_id": sr.pk, "offers": len(created)})
    # Push notification (FCM) hook goes here in phase 2.
    return len(created)


# --- Surveyor actions --------------------------------------------------------------
@transaction.atomic
def accept_job(request_id: int, surveyor, units: int) -> Assignment:
    if not JobOffer.objects.filter(request_id=request_id, surveyor=surveyor).exists():
        raise BusinessError("This job was not offered to you.", code="not_offered", http_status=403)
    sr = _locked(request_id)
    _require(sr, S.OPEN)
    max_units = _biz()["MAX_UNITS_PER_SURVEYOR"]
    if units > max_units:
        raise BusinessError(f"Max {max_units} units per surveyor.", code="too_many_units", http_status=422)
    if units > sr.remaining_units:
        raise BusinessError(f"Only {sr.remaining_units} units left.", code="quota_full")
    if sr.assignments.filter(surveyor=surveyor).exclude(status=Assignment.Status.WITHDRAWN).exists():
        raise BusinessError("You already took this job.", code="already_assigned")

    assignment = Assignment.objects.create(request=sr, surveyor=surveyor, units=units)
    sr.claimed_units += units
    if sr.remaining_units == 0:
        sr.status = S.ASSIGNED
    sr.save(update_fields=["claimed_units", "status", "updated_at"])
    logger.info("job_accepted", extra={"request_id": sr.pk, "surveyor_id": surveyor.pk, "units": units})
    return assignment


@transaction.atomic
def withdraw(assignment_id: int, surveyor) -> Assignment:
    assignment = Assignment.objects.get(pk=assignment_id, surveyor=surveyor)
    sr = _locked(assignment.request_id)
    _require(sr, S.OPEN, S.ASSIGNED)
    if assignment.status != Assignment.Status.ACTIVE:
        raise BusinessError("Assignment is not active.", code="invalid_state")
    if assignment.reports.exclude(status=Report.Status.REJECTED).exists():
        raise BusinessError("Cannot withdraw after submitting reports.", code="has_reports")
    assignment.status = Assignment.Status.WITHDRAWN
    assignment.save(update_fields=["status"])
    sr.claimed_units -= assignment.units
    sr.status = S.OPEN
    sr.save(update_fields=["claimed_units", "status", "updated_at"])
    return assignment


def _fraud_flags(sr: SurveyRequest, *, surveyor, lat, lon, accuracy, city, photo_sha, is_mock) -> list[str]:
    flags = []
    if is_mock:
        flags.append(Report.Flag.MOCK_LOCATION)
    if accuracy > LOW_ACCURACY_M:
        flags.append(Report.Flag.LOW_GPS_ACCURACY)
    if sr.latitude is not None and sr.longitude is not None:
        if haversine_km(sr.latitude, sr.longitude, lat, lon) > _biz()["REPORT_MAX_DISTANCE_KM"]:
            flags.append(Report.Flag.FAR_FROM_TARGET)
    elif city and sr.target_cities and normalize_city(city) not in sr.target_cities:
        flags.append(Report.Flag.OUTSIDE_TARGET_CITY)
    if Report.objects.filter(photo_sha256=photo_sha).exists():
        flags.append(Report.Flag.DUPLICATE_PHOTO)
    return [str(f) for f in flags]


def _existing_report(client_uuid, surveyor) -> Report | None:
    existing = Report.objects.filter(client_uuid=client_uuid).first()
    if existing and existing.surveyor_id != surveyor.pk:
        raise BusinessError("Duplicate report id.", code="duplicate_id")
    return existing


def submit_report(assignment_id: int, surveyor, data: dict, photo_sha: str) -> tuple[Report, bool]:
    """Returns (report, created). Retrying with the same client_uuid is a no-op."""
    existing = _existing_report(data["client_uuid"], surveyor)
    if existing:
        return existing, False
    try:
        return _create_report(assignment_id, surveyor, data, photo_sha), True
    except IntegrityError:
        # Two retries raced; the other one won. Return its result.
        existing = _existing_report(data["client_uuid"], surveyor)
        if existing is None:
            raise
        return existing, False


def _create_report(assignment_id: int, surveyor, data: dict, photo_sha: str) -> Report:
    with transaction.atomic():
        assignment = Assignment.objects.get(pk=assignment_id, surveyor=surveyor)
        sr = _locked(assignment.request_id)
        _require(sr, S.OPEN, S.ASSIGNED)
        if assignment.status != Assignment.Status.ACTIVE:
            raise BusinessError("Assignment is not active.", code="invalid_state")
        live = assignment.reports.exclude(status=Report.Status.REJECTED).count()
        if live >= assignment.units:
            raise BusinessError("All units for this assignment are already reported.", code="units_complete")

        now = timezone.now()
        captured = data["captured_at"]
        if captured > now + CLOCK_SKEW:
            raise BusinessError("captured_at is in the future.", code="invalid_timestamp", http_status=422)
        if captured < now - timedelta(hours=_biz()["REPORT_MAX_AGE_HOURS"]):
            raise BusinessError("Report is too old to submit.", code="report_expired", http_status=422)

        is_mock = data.pop("is_mock_location", False)
        flags = _fraud_flags(
            sr, surveyor=surveyor, lat=data["latitude"], lon=data["longitude"],
            accuracy=data["gps_accuracy_m"], city=data.get("city", ""), photo_sha=photo_sha, is_mock=is_mock,
        )
        report = Report.objects.create(
            assignment=assignment, request=sr, surveyor=surveyor, photo_sha256=photo_sha, flags=flags, **data
        )

        total_live = sr.reports.exclude(status=Report.Status.REJECTED).count()
        if total_live == sr.quantity:
            sr.status = S.IN_REVIEW
            sr.review_started_at = now
            sr.save(update_fields=["status", "review_started_at", "updated_at"])
    logger.info(
        "report_submitted",
        extra={"report_id": report.pk, "request_id": sr.pk, "flags": ",".join(flags) or "-"},
    )
    return report


# --- Scheduled ---------------------------------------------------------------------
def auto_complete_stale() -> int:
    """Complete requests the client did not review in time.

    Requests with flagged (suspicious) reports are skipped: those need a human.
    """
    cutoff = timezone.now() - timedelta(days=_biz()["REVIEW_WINDOW_DAYS"])
    stale = SurveyRequest.objects.filter(status=S.IN_REVIEW, review_started_at__lt=cutoff)
    done = 0
    for sr in stale.iterator():
        if sr.reports.filter(status=Report.Status.SUBMITTED).exclude(flags=[]).exists():
            logger.warning("auto_complete_skipped_flagged", extra={"request_id": sr.pk})
            continue
        try:
            complete_request(sr.pk)
            done += 1
        except BusinessError:
            logger.warning("auto_complete_failed", extra={"request_id": sr.pk})
    return done
