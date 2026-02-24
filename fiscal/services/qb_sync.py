"""
QuickBooks sync: fetch sales from QB, fiscalise via FDMS.
"""

import logging

from fiscal.models import QuickBooksConnection, QuickBooksInvoice
from fiscal.services.qb_client import fetch_invoices, fetch_sales_receipts, get_quickbooks_client, qb_sale_to_invoice_payload
from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice

logger = logging.getLogger("fiscal")


def sync_from_quickbooks(conn: QuickBooksConnection | None = None, max_per_type: int = 50) -> dict:
    """
    Fetch Invoices and SalesReceipts from QB, fiscalise unfiscalised.
    Returns { "invoices_fetched", "sales_receipts_fetched", "fiscalised", "skipped", "errors" }.
    """
    qb = get_quickbooks_client(conn)
    if not qb:
        return {"error": "QuickBooks not connected", "fiscalised": 0, "skipped": 0, "errors": []}

    result = {"invoices_fetched": 0, "sales_receipts_fetched": 0, "fiscalised": 0, "skipped": 0, "errors": []}

    invoices = fetch_invoices(qb, max_results=max_per_type)
    result["invoices_fetched"] = len(invoices)

    sales = fetch_sales_receipts(qb, max_results=max_per_type)
    result["sales_receipts_fetched"] = len(sales)

    seen_ids = set()
    for inv in invoices + sales:
        inv_id = str(inv.get("Id", ""))
        if not inv_id or inv_id in seen_ids:
            continue
        seen_ids.add(inv_id)

        if QuickBooksInvoice.objects.filter(qb_invoice_id=inv_id, fiscalised=True).exists():
            result["skipped"] += 1
            continue

        payload = qb_sale_to_invoice_payload(inv)
        qb_inv, err = fiscalise_qb_invoice(inv_id, payload)
        if qb_inv and qb_inv.fiscalised:
            result["fiscalised"] += 1
        elif err:
            result["errors"].append(f"{inv_id}: {err}")

    return result
