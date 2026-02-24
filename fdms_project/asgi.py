"""ASGI config with Channels."""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fdms_project.settings")

django_asgi_app = get_asgi_application()

from fiscal.routing import websocket_urlpatterns
from fdms_project.jwt_ws_middleware import JWTWebSocketMiddleware

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(JWTWebSocketMiddleware(URLRouter(websocket_urlpatterns)))
    ),
})
