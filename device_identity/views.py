"""Device identity views. UI only - no crypto in templates."""

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from .forms import DeviceRegistrationForm
from .services import register_device


@staff_member_required
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

    if request.method == "POST":
        form = DeviceRegistrationForm(request.POST)
        if form.is_valid():
            device, err = register_device(
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
