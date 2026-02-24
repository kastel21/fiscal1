# QB webhook: Receipt qb_id (unique), fiscal_status; nullable fiscal_day_no/receipt_global_no for PENDING stubs

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0029_receipt_submission_response"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="qb_id",
            field=models.CharField(blank=True, db_index=True, max_length=100, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="receipt",
            name="fiscal_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("PENDING", "Pending"),
                    ("FISCALISED", "Fiscalised"),
                    ("FAILED", "Failed"),
                ],
                db_index=True,
                max_length=20,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="receipt",
            name="fiscal_day_no",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="receipt",
            name="receipt_global_no",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
