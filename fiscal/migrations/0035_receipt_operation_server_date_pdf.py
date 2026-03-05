# ZIMRA FDMS Section 10 InvoiceA4: store operation_id, server_date from SubmitReceipt response; PDF file path

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0034_widen_product_tax_code"),
    ]

    operations = [
        migrations.AddField(
            model_name="receipt",
            name="operation_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="receipt",
            name="server_date",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="receipt",
            name="pdf_file",
            field=models.FileField(
                blank=True,
                help_text="ZIMRA-compliant InvoiceA4 PDF (Section 10/11/13).",
                null=True,
                upload_to="fiscal_invoices/%Y/%m/",
            ),
        ),
    ]
