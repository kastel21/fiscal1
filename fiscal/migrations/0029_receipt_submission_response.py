# Generated manually for ReceiptSubmissionResponse

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0028_receipt_debit_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReceiptSubmissionResponse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("receipt_global_no", models.IntegerField(db_index=True)),
                ("fiscal_day_no", models.IntegerField(blank=True, null=True)),
                ("status_code", models.IntegerField()),
                ("response_payload", models.JSONField(default=dict)),
                ("validation_errors", models.JSONField(default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("device", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="submission_responses", to="fiscal.fiscaldevice")),
                ("receipt", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="submission_responses", to="fiscal.receipt")),
            ],
            options={
                "verbose_name": "Receipt Submission Response",
                "verbose_name_plural": "Receipt Submission Responses",
                "ordering": ["-created_at"],
            },
        ),
    ]
