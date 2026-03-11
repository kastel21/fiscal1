"""Tests for tenant access control and user-tenant relationship."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from tenants.middleware import (
    TenantResolutionMiddleware,
    _get_valid_tenant,
    tenant_exempt,
)
from tenants.models import Tenant
from tenants.utils import user_has_tenant_access

User = get_user_model()


class TenantAccessControlTests(TestCase):
    """Verify users cannot access tenants they are not assigned to."""

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
        self.user_a = User.objects.create_user(
            username="usera",
            password="testpass123",
            is_staff=True,
        )
        self.user_b = User.objects.create_user(
            username="userb",
            password="testpass123",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="super",
            password="superpass123",
            email="super@test.com",
        )
        # Assign user_a to tenant_a only; user_b to tenant_b only (through UserTenant)
        self.tenant_a.users.add(self.user_a, through_defaults={"role": "user"})
        self.tenant_b.users.add(self.user_b, through_defaults={"role": "user"})

    def test_user_can_access_assigned_tenant(self):
        """User can access a tenant they are assigned to."""
        self.assertTrue(user_has_tenant_access(self.user_a, self.tenant_a))
        self.assertTrue(user_has_tenant_access(self.user_b, self.tenant_b))

    def test_user_cannot_access_unassigned_tenant(self):
        """User cannot access a tenant they are not assigned to."""
        self.assertFalse(user_has_tenant_access(self.user_a, self.tenant_b))
        self.assertFalse(user_has_tenant_access(self.user_b, self.tenant_a))

    def test_superuser_can_access_any_tenant(self):
        """Superuser can access all tenants regardless of assignment."""
        self.assertTrue(user_has_tenant_access(self.superuser, self.tenant_a))
        self.assertTrue(user_has_tenant_access(self.superuser, self.tenant_b))
        if self.superuser in self.tenant_a.users.all():
            self.tenant_a.users.remove(self.superuser)
        if self.superuser in self.tenant_b.users.all():
            self.tenant_b.users.remove(self.superuser)
        self.assertTrue(user_has_tenant_access(self.superuser, self.tenant_a))
        self.assertTrue(user_has_tenant_access(self.superuser, self.tenant_b))

    def test_anonymous_cannot_access_tenant(self):
        """Anonymous user cannot access any tenant."""
        self.assertFalse(user_has_tenant_access(None, self.tenant_a))
        self.assertFalse(user_has_tenant_access(AnonymousUser(), self.tenant_a))

    @override_settings(DEBUG=True)
    def test_middleware_returns_403_for_unauthorized_tenant_via_header(self):
        """Session tenant_slug does not bypass access control; 403 if user not in tenant."""
        get_response = lambda req: None
        middleware = TenantResolutionMiddleware(get_response)
        # Session has tenant-b but user_a is only in tenant_a -> 403 (normal users use session only)
        request = self.factory.get("/fdms/dashboard/")
        request.user = self.user_a
        request.session = {"tenant_slug": "tenant-b"}
        response = middleware(request)
        self.assertEqual(response.status_code, 403)
        self.assertIsNone(getattr(request, "tenant", None))

    @override_settings(DEBUG=True)
    def test_middleware_sets_tenant_when_authorized(self):
        """When user is allowed, request.tenant is set (session-based for normal user)."""
        def get_response(req):
            self.assertEqual(req.tenant, self.tenant_a)
            from django.http import HttpResponse
            return HttpResponse(status=200)
        middleware = TenantResolutionMiddleware(get_response)
        request = self.factory.get("/fdms/dashboard/")
        request.user = self.user_a
        request.session = {"tenant_slug": "tenant-a"}
        response = middleware(request)
        self.assertEqual(response.status_code, 200)

    @override_settings(DEBUG=True)
    def test_middleware_header_ignored_for_normal_user(self):
        """X-Tenant-Slug header is ignored for non-superuser; only session is used."""
        get_response = lambda req: None
        middleware = TenantResolutionMiddleware(get_response)
        request = self.factory.get("/fdms/dashboard/")
        request.user = self.user_a
        request.session = {}
        request.META["HTTP_X_TENANT_SLUG"] = "tenant-a"
        response = middleware(request)
        # user_a is not superuser so header is ignored; no session -> redirect to select_tenant
        self.assertEqual(response.status_code, 302)
        self.assertIn("select-tenant", response.url or "")

    @override_settings(DEBUG=True)
    def test_middleware_superuser_can_access_any_tenant_via_header(self):
        """Superuser can access any tenant via X-Tenant-Slug."""
        def get_response(req):
            self.assertEqual(req.tenant, self.tenant_b)
            from django.http import HttpResponse
            return HttpResponse(status=200)
        middleware = TenantResolutionMiddleware(get_response)
        request = self.factory.get("/fdms/dashboard/")
        request.user = self.superuser
        request.session = {}
        request.META["HTTP_X_TENANT_SLUG"] = "tenant-b"
        response = middleware(request)
        self.assertEqual(response.status_code, 200)


class SelectTenantViewTests(TestCase):
    """Tenant selection only shows and allows assigned tenants."""

    def setUp(self):
        self.client = Client()
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
        self.user_a = User.objects.create_user(
            username="usera",
            password="testpass123",
            is_staff=True,
        )
        self.tenant_a.users.add(self.user_a, through_defaults={"role": "user"})
        self.superuser = User.objects.create_superuser(
            username="super",
            password="superpass123",
            email="super@test.com",
        )

    def test_select_tenant_requires_login(self):
        """Anonymous users are redirected to login when opening select-tenant."""
        response = self.client.get(reverse("select_tenant"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login") or "/admin/login/", response.url or "")

    def test_select_tenant_shows_only_allowed_tenants(self):
        """Logged-in user sees only tenants they are assigned to."""
        self.client.login(username="usera", password="testpass123")
        response = self.client.get(reverse("select_tenant"))
        self.assertEqual(response.status_code, 200)
        # user_a is only in tenant_a
        self.assertContains(response, "tenant-a")
        self.assertContains(response, "Tenant A")
        self.assertNotContains(response, "tenant-b")
        self.assertNotContains(response, "Tenant B")

    def test_select_tenant_superuser_sees_all(self):
        """Superuser sees all active tenants."""
        self.client.login(username="super", password="superpass123")
        response = self.client.get(reverse("select_tenant"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tenant-a")
        self.assertContains(response, "tenant-b")

    def test_select_tenant_post_only_sets_allowed_tenant(self):
        """POST with tenant_slug only sets session if user is allowed that tenant."""
        self.client.login(username="usera", password="testpass123")
        # user_a is in tenant_a only; try to set tenant_b via POST
        response = self.client.post(
            reverse("select_tenant"),
            data={"tenant_slug": "tenant-b", "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", "")},
            follow=False,
        )
        # Should redirect back to select_tenant (no session set for tenant-b)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("select_tenant"))
        session_slug = self.client.session.get("tenant_slug")
        self.assertNotEqual(session_slug, "tenant-b")

        # POST with allowed tenant_a
        response = self.client.post(
            reverse("select_tenant"),
            data={"tenant_slug": "tenant-a", "csrfmiddlewaretoken": self.client.cookies.get("csrftoken", "")},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("dashboard", response.url or "")
        self.assertEqual(self.client.session.get("tenant_slug"), "tenant-a")


class TenantExemptTests(TestCase):
    """Paths that do not require tenant resolution."""

    def test_admin_is_exempt(self):
        self.assertTrue(tenant_exempt("/admin/"))
        self.assertTrue(tenant_exempt("/admin/tenants/tenant/"))

    def test_select_tenant_is_exempt(self):
        self.assertTrue(tenant_exempt("/select-tenant/"))

    def test_api_health_is_exempt(self):
        self.assertTrue(tenant_exempt("/api/health/"))

    def test_fdms_dashboard_not_exempt(self):
        self.assertFalse(tenant_exempt("/fdms/dashboard/"))

    def test_api_devices_not_exempt(self):
        self.assertFalse(tenant_exempt("/api/devices/"))


class GetValidTenantTests(TestCase):
    """_get_valid_tenant helper."""

    def test_returns_tenant_for_active_slug(self):
        t = Tenant.objects.create(name="T", slug="t1", device_id=60001, is_active=True)
        self.assertEqual(_get_valid_tenant("t1"), t)

    def test_returns_none_for_inactive_tenant(self):
        Tenant.objects.create(name="T", slug="t2", device_id=60002, is_active=False)
        self.assertIsNone(_get_valid_tenant("t2"))

    def test_returns_none_for_empty_slug(self):
        self.assertIsNone(_get_valid_tenant(""))
        self.assertIsNone(_get_valid_tenant(None))


class TenantAwareManagerTests(TestCase):
    """TenantAwareManager: objects filters by current tenant; all_objects is unscoped; no tenant -> empty."""

    def setUp(self):
        from tenants.context import clear_current_tenant, set_current_tenant
        self.set_current_tenant = set_current_tenant
        self.clear_current_tenant = clear_current_tenant
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
        # Use FiscalDevice (TenantAwareModel) for integration test
        from fiscal.models import FiscalDevice
        self.FiscalDevice = FiscalDevice
        FAKE_CERT = "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----"
        FAKE_KEY = "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----"
        self.device_a = FiscalDevice.all_objects.create(
            tenant=self.tenant_a,
            device_id=60001,
            device_serial_no="A1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
        )
        self.device_b = FiscalDevice.all_objects.create(
            tenant=self.tenant_b,
            device_id=60002,
            device_serial_no="B1",
            certificate_pem=FAKE_CERT,
            private_key_pem=FAKE_KEY,
            is_registered=True,
        )

    def test_objects_empty_when_no_tenant(self):
        """With no current tenant, Model.objects returns no rows."""
        self.assertEqual(list(self.FiscalDevice.objects.all()), [])

    def test_objects_filtered_when_tenant_set(self):
        """With current tenant set, Model.objects returns only that tenant's rows."""
        token = self.set_current_tenant(self.tenant_a)
        try:
            qs = list(self.FiscalDevice.objects.all())
            self.assertEqual(len(qs), 1)
            self.assertEqual(qs[0].pk, self.device_a.pk)
        finally:
            self.clear_current_tenant(token)

        token = self.set_current_tenant(self.tenant_b)
        try:
            qs = list(self.FiscalDevice.objects.all())
            self.assertEqual(len(qs), 1)
            self.assertEqual(qs[0].pk, self.device_b.pk)
        finally:
            self.clear_current_tenant(token)

    def test_all_objects_sees_all_tenants(self):
        """all_objects is unscoped and returns all rows regardless of tenant context."""
        self.assertEqual(self.FiscalDevice.all_objects.count(), 2)
        token = self.set_current_tenant(self.tenant_a)
        try:
            self.assertEqual(self.FiscalDevice.all_objects.count(), 2)
        finally:
            self.clear_current_tenant(token)

    def test_user_tenant_cache_used_when_set(self):
        """user_has_tenant_access uses _tenant_cache when present (avoids extra query)."""
        self.user_a = User.objects.create_user(username="u", password="p", is_staff=True)
        self.tenant_a.users.add(self.user_a, through_defaults={"role": "user"})
        self.assertTrue(user_has_tenant_access(self.user_a, self.tenant_a))
        self.user_a._tenant_cache = set()
        self.assertFalse(user_has_tenant_access(self.user_a, self.tenant_a))
        self.user_a._tenant_cache = {self.tenant_a.pk}
        self.assertTrue(user_has_tenant_access(self.user_a, self.tenant_a))


class TenantOnboardingTests(TestCase):
    """Tests for superuser tenant onboarding view."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            password="superpass123",
            email="super@test.com",
        )
        self.client = Client()
        self.client.force_login(self.superuser)
        self.url = reverse("tenant_onboarding")

    def _post_onboarding(self, **overrides):
        """GET page for CSRF then POST onboarding form. Returns response."""
        get_resp = self.client.get(self.url)
        self.assertEqual(get_resp.status_code, 200)
        csrf = get_resp.context["csrf_token"]
        data = {
            "company_name": "Test Ltd",
            "slug": "test-slug",
            "username": "testuser",
            "email_user": "test@test.com",
            "password": "testpass123",
            "role": "admin",
            "device_id": 99001,
            "certificate_pem": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            "private_key_pem": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
            "register_device_now": "",
            "activation_key": "",
            "csrfmiddlewaretoken": csrf,
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=False)

    def test_superuser_can_create_tenant(self):
        """Superuser can submit onboarding form and create tenant, user, device."""
        from tenants.models import UserTenant
        from fiscal.models import FiscalDevice
        self.assertFalse(Tenant.objects.filter(slug="onboard-test").exists())
        response = self._post_onboarding(
            company_name="Onboard Test Ltd",
            slug="onboard-test",
            tin="123",
            address="123 Main St",
            username="onboarduser",
            email_user="onboard@test.com",
            password="securepass123",
            role="admin",
            device_id=99001,
            device_serial_no="SN001",
            device_model="Model X",
        )
        self.assertEqual(response.status_code, 302, msg=getattr(response, "content", b"").decode()[:500])
        self.assertTrue(Tenant.objects.filter(slug="onboard-test").exists())
        tenant = Tenant.objects.get(slug="onboard-test")
        self.assertEqual(tenant.name, "Onboard Test Ltd")
        self.assertEqual(tenant.device_id, 99001)
        # User linked via UserTenant
        self.assertTrue(UserTenant.objects.filter(tenant=tenant, user__username="onboarduser").exists())
        ut = UserTenant.objects.get(tenant=tenant, user__username="onboarduser")
        self.assertEqual(ut.role, "admin")
        # Device assigned to tenant
        dev = FiscalDevice.all_objects.get(device_id=99001)
        self.assertEqual(dev.tenant_id, tenant.id)
        self.assertEqual(dev.device_serial_no, "SN001")

    def test_onboarding_users_linked_through_usertenant(self):
        """Onboarding creates UserTenant so user is linked to the new tenant."""
        from tenants.models import UserTenant
        self._post_onboarding(
            company_name="Link Test",
            slug="link-test",
            username="linkuser",
            email_user="link@test.com",
            password="linkpass123",
            role="owner",
            device_id=99002,
            certificate_pem="-----BEGIN CERTIFICATE-----\nt\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\nt\n-----END PRIVATE KEY-----",
        )
        tenant = Tenant.objects.get(slug="link-test")
        self.assertTrue(tenant.users.filter(username="linkuser").exists())
        ut = UserTenant.objects.get(tenant=tenant, user__username="linkuser")
        self.assertEqual(ut.role, "owner")

    def test_onboarding_device_assigned_to_tenant(self):
        """Fiscal device created in onboarding is assigned to the new tenant."""
        from fiscal.models import FiscalDevice
        self._post_onboarding(
            company_name="Device Test",
            slug="device-test",
            username="devuser",
            email_user="dev@test.com",
            password="devpass123",
            role="user",
            device_id=99003,
            device_serial_no="SN003",
            device_model="FD-100",
            certificate_pem="-----BEGIN CERTIFICATE-----\nt\n-----END CERTIFICATE-----",
            private_key_pem="-----BEGIN PRIVATE KEY-----\nt\n-----END PRIVATE KEY-----",
        )
        tenant = Tenant.objects.get(slug="device-test")
        dev = FiscalDevice.all_objects.get(device_id=99003)
        self.assertEqual(dev.tenant_id, tenant.id)
        self.assertEqual(dev.device_model_name, "FD-100")

    def test_registration_triggered_when_selected(self):
        """When register_device_now is checked, register_device is called (mocked)."""
        from unittest.mock import patch
        with patch("tenants.context.set_current_tenant"):
            with patch("tenants.context.clear_current_tenant"):
                with patch("device_identity.services.register_device") as mock_svc:
                    mock_svc.return_value = (None, "Mocked failure")
                    response = self._post_onboarding(
                        company_name="Reg Test",
                        slug="reg-test",
                        username="reguser",
                        email_user="reg@test.com",
                        password="regpass123",
                        role="user",
                        device_id=99004,
                        device_serial_no="SN004",
                        device_model="M1",
                        register_device_now="on",
                        activation_key="ABCD1234",
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertTrue(mock_svc.called)
                    call_kw = mock_svc.call_args[1]
                    self.assertEqual(call_kw["device_id"], 99004)
                    self.assertEqual(call_kw["activation_key"], "ABCD1234")


class TenantOnboardingWizardTests(TestCase):
    """Tests for multi-step tenant onboarding wizard."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            password="superpass123",
            email="super@test.com",
        )
        self.client = Client()
        self.client.force_login(self.superuser)

    def _get_csrf(self, url):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        return r.context["csrf_token"]

    def test_superuser_can_complete_wizard(self):
        """Superuser can complete all steps and create tenant."""
        from tenants.models import UserTenant
        from fiscal.models import FiscalDevice
        base = reverse("tenant_wizard", kwargs={"step": 1})
        csrf = self._get_csrf(base)
        # Step 1: Company
        r1 = self.client.post(base, {
            "csrfmiddlewaretoken": csrf,
            "company_name": "Wizard Co",
            "slug": "wizard-co",
            "tin": "999",
            "vat_number": "",
            "address": "1 Wizard St",
            "email": "co@wizard.test",
            "phone": "",
        })
        self.assertEqual(r1.status_code, 302)
        self.assertIn("onboarding_company", self.client.session)
        # Step 2: User
        csrf = self._get_csrf(reverse("tenant_wizard", kwargs={"step": 2}))
        r2 = self.client.post(reverse("tenant_wizard", kwargs={"step": 2}), {
            "csrfmiddlewaretoken": csrf,
            "username": "wizarduser",
            "email": "wizarduser@test.com",
            "password": "wizardpass123",
            "role": "admin",
        })
        self.assertEqual(r2.status_code, 302)
        self.assertIn("onboarding_user", self.client.session)
        # Step 3: Device
        csrf = self._get_csrf(reverse("tenant_wizard", kwargs={"step": 3}))
        r3 = self.client.post(reverse("tenant_wizard", kwargs={"step": 3}), {
            "csrfmiddlewaretoken": csrf,
            "device_id": 99101,
            "device_serial_no": "WZ001",
            "device_model": "Wizard-M1",
            "certificate_pem": "-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
            "private_key_pem": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----",
        })
        self.assertEqual(r3.status_code, 302)
        self.assertIn("onboarding_device", self.client.session)
        # Step 4: Submit
        csrf = self._get_csrf(reverse("tenant_wizard", kwargs={"step": 4}))
        r4 = self.client.post(reverse("tenant_wizard", kwargs={"step": 4}), {
            "csrfmiddlewaretoken": csrf,
        })
        self.assertEqual(r4.status_code, 302)
        self.assertTrue(Tenant.objects.filter(slug="wizard-co").exists())
        tenant = Tenant.objects.get(slug="wizard-co")
        self.assertEqual(tenant.name, "Wizard Co")
        # Session cleared
        self.assertNotIn("onboarding_company", self.client.session)
        self.assertNotIn("onboarding_user", self.client.session)
        self.assertNotIn("onboarding_device", self.client.session)

    def test_wizard_tenant_created_successfully(self):
        """Wizard step 4 submission creates tenant with correct data."""
        self._get_csrf(reverse("tenant_wizard", kwargs={"step": 1}))
        self.client.post(reverse("tenant_wizard", kwargs={"step": 1}), {
            "csrfmiddlewaretoken": self._get_csrf(reverse("tenant_wizard", kwargs={"step": 1})),
            "company_name": "Final Co",
            "slug": "final-co",
            "tin": "", "vat_number": "", "address": "", "email": "", "phone": "",
        })
        self.client.post(reverse("tenant_wizard", kwargs={"step": 2}), {
            "csrfmiddlewaretoken": self._get_csrf(reverse("tenant_wizard", kwargs={"step": 2})),
            "username": "finaluser",
            "email": "final@test.com",
            "password": "finalpass123",
            "role": "owner",
        })
        self.client.post(reverse("tenant_wizard", kwargs={"step": 3}), {
            "csrfmiddlewaretoken": self._get_csrf(reverse("tenant_wizard", kwargs={"step": 3})),
            "device_id": 99102,
            "device_serial_no": "F001",
            "device_model": "F-Model",
            "certificate_pem": "-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----",
            "private_key_pem": "-----BEGIN PRIVATE KEY-----\nx\n-----END PRIVATE KEY-----",
        })
        self.client.post(reverse("tenant_wizard", kwargs={"step": 4}), {
            "csrfmiddlewaretoken": self._get_csrf(reverse("tenant_wizard", kwargs={"step": 4})),
        })
        tenant = Tenant.objects.get(slug="final-co")
        self.assertEqual(tenant.name, "Final Co")
        self.assertEqual(tenant.device_id, 99102)

    def test_wizard_device_linked_to_tenant(self):
        """Fiscal device created in wizard is linked to the new tenant."""
        from fiscal.models import FiscalDevice
        for step, data in [
            (1, {"company_name": "DevCo", "slug": "devco", "tin": "", "vat_number": "", "address": "", "email": "", "phone": ""}),
            (2, {"username": "devuser", "email": "d@test.com", "password": "devpass123", "role": "user"}),
            (3, {"device_id": 99103, "device_serial_no": "D1", "device_model": "D-M", "certificate_pem": "-----BEGIN CERTIFICATE-----\nd\n-----END CERTIFICATE-----", "private_key_pem": "-----BEGIN PRIVATE KEY-----\nd\n-----END PRIVATE KEY-----"}),
            (4, {}),
        ]:
            url = reverse("tenant_wizard", kwargs={"step": step})
            csrf = self._get_csrf(url)
            post_data = {"csrfmiddlewaretoken": csrf, **data}
            self.client.post(url, post_data)
        dev = FiscalDevice.all_objects.get(device_id=99103)
        tenant = Tenant.objects.get(slug="devco")
        self.assertEqual(dev.tenant_id, tenant.id)

    def test_wizard_user_assigned_through_usertenant(self):
        """User created in wizard is assigned to tenant via UserTenant."""
        from tenants.models import UserTenant
        for step, data in [
            (1, {"company_name": "UserCo", "slug": "userco", "tin": "", "vat_number": "", "address": "", "email": "", "phone": ""}),
            (2, {"username": "member1", "email": "m1@test.com", "password": "m1pass", "role": "accountant"}),
            (3, {"device_id": 99104, "device_serial_no": "U1", "device_model": "", "certificate_pem": "-----BEGIN CERTIFICATE-----\nu\n-----END CERTIFICATE-----", "private_key_pem": "-----BEGIN PRIVATE KEY-----\nu\n-----END PRIVATE KEY-----"}),
            (4, {}),
        ]:
            url = reverse("tenant_wizard", kwargs={"step": step})
            csrf = self._get_csrf(url)
            self.client.post(url, {"csrfmiddlewaretoken": csrf, **data})
        tenant = Tenant.objects.get(slug="userco")
        self.assertTrue(UserTenant.objects.filter(tenant=tenant, user__username="member1").exists())
        ut = UserTenant.objects.get(tenant=tenant, user__username="member1")
        self.assertEqual(ut.role, "accountant")

    def test_wizard_session_cleared_after_completion(self):
        """Wizard session keys are removed after successful submit."""
        for step, data in [
            (1, {"company_name": "SessCo", "slug": "sessco", "tin": "", "vat_number": "", "address": "", "email": "", "phone": ""}),
            (2, {"username": "sessuser", "email": "s@test.com", "password": "sesspass", "role": "user"}),
            (3, {"device_id": 99105, "device_serial_no": "S1", "device_model": "", "certificate_pem": "-----BEGIN CERTIFICATE-----\ns\n-----END CERTIFICATE-----", "private_key_pem": "-----BEGIN PRIVATE KEY-----\ns\n-----END PRIVATE KEY-----"}),
            (4, {}),
        ]:
            url = reverse("tenant_wizard", kwargs={"step": step})
            csrf = self._get_csrf(url)
            self.client.post(url, {"csrfmiddlewaretoken": csrf, **data})
        self.assertNotIn("onboarding_company", self.client.session)
        self.assertNotIn("onboarding_user", self.client.session)
        self.assertNotIn("onboarding_device", self.client.session)

    def test_wizard_returns_403_for_non_superuser(self):
        """Non-superuser gets 403 on wizard."""
        staff_user = User.objects.create_user(username="staff", password="staff123", email="s@test.com", is_staff=True)
        self.client.force_login(staff_user)
        r = self.client.get(reverse("tenant_wizard", kwargs={"step": 1}))
        self.assertEqual(r.status_code, 403)


class CreateCompanyWithUserTests(TestCase):
    """Tests for create_company_with_user (company + user in one form, Tenant + UserTenant created)."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super",
            password="superpass123",
            email="super@test.com",
        )
        self.client = Client()
        self.client.force_login(self.superuser)
        self.url = reverse("create_company_with_user")

    def _post_form(self, **overrides):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        csrf = r.context["csrf_token"]
        data = {
            "company_name": "Test Co",
            "slug": "test-co",
            "device_id": 99201,
            "tin": "123",
            "vat_number": "",
            "address": "1 Test St",
            "username": "testuser",
            "email": "test@test.com",
            "password": "testpass123",
            "role": "owner",
            "csrfmiddlewaretoken": csrf,
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=False)

    def test_superuser_can_create_company(self):
        """Superuser can submit form and create company (Tenant) and user."""
        from tenants.models import UserTenant
        self.assertFalse(Tenant.objects.filter(slug="test-co").exists())
        r = self._post_form()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Tenant.objects.filter(slug="test-co").exists())
        tenant = Tenant.objects.get(slug="test-co")
        self.assertEqual(tenant.name, "Test Co")
        self.assertEqual(tenant.device_id, 99201)

    def test_tenant_created_automatically(self):
        """Tenant is created with correct name and slug."""
        self._post_form(company_name="Auto Tenant Ltd", slug="auto-tenant")
        tenant = Tenant.objects.get(slug="auto-tenant")
        self.assertEqual(tenant.name, "Auto Tenant Ltd")

    def test_user_created(self):
        """User is created with given username and email."""
        self._post_form(username="firstuser", email="first@company.com")
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.get(username="firstuser")
        self.assertEqual(user.email, "first@company.com")

    def test_usertenant_relationship_created(self):
        """UserTenant links the new user to the new tenant with role."""
        from tenants.models import UserTenant
        self._post_form(username="member", role="admin")
        tenant = Tenant.objects.get(slug="test-co")
        ut = UserTenant.objects.get(tenant=tenant, user__username="member")
        self.assertEqual(ut.role, "admin")

    def test_duplicate_slug_fails(self):
        """Submitting an existing slug returns form error and does not create duplicate."""
        Tenant.objects.create(name="Existing", slug="existing-co", device_id=99299)
        r = self._post_form(slug="existing-co", device_id=99300)
        self.assertEqual(r.status_code, 200)
        self.assertIn("already exists", r.content.decode().lower())
        self.assertEqual(Tenant.objects.filter(slug="existing-co").count(), 1)


class CreateCompanyOnboardingTests(TestCase):
    """Tests for user onboarding: create_company (logged-in user creates tenant and becomes owner)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="onboarder",
            password="testpass123",
            email="onboard@test.com",
        )
        self.client.force_login(self.user)
        self.url = reverse("create_company")

    def _post_form(self, **overrides):
        self.client.get(self.url)  # get CSRF cookie
        csrf = self.client.cookies.get("csrftoken")
        csrf = csrf.value if csrf else ""
        data = {
            "company_name": "My Company",
            "slug": "my-company",
            "device_id": "88001",
            "tin": "",
            "vat_number": "",
            "address": "",
            "csrfmiddlewaretoken": csrf,
        }
        data.update(overrides)
        return self.client.post(self.url, data, follow=False)

    def test_anonymous_redirected_to_login(self):
        """Anonymous user cannot access create_company; redirected to login."""
        from django.test import Client
        c = Client()
        r = c.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url.lower())

    def test_get_shows_form(self):
        """GET returns 200 and form."""
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Create Company", r.content)
        self.assertIn(b"company_name", r.content)

    def test_user_can_create_company(self):
        """Logged-in user can create company; tenant and UserTenant created."""
        from tenants.models import UserTenant
        self.assertFalse(Tenant.objects.filter(slug="my-company").exists())
        r = self._post_form()
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Tenant.objects.filter(slug="my-company").exists())
        tenant = Tenant.objects.get(slug="my-company")
        self.assertEqual(tenant.name, "My Company")
        self.assertEqual(tenant.device_id, 88001)
        ut = UserTenant.objects.get(tenant=tenant, user=self.user)
        self.assertEqual(ut.role, "owner")

    def test_session_tenant_slug_set(self):
        """After creating company, session tenant_slug is set."""
        r = self._post_form()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.session.get("tenant_slug"), "my-company")

    def test_redirect_to_dashboard_after_company_creation(self):
        """After creating company, user is redirected to dashboard."""
        r = self._post_form()
        self.assertRedirects(r, reverse("fdms_dashboard"))

    def test_onboarding_duplicate_slug_fails(self):
        """Duplicate slug returns form error."""
        Tenant.objects.create(name="Other", slug="my-company", device_id=88002)
        r = self._post_form()
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"already exists", r.content)
        self.assertEqual(Tenant.objects.filter(slug="my-company").count(), 1)

    def test_onboarding_duplicate_tin_fails(self):
        """Duplicate TIN (existing Company) returns form error."""
        from fiscal.models import Company
        t = Tenant.objects.create(name="Other", slug="other-co", device_id=88002)
        Company.all_objects.create(
            tenant=t, name="Other", tin="999", vat_number="", address="—",
            phone="—", email="noreply@example.com",
        )
        r = self._post_form(tin="999")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"already exists", r.content)


class OnboardingWizardTests(TestCase):
    """Tests for 3-step onboarding wizard: Company → Device → Register."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="wizarduser",
            password="testpass123",
            email="wizard@test.com",
        )
        self.client.force_login(self.user)

    def _post_step1(self, **overrides):
        url = reverse("onboarding_company")
        self.client.get(url)
        csrf = self.client.cookies.get("csrftoken")
        csrf = csrf.value if csrf else ""
        data = {
            "company_name": "Wizard Co",
            "slug": "wizard-co",
            "device_id": "77001",
            "tin": "",
            "vat_number": "",
            "address": "",
            "csrfmiddlewaretoken": csrf,
        }
        data.update(overrides)
        return self.client.post(url, data, follow=False)

    def _post_step2(self, **overrides):
        url = reverse("onboarding_device")
        self.client.get(url)
        csrf = self.client.cookies.get("csrftoken")
        csrf = csrf.value if csrf else ""
        data = {
            "device_id": "77001",
            "device_serial_no": "SN-001",
            "device_model": "FDMS-M1",
            "csrfmiddlewaretoken": csrf,
        }
        data.update(overrides)
        return self.client.post(url, data, follow=False)

    def test_wizard_step1_requires_login(self):
        """Anonymous user cannot access onboarding step 1."""
        from django.test import Client
        c = Client()
        r = c.get(reverse("onboarding_company"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.url.lower())

    def test_wizard_step1_creates_tenant_and_redirects(self):
        """Step 1 creates tenant, UserTenant, sets session, redirects to step 2."""
        from tenants.models import UserTenant
        self.assertFalse(Tenant.objects.filter(slug="wizard-co").exists())
        r = self._post_step1()
        self.assertRedirects(r, reverse("onboarding_device"))
        self.assertTrue(Tenant.objects.filter(slug="wizard-co").exists())
        tenant = Tenant.objects.get(slug="wizard-co")
        self.assertEqual(tenant.name, "Wizard Co")
        self.assertEqual(tenant.device_id, 77001)
        ut = UserTenant.objects.get(tenant=tenant, user=self.user)
        self.assertEqual(ut.role, "owner")
        self.assertEqual(self.client.session.get("tenant_slug"), "wizard-co")

    def test_wizard_step2_requires_tenant_in_session(self):
        """Step 2 without tenant_slug in session redirects to step 1."""
        self.client.session.pop("tenant_slug", None)
        r = self.client.get(reverse("onboarding_device"))
        self.assertRedirects(r, reverse("onboarding_company"))

    def test_wizard_step2_creates_device_and_redirects(self):
        """Complete step 1 then step 2: device created, session has onboarding_device_id, redirect to step 3."""
        from fiscal.models import FiscalDevice
        self._post_step1()
        self.assertEqual(self.client.session.get("tenant_slug"), "wizard-co")
        r = self._post_step2()
        self.assertRedirects(r, reverse("onboarding_register_device"))
        tenant = Tenant.objects.get(slug="wizard-co")
        device = FiscalDevice.all_objects.get(tenant=tenant, device_id=77001)
        self.assertEqual(device.device_serial_no, "SN-001")
        self.assertEqual(device.device_model_name, "FDMS-M1")
        self.assertEqual(self.client.session.get("onboarding_device_id"), device.pk)

    def test_wizard_step3_requires_device_in_session(self):
        """Step 3 without onboarding_device_id redirects to step 2."""
        self.client.session.pop("onboarding_device_id", None)
        r = self.client.get(reverse("onboarding_register_device"))
        self.assertRedirects(r, reverse("onboarding_device"), fetch_redirect_response=False)

    def test_wizard_step3_shows_form(self):
        """Step 3 shows registration form when device is in session."""
        self._post_step1()
        self._post_step2()
        r = self.client.get(reverse("onboarding_register_device"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"activation_key", r.content)
        self.assertIn(b"Register device", r.content)

    @override_settings(DEBUG=True)
    def test_wizard_complete_flow_redirects_after_register(self):
        """Step 3 POST with valid-looking key: register_device may fail (FDMS), but we test redirect on success via mock."""
        from unittest.mock import patch
        self._post_step1()
        self._post_step2()
        device_pk = self.client.session.get("onboarding_device_id")
        from fiscal.models import FiscalDevice
        device = FiscalDevice.all_objects.get(pk=device_pk)
        with patch("device_identity.views.register_device") as mock_register:
            mock_register.return_value = (device, None)  # success
            self.client.get(reverse("onboarding_register_device"))  # csrf
            csrf = self.client.cookies.get("csrftoken")
            csrf = csrf.value if csrf else ""
            r = self.client.post(
                reverse("onboarding_register_device"),
                {"activation_key": "12345678", "csrfmiddlewaretoken": csrf},
            )
        self.assertRedirects(r, reverse("fdms_dashboard"), fetch_redirect_response=False)
        self.assertIsNone(self.client.session.get("onboarding_device_id"))
