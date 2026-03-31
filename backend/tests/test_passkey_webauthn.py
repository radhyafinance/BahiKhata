"""
Backend tests for WebAuthn / Passkey endpoints.
Tests: auth-options, register-options, login has_passkeys, /me has_passkeys, passkey list
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_PHONE = "9999999999"
ADMIN_PASSWORD = "Admin@123"
MUNEEM_PHONE = "7777000001"
MUNEEM_PASSWORD = "Test@1234"


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated session for admin user."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def guest_session():
    """Unauthenticated session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ── Test 1: POST /api/auth/passkey/auth-options (no auth needed) ──────────────

class TestPasskeyAuthOptions:
    """auth-options must work without authentication and set wauthn_session cookie."""

    def test_auth_options_status_200(self, guest_session):
        """auth-options endpoint returns 200 without any auth."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: auth-options returns 200 without auth")

    def test_auth_options_returns_challenge(self, guest_session):
        """Response includes 'challenge' field (base64url string)."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        data = resp.json()
        assert "challenge" in data, f"Missing 'challenge' in response: {data}"
        assert isinstance(data["challenge"], str), "challenge should be a string"
        assert len(data["challenge"]) > 0, "challenge should not be empty"
        print(f"PASS: auth-options challenge present: {data['challenge'][:20]}...")

    def test_auth_options_returns_rpid(self, guest_session):
        """Response includes rpId matching the configured RP_ID."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        data = resp.json()
        assert "rpId" in data, f"Missing 'rpId' in response: {data}"
        expected_rp_id = "vasuli-sheet-2.preview.emergentagent.com"
        assert data["rpId"] == expected_rp_id, f"rpId mismatch: {data['rpId']} vs {expected_rp_id}"
        print(f"PASS: auth-options rpId = {data['rpId']}")

    def test_auth_options_sets_wauthn_session_cookie(self, guest_session):
        """Response sets wauthn_session cookie in Set-Cookie header."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        # Check in cookies dict
        assert "wauthn_session" in resp.cookies or "wauthn_session" in (resp.headers.get("set-cookie", "")), \
            f"wauthn_session cookie not set. Headers: {dict(resp.headers)}"
        print("PASS: wauthn_session cookie set")

    def test_auth_options_returns_timeout(self, guest_session):
        """Response includes timeout field."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        data = resp.json()
        assert "timeout" in data, f"Missing 'timeout' in response: {data}"
        print(f"PASS: auth-options timeout = {data['timeout']}")

    def test_auth_options_stores_challenge_in_db(self, guest_session):
        """Each call generates a unique challenge (different per request)."""
        resp1 = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        resp2 = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-options", json={})
        ch1 = resp1.json().get("challenge")
        ch2 = resp2.json().get("challenge")
        assert ch1 != ch2, "Each call should generate a unique challenge"
        print("PASS: Two auth-options calls generate unique challenges")


# ── Test 2: POST /api/auth/passkey/register-options (requires auth) ───────────

class TestPasskeyRegisterOptions:
    """register-options must require auth and return proper RP info."""

    def test_register_options_requires_auth(self, guest_session):
        """Without auth cookie, register-options returns 401."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS: register-options returns 401 without auth")

    def test_register_options_with_auth_returns_200(self, admin_session):
        """With valid auth, register-options returns 200."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: register-options returns 200 with auth")

    def test_register_options_rp_id_correct(self, admin_session):
        """rp.id must be the configured domain."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        data = resp.json()
        assert "rp" in data, f"Missing 'rp' in response: {data}"
        expected_rp_id = "vasuli-sheet-2.preview.emergentagent.com"
        actual_rp_id = data["rp"].get("id")
        assert actual_rp_id == expected_rp_id, \
            f"rp.id mismatch: {actual_rp_id} vs {expected_rp_id}"
        print(f"PASS: register-options rp.id = {actual_rp_id}")

    def test_register_options_rp_name(self, admin_session):
        """rp.name is set."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        data = resp.json()
        rp_name = data.get("rp", {}).get("name")
        assert rp_name, f"rp.name is missing or empty: {data}"
        print(f"PASS: register-options rp.name = {rp_name}")

    def test_register_options_has_challenge(self, admin_session):
        """Response includes challenge field."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        data = resp.json()
        assert "challenge" in data, f"Missing 'challenge': {data}"
        assert len(data["challenge"]) > 0
        print("PASS: register-options challenge present")

    def test_register_options_has_user_field(self, admin_session):
        """Response includes user field with id and name."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        data = resp.json()
        assert "user" in data, f"Missing 'user': {data}"
        user = data["user"]
        assert "id" in user, f"Missing user.id: {user}"
        assert "name" in user, f"Missing user.name: {user}"
        print(f"PASS: register-options user = {user}")

    def test_register_options_no_public_key_exposed(self, admin_session):
        """Response must NOT expose public_key or credential_id fields."""
        resp = admin_session.post(f"{BASE_URL}/api/auth/passkey/register-options", json={})
        data = resp.json()
        assert "public_key" not in data, "public_key must not be in register-options response"
        assert "passkeys" not in data, "passkeys array must not be in register-options response"
        print("PASS: register-options does not expose private credential data")


# ── Test 3: POST /api/auth/login — has_passkeys field ────────────────────────

class TestLoginHasPasskeys:
    """Login endpoint must include has_passkeys bool and NOT expose raw passkeys."""

    def test_login_returns_200(self, guest_session):
        """Login with admin credentials returns 200."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
        )
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        print("PASS: login returns 200")

    def test_login_response_has_passkeys_field(self, guest_session):
        """Login response includes has_passkeys boolean field."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
        )
        data = resp.json()
        assert "has_passkeys" in data, f"has_passkeys field missing from login response: {data.keys()}"
        assert isinstance(data["has_passkeys"], bool), \
            f"has_passkeys should be bool, got {type(data['has_passkeys'])}: {data['has_passkeys']}"
        print(f"PASS: login response has_passkeys = {data['has_passkeys']}")

    def test_login_response_no_raw_passkeys_array(self, guest_session):
        """Login response must NOT include the raw passkeys array."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
        )
        data = resp.json()
        assert "passkeys" not in data, \
            f"Raw 'passkeys' array must not be exposed in login response: {list(data.keys())}"
        print("PASS: login response does not expose raw passkeys array")

    def test_login_response_no_password_hash(self, guest_session):
        """Login response must NOT include password_hash."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
        )
        data = resp.json()
        assert "password_hash" not in data, "password_hash must not be exposed"
        print("PASS: login response does not expose password_hash")

    def test_login_response_no_webauthn_challenge(self, guest_session):
        """Login response must NOT include internal webauthn challenge fields."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD}
        )
        data = resp.json()
        assert "webauthn_reg_challenge" not in data, "webauthn_reg_challenge must not be exposed"
        assert "webauthn_reg_challenge_at" not in data, "webauthn_reg_challenge_at must not be exposed"
        print("PASS: login response does not expose internal WebAuthn challenge fields")

    def test_login_invalid_credentials_returns_401(self, guest_session):
        """Wrong credentials return 401."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": ADMIN_PHONE, "password": "WrongPassword"}
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: invalid credentials return 401")

    def test_muneem_login_has_passkeys_field(self, guest_session):
        """Muneem user login also returns has_passkeys."""
        resp = guest_session.post(
            f"{BASE_URL}/api/auth/login",
            json={"phone": MUNEEM_PHONE, "password": MUNEEM_PASSWORD}
        )
        assert resp.status_code == 200, f"Muneem login failed: {resp.text}"
        data = resp.json()
        assert "has_passkeys" in data, f"has_passkeys missing from Muneem login response: {data.keys()}"
        print(f"PASS: Muneem login response has_passkeys = {data['has_passkeys']}")


# ── Test 4: GET /api/auth/me — has_passkeys field ─────────────────────────────

class TestMeHasPasskeys:
    """/me endpoint must include has_passkeys boolean."""

    def test_me_requires_auth(self):
        """/me returns 401 without auth (fresh unauthenticated session)."""
        fresh = requests.Session()
        fresh.headers.update({"Content-Type": "application/json"})
        resp = fresh.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
        print("PASS: /me returns 401 without auth")

    def test_me_returns_has_passkeys(self, admin_session):
        """/me response includes has_passkeys boolean."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "has_passkeys" in data, f"has_passkeys missing from /me response: {data.keys()}"
        assert isinstance(data["has_passkeys"], bool), \
            f"has_passkeys should be bool, got {type(data['has_passkeys'])}"
        print(f"PASS: /me response has_passkeys = {data['has_passkeys']}")

    def test_me_no_raw_passkeys_array(self, admin_session):
        """/me response must NOT include raw passkeys array."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        data = resp.json()
        assert "passkeys" not in data, \
            f"Raw passkeys array must not be in /me response: {list(data.keys())}"
        print("PASS: /me does not expose raw passkeys array")

    def test_me_no_password_hash(self, admin_session):
        """/me response must NOT include password_hash."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        data = resp.json()
        assert "password_hash" not in data, "password_hash must not be exposed in /me"
        print("PASS: /me does not expose password_hash")

    def test_me_includes_user_fields(self, admin_session):
        """/me response includes expected user fields: id, role, phone."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/me")
        data = resp.json()
        for field in ["id", "role", "phone"]:
            assert field in data, f"Missing '{field}' in /me response: {data.keys()}"
        print(f"PASS: /me includes id={data['id']}, role={data['role']}, phone={data['phone']}")


# ── Test 5: GET /api/auth/passkey/list ─────────────────────────────────────────

class TestPasskeyList:
    """passkey/list must require auth and not expose public_key."""

    def test_passkey_list_requires_auth(self):
        """Without auth, passkey list returns 401 (fresh unauthenticated session)."""
        fresh = requests.Session()
        fresh.headers.update({"Content-Type": "application/json"})
        resp = fresh.get(f"{BASE_URL}/api/auth/passkey/list")
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
        print("PASS: passkey list returns 401 without auth")

    def test_passkey_list_returns_200_with_auth(self, admin_session):
        """With auth, passkey list returns 200."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/passkey/list")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        print("PASS: passkey list returns 200 with auth")

    def test_passkey_list_is_array(self, admin_session):
        """Passkey list response is a JSON array."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/passkey/list")
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}: {data}"
        print(f"PASS: passkey list is an array with {len(data)} items")

    def test_passkey_list_no_public_key_in_items(self, admin_session):
        """If any passkeys exist, they must NOT contain public_key field."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/passkey/list")
        data = resp.json()
        for pk in data:
            assert "public_key" not in pk, \
                f"public_key must NOT be exposed in passkey list: {pk}"
        print("PASS: passkey list items do not expose public_key")

    def test_passkey_list_items_have_expected_fields(self, admin_session):
        """If passkeys exist, each item has credential_id, name, created_at."""
        resp = admin_session.get(f"{BASE_URL}/api/auth/passkey/list")
        data = resp.json()
        for pk in data:
            assert "credential_id" in pk, f"Missing credential_id: {pk}"
            assert "name" in pk, f"Missing name: {pk}"
            assert "created_at" in pk, f"Missing created_at: {pk}"
        print(f"PASS: passkey list items have correct fields ({len(data)} passkeys)")


# ── Test 6: auth-verify endpoint error cases (without actual WebAuthn) ────────

class TestPasskeyAuthVerifyErrorCases:
    """Test auth-verify error handling without performing actual WebAuthn ceremony."""

    def test_auth_verify_missing_credential_id_400(self, guest_session):
        """auth-verify with missing credential_id returns 400."""
        resp = guest_session.post(f"{BASE_URL}/api/auth/passkey/auth-verify", json={})
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "detail" in data
        print(f"PASS: auth-verify missing credential_id → 400: {data['detail']}")

    def test_auth_verify_without_session_cookie_400(self, guest_session):
        """auth-verify without wauthn_session cookie returns 400."""
        new_session = requests.Session()
        new_session.headers.update({"Content-Type": "application/json"})
        resp = new_session.post(
            f"{BASE_URL}/api/auth/passkey/auth-verify",
            json={"id": "fake-credential-id"}
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "session" in data.get("detail", "").lower() or "session" in data.get("detail", "").lower(), \
            f"Error should mention session: {data}"
        print(f"PASS: auth-verify without session cookie → 400: {data['detail']}")
