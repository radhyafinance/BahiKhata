# Bahi Khata — Changelog

## 2026-06-23

### Bug Fix: Deleted EMI collection no longer persists in Cashbook
- **Root cause**: `DELETE /api/loans/{id}/payments/{emi_month}` (`uncollect_emi`) was deleting the payment record and resetting the EMI schedule, but **never deleting the corresponding `journal_entry`** of type `emi_collection`
- **Fix**: Added journal entry deletion to `uncollect_emi` in `loans.py` — mirrors the logic already present in `edit_emi_payment`
- Lookup by `emi_month` field first; falls back to `date` match for legacy entries created before `emi_month` field was added
- Covers both regular EMI and synthetic Gyal collection entries
- Verified: collect → JE created → delete → JE removed (0 remaining)



### Quick Add Loan Feature (Admin/Maalik only)
- New backend endpoint `POST /api/kycs/quick-loan` — creates a minimal KYC + Loan record without Aadhaar/photo/GPS
- Role-restricted to **Admin and Maalik** only (403 for sipahi/muneem)
- Fields: Illaka+Misal dropdowns, Borrower Name (required), Phone (optional), Suffix (optional), Co-borrower (optional, collapsible), Guarantor (optional, collapsible), Principal Amount, Loan Month (YYYY-MM)
- Loan date auto-set to **1st of the selected month**
- EMI calculated using standard formula: `round(principal × 120/103 ÷ 12 ÷ 10) × 10`
- Journal entry auto-booked via `book_loan_disbursement` (Debit: Loans Portfolio, Credit: Cash + Interest Income)
- New `QuickLoanCreate` Pydantic model in `models.py`; KYC doc gets `source: "quick_add"` flag
- Frontend: `QuickAddLoanModal.jsx` — live EMI/interest preview, success screen with Customer ID + Loan Number
- "Quick Add Loan" button added to `LoanList.jsx` for admin/maalik
- All 12 backend tests + 4 frontend success-screen tests passed (iterations 29 & 30)



### Import Page — Preserve Excel Order on Vasuli
- `excel_confirm` endpoint computes misal `display_order` (first appearance per illaka+misal pair) and row `display_order` (Excel row index 0-based); both stored on DB documents
- `_resolve_illaka_misal`: new `misal_display_order` param sets `display_order` on auto-created misals
- `_create_ob_kyc_and_loan`: new `display_order` param stored on loan documents
- `collections.py`: bulk misal lookup now fetches `display_order`; misals sorted by `display_order` (None → last by name); row sort updated to prefer `display_order` over `loan_date`

### Import Page — Blank EMI = Gyal
- `emi_amount` is now optional in both the Opening Balance Form and Excel Import
- If EMI Amount is blank → loan is imported with `is_gyal: True`, empty EMI schedule (no kisht)
- Backend `import_data.py`: `ExcelRow` and `OpeningBalanceEntry` models updated to `Optional[float]`; `_create_ob_kyc_and_loan` sets `is_gyal=True`, `gyal_since=today` when EMI is None/0
- Excel template: Column 9 header changed to "EMI Amount (blank = Gyal)" and moved from required (yellow) to optional (light blue)
- Frontend `ImportPage.jsx`: EMI Amount field no longer `required`; shows Gyal preview banner when blank; preview table shows "Gyal" badge + "—" for EMI count on Gyal rows

## 2026-06-02

### KYC Image Viewer Modal (ClientDetail)
- Created `/app/frontend/src/components/ImageViewer.jsx` — fullscreen modal with:
  - Zoom in/out (mouse wheel, pinch-to-zoom, +/- buttons), rotate left/right, reset
  - Navigation arrows and thumbnail strip (for multi-image sessions)
  - Keyboard shortcuts: ESC closes, arrows navigate, +/- zoom, R rotates
  - All controls have `data-testid` attributes
- Wired into `ClientDetail.jsx`:
  - `buildPersonImages()` helper and `allKycImages` useMemo to collect images per person
  - `openPersonViewer(personData, label, clickedPath)` opens viewer at the clicked image
  - "View All Photos (N)" button aggregates all KYC docs + live photo
  - Each PersonCard (Primary, Co-borrower, Guarantor) passes `onOpenViewer` prop
  - Live Photo circular image is now clickable (opens viewer)
  - `SecureImage` component updated with `testId` prop for KYC images
- 100% frontend test pass rate (11/11 tests via testing agent)

## 2026-05-09

### PWA (Progressive Web App) Support
- Added `public/manifest.json` — app name, standalone display, portrait orientation, theme `#166534` (deep green), 5 icon sizes
- Generated app icons (72/96/144/192/512px + 180px Apple touch) using Pillow — stored in `public/icons/`
- Updated `public/index.html` — manifest link, Apple PWA meta tags (`apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`, `apple-touch-icon`), Microsoft tile meta, theme-color, title updated to "Bahi Khata"
- Created `src/service-worker.js` — Workbox-based offline shell caching (precache app assets, SPA navigation handler, stale-while-revalidate for icons, network-first for API calls)
- Created `src/serviceWorkerRegistration.js` — standard CRA SW registration helper (production only)
- Updated `src/index.js` — `serviceWorkerRegistration.register()` wired in

### CrifCheck.jsx Refactoring
- Extracted `LoanAccountCard` component → `/app/frontend/src/components/crif/LoanAccountCard.jsx` (103 lines)
- Extracted `PaymentHistoryGrid` component → `/app/frontend/src/components/crif/PaymentHistoryGrid.jsx` (47 lines)
- Extracted `parsePaymentHistory`, `dpdCellStyle`, `MONTHS` helpers → `/app/frontend/src/components/crif/parsePaymentHistory.js` (42 lines)
- `CrifCheck.jsx` reduced from 824 lines → 635 lines; now imports from `crif/` subfolder
- Zero lint errors; app smoke-tested and confirmed healthy

### CRIF 30-day Cooldown (previous fork)
- Backend: `POST /api/crif/check/{kyc_id}` returns HTTP 429 with `cooldown_days_remaining` if within 30 days
- Frontend: Re-check button shows "Locked · Nd" and blue informational banner while cooldown is active
