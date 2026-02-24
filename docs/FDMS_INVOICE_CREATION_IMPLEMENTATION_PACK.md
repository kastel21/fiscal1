# FDMS INVOICE CREATION --- FULL IMPLEMENTATION PACK

## React UI + DRF Serializer + Signature-Safe Backend Flow

Generated: 2026-02-14T03:37:05.766085 UTC

------------------------------------------------------------------------

# OVERVIEW

This document provides a production-grade implementation guide for:

1.  Full React Invoice Creation Form UI
2.  Django DRF Serializer for invoice submission
3.  Canonical + signature-safe backend processing flow
4.  Invoice validation checklist
5.  Safe FDMS submission pipeline

Designed for Cursor step-by-step implementation.

------------------------------------------------------------------------

# PHASE 1 --- REACT INVOICE FORM UI (ENTERPRISE STRUCTURE)

Folder Structure:

src/ pages/InvoiceCreate.jsx components/invoice/ InvoiceHeader.jsx
InvoiceItemsTable.jsx InvoiceTotals.jsx InvoicePayments.jsx
CustomerSection.jsx

------------------------------------------------------------------------

## 1.1 Invoice Form Data Model (Frontend State)

Example state structure:

deviceId: null\
currency: "ZWL"\
customer:\
name: ""\
tin: ""

items:\
- productId: null\
description: ""\
quantity: 1\
unitPrice: 0\
taxPercent: 0\
taxCode: ""\
hsCode: ""\
lineTotal: 0

payments:\
- method: "CASH"\
amount: 0

------------------------------------------------------------------------

## 1.2 Invoice Header UI

Fields:

-   Device Selector (Dropdown)
-   Currency Selector
-   Receipt Type (FISCALINVOICE default)
-   Date (auto-set)

Device change triggers:

-   Product pricing reload
-   WebSocket reconnect

------------------------------------------------------------------------

## 1.3 Invoice Items Table

Columns:

Product \| Description \| Qty \| Unit Price \| Tax % \| HS Code \| Line
Total \| Remove

Rules:

-   Selecting product auto-fills taxPercent, taxCode, hsCode, unitPrice
-   Quantity recalculates lineTotal
-   Add row button

------------------------------------------------------------------------

## 1.4 Totals Section

Auto-calculated:

-   Subtotal
-   Tax Total (grouped by tax band)
-   Grand Total

All totals must match server-side recalculation.

------------------------------------------------------------------------

## 1.5 Payments Section

Fields:

-   Payment Method (CASH, CARD, MOBILE)
-   Amount

Validation:

Sum(payments) \>= grandTotal

------------------------------------------------------------------------

## 1.6 Submit Button Flow

1.  Validate locally
2.  POST to /api/invoices/
3.  Show progress modal
4.  Listen for receipt.progress WebSocket events
5.  Show success or failure modal

------------------------------------------------------------------------

# PHASE 2 --- DJANGO DRF SERIALIZER

File:

invoices/serializers.py

------------------------------------------------------------------------

class InvoiceItemSerializer(serializers.Serializer): product_id =
serializers.IntegerField() quantity =
serializers.DecimalField(max_digits=10, decimal_places=2)

class PaymentSerializer(serializers.Serializer): method =
serializers.CharField() amount = serializers.DecimalField(max_digits=15,
decimal_places=2)

class InvoiceCreateSerializer(serializers.Serializer): device_id =
serializers.IntegerField() currency = serializers.CharField()
customer_name = serializers.CharField(required=False, allow_blank=True)
customer_tin = serializers.CharField(required=False, allow_blank=True)
items = InvoiceItemSerializer(many=True) payments =
PaymentSerializer(many=True)

    def validate(self, data):
        if not data["items"]:
            raise serializers.ValidationError("At least one invoice item required.")
        return data

------------------------------------------------------------------------

# PHASE 3 --- CANONICAL + SIGNATURE-SAFE BACKEND FLOW

Safe Invoice Creation Flow:

1.  Validate serializer
2.  Fetch device with select_for_update()
3.  Increment receiptGlobalNo safely
4.  Load products
5.  Calculate line totals and grouped tax totals
6.  Convert totals to cents
7.  Build receiptTaxes string
8.  Fetch previousReceiptHash
9.  Build canonical string EXACTLY per spec
10. SHA256 hash
11. Sign with private key
12. Store receipt locally (PENDING)
13. Call FDMS SubmitReceipt
14. Verify server signature
15. Mark receipt SUCCESS or FAILED
16. Emit WebSocket updates

------------------------------------------------------------------------

Canonical String Order (NO SEPARATORS):

deviceID + receiptType + receiptCurrency + receiptGlobalNo +
receiptDate + receiptTotalInCents + receiptTaxes + previousReceiptHash
(if not first)

------------------------------------------------------------------------

Tax Line Concatenation:

taxCode + formattedTaxPercent + taxAmountInCents +
salesAmountWithTaxInCents

Tax percent formatting:

15 -\> 15.00\
14.5 -\> 14.50\
0 -\> 0.00

------------------------------------------------------------------------

# PHASE 4 --- VALIDATION CHECKLIST

Before submission:

✓ Device ACTIVE\
✓ Fiscal day OPEN\
✓ At least one item\
✓ Quantity \> 0\
✓ Product active\
✓ HS code exists\
✓ Tax percent correct\
✓ Payment total \>= receipt total\
✓ receiptGlobalNo incremented safely\
✓ previousReceiptHash correct\
✓ Canonical string verified\
✓ Hash base64 valid\
✓ Signature base64 valid

After submission:

✓ receiptServerSignature verified\
✓ Receipt stored SUCCESS\
✓ Audit log created

------------------------------------------------------------------------

# PHASE 5 --- FDMS SUBMISSION PIPELINE

View\
↓\
Serializer\
↓\
Service Layer\
↓\
Signature Engine\
↓\
FDMS HTTP Client\
↓\
Response Verification\
↓\
Database Update\
↓\
WebSocket Broadcast

------------------------------------------------------------------------

# PRODUCTION RESULT

You now have:

✓ Enterprise React invoice form\
✓ Secure DRF serializer\
✓ Signature-safe canonical builder\
✓ Safe receipt counter logic\
✓ Strict validation pipeline\
✓ WebSocket progress updates\
✓ FDMS-compliant submission flow

------------------------------------------------------------------------

END OF DOCUMENT
