from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("fiscal", "0037_company_logo"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentSequenceAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(choices=[("INVOICE", "Invoice"), ("CREDIT_NOTE", "Credit Note"), ("DEBIT_NOTE", "Debit Note")], db_index=True, max_length=20)),
                ("year", models.IntegerField(db_index=True)),
                ("mode", models.CharField(choices=[("set_next", "Set Next"), ("skip_by", "Skip By")], max_length=20)),
                ("value", models.IntegerField()),
                ("old_last_number", models.IntegerField()),
                ("new_last_number", models.IntegerField()),
                ("reason", models.TextField()),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="sequence_adjustments", to=settings.AUTH_USER_MODEL)),
                ("tenant", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="documentsequenceadjustment_records", to="tenants.tenant")),
            ],
            options={
                "verbose_name": "Document Sequence Adjustment",
                "verbose_name_plural": "Document Sequence Adjustments",
                "ordering": ["-changed_at"],
            },
        ),
    ]

