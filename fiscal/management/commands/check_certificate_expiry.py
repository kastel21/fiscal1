"""Management command: Check FDMS certificate expiry. Run daily via cron."""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from fiscal.models import FiscalDevice
from fiscal.services.device_api import DeviceApiService

logger = logging.getLogger("fiscal")


class Command(BaseCommand):
    help = "Check FDMS device certificate expiry. Alert if < 30 days remaining."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Alert threshold in days")

    def handle(self, *args, **options):
        threshold_days = options["days"]
        devices = FiscalDevice.objects.filter(is_registered=True)
        now = timezone.now()
        threshold = now + timedelta(days=threshold_days)

        for device in devices:
            service = DeviceApiService()
            try:
                data, err = service.get_config(device)
                if err:
                    self.stderr.write(f"Device {device.device_id}: GetConfig failed: {err}")
                    continue
            except Exception as e:
                self.stderr.write(f"Device {device.device_id}: Error: {e}")
                continue

            valid_till = device.certificate_valid_till
            if not valid_till:
                self.stdout.write(f"Device {device.device_id}: No certificate expiry from GetConfig")
                continue
            if valid_till < now:
                self.stderr.write(f"Device {device.device_id}: CERTIFICATE EXPIRED ({valid_till})")
            elif valid_till < threshold:
                self.stderr.write(
                    f"Device {device.device_id}: Certificate expires in {(valid_till - now).days} days"
                )
            else:
                self.stdout.write(f"Device {device.device_id}: Certificate valid until {valid_till}")
