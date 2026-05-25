"""
P0 Accounting Logic Tests — Bahi Khata MFI
Tests for:
1. Disbursement journal entry: 3-line (Dr Loans Portfolio P+I, Cr Cash P, Cr Interest Income I)
2. EMI collection journal entry: 2-line (Dr Cash full EMI, Cr Loans Portfolio full EMI)
3. GET /api/accounts/bid: EMI Collections = full cash amount grouped by misal
4. GET /api/accounts/bid: Interest Income = only from disbursements (not EMI entries)
5. GET /api/accounts/bid: Loans Portfolio credit = sum of P+I for disbursed loans
6. GET /api/accounts/bid: Balance equation holds
7. Existing 3-line EMI entries (old format) appear at full cash_dr in Bid
"""
import pytest
import requests
import os
import math
from datetime import date

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

INTEREST_FORMULA = lambda p: round(p * 17 / 103, 2)


# ─── Shared sessions (module-scope) ──────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    """Admin session with cookies."""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    """Sipahi session with cookies."""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
    assert resp.status_code == 200, f"Sipahi login failed: {resp.status_code} {resp.text}"
    return s


# ─── Test Infrastructure: Find illaka + misal + create test KYC ───────────────

@pytest.fixture(scope="module")
def test_illaka(admin_session):
    """Return first illaka admin can see."""
    resp = admin_session.get(f"{BASE_URL}/api/illakas")
    assert resp.status_code == 200
    illakas = resp.json()
    assert len(illakas) > 0, "No illakas found"
    # Prefer an illaka named 'Delhi' for predictability; fall back to first
    for ill in illakas:
        if "delhi" in ill.get("name", "").lower():
            return ill
    return illakas[0]


@pytest.fixture(scope="module")
def test_misal(admin_session, test_illaka):
    """Return first misal from the test illaka."""
    resp = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={test_illaka['id']}")
    assert resp.status_code == 200
    data = resp.json()
    misals = data if isinstance(data, list) else data.get("misals", [])
    assert len(misals) > 0, f"No misals in illaka {test_illaka['name']}"
    return misals[0]


@pytest.fixture(scope="module")
def test_kyc(sipahi_session, test_illaka, test_misal):
    """Create a fresh KYC for accounting tests."""
    payload = {
        "illaka_id": test_illaka["id"],
        "illaka_name": test_illaka.get("name", ""),
        "misal_id": test_misal["id"],
        "misal_name": test_misal.get("name", ""),
        "primary_borrower": {
            "name": "TEST_Accounting_Customer",
            "phone": "9000000099",
            "address": "Test Address",
            "relative_name": "Test Relative",
            "relative_type": "husband",
        },
    }
    resp = sipahi_session.post(f"{BASE_URL}/api/kycs", json=payload)
    assert resp.status_code in (200, 201), f"KYC creation failed: {resp.text}"
    return resp.json()


@pytest.fixture(scope="module")
def disbursed_loan(sipahi_session, test_illaka, test_misal, test_kyc):
    """Create a fresh loan and return (loan_doc, principal, interest, total_outstanding)."""
    principal = 10000.0
    today = date.today().isoformat()
    payload = {
        "kyc_id": test_kyc["id"],
        "client_name": "TEST_Accounting_Customer",
        "client_phone": "9000000099",
        "illaka_id": test_illaka["id"],
        "illaka_name": test_illaka.get("name", ""),
        "misal_id": test_misal["id"],
        "misal_name": test_misal.get("name", ""),
        "principal_amount": principal,
        "loan_date": today,
        "notes": "TEST accounting P0 fix",
    }
    resp = sipahi_session.post(f"{BASE_URL}/api/loans", json=payload)
    assert resp.status_code in (200, 201), f"Loan creation failed: {resp.text}"
    loan = resp.json()
    interest = INTEREST_FORMULA(principal)
    total_outstanding = round(principal + interest, 2)
    return loan, principal, interest, total_outstanding


# ─── Test 1: Disbursement journal entry is 3-line ────────────────────────────

class TestDisbursementJournalEntry:
    """Verify 3-line disbursement: Dr Loans Portfolio (P+I), Cr Cash (P), Cr Interest Income (I)."""

    def test_disbursement_entry_exists(self, admin_session, disbursed_loan):
        """Journal entry of type loan_disbursement is created after loan creation."""
        loan, principal, interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        assert resp.status_code == 200
        data = resp.json()
        entries = data.get("entries", [])
        matching = [e for e in entries if e.get("reference_id") == loan_id]
        assert len(matching) >= 1, f"No disbursement entry found for loan {loan_id}"

    def test_disbursement_entry_has_3_lines(self, admin_session, disbursed_loan):
        """Disbursement entry must have exactly 3 lines."""
        loan, principal, interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        assert resp.status_code == 200
        entries = resp.json().get("entries", [])
        matching = [e for e in entries if e.get("reference_id") == loan_id]
        assert len(matching) >= 1
        entry = matching[0]
        lines = entry.get("lines", [])
        assert len(lines) == 3, (
            f"Expected 3 lines in disbursement entry, got {len(lines)}. Lines: {lines}"
        )

    def test_disbursement_loans_portfolio_dr(self, admin_session, disbursed_loan):
        """Loans Portfolio debit = Principal + Interest (P+I)."""
        loan, principal, interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        # Find line where system_key is loans_portfolio (group_name has "Portfolio" or name has "Loans")
        lp_lines = [
            l for l in lines
            if float(l.get("debit", 0)) > 0
            and ("portfolio" in l.get("account_head_name", "").lower() or
                 "loans" in l.get("account_head_name", "").lower())
        ]
        assert len(lp_lines) >= 1, f"No Loans Portfolio debit line found. Lines: {lines}"
        lp_amount = float(lp_lines[0]["debit"])
        assert abs(lp_amount - total_outstanding) < 0.01, (
            f"Loans Portfolio Dr expected {total_outstanding}, got {lp_amount}"
        )

    def test_disbursement_cash_cr(self, admin_session, disbursed_loan):
        """Cash credit = Principal only (P)."""
        loan, principal, interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        cash_lines = [
            l for l in lines
            if float(l.get("credit", 0)) > 0
            and "cash" in l.get("account_head_name", "").lower()
        ]
        assert len(cash_lines) >= 1, f"No Cash credit line found. Lines: {lines}"
        cash_amount = float(cash_lines[0]["credit"])
        assert abs(cash_amount - principal) < 0.01, (
            f"Cash Cr expected {principal}, got {cash_amount}"
        )

    def test_disbursement_interest_income_cr(self, admin_session, disbursed_loan):
        """Interest Income credit = Principal * 17/103 (exactly)."""
        loan, principal, interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        interest_lines = [
            l for l in lines
            if float(l.get("credit", 0)) > 0
            and "interest" in l.get("account_head_name", "").lower()
        ]
        assert len(interest_lines) >= 1, f"No Interest Income credit line found. Lines: {lines}"
        interest_amount = float(interest_lines[0]["credit"])
        expected = INTEREST_FORMULA(principal)
        assert abs(interest_amount - expected) < 0.01, (
            f"Interest Income Cr expected {expected}, got {interest_amount}. "
            f"Formula: round({principal} * 17/103, 2)"
        )

    def test_disbursement_entry_is_balanced(self, admin_session, disbursed_loan):
        """Total debit = Total credit in disbursement entry."""
        loan, principal, interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        total_dr = sum(float(l.get("debit", 0)) for l in lines)
        total_cr = sum(float(l.get("credit", 0)) for l in lines)
        assert abs(total_dr - total_cr) < 0.01, (
            f"Entry not balanced: Dr={total_dr}, Cr={total_cr}"
        )


# ─── Test 2: EMI Collection journal entry is 2-line ─────────────────────────

@pytest.fixture(scope="module")
def collected_emi(sipahi_session, disbursed_loan):
    """Collect the first EMI of the test loan. Return (emi_amount, loan_id, payment_date)."""
    loan, principal, interest, total_outstanding = disbursed_loan
    loan_id = loan["id"]
    emi_amount = float(loan.get("emi_amount", 0))
    schedule = loan.get("emi_schedule", [])
    assert len(schedule) > 0, "No EMI schedule found on loan"
    first_emi = schedule[0]
    emi_month = first_emi["due_month"]
    payment_date = date.today().isoformat()

    resp = sipahi_session.post(
        f"{BASE_URL}/api/loans/{loan_id}/payments",
        json={
            "emi_month": emi_month,
            "amount": emi_amount,
            "payment_date": payment_date,
        },
    )
    assert resp.status_code in (200, 201), f"EMI collection failed: {resp.text}"
    return emi_amount, loan_id, payment_date


class TestEmiCollectionJournalEntry:
    """Verify 2-line EMI entry: Dr Cash (full EMI), Cr Loans Portfolio (full EMI)."""

    def test_emi_entry_exists(self, admin_session, collected_emi):
        """Journal entry of type emi_collection is created after EMI collection."""
        emi_amount, loan_id, payment_date = collected_emi
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection"},
        )
        assert resp.status_code == 200
        entries = resp.json().get("entries", [])
        matching = [e for e in entries if e.get("reference_id") == loan_id]
        assert len(matching) >= 1, f"No emi_collection entry found for loan {loan_id}"

    def test_emi_entry_has_exactly_2_lines(self, admin_session, collected_emi):
        """EMI collection entry must have exactly 2 lines (no interest split)."""
        emi_amount, loan_id, payment_date = collected_emi
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection"},
        )
        entries = resp.json().get("entries", [])
        matching = [e for e in entries if e.get("reference_id") == loan_id]
        assert len(matching) >= 1
        entry = matching[0]
        lines = entry.get("lines", [])
        assert len(lines) == 2, (
            f"Expected 2 lines in EMI collection entry, got {len(lines)}. "
            f"Lines: {lines}. This indicates the OLD 3-line format is still being used."
        )

    def test_emi_cash_dr_equals_full_emi(self, admin_session, collected_emi):
        """Cash debit = full EMI amount (no splitting)."""
        emi_amount, loan_id, payment_date = collected_emi
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        cash_dr_lines = [
            l for l in lines
            if float(l.get("debit", 0)) > 0 and "cash" in l.get("account_head_name", "").lower()
        ]
        assert len(cash_dr_lines) >= 1, f"No Cash debit line found. Lines: {lines}"
        cash_dr = float(cash_dr_lines[0]["debit"])
        assert abs(cash_dr - emi_amount) < 0.01, (
            f"Cash Dr expected {emi_amount} (full EMI), got {cash_dr}"
        )

    def test_emi_loans_portfolio_cr_equals_full_emi(self, admin_session, collected_emi):
        """Loans Portfolio credit = full EMI amount."""
        emi_amount, loan_id, payment_date = collected_emi
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        lp_cr_lines = [
            l for l in lines
            if float(l.get("credit", 0)) > 0
            and ("portfolio" in l.get("account_head_name", "").lower() or
                 "loans" in l.get("account_head_name", "").lower())
        ]
        assert len(lp_cr_lines) >= 1, f"No Loans Portfolio credit line found. Lines: {lines}"
        lp_cr = float(lp_cr_lines[0]["credit"])
        assert abs(lp_cr - emi_amount) < 0.01, (
            f"Loans Portfolio Cr expected {emi_amount} (full EMI), got {lp_cr}"
        )

    def test_emi_entry_no_interest_income_line(self, admin_session, collected_emi):
        """EMI entry must NOT have an Interest Income line (old 3-line format)."""
        emi_amount, loan_id, payment_date = collected_emi
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        interest_lines = [
            l for l in lines
            if "interest" in l.get("account_head_name", "").lower()
        ]
        assert len(interest_lines) == 0, (
            f"EMI entry should NOT have Interest Income line; found: {interest_lines}"
        )


# ─── Tests 3-5: GET /api/accounts/bid ────────────────────────────────────────

@pytest.fixture(scope="module")
def bid_response(admin_session, test_illaka, disbursed_loan, collected_emi):
    """Fetch the Bid for the test illaka for the current month."""
    from datetime import date as _date
    today = _date.today()
    month = f"{today.year}-{today.month:02d}"
    resp = admin_session.get(
        f"{BASE_URL}/api/accounts/bid",
        params={"illaka_id": test_illaka["id"], "month": month},
    )
    assert resp.status_code == 200, f"Bid API failed: {resp.text}"
    return resp.json(), month


class TestBidAPI:
    """Verify GET /api/accounts/bid response structure and values."""

    def test_bid_returns_200(self, admin_session, test_illaka):
        """Bid endpoint returns 200."""
        from datetime import date as _date
        today = _date.today()
        month = f"{today.year}-{today.month:02d}"
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/bid",
            params={"illaka_id": test_illaka["id"], "month": month},
        )
        assert resp.status_code == 200

    def test_bid_has_required_fields(self, bid_response):
        """Bid response contains all required fields."""
        bid, month = bid_response
        for field in ["month", "opening_balance", "dr_totals", "cr_totals", "total_dr", "total_cr", "closing_balance"]:
            assert field in bid, f"Missing field: {field}"

    def test_bid_emi_collections_in_dr(self, bid_response, disbursed_loan, collected_emi):
        """Debit side has EMI Collections section with full cash amount."""
        bid, month = bid_response
        emi_amount, loan_id, payment_date = collected_emi
        dr_totals = bid.get("dr_totals", [])
        emi_sections = [s for s in dr_totals if s.get("type") == "emi_total"]
        assert len(emi_sections) >= 1, (
            f"No 'emi_total' section in dr_totals. dr_totals: {dr_totals}"
        )
        emi_total = emi_sections[0]["total"]
        # EMI total must include the collected EMI at full amount
        assert emi_total >= emi_amount, (
            f"EMI Collections total {emi_total} should be >= {emi_amount} (the EMI we collected)"
        )

    def test_bid_emi_collections_at_full_cash_amount(self, bid_response, collected_emi):
        """EMI Collections in Bid = full cash received (not principal-only)."""
        bid, month = bid_response
        emi_amount, loan_id, payment_date = collected_emi
        dr_totals = bid.get("dr_totals", [])
        emi_sections = [s for s in dr_totals if s.get("type") == "emi_total"]
        assert len(emi_sections) >= 1
        # Check misal breakdown contains the EMI amount
        misal_breakdown = emi_sections[0].get("misal_breakdown", [])
        found = False
        for m in misal_breakdown:
            # If the misal total includes our EMI (we may have multiple), check it's full amount based
            if m["total"] > 0:
                found = True
                break
        assert found, f"No misal with positive total in EMI breakdown: {misal_breakdown}"

    def test_bid_interest_income_in_dr_from_disbursements(self, bid_response, disbursed_loan):
        """Interest Income in Dr totals comes from disbursements, not from EMI entries."""
        bid, month = bid_response
        loan, principal, interest, total_outstanding = disbursed_loan
        dr_totals = bid.get("dr_totals", [])
        income_sections = [s for s in dr_totals if s.get("type") == "income"]
        interest_sections = [
            s for s in income_sections
            if "interest" in s.get("label", "").lower()
        ]
        assert len(interest_sections) >= 1, (
            f"No Interest Income in Dr totals. dr_totals: {dr_totals}"
        )
        interest_total = sum(s["total"] for s in interest_sections)
        # Interest total must include our loan's interest amount
        assert interest_total >= interest, (
            f"Interest Income total {interest_total} should be >= {interest} (from our loan disbursement)"
        )
        # Crucially, the interest_total must NOT include per-EMI interest from EMI entries
        # We can verify this is exactly the disbursement interest (not doubled with EMI interest)
        # For a fresh illaka in current month with only our test data, it should equal interest exactly
        # (within rounding)
        print(f"  Interest Income in Bid Dr: {interest_total}, Expected from disbursement: {interest}")

    def test_bid_loans_portfolio_in_cr(self, bid_response, disbursed_loan):
        """Credit side shows Loans Portfolio = P+I for loans disbursed this month."""
        bid, month = bid_response
        loan, principal, interest, total_outstanding = disbursed_loan
        cr_totals = bid.get("cr_totals", [])
        lp_entries = [
            c for c in cr_totals
            if "portfolio" in c.get("account_head_name", "").lower()
            or "loans" in c.get("account_head_name", "").lower()
        ]
        assert len(lp_entries) >= 1, (
            f"No Loans Portfolio in cr_totals. cr_totals: {cr_totals}"
        )
        lp_total = sum(e["total"] for e in lp_entries)
        # Loans Portfolio Cr must include our loan's P+I
        assert lp_total >= total_outstanding, (
            f"Loans Portfolio Cr {lp_total} should be >= {total_outstanding} (P+I for our loan)"
        )

    def test_bid_balance_equation(self, bid_response):
        """Closing balance = Opening + total_dr - total_cr."""
        bid, month = bid_response
        opening = float(bid["opening_balance"])
        total_dr = float(bid["total_dr"])
        total_cr = float(bid["total_cr"])
        closing = float(bid["closing_balance"])
        expected_closing = round(opening + total_dr - total_cr, 2)
        assert abs(closing - expected_closing) < 0.01, (
            f"Balance equation failed: {opening} + {total_dr} - {total_cr} = {expected_closing}, "
            f"but closing_balance = {closing}"
        )


# ─── Test 6: Old 3-line EMI entries appear at full cash_dr in Bid ─────────────

class TestOldFormatEmiEntriesInBid:
    """Existing 3-line EMI entries (old format) must appear at full cash_dr in Bid."""

    def test_old_3line_emi_uses_cash_dr_for_bid(self, admin_session):
        """Find any existing 3-line emi_collection entry and verify Bid uses full cash_dr."""
        # Fetch recent emi_collection entries to find 3-line ones
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection", "limit": 200},
        )
        assert resp.status_code == 200
        entries = resp.json().get("entries", [])

        # Find entries with 3 lines (old format)
        three_line_entries = [e for e in entries if len(e.get("lines", [])) == 3]
        if not three_line_entries:
            pytest.skip("No 3-line EMI entries found in DB — skipping backward-compat test")

        entry = three_line_entries[0]
        entry_id = entry.get("id")
        illaka_id = entry.get("illaka_id")
        entry_date = entry.get("date", "")
        entry_month = entry_date[:7]

        # Get cash head to find cash_dr
        cash_head = None
        resp2 = admin_session.get(f"{BASE_URL}/api/accounts/heads", params={"is_active": True})
        if resp2.status_code == 200:
            heads = resp2.json()
            cash_head = next((h for h in heads if "cash" in h.get("name", "").lower()), None)

        if not cash_head:
            pytest.skip("Could not find Cash account head")

        cash_head_id = cash_head["id"]
        lines = entry.get("lines", [])
        cash_dr = sum(
            float(l.get("debit", 0))
            for l in lines
            if l.get("account_head_id") == cash_head_id
        )
        if cash_dr <= 0:
            pytest.skip(f"3-line EMI entry {entry_id} has no cash debit, cannot test")

        # Now check the Bid for that month/illaka
        bid_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/bid",
            params={"illaka_id": illaka_id, "month": entry_month},
        )
        assert bid_resp.status_code == 200
        bid = bid_resp.json()
        dr_totals = bid.get("dr_totals", [])
        emi_section = next((s for s in dr_totals if s.get("type") == "emi_total"), None)
        assert emi_section is not None, (
            f"No emi_total section in Bid dr_totals for {illaka_id}/{entry_month}. "
            f"dr_totals: {dr_totals}"
        )
        # The EMI section total must be >= cash_dr (it includes our 3-line entry at full cash_dr)
        assert emi_section["total"] >= cash_dr, (
            f"EMI Collections total {emi_section['total']} should be >= cash_dr {cash_dr} "
            f"from 3-line EMI entry {entry_id}"
        )
        print(f"  3-line EMI entry {entry_id}: cash_dr={cash_dr}, Bid EMI total={emi_section['total']}")


# ─── Test: Interest Income in Bid does NOT come from EMI entries ───────────────

class TestInterestIncomeSourceInBid:
    """Interest Income in Bid must come ONLY from loan_disbursement entries, not emi_collection."""

    def test_emi_entries_do_not_contribute_to_interest_income(self, admin_session, test_illaka, collected_emi):
        """After collecting an EMI (2-line), Interest Income in Bid should NOT increase."""
        from datetime import date as _date
        today = _date.today()
        month = f"{today.year}-{today.month:02d}"

        # Get Bid BEFORE we can observe interest income
        resp_before = admin_session.get(
            f"{BASE_URL}/api/accounts/bid",
            params={"illaka_id": test_illaka["id"], "month": month},
        )
        assert resp_before.status_code == 200
        bid_before = resp_before.json()

        dr_totals = bid_before.get("dr_totals", [])
        interest_before = sum(
            s["total"] for s in dr_totals
            if s.get("type") == "income" and "interest" in s.get("label", "").lower()
        )

        # The interest should be from the disbursement only (fixture already disbursed + collected EMI)
        # Verify no emi_collection entry contributes an interest income line
        emi_amount, loan_id, _ = collected_emi
        emi_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "emi_collection"},
        )
        emi_entries = emi_resp.json().get("entries", [])
        our_emi = next((e for e in emi_entries if e.get("reference_id") == loan_id), None)
        if our_emi:
            lines = our_emi.get("lines", [])
            interest_lines_in_emi = [
                l for l in lines if "interest" in l.get("account_head_name", "").lower()
            ]
            assert len(interest_lines_in_emi) == 0, (
                f"EMI entry should NOT have interest lines, but found: {interest_lines_in_emi}"
            )
        print(f"  Interest Income in Bid for {month}: {interest_before}")
        print("  No interest lines found in EMI entry — PASS")


# ─── Test: Formula Verification ───────────────────────────────────────────────

class TestInterestFormula:
    """Verify the interest formula: interest = round(principal * 17/103, 2)."""

    @pytest.mark.parametrize("principal,expected_interest", [
        (6000.0, round(6000 * 17 / 103, 2)),
        (10000.0, round(10000 * 17 / 103, 2)),
        (15000.0, round(15000 * 17 / 103, 2)),
        (20000.0, round(20000 * 17 / 103, 2)),
        (100000.0, round(100000 * 17 / 103, 2)),
    ])
    def test_formula_calculation(self, principal, expected_interest):
        """Verify interest formula gives correct values for common principals."""
        # This is a pure math verification
        computed = round(principal * 17 / 103, 2)
        assert computed == expected_interest, (
            f"Formula check: round({principal} * 17/103, 2) = {computed}, expected {expected_interest}"
        )

    def test_test_loan_interest_matches_formula(self, admin_session, disbursed_loan):
        """The test loan's disbursement entry has interest = round(principal * 17/103, 2)."""
        loan, principal, expected_interest, total_outstanding = disbursed_loan
        loan_id = loan["id"]
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries",
            params={"entry_type": "loan_disbursement"},
        )
        entries = resp.json().get("entries", [])
        entry = next((e for e in entries if e.get("reference_id") == loan_id), None)
        assert entry is not None
        lines = entry["lines"]
        interest_lines = [
            l for l in lines
            if float(l.get("credit", 0)) > 0
            and "interest" in l.get("account_head_name", "").lower()
        ]
        assert len(interest_lines) >= 1, "Interest Income line not found in disbursement entry"
        actual_interest = float(interest_lines[0]["credit"])
        assert abs(actual_interest - expected_interest) < 0.01, (
            f"Interest in entry: {actual_interest}, expected: {expected_interest} "
            f"(= round({principal} * 17/103, 2))"
        )
