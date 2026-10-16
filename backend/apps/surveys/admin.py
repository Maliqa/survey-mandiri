from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from apps.core.exceptions import BusinessError
from apps.payments.models import Escrow

from . import services
from .models import Assignment, JobOffer, PricingRate, Report, SurveyRequest
from .tasks import broadcast_request


@admin.register(PricingRate)
class PricingRateAdmin(admin.ModelAdmin):
    list_display = ["category", "unit_label", "unit_price", "min_units", "max_units", "is_active", "updated_at"]
    list_editable = ["unit_price", "is_active"]


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    can_delete = False
    readonly_fields = ["surveyor", "units", "status", "accepted_at"]


@admin.register(SurveyRequest)
class SurveyRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "client", "category", "quantity", "claimed_units", "total_price", "status", "created_at"]
    list_filter = ["status", "category"]
    search_fields = ["title", "client__email", "client__organization"]
    readonly_fields = [
        "public_id", "client", "unit_price", "total_price", "commission_percent", "claimed_units", "status",
        "broadcast_at", "review_started_at", "completed_at", "cancelled_at", "created_at",
    ]
    inlines = [AssignmentInline]
    actions = ["confirm_manual_payment", "rebroadcast", "force_complete"]

    @admin.action(description="Konfirmasi transfer manual & broadcast")
    def confirm_manual_payment(self, request, queryset):
        for sr in queryset:
            try:
                services.fund_and_broadcast(sr.pk, actor=request.user, method=Escrow.Method.MANUAL_TRANSFER)
                self.message_user(request, f"#{sr.pk} dibayar & di-broadcast.", messages.SUCCESS)
            except BusinessError as exc:
                self.message_user(request, f"#{sr.pk}: {exc.detail}", messages.ERROR)

    @admin.action(description="Broadcast ulang ke surveyor yang cocok")
    def rebroadcast(self, request, queryset):
        for sr in queryset.filter(status__in=[SurveyRequest.Status.OPEN, SurveyRequest.Status.ASSIGNED]):
            broadcast_request.delay(sr.pk)
        self.message_user(request, "Broadcast dijadwalkan.", messages.INFO)

    @admin.action(description="Selesaikan (setujui semua laporan & cairkan escrow)")
    def force_complete(self, request, queryset):
        for sr in queryset:
            try:
                services.complete_request(sr.pk)
                self.message_user(request, f"#{sr.pk} selesai.", messages.SUCCESS)
            except BusinessError as exc:
                self.message_user(request, f"#{sr.pk}: {exc.detail}", messages.ERROR)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "request", "surveyor", "status", "flag_list", "captured_at", "submitted_at"]
    list_filter = ["status"]
    search_fields = ["request__title", "surveyor__email"]
    readonly_fields = [f.name for f in Report._meta.fields if f.name != "photo"] + ["photo_link"]
    exclude = ["photo"]
    actions = ["reject_selected"]

    @admin.display(description="Flags")
    def flag_list(self, obj):
        return ", ".join(obj.flags) or "-"

    @admin.display(description="Foto")
    def photo_link(self, obj):
        url = reverse("report-photo", kwargs={"pk": obj.pk})
        return format_html('<a href="{}" target="_blank" rel="noopener">Lihat foto</a>', url)

    @admin.action(description="Tolak laporan terpilih (indikasi fraud)")
    def reject_selected(self, request, queryset):
        for report in queryset:
            try:
                services.reject_report(report.pk, reason="Ditolak admin: indikasi fraud")
            except BusinessError as exc:
                self.message_user(request, f"#{report.pk}: {exc.detail}", messages.ERROR)


@admin.register(JobOffer)
class JobOfferAdmin(admin.ModelAdmin):
    list_display = ["request", "surveyor", "distance_km", "created_at"]
    list_filter = ["request__status"]
