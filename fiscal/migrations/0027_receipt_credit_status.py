# Generated migration for invoice credit tracking

from decimal import Decimal

from django.db import migrations, models


def backfill_credit_status(apps, schema_editor):
    Receipt = apps.get_model("fiscal", "Receipt")
    for r in Receipt.objects.filter(document_type="INVOICE").exclude(
        receipt_type__in=["CreditNote", "CREDITNOTE"]
    ):
        total = r.receipt_total or Decimal("0")
        credits = Receipt.objects.filter(
            original_invoice=r,
            receipt_type__in=["CreditNote", "CREDITNOTE"],
        ).exclude(fdms_receipt_id__isnull=True).exclude(fdms_receipt_id=0)
        credited = sum(-(c.receipt_total or Decimal("0")) for c in credits)
        if credited <= 0:
            r.credit_status = "ISSUED"
        elif credited >= total - Decimal("0.01"):
            r.credit_status = "FULLY_CREDITED"
        else:
            r.credit_status = "PARTIALLY_CREDITED"
        r.save(update_fields=["credit_status"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0026_add_receipt_qr_code_value"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="credit_status",
            field=models.CharField(
                max_length=30,
                choices=[
                    ("ISSUED", "Issued"),
                    ("PARTIALLY_CREDITED", "Partially Credited"),
                    ("FULLY_CREDITED", "Fully Credited"),
                ],
                default="ISSUED",
                db_index=True,
            ),
        ),
        migrations.RunPython(backfill_credit_status, noop),
    ]
