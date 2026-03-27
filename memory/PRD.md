# Bahi Khata - NBFC-MFI Platform PRD

## Problem Statement
Build a complete software solution to run an NBFC-MFI / Sahukar (informal lending) operation.
App Name: Bahi Khata
Language: English + Hindi (bilingual)
Business Model: Sahukar Illaka model

## Architecture
- **Frontend**: React + Tailwind CSS + shadcn UI (port 3000)
- **Backend**: FastAPI + MongoDB (port 8001)
- **Storage**: Emergent Object Storage (cloud)
- **OCR**: Google Gemini 2.5 Flash (via Emergent LLM key)
- **Auth**: JWT httpOnly cookies

## User Personas & Roles
1. **Admin** - Full access, user management, KYC + loan status updates
2. **Maalik (Owner)** - Owns Illakas, manages Muneem/Sipahi under them
3. **Muneem (Senior Agent)** - Assigned to Illakas, creates KYCs and loans, can approve/reject
4. **Sipahi (Field Agent)** - Assigned to Illakas, creates KYCs and loans for clients in their Illakas

## Geography
- Maalik owns Illakas (areas/territories)
- Muneems are assigned to Illakas
- Sipahis are assigned to Illakas and see all clients/loans in those Illakas

## Core Requirements (Static)
### KYC
- KYC with Aadhaar (front/back), secondary document (Voter ID/PAN/Ration Card)
- OCR extraction from Aadhaar: Name, DOB, Address, Aadhaar Number, Gender
- Phone number capture per borrower
- Co-borrower full KYC (optional)
- Guarantor full KYC (optional)
- Live photo capture via webcam + GPS location (both mandatory)
- Cloud document storage with image compression
- Role-based access control (RBAC)
- Select Illaka -> Misal before KYC

### Loan Tracking
- Create loan for KYC-verified client
- Track: principal amount, interest rate (% per month), loan date, due date, status
- Loan statuses: active, overdue, closed
- Payment recording with date and amount
- Outstanding balance auto-calculated (principal - total_paid)
- Monthly interest display
- Payment history per loan

## What's Been Implemented

### Backend (server.py)
- JWT authentication with httpOnly cookies
- Admin auto-seeding on startup
- Object storage integration (Emergent)
- Gemini 2.5 Flash OCR for Aadhaar
- CRUD: Users (maalik/muneem/sipahi), Illakas, Misals, KYCs, Loans, Payments
- File upload & serve endpoints
- Dashboard stats endpoint (KYC + loan counts)
- MongoDB indexes
- Role-based query filtering for all collections

### Frontend
- Login page (split-screen, branded, bilingual)
- Responsive sidebar layout (desktop + mobile)
- Dashboard with stats (KYC + loan counts), recent KYCs
- 6-step KYC form:
  1. Illaka & Misal selection
  2. Primary Borrower (Aadhaar + OCR + additional doc)
  3. Co-borrower KYC (optional toggle)
  4. Guarantor KYC (optional toggle)
  5. Live Photo (webcam/gallery) + GPS location (mandatory)
  6. Review + Submit
- Client List with search & status filter
- Client Detail with full document view + Approve/Reject/Pending
- Illaka Management (Admin/Maalik): CRUD Illakas + nested Misals
- User Management (Admin/Maalik): Create/Edit/Deactivate Muneem/Sipahi with Illaka assignment
- Loan List with search and status filter
- Loan Form: Client search (KYC lookup), principal/interest/dates
- Loan Detail: Summary cards, payment history, status management, Add Payment modal

## Test Credentials
- Admin: admin@bahikhata.com / Admin@123
- Test Sipahi: TEST_sipahi_loans@bahikhata.com / Test@1234

## DB Collections
- users: {email, password_hash, role, name, assigned_illaka_ids, maalik_id, is_active}
- illakas: {name, description, maalik_id}
- misals: {name, illaka_id, description}
- kycs: {kyc_number, status, illaka_id, illaka_name, misal_id, misal_name, primary_borrower, co_borrower, guarantor, live_photo_path, gps_location, field_officer_id, field_officer_name}
- loans: {kyc_id, client_name, client_phone, illaka_id, illaka_name, misal_id, misal_name, principal_amount, interest_rate, loan_date, due_date, status, sipahi_id, sipahi_name, total_paid, notes}
- payments: {loan_id, amount, payment_date, collected_by_id, collected_by_name, notes}

## Prioritized Backlog

### P0 (Next Sprint)
- [ ] EMI repayment tracking & collection schedules (weekly/monthly)
- [ ] Loan origination with formal sanction workflow

### P1
- [ ] Individual loan ledger / passbook view per client
- [ ] Repayment schedule generation (installment calendar)
- [ ] Overdue auto-flagging (cron job / scheduled task)
- [ ] SMS notifications (Twilio) for payment reminders
- [ ] Disbursement tracking

### P2
- [ ] Reports & analytics (repayment rate, collection efficiency, delinquency)
- [ ] Branch/Illaka-wise performance dashboard
- [ ] Document expiry alerts (Aadhaar/PAN)
- [ ] Bulk KYC import from CSV
- [ ] Audit trail / activity logs
- [ ] server.py refactor: split into routes/ (auth.py, kycs.py, loans.py, users.py, illakas.py)
