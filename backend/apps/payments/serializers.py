from rest_framework import serializers

from .models import Payout


class PayoutSerializer(serializers.ModelSerializer):
    request_id = serializers.IntegerField(source="escrow.request_id", read_only=True)
    request_title = serializers.CharField(source="escrow.request.title", read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id", "request_id", "request_title", "units", "gross_amount", "fee_amount",
            "net_amount", "status", "created_at", "paid_at",
        ]
        read_only_fields = fields
