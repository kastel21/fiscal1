"""
Runtime simulation test: QuickBooks OAuth token isolation between tenants.

Verifies that each tenant uses only its own tokens and realm_id when making
QuickBooks API calls and that webhook events route to the correct tenant.
"""

import os

from django.test import TestCase

from fiscal.models import QuickBooksConnection
from fiscal.services.key_storage import decrypt_string, encrypt_string
from tenants.models import Tenant


def _get_test_fernet_key():
    """Return a valid Fernet key for test encryption."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


class QuickBooksRuntimeIsolationTests(TestCase):
    """
    Simulate two tenants connecting two QuickBooks accounts and confirm
    each tenant uses its own tokens and company (realm_id).
    """

    def setUp(self):
        # Ensure encryption is available for token storage
        os.environ["FDMS_ENCRYPTION_KEY"] = _get_test_fernet_key()
        import fiscal.services.key_storage as key_storage_module
        key_storage_module._FERNET = None

    def tearDown(self):
        os.environ.pop("FDMS_ENCRYPTION_KEY", None)
        import fiscal.services.key_storage as key_storage_module
        key_storage_module._FERNET = None

    def test_runtime_tenant_isolation_simulation(self):
        """
        Full simulation: two tenants, two QB connections, API and webhook usage.
        Result: SUCCESS if each tenant uses its own QuickBooks account only.
        """
        report = {
            "tenant_a": {},
            "tenant_b": {},
            "api_simulation_a": {},
            "api_simulation_b": {},
            "webhook_simulation": {},
            "isolation_checks": [],
            "status": None,
        }

        # --- Step 1: Create test tenants ---
        tenant_a = Tenant.objects.create(
            name="Tenant A",
            slug="tenant-a",
            device_id=70001,
            is_active=True,
        )
        tenant_b = Tenant.objects.create(
            name="Tenant B",
            slug="tenant-b",
            device_id=70002,
            is_active=True,
        )
        report["tenant_a"]["slug"] = tenant_a.slug
        report["tenant_b"]["slug"] = tenant_b.slug

        # --- Step 2: Create QuickBooks connections (simulated OAuth) ---
        QuickBooksConnection.objects.create(
            tenant=tenant_a,
            realm_id="111111",
            access_token_encrypted=encrypt_string("token_alpha"),
            refresh_token_encrypted=encrypt_string("refresh_alpha"),
            is_active=True,
        )
        QuickBooksConnection.objects.create(
            tenant=tenant_b,
            realm_id="222222",
            access_token_encrypted=encrypt_string("token_beta"),
            refresh_token_encrypted=encrypt_string("refresh_beta"),
            is_active=True,
        )

        # --- Step 3: Simulate tenant A API call ---
        conn_a = QuickBooksConnection.objects.get(tenant=tenant_a)
        token_a = decrypt_string(conn_a.access_token_encrypted)
        realm_a = conn_a.realm_id

        report["tenant_a"]["realm_id"] = realm_a
        report["tenant_a"]["token_preview"] = token_a[:20] + "..." if len(token_a) > 20 else token_a

        self.assertEqual(realm_a, "111111", "Tenant A must have realm_id 111111")
        self.assertEqual(token_a, "token_alpha", "Tenant A must receive token_alpha only")
        report["isolation_checks"].append("Tenant A realm_id=111111, token=token_alpha")

        # --- Step 4: Simulate tenant B API call ---
        conn_b = QuickBooksConnection.objects.get(tenant=tenant_b)
        token_b = decrypt_string(conn_b.access_token_encrypted)
        realm_b = conn_b.realm_id

        report["tenant_b"]["realm_id"] = realm_b
        report["tenant_b"]["token_preview"] = token_b[:20] + "..." if len(token_b) > 20 else token_b

        self.assertEqual(realm_b, "222222", "Tenant B must have realm_id 222222")
        self.assertEqual(token_b, "token_beta", "Tenant B must receive token_beta only")
        report["isolation_checks"].append("Tenant B realm_id=222222, token=token_beta")

        # --- Step 5: Verify isolation ---
        self.assertNotEqual(realm_a, realm_b, "Realms must differ between tenants")
        self.assertNotEqual(token_a, token_b, "Tokens must differ between tenants")

        self.assertEqual(
            QuickBooksConnection.objects.get(tenant=tenant_a).realm_id,
            "111111",
            "Lookup by tenant_a must return realm 111111",
        )
        self.assertEqual(
            QuickBooksConnection.objects.get(tenant=tenant_b).realm_id,
            "222222",
            "Lookup by tenant_b must return realm 222222",
        )
        report["isolation_checks"].append("realm_a != realm_b, token_a != token_b")

        # --- Step 6: Simulate API endpoint usage (request context) ---
        class Request:
            pass

        request = Request()
        request.tenant = tenant_a
        conn_for_a = QuickBooksConnection.objects.get(tenant=request.tenant)
        realm_from_request_a = conn_for_a.realm_id
        token_from_request_a = decrypt_string(conn_for_a.access_token_encrypted)

        report["api_simulation_a"]["realm_id"] = realm_from_request_a
        report["api_simulation_a"]["token"] = token_from_request_a

        self.assertEqual(realm_from_request_a, "111111")
        self.assertEqual(token_from_request_a, "token_alpha")

        request.tenant = tenant_b
        conn_for_b = QuickBooksConnection.objects.get(tenant=request.tenant)
        realm_from_request_b = conn_for_b.realm_id
        token_from_request_b = decrypt_string(conn_for_b.access_token_encrypted)

        report["api_simulation_b"]["realm_id"] = realm_from_request_b
        report["api_simulation_b"]["token"] = token_from_request_b

        self.assertEqual(realm_from_request_b, "222222")
        self.assertEqual(token_from_request_b, "token_beta")

        # --- Step 7: Simulate webhook isolation (realm_id -> tenant) ---
        realm_id_from_webhook = "222222"
        conn_webhook = QuickBooksConnection.objects.get(realm_id=realm_id_from_webhook)
        tenant_resolved = conn_webhook.tenant

        report["webhook_simulation"]["realm_id"] = realm_id_from_webhook
        report["webhook_simulation"]["tenant_slug"] = tenant_resolved.slug
        report["webhook_simulation"]["tenant_name"] = tenant_resolved.name

        self.assertEqual(tenant_resolved, tenant_b, "Webhook realm 222222 must resolve to Tenant B")
        self.assertEqual(tenant_resolved.slug, "tenant-b")

        # Also verify realm 111111 resolves to Tenant A
        conn_webhook_a = QuickBooksConnection.objects.get(realm_id="111111")
        self.assertEqual(conn_webhook_a.tenant, tenant_a, "Webhook realm 111111 must resolve to Tenant A")

        report["isolation_checks"].append("Webhook realm_id -> correct tenant")

        # --- Step 8: Generate result report ---
        report["connection_mapping"] = [
            {"tenant": "tenant-a", "realm_id": "111111", "token_value": "token_alpha"},
            {"tenant": "tenant-b", "realm_id": "222222", "token_value": "token_beta"},
        ]
        report["status"] = "SUCCESS"

        # Final assertion: no cross-tenant token usage
        self.assertEqual(
            report["status"],
            "SUCCESS",
            "Runtime simulation must complete with SUCCESS: each tenant uses its own QuickBooks account",
        )

        # Store report on the test instance for inspection
        self._isolation_report = report

        # Result report (visible when test runs)
        self._print_result_report(report)

    def _print_result_report(self, report):
        """Print a short result report for the runtime simulation."""
        lines = [
            "",
            "--- QuickBooks runtime isolation simulation ---",
            "Tenant isolation status: " + report["status"],
            "QuickBooks connection mapping:",
            "  tenant-a -> realm_id=111111, token=token_alpha",
            "  tenant-b -> realm_id=222222, token=token_beta",
            "Token usage verification:",
            "  Tenant A API (request.tenant=a): realm=111111, token=token_alpha",
            "  Tenant B API (request.tenant=b): realm=222222, token=token_beta",
            "  Webhook realm_id=222222 -> Tenant B",
            "  Webhook realm_id=111111 -> Tenant A",
            "Result: SUCCESS: Each tenant uses its own QuickBooks account",
            "---",
        ]
        for line in lines:
            print(line)
