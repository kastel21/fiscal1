# Generated manually for multi-tenant FDMS Ping every 5 minutes.

from django.db import migrations


def create_fdms_ping_schedule(apps, schema_editor):
    """Create django-celery-beat interval (5 min) and periodic task for fiscal.run_fdms_ping."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=5,
        period="minutes",
        defaults={"every": 5, "period": "minutes"},
    )
    PeriodicTask.objects.update_or_create(
        name="FDMS Ping (all tenants) every 5 min",
        defaults={
            "task": "fiscal.run_fdms_ping",
            "interval": interval,
            "enabled": True,
        },
    )


def remove_fdms_ping_schedule(apps, schema_editor):
    """Remove the periodic task and optionally the interval."""
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(task="fiscal.run_fdms_ping").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("fiscal", "0032_add_tenant_fks"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_fdms_ping_schedule, remove_fdms_ping_schedule),
    ]
