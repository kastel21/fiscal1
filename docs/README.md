# FDMS Documentation Index

Documentation for the ZIMRA FDMS (Fiscal Data Management System) Django integration.

## Quick Links

| Document | Description |
|----------|-------------|
| [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) | Staging, production, backup, rollback, log retention |
| [API_REFERENCE.md](API_REFERENCE.md) | API endpoints and JSON payloads |
| [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) | Day-to-day operations and troubleshooting |

---

## Deployment & Operations

- **[PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)** – Phase 10 deployment: staging environment, separate certs per environment, DB backup strategy, rollback plan, log retention, pre-go-live checklist.

---

## Integration & Architecture

- **[QuickBooks_to_FDMS_Django_Integration.md](QuickBooks_to_FDMS_Django_Integration.md)** – QuickBooks → Django → FDMS integration guide.
- **[FDMS_Integration_Management_QuickBooks.md](FDMS_Integration_Management_QuickBooks.md)** – QuickBooks integration management.
- **[QB_to_FDMS_Auto_Fiscalisation.md](QB_to_FDMS_Auto_Fiscalisation.md)** – Auto-fiscalisation flow.

---

## UI & Dashboard

- **[FDMS_Dashboard_Full_Implementation.md](FDMS_Dashboard_Full_Implementation.md)** – Production-grade dashboard spec (React, Tailwind, metrics, exports).
- **[FDMS_Dashboard_Metrics.md](FDMS_Dashboard_Metrics.md)** – Dashboard metrics definitions.
- **[FDMS_UI_Migration_Plan.md](FDMS_UI_Migration_Plan.md)** – UI migration strategy.
- **[PHASE_1_Dashboard_Scaffold.md](PHASE_1_Dashboard_Scaffold.md)** – Operator dashboard scaffold (Django + HTMX).

---

## Invoicing & Fiscal Compliance

- **[FDMS_Credit_Note_Implementation.md](FDMS_Credit_Note_Implementation.md)** – Credit note handling.
- **[FDMS_Invoice_Number_Duplicate_Prevention.md](FDMS_Invoice_Number_Duplicate_Prevention.md)** – Duplicate invoice prevention.
- **[FDMS_Invoice_Preview_Synced_From_QB.md](FDMS_Invoice_Preview_Synced_From_QB.md)** – Invoice preview from QuickBooks.
- **[FDMS_Invoice_QR_Code_Integration.md](FDMS_Invoice_QR_Code_Integration.md)** – QR code on invoices.
- **[FDMS_Final_Invoice_Layout_Spec.md](FDMS_Final_Invoice_Layout_Spec.md)** – Final invoice layout.
- **[Fiscal_Invoice_Layout_Spec.md](Fiscal_Invoice_Layout_Spec.md)** – Fiscal invoice layout spec.

---

## Import & Data

- **[FDMS_Excel_Import_Credit_Note_UX.md](FDMS_Excel_Import_Credit_Note_UX.md)** – Excel import for credit notes.
- **[FDMS_Reusable_Excel_Import_Engine.md](FDMS_Reusable_Excel_Import_Engine.md)** – Reusable Excel import engine.
- **[FDMS_Excel_Import_Rules_Invoice01.md](FDMS_Excel_Import_Rules_Invoice01.md)** – Invoice import rules.

---

## Configuration & Safeguards

- **[FDMS_Enforce_GetConfigs_Source_of_Truth.md](FDMS_Enforce_GetConfigs_Source_of_Truth.md)** – GetConfig as source of truth.
- **[FDMS_QB_Edit_Safeguards_Post_Fiscalisation.md](FDMS_QB_Edit_Safeguards_Post_Fiscalisation.md)** – Post-fiscalisation edit safeguards.
- **[FDMS_Tax_Mapping_UI.md](FDMS_Tax_Mapping_UI.md)** – Tax mapping UI.

---

## Offline & Batch

- **[PHASE_5_Offline_Mode_and_Batch_Submission.md](PHASE_5_Offline_Mode_and_Batch_Submission.md)** – Offline mode and batch submission.

---

## Templates & Assets

- [FDMS_Fiscal_Invoice_Template.html](FDMS_Fiscal_Invoice_Template.html)
- [Fiscal_Invoice_Template.html](Fiscal_Invoice_Template.html)
- [fiscal_invoice_preview_download_screen.jsx](fiscal_invoice_preview_download_screen.jsx)
- [quick_books_integration_management_ui (2).jsx](quick_books_integration_management_ui%20(2).jsx)
- [quick_books_integration_management_ui (3).jsx](quick_books_integration_management_ui%20(3).jsx)
