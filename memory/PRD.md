# Bahi Khata — NBFC-MFI Platform PRD

## Original Problem Statement
Build a software solution for an NBFC-MFI app named "Bahi Khata" transitioning to a "Sahukar Illaka" model.

## User Personas & Roles Hierarchy
- **Admin** — Super admin; full system access
- **Maalik** (Owner) — Owns Illakas (geographic areas); manages Muneems and Sipahis
- **Muneem** (Senior field agent) — Assigned to Illakas; supervises collections
- **Sipahi** (Junior field agent) — Assigned to Illakas; does KYC and daily collections

## Core Requirements

### Geography
- Maaliks own Illakas (areas). Muneems & Sipahis are assigned to Illakas.
- Each Illaka has multiple Misals (villages).

### KYC Flow (Multi-step Form)
1. Select Illaka → Misal
2. Primary Borrower details (Aadhaar OCR front + back, Hindi transliteration)
3. Co-borrower (optional)
4. Guarantor (optional)
5. Live Photo (back camera, auto-GPS capture)
6. Review + Disbursement Amount → Submit

- Aadhaar front OCR: Name, DOB, Gender, Aadhaar number
- Aadhaar back OCR: Relative name (Husband/Father), Address, Aadhaar number
- Hindi transliteration via Gemini (English → Devanagari for all names)
- Unique Aadhaar + unique mobile validation
- GPS restricted to Admin/Maalik views

### Loan Module
- Fixed 1-year tenure, 12 EMIs, flat 17% per annum
- Auto-creates loan on KYC submission (with disbursement_amount)
- Customer ID: `{IllakaPrefix}{4-digit-seq}` e.g. `DE0001`
- Loan ID: `{customer_id}-L{n}` e.g. `DE0001-L1`

### Tracking & Collections
- Collection Sheet (Vasuli): Grouped by Illaka → Misal → Rows
- Per-client Loan Passbook on ClientDetail page (Passbook tab)
- EMI Notes on unpaid EMIs (in LoanDetail, ClientDetail Passbook, CollectionSheet)
- Field agents can record payments, add notes to unpaid EMIs

## Code Architecture

```
/app/
├── backend/
│   ├── server.py          # Thin app setup, CORS, startup/shutdown, include routers
│   ├── core/
│   │   ├── database.py    # MongoDB connection (client, db)
│   │   ├── storage.py     # Object storage helpers + EMERGENT_KEY + APP_NAME
│   │   └── auth.py        # JWT, hash_password, get_current_user, _user_from_doc
│   ├── models.py          # All Pydantic models (incl. ReLoanRequest)
│   ├── helpers.py         # _doc, generate_customer_id, generate_loan_number, EMI helpers (_get_loan_status handles 'netoff')
│   ├── routes/
│   │   ├── auth.py        # /api/auth/login, logout, me
│   │   ├── users.py       # /api/users CRUD
│   │   ├── illakas.py     # /api/illakas, /api/misals CRUD
│   │   ├── kycs.py        # /api/kycs CRUD + customer ID + auto-loan
│   │   ├── loans.py       # /api/loans CRUD + payments + PATCH emi-note + POST reloan + auto journal entries
│   │   ├── ocr.py         # /api/upload, /api/files, /api/ocr/aadhaar*, /api/transliterate
│   │   ├── collections.py # /api/collections/sheet
│   │   ├── dashboard.py   # /api/dashboard/stats
│   │   └── accounts.py    # /api/accounts/* (groups, heads, entries, cashbook, summary)
│   └── tests/
│       ├── test_bahikhata.py
│       ├── test_loans_emi.py
│       ├── test_new_features.py
│       ├── test_loan_passbook.py
│       ├── test_refactoring.py
│       └── test_reloan.py  # Re-Loan with Net-Off tests
├── frontend/
│   └── src/
│       ├── App.js
│       └── components/
│           ├── Layout.jsx
│           ├── Login.jsx
│           ├── Dashboard.jsx
│           ├── KYCForm.jsx          # Slim orchestrator (imports from kyc/)
│           ├── kyc/
│           │   ├── utils.js
│           │   ├── DocUpload.jsx
│           │   ├── PersonSection.jsx
│           │   ├── LivePhotoGPS.jsx
│           │   └── ReviewSection.jsx
│           ├── ReLoanModal.jsx      # Re-Loan with Net-Off modal
│           ├── ClientList.jsx
│           ├── ClientDetail.jsx     # KYC tab + Passbook tab (Re-Loan button)
│           ├── LoanList.jsx
│           ├── LoanDetail.jsx       # EMI grid + Re-Loan button + netoff display
│           ├── CollectionSheet.jsx  # Vasuli view grouped by Illaka → Misal
│           ├── AccountsModule.jsx   # Slim orchestrator — imports from accounts/
│           ├── accounts/
│           │   ├── utils.js           # fmt, MONTHS, API constant
│           │   ├── MonthNav.jsx
│           │   ├── SimpleEntryModal.jsx
│           │   ├── ManageHeadsModal.jsx
│           │   ├── CashBook.jsx
│           │   ├── Bid.jsx
│           │   ├── PLSummary.jsx
│           │   ├── OpeningBalanceModal.jsx
│           │   ├── TrialBalance.jsx
│           │   └── BalanceSheet.jsx
│           ├── IllakaContext.jsx    # Global Illaka state (selectedIllaka, eligibleIllakas)
│           └── IllakaSelector.jsx  # Illaka picker post-login
```

## DB Schema
- **users**: {email, password_hash, role, name, phone, assigned_illaka_ids, maalik_id, is_active}
- **illakas**: {name, maalik_id, description}
- **misals**: {name, illaka_id, description}
- **kycs**: {customer_id, kyc_number, illaka_id, misal_id, primary_borrower {name, name_hindi, relative_name, relative_name_hindi, aadhaar_number, dob, gender, phone, address, aadhaar_front_path, aadhaar_back_path}, co_borrower, guarantor, live_photo_path, gps_location, field_officer_id, status, loan_id, disbursement_amount}
- **loans**: {loan_number, customer_id, kyc_id, principal_amount, interest_rate, emi_amount, total_repayable, loan_date, status, emi_schedule [{month, due_month, amount, status, paid_amount, paid_date, note}], total_paid, illaka_id, misal_id, is_reloan, parent_loan_id, netoff_amount, **is_gyal**, **gyal_since**}
- **journal_entries**: {date, illaka_id, narration, entry_type (manual/expense_voucher/loan_disbursement/emi_collection/**gyal_writeoff**), reference_id, lines [{account_head_id, account_head_name, group_name, group_type, debit, credit}], total_amount, created_by_id, created_by_name}
- **account_groups**: {name, type (equity/liability/asset/income/expense), nature (debit/credit), display_order}
- **account_heads**: {name, group_id, group_name, group_type, is_system, system_key, is_active, created_by}

## 3rd Party Integrations
- **Emergent Object Storage** — profile photos, Aadhaar scans
- **Google Gemini (via Emergent LLM Key)** — Aadhaar OCR + Hindi transliteration (gemini-2.5-flash)

## Key API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/auth/login | Login |
| GET | /api/auth/me | Current user |
| GET | /api/illakas | List illakas |
| GET | /api/misals?illaka_id= | List misals |
| POST | /api/kycs | Create KYC + auto-loan |
| GET | /api/kycs | List KYCs with filters |
| GET | /api/loans | List loans |
| GET | /api/loans/{id} | Get loan with EMI schedule |
| POST | /api/loans/{id}/payments | Record EMI payment |
| DELETE | /api/loans/{id}/payments/{emi_month} | Undo payment |
| PATCH | /api/loans/{id}/payments/{emi_month} | Edit EMI payment (Admin/Maalik: any; Muneem/Sipahi: current month only) |
| POST | /api/loans/{id}/reloan | Create re-loan (with optional net-off) |
| GET | /api/collections/sheet | Vasuli collection sheet (includes emi_year_data for FY strip) |
| GET | /api/dashboard/stats | Dashboard statistics |
| POST | /api/upload | Upload file to object storage |
| GET | /api/files/{path} | Serve stored file |
| POST | /api/ocr/aadhaar | OCR Aadhaar front |
| POST | /api/ocr/aadhaar-back | OCR Aadhaar back |
| POST | /api/transliterate | Transliterate to Hindi |
| GET | /api/accounts/bid | Monthly Bid (P&L aggregate) |
| GET | /api/accounts/trial-balance | Trial Balance |
| GET | /api/accounts/balance-sheet | Balance Sheet |
| GET,POST,DELETE | /api/accounts/opening-balance | Opening Balances |
| GET | /api/accounts/closing-balances | Closing balances for copy-forward |

## What's Been Implemented
See CHANGELOG.md for full history.

## Prioritized Backlog (P0/P1/P2)

### P0 (Critical) — All Done ✓
- [x] Role-based auth (Admin/Maalik/Muneem/Sipahi)
- [x] KYC multi-step form with Aadhaar OCR
- [x] English → Hindi transliteration (Gemini)
- [x] Auto loan creation on KYC submit (17% flat, 12 EMIs)
- [x] Customer ID (`DE0001`) and Loan ID (`DE0001-L1`)
- [x] Collection Sheet (Vasuli) grouped by Illaka → Misal
- [x] Loan Passbook tab on ClientDetail
- [x] EMI Notes feature across all views

### P0 (Critical Accounting Fix — Done 2026-02) ✓
- [x] Bid & Disbursement Accounting Fix (interest = principal × 17/103, upfront recognition)
- [x] Interest formula corrected throughout: `_build_emi_schedule`, `ReviewSection.jsx`, `LoanForm.jsx`

### P0 (Balance Sheet & Trial Balance — Done 2026-02) ✓
- [x] Trial Balance: cumulative, grouped by type, balanced indicator
- [x] Balance Sheet: Assets vs Capital & Liabilities, balancing plug for opening capital
- [x] Opening Balance: modal to enter asset/liability/equity starting balances; auto-calculates Opening Capital plug; supports update/delete

### P1 (High) — All Done ✓
- [x] Code Refactoring (backend server.py → core/ + routes/, frontend KYCForm.jsx → kyc/)
- [x] **AccountsModule Refactoring (2026-03-31)**: Split 1399-line AccountsModule.jsx into 10 focused files under `accounts/` subfolder.
- [x] Unique Aadhaar + mobile validation
- [x] Live photo with back camera + auto-GPS
- [x] Re-Loan with Net-Off (all roles, active + closed loans, optional phone/co-borrower/guarantor edit)
- [x] Login with Mobile Number instead of Email
- [x] Illaka Selection after login (global context, persists in sessionStorage, switcher in top-right)
- [x] Accounts Module (Cash Book, P&L Summary, Account Heads management, auto journal entries on loan disbursement & EMI collection)
- [x] Enhanced Accounts Module: Full Journal Entry, Expense Sheet per Illaka, Two-column Cashbook, "Bid" monthly aggregate tab
- [x] Admin/Maalik Edit & Delete journal entries
- [x] **Gyal (Bad Debt) Feature** — Manual Year-End Closing per Illaka, marks 36+ month loans as Gyal, Gyal Wasool income
- [x] **Interest Income Accounting Fix (2026-03-30)**
- [x] **12-Month FY Strip on Collection Sheet Desktop (2026-03-31)**: April→March strip, boxy grid, current month highlighted
- [x] **EMI Edit on Vasuli (2026-03-31)**: Muneem/Sipahi edit current month only; Admin/Maalik edit before year closing
- [x] **Copy Opening Balance from Closing (2026-03-31)**: Pre-fill opening balances from last year's closing

### Collection Sheet — Two New Columns (2026-03-31) ✓
- [x] Added **पिछली बाक़ी** column (previous outstanding/netoff_amount) with loan month/year — desktop only
- [x] Added **किस्त हाल** column (total_repayable = principal + interest) with loan month/year — desktop only
- [x] Removed date from **शेष/Bal** column (date moved to new columns)
- [x] Table widened to `max-w-full` to use all available horizontal space
- [x] Mobile shows loan date below the name instead
- [x] FY strip shows full numbers (1,500) instead of compact format (1.5K)
- [x] Gyal rows text shown in black (foreground) — background remains grey
- [x] Real-time state update after Collect/Edit — FY strip updates immediately without page refresh

### Illaka/Misal Name Propagation (2026-03-31) ✓
- [x] Renaming an Illaka or Misal propagates to all denormalized fields across `loans`, `kycs`, `expense_templates` collections via `update_many`
- [x] `collections.py` now does a live bulk lookup of illaka/misal names from source collections as the primary source of truth, with stored name as fallback

### Collection Sheet — Closed Loans Persistence (2026-03-31) ✓
- [x] Closed loans now stay on the Collection Sheet until their 12-month EMI schedule ends naturally (end of FY/last scheduled month), not when marked closed
- [x] Overdue loans whose 12-month tenure has ended now remain on the sheet for the entire FY, showing the last scheduled EMI as the representative entry (so the agent can still collect/action it)
- [x] Logic: if a loan has ANY EMI in the current FY months, it is always shown; if no EMI matches the view month, the last scheduled EMI is used as display entry
- [x] Added `netoff` EMI status styling (blue, ↩ icon) in the FY strip and action column

### P2 (Backlog)
- [ ] **Days Overdue badge** on Collection Sheet EMI rows (P1)
- [ ] "Today's Collection Summary" WhatsApp/PDF export from Vasuli
- [ ] "Print Passbook" PDF/WhatsApp share from ClientDetail
- [ ] Forgot Password OTP Flow (Twilio/Paid Gateway)
- [ ] Misal-level Filtering dropdown on Vasuli
- [ ] Gyal Summary Dashboard Card (NPA overview)
