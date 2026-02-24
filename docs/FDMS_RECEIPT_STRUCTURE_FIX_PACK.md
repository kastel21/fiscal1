# FDMS SUBMIT RECEIPT STRUCTURE FIX PACK

## Fix RCPT025, RCPT026, RCPT027 Errors

This document contains precise implementation instructions to fix
receipt validation errors caused by incorrect receiptLines structure.

------------------------------------------------------------------------

# PROBLEM SUMMARY

FDMS validation errors:

-   RCPT025 -- Invalid tax is used\
-   RCPT026 -- Incorrectly calculated tax amount\
-   RCPT027 -- Incorrectly calculated total sales amount

Root cause: - receiptLines structure does NOT match FDMS
specification. - Missing required tax fields inside each receipt line.

------------------------------------------------------------------------

# REQUIRED RECEIPT LINE STRUCTURE (Per FDMS Spec)

Each receiptLine MUST contain:

-   taxCode
-   taxPercent
-   taxID

DO NOT use: - receiptLineTaxCode

------------------------------------------------------------------------

# CORRECT PAYLOAD STRUCTURE

## Correct receiptLines Example

{ "receiptLineType": "Sale", "receiptLineNo": 1, "receiptLineHSCode":
"11223344", "receiptLineName": "milk", "receiptLinePrice": 3.00,
"receiptLineQuantity": 1.00, "receiptLineTotal": 3.00, "taxCode": "517",
"taxPercent": 15.5, "taxID": 517 }

------------------------------------------------------------------------

## Correct receiptTaxes Example

{ "taxID": 517, "taxCode": "517", "taxPercent": 15.5, "taxAmount": 0.78,
"salesAmountWithTax": 5.78 }

------------------------------------------------------------------------

# IMPLEMENTATION STEPS FOR CURSOR

1)  Update Receipt Line Serializer / Builder

Replace: receiptLineTaxCode

With: taxCode taxPercent taxID

------------------------------------------------------------------------

2)  Ensure Tax Bucket Calculation Is Correct

VAT must be calculated per tax bucket:

from decimal import Decimal, ROUND_HALF_EVEN

TWOPLACES = Decimal("0.01")

def calculate_bucket_vat(net_total: Decimal, tax_percent: Decimal) -\>
Decimal: vat = (net_total \* tax_percent) / Decimal("100") return
vat.quantize(TWOPLACES, rounding=ROUND_HALF_EVEN)

------------------------------------------------------------------------

3)  Ensure receiptTotal = SUM(net) + SUM(VAT)

Before submission:

assert receiptTotal == sum(line_totals) + sum(tax_amounts)

------------------------------------------------------------------------

4)  Canonical Signing Rules (DO NOT CHANGE)

Canonical must use: - taxCode - taxPercent formatted to 2 decimals -
taxAmount in cents - salesAmountWithTax in cents

NO taxID inside canonical tax block.

------------------------------------------------------------------------

EXPECTED RESULT

After implementing:

-   RCPT025 disappears
-   RCPT026 disappears
-   RCPT027 disappears
-   Receipt validates successfully

------------------------------------------------------------------------

END OF DOCUMENT
