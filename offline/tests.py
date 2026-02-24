"""Tests for offline mode."""

from decimal import Decimal

from django.test import TestCase

from fiscal.models import FiscalDevice, Receipt
from offline.models import OfflineReceiptQueue
from offline.services.queue_manager import QueueManager
from offline.services.offline_detector import OfflineDetector


def _make_device():
    return FiscalDevice.objects.create(
        device_id=99999,
        device_serial_no="TEST",
        certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        is_registered=True,
    )


class QueueManagerTests(TestCase):
    def test_enqueue_and_size(self):
        device = _make_device()
        rec = Receipt.objects.create(
            device=device,
            fiscal_day_no=1,
            receipt_global_no=100,
            currency="USD",
            receipt_total=Decimal("10.00"),
            receipt_lines=[],
            receipt_taxes=[],
            receipt_payments=[],
        )
        QueueManager.enqueue(rec)
        self.assertEqual(QueueManager.queue_size(device=device), 1)
        self.assertEqual(OfflineReceiptQueue.objects.filter(state="QUEUED").count(), 1)
