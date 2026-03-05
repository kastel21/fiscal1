# Company logo for ZIMRA A4 invoice PDF (WeasyPrint)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0036_receipt_section10_fiscal_vat_buyer"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="logo",
            field=models.ImageField(blank=True, null=True, upload_to="company_logos/"),
        ),
    ]
