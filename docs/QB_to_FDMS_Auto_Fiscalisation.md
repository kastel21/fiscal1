# QuickBooks → FDMS Auto-Fiscalisation Integration (Cursor-Ready)

## Purpose
Automatically trigger FDMS receipt fiscalisation when **QuickBooks creates an invoice**, then:
- Store the fiscalised receipt locally
- Return FDMS data to QuickBooks
- Update the QuickBooks invoice with fiscal references (safe & auditable)

This document defines the **exact event flow, APIs, validation, and storage rules**.

---

## High-Level Flow (Authoritative)

```
QuickBooks Invoice Created
        ↓ (Webhook)
Django Webhook Endpoint
        ↓
Validate + Store QB Invoice (raw)
        ↓
Map QB → FDMS Receipt
        ↓
SubmitReceipt to FDMS
        ↓
Store Fiscal Receipt (global no, QR, signature)
        ↓
Respond + Update QB Invoice
```

⚠️ **QuickBooks never talks to FDMS directly**.

---

## 1️⃣ QuickBooks Webhook Handling

### Webhook Event
Listen for:
- `Invoice.Create`
- (Optional) `Invoice.Update` (ignored unless re-fiscalisation rules apply)

### Django Endpoint
```
POST /api/integrations/quickbooks/webhook
```

### Immediate Actions
- Verify QB webhook signature
- Persist raw QB payload
- ACK webhook fast (≤5s)

```python
QuickBooksEvent.objects.create(
    event_type="Invoice.Create",
    payload=raw_payload
)
```

---

## 2️⃣ QB Invoice Storage (MANDATORY)

Before fiscalisation, store the invoice snapshot.

```python
class QuickBooksInvoice(models.Model):
    qb_invoice_id = models.CharField(max_length=50, unique=True)
    qb_customer_id = models.CharField(max_length=50)
    currency = models.CharField(max_length=10)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    raw_payload = models.JSONField()
    fiscalised = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
```

Never fiscalise directly from webhook payload without storing it.

---

## 3️⃣ Mapping: QuickBooks → FDMS Receipt

### Required Mapping

| QuickBooks | FDMS |
|---------|------|
| Invoice.Id | internal reference |
| Line.Description | receiptLineName |
| Line.Qty | receiptLineQuantity |
| Line.Amount | receiptLineTotal |
| TaxCode | taxID (via mapping table) |
| Currency | receiptCurrency |
| TotalAmt | receiptTotal |

Tax mapping must come from **GetConfigs**.

---

## 4️⃣ FDMS Receipt Creation Rules

- receiptType = FiscalInvoice
- receiptDate = server time (ISO)
- receiptGlobalNo = proposed from GetStatus
- receiptCounter increments ONLY after success
- All validation happens BEFORE SubmitReceipt

---

## 5️⃣ SubmitReceipt Execution

```python
fdms_response = submit_receipt(mapped_receipt)
```

Success requires:
- receiptID
- receiptGlobalNo
- receiptQrData
- receiptServerSignature

If missing → treat as FAILURE.

---

## 6️⃣ Store Fiscal Receipt (MANDATORY)

```python
class FiscalReceipt(models.Model):
    source = "QUICKBOOKS"
    qb_invoice_id = models.CharField(max_length=50)
    receipt_global_no = models.CharField(max_length=20)
    receipt_id = models.CharField(max_length=100)
    receipt_qr_data = models.CharField(max_length=100)
    receipt_server_signature = models.TextField()
    raw_fdms_response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
```

This record is **immutable**.

---

## 7️⃣ Responding Back to QuickBooks

### What to send back
You do NOT overwrite totals.

You update metadata only:
- Custom field
- Memo / PrivateNote

### Example update
```json
{
  "PrivateNote": "Fiscalised: GlobalNo 000000018 | QR available"
}
```

Optionally store:
- receiptGlobalNo
- verification URL

---

## 8️⃣ Error Handling

### If FDMS fails:
- Mark QB invoice as `PENDING_FISCALISATION`
- Queue retry
- DO NOT update QB as fiscalised

### Never:
- Retry blindly
- Duplicate fiscalisation for same QB invoice

Idempotency key = QB Invoice ID.

---

## 9️⃣ Idempotency & Safety Rules

- One QB invoice → one FDMS receipt
- Replayed webhooks must NOT duplicate receipts
- Use database uniqueness constraints

---

## 10️⃣ UI & Visibility

Expose in UI:
- QB Invoice ID
- Fiscal status (Pending / Fiscalised / Failed)
- receiptGlobalNo
- QR verification link
- Retry button (admin/accountant only)

---

## 11️⃣ Tests to Implement

- QB invoice webhook → receipt created
- Duplicate webhook → no duplicate receipt
- FDMS failure → QB not updated
- Successful fiscalisation → QB updated

---

## Action for Cursor

1. Add QB webhook endpoint
2. Store raw QB invoice
3. Implement QB → FDMS mapping layer
4. Submit to FDMS
5. Store fiscal receipt
6. Update QB invoice metadata
7. Add idempotency guards
8. Add retry logic + tests

---

## One-Line Rule

> A QuickBooks invoice may trigger fiscalisation, but FDMS remains the source of fiscal truth.
