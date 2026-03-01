"""
QuickBooks API: OAuth2 connect URL, code exchange, revoke, invoice pull/push.
"""

import logging
import secrets
from django.conf import settings
from django.utils import timezone
import requests

from quickbooks.models import QuickBooksToken
from quickbooks.utils import QuickBooksTokenError, refresh_quickbooks_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OAuth2 connect & callback
# ---------------------------------------------------------------------------


def build_connect_url(state=None):
    """
    Build the Intuit OAuth2 authorization URL for connecting a user to QuickBooks.
    Returns (url, state). Caller should store state in session to verify in callback.
    """
    client_id = (getattr(settings, "QUICKBOOKS_CLIENT_ID", "") or "").strip()
    redirect_uri = (getattr(settings, "QUICKBOOKS_REDIRECT_URI", "") or "").strip()
    auth_url = getattr(settings, "QUICKBOOKS_OAUTH_AUTHORIZE_URL", "")

    if not client_id or not redirect_uri or not auth_url:
        raise QuickBooksTokenError(
            "QUICKBOOKS_CLIENT_ID, QUICKBOOKS_REDIRECT_URI and QUICKBOOKS_OAUTH_AUTHORIZE_URL must be set"
        )

    if state is None:
        state = secrets.token_urlsafe(32)

    params = {
        "client_id": client_id,
        "scope": "com.intuit.quickbooks.accounting",
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{auth_url}?{qs}"
    return url, state


def exchange_code_for_tokens(code, realm_id, user=None):
    """
    Exchange authorization code for access_token and refresh_token.
    Creates or updates QuickBooksToken. Returns the QuickBooksToken instance.
    """
    import base64

    token_url = getattr(settings, "QUICKBOOKS_OAUTH_TOKEN_URL", "")
    redirect_uri = (getattr(settings, "QUICKBOOKS_REDIRECT_URI", "") or "").strip()
    client_id = (getattr(settings, "QUICKBOOKS_CLIENT_ID", "") or "").strip()
    client_secret = (getattr(settings, "QUICKBOOKS_CLIENT_SECRET", "") or "").strip()

    if not all([token_url, redirect_uri, client_id, client_secret]):
        raise QuickBooksTokenError(
            "QUICKBOOKS_OAUTH_TOKEN_URL, QUICKBOOKS_REDIRECT_URI, QUICKBOOKS_CLIENT_ID, QUICKBOOKS_CLIENT_SECRET must be set"
        )

    credentials = f"{client_id}:{client_secret}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    try:
        response = requests.post(token_url, headers=headers, data=data, timeout=30)
        body = response.text
        try:
            body_json = response.json()
        except Exception:
            body_json = None

        if response.status_code != 200:
            err_msg = body_json.get("error_description", body) if body_json else body
            logger.error(
                "QuickBooks token exchange failed: status=%s body=%s",
                response.status_code,
                body[:500],
            )
            raise QuickBooksTokenError(
                err_msg or f"Token exchange failed (HTTP {response.status_code})",
                status_code=response.status_code,
                response_body=body,
            )

        access_token = body_json.get("access_token")
        refresh_token = body_json.get("refresh_token")
        expires_in = body_json.get("expires_in", 3600)

        if not access_token or not refresh_token:
            raise QuickBooksTokenError("Token response missing access_token or refresh_token")

        expires_at = timezone.now() + timezone.timedelta(seconds=expires_in)

        token, _ = QuickBooksToken.objects.update_or_create(
            realm_id=realm_id,
            defaults={
                "user": user,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": body_json.get("token_type", "Bearer"),
                "expires_at": expires_at,
                "is_active": True,
            },
        )
        logger.info(
            "QuickBooks tokens stored for realm_id=%s user=%s",
            realm_id,
            user,
        )
        return token
    except QuickBooksTokenError:
        raise
    except requests.RequestException as e:
        logger.exception("QuickBooks token exchange request failed")
        raise QuickBooksTokenError(str(e)) from e


# ---------------------------------------------------------------------------
# Token revoke (disconnect)
# ---------------------------------------------------------------------------


def revoke_quickbooks_token(token_model):
    """
    Revoke token at Intuit, then mark token inactive and clear stored tokens.
    """
    revoke_url = getattr(settings, "QUICKBOOKS_OAUTH_REVOKE_URL", "")
    if not revoke_url:
        logger.warning("QUICKBOOKS_OAUTH_REVOKE_URL not set; skipping revoke call")
    else:
        try:
            response = requests.post(
                revoke_url,
                headers={
                    "Authorization": f"Bearer {token_model.access_token}",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"token": token_model.refresh_token},
                timeout=10,
            )
            if response.status_code not in (200, 204):
                logger.warning(
                    "QuickBooks revoke returned status=%s body=%s",
                    response.status_code,
                    response.text[:300],
                )
            else:
                logger.info("QuickBooks token revoked for realm_id=%s", token_model.realm_id)
        except requests.RequestException as e:
            logger.warning("QuickBooks revoke request failed: %s", e)

    token_model.access_token = ""
    token_model.refresh_token = ""
    token_model.is_active = False
    token_model.save(update_fields=["access_token", "refresh_token", "is_active", "updated_at"])


# ---------------------------------------------------------------------------
# API helpers: ensure valid token and base URL
# ---------------------------------------------------------------------------


def get_valid_token(realm_id, user=None):
    """
    Return an active QuickBooksToken for realm_id (and optionally user).
    Refreshes token if expired. Raises QuickBooksTokenError if not found or refresh fails.
    """
    qs = QuickBooksToken.objects.filter(realm_id=realm_id, is_active=True)
    if user is not None:
        qs = qs.filter(user=user)
    token = qs.order_by("-updated_at").first()
    if not token:
        raise QuickBooksTokenError(f"No active QuickBooks connection for realm_id={realm_id}")

    if token.is_expired():
        refresh_quickbooks_token(token)
        token.refresh_from_db()
    return token


def _api_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _base_url():
    return (getattr(settings, "QUICKBOOKS_API_BASE_URL", "") or "").rstrip("/")


# ---------------------------------------------------------------------------
# Invoice pull
# ---------------------------------------------------------------------------


def pull_invoices(realm_id, user=None, max_results=20):
    """
    Query QuickBooks for invoices. Returns list of invoice dicts from QueryResponse.
    """
    token = get_valid_token(realm_id, user=user)
    base = _base_url()
    if not base:
        raise QuickBooksTokenError("QUICKBOOKS_API_BASE_URL is not configured")

    url = f"{base}/v3/company/{realm_id}/query"
    params = {"query": f"SELECT * FROM Invoice MAXRESULTS {max_results}"}

    try:
        response = requests.get(
            url,
            headers=_api_headers(token.access_token),
            params=params,
            timeout=30,
        )
        if response.status_code != 200:
            try:
                err_body = response.json()
                err_msg = err_body.get("Fault", {}).get("Error", [{}])[0].get("Message", response.text)
            except Exception:
                err_msg = response.text
            logger.error("QuickBooks invoice pull failed: status=%s body=%s", response.status_code, response.text[:500])
            raise QuickBooksTokenError(err_msg or f"Invoice pull failed (HTTP {response.status_code})")

        data = response.json()
        query_response = data.get("QueryResponse", {})
        invoices = query_response.get("Invoice", [])
        return invoices if isinstance(invoices, list) else [invoices] if invoices else []
    except QuickBooksTokenError:
        raise
    except requests.RequestException as e:
        logger.exception("QuickBooks invoice pull request failed")
        raise QuickBooksTokenError(str(e)) from e


# ---------------------------------------------------------------------------
# Invoice push (update after fiscalisation)
# ---------------------------------------------------------------------------


def push_invoice_update(realm_id, invoice_id, sync_token, private_note=None, user=None):
    """
    Update a QuickBooks invoice (e.g. set PrivateNote after fiscalisation).
    invoice_id and sync_token are the QuickBooks Id and SyncToken.
    """
    token = get_valid_token(realm_id, user=user)
    base = _base_url()
    if not base:
        raise QuickBooksTokenError("QUICKBOOKS_API_BASE_URL is not configured")

    url = f"{base}/v3/company/{realm_id}/invoice?operation=update"
    payload = {
        "Id": str(invoice_id),
        "SyncToken": str(sync_token),
    }
    if private_note is not None:
        payload["PrivateNote"] = private_note

    try:
        response = requests.post(
            url,
            headers=_api_headers(token.access_token),
            json=payload,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            try:
                err_body = response.json()
                err_msg = err_body.get("Fault", {}).get("Error", [{}])[0].get("Message", response.text)
            except Exception:
                err_msg = response.text
            logger.error(
                "QuickBooks invoice update failed: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            raise QuickBooksTokenError(err_msg or f"Invoice update failed (HTTP {response.status_code})")

        return response.json()
    except QuickBooksTokenError:
        raise
    except requests.RequestException as e:
        logger.exception("QuickBooks invoice update request failed")
        raise QuickBooksTokenError(str(e)) from e
