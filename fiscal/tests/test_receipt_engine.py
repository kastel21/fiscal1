"""
Tests for receipt canonical builder, tax sorting, and cents formatting.
Snapshot tests fail if canonical format changes.
"""

from decimal import Decimal

from django.test import TestCase

from fiscal.services.receipt_engine import build_receipt_canonical_string


class ReceiptCanonicalBuilderTests(TestCase):
    """Tests for build_receipt_canonical_string."""

    def test_empty_taxes_no_previous_hash(self):
        """First receipt of day: no taxes, no previous hash."""
        canonical = build_receipt_canonical_string(
            device_id=12345,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-02-11T10:30:00",
            receipt_total=Decimal("15.00"),
            receipt_tax_lines=[],
            previous_receipt_hash=None,
        )
        self.assertEqual(
            canonical,
            "12345FISCALINVOICEUSD12025-02-11T10:30:001500",
        )

    def test_tax_sorting_by_tax_id_then_tax_code(self):
        """Tax lines sorted by taxID ascending, then taxCode alphabetical ascending."""
        taxes = [
            {"taxID": 2, "taxCode": "B", "taxPercent": 15, "taxAmount": 1.00, "salesAmountWithTax": 10.00},
            {"taxID": 1, "taxCode": "A", "taxPercent": 15, "taxAmount": 0.50, "salesAmountWithTax": 5.00},
            {"taxID": 2, "taxCode": "A", "taxPercent": 15, "taxAmount": 0.25, "salesAmountWithTax": 2.50},
        ]
        canonical = build_receipt_canonical_string(
            device_id=100,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-01-01T00:00:00",
            receipt_total=Decimal("17.50"),
            receipt_tax_lines=taxes,
            previous_receipt_hash=None,
        )
        # Expected order: taxID 1 (A), taxID 2 (A), taxID 2 (B)
        # Format: taxCode + taxPercent + taxAmountCents + salesAmountCents
        # 1A: A15.00 50 500, 2A: A15.00 25 250, 2B: B15.00 100 1000
        self.assertIn("A15.0050500", canonical)
        self.assertIn("A15.0025250", canonical)
        self.assertIn("B15.001001000", canonical)
        idx_1a = canonical.find("A15.0050500")
        idx_2a = canonical.find("A15.0025250")
        idx_2b = canonical.find("B15.001001000")
        self.assertLess(idx_1a, idx_2a)
        self.assertLess(idx_2a, idx_2b)

    def test_cents_formatting(self):
        """Monetary values converted to cents (ROUND_HALF_UP)."""
        taxes = [
            {"taxID": 1, "taxCode": "VAT", "taxPercent": 15, "taxAmount": 1.50, "salesAmountWithTax": 11.50},
            {"taxID": 2, "taxCode": "EX", "taxPercent": 0, "taxAmount": 0.01, "salesAmountWithTax": 1.01},
        ]
        canonical = build_receipt_canonical_string(
            device_id=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-01-01T00:00:00",
            receipt_total=Decimal("12.51"),
            receipt_tax_lines=taxes,
            previous_receipt_hash=None,
        )
        # Format: taxCode + taxPercent + taxAmountCents + salesAmountCents
        # VAT: 1.50 -> 150, 11.50 -> 1150
        self.assertIn("VAT15.001501150", canonical)
        # EX: 0.01 -> 1, 1.01 -> 101
        self.assertIn("EX0.001101", canonical)

    def test_cents_rounding_half_up(self):
        """Verify ROUND_HALF_UP: 1.995 -> 200, 1.994 -> 199."""
        taxes = [
            {"taxID": 1, "taxCode": "T", "taxPercent": 10, "taxAmount": 1.995, "salesAmountWithTax": 19.995},
            {"taxID": 2, "taxCode": "T", "taxPercent": 10, "taxAmount": 1.994, "salesAmountWithTax": 19.994},
        ]
        canonical = build_receipt_canonical_string(
            device_id=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-01-01T00:00:00",
            receipt_total=Decimal("20.00"),
            receipt_tax_lines=taxes,
            previous_receipt_hash=None,
        )
        # Format: taxCode + taxPercent + taxAmountCents + salesAmountCents
        # 1.995 -> 200, 19.995 -> 2000
        self.assertIn("T10.002002000", canonical)
        # 1.994 -> 199, 19.994 -> 1999
        self.assertIn("T10.001991999", canonical)

    def test_currency_uppercase(self):
        """Currency normalised to uppercase."""
        canonical = build_receipt_canonical_string(
            device_id=1,
            receipt_type="FiscalInvoice",
            receipt_currency="usd",
            receipt_global_no=1,
            receipt_date="2025-01-01T00:00:00",
            receipt_total=Decimal("1.00"),
            receipt_tax_lines=[],
            previous_receipt_hash=None,
        )
        self.assertIn("USD", canonical)
        self.assertNotIn("usd", canonical)

    def test_exempt_tax_no_tax_percent_in_canonical(self):
        """Exempt (taxPercent None or missing) must NOT include taxPercent in canonical (FDMS spec, avoids RCPT020)."""
        taxes_exempt = [
            {"taxID": 1, "taxCode": "EX", "taxAmount": 0, "salesAmountWithTax": 100.00},
        ]
        canonical = build_receipt_canonical_string(
            device_id=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-01-01T00:00:00",
            receipt_total=Decimal("100.00"),
            receipt_tax_lines=taxes_exempt,
            previous_receipt_hash=None,
        )
        # Exempt segment must be taxCode + taxAmount + salesAmountWithTax (no percent)
        self.assertIn("EX010000", canonical)
        self.assertNotIn("EX0.00", canonical, "Exempt must not include 0.00 in canonical")

    def test_previous_receipt_hash_appended(self):
        """Previous receipt hash appended when present."""
        prev_hash = "dGVzdF9oYXNoX2Jhc2U2NA=="
        canonical = build_receipt_canonical_string(
            device_id=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=2,
            receipt_date="2025-01-01T00:00:00",
            receipt_total=Decimal("2.00"),
            receipt_tax_lines=[],
            previous_receipt_hash=prev_hash,
        )
        self.assertTrue(canonical.endswith(prev_hash))
        self.assertIn(prev_hash, canonical)


class ReceiptCanonicalSnapshotTests(TestCase):
    """Snapshot tests: fixed spec examples. Fail if canonical format changes."""

    def test_snapshot_minimal_first_receipt(self):
        """Snapshot: minimal first receipt of day (FDMS spec example)."""
        canonical = build_receipt_canonical_string(
            device_id=12345,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=1,
            receipt_date="2025-02-11T10:30:00",
            receipt_total=Decimal("15.00"),
            receipt_tax_lines=[],
            previous_receipt_hash=None,
        )
        self.assertEqual(
            canonical,
            "12345FISCALINVOICEUSD12025-02-11T10:30:001500",
            "Receipt canonical format changed. Update FDMS integration if intentional.",
        )

    def test_snapshot_single_tax_line(self):
        """Snapshot: receipt with one tax line."""
        taxes = [
            {"taxID": 1, "taxCode": "VAT", "taxPercent": 15, "taxAmount": 2.30, "salesAmountWithTax": 15.30},
        ]
        canonical = build_receipt_canonical_string(
            device_id=999,
            receipt_type="FiscalInvoice",
            receipt_currency="ZWG",
            receipt_global_no=42,
            receipt_date="2025-01-15T14:00:00",
            receipt_total=Decimal("15.30"),
            receipt_tax_lines=taxes,
            previous_receipt_hash=None,
        )
        self.assertEqual(
            canonical,
            "999FISCALINVOICEZWG422025-01-15T14:00:001530VAT15.002301530",
            "Receipt canonical format changed. Update FDMS integration if intentional.",
        )

    def test_snapshot_multiple_taxes_chain(self):
        """Snapshot: receipt with multiple taxes and chain hash."""
        taxes = [
            {"taxID": 1, "taxCode": "A", "taxPercent": 10, "taxAmount": 1.00, "salesAmountWithTax": 11.00},
            {"taxID": 2, "taxCode": "B", "taxPercent": 10, "taxAmount": 2.00, "salesAmountWithTax": 22.00},
        ]
        prev_hash = "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo="
        canonical = build_receipt_canonical_string(
            device_id=5000,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            receipt_global_no=10,
            receipt_date="2025-06-01T12:00:00",
            receipt_total=Decimal("33.00"),
            receipt_tax_lines=taxes,
            previous_receipt_hash=prev_hash,
        )
        self.assertEqual(
            canonical,
            "5000FISCALINVOICEUSD102025-06-01T12:00:003300A10.001001100B10.002002200YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo=",
            "Receipt canonical format changed. Update FDMS integration if intentional.",
        )
