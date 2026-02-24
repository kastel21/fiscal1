# SCALABLE MULTI-DEVICE REAL-TIME FDMS PLATFORM

## Full Production Architecture & Cursor Implementation Pack

Generated: 2026-02-13T23:57:20.066801 UTC

------------------------------------------------------------------------

# 1. ARCHITECTURE OVERVIEW

This document defines a production-grade, horizontally scalable,
real-time multi-device fiscal compliance platform integrating with ZIMRA
FDMS.

Core principles:

-   Device isolation
-   Queue-based execution
-   Event-driven UI updates
-   Immutable audit logging
-   Horizontal scalability
-   No in-memory state dependencies

------------------------------------------------------------------------

# 2. HIGH-LEVEL SYSTEM ARCHITECTURE

Frontend (Django Templates or React) ↓ WebSocket Django Channels
(Real-Time Layer) ↓ Django REST API ↓ Redis (Broker + Pub/Sub) ↓ Celery
Workers (Fiscal Engine) ↓ FDMS API

------------------------------------------------------------------------

# 3. DATABASE DESIGN

## FiscalDevice

-   device_id (unique)
-   serial_number
-   certificate
-   encrypted_private_key
-   status
-   last_receipt_global_no

## FiscalDay

-   device (FK)
-   fiscal_day_no
-   fiscal_day_date
-   status

## Receipt

-   device (FK)
-   fiscal_day (FK)
-   receipt_global_no
-   canonical
-   hash
-   signature
-   status

## ActivityEvent

-   timestamp
-   device (FK)
-   event_type
-   message
-   level

## AuditEvent

-   timestamp
-   device (FK)
-   action
-   metadata (JSON)

------------------------------------------------------------------------

# 4. CONCURRENCY SAFETY

All receipt global number increments must use:

-   transaction.atomic()
-   select_for_update()

Never allow concurrent increment without row locking.

------------------------------------------------------------------------

# 5. CELERY TASK ENGINE

Install:

    pip install celery redis

Define tasks:

-   submit_receipt_task
-   open_day_task
-   close_day_task

Each task must:

1.  Validate input
2.  Build canonical
3.  Generate hash
4.  Sign
5.  Call FDMS
6.  Verify response
7.  Persist to DB
8.  Emit WebSocket events
9.  Log ActivityEvent
10. Log AuditEvent

------------------------------------------------------------------------

# 6. WEBSOCKET REAL-TIME LAYER

Install:

    pip install channels

Configure Redis channel layer.

Each device subscribes to group:

    fdms_device_<device_id>

WebSocket events include:

-   receipt.progress
-   receipt.completed
-   fiscal.opened
-   fiscal.closed
-   error
-   activity

------------------------------------------------------------------------

# 7. LIVE RECEIPT PROGRESS SYSTEM

Celery stages emit progress:

0% Validating 20% Building canonical 40% Signing 60% Sending to FDMS 80%
Verifying 100% Completed

Frontend updates progress bar in real-time.

------------------------------------------------------------------------

# 8. ACTIVITY FEED SYSTEM

All major operations create ActivityEvent entries.

Events broadcast live to device WebSocket group.

UI prepends new events in feed panel.

------------------------------------------------------------------------

# 9. ADVANCED AUDIT TIMELINE

AuditEvent model captures:

-   device_registered
-   fiscal_day_opened
-   receipt_submitted
-   fiscal_day_closed
-   error_events

Timeline renders chronological fiscal lifecycle.

------------------------------------------------------------------------

# 10. DEVICE ISOLATION RULES

Every model must filter by device.

Never query receipts without device scoping.

WebSocket groups must be device-specific.

No shared mutable state.

------------------------------------------------------------------------

# 11. SCALING STRATEGY

Deploy stack:

-   NGINX
-   Gunicorn (HTTP)
-   Daphne (ASGI)
-   Redis
-   Celery workers

Multiple workers can run in parallel.

System remains safe due to DB locking and Redis coordination.

------------------------------------------------------------------------

# 12. SECURITY HARDENING

-   Encrypt private keys at rest
-   Restrict WebSocket authentication
-   Validate device ownership
-   Role-based menu rendering
-   Log all failed signature attempts
-   Enable log rotation

------------------------------------------------------------------------

# 13. PRODUCTION DEPLOYMENT CHECKLIST

-   Environment-based configuration
-   DEBUG = False
-   Secure cookies
-   HTTPS enforced
-   Redis password protected
-   Worker monitoring (systemd or supervisor)
-   Database backups enabled

------------------------------------------------------------------------

# 14. ENTERPRISE CAPABILITIES ACHIEVED

✔ Multi-device safe\
✔ Real-time UI updates\
✔ Queue-based fiscal engine\
✔ Horizontal scalability\
✔ Audit-compliant event trail\
✔ Production-ready architecture

------------------------------------------------------------------------

END OF DOCUMENT
