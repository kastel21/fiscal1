"""
QuickBooks API client. Fetch Invoices and SalesReceipts.
"""

import logging

from fiscal.models import QuickBooksConnection
from fiscal.services.key_storage import decrypt_string
from fiscal.services.qb_oauth import get_qb_credentials, refresh_tokens

logger = logging.getLogger("fiscal")


def get_quickbooks_client(conn=None):
    """Return python-quickbooks QuickBooks client or None."""
    try:
        from quickbooks import QuickBooks
    except ImportError:
        logger.warning("python-quickbooks not installed")
        return None

    client_id, client_secret = get_qb_credentials()
    if not client_id or not client_secret:
        return None

    conn = conn or QuickBooksConnection.objects.filter(is_active=True).first()
    if not conn or not conn.access_token_encrypted:
        return None

    from django.utils import timezone
    if conn.token_expires_at and conn.token_expires_at <= timezone.now():
        ok, err = refresh_tokens(conn)
        if not ok:
            logger.warning("QB token refresh failed: %s", err)
            return None

    try:
        access = decrypt_string(conn.access_token_encrypted)
        refresh = decrypt_string(conn.refresh_token_encrypted)
    except Exception as e:
        logger.warning("QB token decrypt failed: %s", e)
        return None

    return QuickBooks(
        sandbox=False,
        consumer_key=client_id,
        consumer_secret=client_secret,
        access_token=access,
        access_token_secret=refresh,
        company_id=conn.realm_id,
    )


def _obj_to_dict(obj):
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        d = obj.to_dict()
        return d if isinstance(d, dict) else {}
    return {}


def _extract_ref(ref):
    if isinstance(ref, dict):
        return ref
    if hasattr(ref, "value"):
        return {"value": ref.value}
    return {}


def fetch_invoices(qb, max_results=50):
    """Fetch Invoices from QuickBooks. Filters to Balance=0 (paid) in Python if query fails."""
    try:
        from quickbooks.objects.invoice import Invoice
        try:
            invoices = Invoice.query(
                "SELECT * FROM Invoice WHERE Balance = '0' MAXRESULTS {}".format(max_results),
                qb=qb,
            )
        except Exception:
            invoices = Invoice.all(qb=qb, max_results=max_results)
            invoices = [i for i in (invoices or []) if getattr(i, "Balance", "0") == "0" or float(getattr(i, "Balance", 0) or 0) == 0]
        return [_obj_to_dict(inv) for inv in (invoices or [])]
    except Exception as e:
        logger.exception("QB fetch invoices failed: %s", e)
        return []


def fetch_sales_receipts(qb, max_results=50):
    """Fetch SalesReceipts from QuickBooks."""
    try:
        from quickbooks.objects.salesreceipt import SalesReceipt
        receipts = SalesReceipt.all(qb=qb, max_results=max_results)
        return [_obj_to_dict(r) for r in (receipts or [])]
    except Exception as e:
        logger.exception("QB fetch sales receipts failed: %s", e)
        return []


def qb_sale_to_invoice_payload(sale):
    """Normalize QB Invoice or SalesReceipt for map_qb_invoice_to_fdms."""
    if not sale:
        return {}
    lines = sale.get("Line") or sale.get("LineItem") or []
    line_items = [ln if isinstance(ln, dict) else (ln.to_dict() if hasattr(ln, "to_dict") else {}) for ln in lines]
    return {
        "Id": sale.get("Id"),
        "Line": line_items,
        "TotalAmt": sale.get("TotalAmt"),
        "CurrencyRef": sale.get("CurrencyRef", {}),
        "CustomerRef": sale.get("CustomerRef", {}),
        "TxnDate": sale.get("TxnDate"),
    }
