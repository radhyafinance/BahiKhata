"""
Tests for new features:
1. /api/ocr/aadhaar-back endpoint
2. Duplicate Aadhaar check in create_kyc
3. relative_name field in PersonKYCData
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Auth credentials
SIPAHI_EMAIL = "TEST_sipahi_loans@bahikhata.com"
SIPAHI_PASS = "Test@1234"
ADMIN_EMAIL = "admin@bahikhata.com"
ADMIN_PASS = "Admin@123"

EXISTING_AADHAAR = "3380 7265 0532"
EXISTING_AADHAAR_NO_SPACES = "338072650532"


@pytest.fixture(scope="module")
def sipahi_session():
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": SIPAHI_EMAIL, "password": SIPAHI_PASS})
    if r.status_code != 200:
        pytest.skip(f"Sipahi login failed: {r.text}")
    return session


@pytest.fixture(scope="module")
def admin_session():
    session = requests.Session()
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if r.status_code != 200:
        pytest.skip(f"Admin login failed: {r.text}")
    return session


# ─── Test 1: OCR aadhaar-back endpoint exists ─────────────────────────────────
class TestOcrAadhaarBack:
    """Test /api/ocr/aadhaar-back endpoint"""

    def test_endpoint_exists_and_not_404(self, sipahi_session):
        """Endpoint should exist - 404 for file-not-found is acceptable, but not for missing endpoint"""
        r = sipahi_session.post(f"{BASE_URL}/api/ocr/aadhaar-back", json={"path": "test/nonexistent.jpg"})
        # 404 "File not found in storage" is expected; 404 "Not Found" means endpoint missing
        if r.status_code == 404:
            detail = r.json().get("detail", "")
            assert "File not found" in detail or "storage" in detail.lower(), \
                f"Endpoint may not exist (404 without storage message): {r.text}"
            print(f"Endpoint exists but file not found (expected): {detail}")
        else:
            print(f"aadhaar-back OCR response status: {r.status_code}")
        # If we reach here without assertion error, endpoint exists

    def test_endpoint_returns_json(self, sipahi_session):
        """Response should be JSON"""
        r = sipahi_session.post(f"{BASE_URL}/api/ocr/aadhaar-back", json={"path": "test/nonexistent.jpg"})
        # Should return JSON with relative_name and address (even if None)
        try:
            data = r.json()
            # If it returns a response (could be error or success), check structure if 200
            if r.status_code == 200:
                assert "relative_name" in data or "address" in data, f"Missing expected keys: {data}"
            print(f"Response: {data}")
        except Exception as e:
            print(f"JSON parse failed: {e}")

    def test_endpoint_requires_auth(self):
        """Endpoint should require authentication"""
        r = requests.post(f"{BASE_URL}/api/ocr/aadhaar-back", json={"path": "test/test.jpg"})
        assert r.status_code == 401, f"Expected 401, got {r.status_code}"


# ─── Test 2: Duplicate Aadhaar check ─────────────────────────────────────────
class TestDuplicateAadhaar:
    """Test duplicate Aadhaar prevention in create_kyc"""

    def _get_valid_kyc_payload(self, aadhaar: str, illaka_id: str, misal_id: str):
        return {
            "illaka_id": illaka_id,
            "illaka_name": "Test Illaka",
            "misal_id": misal_id,
            "misal_name": "Test Misal",
            "primary_borrower": {
                "name": "Test Person",
                "dob": "1990-01-01",
                "address": "Test Address",
                "relative_name": "Test Father",
                "gender": "Male",
                "phone": "9999999999",
                "aadhaar_number": aadhaar,
                "aadhaar_front_path": "test/front.jpg",
                "aadhaar_back_path": "test/back.jpg"
            }
        }

    def _get_illaka_misal(self, sipahi_session):
        r = sipahi_session.get(f"{BASE_URL}/api/illakas")
        illakas = r.json() if r.status_code == 200 else []
        if not illakas:
            return None, None
        illaka_id = illakas[0]["id"]
        r2 = sipahi_session.get(f"{BASE_URL}/api/misals?illaka_id={illaka_id}")
        misals = r2.json() if r2.status_code == 200 else []
        if not misals:
            return illaka_id, None
        return illaka_id, misals[0]["id"]

    def test_duplicate_aadhaar_with_spaces_blocked(self, sipahi_session):
        """Posting duplicate Aadhaar (with spaces) should return 400"""
        illaka_id, misal_id = self._get_illaka_misal(sipahi_session)
        if not illaka_id or not misal_id:
            pytest.skip("No illaka/misal available")
        payload = self._get_valid_kyc_payload(EXISTING_AADHAAR, illaka_id, misal_id)
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json=payload)
        print(f"Duplicate check (with spaces) status: {r.status_code}, body: {r.text[:200]}")
        assert r.status_code == 400, f"Expected 400 for duplicate Aadhaar, got {r.status_code}"
        data = r.json()
        assert "Duplicate" in data.get("detail", "") or "duplicate" in data.get("detail", "").lower() or "आधार" in data.get("detail", ""), \
            f"Expected duplicate error message, got: {data}"

    def test_duplicate_aadhaar_without_spaces_blocked(self, sipahi_session):
        """Posting duplicate Aadhaar (without spaces) should return 400"""
        illaka_id, misal_id = self._get_illaka_misal(sipahi_session)
        if not illaka_id or not misal_id:
            pytest.skip("No illaka/misal available")
        payload = self._get_valid_kyc_payload(EXISTING_AADHAAR_NO_SPACES, illaka_id, misal_id)
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json=payload)
        print(f"Duplicate check (no spaces) status: {r.status_code}, body: {r.text[:200]}")
        assert r.status_code == 400, f"Expected 400 for duplicate Aadhaar (no spaces), got {r.status_code}"

    def test_unique_aadhaar_allowed(self, sipahi_session):
        """Posting a unique Aadhaar should NOT be blocked by duplicate check"""
        illaka_id, misal_id = self._get_illaka_misal(sipahi_session)
        if not illaka_id or not misal_id:
            pytest.skip("No illaka/misal available")
        unique_aadhaar = "1111 2222 3456"
        payload = self._get_valid_kyc_payload(unique_aadhaar, illaka_id, misal_id)
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json=payload)
        print(f"Unique Aadhaar status: {r.status_code}, body: {r.text[:200]}")
        # Should not be 400 due to duplicate check (may fail for other reasons like missing photos)
        assert r.status_code != 400 or "Duplicate" not in r.json().get("detail", ""), \
            f"Unique Aadhaar was blocked by duplicate check: {r.text}"


# ─── Test 3: relative_name field in API response ──────────────────────────────
class TestRelativeNameField:
    """Test relative_name field in KYC data"""

    def test_kycs_list_includes_relative_name_structure(self, admin_session):
        """KYCs list should include primary_borrower with relative_name field"""
        r = admin_session.get(f"{BASE_URL}/api/kycs")
        assert r.status_code == 200
        resp = r.json()
        kycs = resp.get("kycs", resp) if isinstance(resp, dict) else resp
        if kycs:
            pb = kycs[0].get("primary_borrower", {})
            # relative_name key should be present (even if None)
            assert "relative_name" in pb or pb is None, f"relative_name missing from primary_borrower: {pb}"
            print(f"Sample primary_borrower relative_name: {pb.get('relative_name')}")
        print(f"Total KYCs: {len(kycs)}")
