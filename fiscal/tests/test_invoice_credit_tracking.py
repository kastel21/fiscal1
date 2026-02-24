"""Unit tests for invoice credit tracking."""

from decimal import Decimal

from django.test import TestCase

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.invoice_credit_service import (
    update_invoice_credit_status,
    validate_credit_against_invoice,
)
from fiscal.services.credit_allocation_service import get_remaining_balance


class InvoiceCreditTrackingTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=88888,
            device_serial_no="TEST",
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )

    def _create_invoice(self, total="100.00"):
        return Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            document_type="INVOICE",
            receipt_total=Decimal(total),
            fdms_receipt_id=101,
        )

    def _create_credit_note(self, invoice, total="-50.00", global_no=2):
        return Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=global_no,
            receipt_counter=global_no,
            currency="USD",
            receipt_type="CreditNote",
            document_type="CREDIT_NOTE",
            receipt_total=Decimal(total),
            original_invoice=invoice,
            original_receipt_global_no=invoice.receipt_global_no,
            fdms_receipt_id=100 + global_no,
        )

    def test_no_credit_issued(self):
        inv = self._create_invoice("100.00")
        self.assertEqual(inv.credited_total, Decimal("0"))
        self.assertEqual(inv.remaining_balance, Decimal("100"))
        update_invoice_credit_status(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.credit_status, "ISSUED")

    def test_partial_credit(self):
        inv = self._create_invoice("100.00")
        self._create_credit_note(inv, "-40.00", 2)
        inv.refresh_from_db()
        self.assertEqual(inv.credited_total, Decimal("40"))
        self.assertEqual(inv.remaining_balance, Decimal("60"))
        update_invoice_credit_status(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.credit_status, "PARTIALLY_CREDITED")

    def test_full_credit(self):
        inv = self._create_invoice("100.00")
        self._create_credit_note(inv, "-100.00", 2)
        inv.refresh_from_db()
        self.assertEqual(inv.credited_total, Decimal("100"))
        self.assertEqual(inv.remaining_balance, Decimal("0"))
        update_invoice_credit_status(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.credit_status, "FULLY_CREDITED")

    def test_multiple_credit_notes(self):
        inv = self._create_invoice("100.00")
        self._create_credit_note(inv, "-30.00", 2)
        self._create_credit_note(inv, "-40.00", 3)
        inv.refresh_from_db()
        self.assertEqual(inv.credited_total, Decimal("70"))
        self.assertEqual(inv.remaining_balance, Decimal("30"))
        update_invoice_credit_status(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.credit_status, "PARTIALLY_CREDITED")

    def test_rounding_edge_case(self):
        inv = self._create_invoice("33.33")
        self._create_credit_note(inv, "-33.33", 2)
        inv.refresh_from_db()
        self.assertLessEqual(abs(inv.credited_total + inv.remaining_balance - inv.receipt_total), Decimal("0.01"))

    def test_credited_plus_remaining_equals_total(self):
        inv = self._create_invoice("100.00")
        self._create_credit_note(inv, "-50.00", 2)
        inv.refresh_from_db()
        total = inv.receipt_total or Decimal("0")
        self.assertLessEqual(
            abs(inv.credited_total + inv.remaining_balance - total),
            Decimal("0.01"),
        )

    def test_over_credit_rejected(self):
        inv = self._create_invoice("100.00")
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            validate_credit_against_invoice(inv, Decimal("150"))
        self.assertIn("exceed", str(ctx.exception).lower())

    def test_fully_credited_rejected(self):
        inv = self._create_invoice("100.00")
        self._create_credit_note(inv, "-100.00", 2)
        update_invoice_credit_status(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.credit_status, "FULLY_CREDITED")
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            validate_credit_against_invoice(inv, Decimal("1"))
        self.assertIn("fully credited", str(ctx.exception).lower())

    def test_credit_note_cannot_be_credited(self):
        inv = self._create_invoice("100.00")
        cn = self._create_credit_note(inv, "-50.00", 2)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError) as ctx:
            validate_credit_against_invoice(cn, Decimal("10"))
        self.assertIn("credit note", str(ctx.exception).lower())

    def test_get_remaining_balance_matches_remaining_balance_property(self):
        inv = self._create_invoice("100.00")
        self._create_credit_note(inv, "-30.00", 2)
        inv.refresh_from_db()
        self.assertEqual(get_remaining_balance(inv), inv.remaining_balance)
