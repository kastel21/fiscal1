"""
Credit Note Excel import service. Validation, balance calculation, FDMS mapping.
"""

from decimal import Decimal

from django.db.models import Q
from django.core.exceptions import ValidationError

from fiscal.models import FiscalDevice, Receipt


def get_remaining_creditable_balance(original_receipt: Receipt) -> Decimal:
    from fiscal.services.credit_allocation_service import get_remaining_balance
    return get_remaining_balance(original_receipt)


def search_fiscalised_invoices(device: FiscalDevice, query: str = "", limit: int = 50) -> list[dict]:
    """Return fiscalised invoices for original-invoice selector. Searchable by invoice_no, receipt_global_no."""
    device_id = device.device_id if device else None
    if device_id is None:
        return []
    qs = Receipt.objects.filter(
        device__device_id=device_id,
        receipt_type__in=["FiscalInvoice", "FISCALINVOICE"],
    ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0).order_by("-created_at")
    if query and query.strip():
        q = query.strip()
        if q.isdigit():
            qs = qs.filter(Q(receipt_global_no=int(q)) | Q(invoice_no__icontains=q))
        else:
            qs = qs.filter(invoice_no__icontains=q)
    qs = qs[:limit]
    result = []
    for r in qs:
        remaining = get_remaining_creditable_balance(r)
        result.append({
            "id": r.pk,
            "receipt_global_no": r.receipt_global_no,
            "invoice_no": r.invoice_no or "",
            "currency": r.currency or "USD",
            "total": float(r.receipt_total or 0),
            "remaining_balance": float(remaining),
        })
    return result


def get_enriched_invoices_for_form(
    device: FiscalDevice, query: str = "", limit: int = 50, for_debit: bool = False
) -> list[dict]:
    """Return fiscalised invoices with lines, date, customer for credit/debit note form."""
    base = search_fiscalised_invoices(device, query, limit)
    if for_debit and base:
        for inv in base:
            r = Receipt.objects.filter(pk=inv["id"]).first()
            if r:
                inv["remaining_balance"] = float(r.remaining_balance)
    if not base:
        return []
    ids = [x["id"] for x in base]
    receipts = {r.pk: r for r in Receipt.objects.filter(pk__in=ids)}
    result = []
    for inv in base:
        r = receipts.get(inv["id"])
        if not r:
            result.append({**inv, "date": "", "customer": "", "lines": []})
            continue
        cust = r.customer_snapshot or {}
        date_val = ""
        if r.receipt_date:
            date_val = r.receipt_date.strftime("%Y-%m-%d")
        taxes = r.receipt_taxes or []
        tax_pct = 0
        if taxes:
            tax_pct = float(taxes[0].get("taxPercent") or taxes[0].get("fiscalCounterTaxPercent") or 0)
        result.append({
            **inv,
            "date": date_val,
            "customer": cust.get("name", cust.get("buyerRegisterName", "")) or "-",
            "lines": r.receipt_lines or [],
            "receipt_global_no": r.receipt_global_no,
            "tax_percent": tax_pct,
        })
    return result


def validate_credit_note_import(
    original_receipt: Receipt,
    credit_lines: list[dict],
    credit_total: float,
    currency: str,
    device: FiscalDevice,
    config_status: str,
) -> list[str]:
    """
    Validate credit note import. Returns list of error messages. Empty = valid.
    """
    errors = []
    if not original_receipt:
        errors.append("No original invoice selected.")
        return errors

    try:
        from decimal import Decimal
        from fiscal.services.credit_allocation_service import validate_credit_amount
        validate_credit_amount(original_receipt, Decimal(str(credit_total)))
    except Exception as e:
        errors.append(str(e))

    if currency != (original_receipt.currency or "USD"):
        errors.append(f"Currency mismatch. Original invoice: {original_receipt.currency}, credit note: {currency}")

    for line in credit_lines:
        lt = line.get("line_total") or line.get("credit_amount") or 0
        if lt <= 0:
            errors.append(f"Line total must be positive (row {line.get('row_num', '?')}).")

    if not credit_lines:
        errors.append("No valid credit lines.")

    if config_status != "OK":
        errors.append("FDMS configs missing or stale. Refresh configs before submitting.")

    return errors


def lines_to_receipt_payload(
    credit_lines: list[dict],
    original_receipt: Receipt,
    receipt_total: float,
    refund_method: str = "CASH",
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Map to receipt_lines, receipt_taxes, receipt_payments using proportional allocation.
    credit_lines used only for total; allocation is proportional from original invoice.
    """
    from fiscal.services.credit_allocation_service import allocate_credit_proportionally
    allocation = allocate_credit_proportionally(original_receipt, receipt_total)
    money_type = (refund_method or "CASH").strip().upper()
    if money_type == "OFFSET":
        money_type = "CREDIT"
    receipt_payments = [{"paymentAmount": allocation["credit_total"], "method": money_type}]
    return allocation["receipt_lines"], allocation["receipt_taxes"], receipt_payments
