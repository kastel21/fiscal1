"""
Admin-only views for tenant management (e.g. superuser onboarding).
"""

import logging

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.contrib.auth import get_user_model

from .forms import CompanyForm, CompanyUserCreateForm, DeviceForm, TenantOnboardingForm, UserForm
from .models import Tenant, UserTenant

User = get_user_model()
logger = logging.getLogger("tenants")

# Placeholder PEMs for FiscalDevice when registration will be run immediately (FDMS will replace).
PLACEHOLDER_CERT = "-----BEGIN CERTIFICATE-----\nPLACEHOLDER-PENDING-REGISTRATION\n-----END CERTIFICATE-----"
PLACEHOLDER_KEY = "-----BEGIN PRIVATE KEY-----\nPLACEHOLDER-PENDING-REGISTRATION\n-----END PRIVATE KEY-----"

# Session keys for wizard
SESSION_KEY_COMPANY = "onboarding_company"
SESSION_KEY_USER = "onboarding_user"
SESSION_KEY_DEVICE = "onboarding_device"


def _superuser_required(view_func):
    """Decorator: allow only superusers (use after staff_member_required)."""
    def wrapped(request, *args, **kwargs):
        if not getattr(request.user, "is_superuser", False):
            return redirect("admin:index")
        return view_func(request, *args, **kwargs)
    return wrapped


@staff_member_required
@_superuser_required
def create_company_with_user(request):
    """
    Create a company (Tenant) and its first user in one form. Automatically creates UserTenant.
    """
    form = CompanyUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
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
                logger.info(
                    "Company created",
                    extra={"tenant": tenant.slug, "created_by": getattr(request.user, "username", "")},
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
                user = User.objects.create_user(
                    username=(data["username"] or "").strip(),
                    email=(data["email"] or "").strip(),
                    password=data["password"],
                )
                UserTenant.objects.create(
                    user=user,
                    tenant=tenant,
                    role=(data.get("role") or "owner").strip(),
                )
        except Exception as e:
            logger.exception("Create company with user failed")
            form.add_error(None, str(e))
            return render(
                request,
                "admin/company_user_create.html",
                {"form": form, "title": "Create Company & User"},
            )
        messages.success(request, f"Company “{tenant.name}” and user “{user.username}” created.")
        return redirect("admin:index")
    return render(
        request,
        "admin/company_user_create.html",
        {"form": form, "title": "Create Company & User"},
    )


@staff_member_required
@_superuser_required
def create_tenant_onboarding(request):
    """
    Single-page onboarding: create tenant, assign user(s), create fiscal device, optionally register.
    """
    form = TenantOnboardingForm(request.POST or None)
    if request.method != "POST" or not form.is_valid():
        return render(
            request,
            "admin/tenant_onboarding.html",
            {"form": form, "title": "Tenant Onboarding"},
        )

    data = form.cleaned_data
    company_name = (data.get("company_name") or "").strip()
    slug = (data.get("slug") or "").strip().lower()
    device_id = data.get("device_id")
    username = (data.get("username") or "").strip()
    email_user = (data.get("email_user") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "user").strip()
    device_serial_no = (data.get("device_serial_no") or "").strip()
    device_model = (data.get("device_model") or "").strip()
    register_device_now = data.get("register_device_now") or False
    activation_key = (data.get("activation_key") or "").strip()

    certificate_pem = (data.get("certificate_pem") or "").strip()
    private_key_pem = (data.get("private_key_pem") or "").strip()
    if register_device_now:
        certificate_pem = certificate_pem or PLACEHOLDER_CERT
        private_key_pem = private_key_pem or PLACEHOLDER_KEY

    try:
        with transaction.atomic():
            # Step 1 – Create tenant
            tenant = Tenant.objects.create(
                name=company_name,
                slug=slug,
                device_id=device_id,
                device_model=device_model or "",
                serial_number=device_serial_no,
            )
            logger.info("Tenant created", extra={"tenant": tenant.slug})

            # Optional: create Company (fiscal) for TIN, address, etc.
            tin = (data.get("tin") or "").strip()
            vat_number = (data.get("vat_number") or "").strip()
            address = (data.get("address") or "").strip()
            phone = (data.get("phone") or "").strip()
            email_company = (data.get("email") or "").strip()
            if tin or vat_number or address or phone or email_company:
                from fiscal.models import Company
                Company.all_objects.create(
                    tenant=tenant,
                    name=company_name,
                    tin=tin or "—",
                    vat_number=vat_number or "",
                    address=address or "—",
                    phone=phone or "—",
                    email=email_company or "noreply@example.com",
                )

            # Step 2 – Create or get user, then UserTenant
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User.objects.create_user(
                    username=username,
                    email=email_user,
                    password=password,
                )
            else:
                if password:
                    user.set_password(password)
                    user.save(update_fields=["password"])
                if email_user and user.email != email_user:
                    user.email = email_user
                    user.save(update_fields=["email"])

            if not UserTenant.objects.filter(user=user, tenant=tenant).exists():
                UserTenant.objects.create(user=user, tenant=tenant, role=role)

            # Step 3 – Create fiscal device
            from fiscal.models import FiscalDevice
            device = FiscalDevice.all_objects.create(
                tenant=tenant,
                device_id=device_id,
                device_serial_no=device_serial_no,
                device_model_name=device_model,
                certificate_pem=certificate_pem,
                private_key_pem=private_key_pem,
            )

            # Step 4 – Optionally trigger device registration
            if register_device_now and activation_key:
                from tenants.context import set_current_tenant
                token = set_current_tenant(tenant)
                try:
                    from device_identity.services import register_device
                    device, reg_err = register_device(
                        tenant=tenant,
                        device_id=device_id,
                        activation_key=activation_key,
                        device_serial_no=device_serial_no or "ONBOARDING",
                        device_model_name=device_model or "Unknown",
                    )
                    if reg_err:
                        logger.warning(
                            "Onboarding: device registration failed",
                            extra={"tenant": tenant.slug, "device_id": device_id, "error": reg_err},
                        )
                finally:
                    from tenants.context import clear_current_tenant
                    clear_current_tenant(token)

    except Exception as e:
        logger.exception("Tenant onboarding failed")
        form.add_error(None, str(e))
        return render(request, "admin/tenant_onboarding.html", {"form": form, "title": "Tenant Onboarding"})

    messages.success(request, f"Tenant “{tenant.name}” ({tenant.slug}) created successfully.")
    return redirect("admin:tenants_tenant_changelist")


def _clear_wizard_session(request):
    """Remove wizard data from session."""
    for key in (SESSION_KEY_COMPANY, SESSION_KEY_USER, SESSION_KEY_DEVICE):
        request.session.pop(key, None)


@staff_member_required
def tenant_onboarding_wizard(request, step=1):
    """
    Multi-step wizard: 1=Company, 2=User, 3=Device, 4=Review & Submit.
    Stores intermediate data in session. Only superusers allowed (403 otherwise).
    """
    if not getattr(request.user, "is_superuser", False):
        return HttpResponseForbidden("Only superusers can access the tenant onboarding wizard.")

    step = max(1, min(4, int(step)))
    session = request.session

    if step > 1 and not session.get(SESSION_KEY_COMPANY):
        return redirect("tenant_wizard", step=1)
    if step > 2 and not session.get(SESSION_KEY_USER):
        return redirect("tenant_wizard", step=2)
    if step > 3 and not session.get(SESSION_KEY_DEVICE):
        return redirect("tenant_wizard", step=3)

    if step == 1:
        initial = session.get(SESSION_KEY_COMPANY) or {}
        form = CompanyForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            session[SESSION_KEY_COMPANY] = form.cleaned_data
            session.modified = True
            return redirect("tenant_wizard", step=2)
        return render(
            request,
            "admin/tenant_wizard.html",
            {"step": 1, "form": form, "title": "Tenant Onboarding — Company"},
        )

    if step == 2:
        initial = session.get(SESSION_KEY_USER) or {}
        form = UserForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            session[SESSION_KEY_USER] = form.cleaned_data
            session.modified = True
            return redirect("tenant_wizard", step=3)
        return render(
            request,
            "admin/tenant_wizard.html",
            {"step": 2, "form": form, "title": "Tenant Onboarding — User"},
        )

    if step == 3:
        initial = session.get(SESSION_KEY_DEVICE) or {}
        form = DeviceForm(request.POST or None, initial=initial)
        if request.method == "POST" and form.is_valid():
            session[SESSION_KEY_DEVICE] = form.cleaned_data
            session.modified = True
            return redirect("tenant_wizard", step=4)
        return render(
            request,
            "admin/tenant_wizard.html",
            {"step": 3, "form": form, "title": "Tenant Onboarding — Device"},
        )

    company_data = session.get(SESSION_KEY_COMPANY) or {}
    user_data = session.get(SESSION_KEY_USER) or {}
    device_data = session.get(SESSION_KEY_DEVICE) or {}

    if request.method == "POST":
        register_now = request.POST.get("register_device_now") == "on"
        activation_key = (request.POST.get("activation_key") or "").strip()
        if register_now and not activation_key:
            messages.error(request, "Activation key is required when registering the device now.")
        else:
            cert_pem = (device_data.get("certificate_pem") or "").strip()
            key_pem = (device_data.get("private_key_pem") or "").strip()
            if not register_now and (not cert_pem or not key_pem):
                messages.error(request, "Certificate and private key are required when not registering the device.")
            else:
                try:
                    with transaction.atomic():
                        company_name = (company_data.get("company_name") or "").strip()
                        slug = (company_data.get("slug") or "").strip().lower()
                        device_id = device_data.get("device_id")
                        device_serial_no = (device_data.get("device_serial_no") or "").strip()
                        device_model = (device_data.get("device_model") or "").strip()
                        if register_now:
                            cert_pem = cert_pem or PLACEHOLDER_CERT
                            key_pem = key_pem or PLACEHOLDER_KEY

                        tenant = Tenant.objects.create(
                            name=company_name,
                            slug=slug,
                            device_id=device_id,
                            device_model=device_model,
                            serial_number=device_serial_no,
                        )
                        logger.info("Tenant created", extra={"tenant": tenant.slug})

                        tin = (company_data.get("tin") or "").strip()
                        vat_number = (company_data.get("vat_number") or "").strip()
                        address = (company_data.get("address") or "").strip()
                        phone = (company_data.get("phone") or "").strip()
                        email_company = (company_data.get("email") or "").strip()
                        if tin or vat_number or address or phone or email_company:
                            from fiscal.models import Company
                            Company.all_objects.create(
                                tenant=tenant,
                                name=company_name,
                                tin=tin or "—",
                                vat_number=vat_number or "",
                                address=address or "—",
                                phone=phone or "—",
                                email=email_company or "noreply@example.com",
                            )

                        username = (user_data.get("username") or "").strip()
                        email_user = (user_data.get("email") or "").strip()
                        password = (user_data.get("password") or "").strip()
                        role = (user_data.get("role") or "user").strip()
                        user = User.objects.create_user(
                            username=username,
                            email=email_user,
                            password=password,
                        )
                        UserTenant.objects.create(user=user, tenant=tenant, role=role)

                        from fiscal.models import FiscalDevice
                        device = FiscalDevice.all_objects.create(
                            tenant=tenant,
                            device_id=device_id,
                            device_serial_no=device_serial_no,
                            device_model_name=device_model,
                            certificate_pem=cert_pem,
                            private_key_pem=key_pem,
                        )

                        if register_now and activation_key:
                            from tenants.context import set_current_tenant, clear_current_tenant
                            token = set_current_tenant(tenant)
                            try:
                                from device_identity.services import register_device
                                register_device(
                                    tenant=tenant,
                                    device_id=device_id,
                                    activation_key=activation_key,
                                    device_serial_no=device_serial_no or "WIZARD",
                                    device_model_name=device_model or "Unknown",
                                )
                            except Exception as e:
                                logger.warning(
                                    "Wizard: device registration failed",
                                    extra={"tenant": tenant.slug, "device_id": device_id, "error": str(e)},
                                )
                            finally:
                                clear_current_tenant(token)

                    _clear_wizard_session(request)
                    messages.success(request, "Tenant \"%s\" (%s) created successfully." % (tenant.name, tenant.slug))
                    return redirect("admin:tenants_tenant_changelist")
                except Exception as e:
                    logger.exception("Tenant wizard submission failed")
                    messages.error(request, str(e))

    return render(
        request,
        "admin/tenant_wizard.html",
        {
            "step": 4,
            "form": None,
            "title": "Tenant Onboarding — Review",
            "company_data": company_data,
            "user_data": user_data,
            "device_data": device_data,
        },
    )
