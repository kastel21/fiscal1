# QuickBooks OAuth hardening: backfill tenant on QuickBooksConnection, then make tenant required.

import logging

import django.db.models.deletion
from django.db import migrations, models

logger = logging.getLogger(__name__)


def backfill_quickbooks_connection_tenant(apps, schema_editor):
    QuickBooksConnection = apps.get_model("fiscal", "QuickBooksConnection")
    Tenant = apps.get_model("tenants", "Tenant")
    for conn in QuickBooksConnection.objects.filter(tenant__isnull=True):
        tenant = Tenant.objects.filter(is_active=True).order_by("created_at").first()
        if not tenant:
            logger.warning(
                "QuickBooksConnection id=%s realm_id=%s has no tenant and no active Tenant exists; skipping.",
                conn.id,
                conn.realm_id,
            )
            continue
        conn.tenant = tenant
        conn.save(update_fields=["tenant"])
        logger.info(
            "QuickBooksConnection id=%s realm_id=%s assigned to tenant %s",
            conn.id,
            conn.realm_id,
            tenant.slug,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0040_quickbooks_tenant_isolation"),
        ("tenants", "0004_usertenant_through"),
    ]

    operations = [
        migrations.RunPython(backfill_quickbooks_connection_tenant, noop_reverse),
        migrations.AlterField(
            model_name="quickbooksconnection",
            name="tenant",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="quickbooks_connection",
                to="tenants.tenant",
            ),
        ),
    ]
