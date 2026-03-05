"""
ZIMRA Section 10 – VAT engine: group line items by rate (15%, 0%, exempt) and compute breakdown.
All amounts use Decimal, rounded to 2 decimal places. Used after FDMS fiscalisation to populate
subtotal_15, tax_15, subtotal_0, subtotal_exempt, total_tax, and to validate grand_total.
"""

from decimal import Decimal, ROUND_HALF_UP

# Standard VAT rate (ZIMRA). 15.5% per local config; override via vat_rate_standard if needed.
VAT_RATE_STANDARD = Decimal("15.5")
VAT_RATE_ZERO = Decimal("0")


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _percent_to_decimal(percent: float | Decimal) -> Decimal:
    return Decimal(str(percent)) / Decimal("100")


def compute_vat_breakdown(
    receipt_lines: list[dict],
    receipt_taxes: list[dict],
    receipt_total: Decimal | float | None,
    vat_rate_standard: Decimal | None = None,
) -> dict:
    """
    Group line items by 15%, 0%, and exempt. Compute subtotal_15, tax_15, subtotal_0,
    subtotal_exempt, total_tax, grand_total. All monetary values Decimal, 2 dp.

    receipt_lines: list of dicts with receiptLineTotal, taxID / taxPercent (or from receipt_taxes).
    receipt_taxes: list of dicts with taxID, taxPercent, taxAmount, salesAmountWithTax (or taxable).
    receipt_total: expected grand total (for validation).

    Returns dict with keys: subtotal_15, tax_15, subtotal_0, subtotal_exempt, total_tax, grand_total.
    """
    rate_std = vat_rate_standard or VAT_RATE_STANDARD
    subtotal_15 = Decimal("0")
    subtotal_0 = Decimal("0")
    subtotal_exempt = Decimal("0")
    total_tax_calc = Decimal("0")

    # Build tax percent by line: use receipt_taxes to get taxID -> percent; then match lines by taxID
    tax_id_to_percent = {}
    for t in receipt_taxes or []:
        tid = t.get("taxID")
        if tid is not None:
            pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent") or 0
            tax_id_to_percent[int(tid)] = Decimal(str(pct))
        total_tax_calc += Decimal(str(t.get("taxAmount") or 0))

    # Sum line totals by band (15%, 0%, exempt). If receipt_lines have taxID, use that; else use first tax.
    for line in receipt_lines or []:
        amt = Decimal(str(line.get("receiptLineTotal") or line.get("lineAmount") or 0))
        tid = line.get("taxID")
        if tid is not None:
            pct = tax_id_to_percent.get(int(tid), Decimal("0"))
        else:
            pct = (receipt_taxes or [{}])[0].get("taxPercent") if receipt_taxes else Decimal("0")
            pct = Decimal(str(pct)) if pct is not None else Decimal("0")
        if pct >= rate_std - Decimal("0.6"):  # standard rate band (e.g. 15.5%)
            subtotal_15 += amt
        elif pct == VAT_RATE_ZERO:
            subtotal_0 += amt
        else:
            subtotal_exempt += amt

    tax_15 = _round2(subtotal_15 * _percent_to_decimal(rate_std))
    grand_total = _round2(subtotal_15 + tax_15 + subtotal_0 + subtotal_exempt)

    if receipt_total is not None:
        rec_total = _round2(Decimal(str(receipt_total)))
        if abs(grand_total - rec_total) > Decimal("0.01"):
            grand_total = rec_total
            total_tax_calc = rec_total - (subtotal_15 + subtotal_0 + subtotal_exempt)
            tax_15 = total_tax_calc

    total_tax = _round2(total_tax_calc)
    return {
        "subtotal_15": _round2(subtotal_15),
        "tax_15": _round2(tax_15),
        "subtotal_0": _round2(subtotal_0),
        "subtotal_exempt": _round2(subtotal_exempt),
        "total_tax": total_tax,
        "grand_total": grand_total,
    }
