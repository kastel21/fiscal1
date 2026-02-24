# Generated manually - Company, Product, FiscalDevice.company

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0017_creditnoteimport_cascade_fiscaldevice_delete"),
    ]

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("tin", models.CharField(max_length=50)),
                ("vat_number", models.CharField(blank=True, max_length=50, null=True)),
                ("address", models.TextField()),
                ("phone", models.CharField(max_length=50)),
                ("email", models.EmailField(max_length=254)),
                ("currency_default", models.CharField(default="ZWG", max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "Company", "verbose_name_plural": "Companies"},
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("price", models.DecimalField(decimal_places=2, default=0, max_digits=15)),
                ("tax_code", models.CharField(default="VAT", max_length=10)),
                ("tax_percent", models.DecimalField(decimal_places=2, default=15, max_digits=5)),
                ("hs_code", models.CharField(max_length=20)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="products", to="fiscal.company")),
            ],
            options={"verbose_name": "Product", "verbose_name_plural": "Products", "ordering": ["name"]},
        ),
        migrations.AddField(
            model_name="fiscaldevice",
            name="company",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="devices", to="fiscal.company"),
        ),
    ]
