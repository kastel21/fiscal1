"""
Store FDMS SubmitReceipt responses and expose validation errors for invoices/notes.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fiscal.models import FiscalDevice, Receipt


def _extract_validation_errors(response_body: dict | None, status_code: int, fallback_text: str = "") -> list[str]:
    """
    Extract a list of validation error strings from FDMS response body.
    Handles common keys: detail, errors, validationErrors, title, etc.
    """
    errors: list[str] = []
    if not response_body or not isinstance(response_body, dict):
        if fallback_text:
            errors.append(fallback_text)
        return errors

    # Single message
    detail = response_body.get("detail") or response_body.get("title") or response_body.get("message")
    if detail and isinstance(detail, str):
        errors.append(detail)
    elif detail and isinstance(detail, list):
        for item in detail:
            if isinstance(item, str):
                errors.append(item)
            elif isinstance(item, dict):
                msg = item.get("message") or item.get("detail") or item.get("msg") or str(item)
                errors.append(str(msg))

    # Explicit validation errors list
    for key in ("errors", "validationErrors", "validation_errors"):
        val = response_body.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    errors.append(item)
                elif isinstance(item, dict):
                    msg = item.get("message") or item.get("detail") or item.get("field") or str(item)
                    errors.append(str(msg))

    if not errors and status_code >= 400 and fallback_text:
        errors.append(fallback_text)

    return errors


def store_receipt_submission_response(
    device: "FiscalDevice",
    receipt_global_no: int,
    status_code: int,
    response_body: dict | list | None,
    fiscal_day_no: int | None = None,
    receipt: "Receipt | None" = None,
    request_payload: dict | None = None,
) -> "ReceiptSubmissionResponse":
    """
    Store FDMS SubmitReceipt response in the database and link to receipt when provided.
    Extracts validation errors from response for display on invoice/note.
    """
    from fiscal.models import ReceiptSubmissionResponse

    if response_body is None:
        response_payload = {}
    elif isinstance(response_body, dict):
        response_payload = dict(response_body)
    else:
        response_payload = {"raw": response_body}

    fallback = ""
    if status_code >= 400 and not isinstance(response_body, dict):
        fallback = f"HTTP {status_code}"
    elif status_code >= 400 and isinstance(response_body, dict):
        fallback = response_body.get("detail") or response_body.get("title") or f"HTTP {status_code}"

    validation_errors = _extract_validation_errors(
        response_body if isinstance(response_body, dict) else None,
        status_code,
        fallback_text=fallback,
    )

    obj = ReceiptSubmissionResponse.objects.create(
        device=device,
        receipt_global_no=receipt_global_no,
        receipt=receipt,
        fiscal_day_no=fiscal_day_no,
        status_code=status_code,
        response_payload=response_payload,
        validation_errors=validation_errors,
    )
    return obj


def get_validation_errors_for_receipt(receipt: "Receipt") -> list[str]:
    """
    Return validation errors for an invoice or note, from the latest submission
    linked to this receipt (or same device + receipt_global_no). Empty list if none.
    """
    from fiscal.models import ReceiptSubmissionResponse

    # Prefer responses linked to this receipt
    latest = (
        ReceiptSubmissionResponse.objects.filter(receipt=receipt)
        .order_by("-created_at")
        .first()
    )
    if not latest:
        # Fallback: same device + receipt_global_no (e.g. failed attempt before receipt existed)
        latest = (
            ReceiptSubmissionResponse.objects.filter(
                device=receipt.device,
                receipt_global_no=receipt.receipt_global_no,
            )
            .order_by("-created_at")
            .first()
        )
    if not latest or not latest.validation_errors:
        return []
    return list(latest.validation_errors)
