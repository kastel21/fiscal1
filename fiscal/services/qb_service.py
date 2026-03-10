"""
QuickBooks webhook + API service layer.
Verify webhook signature, fetch invoice/creditmemo from QB API, create local Receipt (PENDING), queue fiscalisation.
No fiscalisation logic here; only webhook handling + QB fetch + receipt creation + task queue.
"""

import base64
import hmac
import hashlib
import logging
from decimal import Decimal

from django.conf import settings
import requests

from fiscal.models import FiscalDevice, Receipt

logger = logging.getLogger("fiscal")

QB_API_BASE = "https://quickbooks.api.intuit.com/v3/company"


def verify_qb_webhook_signature(body: bytes, signature_header: str) -> bool:
    """
    Verify QuickBooks webhook signature using HMAC SHA256.
    Header: intuit-signature
    Compute: base64(HMAC_SHA256(request.body, QB_WEBHOOK_VERIFIER))
    Returns True if valid.
    """
    verifier = getattr(settings, "QB_WEBHOOK_VERIFIER", None) or ""
    if not verifier or not signature_header:
        return False
    expected = base64.b64encode(
        hmac.new(
            verifier.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    return hmac.compare_digest(signature_header.strip(), expected)


def _log_qb_api_call(realm_id: str, endpoint: str, method: str, status_code: int, intuit_tid: str | None, request_body=None, response_body=None, qb_invoice_id: str | None = None):
    """Create QuickBooksAPILog entry (fiscal app has no QuickBooksToken; use quickbooks app log model)."""
    try:
        from quickbooks.models import QuickBooksAPILog
        QuickBooksAPILog.objects.create(
            realm_id=realm_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            intuit_tid=intuit_tid,
            request_body=request_body,
            response_body=response_body,
            qb_invoice_id=qb_invoice_id,
        )
    except Exception as e:
        logger.warning("QuickBooksAPILog create failed: %s", e)


def fetch_invoice_from_qb(invoice_id: str, realm_id: str, entity_name: str = "Invoice") -> dict | None:
    """
    Fetch full invoice or creditmemo from QuickBooks API.
    Tenant-scoped: uses QuickBooksConnection for realm_id (no global QB_ACCESS_TOKEN).
    Returns parsed payload or None on failure.
    """
    if not realm_id or not invoice_id:
        return None

    from fiscal.models import QuickBooksConnection
    from fiscal.services.key_storage import decrypt_string
    from fiscal.services.qb_oauth import refresh_tokens
    from django.utils import timezone

    conn = QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).first()
    if not conn or not conn.access_token_encrypted:
        logger.warning("No QuickBooks connection for realm_id=%s", realm_id)
        return None
    if conn.token_expires_at and conn.token_expires_at <= timezone.now():
        ok, err = refresh_tokens(conn)
        if not ok:
            logger.warning("QB token refresh failed for realm %s: %s", realm_id, err)
            return None
        conn.refresh_from_db()
    try:
        token = decrypt_string(conn.access_token_encrypted)
    except Exception as e:
        logger.warning("QB token decrypt failed: %s", e)
        return None

    resource = "creditmemo" if entity_name == "CreditMemo" else "invoice"
    url = f"{QB_API_BASE}/{realm_id}/{resource}/{invoice_id}"
    endpoint = f"{resource}/{invoice_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        intuit_tid = resp.headers.get("intuit_tid") if resp.headers else None
        status_code = resp.status_code

        logger.info(
            "QuickBooks API Call",
            extra={
                "realm_id": realm_id,
                "endpoint": endpoint,
                "method": "GET",
                "status_code": status_code,
                "intuit_tid": intuit_tid,
            },
        )

        try:
            response_body = resp.json() if resp.text else None
        except (ValueError, TypeError):
            response_body = {"_raw": (resp.text[:5000] if resp.text else None)}
        _log_qb_api_call(realm_id=realm_id, endpoint=endpoint, method="GET", status_code=status_code, intuit_tid=intuit_tid, response_body=response_body, qb_invoice_id=invoice_id)

        resp.raise_for_status()
        data = resp.json()
        entity_key = "CreditMemo" if entity_name == "CreditMemo" else "Invoice"
        return data.get(entity_key) or data
    except requests.RequestException as e:
        logger.exception("QB API fetch failed: %s", e)
        return None
    except (ValueError, KeyError) as e:
        logger.exception("QB API response parse error: %s", e)
        return None


def handle_qb_event(entity_name: str, entity_id: str, realm_id: str) -> None:
    """
    Handle a single QB webhook event (Invoice or CreditMemo Create).
    Resolves tenant from QuickBooksConnection(realm_id); uses that tenant's device.
    - Idempotent by qb_id: if Receipt with qb_id=entity_id exists, return.
    - Fetch full invoice/creditmemo from QB API.
    - Create local Receipt: qb_id, receipt_type, currency, receipt_total, status=PENDING.
    - Queue Celery task fiscalise_receipt_task.delay(receipt.id).
    Does NOT perform fiscalisation; returns quickly.
    """
    if entity_name not in ("Invoice", "CreditMemo"):
        return
    if not entity_id or not realm_id:
        return

    from fiscal.models import QuickBooksConnection

    conn = QuickBooksConnection.objects.filter(realm_id=realm_id, is_active=True).select_related("tenant").first()
    if not conn or not conn.tenant_id:
        logger.warning("No tenant for QuickBooks realm_id=%s; skipping webhook", realm_id)
        return
    tenant = conn.tenant

    if Receipt.objects.filter(qb_id=entity_id).exists():
        return  # idempotency

    payload = fetch_invoice_from_qb(entity_id, realm_id, entity_name)
    if not payload:
        logger.warning("Could not fetch QB %s %s; skipping receipt creation", entity_name, entity_id)
        return

    # Extract currency and total from QB payload
    curr_ref = payload.get("CurrencyRef") or {}
    receipt_currency = "USD"
    if isinstance(curr_ref, dict) and curr_ref.get("value"):
        receipt_currency = str(curr_ref.get("value", "USD"))[:10]
    elif isinstance(curr_ref, str):
        receipt_currency = str(curr_ref)[:10]

    total = payload.get("TotalAmt") or payload.get("total_amount") or 0
    try:
        receipt_total = Decimal(str(total))
    except (TypeError, ValueError):
        receipt_total = Decimal("0")

    receipt_type = "CREDITNOTE" if entity_name == "CreditMemo" else "FISCALINVOICE"

    device = FiscalDevice.objects.filter(tenant=tenant, is_registered=True).first()
    if not device:
        logger.warning("No registered fiscal device for tenant %s; cannot create Receipt for qb_id=%s", tenant.slug, entity_id)
        return

    receipt = Receipt.objects.create(
        device=device,
        fiscal_day_no=None,
        receipt_global_no=None,
        qb_id=entity_id,
        receipt_type=receipt_type,
        currency=receipt_currency,
        receipt_total=receipt_total,
        fiscal_status="PENDING",
        document_type="CREDIT_NOTE" if entity_name == "CreditMemo" else "INVOICE",
    )
    from fiscal.tasks import fiscalise_receipt_task
    fiscalise_receipt_task.delay(receipt.id)
    logger.info("Created Receipt id=%s qb_id=%s type=%s status=PENDING; queued fiscalisation", receipt.id, entity_id, receipt_type)
