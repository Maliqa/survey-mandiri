from django.urls import path

from . import views

urlpatterns = [
    path("auth/register/client", views.ClientRegisterView.as_view(), name="register-client"),
    path("auth/register/surveyor", views.SurveyorRegisterView.as_view(), name="register-surveyor"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/refresh", views.RefreshView.as_view(), name="token-refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("me", views.MeView.as_view(), name="me"),
    path(
        "admin/surveyors/<int:pk>/<str:kind>",
        views.SurveyorDocumentView.as_view(),
        name="surveyor-document",
    ),
]
