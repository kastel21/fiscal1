"""
Batch submitter. Submit queued receipts sequentially on recovery.
Replay stops immediately on error. No reordering, no skipping.
"""

import logging

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.receipt_service import _do_submit_receipt
from offline.models import OfflineReceiptQueue, SubmissionAttempt
from offline.services.offline_detector import OfflineDetector
from offline.services.queue_manager import QueueManager

logger = logging.getLogger("fiscal")


class BatchSubmitter:
    """Submit queued receipts sequentially. Stops on first error."""

    @staticmethod
    def _is_ordering_error(err: str) -> bool:
        """401 cert invalid, 422 payload rejected, or explicit ordering error."""
        err_lower = (err or "").lower()
        if "401" in err_lower or "cert" in err_lower or "unauthorized" in err_lower:
            return True
        if "422" in err_lower or "payload" in err_lower or "rejected" in err_lower:
            return True
        if "ordering" in err_lower or "out of sync" in err_lower:
            return True
        return False

    @classmethod
    def process_queue(cls, device: FiscalDevice) -> dict:
        """
        Load QUEUED receipts, submit sequentially. Stop on first error.
        Returns {
            "submitted": int,
            "failed": int,
            "halted_reason": str | None,
            "last_error": str | None,
        }
        """
        is_offline, offline_err = OfflineDetector.is_offline(device)
        if is_offline:
            return {
                "submitted": 0,
                "failed": 0,
                "halted_reason": "Still offline",
                "last_error": offline_err,
            }

        entries = list(QueueManager.get_queued(device=device))
        result = {"submitted": 0, "failed": 0, "halted_reason": None, "last_error": None}

        for entry in entries:
            QueueManager.mark_submitting(entry)
            receipt = entry.receipt

            rec, err = None, None
            try:
                rec, err = _do_submit_receipt(
                    device=receipt.device,
                    fiscal_day_no=receipt.fiscal_day_no,
                    receipt_type=receipt.receipt_type,
                    receipt_currency=receipt.currency,
                    invoice_no=receipt.invoice_no or "",
                    receipt_lines=receipt.receipt_lines or [],
                    receipt_taxes=receipt.receipt_taxes or [],
                    receipt_payments=receipt.receipt_payments or [],
                    receipt_total=float(receipt.receipt_total or 0),
                    receipt_lines_tax_inclusive=receipt.receipt_lines_tax_inclusive,
                    receipt_date=receipt.receipt_date,
                    original_invoice_no=receipt.original_invoice_no or "",
                    original_receipt_global_no=receipt.original_receipt_global_no,
                )
            except Exception as e:
                rec, err = None, str(e)

            SubmissionAttempt.objects.create(
                queue_entry=entry,
                receipt=receipt,
                success=False,
                error_message=err or "Unknown error",
            )

            if rec is not None:
                QueueManager.mark_submitted(entry)
                result["submitted"] += 1
                SubmissionAttempt.objects.filter(
                    queue_entry=entry, receipt=receipt
                ).update(success=True)
                continue

            QueueManager.mark_failed(entry, err or "Unknown error")
            result["failed"] += 1
            result["last_error"] = err
            result["halted_reason"] = (
                "Cert invalid or payload rejected – manual review required"
                if cls._is_ordering_error(err)
                else "Network or submission error – retry later"
            )
            logger.warning("Batch submit halted at receipt %s: %s", receipt.receipt_global_no, err)
            break

        return result
