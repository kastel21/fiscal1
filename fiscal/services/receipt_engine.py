"""
Receipt Engine for SubmitReceipt (FDMS v7.2).
Canonical builder, signature, and receipt chain.

Tax canonical segment (FDMS spec, avoids RCPT020):
- Exempt (taxPercent None or missing): segment = taxCode + taxAmount + salesAmountWithTax (no taxPercent).
- Zero rated or standard VAT: segment = taxCode + taxPercent + taxAmount + salesAmountWithTax.

Example canonical segments:
- Exempt line:  taxCode="EX", taxAmount=0, salesAmountWithTax=100  -> "EX010000" (no "0.00").
- Zero rated:   taxCode="EX", taxPercent=0, taxAmount=0, sales=100  -> "EX0.00010000".
- 15.5% VAT:   taxCode="VAT", taxPercent=15.5, taxAmount=155, sales=1155 -> "VAT15.501551155".
"""

import base64
import hashlib
import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fiscal.services.signature_engine import SignatureEngine

logger = logging.getLogger("fiscal")


def _to_cents(value) -> int:
    """Convert monetary value to cents (integer)."""
    return int(
        (Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100)
        .to_integral_value()
    )


def _format_money(value) -> str:
    """Format monetary value for canonical: remove decimal point. e.g. 1.40 -> '140', 10.40 -> '1040'."""
    return str(_to_cents(value))


def _format_percent(value) -> str:
    """Format tax percent for canonical: keep decimal point, two decimals. e.g. 15.5 -> '15.50'."""
    return f"{float(Decimal(str(value)).quantize(Decimal('0.00'), ROUND_HALF_UP)):.2f}"


def _build_tax_canonical_segment(tax_entry: dict, is_credit_note: bool) -> str:
    """
    Build tax segment for receipt canonical. FDMS rule (avoids RCPT020):
    - Exempt → taxPercent must NOT exist in canonical (strict key check).
    - Zero-rated (0.00%) or standard VAT → taxPercent MUST be included.
    """
    tax_code = str(tax_entry.get("taxCode", "") or "").upper()
    tax_amount = _format_money(tax_entry.get("taxAmount", 0))
    sales_with_tax = _format_money(tax_entry.get("salesAmountWithTax", 0))
    if is_credit_note:
        tax_amount_int = int(tax_amount) if tax_amount.lstrip("-").isdigit() else 0
        sales_int = int(sales_with_tax) if sales_with_tax.lstrip("-").isdigit() else 0
        if tax_amount_int > 0:
            tax_amount = str(-abs(tax_amount_int))
        if sales_int > 0:
            sales_with_tax = str(-abs(sales_int))

    # STRICT: never use .get("taxPercent", 0) — Exempt must not be treated as 0.00%
    has_percent = "taxPercent" in tax_entry and tax_entry["taxPercent"] is not None
    if not has_percent:
        return f"{tax_code}{tax_amount}{sales_with_tax}"
    percent_str = _format_percent(tax_entry["taxPercent"])
    return f"{tax_code}{percent_str}{tax_amount}{sales_with_tax}"


def build_receipt_canonical_string(
    device_id: int,
    receipt_type: str,
    receipt_currency: str,
    receipt_global_no: int,
    receipt_date: str,
    receipt_total: Decimal,
    receipt_tax_lines: list[dict],
    previous_receipt_hash: str | None,
) -> str:
    is_credit_note = (receipt_type or "").strip().upper() in ("CREDITNOTE",)
    receipt_total_cents = _to_cents(receipt_total)
    if is_credit_note and receipt_total_cents > 0:
        receipt_total_cents = -abs(receipt_total_cents)

    canonical = (
        str(device_id)
        + receipt_type.upper()
        + receipt_currency.upper()
        + str(receipt_global_no)
        + receipt_date
        + str(receipt_total_cents)
    )

    def tax_sort_key(t: dict) -> tuple:
        return (
            int(t.get("taxID", 0)),
            str(t.get("taxCode", "") or "").upper(),
        )

    sorted_taxes = sorted(receipt_tax_lines or [], key=tax_sort_key)

    for tax in sorted_taxes:
        logger.debug("DEBUG TAX: %s", tax)
        logger.debug("Has taxPercent key? %s", "taxPercent" in tax)
        canonical += _build_tax_canonical_segment(tax, is_credit_note)

    if previous_receipt_hash:
        canonical += previous_receipt_hash

    return canonical


def sign_receipt(
    device,
    canonical: str,
) -> dict:
    """
    Sign canonical string with device key.
    Returns {"hash": base64, "signature": base64}.
    """
    engine = SignatureEngine(
        certificate_pem=device.certificate_pem,
        private_key_pem=device.get_private_key_pem_decrypted(),
    )
    return engine.sign(canonical)
