# REAL-TIME KPI DASHBOARD IMPLEMENTATION PACK

## Django + React + Chart.js

Generated: 2026-02-14T03:16:08.605346 UTC

------------------------------------------------------------------------

# OVERVIEW

This document provides a complete implementation guide for building:

1.  Enterprise KPI Dashboard
2.  React-based frontend architecture
3.  Live real-time updates
4.  Chart.js integration
5.  Production-ready structure

This pack is designed for Cursor step-by-step execution.

------------------------------------------------------------------------

# PHASE 1 --- BACKEND METRICS API

Create a new Django app:

    python manage.py startapp dashboard

------------------------------------------------------------------------

## 1.1 Metrics Endpoint

Create:

dashboard/services/metrics_service.py

Responsibilities:

-   Calculate:
    -   Active devices
    -   Fiscal day status distribution
    -   Receipts today
    -   Failed receipts
    -   Success rate (24h)
    -   FDMS latency avg
    -   Sales totals by currency
    -   Tax band breakdown
    -   Queue depth

------------------------------------------------------------------------

## 1.2 API View

Create:

dashboard/api.py

Expose endpoint:

GET /api/dashboard/metrics/

Response example:

{ "activeDevices": 12, "totalDevices": 15, "receiptsToday": 1284,
"failedReceipts": 3, "successRate": 99.2, "avgLatencyMs": 540, "sales":
{ "ZWL": 3245000, "USD": 12340 }, "taxBreakdown": \[ { "band": "15%",
"amount": 450000 }, { "band": "0%", "amount": 120000 } \] }

------------------------------------------------------------------------

# PHASE 2 --- WEBSOCKET REAL-TIME METRICS

Extend Channels consumer.

Emit:

-   receipt.completed
-   receipt.failed
-   fiscal.opened
-   fiscal.closed
-   metrics.updated

On receipt submission completion: Trigger recalculation and broadcast
metrics.

------------------------------------------------------------------------

# PHASE 3 --- REACT DASHBOARD STRUCTURE

Create:

frontend/src/

Structure:

src/ components/ KPICard.jsx ProgressBar.jsx ActivityFeed.jsx
ChartPanel.jsx charts/ TaxBreakdownChart.jsx ReceiptsTrendChart.jsx
pages/ Dashboard.jsx context/ DashboardContext.jsx services/ api.js
websocket.js

------------------------------------------------------------------------

# PHASE 4 --- DASHBOARD CONTEXT (STATE MANAGEMENT)

Create:

context/DashboardContext.jsx

Responsibilities:

-   Store metrics state
-   Store activity feed
-   Handle WebSocket updates
-   Trigger re-renders

Use React Context API.

------------------------------------------------------------------------

# PHASE 5 --- KPI CARDS

KPICard.jsx

Display:

-   Active Devices
-   Receipts Today
-   Failed Receipts
-   Success Rate
-   FDMS Latency
-   Sales Totals

Design:

-   Rounded cards
-   Soft shadows
-   Large numeric typography
-   Status color indicators

------------------------------------------------------------------------

# PHASE 6 --- LIVE CHARTS WITH CHART.JS

Install:

    npm install chart.js react-chartjs-2

------------------------------------------------------------------------

## 6.1 Receipts Trend Chart

Type: Line chart

Data: - Receipts per hour (today)

Live updates via WebSocket.

------------------------------------------------------------------------

## 6.2 Tax Breakdown Chart

Type: Doughnut chart

Data: - Tax band totals

------------------------------------------------------------------------

## 6.3 Sales Volume Chart

Type: Bar chart

Data: - ZWL vs USD totals

------------------------------------------------------------------------

# PHASE 7 --- ACTIVITY FEED PANEL

Display real-time events.

Scrollable panel with:

-   Timestamp
-   Event message
-   Status indicator

------------------------------------------------------------------------

# PHASE 8 --- LIVE PROGRESS BAR

For receipt submission.

Stages:

0% Validating 20% Building canonical 40% Signing 60% Sending to FDMS 80%
Verifying 100% Completed

Animate using React state transitions.

------------------------------------------------------------------------

# PHASE 9 --- DASHBOARD LAYOUT

Grid layout:

  ----------------------------------------------------
  \| KPI Row \|
  ----------------------------------------------------
  \| Receipts Trend \| Tax Breakdown \|

  ----------------------------------------------------

## \| Sales Chart \| Activity Feed \|

Use CSS grid or Tailwind grid utilities.

------------------------------------------------------------------------

# PHASE 10 --- REAL-TIME UPDATE FLOW

1.  Receipt submitted (Celery)
2.  Task completes
3.  Broadcast metrics.updated
4.  React WebSocket receives event
5.  Context updates state
6.  Charts and KPIs re-render

No polling required.

------------------------------------------------------------------------

# PHASE 11 --- PERFORMANCE OPTIMIZATION

-   Memoize chart components
-   Throttle WebSocket updates
-   Avoid full dashboard re-render
-   Lazy load heavy charts

------------------------------------------------------------------------

# PHASE 12 --- ENTERPRISE ADDITIONS

Optional:

-   Certificate expiry countdown widget
-   Device health heatmap
-   Queue depth gauge
-   7-day rolling success rate
-   Per-device drill-down modal

------------------------------------------------------------------------

# PHASE 13 --- SECURITY

-   Protect API with JWT/session auth
-   Validate device ownership
-   Authenticate WebSocket connections
-   Rate-limit metrics endpoint

------------------------------------------------------------------------

# FINAL RESULT

You now have:

✔ Real-time enterprise KPI dashboard ✔ Multi-device metrics ✔ Chart.js
live charts ✔ WebSocket-driven UI ✔ Scalable backend ✔ Production-ready
architecture

------------------------------------------------------------------------

END OF DOCUMENT
