"""
Fiscalisation entry point for async tasks (e.g. QB webhook-created receipts).
Calls existing fiscal logic; does not implement new fiscal rules.
"""

import logging
from django.conf import settings

from fiscal.models import Receipt
from fiscal.services.qb_service import fetch_invoice_from_qb

logger = logging.getLogger("fiscal")


def fiscalise_receipt(receipt_id: int) -> None:
    """
    Fiscalise a receipt by id (e.g. PENDING receipt created from QB webhook).
    Fetches full invoice from QB API if needed, then delegates to existing
    fiscalise_qb_invoice. Does not implement fiscal logic; only wires task to existing flow.
    """
    try:
        receipt = Receipt.objects.filter(pk=receipt_id).first()
    except Exception:
        receipt = None
    if not receipt or not getattr(receipt, "qb_id", None):
        return
    if getattr(receipt, "fiscal_status", None) and receipt.fiscal_status != "PENDING":
        return

    realm_id = getattr(settings, "QB_REALM_ID", "") or ""
    entity_name = "CreditMemo" if (receipt.receipt_type or "").strip().upper() == "CREDITNOTE" else "Invoice"
    payload = fetch_invoice_from_qb(receipt.qb_id, realm_id, entity_name)
    if not payload:
        receipt.fiscal_status = "FAILED"
        receipt.save(update_fields=["fiscal_status"])
        logger.warning("fiscalise_receipt: could not fetch QB %s %s", entity_name, receipt.qb_id)
        return

    if entity_name == "CreditMemo":
        # No fiscalisation logic for CreditMemo implemented here; leave PENDING or mark FAILED.
        receipt.fiscal_status = "FAILED"
        receipt.save(update_fields=["fiscal_status"])
        logger.info("fiscalise_receipt: CreditMemo %s not fiscalised (no logic)", receipt.qb_id)
        return

    from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice
    qb_inv, err = fiscalise_qb_invoice(receipt.qb_id, payload)
    if qb_inv and qb_inv.fiscalised:
        receipt.fiscal_status = "FISCALISED"
        receipt.save(update_fields=["fiscal_status"])
        logger.info("fiscalise_receipt: receipt id=%s qb_id=%s fiscalised", receipt_id, receipt.qb_id)
    else:
        receipt.fiscal_status = "FAILED"
        receipt.save(update_fields=["fiscal_status"])
        logger.warning("fiscalise_receipt: receipt id=%s qb_id=%s failed: %s", receipt_id, receipt.qb_id, err or qb_inv.fiscal_error if qb_inv else "unknown")
