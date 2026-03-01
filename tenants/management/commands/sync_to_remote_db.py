"""
Sync data from the default database to a remote Postgres (SYNC_TARGET_DATABASE_URL or --target-url).
Dumps from default (dumpdata), truncates app tables on remote, loaddata into remote, resets sequences.
Both databases must be PostgreSQL. Run migrations on the remote DB first.
"""

import os
import tempfile
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection, connections

REMOTE_ALIAS = "sync_remote"
DEFAULT_TARGET_URL = "postgres://admin:netmannature@localhost:5432/fdms_db"

# Tables we never truncate (FKs from other tables reference them)
SKIP_TRUNCATE_TABLES = {"django_content_type", "auth_permission"}


def get_tables_to_truncate():
    """Return set of table names for all app models except contenttypes and auth.Permission."""
    tables = set()
    for model in apps.get_models():
        if model._meta.app_label == "contenttypes" or (
            model._meta.app_label == "auth" and model._meta.model_name == "permission"
        ):
            continue
        tables.add(model._meta.db_table)
    return tables


def truncate_remote_tables(remote_alias):
    """Truncate app tables on the remote DB (except contenttypes and auth_permission)."""
    tables = get_tables_to_truncate() - SKIP_TRUNCATE_TABLES
    if not tables:
        return
    # Quote table names for safety
    quoted = ", ".join(f'"{t}"' for t in sorted(tables))
    sql = f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"
    with connections[remote_alias].cursor() as cursor:
        cursor.execute(sql)


def reset_remote_sequences(remote_alias):
    """Run sqlsequencereset for main apps and execute on remote."""
    from io import StringIO

    app_labels = [
        "auth",
        "contenttypes",
        "sessions",
        "admin",
        "tenants",
        "fiscal",
        "legal",
        "offline",
        "django_celery_beat",
    ]
    out = StringIO()
    call_command("sqlsequencereset", *app_labels, stdout=out, database=remote_alias, no_color=True)
    sql = out.getvalue()
    if not sql.strip():
        return
    with connections[remote_alias].cursor() as cursor:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                cursor.execute(stmt)


class Command(BaseCommand):
    help = "Sync data from default DB to a remote Postgres (SYNC_TARGET_DATABASE_URL or --target-url)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--target-url",
            default=os.environ.get("SYNC_TARGET_DATABASE_URL", DEFAULT_TARGET_URL),
            help="Postgres URL for the remote DB (default: env SYNC_TARGET_DATABASE_URL or built-in default).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only dump to a file and report; do not connect to remote or load.",
        )

    def handle(self, *args, **options):
        target_url = (options.get("target_url") or "").strip()
        dry_run = options.get("dry_run", False)

        if not target_url or "postgres" not in target_url.lower():
            self.stdout.write(self.style.ERROR("A PostgreSQL target URL is required."))
            return

        default_engine = connection.settings_dict.get("ENGINE", "")
        if "postgresql" not in default_engine:
            self.stdout.write(self.style.ERROR("Default database must be PostgreSQL to sync."))
            return

        self.stdout.write("Dumping from default database...")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = f.name
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                call_command(
                    "dumpdata",
                    "--natural-foreign",
                    "--natural-primary",
                    "--exclude", "contenttypes",
                    "--exclude", "auth.Permission",
                    "--indent", "2",
                    stdout=f,
                )
            size = Path(tmp_path).stat().st_size
            self.stdout.write(self.style.SUCCESS(f"Fixture written ({size} bytes)."))

            if dry_run:
                self.stdout.write(self.style.WARNING("Dry run: not connecting to remote or loading."))
                return

            import dj_database_url
            remote_config = dj_database_url.parse(target_url, conn_max_age=0)
            remote_config["CONN_MAX_AGE"] = 0
            remote_config.setdefault("OPTIONS", {})
            remote_config.setdefault("TIME_ZONE", getattr(settings, "TIME_ZONE", "UTC"))
            if REMOTE_ALIAS not in settings.DATABASES:
                settings.DATABASES[REMOTE_ALIAS] = remote_config
            else:
                settings.DATABASES[REMOTE_ALIAS].update(remote_config)
            connections.close_all()

            self.stdout.write("Truncating tables on remote...")
            truncate_remote_tables(REMOTE_ALIAS)
            self.stdout.write("Loading fixture into remote...")
            call_command("loaddata", tmp_path, "--database=sync_remote", verbosity=1)
            self.stdout.write("Resetting sequences on remote...")
            reset_remote_sequences(REMOTE_ALIAS)
            self.stdout.write(self.style.SUCCESS("Sync to remote DB complete."))
        finally:
            if REMOTE_ALIAS in settings.DATABASES:
                del settings.DATABASES[REMOTE_ALIAS]
            if REMOTE_ALIAS in connections:
                try:
                    connections[REMOTE_ALIAS].close()
                except Exception:
                    pass
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
