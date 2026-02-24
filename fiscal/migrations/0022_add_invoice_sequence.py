# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0021_add_tax_mapping"),
    ]

    operations = [
        migrations.CreateModel(
            name="InvoiceSequence",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("year", models.IntegerField(unique=True)),
                ("last_number", models.IntegerField(default=0)),
            ],
            options={
                "verbose_name": "Invoice Sequence",
                "verbose_name_plural": "Invoice Sequences",
            },
        ),
    ]
