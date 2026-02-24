"""Offline mode views. UI never alters queue contents."""

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.shortcuts import redirect

from fiscal.models import FiscalDevice
from offline.services.batch_submitter import BatchSubmitter


@staff_member_required
def retry_submit(request):
    """Manual retry of queued receipts. Supervised - no auto-mutation."""
    if request.method != "POST":
        return redirect("fdms_dashboard")
    device = FiscalDevice.objects.filter(is_registered=True).first()
    if not device:
        messages.warning(request, "No registered device.")
        return redirect("fdms_dashboard")
    result = BatchSubmitter.process_queue(device)
    if result["submitted"] > 0:
        messages.success(request, f"Submitted {result['submitted']} receipt(s).")
    if result["halted_reason"]:
        messages.warning(request, result["halted_reason"])
    if result["last_error"] and result["failed"] > 0:
        messages.error(request, result["last_error"])
    return redirect(request.META.get("HTTP_REFERER", "fdms_dashboard"))
