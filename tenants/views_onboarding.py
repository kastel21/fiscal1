"""
3-step onboarding wizard: Company → Device → Register.
Step 1: Create company (Tenant + UserTenant), store tenant_slug in session.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from tenants.forms import CompanyCreateForm
from tenants.models import Tenant, UserTenant

logger = logging.getLogger("tenants")


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_company(request):
    """
    Step 1: Create company (Tenant), link user as owner, set session tenant_slug.
    Redirect to step 2: /onboarding/device/
    """
    if request.method == "POST":
        form = CompanyCreateForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            company_name = (data["company_name"] or "").strip()
            slug = (data["slug"] or "").strip().lower()
            device_id = data["device_id"]
            tin = (data.get("tin") or "").strip()
            vat_number = (data.get("vat_number") or "").strip()
            address = (data.get("address") or "").strip()
            try:
                with transaction.atomic():
                    tenant = Tenant.objects.create(
                        name=company_name,
                        slug=slug,
                        device_id=device_id,
                    )
                    if tin or vat_number or address:
                        from fiscal.models import Company
                        Company.all_objects.create(
                            tenant=tenant,
                            name=company_name,
                            tin=tin or "—",
                            vat_number=vat_number or "",
                            address=address or "—",
                            phone="—",
                            email="noreply@example.com",
                        )
                    UserTenant.objects.create(
                        user=request.user,
                        tenant=tenant,
                        role="owner",
                    )
                    request.session["tenant_slug"] = tenant.slug
                logger.info(
                    "tenant_created",
                    extra={"tenant": tenant.slug, "user": request.user.username},
                )
                return redirect("onboarding_device")
            except Exception as e:
                logger.exception("Onboarding step 1 failed")
                form.add_error(None, str(e))
    else:
        form = CompanyCreateForm()

    return render(
        request,
        "onboarding/onboarding_company.html",
        {"form": form, "step": 1, "step_label": "Company"},
    )
