from django.urls import path

from .views import PayoutListView

urlpatterns = [path("payouts", PayoutListView.as_view(), name="payouts")]
