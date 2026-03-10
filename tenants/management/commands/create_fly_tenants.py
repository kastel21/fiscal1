"""
Management command: Create tenants fly1 and fly2 and corresponding staff users.
Users: fly1, fly2 with password netmannature and email takaengwa@gmail.com.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from tenants.models import Tenant
from tenants.signals import set_skip_auto_tenant

User = get_user_model()


class Command(BaseCommand):
    help = "Create tenants fly1 and fly2 and staff users with password netmannature and email takaengwa@gmail.com."

    def handle(self, *args, **options):
        password = "netmannature"
        email = "takaengwa@gmail.com"
        tenant_slugs = ["fly1", "fly2"]
        device_ids = [50001, 50002]  # Unique per tenant; avoid collision with existing FiscalDevice

        for slug, device_id in zip(tenant_slugs, device_ids):
            tenant, created = Tenant.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": slug.capitalize(),
                    "device_id": device_id,
                    "is_active": True,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created tenant: {tenant.slug} (device_id={tenant.device_id})"))
            else:
                self.stdout.write(f"Tenant already exists: {tenant.slug}")

            set_skip_auto_tenant(True)  # We assign tenant ourselves; avoid signal creating a second one
            try:
                user, user_created = User.objects.get_or_create(
                    username=slug,
                    defaults={
                        "email": email,
                        "is_staff": True,
                        "is_active": True,
                    },
                )
                if user_created:
                    user.set_password(password)
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"Created user: {user.username} (email={email})"))
                else:
                    user.set_password(password)
                    user.email = email
                    user.save()
                    self.stdout.write(f"Updated user: {user.username} (password and email set)")
            finally:
                set_skip_auto_tenant(False)

            # Link user to tenant for access control (UserTenant through model)
            if tenant.users.filter(pk=user.pk).exists():
                self.stdout.write(f"User {user.username} already in tenant {tenant.slug}")
            else:
                tenant.users.add(user, through_defaults={"role": "user"})
                self.stdout.write(self.style.SUCCESS(f"Assigned user {user.username} to tenant {tenant.slug}"))

        self.stdout.write(self.style.SUCCESS("Done. Tenants: fly1, fly2. Users: fly1, fly2 (password=netmannature, email=takaengwa@gmail.com)."))
