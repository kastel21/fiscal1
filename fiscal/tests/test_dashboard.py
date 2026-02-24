"""Dashboard accuracy and regression tests. FDMS-confirmed data only."""

from decimal import Decimal

from django.test import TestCase

from fiscal.models import FDMSApiLog, FiscalDevice, Receipt
from fiscal.services.dashboard_service import get_errors, get_receipts, get_summary


class DashboardTotalsTests(TestCase):
    """Dashboard metrics must match persisted FDMS data. Draft receipts must NOT affect totals."""

    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=99999,
            device_serial_no="TEST",
            certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            is_registered=True,
            last_fiscal_day_no=1,
            last_receipt_global_no=10,
        )

    def test_dashboard_totals_invoice_and_credit_note(self):
        """Net total and VAT must match fiscalised invoices minus credit notes."""
        from django.utils import timezone
        now = timezone.now()
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("100.00"),
            receipt_taxes=[{"taxAmount": 15, "salesAmountWithTax": 100}],
            fdms_receipt_id=101,
            created_at=now,
        )
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=2,
            receipt_counter=2,
            currency="USD",
            receipt_type="CreditNote",
            receipt_total=Decimal("-20.00"),
            receipt_taxes=[{"taxAmount": -3, "salesAmountWithTax": -20}],
            fdms_receipt_id=102,
            created_at=now,
        )
        data = get_summary(self.device.device_id, "today")
        self.assertEqual(data["metrics"]["invoicesFiscalised"], 1)
        self.assertEqual(data["metrics"]["creditNotes"], 1)
        self.assertEqual(data["metrics"]["netTotal"], 80.0)
        self.assertEqual(data["metrics"]["vatTotal"], 12.0)

    def test_draft_receipts_excluded_from_totals(self):
        """Receipts without fdms_receipt_id must NOT affect metrics."""
        from django.utils import timezone
        now = timezone.now()
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("100.00"),
            receipt_taxes=[],
            fdms_receipt_id=None,
            created_at=now,
        )
        data = get_summary(self.device.device_id, "today")
        self.assertEqual(data["metrics"]["invoicesFiscalised"], 0)
        self.assertEqual(data["metrics"]["netTotal"], 0)
        self.assertEqual(data["pipeline"]["fiscalised"], 0)
        self.assertEqual(data["pipeline"]["draft"], 1)


class DashboardNoReceiptsTests(TestCase):
    """Dashboard must load with no receipts."""

    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=88888,
            device_serial_no="TEST",
            certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            is_registered=True,
            fiscal_day_status="FiscalDayOpened",
        )

    def test_dashboard_loads_with_no_receipts(self):
        data = get_summary(self.device.device_id, "today")
        self.assertIn("status", data)
        self.assertIn("metrics", data)
        self.assertIn("pipeline", data)
        self.assertEqual(data["metrics"]["invoicesFiscalised"], 0)
        self.assertEqual(data["metrics"]["creditNotes"], 0)
        self.assertEqual(data["metrics"]["netTotal"], 0)
        self.assertEqual(data["pipeline"]["draft"], 0)
        self.assertEqual(data["pipeline"]["fiscalised"], 0)


class DashboardReceiptsApiTests(TestCase):
    """GET /api/dashboard/receipts returns pipeline data."""

    def setUp(self):
        self.device = FiscalDevice.objects.create(
            device_id=77777,
            device_serial_no="TEST",
            certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            is_registered=True,
        )

    def test_get_receipts_filter_draft(self):
        from django.utils import timezone
        now = timezone.now()
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("50.00"),
            fdms_receipt_id=None,
            created_at=now,
        )
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=2,
            receipt_counter=2,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("100.00"),
            fdms_receipt_id=999,
            created_at=now,
        )
        receipts = get_receipts(self.device.device_id, "today", "draft")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["status"], "draft")

    def test_get_receipts_filter_fiscalised(self):
        from django.utils import timezone
        now = timezone.now()
        Receipt.objects.create(
            device=self.device,
            fiscal_day_no=1,
            receipt_global_no=1,
            receipt_counter=1,
            currency="USD",
            receipt_type="FiscalInvoice",
            receipt_total=Decimal("100.00"),
            fdms_receipt_id=999,
            created_at=now,
        )
        receipts = get_receipts(self.device.device_id, "today", "fiscalised")
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["status"], "fiscalised")


class DashboardErrorsTests(TestCase):
    """Failed receipts and errors reflected correctly."""

    def setUp(self):
        from django.utils import timezone
        self.device = FiscalDevice.objects.create(
            device_id=66666,
            device_serial_no="TEST",
            certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            is_registered=True,
        )
        self.now = timezone.now()

    def test_failed_receipts_reflected_in_pipeline(self):
        FDMSApiLog.objects.create(
            endpoint="/fdms/device/66666/SubmitReceipt",
            method="POST",
            status_code=500,
            error_message="Server error",
            created_at=self.now,
        )
        FDMSApiLog.objects.create(
            endpoint="/fdms/device/66666/SubmitReceipt",
            method="POST",
            status_code=200,
            created_at=self.now,
        )
        data = get_summary(self.device.device_id, "today")
        self.assertGreaterEqual(data["pipeline"]["failed"], 1)

    def test_errors_include_operation_id(self):
        FDMSApiLog.objects.create(
            endpoint="/fdms/device/66666/SubmitReceipt",
            method="POST",
            status_code=500,
            error_message="Test error",
            operation_id="OP123",
            created_at=self.now,
        )
        errors = get_errors(self.device.device_id, "today")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["operationId"], "OP123")


class DashboardRoleBasedTests(TestCase):
    """Role-based visibility per FDMS_Dashboard_Metrics spec."""

    def setUp(self):
        from django.contrib.auth.models import Group, User
        self.user_admin = User.objects.create_user("admin", is_staff=True)
        self.user_accountant = User.objects.create_user("acc", is_staff=True)
        grp, _ = Group.objects.get_or_create(name="accountant")
        self.user_accountant.groups.add(grp)
        self.user_cashier = User.objects.create_user("cash", is_staff=True)
        grp_c, _ = Group.objects.get_or_create(name="cashier")
        self.user_cashier.groups.add(grp_c)
        self.device = FiscalDevice.objects.create(
            device_id=55555,
            device_serial_no="TEST",
            certificate_pem="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            is_registered=True,
        )

    def test_cashier_hides_certs_and_counters(self):
        from django.test import RequestFactory
        from fiscal.views_dashboard import _apply_role_filter, _get_user_role, api_dashboard_summary
        req = RequestFactory().get("/api/dashboard/summary/")
        req.user = self.user_cashier
        role = _get_user_role(req)
        self.assertEqual(role, "cashier")
        data = get_summary(self.device.device_id, "today")
        filtered = _apply_role_filter(data, "cashier")
        self.assertEqual(filtered["status"].get("certificate"), "***")
        self.assertEqual(filtered["status"].get("lastSync"), "***")
        self.assertEqual(filtered["compliance"].get("lastReceiptGlobalNo"), "***")
