from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import health

admin.site.site_header = "Survey Mandiri Admin"
admin.site.site_title = "Survey Mandiri"

api_v1 = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.surveys.urls")),
    path("", include("apps.payments.urls")),
]

urlpatterns = [
    path(f"{settings.ADMIN_URL}", admin.site.urls),
    path("api/health", health, name="health"),
    path("api/v1/", include(api_v1)),
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
