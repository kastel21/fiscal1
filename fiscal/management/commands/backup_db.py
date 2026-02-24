"""
Management command: Backup database.
Supports SQLite (file copy) and PostgreSQL (pg_dump).
"""

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backup database to a timestamped file. SQLite: copy file. PostgreSQL: pg_dump."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default=os.environ.get("BACKUP_DIR", ""),
            help="Directory for backup files (default: BACKUP_DIR env or ./backups)",
        )
        parser.add_argument(
            "--retain",
            type=int,
            default=int(os.environ.get("BACKUP_RETAIN_DAYS", "7")),
            help="Number of backups to retain (default: 7)",
        )

    def handle(self, *args, **options):
        output_dir = options["output_dir"] or str(Path(settings.BASE_DIR) / "backups")
        retain = options["retain"]
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        db = settings.DATABASES["default"]
        engine = db.get("ENGINE", "")
        now = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        if "sqlite" in engine:
            src = db.get("NAME")
            if not src:
                self.stderr.write(self.style.ERROR("No database path configured."))
                return
            src_path = Path(src)
            if not src_path.exists():
                self.stderr.write(self.style.ERROR(f"Database file not found: {src_path}"))
                return
            dest = Path(output_dir) / f"db_{now}.sqlite3"
            shutil.copy2(src_path, dest)
            self.stdout.write(self.style.SUCCESS(f"Backed up SQLite to {dest}"))
        elif "postgresql" in engine:
            name = db.get("NAME", "fdms")
            user = db.get("USER", "")
            host = db.get("HOST", "localhost")
            port = db.get("PORT", "5432")
            dest = Path(output_dir) / f"db_{now}.sql"
            env = {**os.environ, "PGPASSWORD": db.get("PASSWORD", "") or ""}
            cmd = [
                "pg_dump",
                "-h", host,
                "-p", str(port),
                "-U", user,
                "-d", name,
                "-F", "p",  # plain SQL
            ]
            try:
                with open(dest, "wb") as f:
                    proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env)
                    if proc.returncode != 0:
                        dest.unlink(missing_ok=True)
                        self.stderr.write(self.style.ERROR(f"pg_dump failed: {proc.stderr.decode()}"))
                        return
                self.stdout.write(self.style.SUCCESS(f"Backed up PostgreSQL to {dest}"))
            except FileNotFoundError:
                self.stderr.write(
                    self.style.ERROR("pg_dump not found. Install PostgreSQL client tools.")
                )
                return
        else:
            self.stderr.write(self.style.ERROR(f"Backup not implemented for {engine}"))
            return

        # Prune old backups
        pattern = "db_*.sqlite3" if "sqlite" in engine else "db_*.sql"
        backups = sorted(Path(output_dir).glob(pattern), key=lambda p: p.stat().st_mtime)
        for old in backups[:-retain]:
            try:
                old.unlink()
                self.stdout.write(f"Pruned old backup: {old.name}")
            except OSError:
                pass
