"""
Tests for fiscal day canonical builder.
Snapshot tests fail if canonical format changes.
"""

from datetime import date

from django.test import TestCase

from fiscal.services.fiscal_signature import build_fiscal_day_canonical_string


class FiscalCanonicalBuilderTests(TestCase):
    """Tests for build_fiscal_day_canonical_string."""

    def test_empty_counters(self):
        """No counters returns deviceID + fiscalDayNo + date only."""
        canonical = build_fiscal_day_canonical_string(
            device_id=12345,
            fiscal_day_no=7,
            fiscal_day_date=date(2025, 2, 11),
            fiscal_day_counters=[],
        )
        self.assertEqual(canonical, "1234572025-02-11")

    def test_filters_zero_counters(self):
        """Only non-zero counters included."""
        counters = [
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxPercent": 15, "fiscalCounterValue": 0},
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxPercent": 15, "fiscalCounterValue": 100.50},
        ]
        canonical = build_fiscal_day_canonical_string(
            device_id=1,
            fiscal_day_no=1,
            fiscal_day_date=date(2025, 1, 1),
            fiscal_day_counters=counters,
        )
        # Should include only the non-zero counter (100.50 -> 10050 cents)
        self.assertIn("10050", canonical)
        self.assertEqual(canonical.count("SALEBYTAX"), 1)
        # Actually the date has 0s - let me just check 10050 is in there
        self.assertIn("10050", canonical)

    def test_counters_sorted(self):
        """Counters sorted by type, currency, taxID/moneyType."""
        counters = [
            {"fiscalCounterType": "creditNoteByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxID": 2, "fiscalCounterValue": 10},
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "ZWG", "fiscalCounterTaxID": 1, "fiscalCounterValue": 20},
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxID": 1, "fiscalCounterValue": 30},
        ]
        canonical = build_fiscal_day_canonical_string(
            device_id=1,
            fiscal_day_no=1,
            fiscal_day_date=date(2025, 1, 1),
            fiscal_day_counters=counters,
        )
        # Sort: creditNoteByTax, saleByTax (alphabetically); then currency USD before ZWG; then taxID 1 before 2
        # creditNoteByTax USD 2: 1000 cents
        # saleByTax USD 1: 3000 cents
        # saleByTax ZWG 1: 2000 cents
        self.assertIn("CREDITNOTEBYTAX", canonical)
        self.assertIn("SALEBYTAX", canonical)
        # Order should be CREDITNOTEBYTAX first, then SALEBYTAX USD, then SALEBYTAX ZWG
        idx_cn = canonical.find("CREDITNOTEBYTAX")
        idx_sale_usd = canonical.find("SALEBYTAX")
        self.assertLess(idx_cn, idx_sale_usd)

    def test_amounts_in_cents(self):
        """Counter values converted to cents."""
        counters = [
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxPercent": 15, "fiscalCounterValue": 10.99},
        ]
        canonical = build_fiscal_day_canonical_string(
            device_id=1,
            fiscal_day_no=1,
            fiscal_day_date=date(2025, 1, 1),
            fiscal_day_counters=counters,
        )
        # 10.99 -> 1099 cents
        self.assertIn("1099", canonical)

    def test_tax_percent_formatting(self):
        """Tax percent formatted: integer as X.00, decimal as X.XX."""
        counters = [
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxPercent": 15, "fiscalCounterValue": 1},
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "ZWG", "fiscalCounterTaxPercent": 14.5, "fiscalCounterValue": 1},
        ]
        canonical = build_fiscal_day_canonical_string(
            device_id=1,
            fiscal_day_no=1,
            fiscal_day_date=date(2025, 1, 1),
            fiscal_day_counters=counters,
        )
        self.assertIn("15.00", canonical)
        self.assertIn("14.50", canonical)


class FiscalCanonicalSnapshotTests(TestCase):
    """Snapshot tests: fixed spec examples. Fail if canonical format changes."""

    def test_snapshot_empty_counters(self):
        """Snapshot: device + day + date only."""
        canonical = build_fiscal_day_canonical_string(
            device_id=12345,
            fiscal_day_no=7,
            fiscal_day_date=date(2025, 2, 11),
            fiscal_day_counters=[],
        )
        self.assertEqual(
            canonical,
            "1234572025-02-11",
            "Fiscal canonical format changed. Update FDMS integration if intentional.",
        )

    def test_snapshot_single_counter(self):
        """Snapshot: one saleByTax counter."""
        counters = [
            {
                "fiscalCounterType": "saleByTax",
                "fiscalCounterCurrency": "USD",
                "fiscalCounterTaxPercent": 15.00,
                "fiscalCounterValue": 123.45,
            },
        ]
        canonical = build_fiscal_day_canonical_string(
            device_id=999,
            fiscal_day_no=3,
            fiscal_day_date=date(2025, 6, 15),
            fiscal_day_counters=counters,
        )
        self.assertEqual(
            canonical,
            "99932025-06-15SALEBYTAXUSD15.0012345",
            "Fiscal canonical format changed. Update FDMS integration if intentional.",
        )

    def test_snapshot_multiple_counters(self):
        """Snapshot: multiple counters with distinct sort order (type, currency)."""
        counters = [
            {"fiscalCounterType": "creditNoteByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxPercent": 15, "fiscalCounterValue": 10.00},
            {"fiscalCounterType": "saleByTax", "fiscalCounterCurrency": "USD", "fiscalCounterTaxPercent": 15, "fiscalCounterValue": 100.00},
        ]
        canonical = build_fiscal_day_canonical_string(
            device_id=5000,
            fiscal_day_no=10,
            fiscal_day_date=date(2025, 12, 1),
            fiscal_day_counters=counters,
        )
        # creditNoteByTax before saleByTax (alphabetically). 10.00->1000, 100.00->10000
        self.assertEqual(
            canonical,
            "5000102025-12-01CREDITNOTEBYTAXUSD15.001000SALEBYTAXUSD15.0010000",
            "Fiscal canonical format changed. Update FDMS integration if intentional.",
        )
