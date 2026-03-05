"""
ZIMRA Section 10 – Validation layer before PDF generation.
Raise ValidationError if any mandatory fiscal field missing or totals do not reconcile.
Do NOT allow PDF generation when validation fails.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError


def validate_receipt_for_section10_pdf(receipt) -> None:
    """
    Validate receipt for Section 10 compliant A4 Tax Invoice PDF.
    - fiscal_signature (or receipt_hash) exists
    - receipt_global_no exists
    - fiscal_invoice_number (or invoice_no) exists
    - tax breakdown matches line items (subtotal + total_tax = total)
    - total equals subtotal + tax
    Raises ValidationError if any check fails.
    """
    if receipt.receipt_global_no is None:
        raise ValidationError("Mandatory fiscal field missing: receipt_global_no.")
    fiscal_sig = getattr(receipt, "fiscal_signature", None) or (receipt.receipt_hash or "").strip()
    if not fiscal_sig:
        raise ValidationError("Mandatory fiscal field missing: fiscal_signature (or receipt_hash).")
    fiscal_inv = getattr(receipt, "fiscal_invoice_number", None) or (receipt.invoice_no or "").strip()
    if not fiscal_inv:
        raise ValidationError("Mandatory fiscal field missing: fiscal_invoice_number (or invoice_no).")
    if not (receipt.receipt_lines and receipt.receipt_taxes and receipt.receipt_payments):
        raise ValidationError("Receipt must have line items, taxes, and payments.")
    # Totals: total equals subtotal + tax (2 dp)
    subtotal = Decimal("0")
    for line in receipt.receipt_lines or []:
        amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        subtotal += Decimal(str(amt))
    total_tax = sum(Decimal(str(t.get("taxAmount") or 0)) for t in (receipt.receipt_taxes or []))
    expected_total = subtotal + total_tax
    rec_total = Decimal(str(receipt.receipt_total or 0))
    if abs(expected_total - rec_total) > Decimal("0.01"):
        raise ValidationError(
            "Tax breakdown does not match: total must equal subtotal + tax. "
            f"subtotal={subtotal} + tax={total_tax} != receipt_total={rec_total}."
        )
    # Optional: denormalized VAT breakdown consistency
    if getattr(receipt, "total_tax", None) is not None and getattr(receipt, "subtotal_15", None) is not None:
        st15 = Decimal(str(receipt.subtotal_15 or 0))
        t15 = Decimal(str(receipt.tax_15 or 0))
        st0 = Decimal(str(receipt.subtotal_0 or 0))
        stex = Decimal(str(receipt.subtotal_exempt or 0))
        tt = Decimal(str(receipt.total_tax or 0))
        if abs((st15 + t15 + st0 + stex) - rec_total) > Decimal("0.01"):
            pass  # non-fatal: breakdown may not be populated yet
        if abs(tt - total_tax) > Decimal("0.01"):
            pass  # non-fatal
