"""
QuickBooks API: OAuth2 connect URL, code exchange, revoke, invoice pull/push.
Uses QuickBooksClient for all API calls (captures intuit_tid, logs to QuickBooksAPILog).
"""

import logging
import secrets
from django.conf import settings

from fiscal.utils import redact_string_for_log
from django.utils import timezone
import requests

from quickbooks.client import QuickBooksClient
from quickbooks.models import QuickBooksToken
from quickbooks.utils import QuickBooksAPIException, QuickBooksTokenError, get_valid_token, refresh_quickbooks_token

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
                redact_string_for_log(body or ""),
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
                    redact_string_for_log((response.text or "")[:300]),
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


# ---------------------------------------------------------------------------
# Invoice query (pull)
# ---------------------------------------------------------------------------


def query_invoice(realm_id, user=None, max_results=20):
    """
    Query QuickBooks for invoices via QuickBooksClient.
    Returns (invoices_list, intuit_tid). intuit_tid may be None if header missing.
    """
    client = QuickBooksClient(realm_id, user=user)
    data, intuit_tid = client.get(
        "query",
        params={"query": f"SELECT * FROM Invoice MAXRESULTS {max_results}"},
        endpoint_label="query?query=SELECT * FROM Invoice",
    )
    query_response = data.get("QueryResponse", {}) if data else {}
    invoices = query_response.get("Invoice", [])
    if not isinstance(invoices, list):
        invoices = [invoices] if invoices else []
    return invoices, intuit_tid


def pull_invoices(realm_id, user=None, max_results=20):
    """
    Query QuickBooks for invoices. Returns list of invoice dicts from QueryResponse.
    Uses QuickBooksClient; captures intuit_tid and logs to QuickBooksAPILog.
    """
    invoices, _ = query_invoice(realm_id, user=user, max_results=max_results)
    return invoices


# ---------------------------------------------------------------------------
# Invoice fetch (single by id)
# ---------------------------------------------------------------------------


def fetch_invoice(realm_id, invoice_id, entity_name="Invoice", user=None):
    """
    Fetch a single invoice or creditmemo by id via QuickBooksClient.
    Returns (payload_dict, intuit_tid). Raises QuickBooksAPIException on API error.
    """
    resource = "creditmemo" if entity_name == "CreditMemo" else "invoice"
    path = f"{resource}/{invoice_id}"
    client = QuickBooksClient(realm_id, user=user)
    data, intuit_tid = client.get(
        path,
        endpoint_label=path,
        qb_invoice_id=str(invoice_id),
    )
    entity_key = "CreditMemo" if entity_name == "CreditMemo" else "Invoice"
    payload = (data.get(entity_key) or data) if data else None
    return payload, intuit_tid


# ---------------------------------------------------------------------------
# Invoice push (update after fiscalisation)
# ---------------------------------------------------------------------------


def update_invoice(realm_id, invoice_id, sync_token, private_note=None, user=None):
    """
    Update a QuickBooks invoice (e.g. set PrivateNote after fiscalisation).
    Uses QuickBooksClient; captures intuit_tid and logs to QuickBooksAPILog.
    Returns (response_body, intuit_tid). intuit_tid may be None.
    """
    client = QuickBooksClient(realm_id, user=user)
    payload = {
        "Id": str(invoice_id),
        "SyncToken": str(sync_token),
    }
    if private_note is not None:
        payload["PrivateNote"] = private_note
    data, intuit_tid = client.post(
        "invoice?operation=update",
        json_payload=payload,
        endpoint_label="invoice?operation=update",
        qb_invoice_id=str(invoice_id),
    )
    return data, intuit_tid


def push_invoice_update(realm_id, invoice_id, sync_token, private_note=None, user=None):
    """
    Update a QuickBooks invoice (e.g. set PrivateNote after fiscalisation).
    Returns response body (for backward compatibility). intuit_tid stored in QuickBooksAPILog.
    """
    data, _ = update_invoice(
        realm_id=realm_id,
        invoice_id=invoice_id,
        sync_token=sync_token,
        private_note=private_note,
        user=user,
    )
    return data
