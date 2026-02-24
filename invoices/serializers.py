"""Invoice creation serializers. FDMS v7.2 compliant. No client tax/totals."""

from decimal import Decimal, InvalidOperation


class ValidationError(Exception):
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(message)


def _to_decimal(value, default=None):
    try:
        return Decimal(str(value)) if value is not None else default
    except (InvalidOperation, TypeError, ValueError):
        return default


def validate_invoice_item(item):
    """
    Validate item. No product linkage.
    Required: item_name, quantity, unit_price, tax_id.
    Optional: hs_code.
    Tax comes only from tax_id (FDMS config).
    """
    if not isinstance(item, dict):
        raise ValidationError("Item must be an object", "items")
    item_name = str(item.get("item_name", item.get("itemName", ""))).strip()
    if not item_name:
        raise ValidationError("item_name is required", "items")
    quantity = _to_decimal(item.get("quantity", 1))
    if quantity is None or quantity <= 0:
        raise ValidationError("Quantity must be > 0", "items")
    unit_price = _to_decimal(item.get("unit_price", item.get("unitPrice", 0)))
    if unit_price is None or unit_price < 0:
        raise ValidationError("unit_price must be >= 0", "items")
    tax_id = item.get("tax_id")
    if tax_id is None:
        raise ValidationError("tax_id is required", "items")
    try:
        tax_id = int(tax_id)
    except (TypeError, ValueError):
        raise ValidationError("tax_id must be an integer", "items")
    tax_percent = item.get("tax_percent")
    if tax_percent is not None:
        try:
            tax_percent = float(tax_percent)
        except (TypeError, ValueError):
            tax_percent = None
    tax_code = str(item.get("tax_code", item.get("taxCode", "")) or "").strip()[:3] or None
    hs_code = str(item.get("hs_code", "")).strip() or "000000"
    return {
        "item_name": item_name[:200],
        "quantity": quantity,
        "unit_price": unit_price,
        "tax_id": tax_id,
        "tax_percent": tax_percent,
        "tax_code": tax_code,
        "hs_code": hs_code[:20] if hs_code else "000000",
    }


def validate_payment(payment):
    if not isinstance(payment, dict):
        raise ValidationError("Payment must be an object", "payments")
    method = str(payment.get("method", "CASH")).strip().upper() or "CASH"
    if method not in ("CASH", "CARD", "MOBILE", "BANK_TRANSFER", "ECOCASH"):
        method = "CASH"
    amount = _to_decimal(payment.get("amount", 0))
    if amount is None or amount < 0:
        raise ValidationError("Payment amount must be >= 0", "payments")
    return {"method": method, "amount": amount}


def validate_invoice_create(data):
    if not isinstance(data, dict):
        raise ValidationError("Request body must be JSON object")
    device_id = data.get("device_id")
    if device_id is None:
        raise ValidationError("device_id is required", "device_id")
    try:
        device_id = int(device_id)
    except (TypeError, ValueError):
        raise ValidationError("device_id must be an integer", "device_id")
    currency = str(data.get("currency", "ZWG")).strip().upper() or "ZWG"
    customer_name = str(data.get("customer_name", data.get("customerName", ""))).strip()
    customer_tin = str(data.get("customer_tin", data.get("customerTin", ""))).strip()
    customer_vat_number = str(data.get("customer_vat_number", data.get("customerVatNumber", ""))).strip()
    customer_address = str(data.get("customer_address", data.get("customerAddress", ""))).strip()
    customer_phone = str(data.get("customer_phone", data.get("customerPhone", ""))).strip()
    customer_email = str(data.get("customer_email", data.get("customerEmail", ""))).strip()
    invoice_reference = str(data.get("invoice_reference", data.get("invoiceReference", ""))).strip()
    notes = str(data.get("notes", "")).strip()
    issue_tax_invoice = data.get("issue_tax_invoice", data.get("issueTaxInvoice", True))
    if isinstance(issue_tax_invoice, str):
        issue_tax_invoice = str(issue_tax_invoice).lower() in ("true", "1", "yes")
    issue_tax_invoice = bool(issue_tax_invoice)
    items_raw = data.get("items", [])
    if not items_raw:
        raise ValidationError("At least one invoice item required", "items")
    items = []
    for i, it in enumerate(items_raw):
        try:
            items.append(validate_invoice_item(it))
        except ValidationError as e:
            e.field = f"items[{i}]"
            raise
    payments_raw = data.get("payments", [])
    if not payments_raw:
        raise ValidationError("At least one payment required", "payments")
    payments = []
    for i, p in enumerate(payments_raw):
        try:
            payments.append(validate_payment(p))
        except ValidationError as e:
            e.field = f"payments[{i}]"
            raise
    payment_total = sum(p["amount"] for p in payments)
    if payment_total <= 0:
        raise ValidationError("Payment total must be > 0", "payments")
    return {
        "device_id": device_id,
        "currency": currency,
        "customer_name": customer_name,
        "customer_tin": customer_tin,
        "customer_vat_number": customer_vat_number,
        "customer_address": customer_address,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "invoice_reference": invoice_reference,
        "notes": notes,
        "issue_tax_invoice": issue_tax_invoice,
        "items": items,
        "payments": payments,
    }
