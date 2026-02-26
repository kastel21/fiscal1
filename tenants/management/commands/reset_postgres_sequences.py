"""
Reset PostgreSQL sequences after loaddata so next inserts get correct IDs.
Run after: python manage.py loaddata migration_fixture.json
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Reset PostgreSQL sequences for all apps (run after loaddata)."

    def handle(self, *args, **options):
        if "postgresql" not in (connection.settings_dict.get("ENGINE") or ""):
            self.stdout.write(self.style.WARNING("Not using PostgreSQL. No-op."))
            return

        from io import StringIO
        out = StringIO()
        call_command(
            "sqlsequencereset",
            "auth",
            "contenttypes",
            "sessions",
            "admin",
            "tenants",
            "dashboard",
            "device_identity",
            "fiscal",
            "invoices",
            "offline",
            "legal",
            "django_celery_beat",
            stdout=out,
        )
        sql = out.getvalue()
        if not sql.strip():
            self.stdout.write("No sequence reset SQL generated.")
            return
        with connection.cursor() as cursor:
            for statement in sql.split(";"):
                statement = statement.strip()
                if statement:
                    cursor.execute(statement)
        self.stdout.write(self.style.SUCCESS("PostgreSQL sequences reset."))
