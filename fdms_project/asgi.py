"""ASGI config with Channels."""

import os
from pathlib import Path

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

def _load_env_file():
    """Load project .env so DJANGO_SETTINGS_MODULE can be sourced in production."""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        return
    with env_file.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_env_file()
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "fdms_project.settings"),
)

django_asgi_app = get_asgi_application()

from fiscal.routing import websocket_urlpatterns
from fdms_project.jwt_ws_middleware import JWTWebSocketMiddleware

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(JWTWebSocketMiddleware(URLRouter(websocket_urlpatterns)))
    ),
})
