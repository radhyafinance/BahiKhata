"""
CRIF High Mark INDV 2.0 Integration Tests
Tests for: POST /api/crif/check/{kyc_id}, GET /api/crif/result/{kyc_id}, GET /api/crif/report-html/{kyc_id}
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test KYC IDs
KYC_WITH_DOB = "69d7561cefd5a127f84854b1"    # Pinki, DOB: 01/01/1987
KYC_WITHOUT_DOB = "69d74eb0f42856df533f4fc0"  # Ramesh Kumar, no DOB
KYC_NONEXISTENT = "000000000000000000000000"   # Invalid KYC ID


@pytest.fixture(scope="module")
def session():
    """Authenticated requests session shared across module tests."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    if resp.status_code != 200:
        pytest.skip(f"Login failed: {resp.status_code} – cannot run CRIF tests")
    return s


# ── GET /result BEFORE any check ─────────────────────────────────────────────

class TestCrifResultBeforeCheck:
    """Verify GET /result returns has_result:false when no check exists yet."""

    def test_result_before_check_status_200(self, session):
        """GET /api/crif/result/{kyc_id} should return 200 even with no prior check."""
        # Use a fresh nonexistent-check KYC (no-DOB KYC unlikely to have a prior check)
        resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITHOUT_DOB}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"

    def test_result_before_check_has_result_false(self, session):
        """GET /api/crif/result returns has_result:false when no check has been run."""
        resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITHOUT_DOB}")
        data = resp.json()
        assert "has_result" in data, "Response must contain 'has_result' field"
        assert data["has_result"] is False, f"Expected has_result=False, got {data['has_result']}"


# ── POST /check – No DOB validation ──────────────────────────────────────────

class TestCrifCheckNoDob:
    """POST /api/crif/check/{kyc_id} must return 422 when KYC has no DOB."""

    def test_check_no_dob_returns_422(self, session):
        """CRIF check should fail with 422 when DOB is missing."""
        resp = session.post(f"{BASE_URL}/api/crif/check/{KYC_WITHOUT_DOB}", json={})
        assert resp.status_code == 422, f"Expected 422 for no-DOB KYC, got {resp.status_code}: {resp.text[:300]}"

    def test_check_no_dob_has_detail_message(self, session):
        """422 response must include a human-readable detail message about DOB."""
        resp = session.post(f"{BASE_URL}/api/crif/check/{KYC_WITHOUT_DOB}", json={})
        data = resp.json()
        assert "detail" in data, "422 response must have 'detail' field"
        detail = data["detail"].lower()
        assert "dob" in detail or "date of birth" in detail or "birth" in detail, \
            f"Error detail should mention DOB: {data['detail']}"

    def test_check_nonexistent_kyc_returns_404(self, session):
        """CRIF check should return 404 for a non-existent KYC ID."""
        resp = session.post(f"{BASE_URL}/api/crif/check/{KYC_NONEXISTENT}", json={})
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text[:200]}"


# ── POST /check – With DOB (Live UAT call) ───────────────────────────────────

class TestCrifCheckWithDob:
    """POST /api/crif/check/{kyc_id} with a KYC that has DOB should call CRIF UAT.
    
    NOTE: This hits the live CRIF UAT API. Allow up to 45 seconds for response.
    """

    def test_check_with_dob_returns_200(self, session):
        """POST /api/crif/check with DOB KYC should return HTTP 200 or handled CRIF error."""
        resp = session.post(
            f"{BASE_URL}/api/crif/check/{KYC_WITH_DOB}", json={},
            timeout=60
        )
        # Accept 200 (success) or 502/504 (CRIF connectivity issue in UAT)
        assert resp.status_code in (200, 502, 504), \
            f"Unexpected status {resp.status_code}: {resp.text[:400]}"

    def test_check_with_dob_response_has_kyc_id(self, session):
        """Successful CRIF check response must contain kyc_id."""
        resp = session.post(
            f"{BASE_URL}/api/crif/check/{KYC_WITH_DOB}", json={},
            timeout=60
        )
        if resp.status_code != 200:
            pytest.skip(f"CRIF API returned {resp.status_code} – skipping data assertions")
        data = resp.json()
        assert "kyc_id" in data, "Response must have 'kyc_id'"
        assert data["kyc_id"] == KYC_WITH_DOB

    def test_check_with_dob_response_has_result(self, session):
        """Successful CRIF check response must contain 'result' dict."""
        resp = session.post(
            f"{BASE_URL}/api/crif/check/{KYC_WITH_DOB}", json={},
            timeout=60
        )
        if resp.status_code != 200:
            pytest.skip(f"CRIF API returned {resp.status_code} – skipping data assertions")
        data = resp.json()
        assert "result" in data, "Response must have 'result'"
        assert isinstance(data["result"], dict), "'result' must be a dict"

    def test_check_with_dob_result_has_status(self, session):
        """CRIF result dict should have a 'status' field."""
        resp = session.post(
            f"{BASE_URL}/api/crif/check/{KYC_WITH_DOB}", json={},
            timeout=60
        )
        if resp.status_code != 200:
            pytest.skip(f"CRIF API returned {resp.status_code}")
        result = resp.json().get("result", {})
        assert "status" in result, f"Result must have 'status', got keys: {list(result.keys())}"
        assert result["status"] in ("success", "error", "no_report"), \
            f"status must be success/error/no_report, got: {result['status']}"

    def test_check_with_dob_response_has_checked_at(self, session):
        """CRIF check response must contain checked_at timestamp."""
        resp = session.post(
            f"{BASE_URL}/api/crif/check/{KYC_WITH_DOB}", json={},
            timeout=60
        )
        if resp.status_code != 200:
            pytest.skip(f"CRIF API returned {resp.status_code}")
        data = resp.json()
        assert "checked_at" in data, "Response must have 'checked_at'"
        assert data["checked_at"], "checked_at must not be empty"


# ── GET /result AFTER check ───────────────────────────────────────────────────

class TestCrifResultAfterCheck:
    """GET /api/crif/result/{kyc_id} should return has_result:true after a check is done."""

    def test_result_after_check_has_result_true(self, session):
        """After running a check, GET /result should return has_result:True."""
        # Run the check first (may use cached DB result)
        check_resp = session.post(
            f"{BASE_URL}/api/crif/check/{KYC_WITH_DOB}", json={},
            timeout=60
        )
        if check_resp.status_code not in (200,):
            pytest.skip(f"CRIF check returned {check_resp.status_code} – cannot verify result")

        # Now fetch the result
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        assert result_resp.status_code == 200, f"Expected 200, got {result_resp.status_code}"
        data = result_resp.json()
        assert data.get("has_result") is True, f"Expected has_result=True, got: {data}"

    def test_result_after_check_has_kyc_id(self, session):
        """GET /result response must contain kyc_id after check."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        if result_resp.status_code != 200:
            pytest.skip("Result endpoint not available")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No result stored yet – run check first")
        assert data.get("kyc_id") == KYC_WITH_DOB, f"kyc_id mismatch: {data.get('kyc_id')}"

    def test_result_after_check_has_result_dict(self, session):
        """GET /result response must have nested 'result' dict."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No result stored – run check first")
        assert "result" in data, "Response must have 'result'"
        assert isinstance(data["result"], dict)

    def test_result_checked_at_present(self, session):
        """GET /result response should contain checked_at timestamp."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No result stored")
        assert "checked_at" in data, "Result must include checked_at"

    def test_result_service_statuses_if_success(self, session):
        """When CRIF returns success, result should have service_statuses dict."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No result stored")
        r = data.get("result", {})
        if r.get("status") != "success":
            pytest.skip(f"CRIF status is {r.get('status')}, not success – skipping")
        assert "service_statuses" in r, "Success result must have 'service_statuses'"
        assert isinstance(r["service_statuses"], dict)

    def test_result_account_summary_if_success(self, session):
        """When CRIF returns success, result should have account_summary dict."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No result stored")
        r = data.get("result", {})
        if r.get("status") != "success":
            pytest.skip(f"CRIF status is {r.get('status')}, not success – skipping")
        assert "account_summary" in r, "Success result must have 'account_summary'"
        assert isinstance(r["account_summary"], dict)


# ── GET /report-html ──────────────────────────────────────────────────────────

class TestCrifReportHtml:
    """GET /api/crif/report-html/{kyc_id} should return HTML content if available."""

    def test_report_html_no_check_returns_404(self, session):
        """HTML report for a KYC with no check should return 404."""
        # Use a fresh KYC that hasn't been checked (highly unlikely to have a stored check)
        resp = session.get(f"{BASE_URL}/api/crif/report-html/{KYC_NONEXISTENT}")
        assert resp.status_code in (404, 422), \
            f"Expected 404 or 422 for unchecked KYC, got {resp.status_code}"

    def test_report_html_after_check_status(self, session):
        """HTML report endpoint after a check should return 200 or 404 if no HTML in response."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No CRIF check result stored – run check first")

        html_resp = session.get(f"{BASE_URL}/api/crif/report-html/{KYC_WITH_DOB}")
        # 200 if HTML was returned by CRIF, 404 if the UAT test response has no HTML section
        assert html_resp.status_code in (200, 404), \
            f"Unexpected status {html_resp.status_code}: {html_resp.text[:200]}"

    def test_report_html_content_type_if_200(self, session):
        """HTML report endpoint when returning 200 should have text/html content type."""
        result_resp = session.get(f"{BASE_URL}/api/crif/result/{KYC_WITH_DOB}")
        data = result_resp.json()
        if not data.get("has_result"):
            pytest.skip("No result stored")

        html_resp = session.get(f"{BASE_URL}/api/crif/report-html/{KYC_WITH_DOB}")
        if html_resp.status_code == 404:
            pytest.skip("No HTML report in CRIF response (UAT may not include HTML)")
        assert "text/html" in html_resp.headers.get("content-type", ""), \
            f"Content-Type should be text/html: {html_resp.headers.get('content-type')}"
