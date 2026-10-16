from datetime import timedelta

import pytest
from django.utils import timezone

from apps.payments.models import Escrow, Payout
from apps.surveys import services
from apps.surveys.models import JobOffer, Report, SurveyRequest

from .conftest import auth, caleg_payload, leasing_payload, report_payload

# transaction=True so transaction.on_commit (broadcast enqueue) really fires.
pytestmark = pytest.mark.django_db(transaction=True)


def create_and_pay(client_user, payload):
    c = auth(client_user)
    res = c.post("/api/v1/requests", payload, format="json")
    assert res.status_code == 201, res.data
    rid = res.data["id"]
    assert res.data["status"] == "quoted"
    assert c.post(f"/api/v1/requests/{rid}/approve-quote").data["status"] == "awaiting_payment"
    res = c.post(f"/api/v1/requests/{rid}/pay", {"reference": "DEMO-1"}, format="json")
    assert res.status_code == 200, res.data
    assert res.data["status"] == "open" and res.data["escrow_status"] == "funded"
    return rid


def test_quote_uses_platform_rate(client_user):
    res = auth(client_user).post("/api/v1/quote", {"category": "caleg", "quantity": 100}, format="json")
    assert res.status_code == 200
    assert res.data["unit_price"] == 50_000 and res.data["total_price"] == 5_000_000


def test_leasing_requires_pinned_address(client_user):
    res = auth(client_user).post("/api/v1/requests", leasing_payload(latitude=None, longitude=None), format="json")
    assert res.status_code == 400


def test_category_details_are_validated(client_user):
    res = auth(client_user).post("/api/v1/requests", caleg_payload(details={"questions": []}), format="json")
    assert res.status_code == 400
    assert "details" in res.data["error"]["details"]


def test_broadcast_matches_city_and_radius_only(client_user, surveyor_jkt, surveyor_bdg):
    rid = create_and_pay(client_user, leasing_payload())
    offered = set(JobOffer.objects.filter(request_id=rid).values_list("surveyor__email", flat=True))
    assert offered == {"jkt@test.id"}
    assert auth(surveyor_bdg).get("/api/v1/jobs/available").data["count"] == 0
    jobs = auth(surveyor_jkt).get("/api/v1/jobs/available").data
    assert jobs["count"] == 1
    # Surveyor sees net earning, never the client identity.
    assert jobs["results"][0]["unit_earning"] == 120_000
    assert "client" not in jobs["results"][0]


def test_job_not_offered_cannot_be_accepted(client_user, surveyor_jkt, surveyor_bdg):
    rid = create_and_pay(client_user, leasing_payload())
    res = auth(surveyor_bdg).post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json")
    assert res.status_code == 403
    assert res.data["error"]["code"] == "not_offered"


def test_full_flow_two_surveyors_escrow_and_payouts(client_user, surveyor_jkt, surveyor_jkt2):
    rid = create_and_pay(client_user, caleg_payload(quantity=3))
    s1, s2 = auth(surveyor_jkt), auth(surveyor_jkt2)

    a1 = s1.post(f"/api/v1/jobs/{rid}/accept", {"units": 2}, format="json")
    assert a1.status_code == 201
    over = s2.post(f"/api/v1/jobs/{rid}/accept", {"units": 2}, format="json")
    assert over.status_code == 409 and over.data["error"]["code"] == "quota_full"
    a2 = s2.post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json")
    assert a2.status_code == 201
    assert SurveyRequest.objects.get(pk=rid).status == SurveyRequest.Status.ASSIGNED

    for color in [(1, 2, 3), (4, 5, 6)]:
        r = s1.post(f"/api/v1/assignments/{a1.data['id']}/reports", report_payload(color=color), format="multipart")
        assert r.status_code == 201, r.data
    extra = s1.post(f"/api/v1/assignments/{a1.data['id']}/reports", report_payload(color=(9, 9, 9)), format="multipart")
    assert extra.status_code == 409 and extra.data["error"]["code"] == "units_complete"

    r = s2.post(f"/api/v1/assignments/{a2.data['id']}/reports", report_payload(color=(7, 8, 9)), format="multipart")
    assert r.status_code == 201
    assert SurveyRequest.objects.get(pk=rid).status == SurveyRequest.Status.IN_REVIEW

    c = auth(client_user)
    assert c.get(f"/api/v1/requests/{rid}/reports").data["count"] == 3
    done = c.post(f"/api/v1/requests/{rid}/complete")
    assert done.status_code == 200 and done.data["status"] == "completed"

    escrow = Escrow.objects.get(request_id=rid)
    assert escrow.status == Escrow.Status.RELEASED
    assert escrow.amount == 150_000 and escrow.platform_fee == 30_000
    payouts = {p.surveyor.email: p for p in Payout.objects.filter(escrow=escrow)}
    assert payouts["jkt@test.id"].net_amount == 80_000
    assert payouts["jkt2@test.id"].net_amount == 40_000
    wallet = s1.get("/api/v1/payouts").data
    assert wallet["totals"] == {"pending": 80_000}
    assert surveyor_jkt.surveyor_profile.__class__.objects.get(pk=surveyor_jkt.surveyor_profile.pk).completed_units == 2


def test_report_retry_is_idempotent(client_user, surveyor_jkt):
    rid = create_and_pay(client_user, caleg_payload(quantity=2))
    s = auth(surveyor_jkt)
    aid = s.post(f"/api/v1/jobs/{rid}/accept", {"units": 2}, format="json").data["id"]
    payload = report_payload()
    first = s.post(f"/api/v1/assignments/{aid}/reports", payload, format="multipart")
    retry_payload = {**payload, "photo": report_payload()["photo"]}
    retry = s.post(f"/api/v1/assignments/{aid}/reports", retry_payload, format="multipart")
    assert first.status_code == 201 and retry.status_code == 200
    assert first.data["id"] == retry.data["id"]
    assert Report.objects.count() == 1


def test_fraud_flags_far_mock_and_duplicate(client_user, surveyor_jkt):
    rid = create_and_pay(client_user, caleg_payload(quantity=3, latitude=-6.26, longitude=106.813))
    s = auth(surveyor_jkt)
    aid = s.post(f"/api/v1/jobs/{rid}/accept", {"units": 3}, format="json").data["id"]

    far = s.post(f"/api/v1/assignments/{aid}/reports", report_payload(lat=-6.40, lon=106.9), format="multipart")
    assert "far_from_target" in far.data["flags"]
    mock = s.post(
        f"/api/v1/assignments/{aid}/reports", report_payload(color=(50, 50, 50), is_mock_location=True), format="multipart"
    )
    assert "mock_location" in mock.data["flags"]
    dup = s.post(f"/api/v1/assignments/{aid}/reports", report_payload(), format="multipart")  # same color as `far`
    assert "duplicate_photo" in dup.data["flags"]

    flagged = auth(client_user).get(f"/api/v1/requests/{rid}/reports?flagged=true").data
    assert flagged["count"] == 3


def test_rejected_report_reopens_unit(client_user, surveyor_jkt):
    rid = create_and_pay(client_user, caleg_payload(quantity=1))
    s = auth(surveyor_jkt)
    aid = s.post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json").data["id"]
    report_id = s.post(f"/api/v1/assignments/{aid}/reports", report_payload(), format="multipart").data["id"]
    assert SurveyRequest.objects.get(pk=rid).status == SurveyRequest.Status.IN_REVIEW

    res = auth(client_user).post(f"/api/v1/reports/{report_id}/reject", {"reason": "Foto buram"}, format="json")
    assert res.status_code == 200 and res.data["status"] == "rejected"
    assert SurveyRequest.objects.get(pk=rid).status == SurveyRequest.Status.ASSIGNED
    redo = s.post(f"/api/v1/assignments/{aid}/reports", report_payload(color=(200, 1, 1)), format="multipart")
    assert redo.status_code == 201
    assert SurveyRequest.objects.get(pk=rid).status == SurveyRequest.Status.IN_REVIEW


def test_report_timestamp_rules(client_user, surveyor_jkt):
    rid = create_and_pay(client_user, caleg_payload(quantity=2))
    s = auth(surveyor_jkt)
    aid = s.post(f"/api/v1/jobs/{rid}/accept", {"units": 2}, format="json").data["id"]
    future = (timezone.now() + timedelta(hours=1)).isoformat()
    old = (timezone.now() - timedelta(days=10)).isoformat()
    assert s.post(f"/api/v1/assignments/{aid}/reports", report_payload(captured_at=future), format="multipart").data["error"]["code"] == "invalid_timestamp"
    assert s.post(f"/api/v1/assignments/{aid}/reports", report_payload(captured_at=old), format="multipart").data["error"]["code"] == "report_expired"


def test_cancel_refunds_only_before_claims(client_user, surveyor_jkt):
    rid = create_and_pay(client_user, caleg_payload(quantity=2))
    c = auth(client_user)
    auth(surveyor_jkt).post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json")
    assert c.post(f"/api/v1/requests/{rid}/cancel").data["error"]["code"] == "already_claimed"

    rid2 = create_and_pay(client_user, caleg_payload(quantity=2))
    res = c.post(f"/api/v1/requests/{rid2}/cancel")
    assert res.data["status"] == "cancelled" and res.data["escrow_status"] == "refunded"


def test_withdraw_frees_units(client_user, surveyor_jkt, surveyor_jkt2):
    rid = create_and_pay(client_user, caleg_payload(quantity=1))
    aid = auth(surveyor_jkt).post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json").data["id"]
    assert auth(surveyor_jkt).post(f"/api/v1/assignments/{aid}/withdraw").status_code == 200
    assert auth(surveyor_jkt2).post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json").status_code == 201


def test_client_cannot_see_other_clients_requests_or_photos(client_user, surveyor_jkt, surveyor_bdg):
    from apps.accounts.models import Role, User

    other = User.objects.create_user("other@test.id", "Str0ng!Passw0rd", role=Role.CLIENT, phone="081200000001")
    rid = create_and_pay(client_user, caleg_payload(quantity=1))
    aid = auth(surveyor_jkt).post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json").data["id"]
    rep = auth(surveyor_jkt).post(f"/api/v1/assignments/{aid}/reports", report_payload(), format="multipart").data

    assert auth(other).get(f"/api/v1/requests/{rid}").status_code == 404
    assert auth(other).get(f"/api/v1/reports/{rep['id']}/photo").status_code == 404
    assert auth(surveyor_bdg).get(f"/api/v1/reports/{rep['id']}/photo").status_code == 404
    assert auth(client_user).get(f"/api/v1/reports/{rep['id']}/photo").status_code == 200


def test_auto_complete_skips_flagged(client_user, surveyor_jkt):
    clean = create_and_pay(client_user, caleg_payload(quantity=1))
    flagged = create_and_pay(client_user, caleg_payload(quantity=1))
    s = auth(surveyor_jkt)
    for rid, mock in [(clean, False), (flagged, True)]:
        aid = s.post(f"/api/v1/jobs/{rid}/accept", {"units": 1}, format="json").data["id"]
        s.post(
            f"/api/v1/assignments/{aid}/reports",
            report_payload(color=(rid, 1, 1), is_mock_location=mock),
            format="multipart",
        )
    SurveyRequest.objects.update(review_started_at=timezone.now() - timedelta(days=5))
    assert services.auto_complete_stale() == 1
    assert SurveyRequest.objects.get(pk=clean).status == SurveyRequest.Status.COMPLETED
    assert SurveyRequest.objects.get(pk=flagged).status == SurveyRequest.Status.IN_REVIEW


def test_demo_payment_can_be_disabled(client_user, settings):
    settings.BUSINESS = {**settings.BUSINESS, "DEMO_PAYMENTS": False}
    c = auth(client_user)
    rid = c.post("/api/v1/requests", caleg_payload(quantity=1), format="json").data["id"]
    c.post(f"/api/v1/requests/{rid}/approve-quote")
    res = c.post(f"/api/v1/requests/{rid}/pay")
    assert res.status_code == 403 and res.data["error"]["code"] == "payments_manual_only"
