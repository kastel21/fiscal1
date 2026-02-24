# Phase 5 – Offline Mode & Batch / File Submission

## Objective
Enable **legally compliant offline operation** of the fiscal device and ensure **guaranteed eventual submission** of all fiscal data to ZIMRA FDMS.

Offline capability is **mandatory** for certification.

---

## Regulatory Truths (Non-Negotiable)

- Network outages are expected and tolerated
- Receipts issued offline are **still legally binding**
- All offline receipts **must** eventually reach FDMS
- Order of receipts **must never change**
- No receipt may be edited or deleted once issued

---

## Preconditions

Phase 5 is enabled only if:
- Phase 4 (Receipt Engine) is fully implemented
- Receipt signing works correctly
- Counters are monotonic and persisted

---

## Offline Detection

### Offline Conditions
- Network unreachable
- TLS handshake failure
- FDMS timeout

Offline detection must be **backend-driven**, not UI-driven.

---

## Offline Receipt Queue (Authoritative)

### Queue Characteristics
- Append-only
- Ordered by receipt number + timestamp
- Persistent (DB + filesystem backup)

### Queue States
```
QUEUED → SUBMITTING → SUBMITTED → FAILED
```

FAILED receipts require **manual review**, not auto-correction.

---

## Batch / File Submission Model

ZIMRA allows receipts to be:
- submitted individually (online)
- submitted later as a batch (offline recovery)

### Offline File Builder Responsibilities
- Serialize receipts in original order
- Preserve original timestamps
- Preserve signatures
- Include device identity metadata

Files must be **immutable once written**.

---

## Django App Design

### App: `offline`

#### Models
- OfflineReceiptQueue
- OfflineBatchFile
- SubmissionAttempt

#### Services
- OfflineDetector
- QueueManager
- BatchFileBuilder
- BatchSubmitter

---

## Replay & Recovery Flow

```
Offline → Online Detected
        ↓
Load QUEUED receipts
        ↓
Submit sequentially
        ↓
Mark SUBMITTED
        ↓
Update fiscal counters
```

Replay must stop immediately on error.

---

## Error Handling

| Error | Meaning | Action |
|---|---|---|
| Network | Still offline | Retry later |
| 401 | Cert invalid | Lock submissions |
| 422 | Payload rejected | Flag receipt |
| Ordering error | Logic bug | Halt system |

No receipt is skipped or reordered.

---

## UI Binding (Dashboard)

- Offline indicator (banner)
- Queue size display
- Last successful submission timestamp
- Manual retry button (supervised)

UI **never** alters queue contents.

---

## Cursor Prompt (Implementation)

> Implement Phase 5 by:
> - Creating an append-only offline receipt queue
> - Detecting offline state server-side
> - Building immutable batch files
> - Submitting receipts sequentially on recovery
> - Logging every submission attempt

DO NOT:
- reorder receipts
- auto-delete failed receipts
- allow UI mutation of queue

---

## Certification Notes

Auditors will check:
- Offline receipt continuity
- Replay correctness
- No data loss during outages
- Deterministic recovery behavior

Offline mode is a **certification gate**.

---

## Next Phase

After offline handling is complete:
→ Phase 6 (Operator & Auditor Dashboard)
