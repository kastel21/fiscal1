"""
Backfill: create a tenant for every user who has no tenants and assign them to it.
Safe to run multiple times (skips users who already have at least one tenant).
"""

from django.contrib.auth import get_user_model
from django.db.models import Count
from django.core.management.base import BaseCommand

from tenants.signals import _create_tenant_for_user

User = get_user_model()


class Command(BaseCommand):
    help = "Create a tenant for each user who has no tenants and assign them to it (backfill)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report which users would get a tenant, do not create.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        users_without = User.objects.annotate(c=Count("tenants")).filter(c=0)
        count = users_without.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No users without tenants. Nothing to do."))
            return
        if dry_run:
            self.stdout.write(f"Would create tenant for {count} user(s):")
            for u in users_without[:50]:
                self.stdout.write(f"  - {u.username} (pk={u.pk})")
            if count > 50:
                self.stdout.write(f"  ... and {count - 50} more.")
            return
        created = 0
        for user in users_without:
            _create_tenant_for_user(user)
            created += 1
            self.stdout.write(self.style.SUCCESS(f"Created tenant for user {user.username}"))
        self.stdout.write(self.style.SUCCESS(f"Done. Created tenants for {created} user(s)."))
