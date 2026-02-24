"""
Management command: Backfill qr_code_value for receipts that have receipt_hash but empty qr_code_value.
Run after fixing QR generation or for receipts created before QR was populated.
"""

import logging

from django.core.management.base import BaseCommand
from django.db.models import Q

from fiscal.models import Receipt
from fiscal.services.qr_service import attach_qr_to_receipt

logger = logging.getLogger("fiscal")


class Command(BaseCommand):
    help = "Auto-populate QR codes for fiscalised receipts that have receipt_hash but empty qr_code_value."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many receipts would be updated; do not save.",
        )
        parser.add_argument(
            "--device",
            type=int,
            default=None,
            help="Limit to receipts for this FDMS device_id (optional).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        device_id = options.get("device")

        qs = (
            Receipt.objects
            .filter(fdms_receipt_id__isnull=False)
            .exclude(fdms_receipt_id=0)
            .exclude(receipt_hash="")
            .filter(Q(qr_code_value__isnull=True) | Q(qr_code_value=""))
            .select_related("device")
            .order_by("device__device_id", "fiscal_day_no", "receipt_global_no")
        )
        if device_id is not None:
            qs = qs.filter(device__device_id=device_id)

        receipts = list(qs)
        total = len(receipts)

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No receipts need QR backfill."))
            return

        self.stdout.write(f"Found {total} receipt(s) with receipt_hash but empty qr_code_value.")
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: not saving. Run without --dry-run to backfill."))
            for r in receipts[:20]:
                self.stdout.write(f"  Would process: device={r.device.device_id} global_no={r.receipt_global_no} type={r.receipt_type}")
            if total > 20:
                self.stdout.write(f"  ... and {total - 20} more.")
            return

        updated = 0
        skipped = 0
        errors = 0

        for receipt in receipts:
            try:
                before = (receipt.qr_code_value or "").strip()
                attach_qr_to_receipt(receipt)
                receipt.refresh_from_db()
                after = (receipt.qr_code_value or "").strip()
                if after and after != before:
                    updated += 1
                    self.stdout.write(f"  OK: device={receipt.device.device_id} receipt_global_no={receipt.receipt_global_no}")
                else:
                    skipped += 1
                    logger.debug(
                        "Backfill QR: no change for receipt %s (type=%s)",
                        receipt.receipt_global_no, receipt.receipt_type,
                    )
            except Exception as e:
                errors += 1
                logger.exception("Backfill QR failed for receipt %s", receipt.receipt_global_no)
                self.stderr.write(
                    self.style.ERROR(f"  Error device={receipt.device.device_id} receipt_global_no={receipt.receipt_global_no}: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Backfill complete: {updated} updated, {skipped} skipped (no QR generated), {errors} errors.")
        )
