"""
Forms for tenant management and superuser onboarding.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from .models import Tenant


def _generate_unique_slug_from_name(company_name: str) -> str:
    """Generate a URL-friendly unique slug from company name."""
    base = slugify(company_name) or "company"
    base = base[:64].strip("-")
    if not base:
        base = "company"
    slug = base
    suffix = 0
    while Tenant.objects.filter(slug=slug).exists():
        suffix += 1
        slug = f"{base}-{suffix}"[:64]
    return slug

User = get_user_model()

ROLE_CHOICES = [
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("accountant", "Accountant"),
    ("user", "User"),
]

INPUT_CLASS = "form-input w-full"


class CompanyCreateForm(forms.Form):
    """User onboarding: create company (Tenant) and become owner. No user creation."""

    company_name = forms.CharField(
        max_length=255,
        label="Company Name",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Acme Ltd"}),
    )
    slug = forms.SlugField(
        max_length=64,
        required=False,
        label="Slug",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Leave blank to generate from company name"}),
        help_text="Leave blank to generate automatically from company name (e.g. Acme Ltd → acme-ltd).",
    )
    device_id = forms.IntegerField(
        label="Device ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
        help_text="Unique FDMS device ID for this company.",
    )
    tin = forms.CharField(
        max_length=50,
        required=False,
        label="TIN",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Tax ID"}),
    )
    vat_number = forms.CharField(
        max_length=50,
        required=False,
        label="VAT Number",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
    )

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip().lower()
        if not slug:
            company_name = (self.cleaned_data.get("company_name") or "").strip()
            if not company_name:
                raise forms.ValidationError("Slug is required, or enter a company name to generate it automatically.")
            slug = _generate_unique_slug_from_name(company_name)
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A company with this slug already exists.")
        return slug

    def clean_device_id(self):
        device_id = self.cleaned_data.get("device_id")
        if device_id is None:
            return device_id
        if Tenant.objects.filter(device_id=device_id).exists():
            raise forms.ValidationError("A tenant with this Device ID already exists.")
        return device_id

    def clean_tin(self):
        tin = (self.cleaned_data.get("tin") or "").strip()
        if not tin:
            return tin
        from fiscal.models import Company
        if Company.all_objects.filter(tin=tin).exists():
            raise forms.ValidationError("A company with this TIN already exists.")
        return tin


class CompanyForm(forms.Form):
    """Step 1: Company information."""

    company_name = forms.CharField(
        max_length=255,
        label="Company Name",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Acme Ltd"}),
    )
    slug = forms.SlugField(
        max_length=64,
        label="Slug",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "acme-ltd"}),
        help_text="Unique URL-friendly identifier (e.g. acme-ltd).",
    )
    tin = forms.CharField(
        max_length=50,
        required=False,
        label="TIN",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Tax ID"}),
    )
    vat_number = forms.CharField(
        max_length=50,
        required=False,
        label="VAT Number",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
    )
    email = forms.EmailField(
        required=False,
        label="Email",
        widget=forms.EmailInput(attrs={"class": INPUT_CLASS}),
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        label="Phone",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip().lower()
        if not slug:
            raise forms.ValidationError("Slug is required.")
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A tenant with this slug already exists.")
        return slug


COMPANY_USER_ROLE_CHOICES = [
    ("owner", "Owner"),
    ("admin", "Admin"),
    ("accountant", "Accountant"),
]


class CompanyUserCreateForm(forms.Form):
    """Single form: create company (Tenant) and first user with UserTenant."""

    # Company
    company_name = forms.CharField(
        max_length=255,
        label="Company Name",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Acme Ltd"}),
    )
    slug = forms.SlugField(
        max_length=64,
        label="Slug",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "acme-ltd"}),
        help_text="Unique URL-friendly identifier.",
    )
    device_id = forms.IntegerField(
        label="Device ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
        help_text="Unique FDMS device ID for this tenant.",
    )
    tin = forms.CharField(
        max_length=50,
        required=False,
        label="TIN",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    vat_number = forms.CharField(
        max_length=50,
        required=False,
        label="VAT Number",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
    )

    # User
    username = forms.CharField(
        max_length=150,
        label="Username",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "jane"}),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": INPUT_CLASS}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS}),
    )
    role = forms.ChoiceField(
        choices=COMPANY_USER_ROLE_CHOICES,
        initial="owner",
        label="Role",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )

    def clean_company_name(self):
        name = (self.cleaned_data.get("company_name") or "").strip()
        if not name:
            raise forms.ValidationError("Company name is required.")
        return name

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip().lower()
        if not slug:
            raise forms.ValidationError("Slug is required.")
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A company with this slug already exists.")
        return slug

    def clean_device_id(self):
        device_id = self.cleaned_data.get("device_id")
        if device_id is not None:
            from fiscal.models import FiscalDevice
            if FiscalDevice.all_objects.filter(device_id=device_id).exists():
                raise forms.ValidationError("A device with this Device ID already exists.")
        return device_id

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Username is required.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username


class UserForm(forms.Form):
    """Step 2: User creation/assignment."""

    username = forms.CharField(
        max_length=150,
        label="Username",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "jane"}),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"class": INPUT_CLASS}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"class": INPUT_CLASS}),
        help_text="Required for new users.",
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial="admin",
        label="Role",
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError("Username is required.")
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean(self):
        data = super().clean()
        if not data:
            return data
        username = (data.get("username") or "").strip()
        if username and not User.objects.filter(username=username).exists():
            if not (data.get("password") or "").strip():
                self.add_error("password", "Password is required when creating a new user.")
        return data


class DeviceForm(forms.Form):
    """Step 3: Fiscal device setup."""

    device_id = forms.IntegerField(
        label="Device ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )
    device_serial_no = forms.CharField(
        max_length=20,
        required=False,
        label="Serial Number",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    device_model = forms.CharField(
        max_length=100,
        required=False,
        label="Device Model",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Unknown"}),
    )
    certificate_pem = forms.CharField(
        required=False,
        label="Certificate (PEM)",
        widget=forms.Textarea(
            attrs={
                "class": f"{INPUT_CLASS} font-mono text-sm",
                "rows": 4,
                "placeholder": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
            }
        ),
        help_text="Leave blank if you will register the device in step 4 (FDMS will issue).",
    )
    private_key_pem = forms.CharField(
        required=False,
        label="Private Key (PEM)",
        widget=forms.Textarea(
            attrs={
                "class": f"{INPUT_CLASS} font-mono text-sm",
                "rows": 4,
                "placeholder": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
            }
        ),
        help_text="Leave blank if you will register the device in step 4.",
    )

    def clean_device_id(self):
        device_id = self.cleaned_data.get("device_id")
        if device_id is None:
            return device_id
        from fiscal.models import FiscalDevice
        if FiscalDevice.all_objects.filter(device_id=device_id).exists():
            raise forms.ValidationError("A device with this Device ID already exists.")
        return device_id


class TenantOnboardingForm(forms.Form):
    """
    Single-step onboarding: company, user, device, optional registration.
    """

    # Company Information
    company_name = forms.CharField(
        max_length=255,
        label="Company Name",
        widget=forms.TextInput(attrs={"class": "form-input w-full", "placeholder": "Acme Ltd"}),
    )
    slug = forms.SlugField(
        max_length=64,
        label="Slug",
        widget=forms.TextInput(attrs={"class": "form-input w-full", "placeholder": "acme-ltd"}),
        help_text="Unique URL-friendly identifier (e.g. acme-ltd).",
    )
    tin = forms.CharField(
        max_length=50,
        required=False,
        label="TIN",
        widget=forms.TextInput(attrs={"class": "form-input w-full", "placeholder": "Tax ID"}),
    )
    vat_number = forms.CharField(
        max_length=50,
        required=False,
        label="VAT Number",
        widget=forms.TextInput(attrs={"class": "form-input w-full"}),
    )
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={"class": "form-input w-full", "rows": 2}),
    )
    phone = forms.CharField(
        max_length=50,
        required=False,
        label="Phone",
        widget=forms.TextInput(attrs={"class": "form-input w-full"}),
    )
    email = forms.EmailField(
        required=False,
        label="Email",
        widget=forms.EmailInput(attrs={"class": "form-input w-full"}),
    )

    # User Information
    username = forms.CharField(
        max_length=150,
        label="Username",
        widget=forms.TextInput(attrs={"class": "form-input w-full", "placeholder": "jane"}),
    )
    email_user = forms.EmailField(
        label="User Email",
        widget=forms.EmailInput(attrs={"class": "form-input w-full"}),
    )
    password = forms.CharField(
        label="Password",
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-input w-full"}),
        help_text="Leave blank to keep existing password if user already exists.",
    )
    role = forms.ChoiceField(
        choices=ROLE_CHOICES,
        initial="admin",
        label="Role",
        widget=forms.Select(attrs={"class": "form-input w-full"}),
    )

    # Device Information
    device_id = forms.IntegerField(
        label="Device ID",
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "form-input w-full"}),
    )
    device_serial_no = forms.CharField(
        max_length=20,
        required=False,
        label="Serial Number",
        widget=forms.TextInput(attrs={"class": "form-input w-full"}),
    )
    device_model = forms.CharField(
        max_length=100,
        required=False,
        label="Device Model",
        widget=forms.TextInput(attrs={"class": "form-input w-full", "placeholder": "Unknown"}),
    )
    certificate_pem = forms.CharField(
        required=False,
        label="Certificate (PEM)",
        widget=forms.Textarea(
            attrs={
                "class": "form-input w-full font-mono text-sm",
                "rows": 4,
                "placeholder": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
            }
        ),
        help_text="Leave blank if you will register the device now (certificate will be issued by FDMS).",
    )
    private_key_pem = forms.CharField(
        required=False,
        label="Private Key (PEM)",
        widget=forms.Textarea(
            attrs={
                "class": "form-input w-full font-mono text-sm",
                "rows": 4,
                "placeholder": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
            }
        ),
        help_text="Leave blank if you will register the device now (key will be generated).",
    )

    # Registration Options
    register_device_now = forms.BooleanField(
        required=False,
        initial=False,
        label="Register device immediately with FDMS",
        widget=forms.CheckboxInput(attrs={"class": "rounded border-slate-300"}),
    )
    activation_key = forms.CharField(
        max_length=20,
        required=False,
        label="Activation Key (8 symbols)",
        widget=forms.TextInput(
            attrs={
                "class": "form-input w-full",
                "placeholder": "Required if registering now",
                "maxlength": "20",
            }
        ),
    )

    def clean_slug(self):
        slug = self.cleaned_data.get("slug", "").strip().lower()
        if not slug:
            raise forms.ValidationError("Slug is required.")
        if Tenant.objects.filter(slug=slug).exists():
            raise forms.ValidationError("A tenant with this slug already exists.")
        return slug

    def clean_device_id(self):
        device_id = self.cleaned_data.get("device_id")
        if device_id is None:
            return device_id
        from fiscal.models import FiscalDevice
        if FiscalDevice.all_objects.filter(device_id=device_id).exists():
            raise forms.ValidationError("A device with this Device ID already exists.")
        return device_id

    def clean(self):
        data = super().clean()
        if not data:
            return data
        username = (data.get("username") or "").strip()
        if username and not User.objects.filter(username=username).exists():
            if not (data.get("password") or "").strip():
                self.add_error("password", "Password is required when creating a new user.")
        if data.get("register_device_now") and not (data.get("activation_key") or "").strip():
            self.add_error(
                "activation_key",
                "Activation key is required when registering the device immediately.",
            )
        # When not registering now, certificate and private key are required for FiscalDevice
        if not data.get("register_device_now"):
            if not (data.get("certificate_pem") or "").strip():
                self.add_error("certificate_pem", "Certificate is required when not registering now.")
            if not (data.get("private_key_pem") or "").strip():
                self.add_error("private_key_pem", "Private key is required when not registering now.")
        return data
