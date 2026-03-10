"""Tests for QB → FDMS auto-fiscalisation (tenant-scoped)."""

from unittest.mock import patch

from django.test import TestCase
from django.utils.timezone import now

from fiscal.models import FDMSConfigs, FiscalDevice, QuickBooksInvoice
from fiscal.services.qb_fiscalisation import fiscalise_qb_invoice, map_qb_invoice_to_fdms
from tenants.models import Tenant


def _make_tenant():
    return Tenant.objects.create(
        name="Test Tenant",
        slug="test-tenant-qb",
        device_id=99998,
        is_active=True,
    )


def _make_device(tenant=None):
    if tenant is None:
        tenant = _make_tenant()
    return FiscalDevice.all_objects.create(
        tenant=tenant,
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
        from tenants.context import set_current_tenant

        device = _make_device()
        FDMSConfigs.all_objects.create(
            tenant=device.tenant,
            device_id=device.device_id,
            tax_table=[{"taxID": 1, "taxCode": "VAT"}],
            allowed_currencies=["USD"],
            fetched_at=now(),
        )
        token = set_current_tenant(device.tenant)
        try:
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
        finally:
            from tenants.context import clear_current_tenant
            clear_current_tenant(token)


class FiscaliseQbInvoiceTests(TestCase):
    @patch("fiscal.services.qb_fiscalisation.submit_receipt", return_value=(None, "FDMS unavailable"))
    @patch("fiscal.services.fdms_device_service.FDMSDeviceService")
    def test_idempotency_same_invoice_same_record(self, mock_fdms_cls, mock_submit):
        from tenants.context import clear_current_tenant, set_current_tenant

        mock_fdms_cls.return_value.get_status.return_value = (
            {"lastFiscalDayNo": 1, "fiscalDayStatus": "FiscalDayOpened"},
            None,
        )
        device = _make_device()
        tenant = device.tenant
        FDMSConfigs.all_objects.create(
            tenant=tenant,
            device_id=device.device_id,
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=now(),
        )
        token = set_current_tenant(tenant)
        try:
            qb = {"Id": "dup-1", "TotalAmt": 50, "Line": [{"Amount": 50, "Qty": 1}]}
            inv1, _ = fiscalise_qb_invoice("dup-1", qb, tenant=tenant)
            self.assertIsNotNone(inv1)
            inv2, _ = fiscalise_qb_invoice("dup-1", qb, tenant=tenant)
            self.assertIsNotNone(inv2)
            self.assertEqual(inv1.pk, inv2.pk)
            self.assertEqual(QuickBooksInvoice.objects.filter(tenant=tenant, qb_invoice_id="dup-1").count(), 1)
        finally:
            clear_current_tenant(token)
