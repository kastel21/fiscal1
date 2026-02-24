"""Tests for QB → FDMS auto-fiscalisation."""

from unittest.mock import patch

from django.test import TestCase
from django.utils.timezone import now

from fiscal.models import FDMSConfigs, FiscalDevice, QuickBooksInvoice
from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice, map_qb_invoice_to_fdms


def _make_device():
    return FiscalDevice.objects.create(
        device_id=99999,
        device_serial_no="TEST",
        certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        is_registered=True,
        last_fiscal_day_no=1,
        fiscal_day_status="FiscalDayOpened",
    )


class MapQbInvoiceTests(TestCase):
    def test_map_qb_invoice_basic(self):
        device = _make_device()
        FDMSConfigs.objects.create(
            device_id=device.device_id,
            tax_table=[{"taxID": 1, "taxCode": "VAT"}],
            allowed_currencies=["USD"],
            fetched_at=now(),
        )
        qb = {
            "Id": "123",
            "TotalAmt": 100,
            "CurrencyRef": {"value": "USD"},
            "Line": [
                {"Description": "Item A", "Amount": 100, "Qty": 1},
            ],
        }
        payload, err = map_qb_invoice_to_fdms(qb, device)
        self.assertIsNone(err)
        self.assertEqual(payload["invoice_no"], "QB-123")
        self.assertEqual(payload["currency"], "USD")
        self.assertEqual(payload["receipt_total"], 100)
        self.assertEqual(len(payload["receipt_lines"]), 1)
        self.assertEqual(payload["receipt_lines"][0]["receiptLineName"], "Item A")


class FiscaliseQbInvoiceTests(TestCase):
    @patch("fiscal.services.qb_fiscalisation.submit_receipt", return_value=(None, "FDMS unavailable"))
    @patch("fiscal.services.qb_fiscalisation.FDMSDeviceService")
    def test_idempotency_same_invoice_same_record(self, mock_fdms_cls, mock_submit):
        mock_fdms_cls.return_value.get_status.return_value = {"lastFiscalDayNo": 1, "fiscalDayStatus": "FiscalDayOpened"}
        device = _make_device()
        FDMSConfigs.objects.create(
            device_id=device.device_id,
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=now(),
        )
        qb = {"Id": "dup-1", "TotalAmt": 50, "Line": [{"Amount": 50, "Qty": 1}]}
        inv1, _ = fiscalise_qb_invoice("dup-1", qb)
        self.assertIsNotNone(inv1)
        inv2, _ = fiscalise_qb_invoice("dup-1", qb)
        self.assertIsNotNone(inv2)
        self.assertEqual(inv1.pk, inv2.pk)
        self.assertEqual(QuickBooksInvoice.objects.filter(qb_invoice_id="dup-1").count(), 1)
