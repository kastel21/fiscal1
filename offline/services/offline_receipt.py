"""
Create and enqueue receipt when offline. Uses local receipt_global_no sequence.
"""

import logging
from datetime import datetime
from decimal import Decimal

from django.db import transaction

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.receipt_engine import build_receipt_canonical_string, sign_receipt
from fiscal.services.receipt_service import _transform_to_credit_note, _validate_credit_note
from offline.models import OfflineReceiptQueue
from offline.services.queue_manager import QueueManager

logger = logging.getLogger("fiscal")


def _to_cents(value) -> int:
    from decimal import ROUND_HALF_UP
    return int(
        (Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP) * 100)
        .to_integral_value()
    )


def _next_receipt_global_no(device: FiscalDevice) -> int:
    """Next receipt_global_no for offline: max(submitted, queued) + 1."""
    last_submitted = device.last_receipt_global_no or 0
    last_queued = (
        OfflineReceiptQueue.objects.filter(receipt__device=device)
        .order_by("-receipt__receipt_global_no")
        .values_list("receipt__receipt_global_no", flat=True)
        .first()
    )
    return max(last_submitted, last_queued or 0) + 1


def create_and_queue_offline_receipt(
    device: FiscalDevice,
    fiscal_day_no: int,
    receipt_type: str,
    receipt_currency: str,
    invoice_no: str,
    receipt_lines: list,
    receipt_taxes: list,
    receipt_payments: list,
    receipt_total: float,
    receipt_lines_tax_inclusive: bool = True,
    receipt_date: datetime | None = None,
    original_invoice_no: str = "",
    original_receipt_global_no: int | None = None,
    customer_snapshot: dict | None = None,
) -> tuple[Receipt | None, str | None]:
    """
    Create receipt locally and add to offline queue. Use when FDMS is unreachable.
    Returns (Receipt, None) or (None, error_message).
    """
    if receipt_type == "CreditNote":
        err = _validate_credit_note(device, original_invoice_no or "", original_receipt_global_no)
        if err:
            return None, err
        receipt_lines, receipt_taxes, receipt_payments, receipt_total = _transform_to_credit_note(
            receipt_lines, receipt_taxes, receipt_payments, receipt_total
        )

    receipt_date = receipt_date or datetime.now()
    receipt_date_str = receipt_date.strftime("%Y-%m-%dT%H:%M:%S")
    receipt_global_no = _next_receipt_global_no(device)

    last_receipt = Receipt.objects.filter(
        device=device, fiscal_day_no=fiscal_day_no
    ).order_by("-receipt_counter").first()

    if last_receipt:
        receipt_counter = last_receipt.receipt_counter + 1
        previous_receipt_hash = last_receipt.receipt_hash or None
    else:
        receipt_counter = 1
        previous_receipt_hash = None

    canonical = build_receipt_canonical_string(
        device_id=device.device_id,
        receipt_type=receipt_type,
        receipt_currency=receipt_currency,
        receipt_global_no=receipt_global_no,
        receipt_date=receipt_date_str,
        receipt_total=Decimal(str(receipt_total)),
        receipt_tax_lines=receipt_taxes,
        previous_receipt_hash=previous_receipt_hash,
    )
    sig = sign_receipt(device, canonical)

    with transaction.atomic():
        receipt = Receipt.objects.create(
            device=device,
            fiscal_day_no=fiscal_day_no,
            receipt_global_no=receipt_global_no,
            receipt_counter=receipt_counter,
            currency=receipt_currency,
            receipt_lines=receipt_lines,
            receipt_taxes=receipt_taxes,
            receipt_payments=receipt_payments,
            receipt_lines_tax_inclusive=receipt_lines_tax_inclusive,
            receipt_type=receipt_type,
            invoice_no=invoice_no or "",
            original_invoice_no=(original_invoice_no or "").strip(),
            original_receipt_global_no=original_receipt_global_no,
            receipt_date=receipt_date,
            receipt_total=Decimal(str(receipt_total)),
            canonical_string=canonical,
            receipt_hash=sig["hash"],
            receipt_signature_hash=sig["hash"],
            receipt_signature_sig=sig["signature"],
            fdms_receipt_id=None,
            customer_snapshot=customer_snapshot or {},
        )
        QueueManager.enqueue(receipt)

    logger.info("Created and queued offline receipt device=%s global_no=%s", device.device_id, receipt_global_no)
    return receipt, None
