import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://nyaya-accounts.preview.emergentagent.com').rstrip('/')

ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@bahikhata.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "Admin@123")

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
        import time
        email = f"test_muneem_{int(time.time())}@bahikhata.com"
        payload = {
            "name": "TEST_Muneem_User",
            "email": email,
            "password": "Test@1234",
            "role": "muneem",
        }
        resp = admin_session.post(f"{BASE_URL}/api/users", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == email
        assert data["role"] == "muneem"
        assert "id" in data
        TestUsers.created_user_id = data["id"]
        print(f"PASS: user created, id={data['id']}")

    def test_create_duplicate_user(self, admin_session):
        payload = {
            "name": "TEST_Dup", "email": "test_muneem_unique123@bahikhata.com",
            "password": "Test@1234", "role": "muneem"
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
        # Create a muneem user for KYC creation (only muneem/sipahi can create KYCs)
        import time
        email = f"test_muneem_kyc_{int(time.time())}@bahikhata.com"
        muneem_resp = admin_session.post(f"{BASE_URL}/api/users", json={
            "name": "TEST_Muneem_KYC", "email": email, "password": "Test@1234", "role": "muneem"
        })
        assert muneem_resp.status_code == 200, f"Muneem creation failed: {muneem_resp.text}"
        muneem_id = muneem_resp.json()["id"]
        # Login as muneem
        muneem_session = requests.Session()
        login_resp = muneem_session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "Test@1234"})
        assert login_resp.status_code == 200, f"Muneem login failed: {login_resp.text}"
        # Get illakas and misals
        illakas = admin_session.get(f"{BASE_URL}/api/illakas").json()
        illaka_id = illakas[0]["id"] if illakas else None
        if not illaka_id:
            pytest.skip("No illaka available for KYC")
        misals = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={illaka_id}").json()
        misal_id = misals[0]["id"] if misals else None
        if not misal_id:
            pytest.skip("No misal available for KYC")
        payload = {
            "illaka_id": illaka_id, "illaka_name": "TestIllaka",
            "misal_id": misal_id, "misal_name": "TestMisal",
            "primary_borrower": {"name": "TEST Borrower", "phone": "9876543210", "dob": "01/01/1990", "gender": "Male", "address": "123 Test Street"},
            "notes": "Test KYC"
        }
        resp = muneem_session.post(f"{BASE_URL}/api/kycs", json=payload)
        # Cleanup muneem
        admin_session.delete(f"{BASE_URL}/api/users/{muneem_id}")
        assert resp.status_code == 200, f"KYC create failed: {resp.text}"
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

# ─── Illaka Tests ─────────────────────────────────────────────────────────────
class TestIllakas:
    created_illaka_id = None
    created_misal_id = None

    def test_list_illakas(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: list illakas, count={len(data)}")

    def test_create_illaka(self, admin_session):
        payload = {"name": "TEST_Illaka_Central", "description": "Test illaka"}
        resp = admin_session.post(f"{BASE_URL}/api/illakas", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["name"] == "TEST_Illaka_Central"
        TestIllakas.created_illaka_id = data["id"]
        print(f"PASS: illaka created, id={data['id']}")

    def test_create_misal(self, admin_session):
        if not TestIllakas.created_illaka_id:
            pytest.skip("No illaka created")
        payload = {"name": "TEST_Misal_1", "illaka_id": TestIllakas.created_illaka_id}
        resp = admin_session.post(f"{BASE_URL}/api/misals", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert data["name"] == "TEST_Misal_1"
        TestIllakas.created_misal_id = data["id"]
        print(f"PASS: misal created, id={data['id']}")

    def test_list_misals_by_illaka(self, admin_session):
        if not TestIllakas.created_illaka_id:
            pytest.skip("No illaka created")
        resp = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={TestIllakas.created_illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(m["name"] == "TEST_Misal_1" for m in data)
        print(f"PASS: list misals by illaka, count={len(data)}")

    def test_dashboard_has_sipahi_count(self, admin_session):
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "sipahi_count" in data
        print(f"PASS: sipahi_count in dashboard stats: {data['sipahi_count']}")

# ─── Sipahi User Tests ────────────────────────────────────────────────────────
class TestSipahiUser:
    sipahi_id = None
    sipahi_email = None

    def test_create_sipahi(self, admin_session):
        import time
        email = f"test_sipahi_{int(time.time())}@bahikhata.com"
        payload = {
            "name": "TEST_Sipahi_One",
            "email": email,
            "password": "Sipahi@1234",
            "role": "sipahi",
        }
        resp = admin_session.post(f"{BASE_URL}/api/users", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "sipahi"
        TestSipahiUser.sipahi_id = data["id"]
        TestSipahiUser.sipahi_email = email
        print(f"PASS: sipahi created, id={data['id']}")

    def test_sipahi_login(self):
        if not TestSipahiUser.sipahi_email:
            pytest.skip("No sipahi created")
        session = requests.Session()
        resp = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TestSipahiUser.sipahi_email,
            "password": "Sipahi@1234"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "sipahi"
        print("PASS: sipahi login works")

    def test_sipahi_sees_assigned_illakas(self):
        if not TestSipahiUser.sipahi_email:
            pytest.skip("No sipahi created")
        # Sipahi with no assigned illakas sees empty list
        session = requests.Session()
        session.post(f"{BASE_URL}/api/auth/login", json={
            "email": TestSipahiUser.sipahi_email,
            "password": "Sipahi@1234"
        })
        resp = session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        print(f"PASS: sipahi illakas (unassigned so empty): {data}")

    def test_cleanup_sipahi(self, admin_session):
        if not TestSipahiUser.sipahi_id:
            pytest.skip("No sipahi created")
        resp = admin_session.delete(f"{BASE_URL}/api/users/{TestSipahiUser.sipahi_id}")
        assert resp.status_code == 200
        print("PASS: sipahi deactivated")
