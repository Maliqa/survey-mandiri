from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.urls import reverse
from django.utils.html import format_html

from apps.surveys.tasks import broadcast_request
from apps.surveys.models import SurveyRequest

from .models import SurveyorProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "role", "client_type", "organization", "is_active", "date_joined"]
    list_filter = ["role", "client_type", "is_active", "is_staff"]
    search_fields = ["email", "phone", "organization"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profil", {"fields": ("phone", "role", "client_type", "organization")}),
        ("Akses", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Waktu", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "phone", "role", "password1", "password2")}),)


@admin.register(SurveyorProfile)
class SurveyorProfileAdmin(admin.ModelAdmin):
    list_display = ["full_name", "user", "city", "status", "completed_units", "created_at"]
    list_filter = ["status", "city_normalized"]
    search_fields = ["full_name", "user__email", "city"]
    readonly_fields = [
        "user", "nik_last4", "id_document_link", "selfie_link", "verified_at", "verified_by",
        "rating_avg", "completed_units", "created_at",
    ]
    exclude = ["id_document", "selfie"]
    actions = ["verify_selected", "reject_selected", "suspend_selected"]

    def _doc_link(self, obj, kind):
        if not obj.pk:
            return "-"
        url = reverse("surveyor-document", kwargs={"pk": obj.pk, "kind": kind})
        return format_html('<a href="{}" target="_blank" rel="noopener">Lihat</a>', url)

    @admin.display(description="Foto KTP")
    def id_document_link(self, obj):
        return self._doc_link(obj, "id-document")

    @admin.display(description="Selfie")
    def selfie_link(self, obj):
        return self._doc_link(obj, "selfie")

    @admin.action(description="Verifikasi surveyor terpilih")
    def verify_selected(self, request, queryset):
        count = 0
        for profile in queryset.exclude(status=SurveyorProfile.Status.VERIFIED):
            profile.verify(request.user)
            count += 1
        # Newly verified surveyors should see jobs already open in their area.
        for pk in SurveyRequest.objects.filter(status=SurveyRequest.Status.OPEN).values_list("pk", flat=True):
            broadcast_request.delay(pk)
        self.message_user(request, f"{count} surveyor diverifikasi.", messages.SUCCESS)

    @admin.action(description="Tolak surveyor terpilih (dokumen tidak valid)")
    def reject_selected(self, request, queryset):
        for profile in queryset:
            profile.reject(request.user, "Dokumen tidak valid. Silakan daftar ulang dengan foto yang jelas.")
        self.message_user(request, "Surveyor ditolak.", messages.WARNING)

    @admin.action(description="Tangguhkan surveyor terpilih")
    def suspend_selected(self, request, queryset):
        queryset.update(status=SurveyorProfile.Status.SUSPENDED)
        self.message_user(request, "Surveyor ditangguhkan.", messages.WARNING)
