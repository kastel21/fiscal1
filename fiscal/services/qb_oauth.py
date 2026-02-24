"""
QuickBooks OAuth 2.0 client. Authorize, callback, token refresh.
"""

import logging
from datetime import datetime, timedelta

import requests
from django.conf import settings

from fiscal.models import QuickBooksConnection
from fiscal.services.key_storage import decrypt_string, encrypt_string

logger = logging.getLogger("fiscal")

INTUIT_AUTH_URL = "https://appcenter.intuit.com/connect/oauth2"
INTUIT_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"


def get_qb_credentials():
    """Return (client_id, client_secret) from settings."""
    client_id = getattr(settings, "QB_CLIENT_ID", "") or ""
    client_secret = getattr(settings, "QB_CLIENT_SECRET", "") or ""
    return client_id, client_secret


def get_redirect_uri(request=None):
    """Build redirect URI for OAuth callback."""
    uri = getattr(settings, "QB_REDIRECT_URI", "")
    if uri:
        return uri
    if request:
        return request.build_absolute_uri("/api/integrations/quickbooks/oauth/callback/")
    return ""


def get_authorize_url(state: str = "", request=None) -> str | None:
    """Build Intuit OAuth authorize URL."""
    client_id, _ = get_qb_credentials()
    if not client_id:
        return None
    redirect_uri = get_redirect_uri(request)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": redirect_uri,
        "state": state or "qb_connect",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{INTUIT_AUTH_URL}?{qs}"


def exchange_code_for_tokens(code: str, redirect_uri: str, realm_id: str) -> tuple[dict | None, str | None]:
    """
    Exchange authorization code for access and refresh tokens.
    Returns (token_dict, None) or (None, error_message).
    """
    client_id, client_secret = get_qb_credentials()
    if not client_id or not client_secret:
        return None, "QB_CLIENT_ID and QB_CLIENT_SECRET required"

    resp = requests.post(
        INTUIT_TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get("error_description", err.get("error", resp.text))
        except Exception:
            msg = resp.text
        return None, msg

    data = resp.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))
    if not access or not refresh:
        return None, "Missing access_token or refresh_token"

    from django.utils import timezone
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    conn, _ = QuickBooksConnection.objects.update_or_create(
        realm_id=realm_id,
        defaults={
            "access_token_encrypted": encrypt_string(access),
            "refresh_token_encrypted": encrypt_string(refresh),
            "token_expires_at": expires_at,
            "is_active": True,
        },
    )
    logger.info("QB OAuth: tokens stored for realm %s", realm_id)
    return {"realm_id": realm_id}, None


def refresh_tokens(conn: QuickBooksConnection) -> tuple[bool, str | None]:
    """Refresh access token. Returns (success, error_message)."""
    client_id, client_secret = get_qb_credentials()
    if not client_id or not client_secret:
        return False, "QB credentials not configured"

    try:
        refresh_token = decrypt_string(conn.refresh_token_encrypted)
    except Exception as e:
        return False, str(e)

    resp = requests.post(
        INTUIT_TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        try:
            err = resp.json()
            msg = err.get("error_description", err.get("error", resp.text))
        except Exception:
            msg = resp.text
        return False, msg

    data = resp.json()
    access = data.get("access_token")
    refresh = data.get("refresh_token") or refresh_token
    expires_in = int(data.get("expires_in", 3600))

    from django.utils import timezone
    conn.access_token_encrypted = encrypt_string(access)
    conn.refresh_token_encrypted = encrypt_string(refresh)
    conn.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    conn.save(update_fields=["access_token_encrypted", "refresh_token_encrypted", "token_expires_at", "updated_at"])
    logger.info("QB OAuth: tokens refreshed for realm %s", conn.realm_id)
    return True, None
