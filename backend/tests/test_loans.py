"""
Loan Tracking Module - Backend API Tests
Tests for /api/loans, /api/loans/{id}/payments, and dashboard loan stats
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://collection-mfi.preview.emergentagent.com').rstrip('/')

ADMIN_EMAIL = "admin@bahikhata.com"
ADMIN_PASSWORD = "Admin@123"

# We'll create a sipahi user for loan creation tests
TEST_SIPAHI_EMAIL = "TEST_sipahi_loans@bahikhata.com"
TEST_SIPAHI_PASSWORD = "Test@1234"
TEST_MUNEEM_EMAIL = "TEST_muneem_loans@bahikhata.com"
TEST_MUNEEM_PASSWORD = "Test@1234"


@pytest.fixture(scope="module")
def admin_session():
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def sipahi_session(admin_session):
    """Create a sipahi test user and return their session"""
    # Check if already exists, create if not
    users_resp = admin_session.get(f"{BASE_URL}/api/users")
    existing = None
    if users_resp.status_code == 200:
        users_data = users_resp.json()
        users_list = users_data if isinstance(users_data, list) else users_data.get("users", [])
        for u in users_list:
            if u.get("email") == TEST_SIPAHI_EMAIL:
                existing = u
                break

    if not existing:
        # Get an illaka to assign
        illakas_resp = admin_session.get(f"{BASE_URL}/api/illakas")
        illaka_id = None
        if illakas_resp.status_code == 200:
            illakas_data = illakas_resp.json()
            illakas_list = illakas_data if isinstance(illakas_data, list) else illakas_data.get("illakas", [])
            if illakas_list:
                illaka_id = illakas_list[0]["id"]

        create_resp = admin_session.post(f"{BASE_URL}/api/users", json={
            "name": "TEST Sipahi Loans",
            "email": TEST_SIPAHI_EMAIL,
            "password": TEST_SIPAHI_PASSWORD,
            "role": "sipahi",
            "assigned_illaka_ids": [illaka_id] if illaka_id else []
        })
        if create_resp.status_code not in [200, 201]:
            pytest.skip(f"Could not create sipahi test user: {create_resp.text}")

    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_SIPAHI_EMAIL, "password": TEST_SIPAHI_PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Sipahi login failed: {resp.text}")
    return session


@pytest.fixture(scope="module")
def first_kyc_id(admin_session):
    """Get a real KYC id for loan creation"""
    resp = admin_session.get(f"{BASE_URL}/api/kycs?limit=1")
    if resp.status_code == 200 and resp.json().get("kycs"):
        kyc = resp.json()["kycs"][0]
        return kyc
    pytest.skip("No KYC records found to test loan creation")


@pytest.fixture(scope="module")
def created_loan(sipahi_session, first_kyc_id):
    """Create a test loan and return it"""
    kyc = first_kyc_id
    payload = {
        "kyc_id": kyc["id"],
        "client_name": kyc.get("primary_borrower", {}).get("name", "TEST Client"),
        "client_phone": kyc.get("primary_borrower", {}).get("phone", ""),
        "illaka_id": kyc.get("illaka_id", ""),
        "illaka_name": kyc.get("illaka_name", "TEST Illaka"),
        "misal_id": kyc.get("misal_id", ""),
        "misal_name": kyc.get("misal_name", "TEST Misal"),
        "principal_amount": 10000.0,
        "interest_rate": 2.5,
        "loan_date": "2026-01-15",
        "due_date": "2026-07-15",
        "notes": "TEST loan for automated testing"
    }
    resp = sipahi_session.post(f"{BASE_URL}/api/loans", json=payload)
    assert resp.status_code == 200, f"Loan creation failed: {resp.text}"
    data = resp.json()
    assert "id" in data
    return data


# ─── Loan CRUD Tests ─────────────────────────────────────────────────────────
class TestLoanCRUD:
    """Test loan creation, listing, and retrieval"""

    def test_admin_cannot_create_loan(self, admin_session, first_kyc_id):
        """Admin should get 403 when creating loans"""
        kyc = first_kyc_id
        payload = {
            "kyc_id": kyc["id"],
            "client_name": "TEST Client",
            "client_phone": "",
            "illaka_id": kyc.get("illaka_id", "test"),
            "illaka_name": "Test Illaka",
            "misal_id": kyc.get("misal_id", "test"),
            "misal_name": "Test Misal",
            "principal_amount": 5000.0,
            "interest_rate": 2.0,
            "loan_date": "2026-01-01",
        }
        resp = admin_session.post(f"{BASE_URL}/api/loans", json=payload)
        assert resp.status_code == 403, f"Expected 403 for admin, got {resp.status_code}: {resp.text}"
        print("PASS: Admin correctly gets 403 when creating loans")

    def test_sipahi_can_create_loan(self, created_loan):
        """Sipahi should be able to create a loan"""
        assert created_loan["id"]
        assert created_loan["principal_amount"] == 10000.0
        assert created_loan["interest_rate"] == 2.5
        assert created_loan["status"] == "active"
        assert created_loan["total_paid"] == 0.0
        print(f"PASS: Sipahi created loan id={created_loan['id']}")

    def test_list_loans_admin(self, admin_session):
        """Admin should be able to list loans"""
        resp = admin_session.get(f"{BASE_URL}/api/loans")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "loans" in data
        assert isinstance(data["loans"], list)
        print(f"PASS: Admin list loans total={data['total']}")

    def test_list_loans_with_status_filter(self, admin_session):
        """Filter loans by status"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?status=active")
        assert resp.status_code == 200
        data = resp.json()
        for loan in data["loans"]:
            assert loan["status"] == "active"
        print(f"PASS: Status filter works, {len(data['loans'])} active loans")

    def test_list_loans_with_search(self, admin_session, created_loan):
        """Search loans by client name"""
        name = created_loan["client_name"]
        resp = admin_session.get(f"{BASE_URL}/api/loans?search={name[:4]}")
        assert resp.status_code == 200
        data = resp.json()
        assert "loans" in data
        print(f"PASS: Search filter works, {data['total']} results for '{name[:4]}'")

    def test_get_loan_by_id(self, admin_session, created_loan):
        """Get specific loan by ID"""
        loan_id = created_loan["id"]
        resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == loan_id
        assert data["principal_amount"] == 10000.0
        print(f"PASS: Get loan by id={loan_id}")

    def test_get_loan_not_found(self, admin_session):
        """404 for invalid loan ID"""
        resp = admin_session.get(f"{BASE_URL}/api/loans/000000000000000000000000")
        assert resp.status_code == 404
        print("PASS: 404 for non-existent loan")

    def test_dashboard_has_loan_stats(self, admin_session):
        """Dashboard stats should include active_loans and total_loans"""
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_loans" in data
        assert "total_loans" in data
        assert isinstance(data["active_loans"], int)
        assert isinstance(data["total_loans"], int)
        print(f"PASS: Dashboard has loan stats: active={data['active_loans']}, total={data['total_loans']}")


class TestLoanStatus:
    """Test loan status update"""

    def test_admin_can_update_status(self, admin_session, created_loan):
        """Admin should be able to update loan status"""
        loan_id = created_loan["id"]
        resp = admin_session.patch(f"{BASE_URL}/api/loans/{loan_id}/status", json={"status": "overdue"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "overdue"
        print("PASS: Admin updated status to overdue")

        # Reset to active
        resp2 = admin_session.patch(f"{BASE_URL}/api/loans/{loan_id}/status", json={"status": "active"})
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "active"
        print("PASS: Admin reset status to active")

    def test_sipahi_cannot_update_status(self, sipahi_session, created_loan):
        """Sipahi should get 403 when updating status"""
        loan_id = created_loan["id"]
        resp = sipahi_session.patch(f"{BASE_URL}/api/loans/{loan_id}/status", json={"status": "closed"})
        assert resp.status_code == 403
        print("PASS: Sipahi gets 403 for status update")

    def test_invalid_status_rejected(self, admin_session, created_loan):
        """Invalid status should return 400"""
        loan_id = created_loan["id"]
        resp = admin_session.patch(f"{BASE_URL}/api/loans/{loan_id}/status", json={"status": "invalid_status"})
        assert resp.status_code == 400
        print("PASS: Invalid status returns 400")


class TestPayments:
    """Test payment recording, listing, deletion"""

    def test_add_payment(self, sipahi_session, created_loan):
        """Add payment to a loan"""
        loan_id = created_loan["id"]
        resp = sipahi_session.post(f"{BASE_URL}/api/loans/{loan_id}/payments", json={
            "amount": 2000.0,
            "payment_date": "2026-02-01",
            "notes": "TEST payment"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["amount"] == 2000.0
        assert data["loan_id"] == loan_id
        assert "id" in data
        print(f"PASS: Payment added id={data['id']}")

    def test_total_paid_updates_after_payment(self, sipahi_session, admin_session, created_loan):
        """Total paid on loan should update after adding payment"""
        loan_id = created_loan["id"]
        # Add another payment
        sipahi_session.post(f"{BASE_URL}/api/loans/{loan_id}/payments", json={
            "amount": 1000.0,
            "payment_date": "2026-02-15",
        })
        # Check loan total_paid
        resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_paid"] >= 2000.0  # At least the first payment
        print(f"PASS: total_paid updated to {data['total_paid']}")

    def test_list_payments(self, admin_session, created_loan):
        """List payments for a loan"""
        loan_id = created_loan["id"]
        resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}/payments")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"PASS: Listed {len(data)} payments for loan")

    def test_delete_payment_by_admin(self, admin_session, created_loan):
        """Admin can delete a payment"""
        loan_id = created_loan["id"]
        # Get payments list
        payments_resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}/payments")
        payments = payments_resp.json()
        if not payments:
            pytest.skip("No payments to delete")

        pid = payments[-1]["id"]  # Delete last payment
        loan_before = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}").json()

        resp = admin_session.delete(f"{BASE_URL}/api/loans/{loan_id}/payments/{pid}")
        assert resp.status_code == 200

        # Verify total_paid recalculated
        loan_after = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}").json()
        assert loan_after["total_paid"] < loan_before["total_paid"] or loan_after["total_paid"] == loan_before["total_paid"] - payments[-1]["amount"]
        print(f"PASS: Payment deleted, total_paid went from {loan_before['total_paid']} to {loan_after['total_paid']}")

    def test_sipahi_cannot_delete_payment(self, sipahi_session, admin_session, created_loan):
        """Sipahi cannot delete payments (403)"""
        loan_id = created_loan["id"]
        # First add a payment
        add_resp = sipahi_session.post(f"{BASE_URL}/api/loans/{loan_id}/payments", json={
            "amount": 500.0, "payment_date": "2026-02-20"
        })
        if add_resp.status_code != 200:
            pytest.skip("Could not add payment for test")
        pid = add_resp.json()["id"]

        resp = sipahi_session.delete(f"{BASE_URL}/api/loans/{loan_id}/payments/{pid}")
        assert resp.status_code == 403
        print("PASS: Sipahi gets 403 for deleting payment")


class TestKYCSearch:
    """Test KYC search for loan form"""

    def test_kyc_search_by_name(self, admin_session):
        """Search KYCs by name - used by loan form"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs?search=Arti&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "kycs" in data
        print(f"PASS: KYC search returned {len(data['kycs'])} results for 'Arti'")

    def test_kyc_search_returns_fields_for_loan(self, admin_session):
        """KYC search results should have fields needed for loan form"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs?limit=1")
        assert resp.status_code == 200
        kycs = resp.json().get("kycs", [])
        if not kycs:
            pytest.skip("No KYCs available")
        kyc = kycs[0]
        assert "id" in kyc
        assert "primary_borrower" in kyc
        assert "illaka_id" in kyc
        assert "misal_id" in kyc
        print(f"PASS: KYC has required fields for loan form")
