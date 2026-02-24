"""Device registration form - moved from fiscal.forms for package consistency."""

from django import forms


class DeviceRegistrationForm(forms.Form):
    """Form for FDMS device registration."""

    device_id = forms.IntegerField(
        label="Device ID",
        min_value=1,
        help_text="Sold or active device ID from ZIMRA.",
        widget=forms.NumberInput(attrs={"class": "form-input", "placeholder": "e.g. 12345"}),
    )
    activation_key = forms.CharField(
        label="Activation Key",
        max_length=8,
        min_length=8,
        help_text="8-symbol activation key (case insensitive).",
        widget=forms.TextInput(
            attrs={"class": "form-input", "placeholder": "e.g. 12AXC178", "maxlength": 8}
        ),
    )
    device_serial_no = forms.CharField(
        label="Device Serial Number",
        max_length=20,
        help_text="Serial number assigned by manufacturer (e.g. SN-001).",
        widget=forms.TextInput(
            attrs={"class": "form-input", "placeholder": "e.g. SN-001"}
        ),
    )
    device_model_name = forms.CharField(
        label="Device Model Name",
        max_length=100,
        help_text="Device model name (e.g. FDMS-Model-1).",
        widget=forms.TextInput(
            attrs={"class": "form-input", "placeholder": "e.g. FDMS-Model-1"}
        ),
    )
    device_model_version = forms.CharField(
        label="Device Model Version",
        max_length=50,
        help_text="Device model version (e.g. 1.0.0).",
        widget=forms.TextInput(
            attrs={"class": "form-input", "placeholder": "e.g. 1.0.0"}
        ),
    )

    def clean_activation_key(self):
        value = self.cleaned_data.get("activation_key", "").strip()
        if len(value) != 8:
            raise forms.ValidationError("Activation key must be exactly 8 characters.")
        return value
