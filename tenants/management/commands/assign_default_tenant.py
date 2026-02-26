"""
Assign all rows with tenant_id=null to the default tenant.
Use after migrating SQLite data to Postgres so dashboard/receipts show under one tenant.
Default tenant = first tenant by created_at, or --slug SLUG if given.
"""

from django.core.management.base import BaseCommand
from django.apps import apps


# Fiscal models that have a nullable tenant FK (from migration 0032 and models)
FISCAL_MODELS_WITH_TENANT = [
    "fiscal.Company",
    "fiscal.FiscalDevice",
    "fiscal.InvoiceSequence",
    "fiscal.DocumentSequence",
    "fiscal.FiscalDay",
    "fiscal.Receipt",
    "fiscal.Customer",
    "fiscal.Product",
    "fiscal.FDMSConfigs",
    "fiscal.TaxMapping",
    "fiscal.ActivityEvent",
    "fiscal.AuditEvent",
    "fiscal.FDMSApiLog",
    "fiscal.ReceiptSubmissionResponse",
    "fiscal.DebitNote",
    "fiscal.CreditNote",
]


class Command(BaseCommand):
    help = "Set tenant_id to the default tenant for all rows where tenant is null."

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            default=None,
            help="Use this tenant slug as default (default: first tenant by created_at).",
        )
        parser.add_argument(
            "--set-all-to",
            default=None,
            metavar="SLUG",
            help="Reassign ALL rows (not only null) to this tenant. Use to move everything under one tenant (e.g. fly1).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be updated, do not change data.",
        )

    def handle(self, *args, **options):
        from tenants.models import Tenant

        slug = options.get("slug")
        set_all_to = options.get("set_all_to")
        dry_run = options.get("dry_run", False)

        target_slug = set_all_to or slug
        if target_slug:
            tenant = Tenant.objects.filter(slug=target_slug).first()
            if not tenant:
                self.stdout.write(self.style.ERROR(f"No tenant with slug={target_slug!r} found."))
                return
        else:
            tenant = Tenant.objects.order_by("created_at").first()
            if not tenant:
                self.stdout.write(self.style.ERROR("No tenants in the database. Create one first."))
                return

        self.stdout.write(f"Target tenant: {tenant.name} (slug={tenant.slug}, id={tenant.pk})")
        if set_all_to:
            self.stdout.write(self.style.WARNING("Mode: reassign ALL rows to this tenant (--set-all-to)."))
        else:
            self.stdout.write("Mode: assign only rows where tenant is null.")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made."))

        total_updated = 0
        for model_label in FISCAL_MODELS_WITH_TENANT:
            try:
                model = apps.get_model(model_label)
            except LookupError:
                continue
            if not hasattr(model, "tenant"):
                continue
            if set_all_to:
                qs = model.objects.all()
            else:
                qs = model.objects.filter(tenant__isnull=True)
            count = qs.count()
            if count == 0:
                continue
            self.stdout.write(f"  {model_label}: {count} row(s) to update")
            if not dry_run:
                updated = qs.update(tenant=tenant)
                total_updated += updated
                self.stdout.write(self.style.SUCCESS(f"    -> updated {updated} to tenant {tenant.slug}"))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run complete. Run without --dry-run to apply."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. Total rows updated: {total_updated}."))
