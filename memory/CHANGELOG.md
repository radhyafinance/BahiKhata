# Bahi Khata — Changelog

## 2026-05-09

### CrifCheck.jsx Refactoring
- Extracted `LoanAccountCard` component → `/app/frontend/src/components/crif/LoanAccountCard.jsx` (103 lines)
- Extracted `PaymentHistoryGrid` component → `/app/frontend/src/components/crif/PaymentHistoryGrid.jsx` (47 lines)
- Extracted `parsePaymentHistory`, `dpdCellStyle`, `MONTHS` helpers → `/app/frontend/src/components/crif/parsePaymentHistory.js` (42 lines)
- `CrifCheck.jsx` reduced from 824 lines → 635 lines; now imports from `crif/` subfolder
- Zero lint errors; app smoke-tested and confirmed healthy

### CRIF 30-day Cooldown (previous fork)
- Backend: `POST /api/crif/check/{kyc_id}` returns HTTP 429 with `cooldown_days_remaining` if within 30 days
- Frontend: Re-check button shows "Locked · Nd" and blue informational banner while cooldown is active
