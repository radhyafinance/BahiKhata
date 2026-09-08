# Bahi Khata / बही खाता

Loan management for an NBFC-MFI — KYC, disbursement, field collections, and
double-entry accounting, built around how a microfinance branch actually works.

**Stack:** FastAPI · MongoDB · React 19 (CRA + CRACO) · Tailwind + shadcn/ui

---

## Domain vocabulary

The code and UI use the terms the business uses. Worth knowing before reading either:

| Term | Meaning |
|---|---|
| **Illaka** (इलाक़ा) | Area or branch. The unit of access control — most data is scoped to one. |
| **Misal** (मिसल) | A register or group of borrowers within an illaka. |
| **Vasuli** (वसूली) | Collections. The main working screen — a monthly EMI grid. |
| **Aasami Khata** (आसामी खाता) | The loan portfolio; total outstanding across borrowers. |
| **Jama / Kharch** | Receipts / payments, the two sides of the cash book. |
| **Bid** | Monthly aggregate cash book. |
| **Gyal** (ग्याल) | Written-off debt. Carried separately from the live portfolio. |
| **Maalik / Muneem / Sipahi** | Owner / accountant / field officer — the three staff roles, plus `admin`. |

---

## Running it locally

Requires **Python 3.12** and **Node 18+**. Older Python will fail on the pinned
dependencies.

### 1. MongoDB

Any local MongoDB on the default port works:

```bash
mongod --dbpath /path/to/data --port 27017
```

### 2. Backend

```bash
cd backend
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt \
  --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
cp .env.example .env        # then fill in JWT_SECRET and ADMIN_PASSWORD
./.venv/bin/python -m uvicorn server:app --port 8000 --reload
```

The extra index is only needed for `emergentintegrations`, which is not on PyPI.
It is used by OCR alone and is being removed — see *Migration status* below.

On first start the app creates its indexes, seeds the chart of accounts, and
creates the admin user from `ADMIN_EMAIL` / `ADMIN_PHONE` / `ADMIN_PASSWORD`.

> **Note:** the admin password is reset to `ADMIN_PASSWORD` on *every* boot, not
> just the first. Treat it as a live credential.

### 3. Frontend

```bash
cd frontend
yarn install
cp .env.example .env
yarn start                  # http://localhost:3000
```

`REACT_APP_BACKEND_URL` must not include `/api` — the code appends it.

### 4. Sign in

Use the phone number and password from your `.env`. Passkey login will not work
over plain `http://` except on localhost.

Sample data, if you want a populated database:

```bash
./.venv/bin/python seed_rampur.py    # 50 clients with loans and re-loans
./.venv/bin/python seed_netoff.py    # net-off / re-loan chains
```

---

## Layout

```
backend/
  server.py            app assembly, startup, index creation, seeding
  core/
    database.py        Mongo client and the shared `db` handle
    auth.py            JWT, password hashing, get_current_user
    storage.py         object storage (being replaced — see below)
  routes/              one module per area; 90 endpoints total
  helpers.py           shared query scoping and journal-entry creation
  models.py            Pydantic request/response models
  tests/               29 pytest files

frontend/src/
  components/          screens and UI; CollectionSheet.jsx is the Vasuli grid
```

### Two things to know before changing backend code

**Access is scoped by role, in every query.** `helpers.py` provides
`permitted_illaka_ids()` and `apply_illaka_scope()`. A query that skips them
returns another branch's borrowers. Narrow an existing query — never assign
`query["illaka_id"]` directly, which overwrites the role filter rather than
tightening it.

**Money movements are double-entry.** Collections, disbursements and expenses all
post balanced journal entries via `create_journal_entry_internal()`, which refuses
to write an entry whose debits and credits disagree. The Balance Sheet derives
opening capital as a plug, so it *always* reports `is_balanced: true` — the trial
balance is the honest check.

---

## Tests

```bash
cd backend
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest tests/
```

Coverage is uneven: read paths are reasonably covered, the ~60 write endpoints
are not systematically tested.

---

## Migration status

This codebase is being moved off the Emergent platform. Two files still depend
on it, and both are scheduled for replacement:

| File | Depends on | Replaced by |
|---|---|---|
| `core/storage.py` | Emergent object store | S3-compatible storage |
| `routes/ocr.py` | `emergentintegrations` wrapper | Google Gemini SDK directly |

The model behind OCR is already `gemini-2.5-flash`; only the client library
changes. Nothing else in the application calls an Emergent service.

**CRIF credit bureau checks are IP-whitelisted.** Any new host must have its
source IP registered with CRIF High Mark before bureau checks will work, and
that runs on their timeline. Start it early.
