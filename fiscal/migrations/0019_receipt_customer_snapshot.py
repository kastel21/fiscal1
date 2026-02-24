# Add customer_snapshot to store name, tin, address, phone, email, reference, notes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0018_company_product_fiscaldevice_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="customer_snapshot",
            field=models.JSONField(default=dict, blank=True),
        ),
    ]
