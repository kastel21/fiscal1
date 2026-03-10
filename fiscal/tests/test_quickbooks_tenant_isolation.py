"""Tests for QuickBooks tenant isolation: credentials and data scoped per tenant."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from fiscal.models import QuickBooksConnection, QuickBooksInvoice
from fiscal.views_api import api_qb_oauth_callback
from tenants.models import Tenant, UserTenant

User = get_user_model()


class QuickBooksTenantIsolationTests(TestCase):
    """Verify QuickBooks connections and invoices are isolated per tenant."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            device_id=60001,
            is_active=True,
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            device_id=60002,
            is_active=True,
        )
        self.user_a = User.objects.create_user(username="usera", password="testpass123")
        self.user_b = User.objects.create_user(username="userb", password="testpass123")
        UserTenant.objects.create(user=self.user_a, tenant=self.tenant_a, role="owner")
        UserTenant.objects.create(user=self.user_b, tenant=self.tenant_b, role="owner")

    def test_connection_stored_per_tenant(self):
        """QuickBooksConnection is stored with tenant; tenant B cannot see tenant A's connection."""
        QuickBooksConnection.objects.create(
            tenant=self.tenant_a,
            realm_id="realm-a",
            access_token_encrypted="ENC:enc-a",
            refresh_token_encrypted="ENC:ref-a",
            is_active=True,
        )
        QuickBooksConnection.objects.create(
            tenant=self.tenant_b,
            realm_id="realm-b",
            access_token_encrypted="ENC:enc-b",
            refresh_token_encrypted="ENC:ref-b",
            is_active=True,
        )
        conn_a = QuickBooksConnection.objects.filter(tenant=self.tenant_a, is_active=True).first()
        conn_b = QuickBooksConnection.objects.filter(tenant=self.tenant_b, is_active=True).first()
        self.assertIsNotNone(conn_a)
        self.assertIsNotNone(conn_b)
        self.assertEqual(conn_a.realm_id, "realm-a")
        self.assertEqual(conn_b.realm_id, "realm-b")
        self.assertNotEqual(conn_a.tenant_id, conn_b.tenant_id)

    def test_tenant_b_cannot_access_tenant_a_connection(self):
        """Lookup by tenant=tenant_b does not return tenant A's connection."""
        QuickBooksConnection.objects.create(
            tenant=self.tenant_a,
            realm_id="realm-a",
            access_token_encrypted="ENC:enc",
            refresh_token_encrypted="ENC:ref",
            is_active=True,
        )
        conn = QuickBooksConnection.objects.filter(tenant=self.tenant_b, is_active=True).first()
        self.assertIsNone(conn)

    def test_invoice_filtered_by_tenant(self):
        """QuickBooksInvoice is scoped by tenant; tenant B does not see tenant A's invoices."""
        QuickBooksInvoice.objects.create(
            tenant=self.tenant_a,
            qb_invoice_id="inv-1",
            total_amount=100,
            raw_payload={},
        )
        QuickBooksInvoice.objects.create(
            tenant=self.tenant_b,
            qb_invoice_id="inv-2",
            total_amount=200,
            raw_payload={},
        )
        qs_a = QuickBooksInvoice.objects.filter(tenant=self.tenant_a)
        qs_b = QuickBooksInvoice.objects.filter(tenant=self.tenant_b)
        self.assertEqual(qs_a.count(), 1)
        self.assertEqual(qs_b.count(), 1)
        self.assertEqual(qs_a.first().qb_invoice_id, "inv-1")
        self.assertEqual(qs_b.first().qb_invoice_id, "inv-2")

    def test_same_qb_invoice_id_different_tenants(self):
        """Same qb_invoice_id can exist per tenant (unique constraint is tenant + qb_invoice_id)."""
        QuickBooksInvoice.objects.create(
            tenant=self.tenant_a,
            qb_invoice_id="same-id",
            total_amount=10,
            raw_payload={},
        )
        QuickBooksInvoice.objects.create(
            tenant=self.tenant_b,
            qb_invoice_id="same-id",
            total_amount=20,
            raw_payload={},
        )
        self.assertEqual(
            QuickBooksInvoice.objects.filter(tenant=self.tenant_a, qb_invoice_id="same-id").count(),
            1,
        )
        self.assertEqual(
            QuickBooksInvoice.objects.filter(tenant=self.tenant_b, qb_invoice_id="same-id").count(),
            1,
        )

    def test_webhook_resolves_tenant_from_realm_id(self):
        """Resolving tenant from realm_id via QuickBooksConnection returns the correct tenant."""
        QuickBooksConnection.objects.create(
            tenant=self.tenant_a,
            realm_id="realm-webhook",
            access_token_encrypted="ENC:x",
            refresh_token_encrypted="ENC:y",
            is_active=True,
        )
        conn = QuickBooksConnection.objects.filter(
            realm_id="realm-webhook", is_active=True
        ).select_related("tenant").first()
        self.assertIsNotNone(conn)
        self.assertEqual(conn.tenant_id, self.tenant_a.id)
        self.assertEqual(conn.tenant.slug, "tenant-a")

    def test_connection_requires_tenant(self):
        """QuickBooksConnection cannot be created without a tenant."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            QuickBooksConnection.objects.create(
                realm_id="realm-orphan",
                access_token_encrypted="ENC:x",
                refresh_token_encrypted="ENC:y",
                is_active=True,
            )

    def test_tokens_must_be_encrypted(self):
        """Saving a connection with plaintext tokens raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            QuickBooksConnection.objects.create(
                tenant=self.tenant_a,
                realm_id="realm-plain",
                access_token_encrypted="plaintext-token",
                refresh_token_encrypted="ENC:ok",
                is_active=True,
            )
        self.assertIn("access token must be encrypted", str(ctx.exception).lower())
        with self.assertRaises(ValueError) as ctx2:
            QuickBooksConnection.objects.create(
                tenant=self.tenant_a,
                realm_id="realm-plain2",
                access_token_encrypted="ENC:ok",
                refresh_token_encrypted="plaintext-refresh",
                is_active=True,
            )
        self.assertIn("refresh token must be encrypted", str(ctx2.exception).lower())

    def test_tokens_stored_encrypted(self):
        """Stored tokens must start with ENC: prefix (encryption enforced)."""
        conn = QuickBooksConnection.objects.create(
            tenant=self.tenant_a,
            realm_id="realm-enc",
            access_token_encrypted="ENC:stored-access",
            refresh_token_encrypted="ENC:stored-refresh",
            is_active=True,
        )
        self.assertIsNotNone(conn.tenant)
        self.assertTrue(
            conn.access_token_encrypted.startswith("ENC:"),
            "access_token_encrypted must be encrypted",
        )
        self.assertTrue(
            conn.refresh_token_encrypted.startswith("ENC:"),
            "refresh_token_encrypted must be encrypted",
        )

    def test_refresh_updates_only_that_connection(self):
        """Token refresh updates only the specified connection."""
        from unittest.mock import patch

        from fiscal.services.qb_oauth import refresh_tokens

        conn_a = QuickBooksConnection.objects.create(
            tenant=self.tenant_a,
            realm_id="realm-a",
            access_token_encrypted="ENC:old-a",
            refresh_token_encrypted="ENC:ref-a",
            is_active=True,
        )
        conn_b = QuickBooksConnection.objects.create(
            tenant=self.tenant_b,
            realm_id="realm-b",
            access_token_encrypted="ENC:old-b",
            refresh_token_encrypted="ENC:ref-b",
            is_active=True,
        )
        token_b_before = conn_b.access_token_encrypted

        def fake_post(url, **kwargs):
            class Resp:
                status_code = 200

                @staticmethod
                def json():
                    return {
                        "access_token": "new-access-a",
                        "refresh_token": "new-refresh-a",
                        "expires_in": 3600,
                    }

            return Resp()

        with patch("fiscal.services.qb_oauth.get_qb_credentials", return_value=("client_id", "client_secret")):
            with patch("fiscal.services.qb_oauth.requests.post", side_effect=fake_post):
                with patch("fiscal.services.qb_oauth.encrypt_string", side_effect=lambda x: f"ENC:{x}"):
                    with patch(
                        "fiscal.services.qb_oauth.decrypt_string",
                        side_effect=lambda x: x[4:] if x.startswith("ENC:") else x,
                    ):
                        ok, err = refresh_tokens(conn_a)
        self.assertTrue(ok, err)
        conn_a.refresh_from_db()
        conn_b.refresh_from_db()
        self.assertEqual(conn_a.access_token_encrypted, "ENC:new-access-a")
        self.assertEqual(conn_b.access_token_encrypted, token_b_before)

    def test_oauth_callback_stores_tokens_for_correct_tenant(self):
        """OAuth callback passes the tenant from state to exchange_code_for_tokens."""
        factory = RequestFactory()
        request = factory.get(
            "/api/integrations/quickbooks/oauth/callback/",
            {"code": "auth-code", "realmId": "realm-123", "state": "tenant-a"},
        )
        request.user = self.user_a
        request.user.is_staff = True
        request.session = {}

        with patch("fiscal.services.qb_oauth.exchange_code_for_tokens") as mock_exchange:
            with patch("fiscal.services.qb_oauth.get_redirect_uri", return_value="https://example.com/callback"):
                mock_exchange.return_value = ({"realm_id": "realm-123"}, None)
                response = api_qb_oauth_callback(request)

        mock_exchange.assert_called_once()
        # exchange_code_for_tokens(code, redirect_uri, realm_id, tenant=tenant)
        call_args, call_kwargs = mock_exchange.call_args
        self.assertEqual(call_args[0], "auth-code")
        self.assertEqual(call_args[2], "realm-123")
        self.assertEqual(call_kwargs.get("tenant"), self.tenant_a)

    def test_oauth_callback_tenant_mismatch_returns_400(self):
        """OAuth callback returns 400 when state does not match resolved tenant (tampering)."""
        factory = RequestFactory()
        request = factory.get(
            "/api/integrations/quickbooks/oauth/callback/",
            {"code": "auth-code", "realmId": "realm-123", "state": "tenant-a"},
        )
        request.user = self.user_a
        request.user.is_staff = True
        request.session = {}
        # First read returns tenant-a (lookup), second read returns tenant-b (tampered)
        state_reads = ["tenant-a", "tenant-b"]
        original_get = request.GET.get

        def get(key, default=None):
            if key == "state" and state_reads:
                return state_reads.pop(0)
            return original_get(key, default)

        request.GET.get = get
        with patch("fiscal.services.qb_oauth.exchange_code_for_tokens"):
            with patch("fiscal.services.qb_oauth.get_redirect_uri", return_value="https://example.com/callback"):
                response = api_qb_oauth_callback(request)
        self.assertEqual(response.status_code, 400)
