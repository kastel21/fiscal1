# QuickBooks → FDMS Integration Guide (Django)

## Purpose
This document explains how to integrate **QuickBooks** with a **Django-based FDMS application**
to fiscalize sales with **ZIMRA FDMS (Fiscal Device Gateway API v7.2)**.

Django acts as a **translation and compliance layer** between QuickBooks and FDMS.

---

## High-Level Architecture

```
QuickBooks → Django (Adapter) → FDMS
```

- QuickBooks: Source of sales data
- Django: Mapping, validation, signing
- FDMS: Fiscalisation authority

---

## Prerequisites

### QuickBooks
- QuickBooks Online account
- OAuth 2.0 Client ID & Secret
- Redirect URI configured
- Company ID (`realmId`)

### Django
- Python 3.9+
- Django + requests
- FDMS device certificate & private key

---

## Python Library

```bash
pip install python-quickbooks
```

---

## Authenticate with QuickBooks (OAuth 2.0)

Store securely:
- Access token
- Refresh token
- Realm ID

Use token refresh logic in background jobs.

---

## Initialize QuickBooks Client

```python
from quickbooks import QuickBooks

qb = QuickBooks(
    sandbox=False,
    consumer_key=QB_CLIENT_ID,
    consumer_secret=QB_CLIENT_SECRET,
    access_token=QB_ACCESS_TOKEN,
    access_token_secret=QB_REFRESH_TOKEN,
    company_id=QB_REALM_ID
)
```

---

## Fetch Sales from QuickBooks

```python
from quickbooks.objects.salesreceipt import SalesReceipt

sales = SalesReceipt.all(qb=qb)
```

Only process:
- Paid SalesReceipts
- Issued Invoices

---

## Map QuickBooks Sale → FDMS Receipt

### Field Mapping

| QuickBooks | FDMS |
|-----------|------|
| TxnDate | receiptDate |
| Line | receiptLines |
| TotalAmt | receiptTotal |
| PaymentMethod | receiptPayments |
| TaxCodeRef | taxID |

---

## Example Mapping Function

```python
def qb_to_fdms_receipt(qb_sale):
    return {
        "receipt": {
            "receiptType": "FiscalInvoice",
            "receiptCurrency": qb_sale.CurrencyRef.value,
            "receiptGlobalNo": get_next_global_no(),
            "receiptDate": qb_sale.TxnDate.strftime("%Y-%m-%dT%H:%M:%S"),
            "receiptLinesTaxInclusive": True,
            "receiptLines": [
                {
                    "receiptLineType": "Sale",
                    "receiptLineNo": i + 1,
                    "receiptLineName": line.Description,
                    "receiptLineQuantity": line.Qty,
                    "receiptLineTotal": line.Amount,
                    "taxID": map_tax(line.TaxCodeRef.value),
                }
                for i, line in enumerate(qb_sale.Line)
            ],
            "receiptTotal": qb_sale.TotalAmt
        }
    }
```

---

## Tax Mapping (Critical)

QuickBooks tax codes ≠ FDMS tax IDs.

Use FDMS `getConfig` to build mapping.

```python
QB_TAX_TO_FDMS = {
    "VAT15": 1,
    "ZERO": 2,
    "EXEMPT": 3
}
```

Never hardcode without validation.

---

## Payments Mapping

```python
"receiptPayments": [
  {
    "moneyTypeCode": "Cash",
    "paymentAmount": qb_sale.TotalAmt
  }
]
```

Rule:
```
sum(receiptPayments) == receiptTotal
```

---

## FDMS Signature Process

1. Canonicalize receipt data
2. Generate hash
3. Sign using device private key
4. Add `receiptDeviceSignature`
5. Submit to FDMS

Never reuse a signature.

---

## Submit to FDMS (Django)

```python
response = requests.post(
    f"{FDMS_URL}/Device/v1/{device_id}/SubmitReceipt",
    json=payload,
    headers=headers,
    cert=(CERT_PATH, KEY_PATH),
    verify=CA_CERT
)
```

---

## Error Handling Strategy

| FDMS Error | Action |
|----------|--------|
| 400 | Mapping / structure bug |
| 422 | Business rule violation |
| 500 | Retry once, then inspect |
| Network | Queue & retry |

Use Celery for reliability.

---

## Webhooks (Optional but Recommended)

QuickBooks webhooks:
- SalesReceipt created
- Invoice paid

Trigger Django task → FDMS SubmitReceipt.

---

## Refunds & Credit Notes

- QuickBooks RefundReceipt
- FDMS receiptType = CreditNote
- Negative totals must match original receipt

Store FDMS receipt reference.

---

## Best Practices
- Fiscalize only finalized sales
- Store FDMS receiptID back into QuickBooks
- Log operationID for audits
- Keep strict sequencing of counters

---

## Action for Cursor
1. Implement QuickBooks OAuth client
2. Build mapping layer
3. Validate taxes & totals
4. Generate FDMS signature
5. Submit receipt and persist result

