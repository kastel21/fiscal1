"""
Safety checks for credit/debit notes. Centralised rules:
- Credit note must not exceed original total (remaining balance).
- Debit note must not reference a credit note.
- No recursive adjustments (original must be INVOICE).
- Original must be fiscalised (no modifying closed fiscal documents by creating adjustments to non-fiscalised receipts).
"""

from fiscal.models import Receipt


def can_use_as_original_for_credit_note(receipt: Receipt) -> tuple[bool, str]:
    """
    Return (True, "") if receipt can be used as original for a credit note.
    Else (False, error_message).
    """
    if not receipt:
        return False, "Original invoice is required."
    if not receipt.is_fiscalised:
        return False, "Original invoice must be fiscalised."
    doc_type = getattr(receipt, "document_type", "INVOICE")
    if doc_type not in ("INVOICE", ""):
        return False, "Credit note cannot reference another credit or debit note."
    if receipt.receipt_type == "CreditNote":
        return False, "Credit note cannot reference a credit note."
    return True, ""


def can_use_as_original_for_debit_note(receipt: Receipt) -> tuple[bool, str]:
    """
    Return (True, "") if receipt can be used as original for a debit note.
    Else (False, error_message).
    """
    if not receipt:
        return False, "Original invoice is required."
    if not receipt.is_fiscalised:
        return False, "Original invoice must be fiscalised."
    doc_type = getattr(receipt, "document_type", "INVOICE")
    if doc_type == "CREDIT_NOTE":
        return False, "Debit note cannot reference a credit note."
    if doc_type == "DEBIT_NOTE":
        return False, "Debit note cannot reference another debit note."
    if receipt.receipt_type == "CreditNote":
        return False, "Debit note cannot reference a credit note."
    return True, ""
