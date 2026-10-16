from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import serializers

from apps.core.files import validate_image

from .models import Assignment, Category, PricingRate, Report, SurveyRequest


# --- Category-specific "details" payloads ----------------------------------------
class LeasingDetails(serializers.Serializer):
    purpose = serializers.ChoiceField(choices=["credit_worthiness", "business_location", "customer_verification"])
    applicant_ref = serializers.CharField(max_length=64, help_text="Client's internal reference, not a name")


class CalegDetails(serializers.Serializer):
    electoral_district = serializers.CharField(max_length=100)
    target_demographic = serializers.CharField(max_length=200, required=False, allow_blank=True)
    questions = serializers.ListField(
        child=serializers.CharField(max_length=300), min_length=1, max_length=30
    )


class ProductDetails(serializers.Serializer):
    product_name = serializers.CharField(max_length=120)
    condition = serializers.ChoiceField(choices=["new", "used"])
    research_type = serializers.ChoiceField(choices=["market_research", "feedback"])
    questions = serializers.ListField(
        child=serializers.CharField(max_length=300), required=False, max_length=30, default=list
    )


DETAILS_SERIALIZERS = {
    Category.LEASING: LeasingDetails,
    Category.CALEG: CalegDetails,
    Category.PRODUCT: ProductDetails,
}


# --- Pricing ------------------------------------------------------------------------
class PricingRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingRate
        fields = ["category", "unit_label", "unit_price", "min_units", "max_units"]


class QuoteInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.choices)
    quantity = serializers.IntegerField(min_value=1)


class QuoteOutputSerializer(serializers.Serializer):
    category = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_label = serializers.CharField()
    unit_price = serializers.IntegerField()
    total_price = serializers.IntegerField()


# --- Requests (client side) ----------------------------------------------------------
class SurveyRequestCreateSerializer(serializers.ModelSerializer):
    target_cities = serializers.ListField(
        child=serializers.CharField(max_length=100), min_length=1, max_length=50
    )

    class Meta:
        model = SurveyRequest
        fields = [
            "category", "title", "description", "details", "quantity",
            "target_cities", "address", "latitude", "longitude", "deadline",
        ]

    def validate_deadline(self, value):
        if value <= timezone.localdate():
            raise serializers.ValidationError("Deadline must be in the future.")
        return value

    def validate(self, attrs):
        category = attrs["category"]
        details = DETAILS_SERIALIZERS[category](data=attrs.get("details") or {})
        if not details.is_valid():
            raise serializers.ValidationError({"details": details.errors})
        attrs["details"] = details.validated_data

        has_lat, has_lon = attrs.get("latitude") is not None, attrs.get("longitude") is not None
        if has_lat != has_lon:
            raise serializers.ValidationError("latitude and longitude must be sent together.")
        if category == Category.LEASING:
            if not has_lat or not attrs.get("address"):
                raise serializers.ValidationError("Leasing surveys need a pinned address (address, lat, lon).")
        return attrs


class SurveyRequestSerializer(serializers.ModelSerializer):
    remaining_units = serializers.IntegerField(read_only=True)
    escrow_status = serializers.SerializerMethodField()
    assignments = serializers.SerializerMethodField()

    class Meta:
        model = SurveyRequest
        fields = [
            "id", "public_id", "category", "title", "description", "details", "quantity",
            "target_cities", "address", "latitude", "longitude", "deadline",
            "unit_price", "total_price", "status", "claimed_units", "remaining_units",
            "escrow_status", "assignments",
            "broadcast_at", "review_started_at", "completed_at", "created_at",
        ]
        read_only_fields = fields

    def get_escrow_status(self, obj) -> str | None:
        escrow = getattr(obj, "escrow", None)
        return escrow.status if escrow else None

    def get_assignments(self, obj) -> list[dict]:
        if not self.context.get("include_assignments"):
            return []
        qs = obj.assignments.select_related("surveyor__surveyor_profile").annotate(
            live_reports=Count("reports", filter=~Q(reports__status=Report.Status.REJECTED))
        )
        return [
            {
                "id": a.id,
                "surveyor_name": a.surveyor.surveyor_profile.full_name,
                "units": a.units,
                "status": a.status,
                "accepted_at": a.accepted_at,
                "reports_submitted": a.live_reports,
            }
            for a in qs
        ]


class RejectReportSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class FundSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


# --- Jobs (surveyor side) -------------------------------------------------------------
class JobSerializer(serializers.ModelSerializer):
    """What a surveyor sees: no client identity, earnings shown net of commission."""

    unit_earning = serializers.IntegerField(source="surveyor_unit_earning", read_only=True)
    remaining_units = serializers.IntegerField(read_only=True)
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = SurveyRequest
        fields = [
            "id", "category", "title", "description", "details", "quantity", "remaining_units",
            "target_cities", "address", "latitude", "longitude", "deadline",
            "unit_earning", "status", "distance_km", "broadcast_at",
        ]
        read_only_fields = fields

    def get_distance_km(self, obj) -> float | None:
        return getattr(obj, "offer_distance_km", None)


class AcceptJobSerializer(serializers.Serializer):
    units = serializers.IntegerField(min_value=1)


class AssignmentSerializer(serializers.ModelSerializer):
    job = JobSerializer(source="request", read_only=True)
    reports_submitted = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = ["id", "units", "status", "accepted_at", "reports_submitted", "job"]
        read_only_fields = fields

    def get_reports_submitted(self, obj) -> int:
        return obj.reports.exclude(status=Report.Status.REJECTED).count()


# --- Reports ----------------------------------------------------------------------------
class ReportCreateSerializer(serializers.ModelSerializer):
    is_mock_location = serializers.BooleanField(default=False, help_text="Location.isMock() on Android")
    photo = serializers.ImageField()

    class Meta:
        model = Report
        fields = [
            "client_uuid", "respondent_label", "answers", "notes", "photo",
            "latitude", "longitude", "gps_accuracy_m", "city", "captured_at", "is_mock_location",
        ]
        # Uniqueness is handled by the service so retries return the original report (idempotent).
        extra_kwargs = {"client_uuid": {"validators": []}}

    def validate_photo(self, value):
        try:
            validate_image(value)
        except Exception as exc:
            raise serializers.ValidationError(getattr(exc, "messages", [str(exc)])) from exc
        return value

    def validate_answers(self, value):
        if not isinstance(value, dict) or len(value) > 50:
            raise serializers.ValidationError("answers must be an object with at most 50 keys.")
        return value


class ReportSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()
    surveyor_name = serializers.CharField(source="surveyor.surveyor_profile.full_name", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id", "client_uuid", "assignment", "request", "surveyor_name", "respondent_label",
            "answers", "notes", "photo_url", "latitude", "longitude", "gps_accuracy_m", "city",
            "captured_at", "submitted_at", "status", "flags", "rejection_reason",
        ]
        read_only_fields = fields

    def get_photo_url(self, obj) -> str:
        request = self.context.get("request")
        path = f"/api/v1/reports/{obj.pk}/photo"
        return request.build_absolute_uri(path) if request else path
