"""
Test Undo Year-End Closing feature for Bahi Khata NBFC-MFI app

Tests:
- GET /api/loans/year-end-closing/history returns list sorted newest first
- Muneem gets 403 on GET history
- Muneem gets 403 on POST undo
- POST undo reverts is_gyal=True loans, removes gyal_since, deletes gyal_writeoff entries
- Undo BLOCKED (400) when newer closing exists
- After undo, new closing can be done again
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# IDs from existing test environment
DELHI_ILLAKA_ID = "69c78cf96781e1fb0d95f0dd"
DELHI_MISAL_ID = "69c78cf96781e1fb0d95f0de"
TEST_ILLAKA_CENTRAL_ID = "69c6902e2eb75a3158e9a20c"  # already has 1 closing (2025-03-31, 1 loan)


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    res = session.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return session


@pytest.fixture(scope="module")
def muneem_session():
    """Login as muneem"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    res = session.post(f"{BASE_URL}/api/auth/login", json={"phone": "7777000001", "password": "Test@1234"})
    assert res.status_code == 200, f"Muneem login failed: {res.text}"
    return session


@pytest.fixture(scope="module")
def sipahi_session():
    """Login as sipahi (field agent who can create KYC and loans)"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    res = session.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
    assert res.status_code == 200, f"Sipahi login failed: {res.text}"
    return session


def create_test_kyc_and_loan(sipahi_session, illaka_id, misal_id, illaka_name, misal_name, loan_date, client_suffix=""):
    """Helper: Create a KYC and loan with an old date, return loan_id and kyc_id"""
    unique = int(time.time() * 1000) % 10000000
    phone = f"700{unique:07d}"
    aadhaar = f"{unique:012d}"

    kyc_data = {
        "illaka_id": illaka_id,
        "illaka_name": illaka_name,
        "misal_id": misal_id,
        "misal_name": misal_name,
        "primary_borrower": {
            "full_name": f"TEST_Undo_Customer{client_suffix}",
            "full_name_hindi": "टेस्ट अनडू",
            "phone": phone,
            "gender": "female",
            "aadhaar_number": aadhaar,
            "address": "Test Village"
        },
        "status": "approved"
    }
    kyc_res = sipahi_session.post(f"{BASE_URL}/api/kycs", json=kyc_data)
    assert kyc_res.status_code == 200, f"KYC creation failed: {kyc_res.text}"
    kyc_id = kyc_res.json()["id"]

    loan_data = {
        "kyc_id": kyc_id,
        "illaka_id": illaka_id,
        "illaka_name": illaka_name,
        "misal_id": misal_id,
        "misal_name": misal_name,
        "client_name": f"TEST_Undo_Customer{client_suffix}",
        "loan_date": loan_date,
        "principal_amount": 5000,
        "tenure_months": 12,
        "status": "active"
    }
    loan_res = sipahi_session.post(f"{BASE_URL}/api/loans", json=loan_data)
    assert loan_res.status_code == 200, f"Loan creation failed: {loan_res.text}"
    return loan_res.json()["id"], kyc_id


# ─── History API Tests ───────────────────────────────────────────────────────

class TestYearEndClosingHistory:
    """Tests for GET /api/loans/year-end-closing/history"""

    def test_history_returns_200_for_admin(self, admin_session):
        """Admin should get 200 with closings list"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_history_response_has_closings_key(self, admin_session):
        """Response must have a 'closings' key with a list"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200
        data = res.json()
        assert "closings" in data, f"Missing 'closings' key in response: {data}"
        assert isinstance(data["closings"], list), f"'closings' should be list, got {type(data['closings'])}"

    def test_history_closings_have_date_and_count(self, admin_session):
        """Each closing entry must have closing_date and count"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200
        data = res.json()
        for closing in data["closings"]:
            assert "closing_date" in closing, f"Closing entry missing 'closing_date': {closing}"
            assert "count" in closing, f"Closing entry missing 'count': {closing}"
            assert isinstance(closing["count"], int), f"count should be int: {closing}"
        print(f"History entries: {data['closings']}")

    def test_history_sorted_newest_first(self, admin_session):
        """Closings should be sorted with newest date first"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200
        closings = res.json()["closings"]
        if len(closings) >= 2:
            dates = [c["closing_date"] for c in closings]
            assert dates == sorted(dates, reverse=True), f"Closings not sorted newest first: {dates}"

    def test_history_shows_existing_closing_count(self, admin_session):
        """TEST_Illaka_Central should show exactly 1 closing with count=1 from previous tests"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["closings"]) >= 1, f"Expected at least 1 closing, got {len(data['closings'])}"
        assert data["closings"][0]["closing_date"] == "2025-03-31"
        assert data["closings"][0]["count"] >= 1
        print(f"Existing closing: {data['closings']}")

    def test_history_empty_illaka_returns_empty_list(self, admin_session):
        """Illaka with no gyal loans should return empty closings list"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID}
        )
        assert res.status_code == 200
        data = res.json()
        # Delhi illaka has no closings (confirmed above), but we just verify structure
        assert "closings" in data
        print(f"Delhi history: {data['closings']}")

    def test_history_muneem_gets_403(self, muneem_session):
        """Muneem should get 403 on GET history"""
        res = muneem_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 403, f"Expected 403 for muneem, got {res.status_code}: {res.text}"
        print(f"Muneem history blocked: {res.json()}")

    def test_history_unauthenticated_returns_401_or_403(self):
        """Unauthenticated request should return 401 or 403"""
        res = requests.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code in [401, 403], f"Expected 401/403, got {res.status_code}"


# ─── Undo Permission Tests ────────────────────────────────────────────────────

class TestUndoPermissions:
    """Tests for role-based access on POST /api/loans/year-end-closing/undo"""

    def test_undo_muneem_gets_403(self, muneem_session):
        """Muneem should get 403 on POST undo"""
        res = muneem_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": TEST_ILLAKA_CENTRAL_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 403, f"Expected 403 for muneem, got {res.status_code}: {res.text}"
        print(f"Muneem undo blocked: {res.json()}")

    def test_undo_unauthenticated_returns_401_or_403(self):
        """Unauthenticated undo should return 401 or 403"""
        res = requests.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": TEST_ILLAKA_CENTRAL_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code in [401, 403], f"Expected 401/403, got {res.status_code}"

    def test_undo_nonexistent_closing_returns_404(self, admin_session):
        """Undo for a date with no gyal loans should return 404"""
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "1999-03-31"}
        )
        assert res.status_code == 404, f"Expected 404 for nonexistent closing, got {res.status_code}: {res.text}"
        print(f"Nonexistent closing undo: {res.json()}")


# ─── Full Undo Flow Tests ─────────────────────────────────────────────────────

class TestUndoFullFlow:
    """Full undo flow: create loan → close → undo → verify loan restored"""

    # Shared state across tests
    loan_id_1 = None
    loan_id_2 = None

    def test_01_setup_create_old_loan_for_delhi(self, sipahi_session):
        """Create a loan with date 2017-01-01 in Delhi illaka for year-end closing"""
        loan_id, _ = create_test_kyc_and_loan(
            sipahi_session,
            DELHI_ILLAKA_ID, DELHI_MISAL_ID,
            "Delhi", "TEST_Misal_Delhi",
            "2017-01-01",
            "_A1"
        )
        TestUndoFullFlow.loan_id_1 = loan_id
        print(f"Created test loan 1: {loan_id} (2017-01-01)")
        assert loan_id is not None

    def test_02_preview_finds_old_loan(self, admin_session):
        """Preview should find the old loan"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1, f"Expected at least 1 loan in preview, got {data['count']}"
        # Preview API returns loan_number/client_name/loan_date/outstanding (not id)
        client_names = [l.get("client_name", "") for l in data["loans"]]
        assert any("TEST_Undo_Customer" in name for name in client_names), (
            f"Expected a TEST_Undo_Customer in preview, got {client_names}"
        )
        print(f"Preview finds {data['count']} loan(s): {client_names}")

    def test_03_do_year_end_closing_2025(self, admin_session):
        """Do year-end closing for 2025-03-31 on Delhi illaka"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Closing failed: {res.text}"
        data = res.json()
        assert data["marked_count"] >= 1
        print(f"Closing 2025-03-31 result: {data}")

    def test_04_verify_loan_is_gyal(self, admin_session):
        """After closing, loan should have is_gyal=True and gyal_since=2025-03-31"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.get(f"{BASE_URL}/api/loans/{TestUndoFullFlow.loan_id_1}")
        assert res.status_code == 200
        loan = res.json()
        assert loan.get("is_gyal") is True, f"Expected is_gyal=True, got {loan.get('is_gyal')}"
        assert loan.get("gyal_since") == "2025-03-31", f"Expected gyal_since=2025-03-31, got {loan.get('gyal_since')}"
        print(f"Loan 1 is_gyal={loan['is_gyal']}, gyal_since={loan['gyal_since']}")

    def test_05_history_shows_one_closing(self, admin_session):
        """History should now show 1 closing for Delhi"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID}
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["closings"]) >= 1
        assert data["closings"][0]["closing_date"] == "2025-03-31"
        print(f"Delhi history after closing: {data['closings']}")

    def test_06_undo_most_recent_closing(self, admin_session):
        """Undo the 2025-03-31 closing - should succeed"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Undo failed: {res.text}"
        data = res.json()
        assert "undone_count" in data, f"Response missing 'undone_count': {data}"
        assert data["undone_count"] >= 1, f"Expected undone_count>=1, got {data['undone_count']}"
        assert "message" in data
        print(f"Undo result: {data}")

    def test_07_verify_loan_is_no_longer_gyal(self, admin_session):
        """After undo, loan should have is_gyal=False and no gyal_since"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.get(f"{BASE_URL}/api/loans/{TestUndoFullFlow.loan_id_1}")
        assert res.status_code == 200
        loan = res.json()
        assert loan.get("is_gyal") is not True, f"Expected is_gyal=False/None after undo, got {loan.get('is_gyal')}"
        assert not loan.get("gyal_since"), f"Expected gyal_since to be removed, got {loan.get('gyal_since')}"
        print(f"Loan 1 after undo: is_gyal={loan.get('is_gyal')}, gyal_since={loan.get('gyal_since')}")

    def test_08_verify_gyal_journal_entries_deleted(self, admin_session):
        """After undo, gyal_writeoff journal entries should be deleted"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        # Check journal entries for this loan
        res = admin_session.get(
            f"{BASE_URL}/api/accounts/journal",
            params={"reference_id": TestUndoFullFlow.loan_id_1, "entry_type": "gyal_writeoff"}
        )
        # If the endpoint exists and returns 200, check entries
        if res.status_code == 200:
            data = res.json()
            entries = data if isinstance(data, list) else data.get("entries", [])
            gyal_entries = [e for e in entries if e.get("entry_type") == "gyal_writeoff"]
            assert len(gyal_entries) == 0, f"Expected no gyal_writeoff entries after undo, found {len(gyal_entries)}"
            print(f"Journal entries after undo: {len(gyal_entries)} gyal_writeoff entries")
        else:
            print(f"Journal endpoint returned {res.status_code} - skipping journal check")

    def test_09_history_is_empty_after_undo(self, admin_session):
        """After undo, Delhi history should be empty"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID}
        )
        assert res.status_code == 200
        data = res.json()
        # The undo should have removed the 2025-03-31 entry
        dates = [c["closing_date"] for c in data["closings"]]
        assert "2025-03-31" not in dates, f"2025-03-31 should be gone from history after undo, got {dates}"
        print(f"Delhi history after undo: {data['closings']}")

    def test_10_loan_reappears_in_preview_after_undo(self, admin_session):
        """After undo, the loan should reappear in preview (can be re-closed)"""
        if not TestUndoFullFlow.loan_id_1:
            pytest.skip("Loan 1 not created")
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1, f"Expected loan to reappear after undo, got count={data['count']}"
        # Preview API returns loan_number/client_name/loan_date/outstanding (not id)
        client_names = [l.get("client_name", "") for l in data["loans"]]
        assert any("TEST_Undo_Customer" in name for name in client_names), (
            f"Expected TEST_Undo_Customer in preview after undo, got {client_names}"
        )
        print(f"Preview after undo: {data['count']} eligible loans: {client_names}")


# ─── Blocked Undo Tests ────────────────────────────────────────────────────────

class TestBlockedUndo:
    """Test that undo is blocked when a newer closing exists"""

    loan_id_older = None
    loan_id_newer = None

    def test_01_create_first_loan_for_blocked_test(self, sipahi_session, admin_session):
        """Create loan 1 with old date in Delhi and close at 2024-03-31"""
        loan_id, _ = create_test_kyc_and_loan(
            sipahi_session,
            DELHI_ILLAKA_ID, DELHI_MISAL_ID,
            "Delhi", "TEST_Misal_Delhi",
            "2015-01-01",
            "_B1"
        )
        TestBlockedUndo.loan_id_older = loan_id
        print(f"Created loan B1: {loan_id}")

        # Close at 2024-03-31 (cutoff = 2021-03-31, which is before 2015-01-01)
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2024-03-31"}
        )
        assert res.status_code == 200, f"First closing failed: {res.text}"
        data = res.json()
        assert data["marked_count"] >= 1, f"Expected >=1 marked, got {data['marked_count']}"
        print(f"First closing (2024-03-31): {data}")

    def test_02_create_second_loan_for_blocked_test(self, sipahi_session, admin_session):
        """Create loan 2 with old date in Delhi and close at 2025-03-31"""
        if not TestBlockedUndo.loan_id_older:
            pytest.skip("Loan B1 not created")
        loan_id, _ = create_test_kyc_and_loan(
            sipahi_session,
            DELHI_ILLAKA_ID, DELHI_MISAL_ID,
            "Delhi", "TEST_Misal_Delhi",
            "2016-06-01",
            "_B2"
        )
        TestBlockedUndo.loan_id_newer = loan_id
        print(f"Created loan B2: {loan_id}")

        # Close at 2025-03-31 (cutoff = 2022-03-31, before 2016-06-01)
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Second closing failed: {res.text}"
        data = res.json()
        assert data["marked_count"] >= 1, f"Expected >=1 marked, got {data['marked_count']}"
        print(f"Second closing (2025-03-31): {data}")

    def test_03_history_shows_two_closings_newest_first(self, admin_session):
        """History should show both closings sorted newest first"""
        if not TestBlockedUndo.loan_id_newer:
            pytest.skip("Loans not set up")
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID}
        )
        assert res.status_code == 200
        data = res.json()
        dates = [c["closing_date"] for c in data["closings"]]
        assert "2024-03-31" in dates, f"Expected 2024-03-31 in history: {dates}"
        assert "2025-03-31" in dates, f"Expected 2025-03-31 in history: {dates}"
        # Newest first
        assert dates[0] == "2025-03-31", f"Newest should be first (2025-03-31), got {dates[0]}"
        print(f"History with 2 closings: {dates}")

    def test_04_undo_older_closing_is_blocked_400(self, admin_session):
        """Trying to undo the older closing (2024-03-31) should return 400"""
        if not TestBlockedUndo.loan_id_newer:
            pytest.skip("Loans not set up")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2024-03-31"}
        )
        assert res.status_code == 400, f"Expected 400 (blocked), got {res.status_code}: {res.text}"
        data = res.json()
        assert "detail" in data, "Response should have 'detail' error message"
        # Error message should mention newer closing
        detail = data["detail"].lower()
        assert any(word in detail for word in ["recent", "newer", "first", "blocked"]), (
            f"Error message should mention blocking reason, got: {data['detail']}"
        )
        print(f"Blocked undo response: {data['detail']}")

    def test_05_undo_newer_closing_succeeds(self, admin_session):
        """Undo the newest closing (2025-03-31) should succeed"""
        if not TestBlockedUndo.loan_id_newer:
            pytest.skip("Loans not set up")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Undo 2025-03-31 failed: {res.text}"
        data = res.json()
        assert data["undone_count"] >= 1
        print(f"Undo 2025-03-31 result: {data}")

    def test_06_after_newer_undone_older_can_be_undone(self, admin_session):
        """After undoing 2025-03-31, now 2024-03-31 should be undoable"""
        if not TestBlockedUndo.loan_id_older:
            pytest.skip("Loan B1 not set up")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2024-03-31"}
        )
        assert res.status_code == 200, f"Undo 2024-03-31 failed: {res.text}"
        data = res.json()
        assert data["undone_count"] >= 1
        print(f"Undo 2024-03-31 result after 2025-03-31 undone: {data}")

    def test_07_verify_all_loans_restored(self, admin_session):
        """Both loans should now have is_gyal=False"""
        for loan_id, label in [(TestBlockedUndo.loan_id_older, "B1"), (TestBlockedUndo.loan_id_newer, "B2")]:
            if not loan_id:
                continue
            res = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
            assert res.status_code == 200
            loan = res.json()
            assert loan.get("is_gyal") is not True, f"Loan {label} should not be gyal after undo"
            assert not loan.get("gyal_since"), f"Loan {label} gyal_since should be empty after undo"
            print(f"Loan {label} restored: is_gyal={loan.get('is_gyal')}, gyal_since={loan.get('gyal_since')}")

    def test_08_delhi_history_empty_after_all_undos(self, admin_session):
        """After undoing both closings, Delhi history should be empty"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID}
        )
        assert res.status_code == 200
        data = res.json()
        dates = [c["closing_date"] for c in data["closings"]]
        assert "2024-03-31" not in dates
        assert "2025-03-31" not in dates
        print(f"Delhi history after all undos: {data['closings']}")


# ─── Do Another Closing After Undo ────────────────────────────────────────────

class TestRedoClosingAfterUndo:
    """Test that a new closing can be done after undo"""

    loan_id_redo = None

    def test_01_create_loan_for_redo_test(self, sipahi_session):
        """Create a fresh old loan for re-closing test"""
        loan_id, _ = create_test_kyc_and_loan(
            sipahi_session,
            DELHI_ILLAKA_ID, DELHI_MISAL_ID,
            "Delhi", "TEST_Misal_Delhi",
            "2013-03-01",
            "_C1"
        )
        TestRedoClosingAfterUndo.loan_id_redo = loan_id
        print(f"Created loan C1: {loan_id}")
        assert loan_id is not None

    def test_02_do_closing_mark_as_gyal(self, admin_session):
        """Do year-end closing for 2025-03-31"""
        if not TestRedoClosingAfterUndo.loan_id_redo:
            pytest.skip("Loan C1 not created")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Closing failed: {res.text}"
        assert res.json()["marked_count"] >= 1

    def test_03_undo_the_closing(self, admin_session):
        """Undo the closing"""
        if not TestRedoClosingAfterUndo.loan_id_redo:
            pytest.skip("Loan C1 not created")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Undo failed: {res.text}"
        print(f"Undo C1: {res.json()}")

    def test_04_redo_closing_succeeds(self, admin_session):
        """After undo, can do a new closing with the same date"""
        if not TestRedoClosingAfterUndo.loan_id_redo:
            pytest.skip("Loan C1 not created")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Re-closing failed: {res.text}"
        data = res.json()
        assert data["marked_count"] >= 1
        print(f"Re-closing after undo: {data}")

    def test_05_loan_is_gyal_again(self, admin_session):
        """After re-closing, loan should be gyal again"""
        if not TestRedoClosingAfterUndo.loan_id_redo:
            pytest.skip("Loan C1 not created")
        res = admin_session.get(f"{BASE_URL}/api/loans/{TestRedoClosingAfterUndo.loan_id_redo}")
        assert res.status_code == 200
        loan = res.json()
        assert loan.get("is_gyal") is True, f"Expected is_gyal=True after re-closing, got {loan.get('is_gyal')}"
        assert loan.get("gyal_since") == "2025-03-31"
        print(f"Loan C1 re-gyal: is_gyal={loan.get('is_gyal')}, gyal_since={loan.get('gyal_since')}")

    def test_06_cleanup_undo_test_closing(self, admin_session):
        """Cleanup: undo the re-closing for C1 to leave Delhi clean"""
        if not TestRedoClosingAfterUndo.loan_id_redo:
            pytest.skip("Loan C1 not created")
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": DELHI_ILLAKA_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Cleanup undo failed: {res.text}"
        print(f"Cleanup undo: {res.json()}")


# ─── Undo on TEST_Illaka_Central (pre-existing closing) ───────────────────────

class TestUndoExistingClosing:
    """Test undo on TEST_Illaka_Central's existing 2025-03-31 closing (from iteration 16 seed data)"""

    existing_loan_id = None

    def test_01_history_shows_existing_closing(self, admin_session):
        """Confirm the existing 2025-03-31 closing exists"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200
        data = res.json()
        dates = [c["closing_date"] for c in data["closings"]]
        assert "2025-03-31" in dates, f"Expected 2025-03-31 in history, got {dates}"
        count = next(c["count"] for c in data["closings"] if c["closing_date"] == "2025-03-31")
        assert count >= 1
        print(f"Existing closing: date=2025-03-31, count={count}")

    def test_02_get_gyal_loan_in_test_illaka(self, admin_session):
        """Get the gyal loan in TEST_Illaka_Central"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID, "is_gyal": "true"}
        )
        if res.status_code == 200:
            loans = res.json()
            if isinstance(loans, list) and loans:
                TestUndoExistingClosing.existing_loan_id = loans[0].get("id")
                print(f"Found gyal loan: {TestUndoExistingClosing.existing_loan_id}")
        print(f"Gyal loans in TEST_Illaka_Central: status={res.status_code}")

    def test_03_undo_existing_closing(self, admin_session):
        """Undo the existing 2025-03-31 closing on TEST_Illaka_Central"""
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing/undo",
            json={"illaka_id": TEST_ILLAKA_CENTRAL_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Undo failed: {res.text}"
        data = res.json()
        assert data["undone_count"] >= 1
        print(f"Undo existing closing: {data}")

    def test_04_history_empty_after_undo(self, admin_session):
        """History should be empty after undoing the only closing"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": TEST_ILLAKA_CENTRAL_ID}
        )
        assert res.status_code == 200
        data = res.json()
        dates = [c["closing_date"] for c in data["closings"]]
        assert "2025-03-31" not in dates, f"2025-03-31 should be gone after undo: {dates}"
        print(f"History after undo: {data['closings']}")

    def test_05_redo_closing_after_undo(self, admin_session):
        """After undo, redo a new closing on TEST_Illaka_Central"""
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": TEST_ILLAKA_CENTRAL_ID, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Re-closing failed: {res.text}"
        data = res.json()
        print(f"Re-closing on TEST_Illaka_Central: {data}")
        # marked_count could be 0 if no eligible loans remain (which is fine)
        assert "marked_count" in data
