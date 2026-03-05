from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings

from fiscal.models import FiscalDevice, Receipt
from fiscal.services.receipt_service import _persist_invoice_pdf_if_enabled
from fiscal.views_fdms import fdms_receipt_invoice_pdf


class PdfPersistenceToggleTests(TestCase):
    @override_settings(FDMS_PERSIST_PDF=False)
    def test_pdf_not_saved_when_persistence_disabled(self):
        receipt = Mock()
        receipt.pdf_file = Mock()
        receipt.fdms_receipt_id = 123

        saved = _persist_invoice_pdf_if_enabled(receipt, 44)

        self.assertFalse(saved)
        receipt.pdf_file.save.assert_not_called()
        receipt.refresh_from_db.assert_not_called()

    @override_settings(FDMS_PERSIST_PDF=True)
    @patch("fiscal.services.pdf_generator.generate_fiscal_invoice_pdf", return_value=b"%PDF-1.4")
    def test_pdf_saved_when_persistence_enabled(self, mock_generate):
        receipt = Mock()
        receipt.pdf_file = Mock()
        receipt.fdms_receipt_id = 0

        saved = _persist_invoice_pdf_if_enabled(receipt, 77)

        self.assertTrue(saved)
        receipt.refresh_from_db.assert_called_once()
        mock_generate.assert_called_once_with(receipt)
        receipt.pdf_file.save.assert_called_once()
        args, _kwargs = receipt.pdf_file.save.call_args
        self.assertEqual(args[0], "77.pdf")


class PdfDownloadEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="staffpdf",
            password="pw12345",
            is_staff=True,
            is_superuser=True,
        )
        self.rf = RequestFactory()
        self.device = FiscalDevice.objects.create(
            device_id=445566,
            device_serial_no="PDF-TEST",
            certificate_pem="cert",
            private_key_pem="key",
            is_registered=True,
            last_fiscal_day_no=1,
        )
        self.receipt = Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            document_type="INVOICE",
            invoice_no="INV-2026-1",
            fdms_receipt_id=1001,
            receipt_lines=[],
            receipt_taxes=[],
            receipt_payments=[],
            receipt_total=0,
        )

    @patch(
        "fiscal.services.pdf_generator.generate_fiscal_invoice_pdf_from_template",
        return_value=b"%PDF-1.4 test",
    )
    def test_pdf_download_is_generated_on_demand(self, _mock_generate):
        req = self.rf.get(f"/fdms/receipts/{self.receipt.pk}/invoice/pdf/")
        req.user = self.user
        req.tenant = None
        resp = fdms_receipt_invoice_pdf(req, self.receipt.pk)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

