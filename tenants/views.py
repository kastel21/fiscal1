"""
Tenant selection view for session-based tenant in development.
Production must use X-Tenant-Slug header; session is a convenience for local dev.
"""

from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from tenants.models import Tenant


@require_http_methods(["GET", "POST"])
def select_tenant(request):
    """
    List active tenants; on POST save selected slug to session and redirect to dashboard.
    Exempt from tenant requirement (middleware); used when no tenant in header/session (DEBUG only redirect).
    """
    if request.method == "POST":
        slug = (request.POST.get("tenant_slug") or "").strip()
        if slug:
            try:
                tenant = Tenant.objects.get(slug=slug, is_active=True)
                request.session["tenant_slug"] = tenant.slug
                return redirect("fdms_dashboard")
            except Tenant.DoesNotExist:
                pass
        return redirect("select_tenant")

    tenants = list(Tenant.objects.filter(is_active=True).order_by("name"))
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
