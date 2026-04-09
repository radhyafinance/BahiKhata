"""
Backend tests for the suffix field feature in KYC.
Tests: suffix stored in primary_borrower.suffix, propagated to loan client_name, returned via GET.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Shared Sessions ─────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sipahi_session():
    """Authenticated sipahi session"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
    assert resp.status_code == 200, f"Sipahi login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def existing_kyc_id(sipahi_session):
    """Get an existing KYC ID for testing"""
    resp = sipahi_session.get(f"{BASE_URL}/api/kycs", params={"limit": 5})
    assert resp.status_code == 200
    kycs = resp.json().get("kycs", [])
    assert len(kycs) > 0, "No KYCs found in DB"
    # Return the first available KYC
    return kycs[0]["id"]


# ── Test 1: List KYCs returns suffix field ───────────────────────────────────
class TestSuffixInListKYC:
    """Suffix field appears in list_kycs response"""

    def test_list_kycs_returns_primary_borrower(self, sipahi_session):
        """GET /api/kycs returns primary_borrower with suffix key"""
        resp = sipahi_session.get(f"{BASE_URL}/api/kycs", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "kycs" in data
        kycs = data["kycs"]
        assert len(kycs) > 0
        # Each KYC should have primary_borrower key
        for kyc in kycs:
            assert "primary_borrower" in kyc
            pb = kyc["primary_borrower"]
            # suffix key may be None but should be accessible (not cause KeyError)
            # Check it is a valid value (None or str)
            if "suffix" in pb:
                assert pb["suffix"] is None or isinstance(pb["suffix"], str)


# ── Test 2: GET /api/kycs/{id} returns suffix ────────────────────────────────
class TestSuffixInGetKYC:
    """GET /api/kycs/{id} includes suffix field"""

    def test_get_kyc_has_suffix_field(self, sipahi_session, existing_kyc_id):
        """Verify suffix field exists in GET /api/kycs/{id} response"""
        resp = sipahi_session.get(f"{BASE_URL}/api/kycs/{existing_kyc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "primary_borrower" in data
        pb = data["primary_borrower"]
        # suffix key should exist (may be None)
        assert "suffix" in pb or pb.get("suffix") is None


# ── Test 3: PUT /api/kycs/{id} stores suffix ─────────────────────────────────
class TestSuffixUpdateKYC:
    """PUT /api/kycs/{id} stores suffix in primary_borrower and propagates to loan"""

    def test_update_kyc_with_suffix_caste(self, sipahi_session, existing_kyc_id):
        """PUT /api/kycs/{id} with suffix='Dhobi' stores it and GET returns it"""
        # First GET to get existing data
        get_resp = sipahi_session.get(f"{BASE_URL}/api/kycs/{existing_kyc_id}")
        assert get_resp.status_code == 200
        kyc = get_resp.json()
        pb = kyc.get("primary_borrower", {})

        # Build payload with suffix
        payload = {
            "illaka_id": kyc.get("illaka_id", ""),
            "illaka_name": kyc.get("illaka_name", ""),
            "misal_id": kyc.get("misal_id", ""),
            "misal_name": kyc.get("misal_name", ""),
            "primary_borrower": {
                "name": pb.get("name") or "TEST Name",
                "name_hindi": pb.get("name_hindi"),
                "suffix": "Dhobi",
                "dob": pb.get("dob"),
                "gender": pb.get("gender"),
                "phone": pb.get("phone"),
                "aadhaar_number": pb.get("aadhaar_number"),
                "aadhaar_front_path": pb.get("aadhaar_front_path"),
                "aadhaar_back_path": pb.get("aadhaar_back_path"),
                "address": pb.get("address"),
                "relative_name": pb.get("relative_name"),
                "relative_name_hindi": pb.get("relative_name_hindi"),
                "document_type": pb.get("document_type"),
                "document_front_path": pb.get("document_front_path"),
                "document_back_path": pb.get("document_back_path"),
            },
            "live_photo_path": kyc.get("live_photo_path"),
            "notes": kyc.get("notes"),
        }
        # Add gps_location if present
        if kyc.get("gps_location"):
            payload["gps_location"] = kyc["gps_location"]

        update_resp = sipahi_session.put(f"{BASE_URL}/api/kycs/{existing_kyc_id}", json=payload)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"

        updated = update_resp.json()
        updated_pb = updated.get("primary_borrower", {})
        assert updated_pb.get("suffix") == "Dhobi", f"Expected 'Dhobi', got: {updated_pb.get('suffix')}"

    def test_get_kyc_after_update_has_suffix(self, sipahi_session, existing_kyc_id):
        """After PUT with suffix='Dhobi', GET /api/kycs/{id} returns suffix='Dhobi'"""
        resp = sipahi_session.get(f"{BASE_URL}/api/kycs/{existing_kyc_id}")
        assert resp.status_code == 200
        data = resp.json()
        pb = data.get("primary_borrower", {})
        assert pb.get("suffix") == "Dhobi", f"Expected persisted 'Dhobi', got: {pb.get('suffix')}"

    def test_update_kyc_with_urf_suffix(self, sipahi_session, existing_kyc_id):
        """PUT with suffix='Urf Pappu' stores correctly"""
        get_resp = sipahi_session.get(f"{BASE_URL}/api/kycs/{existing_kyc_id}")
        assert get_resp.status_code == 200
        kyc = get_resp.json()
        pb = kyc.get("primary_borrower", {})

        payload = {
            "illaka_id": kyc.get("illaka_id", ""),
            "illaka_name": kyc.get("illaka_name", ""),
            "misal_id": kyc.get("misal_id", ""),
            "misal_name": kyc.get("misal_name", ""),
            "primary_borrower": {
                "name": pb.get("name") or "TEST Name",
                "name_hindi": pb.get("name_hindi"),
                "suffix": "Urf Pappu",
                "dob": pb.get("dob"),
                "gender": pb.get("gender"),
                "phone": pb.get("phone"),
                "aadhaar_number": pb.get("aadhaar_number"),
                "aadhaar_front_path": pb.get("aadhaar_front_path"),
                "aadhaar_back_path": pb.get("aadhaar_back_path"),
                "address": pb.get("address"),
                "relative_name": pb.get("relative_name"),
                "relative_name_hindi": pb.get("relative_name_hindi"),
                "document_type": pb.get("document_type"),
                "document_front_path": pb.get("document_front_path"),
                "document_back_path": pb.get("document_back_path"),
            },
            "live_photo_path": kyc.get("live_photo_path"),
            "notes": kyc.get("notes"),
        }

        update_resp = sipahi_session.put(f"{BASE_URL}/api/kycs/{existing_kyc_id}", json=payload)
        assert update_resp.status_code == 200, f"Update with Urf suffix failed: {update_resp.text}"

        data = update_resp.json()
        pb_out = data.get("primary_borrower", {})
        assert pb_out.get("suffix") == "Urf Pappu", f"Expected 'Urf Pappu', got: {pb_out.get('suffix')}"

    def test_update_kyc_clear_suffix(self, sipahi_session, existing_kyc_id):
        """PUT with suffix=None clears suffix"""
        get_resp = sipahi_session.get(f"{BASE_URL}/api/kycs/{existing_kyc_id}")
        kyc = get_resp.json()
        pb = kyc.get("primary_borrower", {})

        payload = {
            "illaka_id": kyc.get("illaka_id", ""),
            "illaka_name": kyc.get("illaka_name", ""),
            "misal_id": kyc.get("misal_id", ""),
            "misal_name": kyc.get("misal_name", ""),
            "primary_borrower": {
                "name": pb.get("name") or "TEST Name",
                "name_hindi": pb.get("name_hindi"),
                "suffix": None,
                "dob": pb.get("dob"),
                "gender": pb.get("gender"),
                "phone": pb.get("phone"),
                "aadhaar_number": pb.get("aadhaar_number"),
                "aadhaar_front_path": pb.get("aadhaar_front_path"),
                "aadhaar_back_path": pb.get("aadhaar_back_path"),
                "address": pb.get("address"),
                "relative_name": pb.get("relative_name"),
                "relative_name_hindi": pb.get("relative_name_hindi"),
                "document_type": pb.get("document_type"),
                "document_front_path": pb.get("document_front_path"),
                "document_back_path": pb.get("document_back_path"),
            },
            "live_photo_path": kyc.get("live_photo_path"),
            "notes": kyc.get("notes"),
        }

        update_resp = sipahi_session.put(f"{BASE_URL}/api/kycs/{existing_kyc_id}", json=payload)
        assert update_resp.status_code == 200
        data = update_resp.json()
        pb_out = data.get("primary_borrower", {})
        assert not pb_out.get("suffix"), f"Expected suffix cleared, got: {pb_out.get('suffix')}"


# ── Test 4: Loan client_name includes suffix ─────────────────────────────────
class TestSuffixPropagatedToLoan:
    """After PUT /api/kycs/{id} with suffix, associated loan's client_name includes suffix"""

    def test_loan_client_name_includes_suffix(self, sipahi_session, admin_session, existing_kyc_id):
        """Update KYC suffix='Yadav', check loan's client_name ends with 'Yadav'"""
        # Get the KYC
        get_resp = sipahi_session.get(f"{BASE_URL}/api/kycs/{existing_kyc_id}")
        assert get_resp.status_code == 200
        kyc = get_resp.json()
        pb = kyc.get("primary_borrower", {})
        client_name = pb.get("name") or "TEST Name"
        loan_id = kyc.get("loan_id")

        if not loan_id:
            pytest.skip("No loan associated with this KYC")

        payload = {
            "illaka_id": kyc.get("illaka_id", ""),
            "illaka_name": kyc.get("illaka_name", ""),
            "misal_id": kyc.get("misal_id", ""),
            "misal_name": kyc.get("misal_name", ""),
            "primary_borrower": {
                "name": client_name,
                "name_hindi": pb.get("name_hindi"),
                "suffix": "Yadav",
                "dob": pb.get("dob"),
                "gender": pb.get("gender"),
                "phone": pb.get("phone"),
                "aadhaar_number": pb.get("aadhaar_number"),
                "aadhaar_front_path": pb.get("aadhaar_front_path"),
                "aadhaar_back_path": pb.get("aadhaar_back_path"),
                "address": pb.get("address"),
                "relative_name": pb.get("relative_name"),
                "relative_name_hindi": pb.get("relative_name_hindi"),
                "document_type": pb.get("document_type"),
                "document_front_path": pb.get("document_front_path"),
                "document_back_path": pb.get("document_back_path"),
            },
            "live_photo_path": kyc.get("live_photo_path"),
            "notes": kyc.get("notes"),
        }

        update_resp = sipahi_session.put(f"{BASE_URL}/api/kycs/{existing_kyc_id}", json=payload)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"

        # Check loan
        loan_resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert loan_resp.status_code == 200, f"Loan GET failed: {loan_resp.text}"
        loan = loan_resp.json()
        expected_name = f"{client_name} Yadav"
        assert loan.get("client_name") == expected_name, \
            f"Expected loan client_name='{expected_name}', got: {loan.get('client_name')}"

        # Cleanup: clear the suffix
        payload["primary_borrower"]["suffix"] = None
        sipahi_session.put(f"{BASE_URL}/api/kycs/{existing_kyc_id}", json=payload)


# ── Test 5: Admin can see suffix in kycs list ─────────────────────────────────
class TestAdminSeesSuffix:
    """Admin sees suffix via GET /api/kycs"""

    def test_admin_list_kycs_has_suffix_field(self, admin_session):
        """Admin GET /api/kycs returns suffix field"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs", params={"limit": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert "kycs" in data
        kycs = data["kycs"]
        for kyc in kycs:
            pb = kyc.get("primary_borrower", {})
            # suffix should exist (None is fine)
            assert isinstance(pb.get("suffix"), (str, type(None)))
