"""Unit tests for credit allocation service."""

from decimal import Decimal

from django.test import TestCase

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.credit_allocation_service import (
    allocate_credit_proportionally,
    CreditAllocationError,
    get_remaining_balance,
    safe_quantize,
    validate_credit_amount,
)


class SafeQuantizeTests(TestCase):
    def test_rounds_half_up(self):
        self.assertEqual(safe_quantize(Decimal("1.125")), Decimal("1.13"))
        self.assertEqual(safe_quantize(Decimal("1.135")), Decimal("1.14"))
        self.assertEqual(safe_quantize(1.125), Decimal("1.13"))


class GetRemainingBalanceTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99998,
            device_serial_no="TEST",
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )

    def test_full_balance_without_credits(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("1000.00"),
            fdms_receipt_id=101,
        )
        self.assertEqual(float(get_remaining_balance(inv)), 1000.0)

    def test_remaining_after_credit(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
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
        self.assertEqual(float(get_remaining_balance(inv)), 800.0)


class ValidateCreditAmountTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99997,
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
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("500.00"),
            fdms_receipt_id=201,
        )

    def test_zero_rejected(self):
        with self.assertRaises(CreditAllocationError) as ctx:
            validate_credit_amount(self.inv, Decimal("0"))
        self.assertIn("positive", str(ctx.exception).lower())

    def test_negative_rejected(self):
        with self.assertRaises(CreditAllocationError) as ctx:
            validate_credit_amount(self.inv, Decimal("-10"))
        self.assertIn("positive", str(ctx.exception).lower())

    def test_over_credit_rejected(self):
        with self.assertRaises(CreditAllocationError) as ctx:
            validate_credit_amount(self.inv, Decimal("600"))
        self.assertIn("exceed", str(ctx.exception).lower())

    def test_valid_amount_accepted(self):
        validate_credit_amount(self.inv, Decimal("500"))
        validate_credit_amount(self.inv, Decimal("250"))


class AllocateCreditProportionallyTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99996,
            device_serial_no="TEST",
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )

    def test_full_credit_single_tax(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("100.00"),
            receipt_taxes=[{
                "taxID": 1,
                "taxCode": "VAT",
                "taxPercent": 15.5,
                "taxAmount": 13.45,
                "salesAmountWithTax": 100.00,
            }],
            fdms_receipt_id=301,
        )
        result = allocate_credit_proportionally(inv, Decimal("100"))
        self.assertEqual(result["credit_total"], 100.0)
        total_allocated = sum(a["salesAmountWithTax"] for a in result["receipt_taxes"])
        self.assertEqual(round(total_allocated, 2), 100.0)

    def test_partial_credit_proportional(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("100.00"),
            receipt_taxes=[{
                "taxID": 1,
                "taxCode": "VAT",
                "taxPercent": 15.5,
                "taxAmount": 13.45,
                "salesAmountWithTax": 100.00,
            }],
            fdms_receipt_id=302,
        )
        result = allocate_credit_proportionally(inv, Decimal("50"))
        self.assertEqual(result["credit_total"], 50.0)
        total_allocated = sum(a["salesAmountWithTax"] for a in result["receipt_taxes"])
        self.assertEqual(round(total_allocated, 2), 50.0)

    def test_multi_tax_preserves_ratios(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("100.00"),
            receipt_taxes=[
                {"taxID": 1, "taxCode": "1", "taxPercent": 15.5, "taxAmount": 7.75, "salesAmountWithTax": 50.00},
                {"taxID": 2, "taxCode": "2", "taxPercent": 0, "taxAmount": 0, "salesAmountWithTax": 50.00},
            ],
            fdms_receipt_id=303,
        )
        result = allocate_credit_proportionally(inv, Decimal("50"))
        self.assertEqual(result["credit_total"], 50.0)
        total_allocated = sum(a["salesAmountWithTax"] for a in result["receipt_taxes"])
        self.assertEqual(round(total_allocated, 2), 50.0)
        self.assertEqual(len(result["receipt_taxes"]), 2)

    def test_rounding_correction(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("33.33"),
            receipt_taxes=[{
                "taxID": 1,
                "taxCode": "VAT",
                "taxPercent": 15,
                "taxAmount": 4.35,
                "salesAmountWithTax": 33.33,
            }],
            fdms_receipt_id=304,
        )
        result = allocate_credit_proportionally(inv, Decimal("11.11"))
        total_allocated = sum(a["salesAmountWithTax"] for a in result["receipt_taxes"])
        self.assertEqual(round(total_allocated, 2), 11.11)
        self.assertEqual(result["credit_total"], 11.11)

    def test_over_credit_raises(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("100.00"),
            fdms_receipt_id=305,
        )
        with self.assertRaises(CreditAllocationError):
            allocate_credit_proportionally(inv, Decimal("150"))

    def test_zero_credit_raises(self):
        inv = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FISCALINVOICE",
            receipt_total=Decimal("100.00"),
            fdms_receipt_id=306,
        )
        with self.assertRaises(CreditAllocationError):
            allocate_credit_proportionally(inv, Decimal("0"))
