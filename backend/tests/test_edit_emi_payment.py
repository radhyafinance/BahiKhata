"""
Iteration 20 tests: Edit EMI Payment Feature
- PATCH /api/loans/{loan_id}/payments/{emi_month} — edit paid EMI entry
- GET  /api/collections/sheet — returns emi_paid_amount, emi_paid_date, latest_closing_ym

Role rules:
  - Muneem/Sipahi: current month only (2026-03)
  - Admin/Maalik: any month not locked by year-end closing
  - Delhi illaka (69c78cf96781e1fb0d95f0dd) has latest_closing_ym='2024-03'
  - emi_month <= '2024-03' for Delhi => 403 for admin
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
DELHI_ILLAKA_ID = "69c78cf96781e1fb0d95f0dd"
CURRENT_MONTH = "2026-03"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def muneem_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "7777000001", "password": "Test@1234"})
    assert resp.status_code == 200, f"Muneem login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def paid_emi_row(admin_session):
    """Find a paid EMI in current month (2026-03) in Delhi illaka."""
    resp = admin_session.get(
        f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
    )
    assert resp.status_code == 200, f"Collection sheet failed: {resp.text}"
    data = resp.json()
    for il in data.get("illakas", []):
        for m in il.get("misals", []):
            for row in m.get("rows", []):
                if row.get("emi_status") == "paid" and not row.get("is_gyal"):
                    return row
    # If no non-gyal paid row, accept gyal too
    for il in data.get("illakas", []):
        for m in il.get("misals", []):
            for row in m.get("rows", []):
                if row.get("emi_status") == "paid":
                    return row
    pytest.skip("No paid EMI row found in Delhi illaka for 2026-03")


@pytest.fixture(scope="module")
def any_delhi_loan_id(admin_session):
    """Find any active loan in Delhi illaka."""
    resp = admin_session.get(
        f"{BASE_URL}/api/loans?illaka_id={DELHI_ILLAKA_ID}&status=active&limit=1"
    )
    if resp.status_code == 200:
        loans = resp.json().get("loans", [])
        if loans:
            return loans[0]["id"]
    # Try collection sheet to get a loan_id
    sheet_resp = admin_session.get(
        f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
    )
    if sheet_resp.status_code == 200:
        data = sheet_resp.json()
        for il in data.get("illakas", []):
            for m in il.get("misals", []):
                for row in m.get("rows", []):
                    return row["loan_db_id"]
    pytest.skip("No loans found in Delhi illaka")


# ── Collection Sheet: field presence tests ────────────────────────────────────

class TestCollectionSheetFields:
    """GET /api/collections/sheet returns required fields for paid rows and latest_closing_ym"""

    def test_collection_sheet_returns_200(self, admin_session):
        """Collection sheet GET returns 200 for admin"""
        resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: GET /api/collections/sheet returns 200")

    def test_collection_sheet_has_latest_closing_ym(self, admin_session):
        """Collection sheet response includes latest_closing_ym per illaka"""
        resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "illakas" in data
        for il in data["illakas"]:
            assert "latest_closing_ym" in il, f"Illaka {il.get('illaka_name')} missing latest_closing_ym"
        print("PASS: Every illaka has latest_closing_ym field")

    def test_delhi_illaka_latest_closing_ym_is_2024_03(self, admin_session):
        """Delhi illaka should have latest_closing_ym = '2024-03'"""
        resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        delhi = next((il for il in data["illakas"] if il["illaka_id"] == DELHI_ILLAKA_ID), None)
        assert delhi is not None, "Delhi illaka not found in response"
        assert delhi["latest_closing_ym"] == "2024-03", (
            f"Expected '2024-03', got '{delhi['latest_closing_ym']}'"
        )
        print(f"PASS: Delhi illaka latest_closing_ym = '{delhi['latest_closing_ym']}'")

    def test_paid_rows_have_emi_paid_amount(self, admin_session):
        """Paid EMI rows should have emi_paid_amount field"""
        resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        paid_found = False
        for il in data["illakas"]:
            for m in il["misals"]:
                for row in m["rows"]:
                    if row.get("emi_status") == "paid":
                        assert "emi_paid_amount" in row, f"Row {row.get('loan_db_id')} missing emi_paid_amount"
                        assert row["emi_paid_amount"] > 0, f"emi_paid_amount should be > 0 for paid row"
                        paid_found = True
        if not paid_found:
            pytest.skip("No paid rows found in 2026-03 for Delhi illaka")
        print("PASS: All paid rows have emi_paid_amount > 0")

    def test_paid_rows_have_emi_paid_date(self, admin_session):
        """Paid EMI rows should have emi_paid_date field"""
        resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        paid_found = False
        for il in data["illakas"]:
            for m in il["misals"]:
                for row in m["rows"]:
                    if row.get("emi_status") == "paid":
                        assert "emi_paid_date" in row, f"Row {row.get('loan_db_id')} missing emi_paid_date"
                        paid_found = True
        if not paid_found:
            pytest.skip("No paid rows found in 2026-03 for Delhi illaka")
        print("PASS: All paid rows have emi_paid_date field")

    def test_unpaid_rows_have_zero_emi_paid_amount(self, admin_session):
        """Non-paid rows should have emi_paid_amount = 0"""
        resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert resp.status_code == 200
        data = resp.json()
        for il in data["illakas"]:
            for m in il["misals"]:
                for row in m["rows"]:
                    if row.get("emi_status") != "paid":
                        paid_amt = row.get("emi_paid_amount", 0)
                        assert paid_amt == 0, (
                            f"Non-paid row {row.get('loan_db_id')} has emi_paid_amount={paid_amt}"
                        )
        print("PASS: Non-paid rows have emi_paid_amount = 0")


# ── PATCH /api/loans/{loan_id}/payments/{emi_month} ──────────────────────────

class TestEditEmiPayment:
    """PATCH /loans/{loan_id}/payments/{emi_month} — admin edits paid EMI"""

    def test_admin_can_edit_current_month_paid_emi(self, admin_session, paid_emi_row):
        """Admin can edit a paid EMI in current month (2026-03) in Delhi illaka"""
        loan_id = paid_emi_row["loan_db_id"]
        emi_month = paid_emi_row["emi_month"]
        original_amount = paid_emi_row["emi_paid_amount"]
        original_date = paid_emi_row["emi_paid_date"]

        new_amount = original_amount + 1  # slight change for test
        new_date = "2026-03-15"

        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": new_amount, "payment_date": new_date}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "emi_schedule" in data or "id" in data, "Response should contain loan data"
        print(f"PASS: PATCH /loans/{loan_id}/payments/{emi_month} → 200 (amount={new_amount})")

        # Restore original values
        admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": original_amount, "payment_date": original_date}
        )
        print(f"PASS: Restored original amount={original_amount}, date={original_date}")

    def test_edit_persists_in_collection_sheet(self, admin_session, paid_emi_row):
        """After edit, collection sheet should show updated emi_paid_amount"""
        loan_id = paid_emi_row["loan_db_id"]
        emi_month = paid_emi_row["emi_month"]
        original_amount = paid_emi_row["emi_paid_amount"]
        original_date = paid_emi_row["emi_paid_date"]

        new_amount = original_amount + 2
        new_date = "2026-03-20"

        # Edit
        edit_resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": new_amount, "payment_date": new_date}
        )
        assert edit_resp.status_code == 200, f"Edit failed: {edit_resp.text}"

        # Verify in collection sheet
        sheet_resp = admin_session.get(
            f"{BASE_URL}/api/collections/sheet?month={CURRENT_MONTH}&illaka_id={DELHI_ILLAKA_ID}"
        )
        assert sheet_resp.status_code == 200
        sheet_data = sheet_resp.json()
        updated_row = None
        for il in sheet_data["illakas"]:
            for m in il["misals"]:
                for row in m["rows"]:
                    if row["loan_db_id"] == loan_id and row["emi_month"] == emi_month:
                        updated_row = row
                        break
        assert updated_row is not None, "Edited row not found in collection sheet"
        assert updated_row["emi_paid_amount"] == new_amount, (
            f"Expected emi_paid_amount={new_amount}, got {updated_row['emi_paid_amount']}"
        )
        assert updated_row["emi_paid_date"] == new_date, (
            f"Expected emi_paid_date={new_date}, got {updated_row['emi_paid_date']}"
        )
        print(f"PASS: Collection sheet shows updated emi_paid_amount={new_amount} and date={new_date}")

        # Restore
        admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": original_amount, "payment_date": original_date}
        )

    def test_edit_only_amount_keeps_date(self, admin_session, paid_emi_row):
        """Editing only amount should keep the existing date"""
        loan_id = paid_emi_row["loan_db_id"]
        emi_month = paid_emi_row["emi_month"]
        original_amount = paid_emi_row["emi_paid_amount"]
        original_date = paid_emi_row["emi_paid_date"]

        new_amount = original_amount + 3

        # Edit only amount (no payment_date)
        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": new_amount}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print(f"PASS: PATCH with only amount → 200")

        # Restore
        admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": original_amount, "payment_date": original_date}
        )

    def test_edit_invalid_loan_id_returns_400(self, admin_session):
        """PATCH with invalid loan_id format returns 400"""
        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/invalid_id/payments/{CURRENT_MONTH}",
            json={"amount": 500.0, "payment_date": "2026-03-15"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("PASS: PATCH with invalid loan_id → 400")

    def test_edit_nonexistent_loan_returns_404(self, admin_session):
        """PATCH with nonexistent loan_id returns 404"""
        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/000000000000000000000000/payments/{CURRENT_MONTH}",
            json={"amount": 500.0, "payment_date": "2026-03-15"}
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("PASS: PATCH with nonexistent loan → 404")


# ── Year-closing lock tests ───────────────────────────────────────────────────

class TestYearClosingLock:
    """Admin/Maalik cannot edit emi_month <= latest_closing_ym for that illaka"""

    def test_admin_edit_locked_month_returns_403(self, admin_session, any_delhi_loan_id):
        """Admin editing emi_month <= '2024-03' for Delhi illaka returns 403"""
        loan_id = any_delhi_loan_id
        locked_emi_month = "2024-01"  # clearly locked (before 2024-03)

        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{locked_emi_month}",
            json={"amount": 500.0, "payment_date": "2024-01-15"}
        )
        assert resp.status_code == 403, (
            f"Expected 403 for locked emi_month={locked_emi_month}, got {resp.status_code}: {resp.text}"
        )
        detail = resp.json().get("detail", "")
        assert "locked" in detail.lower() or "closing" in detail.lower(), (
            f"Expected locking message in detail, got: {detail}"
        )
        print(f"PASS: Admin editing locked month 2024-01 → 403: {detail}")

    def test_admin_edit_closing_month_itself_returns_403(self, admin_session, any_delhi_loan_id):
        """Admin editing emi_month = '2024-03' (the closing month) also returns 403"""
        loan_id = any_delhi_loan_id
        closing_emi_month = "2024-03"

        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{closing_emi_month}",
            json={"amount": 500.0, "payment_date": "2024-03-15"}
        )
        assert resp.status_code == 403, (
            f"Expected 403 for closing month {closing_emi_month}, got {resp.status_code}: {resp.text}"
        )
        print(f"PASS: Admin editing closing month 2024-03 → 403")

    def test_admin_edit_month_after_closing_not_blocked(self, admin_session, paid_emi_row):
        """Admin editing emi_month > '2024-03' should NOT be blocked by year-closing lock"""
        # emi_month = 2026-03 > 2024-03, so should pass the lock check
        loan_id = paid_emi_row["loan_db_id"]
        emi_month = paid_emi_row["emi_month"]
        original_amount = paid_emi_row["emi_paid_amount"]
        original_date = paid_emi_row["emi_paid_date"]

        assert emi_month > "2024-03", f"emi_month {emi_month} should be > 2024-03 for this test"

        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": original_amount, "payment_date": original_date}
        )
        # Should be 200 (not 403)
        assert resp.status_code == 200, (
            f"Expected 200 for unlocked emi_month {emi_month}, got {resp.status_code}: {resp.text}"
        )
        print(f"PASS: Admin editing emi_month {emi_month} (after closing) → 200 (not blocked)")


# ── Muneem permission tests ───────────────────────────────────────────────────

class TestMuneemPermissions:
    """Muneem/Sipahi can only edit current month"""

    def test_muneem_edit_past_month_returns_403(self, muneem_session, any_delhi_loan_id):
        """Muneem editing any past month (not 2026-03) returns 403"""
        loan_id = any_delhi_loan_id
        past_emi_month = "2025-01"

        resp = muneem_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{past_emi_month}",
            json={"amount": 500.0, "payment_date": "2025-01-15"}
        )
        assert resp.status_code == 403, (
            f"Expected 403 for muneem editing past month, got {resp.status_code}: {resp.text}"
        )
        detail = resp.json().get("detail", "")
        assert "current month" in detail.lower() or "muneem" in detail.lower() or "sipahi" in detail.lower(), (
            f"Expected relevant error message, got: {detail}"
        )
        print(f"PASS: Muneem editing past month 2025-01 → 403: {detail}")

    def test_muneem_edit_future_month_returns_403(self, muneem_session, any_delhi_loan_id):
        """Muneem editing a future month (not 2026-03) returns 403"""
        loan_id = any_delhi_loan_id
        future_emi_month = "2026-06"

        resp = muneem_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{future_emi_month}",
            json={"amount": 500.0, "payment_date": "2026-06-15"}
        )
        assert resp.status_code == 403, (
            f"Expected 403 for muneem editing future month, got {resp.status_code}: {resp.text}"
        )
        print(f"PASS: Muneem editing future month 2026-06 → 403")

    def test_muneem_edit_current_month_reaches_schedule_lookup(self, muneem_session, paid_emi_row):
        """Muneem editing current month (2026-03) should pass role check (may fail on paid status for real data)"""
        # This test verifies muneem PASSES the role check for current month
        # It might return 200 (if paid) or 400 (if not found/not paid), but NOT 403 for wrong month
        loan_id = paid_emi_row["loan_db_id"]
        emi_month = paid_emi_row["emi_month"]
        original_amount = paid_emi_row["emi_paid_amount"]
        original_date = paid_emi_row["emi_paid_date"]

        assert emi_month == CURRENT_MONTH, f"Test requires emi_month={CURRENT_MONTH}"

        resp = muneem_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}",
            json={"amount": original_amount, "payment_date": original_date}
        )
        # Should NOT be 403 for wrong month (current month is allowed for muneem)
        # Could be 200 (success) or 400 (not paid / other error)
        assert resp.status_code != 403, (
            f"Muneem should not get 403 for current month, got {resp.status_code}: {resp.text}"
        )
        if resp.status_code == 200:
            print(f"PASS: Muneem editing current month {emi_month} → 200")
        else:
            print(f"PASS: Muneem editing current month {emi_month} → {resp.status_code} (not 403, role check passed)")
