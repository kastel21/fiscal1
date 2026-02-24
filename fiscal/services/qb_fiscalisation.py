"""
QuickBooks → FDMS Auto-Fiscalisation.
Map QB invoice to FDMS receipt, submit, store. Idempotent by qb_invoice_id.
"""

import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction

from fiscal.models import FiscalDevice, QuickBooksInvoice, Receipt
from fiscal.services.config_service import get_latest_configs, validate_against_configs
from fiscal.services.receipt_service import submit_receipt

logger = logging.getLogger("fiscal")


def _extract_line(line: dict) -> tuple[float, float, str]:
    """Extract qty, amount, description from QB line. Returns (qty, amount, desc).
    Amount is taken from top-level Amount/receiptLineTotal/lineAmount, or from
    SalesItemLineDetail Qty * UnitPrice when top-level amount is missing/zero.
    """
    qty = float(line.get("Qty") or line.get("Quantity") or line.get("receiptLineQuantity") or 1)
    amt = float(line.get("Amount") or line.get("receiptLineTotal") or line.get("lineAmount") or 0)
    if amt == 0:
        detail = line.get("SalesItemLineDetail") or line.get("ItemBasedExpenseLineDetail") or {}
        if isinstance(detail, dict):
            up = detail.get("UnitPrice") or detail.get("unit_price")
            if up is not None and qty:
                amt = float(qty) * float(up)
    desc_ref = line.get("DescriptionLineDetail")
    desc = str(
        line.get("Description")
        or line.get("receiptLineName")
        or (desc_ref.get("ServiceDate") if isinstance(desc_ref, dict) else None)
        or ""
    )[:200]
    return qty, amt, desc


def _extract_tax_code(line: dict) -> str | None:
    """Extract QB tax code from line if present."""
    detail = line.get("SalesItemLineDetail") or line.get("ItemBasedExpenseLineDetail") or {}
    ref = detail.get("TaxCodeRef") or {}
    return ref.get("value") if isinstance(ref, dict) else None


def _tax_code_to_fdms_id(qb_tax_code: str | None, configs) -> int:
    """Map QB tax code to FDMS taxID. Falls back to first valid from configs."""
    tax_table = (configs and configs.tax_table) or []
    valid_ids = [t.get("taxID") for t in tax_table if t.get("taxID") is not None]
    if not valid_ids:
        return 1
    if qb_tax_code:
        for t in tax_table:
            if str(t.get("taxCode", "")).upper() == str(qb_tax_code).upper():
                return int(t.get("taxID", 1))
            if str(t.get("taxName", "")).upper() == str(qb_tax_code).upper():
                return int(t.get("taxID", 1))
    return int(valid_ids[0])


def map_qb_invoice_to_fdms(qb_payload: dict, device: FiscalDevice) -> tuple[dict, str | None]:
    """
    Map QB invoice JSON to FDMS receipt payload.
    Returns (receipt_payload_dict, error_message).
    receipt_payload_dict has: receipt_lines, receipt_taxes, receipt_payments, receipt_total, currency, invoice_no.
    """
    configs = get_latest_configs(device.device_id)
    if not configs:
        return {}, "FDMS configs missing. Call GetConfig before fiscalisation."

    invoice_id = str(
        qb_payload.get("Id")
        or qb_payload.get("Invoice", {}).get("Id")
        or qb_payload.get("qb_invoice_id", "")
    )
    if not invoice_id:
        return {}, "Missing QB invoice ID"

    currency = "USD"
    curr_ref = qb_payload.get("CurrencyRef") or qb_payload.get("currency")
    if isinstance(curr_ref, dict) and curr_ref.get("value"):
        currency = str(curr_ref.get("value", "USD"))[:10]
    elif isinstance(curr_ref, str):
        currency = curr_ref[:10]

    total = float(qb_payload.get("TotalAmt") or qb_payload.get("total_amount") or qb_payload.get("receipt_total") or 0)
    lines_raw = qb_payload.get("Line") or qb_payload.get("receipt_lines") or qb_payload.get("LineItem") or []

    receipt_lines = []
    line_total_sum = 0.0
    tax_id_used = 1

    # Only skip non-product line types (e.g. subtotal); include all lines that have an amount.
    # Skip after extracting so we include lines where amount is in SalesItemLineDetail (Qty*UnitPrice).
    SUBTOTAL_LINE_TYPES = ("SubTotalLineDetail",)
    for line in lines_raw:
        if line.get("DetailType") in SUBTOTAL_LINE_TYPES:
            continue
        qty, amt, desc = _extract_line(line)
        if amt == 0:
            continue
        tax_code = _extract_tax_code(line)
        tax_id = _tax_code_to_fdms_id(tax_code, configs)
        tax_id_used = tax_id
        line_total_sum += amt
        receipt_lines.append({
            "receiptLineQuantity": qty,
            "receiptLineTotal": amt,
            "receiptLineName": desc or "Line item",
            "taxID": tax_id,
        })

    if not receipt_lines:
        return {}, "No valid line items in QB invoice"

    if abs(line_total_sum - total) > 0.02:
        total = line_total_sum

    receipt_taxes = [{"taxID": tax_id_used, "taxCode": "VAT", "taxAmount": 0, "salesAmountWithTax": total}]
    receipt_payments = [{"paymentAmount": total}]

    try:
        validate_against_configs(currency, receipt_taxes, receipt_lines, configs)
    except Exception as e:
        return {}, str(e)

    return {
        "receipt_lines": receipt_lines,
        "receipt_taxes": receipt_taxes,
        "receipt_payments": receipt_payments,
        "receipt_total": total,
        "currency": currency,
        "invoice_no": f"QB-{invoice_id}",
    }, None


def fiscalise_qb_invoice(qb_invoice_id: str, qb_payload: dict) -> tuple[QuickBooksInvoice | None, str | None]:
    """
    Store QB invoice, map to FDMS, submit, store receipt. Idempotent.
    Returns (QuickBooksInvoice, None) or (None, error_message).
    """
    device = FiscalDevice.objects.filter(is_registered=True).first()
    if not device:
        return None, "No registered fiscal device"

    cust_ref = qb_payload.get("CustomerRef")
    qb_customer_id = ""
    if isinstance(cust_ref, dict):
        qb_customer_id = str(cust_ref.get("value", ""))
    curr_ref = qb_payload.get("CurrencyRef")
    currency = "USD"
    if isinstance(curr_ref, dict) and curr_ref.get("value"):
        currency = str(curr_ref.get("value", "USD"))[:10]
    elif isinstance(curr_ref, str):
        currency = str(curr_ref)[:10]
    total = Decimal(str(qb_payload.get("TotalAmt") or qb_payload.get("total_amount") or 0))

    with transaction.atomic():
        qb_inv, created = QuickBooksInvoice.objects.get_or_create(
            qb_invoice_id=qb_invoice_id,
            defaults={
                "qb_customer_id": qb_customer_id,
                "currency": currency,
                "total_amount": total,
                "raw_payload": qb_payload,
            },
        )

        if qb_inv.fiscalised and qb_inv.fiscal_receipt_id:
            return qb_inv, None

    payload, err = map_qb_invoice_to_fdms(qb_payload, device)
    if err:
        qb_inv.fiscal_error = err
        qb_inv.save(update_fields=["fiscal_error", "updated_at"])
        return qb_inv, err

    status_data, status_err = None, None
    try:
        from fiscal.services.fdms_device_service import FDMSDeviceService
        status_data, status_err = FDMSDeviceService().get_status(device)
    except Exception as e:
        status_err = str(e)
    if status_err or not status_data:
        fiscal_day_no = device.last_fiscal_day_no or 1
    else:
        fiscal_day_no = status_data.get("lastFiscalDayNo") or device.last_fiscal_day_no or 1

    status = status_data.get("fiscalDayStatus", device.fiscal_day_status) if status_data else device.fiscal_day_status
    if status not in ("FiscalDayOpened", "FiscalDayCloseFailed"):
        err = f"Cannot submit: fiscal day status must be FiscalDayOpened or FiscalDayCloseFailed (current: {status})"
        qb_inv.fiscal_error = err
        qb_inv.save(update_fields=["fiscal_error", "updated_at"])
        return qb_inv, err

    receipt, err = submit_receipt(
        device=device,
        fiscal_day_no=int(fiscal_day_no),
        receipt_type="FiscalInvoice",
        receipt_currency=payload["currency"],
        invoice_no=payload["invoice_no"],
        receipt_lines=payload["receipt_lines"],
        receipt_taxes=payload["receipt_taxes"],
        receipt_payments=payload["receipt_payments"],
        receipt_total=payload["receipt_total"],
        receipt_lines_tax_inclusive=True,
        receipt_date=datetime.now(),
    )

    if receipt:
        qb_inv.fiscalised = True
        qb_inv.fiscal_receipt = receipt
        qb_inv.fiscal_error = ""
        qb_inv.save(update_fields=["fiscalised", "fiscal_receipt", "fiscal_error", "updated_at"])
        logger.info("QB invoice %s fiscalised: receipt_global_no=%s", qb_invoice_id, receipt.receipt_global_no)
        return qb_inv, None

    qb_inv.fiscal_error = err or "Unknown error"
    qb_inv.save(update_fields=["fiscal_error", "updated_at"])
    return qb_inv, err
