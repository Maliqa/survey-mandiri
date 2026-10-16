"""Uniform error envelope for every API error.

{"error": {"code": "invalid_state", "message": "...", "details": {...}}}
"""
import logging

from django.core.exceptions import PermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class BusinessError(exceptions.APIException):
    """Domain rule violation (wrong state, quota full, etc.)."""

    status_code = status.HTTP_409_CONFLICT
    default_code = "business_rule_violation"
    default_detail = "Operation not allowed."

    def __init__(self, message: str, code: str | None = None, http_status: int | None = None):
        super().__init__(detail=message, code=code or self.default_code)
        self.error_code = code or self.default_code
        if http_status:
            self.status_code = http_status


def _code_for(exc: Exception) -> str:
    if isinstance(exc, BusinessError):
        return exc.error_code
    if isinstance(exc, exceptions.ValidationError):
        return "validation_error"
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)):
        return "unauthenticated"
    if isinstance(exc, (exceptions.PermissionDenied, PermissionDenied)):
        return "forbidden"
    if isinstance(exc, (exceptions.NotFound, Http404)):
        return "not_found"
    if isinstance(exc, exceptions.Throttled):
        return "rate_limited"
    if isinstance(exc, exceptions.APIException):
        return exc.default_code
    return "server_error"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        logger.exception("Unhandled API error", extra={"view": context["view"].__class__.__name__})
        return Response(
            {"error": {"code": "server_error", "message": "Internal server error.", "details": {}}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    if isinstance(exc, exceptions.ValidationError):
        message, details = "Invalid input.", data
    elif isinstance(data, dict) and "detail" in data:
        message, details = str(data["detail"]), {k: v for k, v in data.items() if k != "detail"}
    else:
        message, details = "Request failed.", data
    response.data = {"error": {"code": _code_for(exc), "message": message, "details": details}}
    return response
