from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from apps.core.exceptions import BusinessError
from apps.core.geo import haversine_km
from apps.payments.models import Escrow

from . import reporting, services
from .models import Assignment, JobOffer, PricingRate, Report, SurveyRequest
from .tasks import broadcast_request

RED = "#C5221F"


def _flag_badges(flags):
    if not flags:
        return format_html('<span style="color:#1E8E3E;font-weight:600">✓ Bersih</span>')
    labels = dict(Report.Flag.choices)
    return format_html_join(
        " ",
        '<span style="background:#FDECEA;color:' + RED + ';border-radius:6px;padding:2px 7px;'
        'font-weight:600;white-space:nowrap;display:inline-block;margin:1px 0">⚠ {}</span>',
        ((labels.get(f, f),) for f in flags),
    )


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
    list_display = ["id", "title", "client", "category", "quantity", "claimed_units", "total_price", "status", "report_links", "created_at"]
    list_filter = ["status", "category"]
    search_fields = ["title", "client__email", "client__organization"]
    readonly_fields = [
        "report_links", "public_id", "client", "unit_price", "total_price", "commission_percent", "claimed_units", "status",
        "broadcast_at", "review_started_at", "completed_at", "cancelled_at", "created_at",
    ]
    inlines = [AssignmentInline]
    actions = ["confirm_manual_payment", "rebroadcast", "force_complete"]

    @admin.display(description="Laporan")
    def report_links(self, obj):
        if not obj.pk:
            return "-"
        urls = reporting.report_urls(obj)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Lihat</a> · <a href="{}?download=1">PDF</a>',
            urls["url"], urls["pdf_url"],
        )

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


class FlaggedFilter(admin.SimpleListFilter):
    title = "indikasi fraud"
    parameter_name = "flagged"

    def lookups(self, request, model_admin):
        return [("yes", "Mencurigakan"), ("no", "Bersih")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.exclude(flags=[])
        if self.value() == "no":
            return queryset.filter(flags=[])
        return queryset


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "thumbnail", "flag_badges", "request_link", "surveyor_name", "status", "captured_at", "maps_link"]
    list_display_links = ["id", "thumbnail"]
    list_filter = [FlaggedFilter, "status"]
    search_fields = ["request__title", "surveyor__email", "respondent_label"]
    list_select_related = ["request", "surveyor__surveyor_profile"]
    list_per_page = 30
    fieldsets = [
        ("Bukti", {"fields": ["photo_large", "flag_badges", "maps_link", "distance_to_target"]}),
        ("Laporan", {"fields": ["request_link", "surveyor_name", "respondent_label", "answers_table", "notes", "status", "rejection_reason"]}),
        ("Data teknis", {"classes": ["collapse"], "fields": [
            "latitude", "longitude", "gps_accuracy_m", "city", "captured_at", "submitted_at", "client_uuid", "photo_sha256",
        ]}),
    ]
    readonly_fields = [
        "photo_large", "flag_badges", "maps_link", "distance_to_target", "request_link", "surveyor_name",
        "respondent_label", "answers_table", "notes", "status", "rejection_reason",
        "latitude", "longitude", "gps_accuracy_m", "city", "captured_at", "submitted_at", "client_uuid", "photo_sha256",
    ]
    actions = ["reject_selected"]

    def has_add_permission(self, request):
        return False  # reports only come from the surveyor app

    def _photo_url(self, obj):
        return reverse("report-photo", kwargs={"pk": obj.pk})

    @admin.display(description="Foto")
    def thumbnail(self, obj):
        return format_html(
            '<img src="{}" loading="lazy" style="width:72px;height:72px;object-fit:cover;border-radius:8px">',
            self._photo_url(obj),
        )

    @admin.display(description="Foto bukti")
    def photo_large(self, obj):
        url = self._photo_url(obj)
        return format_html(
            '<a href="{}" target="_blank" rel="noopener"><img src="{}" style="max-width:min(480px,100%);border-radius:10px"></a>',
            url, url,
        )

    @admin.display(description="Indikasi fraud")
    def flag_badges(self, obj):
        return _flag_badges(obj.flags)

    @admin.display(description="Lokasi")
    def maps_link(self, obj):
        return format_html(
            '<a href="https://www.google.com/maps?q={},{}" target="_blank" rel="noopener noreferrer">Buka Maps</a>'
            ' <span style="color:#888">(±{} m)</span>',
            f"{obj.latitude:.6f}", f"{obj.longitude:.6f}", f"{obj.gps_accuracy_m:.0f}",
        )

    @admin.display(description="Jarak ke titik target")
    def distance_to_target(self, obj):
        sr = obj.request
        if sr.latitude is None or sr.longitude is None:
            return "Tidak ada titik target"
        meters = round(haversine_km(sr.latitude, sr.longitude, obj.latitude, obj.longitude) * 1000)
        return f"{meters} m"

    @admin.display(description="Permintaan", ordering="request")
    def request_link(self, obj):
        url = reverse("admin:surveys_surveyrequest_change", args=[obj.request_id])
        return format_html('<a href="{}">#{} {}</a>', url, obj.request_id, obj.request.title)

    @admin.display(description="Surveyor")
    def surveyor_name(self, obj):
        profile = getattr(obj.surveyor, "surveyor_profile", None)
        return profile.full_name if profile else obj.surveyor.email

    @admin.display(description="Jawaban")
    def answers_table(self, obj):
        answers = obj.answers if isinstance(obj.answers, dict) else {}
        if not answers:
            return "-"
        return format_html(
            '<table style="border-collapse:collapse">{}</table>',
            format_html_join("", '<tr><td style="padding:2px 12px 2px 0;color:#888">{}</td><td>{}</td></tr>', answers.items()),
        )

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
