# Generated manually for FDMS VAT Auto-Verification Phase

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0022_add_invoice_sequence"),
    ]

    operations = [
        migrations.AddField(
            model_name="fiscaldevice",
            name="taxpayer_name",
            field=models.CharField(blank=True, max_length=250, null=True),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="taxpayer_tin",
            field=models.CharField(blank=True, max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="vat_number",
            field=models.CharField(blank=True, max_length=9, null=True),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="branch_name",
            field=models.CharField(blank=True, max_length=250, null=True),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="branch_address",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="is_vat_registered",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="verification_operation_id",
            field=models.CharField(blank=True, max_length=60, null=True),
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
