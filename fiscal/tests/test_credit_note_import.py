"""Tests for Credit Note Excel import. Validation, balance, blocking rules."""

from decimal import Decimal
from io import BytesIO

from django.test import TestCase

from openpyxl import Workbook

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.credit_note_import_service import (
    get_remaining_creditable_balance,
    lines_to_receipt_payload,
    search_fiscalised_invoices,
    validate_credit_note_import,
)
from fiscal.services.excel_parser import parse_excel


class RemainingBalanceTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99999,
            device_serial_no="TEST",
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )

    def test_remaining_balance_without_credits(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("1000.00"),
            fdms_receipt_id=101,
        )
        remaining = get_remaining_creditable_balance(inv)
        self.assertEqual(float(remaining), 1000.0)

    def test_remaining_balance_after_credit(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("1000.00"),
            fdms_receipt_id=101,
        )
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=2,
            receipt_counter=2,
            currency="USD",
            receipt_type="CreditNote",
            receipt_total=Decimal("-200.00"),
            original_receipt_global_no=1,
            fdms_receipt_id=102,
        )
        remaining = get_remaining_creditable_balance(inv)
        self.assertEqual(float(remaining), 800.0)


class ValidateCreditNoteImportTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=88888,
            device_serial_no="TEST",
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )
        self.inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("500.00"),
            fdms_receipt_id=201,
        )

    def test_credit_exceeds_balance_blocked(self):
        errors = validate_credit_note_import(
            self.inv,
            [{"line_total": 100}, {"line_total": 200}],
            credit_total=600.0,
            currency="USD",
            device=self.device,
            config_status="OK",
        )
        self.assertTrue(any("exceed" in e.lower() for e in errors))

    def test_currency_mismatch_blocked(self):
        errors = validate_credit_note_import(
            self.inv,
            [{"line_total": 100}],
            credit_total=100.0,
            currency="ZWG",
            device=self.device,
            config_status="OK",
        )
        self.assertTrue(any("currency" in e.lower() for e in errors))

    def test_missing_original_invoice_blocked(self):
        errors = validate_credit_note_import(
            None,
            [{"line_total": 100}],
            credit_total=100.0,
            currency="USD",
            device=self.device,
            config_status="OK",
        )
        self.assertTrue(any("original" in e.lower() or "invoice" in e.lower() for e in errors))


class LinesToReceiptPayloadTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=77777,
            device_serial_no="TEST",
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )
        self.inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("100.00"),
            receipt_taxes=[{"taxID": 1, "taxCode": "VAT"}],
            fdms_receipt_id=301,
        )

    def test_lines_mapped_correctly(self):
        lines = [{"quantity": 2, "description": "Item A", "line_total": 50}]
        rl, rt, rp = lines_to_receipt_payload(lines, self.inv, 50.0)
        self.assertEqual(len(rl), 1)
        self.assertEqual(rl[0]["receiptLineQuantity"], 1)
        self.assertEqual(float(rl[0]["receiptLineTotal"]), 50.0)
        self.assertIn("Credit allocation", rl[0]["receiptLineName"])


class ExcelParserTests(TestCase):
    def test_parse_excel_detects_lines(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Qty", "Description", "Unit Price", "Total"])
        ws.append([2, "Product A", 25.0, 50.0])
        ws.append([1, "Product B", 30.0, 30.0])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        lines, meta = parse_excel(buf.read())
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["quantity"], 2)
        self.assertEqual(lines[0]["line_total"], 50.0)
        self.assertEqual(lines[0]["description"], "Product A")
        self.assertTrue(lines[0]["from_excel"])
