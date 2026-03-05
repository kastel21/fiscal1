# ZIMRA Section 10 compliant A4 Tax Invoice – fiscal fields, VAT breakdown, buyer

from django.db import migrations, models


def _decimal_field():
    return models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0035_receipt_operation_server_date_pdf"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="fiscal_invoice_number",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="receipt",
            name="receipt_number",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="receipt",
            name="fiscal_signature",
            field=models.TextField(blank=True, help_text="FDMS fiscal signature (device/signer)."),
        ),
        migrations.AddField(
            model_name="receipt",
            name="verification_code",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="receipt",
            name="subtotal_15",
            field=_decimal_field(),
        ),
        migrations.AddField(
            model_name="receipt",
            name="tax_15",
            field=_decimal_field(),
        ),
        migrations.AddField(
            model_name="receipt",
            name="subtotal_0",
            field=_decimal_field(),
        ),
        migrations.AddField(
            model_name="receipt",
            name="subtotal_exempt",
            field=_decimal_field(),
        ),
        migrations.AddField(
            model_name="receipt",
            name="total_tax",
            field=_decimal_field(),
        ),
        migrations.AddField(
            model_name="receipt",
            name="buyer_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="receipt",
            name="buyer_vat",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="receipt",
            name="buyer_tin",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="receipt",
            name="buyer_address",
            field=models.TextField(blank=True),
        ),
    ]
