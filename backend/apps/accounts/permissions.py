from rest_framework.permissions import BasePermission

from .models import Role


class IsClient(BasePermission):
    message = "Only client accounts can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == Role.CLIENT)


class IsVerifiedSurveyor(BasePermission):
    message = "Only verified surveyors can do this."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_verified_surveyor)


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.role == Role.ADMIN or user.is_staff))
