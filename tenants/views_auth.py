"""
Tenant-aware login: after authentication, set session tenant and redirect to dashboard or tenant selection.
"""

from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render


def login_view(request):
    """
    Custom login: authenticate, then set tenant in session and redirect.
    - One tenant → set request.session["tenant_slug"], redirect to dashboard.
    - Multiple or zero tenants → redirect to select_tenant.
    """
    if request.user.is_authenticated:
        # Already logged in: send to tenant selection or dashboard
        tenants = request.user.tenants.filter(is_active=True)
        if tenants.count() == 1:
            request.session["tenant_slug"] = tenants.first().slug
            return redirect("fdms_dashboard")
        return redirect("select_tenant")

    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            tenants = user.tenants.filter(is_active=True)
            if tenants.count() == 1:
                tenant = tenants.first()
                request.session["tenant_slug"] = tenant.slug
                return redirect("fdms_dashboard")
            return redirect("select_tenant")
        # Invalid credentials: render form with errors
    else:
        form = AuthenticationForm(request)

    return render(request, "auth/login.html", {"form": form, "next": request.GET.get("next")})
