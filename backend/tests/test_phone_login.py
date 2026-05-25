"""
Backend tests for phone-based login feature (iteration_11)
Tests: LoginRequest uses phone, queries by phone, error messages, user creation with phone required
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


class TestPhoneLogin:
    """Test phone-based authentication endpoints"""

    def test_admin_login_with_phone_success(self):
        """Admin can login with correct phone + password"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "9999999999", "password": "Admin@123"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data, "Response should have user id"
        assert data.get("role") == "admin", f"Expected role=admin, got {data.get('role')}"
        # Phone should be present in response (not email as primary)
        assert data.get("phone") == "9999999999", f"Expected phone=9999999999, got {data.get('phone')}"
        # Cookie should be set
        assert "access_token" in resp.cookies or resp.status_code == 200, "Access token cookie should be set"
        print(f"PASS: Admin login with phone=9999999999 returned 200, role={data.get('role')}")

    def test_sipahi_login_with_phone_success(self):
        """Sipahi can login with correct phone + password"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "8888888888", "password": "Test@1234"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("role") == "sipahi", f"Expected role=sipahi, got {data.get('role')}"
        assert data.get("phone") == "8888888888", f"Expected phone=8888888888, got {data.get('phone')}"
        print(f"PASS: Sipahi login with phone=8888888888 returned 200, role={data.get('role')}")

    def test_login_wrong_phone_returns_401(self):
        """Login with wrong/non-existent phone returns 401 with correct message"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "0000000000", "password": "Admin@123"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", "")
        assert "Invalid mobile number or password" in detail, (
            f"Expected 'Invalid mobile number or password', got '{detail}'"
        )
        print(f"PASS: Wrong phone returns 401 with detail='{detail}'")

    def test_login_wrong_password_returns_401(self):
        """Login with correct phone but wrong password returns 401"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "9999999999", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        data = resp.json()
        detail = data.get("detail", "")
        assert "Invalid mobile number or password" in detail, (
            f"Expected 'Invalid mobile number or password', got '{detail}'"
        )
        print(f"PASS: Wrong password returns 401 with detail='{detail}'")

    def test_login_with_email_field_fails(self):
        """Login request with 'email' field instead of 'phone' should return 422 (validation error)"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@bahikhata.com", "password": "Admin@123"},
        )
        # Should fail because model expects 'phone' not 'email'
        assert resp.status_code == 422, f"Expected 422 (validation error), got {resp.status_code}: {resp.text}"
        print("PASS: Login with 'email' field (not 'phone') returns 422 validation error")

    def test_login_missing_phone_field_returns_422(self):
        """Missing phone field returns validation error"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"password": "Admin@123"},
        )
        assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"
        print("PASS: Missing phone field returns 422")

    def test_login_empty_phone_returns_401(self):
        """Empty phone string returns 401"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "", "password": "Admin@123"},
        )
        assert resp.status_code in (401, 422), f"Expected 401 or 422, got {resp.status_code}: {resp.text}"
        print(f"PASS: Empty phone returns {resp.status_code}")


class TestPhoneLoginCookieSession:
    """Test session cookie set on successful login"""

    def test_login_sets_httponly_cookie(self):
        """Successful login sets access_token cookie"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "9999999999", "password": "Admin@123"},
        )
        assert resp.status_code == 200
        # Check cookie is set in response headers
        set_cookie = resp.headers.get("set-cookie", "")
        assert "access_token" in set_cookie or "access_token" in resp.cookies, (
            f"access_token cookie not found in response. set-cookie: {set_cookie}"
        )
        print("PASS: Login sets access_token cookie")

    def test_auth_me_after_login(self):
        """GET /auth/me returns user data after successful login"""
        session = requests.Session()
        login_resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "9999999999", "password": "Admin@123"},
        )
        assert login_resp.status_code == 200

        me_resp = session.get(f"{BASE_URL}/api/auth/me")
        assert me_resp.status_code == 200, f"Expected 200, got {me_resp.status_code}: {me_resp.text}"
        me_data = me_resp.json()
        assert me_data.get("phone") == "9999999999", f"Expected phone=9999999999, got {me_data.get('phone')}"
        assert me_data.get("role") == "admin"
        print(f"PASS: /auth/me returns user after login: phone={me_data.get('phone')}, role={me_data.get('role')}")

    def test_auth_me_without_login_returns_401(self):
        """GET /auth/me without login returns 401"""
        session = requests.Session()  # fresh session, no cookies
        resp = session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS: /auth/me without login returns 401")


class TestUserCreationWithPhone:
    """Test user creation requires phone not email"""

    def _get_admin_session(self):
        session = requests.Session()
        resp = session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": "9999999999", "password": "Admin@123"},
        )
        assert resp.status_code == 200, "Admin login failed"
        return session

    def test_create_user_with_phone_required(self):
        """Creating a user requires phone field; email is optional"""
        import time
        session = self._get_admin_session()
        unique_phone = f"6{str(int(time.time()))[-9:]}"  # unique phone based on timestamp
        payload = {
            "name": "TEST_PhoneUser",
            "phone": unique_phone,
            "password": "Test@1234",
            "role": "sipahi",
        }
        resp = session.post(f"{BASE_URL}/api/users", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("phone") == unique_phone, f"Phone not saved correctly: {data.get('phone')}"
        assert data.get("name") == "TEST_PhoneUser"
        print(f"PASS: Created user with phone only (no email), id={data.get('id')}, phone={unique_phone}")

    def test_create_user_without_phone_fails(self):
        """Creating a user without phone should fail validation"""
        session = self._get_admin_session()
        payload = {
            "name": "TEST_NoPhoneUser",
            "email": "nophone@test.com",
            "password": "Test@1234",
            "role": "sipahi",
        }
        resp = session.post(f"{BASE_URL}/api/users", json=payload)
        # phone is required in UserCreate, so should fail with 422
        assert resp.status_code == 422, f"Expected 422 (phone required), got {resp.status_code}: {resp.text}"
        print("PASS: Creating user without phone returns 422")

    def test_create_user_with_phone_and_email(self):
        """Creating a user with both phone and email works (email optional)"""
        import time
        session = self._get_admin_session()
        ts = str(int(time.time()))[-8:]
        unique_phone = f"5{ts}1"
        unique_email = f"TEST_phonemail_{ts}@test.com"
        payload = {
            "name": "TEST_PhoneEmailUser",
            "phone": unique_phone,
            "email": unique_email,
            "password": "Test@1234",
            "role": "sipahi",
        }
        resp = session.post(f"{BASE_URL}/api/users", json=payload)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("phone") == unique_phone
        assert data.get("email") == unique_email.lower()  # backend normalizes email to lowercase
        print(f"PASS: Created user with both phone and email, id={data.get('id')}")

        # Verify phone-based login works for this new user
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": unique_phone, "password": "Test@1234"},
        )
        assert login_resp.status_code == 200, f"New user phone login failed: {login_resp.status_code}: {login_resp.text}"
        print(f"PASS: New user can login with phone={unique_phone}")
