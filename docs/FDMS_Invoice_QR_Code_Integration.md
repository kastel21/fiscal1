# Invoice QR Code Integration – Verification & Preview (Cursor-Ready)

## Purpose
Embed **ZIMRA public verification QR codes** into:
- Invoice Preview screen
- Downloadable PDF invoices
- Printed receipts

This allows customers and auditors to verify fiscalization.

---

## ZIMRA Verification URL

Format:
```
https://fdmstest.zimra.co.zw/Receipt/Result
 ?deviceID={deviceID}
 &receiptDate={receiptDate}
 &receiptGlobalNo={receiptGlobalNo}
 &receiptQrData={receiptQrData}
```

Values MUST come from FDMS response.

---

## QR Code Generation

### Backend helper

```python
def build_verification_url(receipt):
    return (
        f"{FDMS_VERIFY_BASE}?"
        f"deviceID={receipt.device_id}"
        f"&receiptDate={receipt.receipt_date.isoformat()}"
        f"&receiptGlobalNo={receipt.receipt_global_no}"
        f"&receiptQrData={receipt.receipt_qr_data}"
    )
```

---

## Invoice Preview UI (React)

```tsx
<img src={`/api/receipts/${id}/qr`} alt="ZIMRA Verification QR" />
```

QR should be visible:
- Near totals
- With label: “Scan to verify with ZIMRA”

---

## Django QR Endpoint

```python
def receipt_qr(request, receipt_id):
    receipt = get_object_or_404(FiscalReceipt, id=receipt_id)
    url = build_verification_url(receipt)
    return generate_qr_response(url)
```

---

## PDF Invoice Integration

- Generate QR as SVG/PNG
- Embed bottom-right of invoice
- Include verification URL as text fallback

---

## Guards

- QR only shown if receipt is fiscalized
- Hide QR for draft/unsubmitted receipts
- Never allow manual override

---

## Action for Cursor

1. Add verification URL builder
2. Add QR generation endpoint
3. Embed QR in Invoice Preview screen
4. Embed QR in PDF invoices
5. Add tests verifying QR correctness

---

## Result

- Publicly verifiable fiscal invoices
- Compliance with ZIMRA expectations
- Professional, audit-ready invoices

