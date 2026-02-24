"""
Debit note validation. Prevents RCPT015, RCPT029, RCPT032, RCPT033, RCPT036, RCPT042.
"""

from decimal import Decimal

from fiscal.models import Receipt


def validate_debit_note(
    original_receipt: Receipt,
    debit_total: Decimal | float,
    tax_ids: list[int],
    currency: str,
) -> None:
    """
    Validate debit note preconditions. Raises ValueError on failure.
    RCPT015: missing reference, RCPT029: wrong reference type,
    RCPT032: invoice not found, RCPT033: older than 12 months,
    RCPT036: new tax IDs, RCPT042: currency mismatch.
    """
    if not original_receipt:
        raise ValueError("Debit note can only reference a fiscal invoice.")
    rt = (original_receipt.receipt_type or "").strip().upper()
    if rt != "FISCALINVOICE":
        raise ValueError("Debit note can only reference a fiscal invoice.")
    doc_type = getattr(original_receipt, "document_type", "INVOICE")
    if doc_type not in ("INVOICE", ""):
        raise ValueError("Debit note can only reference a fiscal invoice.")
    receipt_currency = original_receipt.currency or "USD"
    if receipt_currency.upper() != (currency or "USD").upper():
        raise ValueError("Currency must match original invoice.")
    total = Decimal(str(debit_total))
    if total <= 0:
        raise ValueError("Debit total must be positive.")
    if original_receipt.is_older_than_12_months():
        raise ValueError("Cannot debit invoice older than 12 months.")
    original_tax_ids = set(original_receipt.get_tax_ids())
    debit_tax_ids = set(int(t) for t in tax_ids if t is not None)
    if debit_tax_ids and not debit_tax_ids.issubset(original_tax_ids):
        raise ValueError("Debit note cannot introduce new tax IDs.")
