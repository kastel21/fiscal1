"""Batch file builder. Immutable once written."""

import hashlib
import json
import logging
from pathlib import Path

from django.conf import settings

from offline.models import OfflineBatchFile, OfflineReceiptQueue

logger = logging.getLogger("fiscal")


class BatchFileBuilder:
    """Build immutable batch files."""

    @staticmethod
    def _receipt_payload(receipt) -> dict:
        return {
            "device_id": receipt.device_id,
            "fiscal_day_no": receipt.fiscal_day_no,
            "receipt_global_no": receipt.receipt_global_no,
            "receipt_counter": receipt.receipt_counter,
            "receipt_type": receipt.receipt_type,
            "currency": receipt.currency,
            "invoice_no": receipt.invoice_no or "",
            "receipt_date": receipt.receipt_date.isoformat() if receipt.receipt_date else None,
            "receipt_total": str(receipt.receipt_total) if receipt.receipt_total else None,
            "receipt_lines": receipt.receipt_lines or [],
            "receipt_taxes": receipt.receipt_taxes or [],
            "receipt_payments": receipt.receipt_payments or [],
            "canonical_string": receipt.canonical_string or "",
            "receipt_hash": receipt.receipt_hash or "",
            "receipt_signature_hash": receipt.receipt_signature_hash or "",
            "receipt_signature_sig": receipt.receipt_signature_sig or "",
            "created_at": receipt.created_at.isoformat() if receipt.created_at else None,
        }

    @classmethod
    def build(cls, queue_entries: list) -> OfflineBatchFile | None:
        """Build immutable batch file."""
        if not queue_entries:
            return None

        receipts = [e.receipt for e in queue_entries]
        device = receipts[0].device

        batch_data = {
            "device_id": device.device_id,
            "device_serial_no": device.device_serial_no or "",
            "batch_receipts": [cls._receipt_payload(r) for r in receipts],
        }
        content = json.dumps(batch_data, indent=2, default=str)
        content_bytes = content.encode("utf-8")
        checksum = hashlib.sha256(content_bytes).hexdigest()

        base_dir = Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR))
        batch_dir = base_dir / "offline_batches"
        batch_dir.mkdir(parents=True, exist_ok=True)
        filename = f"batch_{device.device_id}_{checksum[:16]}.json"
        file_path = batch_dir / filename
        file_path.write_bytes(content_bytes)

        batch_file = OfflineBatchFile.objects.create(
            device=device,
            file_path=str(file_path),
            file_checksum=checksum,
            receipt_count=len(receipts),
        )
        logger.info("Built batch file %s with %d receipts", file_path, len(receipts))
        return batch_file
