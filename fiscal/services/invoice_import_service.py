"""
Invoice Excel import service. Validation, FDMS mapping per Invoice 01 rules.
"""

from decimal import Decimal

from fiscal.models import FiscalDevice
from fiscal.services.config_service import get_config_status, get_latest_configs
from fiscal.services.excel_parser import validate_line_math


def validate_invoice_import(
    lines: list[dict],
    receipt_type: str,
    currency: str,
    tax_id: int | None,
    device: FiscalDevice,
) -> list[str]:
    """
    Validate invoice import. Returns list of error messages. Empty = valid.
    """
    errors = []
    if not lines:
        errors.append("No valid line items detected.")
        return errors
    for line in lines:
        errors.extend(validate_line_math(line))
    if not currency or not currency.strip():
        errors.append("Currency must be selected.")
    if tax_id is None:
        errors.append("Tax type must be selected.")
    config_status = get_config_status(device.device_id)["status"]
    if config_status != "OK":
        errors.append("FDMS configs missing or stale. Refresh configs before submitting.")
    return errors


def lines_to_receipt_payload(
    lines: list[dict],
    currency: str,
    tax_id: int,
    receipt_lines_tax_inclusive: bool = False,
) -> tuple[list[dict], list[dict], list[dict], float]:
    """
    Map parsed lines to receipt_lines, receipt_taxes, receipt_payments.
    receiptLinesTaxInclusive = false per spec. Tax from GetConfig.
    """
    receipt_lines = []
    total = Decimal("0")
    for line in lines:
        qty = float(line.get("quantity", 1))
        amt = float(line.get("line_total", 0))
        total += Decimal(str(amt))
        receipt_lines.append({
            "lineQuantity": qty,
            "receiptLineQuantity": qty,
            "lineAmount": amt,
            "receiptLineTotal": amt,
            "receiptLineName": str(line.get("description", ""))[:200],
        })
    total_float = float(total)
    receipt_taxes = [{"taxID": tax_id, "taxCode": "VAT", "taxAmount": 0, "salesAmountWithTax": total_float}]
    receipt_payments = [{"paymentAmount": total_float}]
    return receipt_lines, receipt_taxes, receipt_payments, total_float
