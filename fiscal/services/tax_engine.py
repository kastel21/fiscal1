"""
FDMS-compliant tax calculation engine.
Aggregate first, calculate tax once per tax group, round once at final stage.
Guarantees receiptTotal = SUM(salesAmountWithTax). Avoids RCPT026/RCPT027.
"""

from decimal import Decimal, ROUND_HALF_UP


def money(value) -> Decimal:
    """Round monetary value to 2 decimals (ROUND_HALF_UP)."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_receipt_totals(receipt_lines: list[dict], tax_inclusive: bool) -> tuple[list[dict], float]:
    """
    Fully FDMS-compliant tax calculation.
    Works for Invoice, CreditNote, DebitNote (negative amounts pass through).
    - Groups by (taxID, taxCode, taxPercent).
    - Aggregates line totals per group (no rounding).
    - Computes tax once per group, rounds once.
    - receiptTotal = SUM(salesAmountWithTax).
    Returns (receipt_taxes, receipt_total) in currency units (not cents).
    """
    tax_groups = {}

    for line in receipt_lines:
        tax_id = line.get("taxID")
        tax_code = line.get("taxCode") or str(tax_id or "")
        raw_pct = line.get("taxPercent")
        tax_percent = Decimal(str(raw_pct)) if raw_pct is not None and "taxPercent" in line else None

        key = (tax_id, tax_code, tax_percent)
        line_total = Decimal(str(line.get("receiptLineTotal") or line.get("lineAmount") or line.get("amount") or 0))

        if key not in tax_groups:
            tax_groups[key] = Decimal("0.00")
        tax_groups[key] += line_total

    receipt_taxes = []
    receipt_total = Decimal("0.00")

    for (tax_id, tax_code, tax_percent), group_sum in sorted(
        tax_groups.items(), key=lambda x: (x[0][0] if x[0][0] is not None else 0, x[0][1] or "", x[0][2] if x[0][2] is not None else -1)
    ):
        group_sum = money(group_sum)

        if tax_percent is None:
            tax_amount = Decimal("0.00")
            sales_with_tax = group_sum
        else:
            percent = Decimal(str(tax_percent)) / Decimal("100")
            if tax_inclusive:
                tax_amount = money(group_sum * percent / (1 + percent))
                sales_with_tax = group_sum
            else:
                tax_amount = money(group_sum * percent)
                sales_with_tax = money(group_sum * (1 + percent))

        receipt_total += sales_with_tax

        tax_entry = {
            "taxID": tax_id,
            "taxCode": tax_code,
            "taxAmount": float(tax_amount),
            "salesAmountWithTax": float(sales_with_tax),
        }
        if tax_percent is not None:
            tax_entry["taxPercent"] = float(tax_percent)
        receipt_taxes.append(tax_entry)

    receipt_total = money(receipt_total)
    return receipt_taxes, float(receipt_total)
