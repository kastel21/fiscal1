"""Queue manager for offline receipts."""

import logging

from django.db import transaction

from offline.models import OfflineReceiptQueue

logger = logging.getLogger("fiscal")


class QueueManager:
    """Manage offline receipt queue."""

    @staticmethod
    def enqueue(receipt) -> OfflineReceiptQueue:
        """Append receipt to queue."""
        if receipt.fdms_receipt_id:
            raise ValueError("Cannot enqueue already-submitted receipt")
        entry, created = OfflineReceiptQueue.objects.get_or_create(
            receipt=receipt,
            defaults={"state": "QUEUED"},
        )
        if created:
            logger.info("Enqueued receipt %s (device=%s, global_no=%s)",
                        receipt.id, receipt.device_id, receipt.receipt_global_no)
        return entry

    @staticmethod
    def get_queued(device=None):
        """Return QUEUED entries in order."""
        qs = OfflineReceiptQueue.objects.filter(state="QUEUED").select_related("receipt", "receipt__device")
        if device:
            qs = qs.filter(receipt__device=device)
        return qs.order_by("receipt__receipt_global_no", "receipt__fiscal_day_no", "created_at")

    @staticmethod
    def mark_submitting(entry: OfflineReceiptQueue) -> None:
        with transaction.atomic():
            entry.state = "SUBMITTING"
            entry.save(update_fields=["state", "updated_at"])

    @staticmethod
    def mark_submitted(entry: OfflineReceiptQueue) -> None:
        with transaction.atomic():
            entry.state = "SUBMITTED"
            entry.save(update_fields=["state", "updated_at"])

    @staticmethod
    def mark_failed(entry: OfflineReceiptQueue, reason: str) -> None:
        with transaction.atomic():
            entry.state = "FAILED"
            entry.failure_reason = reason or ""
            entry.save(update_fields=["state", "failure_reason", "updated_at"])

    @staticmethod
    def queue_size(device=None) -> int:
        qs = OfflineReceiptQueue.objects.filter(state="QUEUED")
        if device:
            qs = qs.filter(receipt__device=device)
        return qs.count()
