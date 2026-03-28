"""
Test suite for Bahi Khata NBFC-MFI backend refactoring.
Tests all key endpoints after server.py split into core/ + routes/ modules.
Focus: ensuring all APIs still work at same paths with /api prefix.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL env var not set")

ADMIN_EMAIL = "admin@bahikhata.com"
ADMIN_PASSWORD = "Admin@123"
SIPAHI_EMAIL = "TEST_sipahi_loans@bahikhata.com"
SIPAHI_PASSWORD = "Test@1234"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    """Admin session (cookie-based auth)."""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    """Sipahi session (cookie-based auth)."""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": SIPAHI_EMAIL, "password": SIPAHI_PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Sipahi login failed: {resp.text}")
    return s


# ─── Auth Routes (/api/auth/*) ────────────────────────────────────────────────

class TestAuthRoutes:
    """Tests for backend/routes/auth.py"""

    def test_admin_login_success(self):
        """POST /api/auth/login with admin credentials."""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "id" in data
        print(f"PASS: admin login — id={data['id']}, role={data['role']}")

    def test_sipahi_login_success(self):
        """POST /api/auth/login with sipahi credentials."""
        s = requests.Session()
        resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": SIPAHI_EMAIL, "password": SIPAHI_PASSWORD})
        if resp.status_code == 401:
            pytest.skip("Sipahi account not created yet")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["role"] == "sipahi"
        print(f"PASS: sipahi login — id={data['id']}, role={data['role']}")

    def test_login_invalid_credentials(self):
        """POST /api/auth/login with wrong password returns 401."""
        resp = requests.post(f"{BASE_URL}/api/auth/login",
                             json={"email": ADMIN_EMAIL, "password": "WrongPassword!"})
        assert resp.status_code == 401
        print("PASS: invalid credentials rejected with 401")

    def test_get_me_authenticated(self, admin_session):
        """GET /api/auth/me returns current user for authenticated session."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["role"] == "admin"
        assert "id" in data
        print(f"PASS: /auth/me returns role={data['role']}")

    def test_get_me_unauthenticated(self):
        """GET /api/auth/me returns 401 without cookie."""
        s = requests.Session()
        resp = s.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401
        print("PASS: /auth/me returns 401 without auth")

    def test_logout(self, admin_session):
        """POST /api/auth/logout returns 200."""
        # Use a new session for logout to not break admin_session
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        resp = s.post(f"{BASE_URL}/api/auth/logout")
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        print(f"PASS: logout returned: {data['message']}")


# ─── Dashboard Routes (/api/dashboard/*) ─────────────────────────────────────

class TestDashboardRoutes:
    """Tests for backend/routes/dashboard.py"""

    def test_dashboard_stats_admin(self, admin_session):
        """GET /api/dashboard/stats returns valid stats for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        required_keys = ["total", "pending", "approved", "rejected", "today",
                         "sipahi_count", "muneem_count", "active_loans", "total_loans"]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"
            assert isinstance(data[key], int), f"{key} should be int, got {type(data[key])}"
        assert data["total"] >= 0
        assert data["active_loans"] >= 0
        print(f"PASS: dashboard stats — total_kycs={data['total']}, active_loans={data['active_loans']}")

    def test_dashboard_stats_sipahi(self, sipahi_session):
        """GET /api/dashboard/stats returns valid stats for sipahi."""
        resp = sipahi_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total" in data
        print(f"PASS: sipahi dashboard stats — total_kycs={data['total']}")

    def test_dashboard_stats_unauthenticated(self):
        """GET /api/dashboard/stats returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 401
        print("PASS: /dashboard/stats returns 401 without auth")


# ─── Illaka Routes (/api/illakas, /api/misals) ────────────────────────────────

class TestIllakaRoutes:
    """Tests for backend/routes/illakas.py"""

    def test_list_illakas_admin(self, admin_session):
        """GET /api/illakas returns list for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /illakas returned {len(data)} illakas for admin")

    def test_list_illakas_sipahi(self, sipahi_session):
        """GET /api/illakas returns list for sipahi."""
        resp = sipahi_session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /illakas returned {len(data)} illakas for sipahi")

    def test_illaka_fields(self, admin_session):
        """Illakas have expected fields: id, name."""
        resp = admin_session.get(f"{BASE_URL}/api/illakas")
        data = resp.json()
        if data:
            illaka = data[0]
            assert "id" in illaka, "Illaka missing 'id' field"
            assert "name" in illaka, "Illaka missing 'name' field"
            assert "_id" not in illaka, "MongoDB _id exposed in response"
            print(f"PASS: illaka fields correct — id={illaka['id']}, name={illaka['name']}")

    def test_list_misals(self, admin_session):
        """GET /api/misals returns list."""
        resp = admin_session.get(f"{BASE_URL}/api/misals")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /misals returned {len(data)} misals")


# ─── KYC Routes (/api/kycs) ───────────────────────────────────────────────────

class TestKYCRoutes:
    """Tests for backend/routes/kycs.py"""

    def test_list_kycs_admin(self, admin_session):
        """GET /api/kycs returns paginated KYC list for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/kycs")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total" in data, "Missing 'total' key in KYC list response"
        assert "kycs" in data, "Missing 'kycs' key in KYC list response"
        assert isinstance(data["kycs"], list)
        assert isinstance(data["total"], int)
        print(f"PASS: GET /kycs — total={data['total']}, returned={len(data['kycs'])}")

    def test_list_kycs_sipahi(self, sipahi_session):
        """GET /api/kycs returns list for sipahi."""
        resp = sipahi_session.get(f"{BASE_URL}/api/kycs")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total" in data
        assert "kycs" in data
        print(f"PASS: sipahi GET /kycs — total={data['total']}")

    def test_kycs_pagination(self, admin_session):
        """GET /api/kycs with limit/skip parameters."""
        resp = admin_session.get(f"{BASE_URL}/api/kycs?limit=5&skip=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["kycs"]) <= 5
        print(f"PASS: /kycs?limit=5 returns {len(data['kycs'])} records")

    def test_kycs_no_mongodb_id(self, admin_session):
        """KYC records should not expose raw MongoDB _id."""
        resp = admin_session.get(f"{BASE_URL}/api/kycs?limit=1")
        data = resp.json()
        if data["kycs"]:
            kyc = data["kycs"][0]
            assert "_id" not in kyc, "MongoDB _id exposed in KYC response"
            assert "id" in kyc, "KYC missing 'id' field"
            print(f"PASS: KYC _id correctly converted — id={kyc['id']}")

    def test_list_kycs_unauthenticated(self):
        """GET /api/kycs returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/kycs")
        assert resp.status_code == 401
        print("PASS: /kycs returns 401 without auth")


# ─── Loan Routes (/api/loans) ─────────────────────────────────────────────────

class TestLoanRoutes:
    """Tests for backend/routes/loans.py"""

    def test_list_loans_admin(self, admin_session):
        """GET /api/loans returns paginated loan list for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/loans")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total" in data
        assert "loans" in data
        assert isinstance(data["loans"], list)
        print(f"PASS: GET /loans — total={data['total']}, returned={len(data['loans'])}")

    def test_list_loans_sipahi(self, sipahi_session):
        """GET /api/loans returns list for sipahi (filtered by sipahi_id or illaka)."""
        resp = sipahi_session.get(f"{BASE_URL}/api/loans")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "total" in data
        print(f"PASS: sipahi GET /loans — total={data['total']}")

    def test_loan_fields(self, admin_session):
        """Loan records have expected fields (loan_number may be None for old test data)."""
        resp = admin_session.get(f"{BASE_URL}/api/loans?limit=10")
        data = resp.json()
        if data["loans"]:
            # Use the first loan with an emi_schedule
            loan = data["loans"][0]
            # Fields that must exist (loan_number may be absent in old test data)
            required_fields = ["id", "client_name", "principal_amount", "emi_amount", "status", "emi_schedule"]
            for f in required_fields:
                assert f in loan, f"Loan missing field: {f}"
            assert "_id" not in loan, "MongoDB _id exposed in loan response"
            assert isinstance(loan["emi_schedule"], list)
            print(f"PASS: loan fields correct — status={loan['status']}, loan_number={loan.get('loan_number', 'N/A (old data)')}")

    def test_loans_kyc_id_filter(self, admin_session):
        """GET /api/loans?kyc_id= filters correctly."""
        # Get a loan to retrieve its kyc_id
        resp = admin_session.get(f"{BASE_URL}/api/loans?limit=1")
        data = resp.json()
        if not data["loans"]:
            pytest.skip("No loans available for kyc_id filter test")
        loan = data["loans"][0]
        kyc_id = loan.get("kyc_id")
        if not kyc_id:
            pytest.skip("First loan has no kyc_id")

        # Filter by kyc_id
        filtered_resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={kyc_id}")
        assert filtered_resp.status_code == 200
        filtered_data = filtered_resp.json()
        for l in filtered_data["loans"]:
            assert l["kyc_id"] == kyc_id, f"Loan kyc_id mismatch: expected {kyc_id}, got {l['kyc_id']}"
        print(f"PASS: /loans?kyc_id={kyc_id} returned {filtered_data['total']} loans, all matching")

    def test_get_specific_loan(self, admin_session):
        """GET /api/loans/{loan_id} returns single loan details."""
        # Get list first
        resp = admin_session.get(f"{BASE_URL}/api/loans?limit=1")
        data = resp.json()
        if not data["loans"]:
            pytest.skip("No loans to test single loan fetch")
        loan_id = data["loans"][0]["id"]

        # Get specific loan
        detail_resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert detail_resp.status_code == 200, f"Expected 200, got {detail_resp.status_code}"
        detail = detail_resp.json()
        assert detail["id"] == loan_id
        assert "emi_schedule" in detail
        assert isinstance(detail["emi_schedule"], list)
        print(f"PASS: GET /loans/{loan_id} — {len(detail['emi_schedule'])} EMI entries")

    def test_get_loan_not_found(self, admin_session):
        """GET /api/loans/{invalid_id} returns 404."""
        resp = admin_session.get(f"{BASE_URL}/api/loans/000000000000000000000000")
        assert resp.status_code == 404
        print("PASS: GET /loans/000000000000000000000000 returns 404")

    def test_list_loans_unauthenticated(self):
        """GET /api/loans returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/loans")
        assert resp.status_code == 401
        print("PASS: /loans returns 401 without auth")


# ─── EMI Note Endpoint (/api/loans/{id}/emi-note) ────────────────────────────

class TestEmiNoteEndpoint:
    """Tests for PATCH /api/loans/{loan_id}/emi-note endpoint."""

    def test_emi_note_update(self, admin_session):
        """PATCH /api/loans/{loan_id}/emi-note adds a note to an EMI."""
        # Get a loan with an EMI schedule
        resp = admin_session.get(f"{BASE_URL}/api/loans?limit=5")
        data = resp.json()

        loan_with_schedule = None
        for loan in data["loans"]:
            if loan.get("emi_schedule"):
                loan_with_schedule = loan
                break

        if not loan_with_schedule:
            pytest.skip("No loans with EMI schedule found")

        loan_id = loan_with_schedule["id"]
        first_emi = loan_with_schedule["emi_schedule"][0]
        emi_month = first_emi["due_month"]

        # Add a note
        note_text = "TEST_NOTE: Client will pay next week / TEST अगले हफ्ते"
        patch_resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/emi-note",
            json={"emi_month": emi_month, "note": note_text}
        )
        assert patch_resp.status_code == 200, f"Expected 200, got {patch_resp.status_code}: {patch_resp.text}"

        updated = patch_resp.json()
        # Verify note is in the response
        schedule = updated.get("emi_schedule", [])
        emi_item = next((e for e in schedule if e["due_month"] == emi_month), None)
        assert emi_item is not None, f"EMI {emi_month} not found in updated schedule"
        assert emi_item.get("note") == note_text, f"Note not updated: got {emi_item.get('note')}"
        print(f"PASS: PATCH /loans/{loan_id}/emi-note — note set for {emi_month}")

        # Verify persisted via GET
        get_resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        persisted_emi = next((e for e in get_data["emi_schedule"] if e["due_month"] == emi_month), None)
        assert persisted_emi is not None
        assert persisted_emi.get("note") == note_text, "Note not persisted after GET"
        print(f"PASS: Note persisted in DB — verified via GET")

        # Clean up: clear the note
        admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/emi-note",
            json={"emi_month": emi_month, "note": ""}
        )

    def test_emi_note_invalid_loan(self, admin_session):
        """PATCH /api/loans/invalid_id/emi-note returns 400 or 404."""
        resp = admin_session.patch(
            f"{BASE_URL}/api/loans/invalid_loan_id/emi-note",
            json={"emi_month": "2026-01", "note": "test"}
        )
        assert resp.status_code in [400, 404, 422], f"Expected 400/404/422, got {resp.status_code}"
        print(f"PASS: invalid loan id returns {resp.status_code}")

    def test_emi_note_invalid_month(self, admin_session):
        """PATCH /api/loans/{id}/emi-note with non-existent month returns 404."""
        resp = admin_session.get(f"{BASE_URL}/api/loans?limit=1")
        data = resp.json()
        if not data["loans"]:
            pytest.skip("No loans available")
        loan_id = data["loans"][0]["id"]

        # Use a month that won't exist in any loan schedule
        patch_resp = admin_session.patch(
            f"{BASE_URL}/api/loans/{loan_id}/emi-note",
            json={"emi_month": "1900-01", "note": "test"}
        )
        assert patch_resp.status_code == 404, f"Expected 404, got {patch_resp.status_code}"
        print(f"PASS: non-existent EMI month returns 404")


# ─── Collection Sheet (/api/collections/sheet) ───────────────────────────────

class TestCollectionRoutes:
    """Tests for backend/routes/collections.py"""

    def test_collection_sheet_admin(self, admin_session):
        """GET /api/collections/sheet returns grouped collection data."""
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "month" in data
        assert "total" in data
        assert "collected" in data
        assert "illakas" in data
        assert isinstance(data["illakas"], list)
        print(f"PASS: GET /collections/sheet — month={data['month']}, total={data['total']}")

    def test_collection_sheet_structure(self, admin_session):
        """Collection sheet has correct illaka → misal → rows structure."""
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet")
        data = resp.json()
        for illaka in data["illakas"]:
            assert "illaka_id" in illaka
            assert "illaka_name" in illaka
            assert "misals" in illaka
            for misal in illaka["misals"]:
                assert "misal_id" in misal
                assert "misal_name" in misal
                assert "rows" in misal
                for row in misal["rows"]:
                    assert "loan_db_id" in row
                    assert "loan_number" in row
                    assert "client_name" in row
                    assert "emi_amount" in row
                    assert "emi_status" in row
                    assert row["emi_status"] in ["paid", "pending", "overdue"]
        print(f"PASS: collection sheet structure correct — {len(data['illakas'])} illakas")

    def test_collection_sheet_with_month(self, admin_session):
        """GET /api/collections/sheet?month=YYYY-MM returns correct month."""
        month = "2026-02"
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet?month={month}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["month"] == month
        print(f"PASS: /collections/sheet?month={month} — total={data['total']}")

    def test_collection_sheet_sipahi(self, sipahi_session):
        """GET /api/collections/sheet returns filtered data for sipahi."""
        resp = sipahi_session.get(f"{BASE_URL}/api/collections/sheet")
        assert resp.status_code == 200
        data = resp.json()
        assert "illakas" in data
        print(f"PASS: sipahi collection sheet — total={data['total']}")

    def test_collection_sheet_unauthenticated(self):
        """GET /api/collections/sheet returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/collections/sheet")
        assert resp.status_code == 401
        print("PASS: /collections/sheet returns 401 without auth")


# ─── Users Routes (/api/users) ────────────────────────────────────────────────

class TestUsersRoutes:
    """Tests for backend/routes/users.py"""

    def test_list_users_admin(self, admin_session):
        """GET /api/users returns list for admin."""
        resp = admin_session.get(f"{BASE_URL}/api/users")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: GET /users returns {len(data)} users")

    def test_users_no_password_in_response(self, admin_session):
        """Users list should not expose password_hash."""
        resp = admin_session.get(f"{BASE_URL}/api/users")
        data = resp.json()
        if data:
            user = data[0]
            assert "password_hash" not in user, "password_hash exposed in /api/users response"
            assert "id" in user
            print(f"PASS: user fields correct — id={user['id']}, no password_hash exposed")

    def test_list_users_unauthenticated(self):
        """GET /api/users returns 401 without auth."""
        resp = requests.get(f"{BASE_URL}/api/users")
        assert resp.status_code == 401
        print("PASS: /users returns 401 without auth")
