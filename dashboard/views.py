"""Dashboard views. Phase-gated operator UI."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .context import get_navigation_state


@login_required
def home(request):
    """Dashboard home. Main content area."""
    ctx = get_navigation_state()
    ctx["page_title"] = "Operator Dashboard"
    return render(request, "dashboard/home.html", ctx)
