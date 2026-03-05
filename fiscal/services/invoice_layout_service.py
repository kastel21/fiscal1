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


def build_invoice_a4_context(receipt: Receipt) -> dict:
    """
    Build context for ZIMRA FDMS Section 10 (InvoiceA4), Section 11 (QR), Section 13 (Signatures).
    Includes all mandatory fiscal block fields, buyer (if any), line items with HS Code,
    tax summary, totals, payments, signatures, and QR. Used for legally compliant PDF.
    """
    from fiscal.services.qr_generator import get_receipt_device_signature_hash_hex, generate_qr_base64, generate_receipt_qr_string

    device = receipt.device
    configs = get_latest_configs(device.device_id)
    raw = configs.raw_response if configs else {}
    # Header left: taxpayer (Section 10)
    taxpayer_name = (
        getattr(device, "taxpayer_name", None)
        or raw.get("taxPayerName")
        or raw.get("taxpayerName")
        or f"Device {device.device_id}"
    )
    taxpayer_tin = getattr(device, "taxpayer_tin", None) or raw.get("taxPayerTIN") or raw.get("taxpayerTIN") or ""
    vat_number = getattr(device, "vat_number", None) or raw.get("vatNumber") or ""
    branch_name = getattr(device, "branch_name", None) or raw.get("deviceBranchName") or ""
    branch_addr = getattr(device, "branch_address", None) or raw.get("deviceBranchAddress") or {}
    branch_address = _format_address(branch_addr) if isinstance(branch_addr, dict) else str(branch_addr or "")
    device_serial_no = getattr(device, "device_serial_no", None) or ""

    # Fiscal block right (Section 10)
    receipt_id = receipt.fdms_receipt_id
    receipt_date_dt = receipt.receipt_date or receipt.created_at
    receipt_date_str = receipt_date_dt.strftime("%Y-%m-%d %H:%M") if receipt_date_dt else ""
    server_date_val = getattr(receipt, "server_date", None)
    server_date_str = server_date_val.strftime("%Y-%m-%d %H:%M") if server_date_val else ""
    operation_id = getattr(receipt, "operation_id", None) or ""

    # Buyer (Section 10 – buyerData if present)
    customer = receipt.customer_snapshot or {}
    buyer_register_name = customer.get("name") or customer.get("buyerRegisterName") or ""
    buyer_tin = customer.get("tin") or customer.get("buyerTIN") or ""
    buyer_vat_number = customer.get("vatNumber") or customer.get("VATNumber") or ""
    buyer_address = customer.get("address") or ""
    if isinstance(buyer_address, dict):
        buyer_address = _format_address(buyer_address)

    # Line items with HS Code (Section 10; VAT taxpayers require HS Code)
    line_items = []
    for i, line in enumerate(receipt.receipt_lines or []):
        qty = line.get("receiptLineQuantity") or line.get("lineQuantity") or 1
        amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        desc = line.get("receiptLineName") or line.get("description") or ""
        qty_f = float(qty) if qty else 1
        amt_f = float(amt) if amt else 0
        unit_price = amt_f / qty_f if qty_f else 0
        hs_code = line.get("receiptLineHSCode") or line.get("hs_code") or ""
        tax_pct = line.get("taxPercent") or line.get("fiscalCounterTaxPercent")
        if tax_pct is not None:
            tax_pct = f"{tax_pct}%"
        line_items.append({
            "line_no": i + 1,
            "hs_code": hs_code,
            "description": desc,
            "quantity": qty_f,
            "unit_price": unit_price,
            "line_total": amt_f,
            "tax_percent": tax_pct,
        })

    # Tax summary grouped by tax_percent (Section 10 – receiptTaxes)
    tax_summary = []
    for t in receipt.receipt_taxes or []:
        tax_code = t.get("taxCode") or ""
        tax_pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent")
        sales_with_tax = float(t.get("salesAmountWithTax") or t.get("fiscalCounterValue") or 0)
        tax_amt = float(t.get("taxAmount") or 0)
        taxable = round(sales_with_tax - tax_amt, 2)
        tax_summary.append({
            "tax_code": tax_code,
            "tax_percent": tax_pct,
            "taxable_amount": taxable,
            "tax_amount": tax_amt,
            "sales_amount_with_tax": sales_with_tax,
            "sales_with_tax": sales_with_tax,
        })

    # Totals – must reconcile with receiptTotal
    subtotal = Decimal("0")
    for line in receipt.receipt_lines or []:
        amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        subtotal += Decimal(str(amt))
    total_vat = sum(r["tax_amount"] for r in tax_summary)
    grand_total = float(receipt.receipt_total or 0)
    if abs(float(subtotal) + total_vat - grand_total) > 0.01:
        total_vat = grand_total - float(subtotal)

    # Payment section (payment.method, payment.amount)
    payment_rows = []
    payments = receipt.receipt_payments or []
    for p in payments:
        method = p.get("moneyTypeCode") or p.get("moneyType") or p.get("paymentMethod") or p.get("method") or "Cash"
        amt = float(p.get("paymentAmount") or p.get("amount") or 0)
        payment_rows.append({"method": method, "amount": amt, "payment_amount": amt})
    if not payment_rows:
        payment_rows = [{"method": "—", "amount": grand_total, "payment_amount": grand_total}]

    payment_total = sum(p["amount"] for p in payment_rows)
    change_amount = round(payment_total - grand_total, 2) if payment_total > grand_total else None
    if change_amount is not None and abs(change_amount) < 0.01:
        change_amount = None

    # Signatures (Section 13)
    receipt_device_signature_hash = (receipt.receipt_hash or "").strip()
    try:
        hex_hash = get_receipt_device_signature_hash_hex(receipt)
        if hex_hash:
            receipt_device_signature_hash = hex_hash
    except Exception:
        pass
    server_sig = receipt.receipt_server_signature
    if isinstance(server_sig, dict):
        receipt_server_signature = server_sig.get("signature") or server_sig.get("receiptServerSignature") or ""
    else:
        receipt_server_signature = str(server_sig or "")

    # QR (Section 11): qrUrl + receiptDeviceSignature.hash → we use full QR string (qrUrl/deviceID+date+globalNo+qrData)
    qr_code_value = getattr(receipt, "qr_code_value", None) or ""
    if not qr_code_value and receipt.receipt_hash:
        qr_code_value = generate_receipt_qr_string(receipt)
    qr_image_base64 = generate_qr_base64(qr_code_value) if qr_code_value else ""

    # Buyer object for template (buyer.name, buyer.tin, buyer.vat, buyer.address)
    buyer = None
    if buyer_register_name or buyer_tin or buyer_vat_number or buyer_address:
        buyer = {
            "name": buyer_register_name,
            "tin": buyer_tin,
            "vat": buyer_vat_number,
            "address": buyer_address,
        }

    return {
        "taxpayer_name": taxpayer_name,
        "taxpayer_tin": taxpayer_tin,
        "vat_number": vat_number,
        "branch_name": branch_name,
        "branch_address": branch_address,
        "device_serial": device_serial_no,
        "device_serial_no": device_serial_no,
        "device_id": device.device_id,
        "receipt_id": receipt_id,
        "fiscal_day_no": receipt.fiscal_day_no,
        "receipt_counter": receipt.receipt_counter,
        "receipt_global_no": receipt.receipt_global_no,
        "invoice_no": receipt.invoice_no or "",
        "receipt_type": receipt.receipt_type or "FiscalInvoice",
        "receipt_date": receipt_date_str,
        "receipt_currency": receipt.currency or "USD",
        "operation_id": operation_id,
        "server_date": server_date_str,
        "buyer": buyer,
        "line_items": line_items,
        "tax_summary": tax_summary,
        "subtotal": float(subtotal),
        "total_vat": round(total_vat, 2),
        "grand_total": grand_total,
        "payment_rows": payment_rows,
        "change_amount": change_amount,
        "device_signature_hash": receipt_device_signature_hash,
        "fdms_signature": receipt_server_signature,
        "receipt_device_signature_hash": receipt_device_signature_hash,
        "receipt_server_signature": receipt_server_signature,
        "qr_code_value": qr_code_value,
        "qr_image_base64": qr_image_base64,
    }
