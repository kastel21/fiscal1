"""
Fiscalised invoice layout per FDMS_Final_Invoice_Layout_Spec.
Builds context for compliant invoice template. No forbidden content.
"""

from decimal import Decimal

from fiscal.models import Receipt
from fiscal.services.config_service import get_latest_configs


def _format_address(addr: dict | None) -> str:
    if not addr or not isinstance(addr, dict):
        return ""
    parts = []
    for k in ("street", "houseNo", "city", "province"):
        v = addr.get(k)
        if v:
            parts.append(str(v))
    return ", ".join(parts)


def build_invoice_context(receipt: Receipt) -> dict:
    """
    Build context for FDMS-compliant invoice template.
    Excludes all forbidden content: operationID, receiptID, signatures, hashes, UUIDs.
    """
    device = receipt.device
    configs = get_latest_configs(device.device_id)
    raw = configs.raw_response if configs else {}
    # Supplier from GetConfig
    business_name = raw.get("taxPayerName") or raw.get("taxpayerName") or f"Device {device.device_id}"
    addr = raw.get("deviceBranchAddress") or {}
    business_address = _format_address(addr) or raw.get("deviceBranchName") or ""
    vat_tin = raw.get("vatNumber") or raw.get("taxPayerTIN") or raw.get("taxpayerTIN") or ""

    # Fiscal header: use document_type when set, else receipt_type
    doc_type = getattr(receipt, "document_type", None)
    if doc_type == "CREDIT_NOTE":
        doc_type = "CREDIT NOTE"
    elif doc_type == "DEBIT_NOTE":
        doc_type = "DEBIT NOTE"
    elif receipt.receipt_type == "CreditNote":
        doc_type = "Fiscal Credit Note"
    elif receipt.receipt_type == "DebitNote":
        doc_type = "Fiscal Debit Note"
    else:
        doc_type = "TAX INVOICE"
    fiscal_date = receipt.receipt_date or receipt.created_at
    fiscal_date_str = fiscal_date.strftime("%Y-%m-%d %H:%M") if fiscal_date else ""

    # Credit/Debit: original invoice and reason
    original_invoice_no = receipt.original_invoice_no or ""
    original_invoice_date = ""
    if getattr(receipt, "original_invoice", None) and receipt.original_invoice.receipt_date:
        original_invoice_date = receipt.original_invoice.receipt_date.strftime("%Y-%m-%d %H:%M")
    elif getattr(receipt, "original_invoice", None) and receipt.original_invoice.created_at:
        original_invoice_date = receipt.original_invoice.created_at.strftime("%Y-%m-%d %H:%M")
    if not original_invoice_no and getattr(receipt, "original_invoice", None):
        original_invoice_no = receipt.original_invoice.invoice_no or ""
    reason = (getattr(receipt, "reason", None) or "").strip()

    # Line items
    tax_rate_display = ""
    if receipt.receipt_taxes:
        first_tax = receipt.receipt_taxes[0]
        pct = first_tax.get("taxPercent") or first_tax.get("fiscalCounterTaxPercent")
        if pct is not None:
            tax_rate_display = f"{pct}%"
    lines = []
    for line in receipt.receipt_lines or []:
        qty = line.get("receiptLineQuantity") or line.get("lineQuantity") or 1
        amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        desc = line.get("receiptLineName") or line.get("description") or ""
        qty_f = float(qty) if qty else 1
        amt_f = float(amt) if amt else 0
        lines.append({
            "description": desc,
            "quantity": qty,
            "unit_price": amt_f / qty_f if qty_f else 0,
            "line_total": amt_f,
            "tax_rate": tax_rate_display,
        })

    # Tax summary
    tax_rows = []
    for t in receipt.receipt_taxes or []:
        rate = t.get("taxPercent") or t.get("fiscalCounterTaxPercent") or 0
        amt = t.get("salesAmountWithTax") or t.get("fiscalCounterValue") or 0
        tax_amt = round(float(t.get("taxAmount") or 0), 2)
        tax_rows.append({
            "rate": rate,
            "taxable_amount": round(float(amt) - tax_amt if tax_amt else float(amt), 2),
            "tax_amount": tax_amt,
        })
    total_tax_val = sum(r["tax_amount"] for r in tax_rows) if tax_rows else 0

    # Totals
    subtotal = Decimal("0")
    for line in receipt.receipt_lines or []:
        amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        subtotal += Decimal(str(amt))
    grand_total = receipt.receipt_total or subtotal
    if not tax_rows and receipt.receipt_taxes:
        total_tax_val = sum(float(t.get("taxAmount") or 0) for t in receipt.receipt_taxes)
    total_tax_val = round(float(total_tax_val), 2)

    # Payment summary
    payments = receipt.receipt_payments or []
    payment_rows = []
    for p in payments:
        method = p.get("paymentMethod") or p.get("method") or "Cash"
        amt = p.get("paymentAmount") or p.get("amount") or 0
        payment_rows.append({"method": method, "amount": float(amt)})
    if not payment_rows and payments:
        payment_rows = [{"method": "Cash", "amount": float(receipt.receipt_total or 0)}]
    elif not payment_rows:
        payment_rows = [{"method": "—", "amount": float(receipt.receipt_total or 0)}]

    qr_code_value = getattr(receipt, "qr_code_value", None) or ""
    qr_data = None
    if receipt.receipt_server_signature and isinstance(receipt.receipt_server_signature, dict):
        qr_data = receipt.receipt_server_signature.get("qrData") or receipt.receipt_server_signature.get("receiptQrData")
    qr_image_base64 = ""
    if qr_code_value:
        from fiscal.services.qr_generator import generate_qr_base64
        qr_image_base64 = generate_qr_base64(qr_code_value)

    # Customer snapshot (optional, from invoice creation)
    customer = receipt.customer_snapshot or {}
    has_customer = any(
        customer.get(k) for k in ("name", "tin", "address", "phone", "email", "reference", "notes")
    )

    # Validation errors from last submission (if any) linked to this invoice/note
    validation_errors = []
    try:
        from fiscal.services.receipt_submission_response_service import get_validation_errors_for_receipt
        validation_errors = get_validation_errors_for_receipt(receipt)
    except Exception:
        pass

    return {
        "business_name": business_name,
        "business_address": business_address,
        "vat_number": vat_tin,
        "device_id": device.device_id,
        "document_type": doc_type,
        "receipt_global_no": receipt.receipt_global_no,
        "fiscal_date": fiscal_date_str,
        "currency": receipt.currency or "USD",
        "invoice_no": receipt.invoice_no or "",
        "lines": lines,
        "tax_rows": tax_rows if tax_rows else [{"rate": 0, "taxable_amount": float(subtotal), "tax_amount": total_tax_val}],
        "subtotal": float(subtotal),
        "total_tax": total_tax_val,
        "grand_total": float(grand_total or 0),
        "payment_rows": payment_rows,
        "qr_code_value": qr_code_value,
        "qr_data": qr_data,
        "qr_image_base64": qr_image_base64,
        "qb_invoice_no": "",  # Optional: from sync metadata
        "customer": customer if has_customer else None,
        "original_invoice_no": original_invoice_no,
        "original_invoice_date": original_invoice_date,
        "reason": reason,
        "validation_errors": validation_errors,
    }
