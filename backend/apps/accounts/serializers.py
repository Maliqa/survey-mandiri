from django.contrib.auth import password_validation
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.files import validate_image

from .models import ClientType, Role, SurveyorProfile, User


def _validate_image_field(value):
    try:
        validate_image(value)
    except Exception as exc:  # django ValidationError -> DRF ValidationError
        raise serializers.ValidationError(getattr(exc, "messages", [str(exc)])) from exc
    return value


class SurveyorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyorProfile
        fields = [
            "full_name", "city", "service_cities", "latitude", "longitude", "service_radius_km",
            "status", "rejection_reason", "rating_avg", "completed_units", "verified_at",
        ]
        read_only_fields = ["status", "rejection_reason", "rating_avg", "completed_units", "verified_at"]


class UserSerializer(serializers.ModelSerializer):
    surveyor_profile = SurveyorProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "phone", "role", "client_type", "organization", "surveyor_profile"]
        read_only_fields = fields


class _BaseRegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    phone = serializers.RegexField(r"^\+?62\d{8,13}$|^0\d{9,13}$")

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(attrs["password"], User(email=attrs["email"]))
        return attrs


class ClientRegisterSerializer(_BaseRegisterSerializer):
    client_type = serializers.ChoiceField(choices=ClientType.choices)
    organization = serializers.CharField(max_length=150)

    def create(self, validated_data):
        return User.objects.create_user(role=Role.CLIENT, **validated_data)


class SurveyorRegisterSerializer(_BaseRegisterSerializer):
    full_name = serializers.CharField(max_length=150)
    nik = serializers.RegexField(r"^\d{16}$", write_only=True, help_text="16-digit NIK; only last 4 stored")
    city = serializers.CharField(max_length=100)
    service_cities = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False, max_length=10, default=list
    )
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    service_radius_km = serializers.IntegerField(min_value=1, max_value=300, default=25)
    id_document = serializers.ImageField(validators=[_validate_image_field])
    selfie = serializers.ImageField(validators=[_validate_image_field])

    @transaction.atomic
    def create(self, validated_data):
        nik = validated_data.pop("nik")
        user = User.objects.create_user(
            email=validated_data.pop("email"),
            password=validated_data.pop("password"),
            phone=validated_data.pop("phone"),
            role=Role.SURVEYOR,
        )
        SurveyorProfile.objects.create(user=user, nik_last4=nik[-4:], **validated_data)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """JWT pair + role claim so the app can route without an extra call."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
