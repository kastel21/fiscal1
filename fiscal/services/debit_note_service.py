"""
Debit note creation service. Uses fdms_debitnote_builder for correct payload.
submit_receipt with receipt_type DebitNote, referencedReceipt, creditDebitNoteReason.
Updates original invoice total_debited and credit_status after success.
"""

from decimal import Decimal

from django.db import transaction

from fiscal.models import Receipt
from fiscal.services.fdms_debitnote_builder import build_debitnote_payload
from fiscal.services.invoice_number import get_next_debit_note_no
from fiscal.services.receipt_service import submit_receipt


def _update_original_invoice_after_debit(original: Receipt, debit_total: Decimal) -> None:
    """Update original invoice total_debited and credit_status."""
    with transaction.atomic():
        original.refresh_from_db()
        new_debited = (original.total_debited or Decimal("0")) + debit_total
        original.total_debited = new_debited
        orig_total = original.original_total if original.original_total is not None else (original.receipt_total or Decimal("0"))
        credited = original.credited_total
        remaining = orig_total - credited + new_debited
        if remaining > orig_total + Decimal("0.01"):
            original.credit_status = "ADJUSTED_UP"
        elif credited == 0:
            original.credit_status = "ISSUED"
        else:
            original.credit_status = "PARTIALLY_CREDITED"
        original.save(update_fields=["total_debited", "credit_status"])


def create_debit_note(
    original_receipt: Receipt,
    debit_lines: list[dict],
    debit_total: Decimal | float,
    reason: str,
    customer_snapshot: dict | None = None,
) -> tuple[Receipt | None, str | None]:
    """
    Create and submit a debit note to FDMS.
    Returns (Receipt, None) or (None, error_message).
    """
    total_dec = Decimal(str(debit_total))
    if total_dec <= 0:
        return None, "Debit total must be positive."

    device = original_receipt.device
    if device.fiscal_day_status not in ("FiscalDayOpened", "FiscalDayCloseFailed"):
        return None, "Fiscal day must be open to issue debit notes."
    fiscal_day_no = device.last_fiscal_day_no
    if fiscal_day_no is None:
        return None, "No fiscal day open."

    debit_note_data = {
        "debit_lines": debit_lines,
        "debit_total": float(total_dec),
        "reason": reason,
    }
    try:
        payload = build_debitnote_payload(device, debit_note_data, original_receipt)
    except Exception as e:
        return None, str(e)

    invoice_no = get_next_debit_note_no()

    receipt_obj, err = submit_receipt(
        device=device,
        fiscal_day_no=int(fiscal_day_no),
        receipt_type="DebitNote",
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
        referenced_receipt=payload["credit_debit_note"],
        receipt_notes=payload["receipt_notes"],
    )
    if err:
        return None, err

    with transaction.atomic():
        receipt_obj.document_type = "DEBIT_NOTE"
        receipt_obj.original_invoice = original_receipt
        receipt_obj.reason = (reason or "").strip()
        receipt_obj.save(update_fields=["document_type", "original_invoice", "reason"])
        _update_original_invoice_after_debit(original_receipt, Decimal(str(payload["receipt_total"])))

    return receipt_obj, None
