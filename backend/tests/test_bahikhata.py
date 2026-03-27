import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lending-kyc.preview.emergentagent.com').rstrip('/')

ADMIN_EMAIL = "admin@bahikhata.com"
ADMIN_PASSWORD = "Admin@123"

@pytest.fixture(scope="module")
def admin_session():
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session

# ─── Auth Tests ───────────────────────────────────────────────────────────────
class TestAuth:
    def test_login_success(self):
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"
        assert "id" in data
        print(f"PASS: login success, user id={data['id']}")

    def test_login_invalid_credentials(self):
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrongpass"})
        assert resp.status_code == 401
        print("PASS: invalid credentials rejected")

    def test_get_me(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"
        print(f"PASS: /auth/me returns role={data['role']}")

    def test_logout(self):
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        resp = session.post(f"{BASE_URL}/api/auth/logout")
        assert resp.status_code == 200
        print("PASS: logout success")

# ─── Dashboard Tests ──────────────────────────────────────────────────────────
class TestDashboard:
    def test_dashboard_stats(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        for key in ["total", "pending", "approved", "rejected", "today"]:
            assert key in data, f"Missing key: {key}"
        print(f"PASS: dashboard stats: {data}")

    def test_dashboard_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 401
        print("PASS: dashboard requires auth")

# ─── User Tests ───────────────────────────────────────────────────────────────
class TestUsers:
    created_user_id = None

    def test_list_users(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/users")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        print(f"PASS: list users, count={len(data)}")

    def test_create_user(self, admin_session):
        payload = {
            "name": "TEST_Field Officer",
            "email": "test_fo_unique123@bahikhata.com",
            "password": "Test@1234",
            "role": "field_officer",
            "branch": "TestBranch"
        }
        resp = admin_session.post(f"{BASE_URL}/api/users", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == payload["email"]
        assert data["role"] == "field_officer"
        assert "id" in data
        TestUsers.created_user_id = data["id"]
        print(f"PASS: user created, id={data['id']}")

    def test_create_duplicate_user(self, admin_session):
        payload = {
            "name": "TEST_Dup", "email": "test_fo_unique123@bahikhata.com",
            "password": "Test@1234", "role": "field_officer"
        }
        resp = admin_session.post(f"{BASE_URL}/api/users", json=payload)
        assert resp.status_code == 400
        print("PASS: duplicate email rejected")

    def test_deactivate_user(self, admin_session):
        if not TestUsers.created_user_id:
            pytest.skip("No test user created")
        resp = admin_session.delete(f"{BASE_URL}/api/users/{TestUsers.created_user_id}")
        assert resp.status_code == 200
        print("PASS: user deactivated")

# ─── KYC Tests ───────────────────────────────────────────────────────────────
class TestKYC:
    created_kyc_id = None

    def test_list_kycs(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/kycs")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "kycs" in data
        assert isinstance(data["kycs"], list)
        print(f"PASS: list kycs, total={data['total']}")

    def test_create_kyc(self, admin_session):
        payload = {
            "primary_borrower": {
                "name": "TEST Borrower",
                "phone": "9876543210",
                "dob": "01/01/1990",
                "gender": "Male",
                "address": "123 Test Street"
            },
            "notes": "Test KYC",
            "branch": "TestBranch"
        }
        resp = admin_session.post(f"{BASE_URL}/api/kycs", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert "kyc_number" in data
        TestKYC.created_kyc_id = data["id"]
        print(f"PASS: KYC created, kyc_number={data['kyc_number']}")

    def test_get_kyc(self, admin_session):
        if not TestKYC.created_kyc_id:
            pytest.skip("No test KYC created")
        resp = admin_session.get(f"{BASE_URL}/api/kycs/{TestKYC.created_kyc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == TestKYC.created_kyc_id
        print("PASS: get KYC by id")

    def test_update_kyc_status(self, admin_session):
        if not TestKYC.created_kyc_id:
            pytest.skip("No test KYC created")
        resp = admin_session.patch(
            f"{BASE_URL}/api/kycs/{TestKYC.created_kyc_id}/status",
            json={"status": "approved", "notes": "Approved in test"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        print("PASS: KYC status updated to approved")
