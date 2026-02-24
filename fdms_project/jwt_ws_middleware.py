"""WebSocket middleware to authenticate via JWT in query string."""

from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

User = get_user_model()


class JWTWebSocketMiddleware:
    """If token in query string, validate and set scope['user']."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket":
            return await self.app(scope, receive, send)
        qs = scope.get("query_string", b"").decode()
        params = parse_qs(qs)
        token_list = params.get("token")
        token = token_list[0] if token_list else None
        if token and (not scope.get("user") or not scope["user"].is_authenticated):
            try:
                access = AccessToken(token)
                user_id = access.get("user_id") or access.get("sub")
                if user_id:
                    user = await sync_to_async(User.objects.get)(pk=user_id)
                    if getattr(user, "is_staff", False) or user.is_superuser:
                        scope["user"] = user
            except Exception:
                pass
        return await self.app(scope, receive, send)
