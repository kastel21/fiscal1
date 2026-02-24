"""Middleware to authenticate API requests via JWT Bearer token."""

from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed


class JWTAuthenticationMiddleware(MiddlewareMixin):
    """Set request.user from JWT when Authorization: Bearer <token> is present."""

    def process_request(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Bearer "):
            return
        try:
            jwt_auth = JWTAuthentication()
            validated = jwt_auth.authenticate(request)
            if validated:
                request.user = validated[0]
        except (AuthenticationFailed, Exception):
            pass
