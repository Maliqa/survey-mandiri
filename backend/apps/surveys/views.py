import logging

from django.conf import settings
from django.db.models import F, OuterRef, Subquery
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import Role
from apps.accounts.permissions import IsClient, IsVerifiedSurveyor
from apps.core.exceptions import BusinessError
from apps.core.files import sha256_of
from apps.payments.models import Escrow

from . import services
from .models import Assignment, JobOffer, PricingRate, Report, SurveyRequest
from .serializers import (
    AcceptJobSerializer,
    AssignmentSerializer,
    FundSerializer,
    JobSerializer,
    PricingRateSerializer,
    QuoteInputSerializer,
    QuoteOutputSerializer,
    RejectReportSerializer,
    ReportCreateSerializer,
    ReportSerializer,
    SurveyRequestCreateSerializer,
    SurveyRequestSerializer,
)

logger = logging.getLogger(__name__)


class PricingListView(generics.ListAPIView):
    serializer_class = PricingRateSerializer
    pagination_class = None
    queryset = PricingRate.objects.filter(is_active=True).order_by("category")


class QuoteView(APIView):
    permission_classes = [IsClient]

    @extend_schema(request=QuoteInputSerializer, responses=QuoteOutputSerializer)
    def post(self, request):
        s = QuoteInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(services.quote(**s.validated_data))


# --- Client: survey requests -------------------------------------------------------------
class SurveyRequestViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsClient]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return SurveyRequest.objects.none()
        qs = SurveyRequest.objects.filter(client=self.request.user).select_related("escrow")
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    def get_serializer_class(self):
        return SurveyRequestCreateSerializer if self.action == "create" else SurveyRequestSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["include_assignments"] = self.action != "list"
        return ctx

    def _out(self, sr, code=status.HTTP_200_OK):
        sr = SurveyRequest.objects.select_related("escrow").get(pk=sr.pk)
        return Response(SurveyRequestSerializer(sr, context=self.get_serializer_context()).data, status=code)

    @extend_schema(request=SurveyRequestCreateSerializer, responses={201: SurveyRequestSerializer})
    def create(self, request, *args, **kwargs):
        s = SurveyRequestCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sr = services.create_request(request.user, dict(s.validated_data))
        return self._out(sr, status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=SurveyRequestSerializer)
    @action(detail=True, methods=["post"], url_path="approve-quote")
    def approve_quote(self, request, pk=None):
        return self._out(services.approve_quote(self.get_object().pk))

    @extend_schema(request=FundSerializer, responses=SurveyRequestSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        """Demo payment: funds escrow instantly. Disabled when DEMO_PAYMENTS=false."""
        if not settings.BUSINESS["DEMO_PAYMENTS"]:
            raise BusinessError(
                "Online payment is not enabled. Transfer manually; admin will confirm.",
                code="payments_manual_only",
                http_status=403,
            )
        s = FundSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        sr = services.fund_and_broadcast(
            self.get_object().pk, actor=request.user, method=Escrow.Method.DEMO, reference=s.validated_data["reference"]
        )
        return self._out(sr)

    @extend_schema(request=None, responses=SurveyRequestSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self._out(services.cancel_request(self.get_object().pk))

    @extend_schema(request=None, responses=SurveyRequestSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._out(services.complete_request(self.get_object().pk))

    @extend_schema(responses=ReportSerializer(many=True))
    @action(detail=True, methods=["get"])
    def reports(self, request, pk=None):
        sr = self.get_object()
        qs = sr.reports.select_related("surveyor__surveyor_profile")
        if request.query_params.get("flagged") == "true":
            qs = qs.exclude(flags=[])
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(ReportSerializer(page, many=True, context={"request": request}).data)


class RejectReportView(APIView):
    permission_classes = [IsClient]

    @extend_schema(request=RejectReportSerializer, responses=ReportSerializer)
    def post(self, request, pk: int):
        report = get_object_or_404(Report, pk=pk, request__client=request.user)
        s = RejectReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        report = services.reject_report(report.pk, reason=s.validated_data["reason"])
        return Response(ReportSerializer(report, context={"request": request}).data)


# --- Surveyor: jobs & assignments ------------------------------------------------------------
class AvailableJobsView(generics.ListAPIView):
    serializer_class = JobSerializer
    permission_classes = [IsVerifiedSurveyor]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SurveyRequest.objects.none()
        user = self.request.user
        offer = JobOffer.objects.filter(request=OuterRef("pk"), surveyor=user)
        return (
            SurveyRequest.objects.filter(
                status=SurveyRequest.Status.OPEN, offers__surveyor=user, claimed_units__lt=F("quantity")
            )
            .exclude(assignments__surveyor=user, assignments__status=Assignment.Status.ACTIVE)
            .annotate(offer_distance_km=Subquery(offer.values("distance_km")[:1]))
            .order_by("offer_distance_km", "-broadcast_at")
            .distinct()
        )


class JobDetailView(generics.RetrieveAPIView):
    serializer_class = JobSerializer
    permission_classes = [IsVerifiedSurveyor]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SurveyRequest.objects.none()
        return SurveyRequest.objects.filter(offers__surveyor=self.request.user).distinct()


class AcceptJobView(APIView):
    permission_classes = [IsVerifiedSurveyor]

    @extend_schema(request=AcceptJobSerializer, responses={201: AssignmentSerializer})
    def post(self, request, pk: int):
        get_object_or_404(SurveyRequest, pk=pk)
        s = AcceptJobSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        assignment = services.accept_job(pk, request.user, s.validated_data["units"])
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)


class AssignmentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AssignmentSerializer
    permission_classes = [IsVerifiedSurveyor]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    throttle_scope: str | None = None  # set per action ("upload" on report submit)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Assignment.objects.none()
        qs = Assignment.objects.filter(surveyor=self.request.user).select_related("request")
        status_filter = self.request.query_params.get("status")
        return qs.filter(status=status_filter) if status_filter else qs

    @extend_schema(request=None, responses=AssignmentSerializer)
    @action(detail=True, methods=["post"])
    def withdraw(self, request, pk=None):
        assignment = services.withdraw(self.get_object().pk, request.user)
        return Response(AssignmentSerializer(assignment).data)

    @extend_schema(
        request={"multipart/form-data": ReportCreateSerializer},
        responses={201: ReportSerializer, 200: OpenApiResponse(ReportSerializer, "Already received (retry)")},
    )
    @action(detail=True, methods=["get", "post"], url_path="reports", throttle_scope="upload")
    def submit_report(self, request, pk=None):
        assignment = self.get_object()
        if request.method == "GET":
            qs = assignment.reports.all()
            return Response(ReportSerializer(qs, many=True, context={"request": request}).data)

        s = ReportCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        photo_sha = sha256_of(data["photo"])
        report, created = services.submit_report(assignment.pk, request.user, data, photo_sha)
        return Response(
            ReportSerializer(report, context={"request": request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# --- Private files --------------------------------------------------------------------------
class ReportPhotoView(APIView):
    # Session auth lets the Django admin open these links in a browser.
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, "image/*"): bytes})
    def get(self, request, pk: int):
        report = get_object_or_404(Report.objects.select_related("request"), pk=pk)
        user = request.user
        allowed = (
            user.pk in (report.surveyor_id, report.request.client_id)
            or user.role == Role.ADMIN
            or user.is_staff
        )
        if not allowed:
            # 404 instead of 403: don't reveal that the report exists.
            return Response(
                {"error": {"code": "not_found", "message": "Not found.", "details": {}}},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = FileResponse(report.photo.open("rb"))
        response["Cache-Control"] = "private, max-age=3600"
        return response
