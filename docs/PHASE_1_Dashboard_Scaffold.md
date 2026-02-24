# Phase 1 – Operator Dashboard Scaffold (Django + HTMX)

## Purpose
Provide a minimal but extensible **operator dashboard scaffold** that supports:
- Device onboarding (Phase 1)
- Future fiscal operations (Phases 2–6)
- Strict separation between UI and business logic

This scaffold is **certification-safe** and **Cursor-friendly**.

---

## Architectural Principles

- UI never performs cryptography
- UI never constructs API payloads directly
- All actions go through service-layer business logic
- Navigation is **phase-gated**
- Errors are surfaced from backend truthfully

---

## Django App Structure

```
core/
  settings.py
  urls.py

dashboard/
  views.py
  urls.py
  templates/dashboard/
    base.html
    sidebar.html
    home.html

device_identity/
  models.py
  services.py
  forms.py
  views.py
  templates/device_identity/
    register_device.html
```

---

## Navigation Model (Phase-Gated)

### Sidebar Items

| Menu Item | Enabled When |
|---|---|
| Device Registration | Always |
| Device Status | After registration |
| Fiscal Day | After registration |
| Receipts | After fiscal day open |
| Imports | After registration |
| Audit | After activity exists |

Sidebar state is computed from backend device state.

---

## Base Template (`base.html`)

- Header: system name + environment (TEST / PROD)
- Sidebar: phase-aware navigation
- Main content area (HTMX swap target)
- Footer: certificate + device status indicator

---

## Device Registration Screen (Phase 1 UI)

### Fields (Operator Input)
- Device ID (read-only if preloaded)
- Activation Key
- Device Serial Number

### Hidden (Backend Only)
- CSR generation
- CN construction
- Keypair handling

### Actions
- Register Device
- View certificate (after success)
- Download certificate

---

## Business Logic Binding

UI calls only:

```
device_identity.services.register_device()
```

This service:
1. Generates CSR
2. Validates CN
3. Calls ZIMRA RegisterDevice
4. Stores certificate
5. Updates device state

UI only reacts to result.

---

## URL Map

```
/               → dashboard.home
/device/register → device_identity.register
```

---

## HTMX Interaction Pattern

- Form submit via HTMX
- Partial page update on success/error
- No page reloads
- Errors rendered inline

---

## Cursor Prompt (Scaffold Build)

> Build a Django + HTMX dashboard scaffold with:
> - Phase-gated sidebar
> - Device registration page wired to backend service
> - No cryptographic logic in templates
> - Clear separation of UI and business logic
> - Future-ready navigation slots

DO NOT:
- hardcode API calls in views
- expose CSR or private key
- allow navigation to locked phases

---

## Certification Notes

- UI actions are auditable
- Operator intent is explicit
- Cryptographic material never leaves backend
- Dashboard does not violate FDMS constraints

---

## Next Phase

After successful registration:
→ enable Phase 2 (mTLS + GetConfig / GetStatus)
