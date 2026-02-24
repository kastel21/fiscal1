"""
Fiscal day totals service. Aggregates invoices, credit notes, and debit notes
for a given fiscal day. Includes breakdown (subtotal, tax) and tax-inclusive flag.
"""

from decimal import Decimal

from django.db.models import Sum, Q

from fiscal.models import FiscalDevice, Receipt


def _sum_receipt_total(receipts) -> Decimal:
    """Sum receipt_total from a queryset."""
    r = receipts.aggregate(s=Sum("receipt_total"))
    return r["s"] or Decimal("0")


def _sum_line_totals(receipts) -> Decimal:
    """Sum line totals from receipt_lines across receipts."""
    total = Decimal("0")
    for r in receipts:
        for line in r.receipt_lines or []:
            amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
            total += Decimal(str(amt))
    return total


def _sum_tax_amounts(receipts) -> Decimal:
    """Sum tax amounts from receipt_taxes across receipts."""
    total = Decimal("0")
    for r in receipts:
        for t in r.receipt_taxes or []:
            amt = t.get("taxAmount") or t.get("fiscalCounterValue") or 0
            total += Decimal(str(amt))
    return total


def _describe_tax_inclusive(receipts) -> dict:
    """
    Describe whether line totals are tax inclusive across receipts.
    Returns: {
        "all_inclusive": bool,
        "all_exclusive": bool,
        "mixed": bool,
        "summary": str,
    }
    """
    inclusive_count = 0
    exclusive_count = 0
    for r in receipts:
        if getattr(r, "receipt_lines_tax_inclusive", True):
            inclusive_count += 1
        else:
            exclusive_count += 1
    all_inclusive = exclusive_count == 0 and inclusive_count > 0
    all_exclusive = inclusive_count == 0 and exclusive_count > 0
    mixed = inclusive_count > 0 and exclusive_count > 0
    if mixed:
        summary = f"Mixed: {inclusive_count} tax-inclusive, {exclusive_count} tax-exclusive"
    elif all_inclusive:
        summary = "All line totals are tax-inclusive"
    elif all_exclusive:
        summary = "All line totals are tax-exclusive"
    else:
        summary = "No documents"
    return {
        "all_inclusive": all_inclusive,
        "all_exclusive": all_exclusive,
        "mixed": mixed,
        "summary": summary,
        "inclusive_count": inclusive_count,
        "exclusive_count": exclusive_count,
    }


def _totals_for_querysets(
    invoices_qs, credit_notes_qs, debit_notes_qs
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Compute all sums for three querysets. Returns inv_total, inv_sub, inv_tax, cn_total, ... dn_tax."""
    inv_total = _sum_receipt_total(invoices_qs)
    inv_subtotal = _sum_line_totals(invoices_qs)
    inv_tax = _sum_tax_amounts(invoices_qs)
    cn_total = _sum_receipt_total(credit_notes_qs)
    cn_subtotal = _sum_line_totals(credit_notes_qs)
    cn_tax = _sum_tax_amounts(credit_notes_qs)
    dn_total = _sum_receipt_total(debit_notes_qs)
    dn_subtotal = _sum_line_totals(debit_notes_qs)
    dn_tax = _sum_tax_amounts(debit_notes_qs)
    return inv_total, inv_subtotal, inv_tax, cn_total, cn_subtotal, cn_tax, dn_total, dn_subtotal, dn_tax


def get_fiscal_day_totals(device: FiscalDevice | None, fiscal_day_no: int | None) -> dict:
    """
    Compute totals for a fiscal day considering invoices, credit notes, and debit notes.
    Breaks down by currency for readability.
    Returns a dict with:
    - by_currency: list of { currency, invoices, credit_notes, debit_notes, net_total } per currency
    - currency: first/primary currency (for backward compatibility)
    - has_data: bool
    """
    if not device or fiscal_day_no is None:
        return {
            "by_currency": [],
            "invoices": {"count": 0, "total": 0, "subtotal": 0, "tax": 0, "tax_inclusive": None},
            "credit_notes": {"count": 0, "total": 0, "subtotal": 0, "tax": 0, "tax_inclusive": None},
            "debit_notes": {"count": 0, "total": 0, "subtotal": 0, "tax": 0, "tax_inclusive": None},
            "net_total": 0,
            "currency": "USD",
            "has_data": False,
        }

    base_qs = Receipt.objects.filter(device=device, fiscal_day_no=fiscal_day_no)
    currencies = list(
        base_qs.values_list("currency", flat=True).distinct().order_by("currency")
    )
    if not currencies:
        return {
            "by_currency": [],
            "invoices": {"count": 0, "total": 0, "subtotal": 0, "tax": 0, "tax_inclusive": None},
            "credit_notes": {"count": 0, "total": 0, "subtotal": 0, "tax": 0, "tax_inclusive": None},
            "debit_notes": {"count": 0, "total": 0, "subtotal": 0, "tax": 0, "tax_inclusive": None},
            "net_total": 0,
            "currency": "USD",
            "has_data": False,
        }

    by_currency = []
    for curr in currencies:
        curr_qs = base_qs.filter(currency=curr)
        invoices_qs = curr_qs.filter(
            Q(document_type="INVOICE") | (Q(document_type="") & Q(receipt_type="FiscalInvoice"))
        )
        credit_notes_qs = curr_qs.filter(
            Q(document_type="CREDIT_NOTE") | Q(receipt_type__in=("CreditNote", "CREDITNOTE"))
        )
        debit_notes_qs = curr_qs.filter(
            Q(document_type="DEBIT_NOTE") | Q(receipt_type__in=("DebitNote", "DEBITNOTE"))
        )
        (
            inv_total, inv_subtotal, inv_tax,
            cn_total, cn_subtotal, cn_tax,
            dn_total, dn_subtotal, dn_tax,
        ) = _totals_for_querysets(invoices_qs, credit_notes_qs, debit_notes_qs)
        net_total = inv_total + cn_total + dn_total
        inv_tax_info = _describe_tax_inclusive(invoices_qs) if invoices_qs.exists() else None
        cn_tax_info = _describe_tax_inclusive(credit_notes_qs) if credit_notes_qs.exists() else None
        dn_tax_info = _describe_tax_inclusive(debit_notes_qs) if debit_notes_qs.exists() else None
        by_currency.append({
            "currency": curr,
            "invoices": {
                "count": invoices_qs.count(),
                "total": float(inv_total),
                "subtotal": float(inv_subtotal),
                "tax": float(inv_tax),
                "tax_inclusive": inv_tax_info,
            },
            "credit_notes": {
                "count": credit_notes_qs.count(),
                "total": float(cn_total),
                "subtotal": float(cn_subtotal),
                "tax": float(cn_tax),
                "tax_inclusive": cn_tax_info,
            },
            "debit_notes": {
                "count": debit_notes_qs.count(),
                "total": float(dn_total),
                "subtotal": float(dn_subtotal),
                "tax": float(dn_tax),
                "tax_inclusive": dn_tax_info,
            },
            "net_total": float(net_total),
        })

    first_curr = by_currency[0]
    return {
        "by_currency": by_currency,
        "invoices": first_curr["invoices"],
        "credit_notes": first_curr["credit_notes"],
        "debit_notes": first_curr["debit_notes"],
        "net_total": first_curr["net_total"],
        "currency": first_curr["currency"],
        "has_data": base_qs.exists(),
    }
