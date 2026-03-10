# Generated migration: FiscalDevice.tenant non-nullable for fiscal compliance.
# Backfills tenant_id for any existing device missing tenant, then makes the field required.

from django.db import migrations, models
import django.db.models.deletion


def backfill_fiscaldevice_tenant(apps, schema_editor):
    """Assign first active tenant to any FiscalDevice that has no tenant."""
    FiscalDevice = apps.get_model("fiscal", "FiscalDevice")
    Tenant = apps.get_model("tenants", "Tenant")
    default_tenant = Tenant.objects.filter(is_active=True).order_by("created_at").first()
    if default_tenant is None:
        return
    updated = FiscalDevice.objects.filter(tenant_id__isnull=True).update(tenant_id=default_tenant.pk)
    if updated:
        # Log would go here if needed
        pass


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0038_documentsequenceadjustment"),
        ("tenants", "0004_usertenant_through"),
    ]

    operations = [
        migrations.RunPython(backfill_fiscaldevice_tenant, noop_reverse),
        migrations.AlterField(
            model_name="fiscaldevice",
            name="tenant",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="devices",
                to="tenants.tenant",
                db_index=True,
            ),
        ),
    ]
