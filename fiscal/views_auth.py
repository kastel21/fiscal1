"""JWT authentication views with role in payload."""

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


def _get_user_role(user):
    """Resolve role: admin, operator, viewer."""
    if not user or not user.is_authenticated:
        return "viewer"
    if user.is_superuser or user.is_staff or user.groups.filter(name="admin").exists():
        return "admin"
    if user.groups.filter(name="operator").exists():
        return "operator"
    return "viewer"


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if not getattr(user, "is_staff", False) and not user.is_superuser:
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("Staff access required")
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = _get_user_role(user)
        token["username"] = user.username
        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
