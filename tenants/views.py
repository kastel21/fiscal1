"""
Tenant selection view. Requires login; only tenants the user belongs to are shown and selectable.
User onboarding: create_company lets a logged-in user create a tenant and become owner.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from tenants.forms import CompanyCreateForm
from tenants.models import Tenant, UserTenant
from tenants.utils import user_has_tenant_access

logger = logging.getLogger("tenants")


def _get_tenants_for_user(user):
    """Return queryset of active tenants the user may access (superusers see all)."""
    qs = Tenant.objects.filter(is_active=True).order_by("name")
    if user is None or not user.is_authenticated:
        return qs.none()
    if getattr(user, "is_superuser", False):
        return qs
    return user.tenants.filter(is_active=True).order_by("name")


@login_required
@require_http_methods(["GET", "POST"])
def select_tenant(request):
    """
    List active tenants the user may access; on POST validate and set session tenant_slug.
    Only tenants in request.user.tenants are shown and allowed (superusers see all).
    """
    if request.method == "POST":
        slug = (request.POST.get("tenant_slug") or "").strip()
        if slug:
            tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
            if tenant is not None and user_has_tenant_access(request.user, tenant):
                request.session["tenant_slug"] = tenant.slug
                return redirect("fdms_dashboard")
        return redirect("select_tenant")

    tenants = list(_get_tenants_for_user(request.user))
    if len(tenants) == 1:
        request.session["tenant_slug"] = tenants[0].slug
        next_url = request.GET.get("next", "").strip()
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=[request.get_host()]):
            return redirect(next_url)
        return redirect("fdms_dashboard")

    current_tenant_slug = request.session.get("tenant_slug") or ""
    return render(
        request,
        "tenants/select_tenant.html",
        {
            "tenants": tenants,
            "title": "Select Tenant",
            "current_tenant_slug": current_tenant_slug,
            "show_search": len(tenants) > 10,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def create_company(request):
    """
    User onboarding: create a company (Tenant), link user as owner, then go to dashboard.
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
                    "Tenant created by user",
                    extra={"tenant": tenant.slug, "user": request.user.username},
                )
                return redirect("fdms_dashboard")
            except Exception as e:
                logger.exception("Create company failed")
                form.add_error(None, str(e))
    else:
        form = CompanyCreateForm()

    return render(
        request,
        "onboarding/create_company.html",
        {"form": form},
    )
