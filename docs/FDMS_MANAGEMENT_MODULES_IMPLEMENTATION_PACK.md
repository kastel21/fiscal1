# FDMS MANAGEMENT MODULES IMPLEMENTATION PACK

## Company, Device, and Product (HS Code Linked)

Generated: 2026-02-14T03:35:51.146890 UTC

------------------------------------------------------------------------

# OVERVIEW

This document defines the architecture and implementation plan for:

1.  Company Management
2.  Device Management
3.  Product Management (HS Code linked)

These modules form the foundation of a production-grade FDMS platform.

------------------------------------------------------------------------

# 1. COMPANY MANAGEMENT MODULE

## Purpose

Stores legal entity information used for:

-   Device registration
-   Receipt headers
-   Tax compliance
-   Multi-tenant expansion

## Django Model

class Company(models.Model): name = models.CharField(max_length=255) tin
= models.CharField(max_length=50) vat_number =
models.CharField(max_length=50, blank=True, null=True) address =
models.TextField() phone = models.CharField(max_length=50) email =
models.EmailField() currency_default = models.CharField(max_length=3,
default="ZWL") created_at = models.DateTimeField(auto_now_add=True)

## API Endpoints

GET /api/company/ PUT /api/company/

## UI Requirements

Fields: - Company Name - TIN - VAT Number - Address - Phone - Email -
Default Currency

Only Admin role can edit.

------------------------------------------------------------------------

# 2. DEVICE MANAGEMENT MODULE

## Purpose

Manages fiscal devices connected to FDMS.

## Django Model

class FiscalDevice(models.Model): company = models.ForeignKey(Company,
on_delete=models.CASCADE) device_id = models.IntegerField(unique=True)
serial_number = models.CharField(max_length=100) model_name =
models.CharField(max_length=100) model_version =
models.CharField(max_length=50) certificate = models.TextField()
private_key_encrypted = models.TextField() certificate_expiry =
models.DateField() status = models.CharField(max_length=30,
default="UNREGISTERED") last_receipt_global_no =
models.IntegerField(default=0) created_at =
models.DateTimeField(auto_now_add=True)

## API Endpoints

GET /api/devices/ POST /api/devices/ GET /api/devices/{id}/ POST
/api/devices/{id}/open-day/ POST /api/devices/{id}/close-day/

## UI Requirements

Device List Page: - Device ID - Serial Number - Status - Certificate
Expiry - Actions

Device Detail Page: - Fiscal Day Status - Last Receipt Number -
Certificate Days Remaining - Open Day Button - Close Day Button

Certificate Expiry Indicator: Green: \>60 days Yellow: 30--60 days Red:
\<30 days

------------------------------------------------------------------------

# 3. PRODUCT MANAGEMENT MODULE (HS CODE LINKED)

## Purpose

Ensures invoice safety and FDMS compliance.

HS Code must never be manually entered during invoice creation.

## Django Model

class Product(models.Model): company = models.ForeignKey(Company,
on_delete=models.CASCADE) name = models.CharField(max_length=255)
description = models.TextField(blank=True) price =
models.DecimalField(max_digits=15, decimal_places=2) tax_code =
models.CharField(max_length=10) tax_percent =
models.DecimalField(max_digits=5, decimal_places=2) hs_code =
models.CharField(max_length=20) is_active =
models.BooleanField(default=True) created_at =
models.DateTimeField(auto_now_add=True)

## API Endpoints

GET /api/products/ POST /api/products/ PUT /api/products/{id}/ DELETE
/api/products/{id}/

## UI Requirements

Product List: - Name - Price - Tax Percent - HS Code - Status

Add/Edit Product Form: - Name - Description - Price - Tax Code - Tax
Percent - HS Code

Only Admin role can manage products.

------------------------------------------------------------------------

# 4. INVOICE INTEGRATION FLOW

Invoice creation must:

1.  Select Device
2.  Select Product(s)
3.  Auto-fill:
    -   Tax Code
    -   Tax Percent
    -   HS Code
4.  Server calculates:
    -   receiptTaxes
    -   canonical string
    -   hash
    -   signature

No manual tax or HS entry allowed.

------------------------------------------------------------------------

# 5. ROLE-BASED ACCESS CONTROL

Admin: - Full access

Operator: - Invoice creation only

Viewer: - Dashboard only

Backend must enforce role validation.

------------------------------------------------------------------------

# 6. RECOMMENDED FRONTEND ROUTING

/dashboard /company /devices /devices/:id /products /products/new
/products/:id/edit /invoices /audit /settings

------------------------------------------------------------------------

# 7. ENTERPRISE STRUCTURE SUMMARY

Company ├── Devices └── Products └── Used in Invoice └── Used in FDMS
SubmitReceipt

------------------------------------------------------------------------

# 8. SECURITY NOTES

-   Encrypt private keys at rest
-   Validate company ownership server-side
-   Never expose HS code editing to operators
-   Log all device actions
-   Implement audit trail for product edits

------------------------------------------------------------------------

END OF DOCUMENT
