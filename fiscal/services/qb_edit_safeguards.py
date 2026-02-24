"""
Safeguards for invoice edits after fiscalisation.
Once fiscalised, fiscal data must never change. Corrections require credit notes.
"""

from decimal import Decimal

from django.utils import timezone

from fiscal.models import FiscalEditAttempt, Receipt

FISCAL_FIELDS = [
    "currency",
    "receipt_total",
    "receipt_lines",
    "receipt_taxes",
    "receipt_payments",
]


def _snapshot_receipt(receipt: Receipt) -> dict:
    """Extract fiscal fields for comparison."""
    return {
        "currency": receipt.currency or "",
        "receipt_total": float(receipt.receipt_total or 0),
        "receipt_lines": list(receipt.receipt_lines or []),
        "receipt_taxes": list(receipt.receipt_taxes or []),
        "receipt_payments": list(receipt.receipt_payments or []),
    }


def _snapshot_from_payload(payload: dict) -> dict:
    """Extract fiscal fields from QB-style or API payload."""
    receipt = payload.get("receipt") or payload
    lines = receipt.get("receiptLines") or receipt.get("receipt_lines") or []
    taxes = receipt.get("receiptTaxes") or receipt.get("receipt_taxes") or []
    payments = receipt.get("receiptPayments") or receipt.get("receipt_payments") or []
    total = receipt.get("receiptTotal") or receipt.get("receipt_total") or 0
    return {
        "currency": (receipt.get("receiptCurrency") or receipt.get("currency") or "").strip(),
        "receipt_total": float(total),
        "receipt_lines": lines,
        "receipt_taxes": taxes,
        "receipt_payments": payments,
    }


def _norm_lines(lines: list) -> list:
    """Normalize for comparison (sort by key fields)."""
    out = []
    for line in lines or []:
        out.append({
            "qty": float(line.get("receiptLineQuantity") or line.get("lineQuantity") or 1),
            "desc": str(line.get("receiptLineName") or line.get("description") or ""),
            "total": float(line.get("receiptLineTotal") or line.get("lineAmount") or 0),
        })
    return sorted(out, key=lambda x: (x["desc"], x["qty"], x["total"]))


def _lines_differ(a: list, b: list) -> bool:
    if len(a) != len(b):
        return True
    na = _norm_lines(a)
    nb = _norm_lines(b)
    for i, (la, lb) in enumerate(zip(na, nb)):
        if abs(la["qty"] - lb["qty"]) > 0.001:
            return True
        if abs(la["total"] - lb["total"]) > 0.001:
            return True
        if la["desc"] != lb["desc"]:
            return True
    return False


def _taxes_differ(a: list, b: list) -> bool:
    if len(a) != len(b):
        return True
    for ta, tb in zip(a or [], b or []):
        amt_a = float(ta.get("salesAmountWithTax") or ta.get("taxAmount") or 0)
        amt_b = float(tb.get("salesAmountWithTax") or tb.get("taxAmount") or 0)
        if abs(amt_a - amt_b) > 0.001:
            return True
    return False


def _payments_differ(a: list, b: list) -> bool:
    if len(a) != len(b):
        return True
    tot_a = sum(float(p.get("paymentAmount") or p.get("amount") or 0) for p in (a or []))
    tot_b = sum(float(p.get("paymentAmount") or p.get("amount") or 0) for p in (b or []))
    return abs(tot_a - tot_b) > 0.001


def fiscal_fields_changed(original: dict, attempted: dict) -> tuple[bool, list[str]]:
    """
    Compare fiscal fields. Returns (changed, list of changed field names).
    """
    changes = []
    if (original.get("currency") or "").strip() != (attempted.get("currency") or "").strip():
        changes.append("currency")
    if abs(float(original.get("receipt_total") or 0) - float(attempted.get("receipt_total") or 0)) > 0.001:
        changes.append("totals")
    if _lines_differ(original.get("receipt_lines") or [], attempted.get("receipt_lines") or []):
        changes.append("line_items")
    if _taxes_differ(original.get("receipt_taxes") or [], attempted.get("receipt_taxes") or []):
        changes.append("taxes")
    if _payments_differ(original.get("receipt_payments") or [], attempted.get("receipt_payments") or []):
        changes.append("payments")
    return len(changes) > 0, changes


def validate_qb_invoice_update(
    receipt: Receipt,
    attempted_payload: dict,
    source: str = "QB",
    actor: str = "",
) -> tuple[bool, str]:
    """
    Validate update to a fiscalised invoice. Returns (allowed, reason).
    If allowed=False, callers must block the update and optionally log.
    """
    if not receipt.is_fiscalised:
        return True, ""

    original = _snapshot_receipt(receipt)
    attempted = _snapshot_from_payload(attempted_payload)
    changed, diff = fiscal_fields_changed(original, attempted)

    if changed:
        diff_summary = ", ".join(diff)
        FiscalEditAttempt.objects.create(
            receipt=receipt,
            original_snapshot=original,
            attempted_change=attempted,
            source=source,
            actor=actor,
            blocked=True,
            diff_summary=diff_summary,
        )
        return False, (
            f"Fiscal data cannot be changed. Blocked fields: {diff_summary}. "
            "To correct, issue a credit note."
        )
    return True, ""
