# ZIMRA Section 11 QR code value for receipt verification

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0025_add_credit_debit_note_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="qr_code_value",
            field=models.TextField(blank=True),
        ),
    ]
