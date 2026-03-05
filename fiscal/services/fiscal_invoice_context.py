"""
Build context for templates/invoices/fiscal_invoice_a4.html (Section 10 A4 Tax Invoice).
Uses Receipt model fields including fiscal_invoice_number, receipt_number, VAT breakdown, buyer.
Context provides company, invoice (namespace), and invoice_items for the Tax Invoice template.
"""

from decimal import Decimal
from types import SimpleNamespace

from fiscal.models import Receipt
from fiscal.services.config_service import get_latest_configs


def _format_address(addr: dict | None) -> str:
    if not addr or not isinstance(addr, dict):
        return ""
    parts = [str(addr.get(k)) for k in ("street", "houseNo", "city", "province") if addr.get(k)]
    return ", ".join(parts)


def _fmt(num) -> str:
    """Format number for display (2 dp)."""
    if num is None:
        return "0.00"
    try:
        return f"{float(num):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def _safe_list(value, default=None):
    """Return value if it is a list, else default. Avoids iterating over NotImplemented/None/non-list."""
    if default is None:
        default = []
    return value if isinstance(value, list) else default


def build_fiscal_invoice_a4_context(receipt: Receipt) -> dict:
    """
    Build context for invoices/fiscal_invoice_a4.html.
    Returns company, invoice (SimpleNamespace), and invoice_items so template can use
    {{ company.name }}, {{ invoice.fiscal_invoice_number }}, {% for item in invoice_items %}.
    """
    from fiscal.services.qr_generator import generate_qr_base64, generate_receipt_qr_string

    device = receipt.device
    configs = get_latest_configs(device.device_id)
    raw = configs.raw_response if configs else {}
    supplier_name = (
        getattr(device, "taxpayer_name", None)
        or raw.get("taxPayerName")
        or raw.get("taxpayerName")
        or f"Device {device.device_id}"
    )
    supplier_tin = getattr(device, "taxpayer_tin", None) or raw.get("taxPayerTIN") or raw.get("taxpayerTIN") or ""
    supplier_vat = getattr(device, "vat_number", None) or raw.get("vatNumber") or ""
    branch_addr = getattr(device, "branch_address", None) or raw.get("deviceBranchAddress") or {}
    supplier_address = _format_address(branch_addr) if isinstance(branch_addr, dict) else str(branch_addr or "")
    branch_name = getattr(device, "branch_name", None) or raw.get("deviceBranchName") or ""

    fiscal_invoice_number = getattr(receipt, "fiscal_invoice_number", None) or receipt.invoice_no or ""
    receipt_number = getattr(receipt, "receipt_number", None) or ""
    if not receipt_number and receipt.receipt_global_no is not None:
        receipt_number = str(receipt.receipt_global_no)
    receipt_date = (receipt.receipt_date or receipt.created_at)
    receipt_date_str = receipt_date.strftime("%Y-%m-%d %H:%M") if receipt_date else ""
    currency = receipt.currency or "USD"

    buyer_name = getattr(receipt, "buyer_name", None) or (receipt.customer_snapshot or {}).get("name") or ""
    buyer_tin = getattr(receipt, "buyer_tin", None) or (receipt.customer_snapshot or {}).get("tin") or ""
    buyer_vat = getattr(receipt, "buyer_vat", None) or (receipt.customer_snapshot or {}).get("vat_number") or ""
    buyer_address = getattr(receipt, "buyer_address", None) or ""
    if not buyer_address and isinstance((receipt.customer_snapshot or {}).get("address"), dict):
        buyer_address = _format_address((receipt.customer_snapshot or {}).get("address"))
    elif not buyer_address:
        buyer_address = str((receipt.customer_snapshot or {}).get("address") or "")

    # Use stored values from DB only; do not recalculate VAT/exclusive (would diverge from submission).
    # Guard: use only list values (avoid NotImplemented / None / non-iterable causing 'not iterable' errors)
    lines = _safe_list(getattr(receipt, "receipt_lines", None))
    receipt_taxes = _safe_list(getattr(receipt, "receipt_taxes", None))
    # Build taxID -> taxPercent from receipt_taxes for per-line VAT % (multi-rate: 15.5%, 0%, exempt)
    tax_pct_by_id = {}
    for t in receipt_taxes:
        tid = t.get("taxID") or t.get("fiscalCounterTaxID")
        pct = t.get("taxPercent") or t.get("fiscalCounterTaxPercent")
        if tid is not None:
            tax_pct_by_id[int(tid)] = float(pct) if pct is not None else None

    invoice_items = []
    for i, line in enumerate(lines):
        qty = line.get("receiptLineQuantity") or line.get("lineQuantity") or 1
        line_total_stored = line.get("receiptLineTotal") or line.get("lineAmount") or 0
        unit_price_stored = line.get("receiptLinePrice") or line.get("linePrice") or (float(line_total_stored) / float(qty) if qty else 0)
        desc = line.get("receiptLineName") or line.get("description") or ""
        qty_f = float(qty) if qty else 1
        line_total_f = float(line_total_stored) if line_total_stored else 0
        unit_price_f = float(unit_price_stored) if unit_price_stored else 0
        # Unit price is tax-exclusive: exclusive = qty * unit_price; tax = line_total - exclusive (per-line VAT)
        exclusive_f = round(unit_price_f * qty_f, 2)
        line_tax_f = round(line_total_f - exclusive_f, 2)
        code = line.get("receiptLineHSCode") or line.get("hs_code") or ""
        # Original VAT % for this line (different lines can be 15.5%, 0%, exempt)
        tax_pct = line.get("taxPercent") or line.get("fiscalCounterTaxPercent") or line.get("receiptLineTaxPercent")
        if tax_pct is None:
            tid = line.get("taxID") or line.get("fiscalCounterTaxID")
            if tid is not None:
                tax_pct = tax_pct_by_id.get(int(tid))
        if tax_pct is not None:
            tax_percent_val = float(tax_pct)
            tax_percent_display = f"{tax_percent_val:.1f}%" if tax_percent_val else "0%"
        else:
            tax_percent_val = None
            tax_percent_display = "Exempt"

        # Display-only: if stored VAT is 0 but line is taxable, compute VAT for display (tax-exclusive pricing)
        if line_tax_f == 0 and tax_percent_val and tax_percent_val > 0:
            display_vat = round(exclusive_f * (tax_percent_val / 100), 2)
            display_total = round(exclusive_f + display_vat, 2)
        else:
            display_vat = line_tax_f
            display_total = line_total_f

        invoice_items.append({
            "line_no": i + 1,
            "code": code,
            "hs_code": code,
            "description": desc,
            "quantity": qty_f,
            "unit_price": unit_price_f,
            "exclusive_amount": exclusive_f,
            "line_total": line_total_f,
            "tax_amount": line_tax_f,
            "tax_rate": tax_percent_val,
            "tax_percent": tax_percent_val,
            "tax_percent_display": tax_percent_display,
            "display_vat": display_vat,
            "display_total": display_total,
        })

    # Totals from display values (so totals match sum of displayed line VAT and line totals)
    subtotal_sum = sum(item["exclusive_amount"] for item in invoice_items)
    display_total_tax_sum = sum(item["display_vat"] for item in invoice_items)
    display_grand_total_sum = sum(item["display_total"] for item in invoice_items)
    subtotal = Decimal(str(subtotal_sum))
    total_tax = Decimal(str(round(display_total_tax_sum, 2)))
    grand_total = Decimal(str(round(display_grand_total_sum, 2)))

    subtotal_15 = getattr(receipt, "subtotal_15", None) or Decimal("0")
    tax_15 = getattr(receipt, "tax_15", None) or Decimal("0")
    subtotal_0 = getattr(receipt, "subtotal_0", None) or Decimal("0")
    subtotal_exempt = getattr(receipt, "subtotal_exempt", None) or Decimal("0")

    # VAT breakdown: only include rows for taxes that were used (non-zero amounts)
    vat_breakdown_rows = []
    if subtotal_15 or tax_15:
        vat_breakdown_rows.append({"label": "VAT 15%", "taxable": _fmt(subtotal_15), "tax": _fmt(tax_15)})
    if subtotal_0:
        vat_breakdown_rows.append({"label": "VAT 0%", "taxable": _fmt(subtotal_0), "tax": "0.00"})
    if subtotal_exempt:
        vat_breakdown_rows.append({"label": "Exempt", "taxable": _fmt(subtotal_exempt), "tax": "0.00"})

    payment_rows = []
    for p in _safe_list(getattr(receipt, "receipt_payments", None)):
        method = p.get("moneyTypeCode") or p.get("method") or "Cash"
        amt = float(p.get("paymentAmount") or p.get("amount") or 0)
        payment_rows.append({"method": method, "amount": amt})
    if not payment_rows:
        payment_rows = [{"method": "—", "amount": float(grand_total or 0)}]
    payment_method = payment_rows[0]["method"] if payment_rows else "—"
    amount_paid = float(grand_total or 0)
    balance = "0.00"

    fiscal_signature = getattr(receipt, "fiscal_signature", None) or (receipt.receipt_hash or "")
    verification_code = getattr(receipt, "verification_code", None) or ""

    device_serial = getattr(device, "device_serial_no", None) or ""
    customer_ref = (receipt.customer_snapshot or {}).get("reference") or getattr(receipt, "customer_ref", None) or ""
    internal_invoice_no = receipt.invoice_no or receipt_number
    reference = (receipt.customer_snapshot or {}).get("reference") or getattr(receipt, "reference", None) or ""

    qr_string = getattr(receipt, "qr_code_value", None) or ""
    if not qr_string and receipt.receipt_hash:
        qr_string = generate_receipt_qr_string(receipt)
    qr_image_base64 = generate_qr_base64(qr_string) if qr_string else ""

    from fiscal.utils import get_logo_base64
    from fiscal.models import Company
    company_model = getattr(device, "company", None)
    logo_base64 = get_logo_base64(company_model) if company_model else None
    if not logo_base64:
        # Fall back to any company with a logo (e.g. logo uploaded in Settings uses first company)
        for c in Company.objects.all()[:10]:
            logo_base64 = get_logo_base64(c)
            if logo_base64:
                break
    company_email = getattr(company_model, "email", None) if company_model else None
    company_phone = getattr(company_model, "phone", None) if company_model else None
    company_email = company_email or ""
    company_phone = company_phone or ""

    company = SimpleNamespace(
        name=supplier_name,
        address=supplier_address,
        vat_number=supplier_vat or "—",
        tin=supplier_tin or "—",
        branch_name=branch_name or "",
        logo_base64=logo_base64,
        email=company_email,
        phone=company_phone,
    )

    invoice = SimpleNamespace(
        device_id=device.device_id,
        device_serial=device_serial,
        fiscal_invoice_number=fiscal_invoice_number,
        receipt_number=receipt_number,
        receipt_global_no=receipt.receipt_global_no,
        fiscal_day_no=receipt.fiscal_day_no,
        fiscalisation_datetime=receipt_date_str,
        currency=currency,
        buyer_name=buyer_name,
        buyer_address=buyer_address,
        buyer_vat=buyer_vat or "—",
        buyer_tin=buyer_tin or "—",
        customer_ref=customer_ref,
        internal_invoice_no=internal_invoice_no,
        reference=reference,
        subtotal_15=_fmt(subtotal_15),
        tax_15=_fmt(tax_15),
        subtotal_0=_fmt(subtotal_0),
        subtotal_exempt=_fmt(subtotal_exempt),
        subtotal=_fmt(subtotal),
        total_tax=_fmt(total_tax),
        total=_fmt(grand_total),
        payment_method=payment_method,
        amount_paid=_fmt(amount_paid),
        balance=balance,
        fiscal_signature=fiscal_signature,
        verification_code=verification_code,
        qr_code_base64=qr_image_base64,
    )

    return {
        "company": company,
        "invoice": invoice,
        "invoice_items": invoice_items,
        "vat_breakdown_rows": vat_breakdown_rows,
        # Legacy flat keys for any code still using them
        "supplier_name": supplier_name,
        "supplier_address": supplier_address,
        "supplier_vat": supplier_vat,
        "supplier_tin": supplier_tin,
        "device_id": device.device_id,
        "fiscal_invoice_number": fiscal_invoice_number,
        "invoice_no": receipt.invoice_no or "",
        "receipt_number": receipt_number,
        "receipt_global_no": receipt.receipt_global_no,
        "fiscal_day_no": receipt.fiscal_day_no,
        "receipt_date": receipt_date_str,
        "receipt_currency": currency,
        "buyer_name": buyer_name,
        "buyer_tin": buyer_tin,
        "buyer_vat": buyer_vat,
        "buyer_address": buyer_address,
        "line_items": invoice_items,
        "subtotal_15": float(subtotal_15),
        "tax_15": float(tax_15),
        "subtotal_0": float(subtotal_0),
        "subtotal_exempt": float(subtotal_exempt),
        "total_tax": float(total_tax),
        "subtotal": float(subtotal),
        "grand_total": float(grand_total or 0),
        "payment_rows": payment_rows,
        "fiscal_signature": fiscal_signature,
        "verification_code": verification_code,
        "qr_image_base64": qr_image_base64,
    }


def build_fiscal_credit_note_a4_context(receipt: Receipt) -> dict:
    """
    Build context for invoices/credit_note_a4.html (Fiscal Credit Note).
    Returns company, credit_note (SimpleNamespace), credit_note_items, and vat_breakdown_rows.
    Uses same company/supplier and VAT logic as invoice; adds original invoice refs and reason.
    """
    from fiscal.services.qr_generator import generate_qr_base64, generate_receipt_qr_string
    from fiscal.utils import get_logo_base64
    from fiscal.models import Company

    device = receipt.device
    configs = get_latest_configs(device.device_id)
    raw = configs.raw_response if configs else {}
    supplier_name = (
        getattr(device, "taxpayer_name", None)
        or raw.get("taxPayerName")
        or raw.get("taxpayerName")
        or f"Device {device.device_id}"
    )
    supplier_tin = getattr(device, "taxpayer_tin", None) or raw.get("taxPayerTIN") or raw.get("taxpayerTIN") or ""
    supplier_vat = getattr(device, "vat_number", None) or raw.get("vatNumber") or ""
    branch_addr = getattr(device, "branch_address", None) or raw.get("deviceBranchAddress") or {}
    supplier_address = _format_address(branch_addr) if isinstance(branch_addr, dict) else str(branch_addr or "")
    branch_name = getattr(device, "branch_name", None) or raw.get("deviceBranchName") or ""

    company_model = getattr(device, "company", None)
    logo_base64 = get_logo_base64(company_model) if company_model else None
    if not logo_base64:
        for c in Company.objects.all()[:10]:
            logo_base64 = get_logo_base64(c)
            if logo_base64:
                break

    company = SimpleNamespace(
        name=supplier_name,
        address=supplier_address,
        vat_number=supplier_vat or "—",
        tin=supplier_tin or "—",
        branch_name=branch_name or "",
        logo_base64=logo_base64,
    )

    fiscal_credit_number = getattr(receipt, "fiscal_invoice_number", None) or receipt.invoice_no or ""
    receipt_number = getattr(receipt, "receipt_number", None) or ""
    if not receipt_number and receipt.receipt_global_no is not None:
        receipt_number = str(receipt.receipt_global_no)
    receipt_date = receipt.receipt_date or receipt.created_at
    receipt_date_str = receipt_date.strftime("%Y-%m-%d %H:%M") if receipt_date else ""
    currency = receipt.currency or "USD"

    original_invoice_no = receipt.original_invoice_no or ""
    original_receipt_global_no = receipt.original_receipt_global_no
    original_invoice_date = ""
    if getattr(receipt, "original_invoice", None) and receipt.original_invoice.receipt_date:
        original_invoice_date = receipt.original_invoice.receipt_date.strftime("%Y-%m-%d %H:%M")
    elif getattr(receipt, "original_invoice", None) and receipt.original_invoice.created_at:
        original_invoice_date = receipt.original_invoice.created_at.strftime("%Y-%m-%d %H:%M")
    reason = getattr(receipt, "reason", None) or ""

    buyer_name = getattr(receipt, "buyer_name", None) or (receipt.customer_snapshot or {}).get("name") or ""
    buyer_tin = getattr(receipt, "buyer_tin", None) or (receipt.customer_snapshot or {}).get("tin") or ""
    buyer_vat = getattr(receipt, "buyer_vat", None) or (receipt.customer_snapshot or {}).get("vat_number") or ""
    buyer_address = getattr(receipt, "buyer_address", None) or ""
    if not buyer_address and isinstance((receipt.customer_snapshot or {}).get("address"), dict):
        buyer_address = _format_address((receipt.customer_snapshot or {}).get("address"))
    elif not buyer_address:
        buyer_address = str((receipt.customer_snapshot or {}).get("address") or "")

    device_serial = getattr(device, "device_serial_no", None) or ""
    customer_ref = (receipt.customer_snapshot or {}).get("reference") or getattr(receipt, "customer_ref", None) or ""
    reference = (receipt.customer_snapshot or {}).get("reference") or getattr(receipt, "reference", None) or ""

    _lines = _safe_list(getattr(receipt, "receipt_lines", None))
    _taxes = _safe_list(getattr(receipt, "receipt_taxes", None))
    # Use description from original invoice when available (credit note references original)
    _orig_lines = []
    if getattr(receipt, "original_invoice", None):
        _orig_lines = _safe_list(getattr(receipt.original_invoice, "receipt_lines", None))
    # UNIT PRICES ARE TAX EXCLUSIVE. exclusive = qty * unit_price; vat = exclusive * (tax_rate/100); line_total = exclusive + vat. Credit note displays negative values.
    credit_note_items = []
    for i, line in enumerate(_lines):
        qty = line.get("receiptLineQuantity") or line.get("lineQuantity") or 1
        unit_price_stored = line.get("receiptLinePrice") or line.get("linePrice")
        if unit_price_stored is None:
            amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
            qty_f = abs(float(qty)) if qty else 1
            unit_price_stored = float(amt) / qty_f if qty_f else 0
        # Prefer description, code, and tax from original invoice line (same index)
        if i < len(_orig_lines):
            orig_ln = _orig_lines[i]
            desc = orig_ln.get("receiptLineName") or orig_ln.get("description") or line.get("receiptLineName") or line.get("description") or "Credit"
            code = orig_ln.get("receiptLineHSCode") or orig_ln.get("hs_code") or line.get("receiptLineHSCode") or line.get("hs_code") or ""
            tax_pct = orig_ln.get("taxPercent") or orig_ln.get("fiscalCounterTaxPercent") or line.get("taxPercent") or line.get("fiscalCounterTaxPercent")
            tax_cat = orig_ln.get("taxCode") or line.get("taxCode") or ""
        else:
            desc = line.get("receiptLineName") or line.get("description") or "Credit"
            code = line.get("receiptLineHSCode") or line.get("hs_code") or ""
            tax_pct = line.get("taxPercent") or line.get("fiscalCounterTaxPercent")
            tax_cat = line.get("taxCode") or ""
        qty_f = abs(float(qty)) if qty else 1
        unit_price_f = abs(float(unit_price_stored)) if unit_price_stored is not None else 0
        tax_rate = float(tax_pct) if tax_pct is not None else None
        exclusive_f = round(qty_f * unit_price_f, 2)
        tax_amount_f = round(exclusive_f * (tax_rate / 100), 2) if (tax_rate is not None and tax_rate) else 0.0
        line_total_f = round(exclusive_f + tax_amount_f, 2)
        credit_note_items.append({
            "code": code,
            "description": desc,
            "quantity": qty_f,
            "unit_price": unit_price_f,
            "exclusive_amount": exclusive_f,
            "line_total": line_total_f,
            "tax_rate": tax_rate,
            "tax_category": tax_cat,
            "tax_amount": tax_amount_f,
        })

    # Totals: total_exclusive = sum(exclusive), total_vat = sum(vat), total = sum(line_total). Credit note: display as negative.
    subtotal_sum = sum(item["exclusive_amount"] for item in credit_note_items)
    total_tax_sum = sum(item["tax_amount"] for item in credit_note_items)
    grand_total_sum = round(sum(item["line_total"] for item in credit_note_items), 2)
    exclusive_display = round(-subtotal_sum, 2)
    vat_display = round(-total_tax_sum, 2)
    total_display = round(-grand_total_sum, 2)

    subtotal_15 = abs(getattr(receipt, "subtotal_15", None) or Decimal("0"))
    tax_15 = abs(getattr(receipt, "tax_15", None) or Decimal("0"))
    subtotal_0 = abs(getattr(receipt, "subtotal_0", None) or Decimal("0"))
    subtotal_exempt = abs(getattr(receipt, "subtotal_exempt", None) or Decimal("0"))

    vat_breakdown_rows = []
    if subtotal_15 or tax_15:
        vat_breakdown_rows.append({"label": "VAT 15%", "taxable": _fmt(subtotal_15), "tax": _fmt(tax_15)})
    if subtotal_0:
        vat_breakdown_rows.append({"label": "VAT 0%", "taxable": _fmt(subtotal_0), "tax": "0.00"})
    if subtotal_exempt:
        vat_breakdown_rows.append({"label": "Exempt", "taxable": _fmt(subtotal_exempt), "tax": "0.00"})

    fiscal_signature = getattr(receipt, "fiscal_signature", None) or (receipt.receipt_hash or "")
    verification_code = getattr(receipt, "verification_code", None) or ""
    qr_string = getattr(receipt, "qr_code_value", None) or ""
    if not qr_string and receipt.receipt_hash:
        qr_string = generate_receipt_qr_string(receipt)
    qr_image_base64 = generate_qr_base64(qr_string) if qr_string else ""

    credit_note = SimpleNamespace(
        device_id=device.device_id,
        device_serial=device_serial,
        fiscal_credit_number=fiscal_credit_number,
        receipt_number=receipt_number,
        receipt_global_no=receipt.receipt_global_no,
        fiscal_day_no=receipt.fiscal_day_no,
        fiscalisation_datetime=receipt_date_str,
        currency=currency,
        original_invoice_number=original_invoice_no,
        original_receipt_global_no=original_receipt_global_no or "",
        original_invoice_date=original_invoice_date,
        reason=reason,
        buyer_name=buyer_name,
        buyer_tin=buyer_tin,
        buyer_address=buyer_address,
        buyer_vat=buyer_vat,
        customer_ref=customer_ref,
        reference=reference,
        subtotal_15=_fmt(subtotal_15),
        tax_15=_fmt(tax_15),
        subtotal_0=_fmt(subtotal_0),
        subtotal_exempt=_fmt(subtotal_exempt),
        subtotal=_fmt(subtotal_sum),
        total_tax=_fmt(total_tax_sum),
        total=_fmt(grand_total_sum),
        exclusive_display=exclusive_display,
        vat_display=vat_display,
        total_display=total_display,
        fiscal_signature=fiscal_signature,
        verification_code=verification_code,
        qr_code_base64=qr_image_base64,
    )

    return {
        "company": company,
        "credit_note": credit_note,
        "credit_note_items": credit_note_items,
        "vat_breakdown_rows": vat_breakdown_rows,
    }


def build_fiscal_debit_note_a4_context(receipt: Receipt) -> dict:
    """
    Build context for invoices/fiscal_debit_note.html (Fiscal Debit Note).
    Returns company, debit_note (SimpleNamespace), debit_note_items, and vat_breakdown_rows.
    Unit price is tax-exclusive: exclusive = qty * unit_price, total = exclusive + vat.
    Debit note amounts are positive (add to original invoice).
    """
    from fiscal.services.qr_generator import generate_qr_base64, generate_receipt_qr_string
    from fiscal.utils import get_logo_base64
    from fiscal.models import Company

    device = receipt.device
    configs = get_latest_configs(device.device_id)
    raw = configs.raw_response if configs else {}
    supplier_name = (
        getattr(device, "taxpayer_name", None)
        or raw.get("taxPayerName")
        or raw.get("taxpayerName")
        or f"Device {device.device_id}"
    )
    supplier_tin = getattr(device, "taxpayer_tin", None) or raw.get("taxPayerTIN") or raw.get("taxpayerTIN") or ""
    supplier_vat = getattr(device, "vat_number", None) or raw.get("vatNumber") or ""
    branch_addr = getattr(device, "branch_address", None) or raw.get("deviceBranchAddress") or {}
    supplier_address = _format_address(branch_addr) if isinstance(branch_addr, dict) else str(branch_addr or "")
    branch_name = getattr(device, "branch_name", None) or raw.get("deviceBranchName") or ""

    company_model = getattr(device, "company", None)
    logo_base64 = get_logo_base64(company_model) if company_model else None
    if not logo_base64:
        for c in Company.objects.all()[:10]:
            logo_base64 = get_logo_base64(c)
            if logo_base64:
                break

    company = SimpleNamespace(
        name=supplier_name,
        address=supplier_address,
        vat_number=supplier_vat or "—",
        tin=supplier_tin or "—",
        branch_name=branch_name or "",
        logo_base64=logo_base64,
    )

    fiscal_debit_number = getattr(receipt, "fiscal_invoice_number", None) or receipt.invoice_no or ""
    receipt_number = getattr(receipt, "receipt_number", None) or ""
    if not receipt_number and receipt.receipt_global_no is not None:
        receipt_number = str(receipt.receipt_global_no)
    receipt_date = receipt.receipt_date or receipt.created_at
    receipt_date_str = receipt_date.strftime("%Y-%m-%d %H:%M") if receipt_date else ""
    currency = receipt.currency or "USD"

    original_invoice_no = receipt.original_invoice_no or ""
    original_receipt_global_no = receipt.original_receipt_global_no
    original_invoice_date = ""
    if getattr(receipt, "original_invoice", None) and receipt.original_invoice.receipt_date:
        original_invoice_date = receipt.original_invoice.receipt_date.strftime("%Y-%m-%d %H:%M")
    elif getattr(receipt, "original_invoice", None) and receipt.original_invoice.created_at:
        original_invoice_date = receipt.original_invoice.created_at.strftime("%Y-%m-%d %H:%M")
    reason = getattr(receipt, "reason", None) or ""

    buyer_name = getattr(receipt, "buyer_name", None) or (receipt.customer_snapshot or {}).get("name") or ""
    buyer_tin = getattr(receipt, "buyer_tin", None) or (receipt.customer_snapshot or {}).get("tin") or ""
    buyer_vat = getattr(receipt, "buyer_vat", None) or (receipt.customer_snapshot or {}).get("vat_number") or ""
    buyer_address = getattr(receipt, "buyer_address", None) or ""
    if not buyer_address and isinstance((receipt.customer_snapshot or {}).get("address"), dict):
        buyer_address = _format_address((receipt.customer_snapshot or {}).get("address"))
    elif not buyer_address:
        buyer_address = str((receipt.customer_snapshot or {}).get("address") or "")
    customer_ref = (receipt.customer_snapshot or {}).get("reference") or getattr(receipt, "customer_ref", None) or ""
    reference = getattr(receipt, "reference", None) or (receipt.customer_snapshot or {}).get("reference") or ""
    device_serial = getattr(device, "device_serial_no", None) or ""

    _lines = _safe_list(getattr(receipt, "receipt_lines", None))
    _taxes = _safe_list(getattr(receipt, "receipt_taxes", None))
    # UNIT PRICES ARE TAX INCLUSIVE for debit notes:
    # line_total_incl = qty * unit_price_incl
    # exclusive = line_total_incl / (1 + tax_rate/100)
    # vat = line_total_incl - exclusive
    debit_note_items = []
    for i, line in enumerate(_lines):
        qty = line.get("receiptLineQuantity") or line.get("lineQuantity") or 1
        unit_price_stored = line.get("receiptLinePrice") or line.get("linePrice")
        if unit_price_stored is None:
            amt = line.get("receiptLineTotal") or line.get("lineAmount") or 0
            qty_f = float(qty) if qty else 1
            unit_price_stored = float(amt) / qty_f if qty_f else 0
        desc = line.get("receiptLineName") or line.get("description") or "Debit"
        code = line.get("receiptLineHSCode") or line.get("hs_code") or ""
        qty_f = float(qty) if qty else 1
        unit_price_f = float(unit_price_stored) if unit_price_stored is not None else 0
        tax_pct = line.get("taxPercent") or line.get("fiscalCounterTaxPercent")
        tax_rate = float(tax_pct) if tax_pct is not None else None
        line_total_f = round(qty_f * unit_price_f, 2)
        if tax_rate is not None and tax_rate > 0:
            divisor = 1 + (tax_rate / 100)
            exclusive_f = round(line_total_f / divisor, 2)
        else:
            exclusive_f = line_total_f
        tax_amount_f = round(line_total_f - exclusive_f, 2)
        debit_note_items.append({
            "code": code,
            "description": desc,
            "quantity": qty_f,
            "unit_price": unit_price_f,
            "exclusive_amount": exclusive_f,
            "line_total": line_total_f,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount_f,
        })

    # Totals: total_exclusive = sum(exclusive), total_vat = sum(vat), total = sum(line_total)
    subtotal_sum = sum(item["exclusive_amount"] for item in debit_note_items)
    total_tax_sum = sum(item["tax_amount"] for item in debit_note_items)
    grand_total_sum = round(sum(item["line_total"] for item in debit_note_items), 2)
    subtotal = Decimal(str(round(subtotal_sum, 2)))
    total_tax = Decimal(str(round(total_tax_sum, 2)))
    grand_total = Decimal(str(grand_total_sum))

    subtotal_15 = getattr(receipt, "subtotal_15", None) or Decimal("0")
    tax_15 = getattr(receipt, "tax_15", None) or Decimal("0")
    subtotal_0 = getattr(receipt, "subtotal_0", None) or Decimal("0")
    subtotal_exempt = getattr(receipt, "subtotal_exempt", None) or Decimal("0")

    vat_breakdown_rows = []
    if subtotal_15 or tax_15:
        vat_breakdown_rows.append({"label": "VAT 15%", "taxable": _fmt(subtotal_15), "tax": _fmt(tax_15)})
    if subtotal_0:
        vat_breakdown_rows.append({"label": "VAT 0%", "taxable": _fmt(subtotal_0), "tax": "0.00"})
    if subtotal_exempt:
        vat_breakdown_rows.append({"label": "Exempt", "taxable": _fmt(subtotal_exempt), "tax": "0.00"})

    fiscal_signature = getattr(receipt, "fiscal_signature", None) or (receipt.receipt_hash or "")
    verification_code = getattr(receipt, "verification_code", None) or ""
    qr_string = getattr(receipt, "qr_code_value", None) or ""
    if not qr_string and receipt.receipt_hash:
        qr_string = generate_receipt_qr_string(receipt)
    qr_image_base64 = generate_qr_base64(qr_string) if qr_string else ""

    debit_note = SimpleNamespace(
        device_id=device.device_id,
        device_serial=device_serial,
        fiscal_debit_number=fiscal_debit_number,
        receipt_number=receipt_number,
        receipt_global_no=receipt.receipt_global_no,
        fiscal_day_no=receipt.fiscal_day_no,
        fiscalisation_datetime=receipt_date_str,
        currency=currency,
        original_invoice_number=original_invoice_no,
        original_receipt_global_no=original_receipt_global_no or "",
        original_invoice_date=original_invoice_date,
        reason=reason,
        buyer_name=buyer_name,
        buyer_tin=buyer_tin,
        buyer_address=buyer_address,
        buyer_vat=buyer_vat,
        customer_ref=customer_ref,
        reference=reference,
        subtotal_15=_fmt(subtotal_15),
        tax_15=_fmt(tax_15),
        subtotal_0=_fmt(subtotal_0),
        subtotal_exempt=_fmt(subtotal_exempt),
        subtotal=subtotal,
        total_tax=total_tax,
        total=grand_total,
        fiscal_signature=fiscal_signature,
        verification_code=verification_code,
        qr_code_base64=qr_image_base64,
    )

    return {
        "company": company,
        "debit_note": debit_note,
        "debit_note_items": debit_note_items,
        "vat_breakdown_rows": vat_breakdown_rows,
    }


def get_receipt_print_template_and_context(receipt: Receipt) -> tuple[str, dict]:
    """
    Return (template_name, context) for the receipt — exactly what the print view shows.
    Use for both print and PDF so the PDF is the exact same content as print.
    """
    receipt_type = getattr(receipt, "receipt_type", None)
    if receipt_type == "CreditNote":
        return "invoices/fiscal_credit_note.html", build_fiscal_credit_note_a4_context(receipt)
    if receipt_type == "DebitNote":
        return "invoices/fiscal_debit_note.html", build_fiscal_debit_note_a4_context(receipt)
    return "invoices/fiscal_invoice_a4.html", build_fiscal_invoice_a4_context(receipt)
