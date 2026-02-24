"""
Invoice credit tracking. Immutable invoice, status updates, validation.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError

from fiscal.models import Receipt

TOLERANCE = Decimal("0.01")


def update_invoice_credit_status(invoice: Receipt) -> None:
    if invoice.document_type not in ("INVOICE", "") or invoice.receipt_type in ("CreditNote", "CREDITNOTE"):
        return
    credited = invoice.credited_total
    total = invoice.receipt_total or Decimal("0")
    if credited <= 0:
        invoice.credit_status = "ISSUED"
    elif credited >= total - TOLERANCE:
        invoice.credit_status = "FULLY_CREDITED"
    else:
        invoice.credit_status = "PARTIALLY_CREDITED"
    invoice.save(update_fields=["credit_status"])


def validate_credit_against_invoice(invoice: Receipt, credit_total: Decimal) -> None:
    if not invoice:
        raise ValidationError("Original invoice is required.")
    if invoice.receipt_type in ("CreditNote", "CREDITNOTE"):
        raise ValidationError("Cannot credit a credit note.")
    if invoice.document_type not in ("INVOICE", ""):
        raise ValidationError("Cannot credit a credit or debit note.")
    if invoice.credit_status == "FULLY_CREDITED":
        raise ValidationError("Cannot credit a fully credited invoice.")
    if credit_total <= 0:
        raise ValidationError("Credit total must be positive.")
    remaining = invoice.remaining_balance
    if credit_total > remaining + TOLERANCE:
        raise ValidationError(
            f"Credit total {credit_total} exceeds remaining invoice balance {remaining}."
        )
