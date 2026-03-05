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


def _tax_map_from_invoice(invoice: Receipt) -> dict:
    """Build taxID -> {taxCode, taxPercent} from invoice.receipt_taxes. Used to copy tax to credit lines."""
    out = {}
    for t in invoice.receipt_taxes or []:
        tid = t.get("taxID") or t.get("fiscalCounterTaxID")
        if tid is not None:
            tid = int(tid)
            pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent")
            out[tid] = {
                "taxCode": str(t.get("taxCode") or "1")[:20],
                "taxPercent": float(pct) if pct is not None else 0.0,
            }
    if not out:
        out[1] = {"taxCode": "VAT", "taxPercent": 0.0}
    return out


def allocate_credit_proportionally(
    invoice: Receipt,
    credit_total: Decimal | float,
) -> dict:
    """
    Allocate credit total across lines using the SAME tax category and tax rate as each original invoice line.
    Each credit note line references the original invoice line (same index); taxID and taxPercent are copied
    from the original and must not be changed.
    """
    credit_total = Decimal(str(credit_total))
    validate_credit_amount(invoice, credit_total)

    invoice_total = _to_decimal(invoice.receipt_total or 0)
    if invoice_total <= 0:
        raise CreditAllocationError("Invoice total must be positive.")

    orig_lines = invoice.receipt_lines if isinstance(getattr(invoice, "receipt_lines", None), list) else []
    tax_map = _tax_map_from_invoice(invoice)

    if not orig_lines:
        # Fallback: allocate by tax band (existing behaviour) when original has no line detail
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
            last["salesAmountWithTax"] = safe_quantize(last["salesAmountWithTax"] + difference)
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

    # Line-by-line: each credit line matches original invoice line and copies its tax category/rate
    line_totals = []
    line_tax_info = []
    for ln in orig_lines:
        amt = _to_decimal(ln.get("receiptLineTotal") or ln.get("lineAmount") or 0)
        line_totals.append(abs(amt))
        tid = ln.get("taxID") or ln.get("fiscalCounterTaxID")
        tid = int(tid) if tid is not None else 1
        pct = ln.get("taxPercent") or ln.get("fiscalCounterTaxPercent")
        if pct is not None:
            pct = float(pct)
        else:
            pct = tax_map.get(tid, {}).get("taxPercent", 0.0)
        info = tax_map.get(tid, {"taxCode": "1", "taxPercent": 0.0})
        tax_code = info.get("taxCode", "1")
        if pct is None:
            pct = info.get("taxPercent", 0.0)
        line_tax_info.append({
            "taxID": tid,
            "taxCode": tax_code,
            "taxPercent": pct,
            "receiptLineName": ln.get("receiptLineName") or ln.get("description") or "Credit",
            "receiptLineHSCode": (ln.get("receiptLineHSCode") or ln.get("hs_code") or "0000")[:8],
            "receiptLineQuantity": float(ln.get("receiptLineQuantity") or ln.get("lineQuantity") or 1),
        })

    sum_line_totals = sum(line_totals)
    if sum_line_totals <= 0:
        sum_line_totals = invoice_total
    ratio = credit_total / sum_line_totals

    receipt_lines = []
    tax_agg = {}
    for i, (lt, info) in enumerate(zip(line_totals, line_tax_info)):
        allocated_sales = safe_quantize(lt * ratio)
        qty = info["receiptLineQuantity"]
        if qty <= 0:
            qty = Decimal("1")
        pct = Decimal(str(info["taxPercent"]))
        if pct > 0:
            tax_amt = extract_tax_from_inclusive(allocated_sales, pct)
            net_amt = extract_net_from_inclusive(allocated_sales, pct)
            if net_amt + tax_amt != allocated_sales:
                tax_amt = (allocated_sales - net_amt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            tax_amt = Decimal("0")

        receipt_lines.append({
            "receiptLineNo": i + 1,
            "receiptLineQuantity": float(qty),
            "receiptLineTotal": float(allocated_sales),
            "receiptLineName": info["receiptLineName"][:200],
            "receiptLineHSCode": info["receiptLineHSCode"],
            "taxID": info["taxID"],
            "taxCode": info["taxCode"],
            "taxPercent": round(info["taxPercent"], 2),
        })

    sum_allocated = sum(ln["receiptLineTotal"] for ln in receipt_lines)
    difference = credit_total - Decimal(str(sum_allocated))
    if difference != 0 and receipt_lines:
        last = receipt_lines[-1]
        last["receiptLineTotal"] = float(safe_quantize(Decimal(str(last["receiptLineTotal"])) + difference))

    # Rebuild receipt_taxes from final line totals so rounding difference is reflected
    tax_agg = {}
    for ln in receipt_lines:
        tid = ln["taxID"]
        sales = Decimal(str(ln["receiptLineTotal"]))
        pct = Decimal(str(ln["taxPercent"]))
        if pct > 0:
            tax_amt = extract_tax_from_inclusive(sales, pct)
        else:
            tax_amt = Decimal("0")
        tax_agg.setdefault(tid, {"taxCode": ln["taxCode"], "taxPercent": ln["taxPercent"], "sales": Decimal("0"), "tax": Decimal("0")})
        tax_agg[tid]["sales"] += sales
        tax_agg[tid]["tax"] += tax_amt

    receipt_taxes = []
    for tid, agg in tax_agg.items():
        receipt_taxes.append({
            "taxID": tid,
            "taxCode": agg["taxCode"],
            "taxPercent": round(agg["taxPercent"], 2),
            "taxAmount": float(agg["tax"]),
            "salesAmountWithTax": float(agg["sales"]),
        })

    return {
        "receipt_lines": receipt_lines,
        "receipt_taxes": receipt_taxes,
        "credit_total": float(credit_total),
    }
