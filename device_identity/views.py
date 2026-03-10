"""Device identity views. UI only - no crypto in templates."""

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import DeviceRegistrationForm, OnboardingRegisterForm
from .services import register_device

logger = logging.getLogger("device_identity")


@login_required
def register_device_view(request):
    """
    Device registration page. Form submit via HTMX for partial update.
    UI only reacts to service result.
    """
    form = DeviceRegistrationForm()
    success_message = None
    error_message = None
    device_status = None
    device_id = None

    tenant = getattr(request, "tenant", None)
    if request.method == "POST":
        form = DeviceRegistrationForm(request.POST)
        if form.is_valid():
            if not tenant:
                error_message = "Please select a company first."
            else:
                device, err = register_device(
                    tenant=tenant,
                    device_id=form.cleaned_data["device_id"],
                    activation_key=form.cleaned_data["activation_key"],
                    device_serial_no=form.cleaned_data["device_serial_no"],
                    device_model_name=form.cleaned_data.get("device_model_name") or "Unknown",
                    device_model_version=form.cleaned_data.get("device_model_version") or "v1",
                )
                if err:
                    error_message = err
                else:
                    success_message = f"Device {device.device_id} registered successfully."
                    device_id = device.device_id
        else:
            error_message = "Please correct the errors below."

    if device_id:
        from fiscal.models import FiscalDevice
        try:
            dev = FiscalDevice.objects.get(device_id=device_id)
            device_status = (
                f"Device {dev.device_id} is registered. "
                f"Certificate stored: Yes. Status: {'Active' if dev.is_registered else 'Inactive'}."
            )
        except FiscalDevice.DoesNotExist:
            pass
    elif request.GET.get("device_id"):
        from fiscal.models import FiscalDevice
        try:
            dev = FiscalDevice.objects.get(device_id=int(request.GET["device_id"]))
            device_status = (
                f"Device {dev.device_id}: Registered={dev.is_registered}, "
                f"Certificate stored: Yes."
            )
        except (FiscalDevice.DoesNotExist, ValueError):
            device_status = "Device not found."

    context = {
        "form": form,
        "success_message": success_message,
        "error_message": error_message,
        "device_status": device_status,
        "device_id": device_id,
    }

    if request.headers.get("HX-Request"):
        return render(request, "device_identity/register_device_partial.html", context)
    return render(request, "device_identity/register_device.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_register_device(request):
    """
    Wizard Step 3: Register device with FDMS. Requires onboarding_device_id in session.
    On success: log device_registered, redirect to dashboard.
    """
    device_pk = request.session.get("onboarding_device_id")
    if not device_pk:
        return redirect("onboarding_device")
    from fiscal.models import FiscalDevice
    try:
        device = FiscalDevice.all_objects.get(pk=device_pk)
    except (FiscalDevice.DoesNotExist, ValueError, TypeError):
        request.session.pop("onboarding_device_id", None)
        return redirect("onboarding_device")

    form = OnboardingRegisterForm(request.POST or None)
    error_message = None
    if request.method == "POST" and form.is_valid():
        activation_key = form.cleaned_data["activation_key"]
        tenant = getattr(device, "tenant", None) or getattr(request, "tenant", None)
        if not tenant:
            error_message = "No tenant associated with this device. Please select a company first."
        else:
            dev, err = register_device(
                tenant=tenant,
                device_id=device.device_id,
                activation_key=activation_key,
                device_serial_no=device.device_serial_no or "",
                device_model_name=device.device_model_name or "Unknown",
                device_model_version=getattr(device, "device_model_version", None) or "v1",
            )
            if err:
                error_message = err
            else:
                logger.info(
                    "device_registered",
                    extra={"device_id": device.device_id, "user": request.user.username},
                )
                request.session.pop("onboarding_device_id", None)
                return redirect("fdms_dashboard")

    return render(
        request,
        "onboarding/onboarding_register_device.html",
        {
            "form": form,
            "device": device,
            "error_message": error_message,
            "step": 3,
            "step_label": "Register",
        },
    )
