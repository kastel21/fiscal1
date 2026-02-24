"""Tests for FDMS-compliant invoice layout. No forbidden content."""

from decimal import Decimal

from django.test import TestCase

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.invoice_layout_service import build_invoice_context


class InvoiceLayoutTests(TestCase):
    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99999,
            certificate_pem="x",
            private_key_pem="x",
            is_registered=True,
        )

    def test_build_context_excludes_forbidden(self):
        """Context must never contain operationID, receiptID, hashes, signatures."""
        receipt = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("100.00"),
            receipt_lines=[{"receiptLineQuantity": 1, "receiptLineTotal": 100, "receiptLineName": "Item"}],
            receipt_taxes=[{"taxID": 1, "taxAmount": 15, "salesAmountWithTax": 100}],
            receipt_payments=[{"paymentAmount": 100}],
        )
        ctx = build_invoice_context(receipt)
        forbidden = ["operationID", "operation_id", "receiptID", "receipt_id", "receiptServerSignature",
                     "receiptDeviceSignature", "receipt_hash", "canonical_string"]
        for key in forbidden:
            self.assertNotIn(key, str(ctx).lower().replace("_", "").replace(" ", ""),
                            msg=f"Forbidden content '{key}' must not appear in invoice context")
