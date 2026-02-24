"""
FDMS-compliant VAT extraction for tax-inclusive receipts.
RCPT026: tax = total × taxPercent / (100 + taxPercent)
"""

from decimal import Decimal, ROUND_HALF_UP


def extract_tax_from_inclusive(total: Decimal, tax_percent: Decimal) -> Decimal:
    """
    Extract VAT from tax-inclusive amount.
    Must match FDMS internal calculation.
    """
    if total == 0 or tax_percent == 0:
        return Decimal("0")
    tax = (
        total * tax_percent / (Decimal("100") + tax_percent)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return tax


def extract_net_from_inclusive(total: Decimal, tax_percent: Decimal) -> Decimal:
    tax = extract_tax_from_inclusive(total, tax_percent)
    net = (total - tax).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return net
