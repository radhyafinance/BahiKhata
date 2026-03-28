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
│   │   ├── loans.py       # /api/loans CRUD + payments + PATCH emi-note + POST reloan
│   │   ├── ocr.py         # /api/upload, /api/files, /api/ocr/aadhaar*, /api/transliterate
│   │   ├── collections.py # /api/collections/sheet
│   │   └── dashboard.py   # /api/dashboard/stats
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
│           └── CollectionSheet.jsx  # Vasuli view grouped by Illaka → Misal
```

## DB Schema
- **users**: {email, password_hash, role, name, assigned_illaka_ids, maalik_id, is_active}
- **illakas**: {name, maalik_id, description}
- **misals**: {name, illaka_id, description}
- **kycs**: {customer_id, kyc_number, illaka_id, misal_id, primary_borrower {name, name_hindi, relative_name, relative_name_hindi, aadhaar_number, dob, gender, phone, address, aadhaar_front_path, aadhaar_back_path}, co_borrower, guarantor, live_photo_path, gps_location, field_officer_id, status, loan_id, disbursement_amount}
- **loans**: {loan_number, customer_id, kyc_id, principal_amount, interest_rate, emi_amount, total_repayable, loan_date, status, emi_schedule [{month, due_month, amount, status, paid_amount, paid_date, note}], total_paid, illaka_id, misal_id}
- **payments**: {loan_id, emi_month, amount, payment_date, collected_by_id, collected_by_name, notes}

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
| POST | /api/loans/{id}/reloan | Create re-loan (with optional net-off) |
| GET | /api/collections/sheet | Vasuli collection sheet |
| GET | /api/dashboard/stats | Dashboard statistics |
| POST | /api/upload | Upload file to object storage |
| GET | /api/files/{path} | Serve stored file |
| POST | /api/ocr/aadhaar | OCR Aadhaar front |
| POST | /api/ocr/aadhaar-back | OCR Aadhaar back |
| POST | /api/transliterate | Transliterate to Hindi |

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

### P1 (High) — All Done ✓
- [x] Code Refactoring (backend server.py → core/ + routes/, frontend KYCForm.jsx → kyc/)
- [x] Unique Aadhaar + mobile validation
- [x] Live photo with back camera + auto-GPS
- [x] Re-Loan with Net-Off (all roles, active + closed loans, optional phone/co-borrower/guarantor edit)

### P2 (Backlog)
- [ ] Days Overdue badge on Collection Sheet EMI rows
- [ ] "Today's Collection Summary" WhatsApp/PDF export from Vasuli
- [ ] "Print Passbook" PDF/WhatsApp share from ClientDetail
