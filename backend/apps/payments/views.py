from django.db.models import Sum
from rest_framework import generics
from rest_framework.response import Response

from apps.accounts.permissions import IsVerifiedSurveyor

from .models import Payout
from .serializers import PayoutSerializer


class PayoutListView(generics.ListAPIView):
    """Surveyor earnings, with totals for the wallet screen."""

    serializer_class = PayoutSerializer
    permission_classes = [IsVerifiedSurveyor]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Payout.objects.none()
        return Payout.objects.filter(surveyor=self.request.user).select_related("escrow__request")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        totals = self.get_queryset().values("status").annotate(total=Sum("net_amount"))
        response.data["totals"] = {row["status"]: row["total"] for row in totals}
        return response
