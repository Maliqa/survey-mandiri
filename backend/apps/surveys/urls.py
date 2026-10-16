from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter(trailing_slash=False)
router.register("requests", views.SurveyRequestViewSet, basename="requests")
router.register("assignments", views.AssignmentViewSet, basename="assignments")

urlpatterns = [
    path("pricing", views.PricingListView.as_view(), name="pricing"),
    path("quote", views.QuoteView.as_view(), name="quote"),
    path("reports/<int:pk>/reject", views.RejectReportView.as_view(), name="report-reject"),
    path("reports/<int:pk>/photo", views.ReportPhotoView.as_view(), name="report-photo"),
    path("jobs/available", views.AvailableJobsView.as_view(), name="jobs-available"),
    path("jobs/<int:pk>", views.JobDetailView.as_view(), name="job-detail"),
    path("jobs/<int:pk>/accept", views.AcceptJobView.as_view(), name="job-accept"),
    *router.urls,
]
