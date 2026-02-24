"""
Credit note creation service. Reuses submit_receipt and existing QR/PDF.
Uses credit_allocation_service for proportional VAT allocation.
FDMS payload built via fdms_creditnote_builder (correct signs, referencedReceipt, reason).
"""

from decimal import Decimal

from django.db import transaction

from fiscal.models import Receipt
from fiscal.services.credit_allocation_service import (
    allocate_credit_proportionally,
    CreditAllocationError,
    validate_credit_amount,
)
from fiscal.services.fdms_creditnote_builder import build_creditnote_payload
from fiscal.services.invoice_number import get_next_credit_note_no
from fiscal.services.receipt_service import submit_receipt


def _validate_original_for_credit_note(original: Receipt) -> str | None:
    if not original:
        return "Original invoice is required."
    if not original.is_fiscalised:
        return "Original invoice must be fiscalised."
    doc_type = getattr(original, "document_type", "INVOICE")
    if doc_type not in ("INVOICE", ""):
        return "Credit note cannot reference another credit or debit note."
    if original.receipt_type == "CreditNote":
        return "Credit note cannot reference a credit note."
    if original.credit_status == "FULLY_CREDITED":
        return "Cannot credit a fully credited invoice."
    return None


def create_credit_note(
    original_receipt: Receipt,
    credit_lines: list[dict],
    credit_total: Decimal | float,
    reason: str,
    customer_snapshot: dict | None = None,
    refund_method: str = "CASH",
    debug_capture: dict | None = None,
) -> tuple[Receipt | None, str | None]:
    """
    Create and submit a credit note to FDMS. Uses proportional allocation.
    credit_lines ignored for allocation; only credit_total used.
    Returns (Receipt, None) or (None, error_message).
    """
    err = _validate_original_for_credit_note(original_receipt)
    if err:
        return None, err

    total_dec = Decimal(str(credit_total))
    try:
        validate_credit_amount(original_receipt, total_dec)
    except CreditAllocationError as e:
        return None, str(e)

    device = original_receipt.device
    if device.fiscal_day_status not in ("FiscalDayOpened", "FiscalDayCloseFailed"):
        return None, "Fiscal day must be open to issue credit notes."
    fiscal_day_no = device.last_fiscal_day_no
    if fiscal_day_no is None:
        return None, "No fiscal day open."

    allocation = allocate_credit_proportionally(original_receipt, total_dec)
    credit_note_data = {
        "receipt_lines": allocation["receipt_lines"],
        "receipt_taxes": allocation["receipt_taxes"],
        "credit_total": allocation["credit_total"],
        "reason": reason,
        "refund_method": refund_method,
    }
    payload = build_creditnote_payload(device, credit_note_data, original_receipt)
    invoice_no = get_next_credit_note_no()

    receipt_obj, err = submit_receipt(
        device=device,
        fiscal_day_no=int(fiscal_day_no),
        receipt_type="CreditNote",
        receipt_currency=original_receipt.currency or "USD",
        invoice_no=invoice_no[:50],
        receipt_lines=payload["receipt_lines"],
        receipt_taxes=payload["receipt_taxes"],
        receipt_payments=payload["receipt_payments"],
        receipt_total=payload["receipt_total"],
        receipt_lines_tax_inclusive=True,
        original_invoice_no=original_receipt.invoice_no or "",
        original_receipt_global_no=original_receipt.receipt_global_no,
        customer_snapshot=customer_snapshot or {},
        tax_from_request_only=True,
        use_preallocated_credit_taxes=True,
        debug_capture=debug_capture,
        referenced_receipt=payload["credit_debit_note"],
        receipt_notes=payload["receipt_notes"],
    )
    if err:
        return None, err

    with transaction.atomic():
        receipt_obj.document_type = "CREDIT_NOTE"
        receipt_obj.original_invoice = original_receipt
        receipt_obj.reason = (reason or "").strip()
        receipt_obj.save(update_fields=["document_type", "original_invoice", "reason"])
        from fiscal.services.invoice_credit_service import update_invoice_credit_status
        update_invoice_credit_status(original_receipt)

    return receipt_obj, None
