"""
Dump data from current SQLite DB for loading into PostgreSQL.
Step 1: Run this while using SQLite (no DATABASE_URL or SQLite in use).
Step 2: Set DATABASE_URL to PostgreSQL, run migrate, then loaddata.
"""

from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Dump data from SQLite to a JSON fixture for loading into PostgreSQL later."

    def add_arguments(self, parser):
        parser.add_argument(
            "-o", "--output",
            default="migration_fixture.json",
            help="Output fixture file path (default: migration_fixture.json)",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"]).resolve()
        if not connection.settings_dict["ENGINE"].endswith("sqlite3"):
            self.stdout.write(
                self.style.WARNING(
                    "Current default database is not SQLite. "
                    "Unset DATABASE_URL (or point to SQLite) and run this command again."
                )
            )
            return

        self.stdout.write("Dumping data from SQLite (excluding contenttypes and auth.Permission)...")
        with open(output_path, "w", encoding="utf-8") as f:
            call_command(
                "dumpdata",
                "--natural-foreign",
                "--natural-primary",
                "--exclude", "contenttypes",
                "--exclude", "auth.Permission",
                "--indent", "2",
                stdout=f,
            )
        self.stdout.write(self.style.SUCCESS(f"Fixture written to: {output_path}"))

        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write("  1. Set DATABASE_URL to your PostgreSQL URL (e.g. in .env or shell).")
        self.stdout.write("  2. Create the database if needed: createdb -U postgres fdms")
        self.stdout.write("  3. Run: python manage.py migrate")
        self.stdout.write("  4. Run: python manage.py migrate django_celery_beat")
        self.stdout.write(f"  5. Run: python manage.py loaddata {output_path.name}")
        self.stdout.write("  6. Run: python manage.py reset_postgres_sequences")
        self.stdout.write("")
