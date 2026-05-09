# Bahi Khata — Changelog

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
