"""Tests for GetConfigs source-of-truth enforcement. SubmitReceipt must be blocked if configs missing/stale."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from fiscal.models import FDMSConfigs, FiscalDevice, Receipt
from fiscal.services.config_service import (
    configs_are_fresh,
    enrich_receipt_taxes_with_tax_id,
    get_config_status,
    get_latest_configs,
    persist_configs,
    validate_against_configs,
)
from fiscal.services.receipt_service import submit_receipt


class ConfigServiceTests(TestCase):
    def test_configs_are_fresh_within_24h(self):
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        self.assertTrue(configs_are_fresh(cfg))

    def test_configs_stale_after_24h(self):
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now() - timedelta(hours=25),
        )
        self.assertFalse(configs_are_fresh(cfg))

    def test_persist_configs_parses_response(self):
        raw = {
            "applicableTaxes": [{"taxID": 1, "taxName": "VAT", "taxPercent": 15}],
            "allowedCurrencies": ["USD", "ZWG"],
        }
        cfg = persist_configs(123, raw)
        self.assertEqual(cfg.device_id, 123)
        self.assertEqual(len(cfg.tax_table), 1)
        self.assertEqual(cfg.tax_table[0]["taxID"], 1)
        self.assertEqual(cfg.allowed_currencies, ["USD", "ZWG"])

    def test_persist_configs_default_currencies(self):
        raw = {"applicableTaxes": []}
        cfg = persist_configs(456, raw)
        self.assertEqual(cfg.allowed_currencies, ["USD", "ZWG"])

    def test_get_latest_configs(self):
        FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[],
            allowed_currencies=["USD"],
            fetched_at=timezone.now() - timedelta(hours=2),
        )
        cfg2 = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        latest = get_latest_configs(1)
        self.assertEqual(latest.pk, cfg2.pk)

    def test_validate_currency_rejected(self):
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        with self.assertRaises(ValidationError) as cm:
            validate_against_configs("EUR", [], [], cfg)
        self.assertIn("Currency", str(cm.exception))
        self.assertIn("EUR", str(cm.exception))

    def test_validate_currency_accepted(self):
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        validate_against_configs("USD", [{"taxID": 1}], [], cfg)

    def test_validate_invalid_tax_id_rejected(self):
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        with self.assertRaises(ValidationError) as cm:
            validate_against_configs("USD", [{"taxID": 99}], [], cfg)
        self.assertIn("taxID", str(cm.exception))

    def test_validate_tax_code_only_accepted(self):
        """taxCode-only receipt_taxes pass when taxCode is in config."""
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 1, "taxCode": "A"}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        validate_against_configs(
            "USD",
            [{"taxCode": "A", "taxPercent": 15, "taxAmount": 10, "salesAmountWithTax": 100}],
            [{"receiptLineTaxCode": "A", "receiptLineName": "Item", "receiptLineTotal": 100}],
            cfg,
        )

    def test_enrich_receipt_taxes_adds_tax_id(self):
        cfg = FDMSConfigs.objects.create(
            device_id=1,
            raw_response={},
            tax_table=[{"taxID": 42, "taxCode": "VAT"}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now(),
        )
        taxes = [{"taxCode": "VAT", "taxPercent": 15, "taxAmount": 10, "salesAmountWithTax": 100}]
        enriched = enrich_receipt_taxes_with_tax_id(cfg, taxes)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["taxID"], 42)

    def test_get_config_status_missing(self):
        status = get_config_status(99999)
        self.assertEqual(status["status"], "MISSING")
        self.assertIsNone(status["lastSync"])


class SubmitReceiptBlockedTests(TestCase):
    """SubmitReceipt must be blocked when configs missing or stale."""

    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99999,
            device_serial_no="TEST",
            certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            is_registered=True,
            last_fiscal_day_no=1,
            last_receipt_global_no=0,
        )

    def test_submit_blocked_when_configs_missing(self):
        """Without FDMSConfigs, submit must return error."""
        receipt_obj, err = submit_receipt(
            device=self.device,
            fiscal_day_no=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            invoice_no="INV-1",
            receipt_lines=[{"lineAmount": 100, "lineQuantity": 1}],
            receipt_taxes=[{"taxID": 1, "taxAmount": 0, "salesAmountWithTax": 100}],
            receipt_payments=[{"paymentAmount": 100}],
            receipt_total=100.0,
        )
        self.assertIsNone(receipt_obj)
        self.assertIn("configs", (err or "").lower())
        self.assertIn("missing", (err or "").lower())

    def test_submit_blocked_when_configs_stale(self):
        FDMSConfigs.objects.create(
            device_id=self.device.device_id,
            raw_response={},
            tax_table=[{"taxID": 1}],
            allowed_currencies=["USD"],
            fetched_at=timezone.now() - timedelta(hours=25),
        )
        receipt_obj, err = submit_receipt(
            device=self.device,
            fiscal_day_no=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            invoice_no="INV-1",
            receipt_lines=[{"lineAmount": 100, "lineQuantity": 1}],
            receipt_taxes=[{"taxID": 1, "taxAmount": 0, "salesAmountWithTax": 100}],
            receipt_payments=[{"paymentAmount": 100}],
            receipt_total=100.0,
        )
        self.assertIsNone(receipt_obj)
        self.assertIn("stale", (err or "").lower())
