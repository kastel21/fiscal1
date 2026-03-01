"""
QuickBooks OAuth2 token refresh and secure token handling.
"""

import base64
import logging
from django.conf import settings
from django.utils import timezone
import requests

logger = logging.getLogger(__name__)


class QuickBooksTokenError(Exception):
    """Raised when token exchange or refresh fails."""

    def __init__(self, message, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def _get_token_request_headers():
    """Basic auth header for Intuit token endpoint: base64(client_id:client_secret)."""
    client_id = (getattr(settings, "QUICKBOOKS_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "QUICKBOOKS_CLIENT_SECRET", "") or "").strip()
    if not client_id or not client_secret:
        raise QuickBooksTokenError("QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET must be set")
    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def refresh_quickbooks_token(token_model):
    """
    Exchange refresh_token for new access_token. Updates token_model in DB.
    Raises QuickBooksTokenError on failure.
    """
    token_url = getattr(settings, "QUICKBOOKS_OAUTH_TOKEN_URL", "")
    if not token_url:
        raise QuickBooksTokenError("QUICKBOOKS_OAUTH_TOKEN_URL is not configured")

    if not token_model.refresh_token:
        raise QuickBooksTokenError("No refresh token available")

    headers = _get_token_request_headers()
    data = {
        "grant_type": "refresh_token",
        "refresh_token": token_model.refresh_token,
    }

    try:
        response = requests.post(
            token_url,
            headers=headers,
            data=data,
            timeout=30,
        )
        body = response.text
        try:
            body_json = response.json()
        except Exception:
            body_json = None

        if response.status_code != 200:
            err_msg = body_json.get("error_description", body) if body_json else body
            logger.error(
                "QuickBooks token refresh failed: status=%s body=%s",
                response.status_code,
                body[:500],
            )
            raise QuickBooksTokenError(
                err_msg or f"Token refresh failed (HTTP {response.status_code})",
                status_code=response.status_code,
                response_body=body,
            )

        access_token = body_json.get("access_token")
        refresh_token = body_json.get("refresh_token", token_model.refresh_token)
        expires_in = body_json.get("expires_in", 3600)

        if not access_token:
            raise QuickBooksTokenError("Token response missing access_token")

        # Timezone-aware expiry (Intuit returns seconds from now)
        token_model.access_token = access_token
        token_model.refresh_token = refresh_token
        token_model.expires_at = timezone.now() + timezone.timedelta(seconds=expires_in)
        token_model.save(update_fields=["access_token", "refresh_token", "expires_at", "updated_at"])

        logger.info("QuickBooks token refreshed for realm_id=%s", token_model.realm_id)
    except QuickBooksTokenError:
        raise
    except requests.RequestException as e:
        logger.exception("QuickBooks token refresh request failed")
        raise QuickBooksTokenError(str(e)) from e
