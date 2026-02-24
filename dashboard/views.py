"""Dashboard views. Phase-gated operator UI."""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from .context import get_navigation_state


@staff_member_required
def home(request):
    """Dashboard home. Main content area."""
    ctx = get_navigation_state()
    ctx["page_title"] = "Operator Dashboard"
    return render(request, "dashboard/home.html", ctx)
