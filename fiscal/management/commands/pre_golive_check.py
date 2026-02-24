"""
Management command: Pre-go-live checklist.
Run before production deployment:
- Close test fiscal day
- Verify test receipts submitted
- Run integrity audit
"""

from django.core.management.base import BaseCommand

from fiscal.models import FiscalDevice, Receipt


class Command(BaseCommand):
    help = (
        "Pre-go-live checklist: close test fiscal day, verify test receipts, run integrity audit. "
        "Exit code 0 = pass, 1 = fail."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-close",
            action="store_true",
            help="Do not attempt to close open fiscal day (manual close required)",
        )
        parser.add_argument(
            "--min-receipts",
            type=int,
            default=1,
            help="Minimum number of test receipts expected (default: 1)",
        )

    def handle(self, *args, **options):
        skip_close = options["skip_close"]
        min_receipts = options["min_receipts"]
        failed = False

        devices = FiscalDevice.objects.filter(is_registered=True)
        if not devices.exists():
            self.stdout.write(self.style.WARNING("No registered devices. Register a device first."))
            return 1

        for device in devices:
            self.stdout.write(f"\n--- Device {device.device_id} ---")

            # 1. Check fiscal day status - warn if open
            status = device.fiscal_day_status or ""
            last_day = device.last_fiscal_day_no
            if status == "FiscalDayOpened":
                self.stdout.write(
                    self.style.WARNING(
                        f"  Fiscal day {last_day} is OPEN. Close before go-live."
                    )
                )
                if not skip_close:
                    self.stdout.write("  Attempting to close fiscal day via CloseDay API...")
                    try:
                        from fiscal.services.device_api import DeviceApiService
                        svc = DeviceApiService()
                        data, err = svc.close_day(device)
                        if err:
                            self.stdout.write(self.style.ERROR(f"  CloseDay failed: {err}"))
                            failed = True
                        else:
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  CloseDay initiated. operationID: {data.get('operationID', 'N/A')}"
                                )
                            )
                            self.stdout.write(
                                "  Poll GetStatus until FiscalDayClosed. Re-run this command after close."
                            )
                            failed = True
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"  CloseDay error: {e}"))
                        failed = True
                else:
                    failed = True
            elif status == "FiscalDayCloseInitiated":
                self.stdout.write(
                    self.style.WARNING(
                        "  Fiscal day close in progress. Wait for FiscalDayClosed, then re-run."
                    )
                )
                failed = True
            elif status in ("FiscalDayClosed", "FiscalDayCloseFailed"):
                self.stdout.write(self.style.SUCCESS(f"  Fiscal day status: {status}"))
            else:
                self.stdout.write(f"  Fiscal day status: {status or 'unknown'}")

            # 2. Verify test receipts
            count = Receipt.objects.filter(device=device).count()
            if count < min_receipts:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Only {count} receipt(s). Submit at least {min_receipts} test receipt(s)."
                    )
                )
                failed = True
            else:
                self.stdout.write(self.style.SUCCESS(f"  Receipts: {count} (>= {min_receipts})"))

        # 3. Run integrity audit
        self.stdout.write("\n--- Integrity Audit ---")
        from fiscal.services.audit_integrity import run_full_audit
        result = run_full_audit()
        if result.has_errors:
            self.stdout.write(self.style.ERROR("Integrity audit FAILED."))
            for msg in result.receipt_chain_errors + result.receipt_hash_mismatches + result.receipt_signature_failures + result.fiscal_day_counter_errors:
                self.stderr.write(f"  - {msg}")
            failed = True
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Integrity audit PASSED ({result.receipts_checked} receipts, "
                    f"{result.fiscal_days_checked} fiscal days)."
                )
            )

        if failed:
            self.stdout.write(self.style.ERROR("\nPre-go-live checklist FAILED. Address items above."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("\nPre-go-live checklist PASSED."))
