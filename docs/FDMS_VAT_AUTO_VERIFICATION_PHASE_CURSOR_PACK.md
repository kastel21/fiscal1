# FDMS VAT AUTO-VERIFICATION PHASE

## Cursor Implementation Pack

------------------------------------------------------------------------

# OBJECTIVE

Automatically run `VerifyTaxpayerInformation` during device
registration, persist the returned taxpayer profile, and enforce VAT
rules system-wide.

This phase prevents: - VAT misuse errors - Receipt rejection due to VAT
mismatch - Manual VAT misconfiguration

------------------------------------------------------------------------

# PHASE OVERVIEW

1.  Call VerifyTaxpayerInformation before RegisterDevice
2.  Store taxpayer profile in database
3.  Derive VAT registration status
4.  Enforce VAT validation in receipt builder
5.  Expose VAT status in UI

------------------------------------------------------------------------

# STEP 1 --- Update Device Model

Add the following fields:

``` python
class FiscalDevice(models.Model):
    device_id = models.IntegerField()
    activation_key = models.CharField(max_length=8)
    serial_number = models.CharField(max_length=20)

    taxpayer_name = models.CharField(max_length=250, null=True)
    taxpayer_tin = models.CharField(max_length=10, null=True)
    vat_number = models.CharField(max_length=9, null=True)

    branch_name = models.CharField(max_length=250, null=True)
    branch_address = models.JSONField(null=True)

    is_vat_registered = models.BooleanField(default=False)
    verification_operation_id = models.CharField(max_length=60, null=True)
    verified_at = models.DateTimeField(null=True)
```

Run migrations.

------------------------------------------------------------------------

# STEP 2 --- Create Verification Service

Create:

services/device_verification.py

``` python
import requests
from django.conf import settings

def verify_taxpayer(device_id, activation_key, serial_no):
    payload = {
        "deviceID": device_id,
        "activationKey": activation_key,
        "deviceSerialNo": serial_no,
    }

    response = requests.post(
        f"{settings.FDMS_BASE_URL}/Public/v1/VerifyTaxpayerInformation",
        json=payload,
        timeout=30
    )

    response.raise_for_status()
    return response.json()
```

------------------------------------------------------------------------

# STEP 3 --- Integrate Into Registration Flow

Before RegisterDevice:

``` python
verification = verify_taxpayer(
    device.device_id,
    device.activation_key,
    device.serial_number,
)

device.taxpayer_name = verification["taxPayerName"]
device.taxpayer_tin = verification["taxPayerTIN"]
device.vat_number = verification.get("vatNumber")
device.branch_name = verification["deviceBranchName"]
device.branch_address = verification["deviceBranchAddress"]
device.verification_operation_id = verification["operationID"]
device.is_vat_registered = bool(verification.get("vatNumber"))
device.verified_at = timezone.now()

device.save()
```

------------------------------------------------------------------------

# STEP 4 --- VAT Enforcement Rule

Inside receipt payload builder:

``` python
if not device.is_vat_registered:
    for tax in receipt_taxes:
        if tax["taxPercent"] > 0:
            raise ValidationError(
                "VAT tax used while taxpayer is not VAT registered."
            )
```

------------------------------------------------------------------------

# STEP 5 --- UI VAT Display

Display:

Taxpayer Name TIN VAT Number (if available) VAT Status Badge

If not VAT registered: - Hide VAT selection - Disable VAT tax codes

------------------------------------------------------------------------

# VALIDATION CHECKLIST

Before allowing VAT in receipt:

-   device.is_vat_registered == True
-   vat_number exists
-   taxPercent \> 0 only allowed if VAT registered

------------------------------------------------------------------------

# FINAL FLOW

User enters activation details → VerifyTaxpayerInformation → Persist
taxpayer profile → RegisterDevice → Use stored VAT status for all
invoices

------------------------------------------------------------------------

END OF PHASE
