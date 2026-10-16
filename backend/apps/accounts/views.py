import logging

from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import SurveyorProfile
from .permissions import IsPlatformAdmin
from .serializers import (
    ClientRegisterSerializer,
    LoginSerializer,
    LogoutSerializer,
    SurveyorRegisterSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


class _RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        logger.info("user_registered", extra={"user_id": user.id, "role": user.role})
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class ClientRegisterView(_RegisterView):
    serializer_class = ClientRegisterSerializer


class SurveyorRegisterView(_RegisterView):
    serializer_class = SurveyorRegisterSerializer
    parser_classes = [MultiPartParser, FormParser]


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = "auth"


class RefreshView(TokenRefreshView):
    throttle_scope = "auth"


class LogoutView(APIView):
    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            if str(token.get("user_id")) != str(request.user.id):
                return Response(status=status.HTTP_204_NO_CONTENT)
            token.blacklist()
        except TokenError:
            pass  # already invalid: logout is idempotent
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class SurveyorDocumentView(APIView):
    """Admin-only stream of a surveyor's private KYC images."""

    # Session auth lets the Django admin open these links in a browser.
    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsPlatformAdmin]

    @extend_schema(responses={(200, "image/*"): bytes})
    def get(self, request, pk: int, kind: str):
        profile = get_object_or_404(SurveyorProfile, pk=pk)
        field = {"id-document": profile.id_document, "selfie": profile.selfie}.get(kind)
        if not field:
            raise Http404
        logger.info("kyc_document_viewed", extra={"profile_id": pk, "kind": kind, "admin_id": request.user.id})
        response = FileResponse(field.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response
