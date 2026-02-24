"""
Production-safe credit allocation engine for FDMS.
Proportional allocation, multi-tax support, no VAT recalculation.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import Q

from fiscal.models import Receipt
from fiscal.services.tax_calculator import extract_net_from_inclusive, extract_tax_from_inclusive


def safe_quantize(value: Decimal | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def get_remaining_balance(invoice: Receipt) -> Decimal:
    total = invoice.receipt_total or Decimal("0")
    credits = Receipt.objects.filter(
        device=invoice.device,
        original_receipt_global_no=invoice.receipt_global_no,
    ).filter(
        Q(receipt_type="CreditNote") | Q(receipt_type="CREDITNOTE")
    ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0)
    for r in credits:
        amt = r.receipt_total or Decimal("0")
        total += amt
    return total


class CreditAllocationError(Exception):
    pass


def validate_credit_amount(invoice: Receipt, credit_total: Decimal) -> None:
    from fiscal.services.invoice_credit_service import validate_credit_against_invoice
    try:
        validate_credit_against_invoice(invoice, credit_total)
    except ValidationError as e:
        raise CreditAllocationError(str(e))


def _to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _normalize_tax_amounts(receipt_taxes: list[dict], invoice_total: Decimal) -> list[dict]:
    out = []
    for t in receipt_taxes or []:
        sales = _to_decimal(t.get("salesAmountWithTax") or t.get("fiscalCounterValue") or 0)
        tax_amt = _to_decimal(t.get("taxAmount") or 0)
        if sales == 0 and tax_amt == 0:
            continue
        if sales < 0:
            sales = -sales
        if tax_amt < 0:
            tax_amt = -tax_amt
        out.append({
            "taxID": t.get("taxID"),
            "taxCode": (str(t.get("taxCode") or "")[:20]) or "VAT",
            "taxPercent": t.get("taxPercent") or t.get("fiscalCounterTaxPercent") or Decimal("0"),
            "salesAmountWithTax": sales,
            "taxAmount": tax_amt,
        })
    if out:
        total_from_taxes = sum(x["salesAmountWithTax"] for x in out)
        if invoice_total and total_from_taxes > invoice_total * 10:
            for x in out:
                x["salesAmountWithTax"] = safe_quantize(x["salesAmountWithTax"] / 100)
                x["taxAmount"] = safe_quantize(x["taxAmount"] / 100)
    return out


def allocate_credit_proportionally(
    invoice: Receipt,
    credit_total: Decimal | float,
) -> dict:
    credit_total = Decimal(str(credit_total))
    validate_credit_amount(invoice, credit_total)

    invoice_total = _to_decimal(invoice.receipt_total or 0)
    if invoice_total <= 0:
        raise CreditAllocationError("Invoice total must be positive.")

    taxes = _normalize_tax_amounts(invoice.receipt_taxes or [], invoice_total)
    if not taxes:
        taxes = [{
            "taxID": 1,
            "taxCode": "VAT",
            "taxPercent": Decimal("0"),
            "salesAmountWithTax": invoice_total,
            "taxAmount": Decimal("0"),
        }]

    ratio = credit_total / invoice_total
    allocations = []
    for t in taxes:
        orig_sales = t["salesAmountWithTax"]
        tax_pct = _to_decimal(t.get("taxPercent") or 0)
        allocated_sales = safe_quantize(orig_sales * ratio)
        if tax_pct > 0:
            tax_pos = extract_tax_from_inclusive(allocated_sales, tax_pct)
            net_pos = extract_net_from_inclusive(allocated_sales, tax_pct)
            if net_pos + tax_pos != allocated_sales:
                tax_pos = (allocated_sales - net_pos).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            allocated_tax = tax_pos
        else:
            allocated_tax = Decimal("0")
        allocations.append({
            "taxID": t["taxID"],
            "taxCode": t["taxCode"],
            "taxPercent": float(t["taxPercent"]) if t["taxPercent"] is not None else 0,
            "salesAmountWithTax": allocated_sales,
            "taxAmount": allocated_tax,
        })

    sum_allocated = sum(a["salesAmountWithTax"] for a in allocations)
    difference = credit_total - sum_allocated
    if difference != 0 and allocations:
        last = allocations[-1]
        last["salesAmountWithTax"] = safe_quantize(
            last["salesAmountWithTax"] + difference
        )
        tax_pct = _to_decimal(last.get("taxPercent") or 0)
        if tax_pct > 0:
            tax_pos = extract_tax_from_inclusive(last["salesAmountWithTax"], tax_pct)
            net_pos = extract_net_from_inclusive(last["salesAmountWithTax"], tax_pct)
            if net_pos + tax_pos != last["salesAmountWithTax"]:
                tax_pos = (last["salesAmountWithTax"] - net_pos).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            last["taxAmount"] = tax_pos
        else:
            last["taxAmount"] = Decimal("0")

    receipt_lines = []
    for i, a in enumerate(allocations):
        receipt_lines.append({
            "receiptLineNo": i + 1,
            "receiptLineQuantity": 1,
            "receiptLineTotal": float(a["salesAmountWithTax"]),
            "receiptLineName": f"Credit allocation ({a['taxCode']})",
            "receiptLineHSCode": "0000",
            "taxID": a["taxID"],
            "taxCode": a["taxCode"],
            "taxPercent": a["taxPercent"],
        })

    receipt_taxes = []
    for a in allocations:
        receipt_taxes.append({
            "taxID": a["taxID"],
            "taxCode": a["taxCode"],
            "taxPercent": a["taxPercent"],
            "taxAmount": float(a["taxAmount"]),
            "salesAmountWithTax": float(a["salesAmountWithTax"]),
        })

    return {
        "receipt_lines": receipt_lines,
        "receipt_taxes": receipt_taxes,
        "credit_total": float(credit_total),
    }
