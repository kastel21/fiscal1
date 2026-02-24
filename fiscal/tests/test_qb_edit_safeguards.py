"""Tests for QB edit safeguards post-fiscalisation."""

import json
from decimal import Decimal

from django.test import Client, TestCase

from fiscal.models import FiscalDevice, FiscalEditAttempt, Receipt
from fiscal.services.qb_edit_safeguards import (
    fiscal_fields_changed,
    validate_qb_invoice_update,
)


def _make_test_device(device_id: int = 99999) -> FiscalDevice:
    """Create a FiscalDevice for testing."""
    return FiscalDevice.objects.create(
        device_id=device_id,
        device_serial_no="TEST-SN",
        certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        is_registered=True,
    )


def _make_receipt(device, fiscalised: bool = True, **kwargs) -> Receipt:
    """Create a Receipt with optional fiscalisation."""
    defaults = {
        "fiscal_day_no": 1,
        "receipt_global_no": 1000,
        "currency": "USD",
        "receipt_total": Decimal("100.00"),
        "receipt_lines": [
            {"receiptLineQuantity": 1, "receiptLineName": "Item A", "receiptLineTotal": 100},
        ],
        "receipt_taxes": [{"salesAmountWithTax": 15}],
        "receipt_payments": [{"paymentAmount": 100}],
    }
    defaults.update(kwargs)
    rec = Receipt.objects.create(device=device, **defaults)
    if fiscalised:
        rec.fdms_receipt_id = 12345
        rec.save(update_fields=["fdms_receipt_id"])
    return rec


class FiscalFieldsChangedTests(TestCase):
    """Tests for fiscal_fields_changed."""

    def test_no_change(self):
        orig = {"currency": "USD", "receipt_total": 100.0, "receipt_lines": [], "receipt_taxes": [], "receipt_payments": []}
        att = orig.copy()
        changed, diff = fiscal_fields_changed(orig, att)
        self.assertFalse(changed)
        self.assertEqual(diff, [])

    def test_currency_change(self):
        orig = {"currency": "USD", "receipt_total": 100.0, "receipt_lines": [], "receipt_taxes": [], "receipt_payments": []}
        att = orig.copy()
        att["currency"] = "ZWG"
        changed, diff = fiscal_fields_changed(orig, att)
        self.assertTrue(changed)
        self.assertIn("currency", diff)

    def test_total_change(self):
        orig = {"currency": "USD", "receipt_total": 100.0, "receipt_lines": [], "receipt_taxes": [], "receipt_payments": []}
        att = orig.copy()
        att["receipt_total"] = 99.0
        changed, diff = fiscal_fields_changed(orig, att)
        self.assertTrue(changed)
        self.assertIn("totals", diff)

    def test_line_items_change(self):
        orig = {"currency": "USD", "receipt_total": 100.0, "receipt_lines": [{"receiptLineQuantity": 1, "receiptLineName": "A", "receiptLineTotal": 100}], "receipt_taxes": [], "receipt_payments": []}
        att = orig.copy()
        att["receipt_lines"] = [{"receiptLineQuantity": 2, "receiptLineName": "A", "receiptLineTotal": 200}]
        changed, diff = fiscal_fields_changed(orig, att)
        self.assertTrue(changed)
        self.assertIn("line_items", diff)


class ValidateQbInvoiceUpdateTests(TestCase):
    """Tests for validate_qb_invoice_update."""

    def test_non_fiscalised_allows(self):
        """Non-fiscalised receipts allow any update."""
        device = _make_test_device()
        rec = _make_receipt(device, fiscalised=False)
        attempted = {"receiptTotal": 999, "currency": "ZWG"}
        allowed, reason = validate_qb_invoice_update(rec, attempted, source="QB", actor="user")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_fiscalised_no_change_allows(self):
        """Fiscalised receipt with no fiscal field change allows."""
        device = _make_test_device()
        rec = _make_receipt(device, fiscalised=True)
        attempted = {
            "receiptTotal": 100.0,
            "receiptCurrency": "USD",
            "receiptLines": rec.receipt_lines,
            "receiptTaxes": rec.receipt_taxes,
            "receiptPayments": rec.receipt_payments,
        }
        allowed, reason = validate_qb_invoice_update(rec, attempted, source="QB", actor="user")
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_fiscalised_total_change_blocks(self):
        """Fiscalised receipt with total change blocks and logs."""
        device = _make_test_device()
        rec = _make_receipt(device, fiscalised=True)
        attempted = {
            "receiptTotal": 99.0,
            "receiptCurrency": "USD",
            "receiptLines": rec.receipt_lines,
            "receiptTaxes": rec.receipt_taxes,
            "receiptPayments": rec.receipt_payments,
        }
        allowed, reason = validate_qb_invoice_update(rec, attempted, source="QB", actor="user")
        self.assertFalse(allowed)
        self.assertIn("totals", reason)
        self.assertIn("credit note", reason)
        self.assertEqual(FiscalEditAttempt.objects.filter(receipt=rec).count(), 1)
        attempt = FiscalEditAttempt.objects.get(receipt=rec)
        self.assertTrue(attempt.blocked)
        self.assertIn("totals", attempt.diff_summary)


class ApiQbValidateInvoiceUpdateTests(TestCase):
    """Tests for api_qb_validate_invoice_update endpoint."""

    def setUp(self):
        self.client = Client()
        self.device = _make_test_device()
        self.receipt = _make_receipt(self.device, fiscalised=True, invoice_no="INV-001")

    def _post(self, data):
        return self.client.post(
            "/api/integrations/quickbooks/validate-update/",
            data=json.dumps(data),
            content_type="application/json",
        )

    def test_receipt_not_found_404(self):
        resp = self._post({"receipt_id": 999999, "invoice": {"receiptTotal": 100}})
        self.assertEqual(resp.status_code, 404)
        body = json.loads(resp.content)
        self.assertFalse(body["allowed"])
        self.assertIn("not found", body["reason"])

    def test_allowed_no_change_200(self):
        data = {
            "receipt_id": self.receipt.pk,
            "invoice": {
                "receiptTotal": 100.0,
                "receiptCurrency": "USD",
                "receiptLines": self.receipt.receipt_lines,
                "receiptTaxes": self.receipt.receipt_taxes,
                "receiptPayments": self.receipt.receipt_payments,
            },
        }
        resp = self._post(data)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content)
        self.assertTrue(body["allowed"])

    def test_blocked_fiscal_change_403(self):
        data = {
            "receipt_id": self.receipt.pk,
            "invoice": {
                "receiptTotal": 99.0,
                "receiptCurrency": "USD",
                "receiptLines": self.receipt.receipt_lines,
                "receiptTaxes": self.receipt.receipt_taxes,
                "receiptPayments": self.receipt.receipt_payments,
            },
        }
        resp = self._post(data)
        self.assertEqual(resp.status_code, 403)
        body = json.loads(resp.content)
        self.assertFalse(body["allowed"])
        self.assertIn("totals", body["reason"])

    def test_lookup_by_invoice_no(self):
        data = {
            "invoice_no": "INV-001",
            "invoice": {
                "receiptTotal": 100.0,
                "receiptCurrency": "USD",
                "receiptLines": self.receipt.receipt_lines,
                "receiptTaxes": self.receipt.receipt_taxes,
                "receiptPayments": self.receipt.receipt_payments,
            },
        }
        resp = self._post(data)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(json.loads(resp.content)["allowed"])
