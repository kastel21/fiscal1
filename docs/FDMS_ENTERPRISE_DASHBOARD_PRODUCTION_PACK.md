# FDMS ENTERPRISE DASHBOARD --- PRODUCTION IMPLEMENTATION PACK

Generated: 2026-02-14T03:27:32.012852 UTC

This document upgrades the existing React KPI dashboard into a
production-grade enterprise control panel.

Included:

1.  Collapsible sidebar layout
2.  Role-based menu rendering (RBAC)
3.  Real WebSocket integration (Django Channels)
4.  Authentication layer (JWT)
5.  Production UI kit structure
6.  Multi-device selector
7.  Certificate expiry widget

------------------------------------------------------------------------

# PHASE 1 --- ENTERPRISE LAYOUT STRUCTURE

Update folder structure:

src/ layout/ Sidebar.jsx Topbar.jsx Layout.jsx auth/ AuthContext.jsx
ProtectedRoute.jsx devices/ DeviceSelector.jsx widgets/
CertificateExpiry.jsx

------------------------------------------------------------------------

# PHASE 2 --- COLLAPSIBLE SIDEBAR

Sidebar.jsx must:

-   Support collapse/expand
-   Persist state in localStorage
-   Render dynamic menu from role

Menu structure:

const MENU = { admin: \["Dashboard","Devices","Audit","Settings"\],
operator: \["Dashboard","Receipts"\], viewer: \["Dashboard"\] }

Toggle collapse using useState.

Layout grid:

  Sidebar   Main Content
  --------- --------------

Use Tailwind classes: - w-64 (expanded) - w-20 (collapsed) -
transition-all duration-300

------------------------------------------------------------------------

# PHASE 3 --- ROLE-BASED MENU RENDERING

AuthContext must provide:

{ user, role, token }

Sidebar renders:

MENU\[role\].map(item =\> render)

Never hardcode permissions in components. All permissions controlled via
role.

Backend must return role in JWT payload.

------------------------------------------------------------------------

# PHASE 4 --- AUTHENTICATION LAYER (JWT)

Backend (Django):

Install: pip install djangorestframework-simplejwt

Add endpoints: POST /api/token/ POST /api/token/refresh/

Frontend:

AuthContext handles:

-   login()
-   logout()
-   store token in memory (not localStorage in production)
-   attach token in axios interceptor

ProtectedRoute:

Redirect if no token.

------------------------------------------------------------------------

# PHASE 5 --- REAL WEBSOCKET INTEGRATION

Replace mock interval with real WebSocket.

Create:

services/websocket.js

Connect:

ws://localhost:8000/ws/fdms/`<device_id>`{=html}/

On message:

switch(event.type): - metrics.updated - receipt.progress -
receipt.completed - fiscal.closed - activity

Dispatch updates into DashboardContext.

Django Channels:

Group name: fdms_device\_`<device_id>`{=html}

Only allow authenticated users. Validate token in query string.

------------------------------------------------------------------------

# PHASE 6 --- MULTI-DEVICE SELECTOR

DeviceSelector.jsx

Dropdown listing:

-   Device ID
-   Serial number
-   Status

On change:

-   Update selectedDevice in context
-   Reconnect WebSocket
-   Fetch metrics for device

All dashboard widgets depend on selectedDevice.

------------------------------------------------------------------------

# PHASE 7 --- CERTIFICATE EXPIRY WIDGET

CertificateExpiry.jsx

Display:

-   Days remaining
-   Color indicator:

Green: \>60 days Yellow: 30--60 days Red: \<30 days

Backend must expose:

GET /api/devices/`<id>`{=html}/certificate-status/

Response:

{ expiresOn: "2026-12-01", daysRemaining: 42 }

Widget updates live via WebSocket event: certificate.updated

------------------------------------------------------------------------

# PHASE 8 --- PRODUCTION UI KIT STRUCTURE

Create design tokens:

theme.js:

{ colors: { primary: "#2563eb", danger: "#dc2626", success: "#16a34a",
warning: "#d97706" }, radius: "rounded-xl", shadow: "shadow-md" }

Create reusable components:

-   Card
-   Button
-   Badge
-   Modal
-   Table
-   LoadingSpinner

All UI must use shared components.

------------------------------------------------------------------------

# PHASE 9 --- ENTERPRISE DASHBOARD LAYOUT

  --------------------------------------------------
  \| Sidebar (collapsible) \| Topbar \|
  --------------------------------------------------
  \| KPI Cards \|

  --------------------------------------------------

## \| Charts (Trend + Tax) \|

## \| Sales Chart \| Activity Feed \| Cert Widget \|

Topbar includes:

-   Device selector
-   User menu
-   Logout
-   Notification bell

------------------------------------------------------------------------

# PHASE 10 --- SECURITY HARDENING

-   Do not store private keys in frontend
-   Validate device access server-side
-   WebSocket authentication required
-   Enforce HTTPS
-   Use refresh tokens securely
-   Role validation in backend views

------------------------------------------------------------------------

# PHASE 11 --- ENTERPRISE FEATURES READY

✔ Collapsible sidebar ✔ Role-based UI ✔ Real-time WebSocket ✔ JWT
authentication ✔ Multi-device dashboard ✔ Certificate expiry monitoring
✔ Production UI kit ✔ Secure architecture

------------------------------------------------------------------------

END OF DOCUMENT
