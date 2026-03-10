"""
Device registration for user onboarding: create FiscalDevice record, then redirect to FDMS registration.
Wizard step 2: onboarding_device — add fiscal device, store device id in session.
"""

import logging

from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from fiscal.models import FiscalDevice
from fiscal.services.key_storage import encrypt_private_key

logger = logging.getLogger("fiscal")

# Placeholder PEMs until user runs RegisterDevice with FDMS
PLACEHOLDER_CERT = "-----BEGIN CERTIFICATE-----\nPLACEHOLDER-PENDING-REGISTRATION\n-----END CERTIFICATE-----"
PLACEHOLDER_KEY = "-----BEGIN PRIVATE KEY-----\nPLACEHOLDER-PENDING-REGISTRATION\n-----END PRIVATE KEY-----"


class OnboardingDeviceForm(forms.Form):
    """Form to create first fiscal device for a tenant (device_id, serial, model)."""

    device_id = forms.IntegerField(
        label="Device ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-input w-full"}),
        help_text="Must match the Device ID you entered when creating the company.",
    )
    device_serial_no = forms.CharField(
        max_length=20,
        required=False,
        label="Device Serial Number",
        widget=forms.TextInput(attrs={"class": "form-input w-full"}),
    )
    device_model = forms.CharField(
        max_length=100,
        required=False,
        label="Device Model",
        widget=forms.TextInput(attrs={"class": "form-input w-full", "placeholder": "e.g. FDMS-Model-1"}),
    )

    def __init__(self, tenant=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant

    def clean_device_id(self):
        device_id = self.cleaned_data.get("device_id")
        if device_id is None:
            return device_id
        if FiscalDevice.all_objects.filter(device_id=device_id).exists():
            raise forms.ValidationError("A device with this Device ID already exists.")
        if self.tenant and self.tenant.device_id and self.tenant.device_id != device_id:
            raise forms.ValidationError(
                "Device ID must match the company's Device ID (%s)." % self.tenant.device_id
            )
        return device_id


@login_required
def register_device_page(request):
    """
    Onboarding step after company creation: create FiscalDevice for the current tenant,
    then redirect to Device Registration page where the user can trigger register_device(device).
    """
    tenant = getattr(request, "tenant", None)
    if not tenant:
        # Resolve from session when middleware did not set request.tenant (e.g. tenant-exempt path)
        slug = request.session.get("tenant_slug")
        if slug:
            from tenants.models import Tenant
            tenant = Tenant.objects.filter(slug=slug, is_active=True).first()
        if not tenant:
            return redirect("select_tenant")

    # Optional: prevent creating a second device if one already exists for this tenant
    existing = FiscalDevice.all_objects.filter(tenant=tenant).first()
    if existing:
        # Already have a device; redirect to Device Registration to register it if needed
        return redirect(
            reverse("fdms_device") + f"?device_id={existing.device_id}"
        )

    initial = {"device_id": tenant.device_id} if tenant.device_id else None
    form = OnboardingDeviceForm(tenant=tenant, data=request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        device_id = form.cleaned_data["device_id"]
        device_serial_no = (form.cleaned_data.get("device_serial_no") or "").strip()
        device_model = (form.cleaned_data.get("device_model") or "").strip()
        key_stored = encrypt_private_key(PLACEHOLDER_KEY)
        FiscalDevice.all_objects.create(
            tenant=tenant,
            device_id=device_id,
            device_serial_no=device_serial_no or "",
            device_model_name=device_model,
            certificate_pem=PLACEHOLDER_CERT,
            private_key_pem=key_stored,
        )
        return redirect(
            reverse("fdms_device") + f"?device_id={device_id}"
        )

    return render(
        request,
        "onboarding/register_device.html",
        {
            "form": form,
            "tenant": tenant,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def onboarding_device(request):
    """
    Wizard Step 2: Add fiscal device for the tenant from session.
    Requires tenant_slug in session (set in step 1). Creates FiscalDevice, stores onboarding_device_id, redirects to step 3.
    """
    tenant_slug = request.session.get("tenant_slug")
    if not tenant_slug:
        return redirect("onboarding_company")
    from tenants.models import Tenant
    tenant = Tenant.objects.filter(slug=tenant_slug, is_active=True).first()
    if not tenant:
        return redirect("onboarding_company")

    # If tenant already has a device from this wizard, go to step 3
    existing = FiscalDevice.all_objects.filter(tenant=tenant).first()
    if existing:
        request.session["onboarding_device_id"] = existing.pk
        return redirect("onboarding_register_device")

    initial = {"device_id": tenant.device_id, "device_serial_no": "", "device_model": ""} if tenant.device_id else None
    form = OnboardingDeviceForm(tenant=tenant, data=request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        device_id = form.cleaned_data["device_id"]
        device_serial_no = (form.cleaned_data.get("device_serial_no") or "").strip()
        device_model = (form.cleaned_data.get("device_model") or "").strip()
        key_stored = encrypt_private_key(PLACEHOLDER_KEY)
        device = FiscalDevice.all_objects.create(
            tenant=tenant,
            device_id=device_id,
            device_serial_no=device_serial_no or "",
            device_model_name=device_model,
            certificate_pem=PLACEHOLDER_CERT,
            private_key_pem=key_stored,
        )
        request.session["onboarding_device_id"] = device.pk
        logger.info(
            "device_created",
            extra={"device_id": device_id, "tenant": tenant.slug},
        )
        return redirect("onboarding_register_device")

    return render(
        request,
        "onboarding/onboarding_device.html",
        {"form": form, "tenant": tenant, "step": 2, "step_label": "Device"},
    )
