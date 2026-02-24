# CREDIT_DEBIT_FULL_IMPLEMENTATION_PACK.md

## Full FDMS Credit Note + Debit Note Implementation (With UI)

## Cursor-Ready Implementation Guide

------------------------------------------------------------------------

# OBJECTIVE

Implement full FDMS-compliant:

-   Fiscal Invoice
-   Credit Note
-   Debit Note

Including: - Backend logic - Sign handling - Canonical-safe signing -
Close day compatibility - React UI forms - Validation layer

This document is ready to paste into Cursor.

------------------------------------------------------------------------

# 1. DATABASE MODEL UPDATE

## Receipt Model

``` python
class Receipt(models.Model):

    RECEIPT_TYPES = (
        ("FISCALINVOICE", "Fiscal Invoice"),
        ("CREDITNOTE", "Credit Note"),
        ("DEBITNOTE", "Debit Note"),
    )

    receiptType = models.CharField(max_length=20, choices=RECEIPT_TYPES)
    referencedReceipt = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT
    )

    receiptGlobalNo = models.IntegerField()
    receiptCounter = models.IntegerField()
    receiptTotal = models.DecimalField(max_digits=18, decimal_places=2)
```

------------------------------------------------------------------------

# 2. SIGN RULE ENGINE

``` python
from decimal import Decimal

def apply_sign(value: Decimal, receipt_type: str) -> Decimal:
    if receipt_type == "CREDITNOTE":
        return -abs(value)
    return abs(value)
```

------------------------------------------------------------------------

# 3. RECEIPT BUILDER LOGIC

``` python
def build_receipt_lines(lines, receipt_type):

    built_lines = []

    for idx, line in enumerate(lines, start=1):

        net = Decimal(str(line["price"])) * Decimal(str(line["qty"]))
        tax_percent = Decimal(str(line["taxPercent"]))
        tax_amount = (net * tax_percent / Decimal("100")).quantize(Decimal("0.01"))

        net_signed = apply_sign(net, receipt_type)
        tax_signed = apply_sign(tax_amount, receipt_type)

        built_lines.append({
            "receiptLineType": "Sale",
            "receiptLineNo": idx,
            "receiptLineHSCode": line["hsCode"],
            "receiptLineName": line["name"],
            "receiptLinePrice": float(apply_sign(Decimal(str(line["price"])), receipt_type)),
            "receiptLineQuantity": float(line["qty"]),
            "receiptLineTotal": float(net_signed),
            "taxCode": str(line["taxID"]),
            "taxPercent": float(tax_percent),
            "taxID": line["taxID"],
        })

    return built_lines
```

------------------------------------------------------------------------

# 4. TAX AGGREGATION

``` python
def build_receipt_taxes(lines, receipt_type):

    buckets = {}

    for line in lines:
        key = line["taxID"]

        if key not in buckets:
            buckets[key] = {
                "taxID": line["taxID"],
                "taxCode": line["taxCode"],
                "taxPercent": line["taxPercent"],
                "taxAmount": 0,
                "salesAmountWithTax": 0,
            }

        buckets[key]["taxAmount"] += (
            Decimal(str(line["receiptLineTotal"])) *
            Decimal(str(line["taxPercent"])) / Decimal("100")
        )

        buckets[key]["salesAmountWithTax"] += (
            Decimal(str(line["receiptLineTotal"])) +
            (Decimal(str(line["receiptLineTotal"])) *
             Decimal(str(line["taxPercent"])) / Decimal("100"))
        )

    return [{
        **v,
        "taxAmount": float(v["taxAmount"]),
        "salesAmountWithTax": float(v["salesAmountWithTax"])
    } for v in buckets.values()]
```

------------------------------------------------------------------------

# 5. PAYLOAD RULES

If receiptType == CREDITNOTE:

-   receiptTotal must be negative
-   taxAmount must be negative
-   salesAmountWithTax must be negative
-   paymentAmount must be negative
-   referencedReceiptGlobalNo required

If receiptType == DEBITNOTE:

-   all values positive
-   referencedReceiptGlobalNo required

------------------------------------------------------------------------

# 6. REACT UI IMPLEMENTATION

## Receipt Type Selector

``` jsx
<select
  value={receiptType}
  onChange={(e) => setReceiptType(e.target.value)}
  className="border p-2 rounded"
>
  <option value="FISCALINVOICE">Fiscal Invoice</option>
  <option value="CREDITNOTE">Credit Note</option>
  <option value="DEBITNOTE">Debit Note</option>
</select>
```

------------------------------------------------------------------------

## Conditional Reference Field

``` jsx
{receiptType !== "FISCALINVOICE" && (
  <div>
    <label>Referenced Receipt</label>
    <input
      type="number"
      value={referencedReceipt}
      onChange={(e) => setReferencedReceipt(e.target.value)}
      className="border p-2 rounded w-full"
    />
  </div>
)}
```

------------------------------------------------------------------------

## Live Total Display

``` jsx
<div className="bg-gray-100 p-4 rounded mt-4">
  <div>Net: {netTotal.toFixed(2)}</div>
  <div>Tax: {taxTotal.toFixed(2)}</div>
  <div className="font-bold">
    Total: {grandTotal.toFixed(2)}
  </div>
</div>
```

------------------------------------------------------------------------

# 7. VALIDATION BEFORE SUBMIT

Block submission if:

-   CREDITNOTE and values not negative
-   DEBITNOTE and values negative
-   referencedReceipt missing for notes
-   total mismatch

------------------------------------------------------------------------

# 8. CLOSE DAY COMPATIBILITY

Counters must reflect:

FiscalInvoice → positive CreditNote → subtract DebitNote → add

Already covered in strict CloseDay engine.

------------------------------------------------------------------------

# 9. FINAL CHECKLIST

Before submit:

-   Correct sign logic
-   referencedReceiptGlobalNo included
-   Canonical string built with signed cents
-   Tax bucket math validated
-   receiptTotal matches tax aggregation

------------------------------------------------------------------------

END OF IMPLEMENTATION PACK
