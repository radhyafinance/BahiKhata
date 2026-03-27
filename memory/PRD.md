# Bahi Khata - NBFC-MFI Platform PRD

## Problem Statement
Build a complete software solution to run an NBFC-MFI, starting with KYC collection. 
App Name: Bahi Khata
Language: English + Hindi (bilingual)

## Architecture
- **Frontend**: React + Tailwind CSS + shadcn UI (port 3000)
- **Backend**: FastAPI + MongoDB (port 8001)
- **Storage**: Emergent Object Storage (cloud)
- **OCR**: Google Gemini 2.5 Flash (via Emergent LLM key)
- **Auth**: JWT httpOnly cookies

## User Personas & Roles
1. **Admin** - Full access, user management, KYC status updates
2. **Branch Manager** - View all branch KYCs, approve/reject
3. **Field Officer** - Create & manage own KYCs

## Core Requirements (Static)
- KYC with Aadhaar (front/back), secondary document (Voter ID/PAN/Ration Card)
- OCR extraction from Aadhaar: Name, DOB, Address, Aadhaar Number, Gender
- Phone number capture per borrower
- Co-borrower full KYC (same documents)
- Guarantor full KYC (same documents)
- Live photo capture via webcam + GPS location
- Cloud document storage
- Role-based access control

## What's Been Implemented (MVP - March 2025)

### Backend (server.py)
- JWT authentication with httpOnly cookies
- Admin auto-seeding on startup
- Object storage integration (Emergent)
- Gemini 2.5 Flash OCR for Aadhaar
- CRUD: Users, KYCs
- File upload & serve endpoints
- Dashboard stats endpoint
- MongoDB indexes

### Frontend
- Login page (split-screen, branded, bilingual)
- Responsive sidebar layout (desktop + mobile)
- Dashboard with stats cards + recent KYCs
- 5-step KYC form:
  1. Primary Borrower (Aadhaar + OCR + additional doc)
  2. Co-borrower KYC
  3. Guarantor KYC
  4. Live Photo (webcam) + GPS location
  5. Review + Submit
- Client List with search & status filter
- Client Detail with full document view + Approve/Reject
- User Management (Admin: create/edit/deactivate users)

## Test Credentials
- Admin: admin@bahikhata.com / Admin@123

## Prioritized Backlog

### P0 (Next Sprint)
- [ ] Loan origination module (loan application, sanction)
- [ ] EMI repayment tracking & collection
- [ ] KYC document verification status

### P1
- [ ] Individual loan ledger / passbook view
- [ ] Repayment schedule generation
- [ ] Field officer mobile app optimization
- [ ] SMS notifications (Twilio)
- [ ] Disbursement tracking

### P2
- [ ] Reports & analytics (repayment rate, delinquency)
- [ ] Branch-wise performance dashboard
- [ ] Document expiry alerts (Aadhaar/PAN)
- [ ] Multi-branch management
- [ ] Audit trail / activity logs
- [ ] Bulk KYC import from CSV
