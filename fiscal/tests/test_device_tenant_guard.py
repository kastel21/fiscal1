"""Tests for fiscal-device-to-tenant security guard."""

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from fiscal.models import FiscalDevice
from fiscal.utils import validate_device_for_tenant
from tenants.models import Tenant
from django.contrib.auth import get_user_model

User = get_user_model()

# Minimal PEMs for device creation
FAKE_CERT = "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
FAKE_KEY = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"


class ValidateDeviceForTenantTests(TestCase):
    """validate_device_for_tenant helper."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            device_id=50001,
            is_active=True,
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            device_id=50002,
            is_active=True,
        )
        self.device_a = FiscalDevice.objects.create(
            tenant=self.tenant_a,
            device_id=60001,
            device_serial_no="A1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
        )
        self.device_b = FiscalDevice.objects.create(
            tenant=self.tenant_b,
            device_id=60002,
            device_serial_no="B1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
        )

    def test_accepts_device_belonging_to_tenant(self):
        validate_device_for_tenant(self.device_a, self.tenant_a)
        validate_device_for_tenant(self.device_b, self.tenant_b)

    def test_raises_when_device_belongs_to_other_tenant(self):
        with self.assertRaises(PermissionDenied) as ctx:
            validate_device_for_tenant(self.device_b, self.tenant_a)
        self.assertIn("does not belong", str(ctx.exception))

        with self.assertRaises(PermissionDenied):
            validate_device_for_tenant(self.device_a, self.tenant_b)

    def test_skips_when_tenant_none(self):
        validate_device_for_tenant(self.device_a, None)

    def test_skips_when_device_none(self):
        validate_device_for_tenant(None, self.tenant_a)


class DeviceTenantIsolationAPITests(TestCase):
    """A tenant cannot use another tenant's device via API."""

    def setUp(self):
        self.factory = RequestFactory()
        self.tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            device_id=50001,
            is_active=True,
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            device_id=50002,
            is_active=True,
        )
        self.device_a = FiscalDevice.objects.create(
            tenant=self.tenant_a,
            device_id=60001,
            device_serial_no="A1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
        )
        self.device_b = FiscalDevice.objects.create(
            tenant=self.tenant_b,
            device_id=60002,
            device_serial_no="B1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
        )
        self.user_a = User.objects.create_user(
            username="usera",
            password="testpass",
            is_staff=True,
        )
        self.tenant_a.users.add(self.user_a, through_defaults={"role": "user"})

    def test_api_device_detail_other_tenant_returns_403(self):
        """GET /api/devices/{pk}/ for device of another tenant returns 403 when request.tenant is set."""
        from fiscal.views_management import api_device_detail
        request = self.factory.get(f"/api/devices/{self.device_b.pk}/")
        request.user = self.user_a
        request.tenant = self.tenant_a
        response = api_device_detail(request, pk=self.device_b.pk)
        self.assertEqual(response.status_code, 403)

    def test_api_device_open_day_other_tenant_returns_403(self):
        """POST open-day for device of another tenant returns 403 when request.tenant is set."""
        from fiscal.views_management import api_device_open_day
        request = self.factory.post(f"/api/devices/{self.device_b.pk}/open-day/", {})
        request.user = self.user_a
        request.tenant = self.tenant_a
        response = api_device_open_day(request, pk=self.device_b.pk)
        self.assertEqual(response.status_code, 403)


class SubmitReceiptTaskTenantValidationTests(TestCase):
    """Background task submit_receipt_task respects tenant_id validation."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            device_id=50001,
            is_active=True,
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            device_id=50002,
            is_active=True,
        )
        self.device_b = FiscalDevice.objects.create(
            tenant=self.tenant_b,
            device_id=60002,
            device_serial_no="B1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
            last_fiscal_day_no=1,
        )

    def test_submit_receipt_task_rejects_device_from_other_tenant(self):
        """When tenant_id is passed, device must belong to that tenant."""
        from fiscal.tasks import submit_receipt_task
        # device_b belongs to tenant_b; pass tenant_a.id -> should fail validation
        result = submit_receipt_task(
            device_id=self.device_b.device_id,
            fiscal_day_no=1,
            receipt_type="FiscalInvoice",
            receipt_currency="USD",
            invoice_no="",
            receipt_lines=[],
            receipt_taxes=[],
            receipt_payments=[],
            receipt_total=0.0,
            tenant_id=str(self.tenant_a.id),
        )
        self.assertFalse(result.get("success"))
        err = result.get("error", "")
        self.assertTrue(
            "tenant" in err.lower() or "denied" in err.lower() or "device" in err.lower(),
            msg=f"Expected tenant/denied/device in error: {err!r}",
        )


class InvoiceCreationDeviceTenantTests(TestCase):
    """Receipt/invoice creation fails if device does not belong to tenant."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            device_id=50001,
            is_active=True,
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            device_id=50002,
            is_active=True,
        )
        self.device_b = FiscalDevice.objects.create(
            tenant=self.tenant_b,
            device_id=60002,
            device_serial_no="B1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
            is_vat_registered=True,
            last_fiscal_day_no=1,
        )

    def test_create_invoice_with_tenant_id_ignores_other_tenant_device(self):
        """create_invoice with tenant_id only uses devices for that tenant; other tenant's device_id returns no device."""
        from invoices.services import create_invoice
        validated = {
            "device_id": self.device_b.device_id,
            "tenant_id": str(self.tenant_a.id),
            "items": [
                {"quantity": 1, "unit_price": 100, "tax_id": 517, "tax_percent": 15.5, "tax_code": "517", "item_name": "x", "hs_code": "000000"},
            ],
            "payments": [{"payment_type": "Cash", "amount": 115.5}],
        }
        receipt, err = create_invoice(validated)
        self.assertIsNone(receipt)
        self.assertIn("Device not found", err or "")
