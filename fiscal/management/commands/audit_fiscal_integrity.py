"""
Management command: Audit fiscal integrity.
Recalculates hashes, validates receipt chains, verifies signatures.
"""

from django.core.management.base import BaseCommand

from fiscal.models import FiscalDevice
from fiscal.services.audit_integrity import run_full_audit


class Command(BaseCommand):
    help = (
        "Audit fiscal integrity: recalculate hashes, detect mismatches, "
        "validate receipt chains, verify signatures."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Verbose output",
        )

    def handle(self, *args, **options):
        verbose = options["verbose"]
        devices = FiscalDevice.objects.filter(is_registered=True).count()

        if devices == 0:
            self.stdout.write(self.style.WARNING("No registered devices. Nothing to audit."))
            return

        self.stdout.write(f"Auditing {devices} device(s)...")
        result = run_full_audit()

        self.stdout.write(
            f"Checked: {result.devices_checked} devices, "
            f"{result.receipts_checked} receipts, "
            f"{result.fiscal_days_checked} fiscal days"
        )

        if not result.has_errors:
            self.stdout.write(self.style.SUCCESS("Integrity audit PASSED. No issues found."))
            return

        self.stdout.write(self.style.ERROR("Integrity audit FAILED. Issues found:"))

        if result.receipt_chain_errors:
            self.stdout.write(self.style.ERROR("\nReceipt chain errors (broken chain):"))
            for msg in result.receipt_chain_errors:
                self.stderr.write(f"  - {msg}")

        if result.receipt_hash_mismatches:
            self.stdout.write(self.style.ERROR("\nReceipt hash mismatches:"))
            for msg in result.receipt_hash_mismatches:
                self.stderr.write(f"  - {msg}")

        if result.receipt_signature_failures:
            self.stdout.write(self.style.ERROR("\nReceipt signature verification failures:"))
            for msg in result.receipt_signature_failures:
                self.stderr.write(f"  - {msg}")

        if result.fiscal_day_counter_errors:
            self.stdout.write(self.style.ERROR("\nFiscal day counter errors:"))
            for msg in result.fiscal_day_counter_errors:
                self.stderr.write(f"  - {msg}")
