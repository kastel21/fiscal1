# Generated manually - cascade delete devices

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0016_activityevent_auditevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditnoteimport",
            name="original_receipt",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="credit_note_imports",
                to="fiscal.receipt",
            ),
        ),
    ]
