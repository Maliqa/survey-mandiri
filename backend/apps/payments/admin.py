from django.contrib import admin, messages
from django.utils import timezone

from .models import Escrow, Payout


@admin.register(Escrow)
class EscrowAdmin(admin.ModelAdmin):
    list_display = ["request", "amount", "method", "status", "platform_fee", "funded_at", "closed_at"]
    list_filter = ["status", "method"]
    readonly_fields = [f.name for f in Escrow._meta.fields]

    def has_add_permission(self, request):
        return False  # escrow is only created through the payment flow

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ["id", "surveyor", "escrow", "units", "net_amount", "status", "paid_at"]
    list_filter = ["status"]
    readonly_fields = ["escrow", "surveyor", "units", "gross_amount", "fee_amount", "net_amount", "created_at", "paid_at"]
    actions = ["mark_paid"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Tandai sudah ditransfer")
    def mark_paid(self, request, queryset):
        n = queryset.filter(status=Payout.Status.PENDING).update(status=Payout.Status.PAID, paid_at=timezone.now())
        self.message_user(request, f"{n} payout ditandai lunas.", messages.SUCCESS)
