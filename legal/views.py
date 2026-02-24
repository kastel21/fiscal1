"""Public legal pages and EULA acceptance."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect

from .models import EulaAcceptance
from .utils import user_has_accepted_eula


@require_http_methods(["GET"])
def eula_view(request):
    """
    Public End-User License Agreement page.
    URL: /legal/eula/
    No authentication required. Shows accept form for logged-in users who have not yet accepted.
    """
    has_accepted = user_has_accepted_eula(request.user) if request.user.is_authenticated else False
    show_accept_form = request.user.is_authenticated and not has_accepted
    context = {
        "last_updated": "February 2026",
        "show_accept_form": show_accept_form,
        "eula_already_accepted": has_accepted,
    }
    return render(request, "legal/eula.html", context)


@require_http_methods(["POST"])
@csrf_protect
def accept_eula_view(request):
    """
    Record that the current user has accepted the EULA.
    Login required. Redirects back to EULA page or 'next' param.
    """
    if not request.user.is_authenticated:
        messages.error(request, "You must be logged in to accept the terms.")
        return redirect("eula")
    EulaAcceptance.objects.get_or_create(user=request.user)
    messages.success(request, "You have accepted the End-User License Agreement.")
    next_url = request.POST.get("next") or request.GET.get("next") or "eula"
    if next_url == "eula":
        return redirect("eula")
    return redirect(next_url)


@require_http_methods(["GET"])
def terms_view(request):
    """Public Terms of Service. /legal/terms/. No authentication required."""
    return render(request, "legal/terms.html", {"last_updated": "February 2026"})


@require_http_methods(["GET"])
def privacy_view(request):
    """Public Privacy Policy. /legal/privacy/. No authentication required."""
    return render(request, "legal/privacy.html", {"last_updated": "February 2026"})


@require_http_methods(["GET"])
def dpa_view(request):
    """Public Data Processing Addendum. /legal/dpa/. No authentication required."""
    return render(request, "legal/dpa.html", {"last_updated": "February 2026"})


@require_http_methods(["GET"])
def cookies_view(request):
    """Public Cookie Policy. /legal/cookies/. No authentication required."""
    return render(request, "legal/cookies.html", {"last_updated": "February 2026"})
