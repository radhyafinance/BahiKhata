"""
Tests for Illaka feature:
- GET /api/illakas (list illakas)
- GET /api/misals (list misals, with illaka_id filter)
- GET /api/dashboard/stats?illaka_id= filter
- GET /api/collections/sheet?illaka_id= filter
- GET /api/loans?illaka_id= filter
- GET /api/kycs?illaka_id= filter
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session"""
    session = requests.Session()
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"phone": "9999999999", "password": "Admin@123"},
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return session


@pytest.fixture(scope="module")
def sipahi_session():
    """Authenticated sipahi session"""
    session = requests.Session()
    resp = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"phone": "8888888888", "password": "Test@1234"},
    )
    assert resp.status_code == 200, f"Sipahi login failed: {resp.text}"
    return session


# ── 1. Illakas List ──────────────────────────────────────────────────────────

class TestIllakasList:
    """GET /api/illakas"""

    def test_admin_can_list_illakas(self, admin_session):
        """Admin should see all illakas"""
        resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Response should be a list"

    def test_illakas_have_required_fields(self, admin_session):
        """Each illaka should have id, name fields"""
        resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200
        data = resp.json()
        if data:
            illaka = data[0]
            assert "id" in illaka, "Illaka should have 'id' field"
            assert "name" in illaka, "Illaka should have 'name' field"

    def test_sipahi_can_list_their_illakas(self, sipahi_session):
        """Sipahi should see only assigned illakas (list, possibly empty)"""
        resp = sipahi_session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_unauthenticated_cannot_list_illakas(self):
        """Unauthenticated request should return 401"""
        session = requests.Session()
        resp = session.get(f"{BASE_URL}/api/illakas")
        assert resp.status_code == 401


# ── 2. Misals List ───────────────────────────────────────────────────────────

class TestMisalsList:
    """GET /api/misals"""

    def test_admin_can_list_all_misals(self, admin_session):
        """Admin should see misals"""
        resp = admin_session.get(f"{BASE_URL}/api/misals")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_misals_filter_by_illaka_id(self, admin_session):
        """Misals filtered by illaka_id should return only matching misals"""
        # First get all illakas
        illakas_resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert illakas_resp.status_code == 200
        illakas = illakas_resp.json()

        if not illakas:
            pytest.skip("No illakas in database to test misal filter")

        illaka_id = illakas[0]["id"]

        # Filter misals by this illaka
        resp = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # All returned misals should belong to this illaka
        for misal in data:
            assert misal.get("illaka_id") == illaka_id, (
                f"Misal {misal.get('id')} has illaka_id={misal.get('illaka_id')}, expected {illaka_id}"
            )

    def test_misals_invalid_illaka_id_returns_empty(self, admin_session):
        """Misals filtered by non-existent illaka_id should return empty list"""
        resp = admin_session.get(f"{BASE_URL}/api/misals?illaka_id=nonexistent999")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0, "Non-existent illaka_id should return empty misals"


# ── 3. Dashboard Stats with illaka_id filter ─────────────────────────────────

class TestDashboardStatsIllakaFilter:
    """GET /api/dashboard/stats?illaka_id="""

    def test_dashboard_stats_without_illaka_filter(self, admin_session):
        """Stats without filter should return all data"""
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "pending" in data
        assert "approved" in data
        assert "rejected" in data
        assert "active_loans" in data
        assert "total_loans" in data
        assert isinstance(data["total"], int)
        assert isinstance(data["active_loans"], int)

    def test_dashboard_stats_with_valid_illaka_id(self, admin_session):
        """Stats with specific illaka_id should return 200 and valid structure"""
        illakas_resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert illakas_resp.status_code == 200
        illakas = illakas_resp.json()

        if not illakas:
            pytest.skip("No illakas in database")

        illaka_id = illakas[0]["id"]
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats?illaka_id={illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "active_loans" in data
        # Filtered count should be <= total without filter
        assert isinstance(data["total"], int)

    def test_dashboard_stats_illaka_filter_reduces_count(self, admin_session):
        """Filtering by a non-existent illaka_id should give total=0"""
        resp = admin_session.get(f"{BASE_URL}/api/dashboard/stats?illaka_id=nonexistent999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0, "Non-existent illaka should give total=0"
        assert data["active_loans"] == 0, "Non-existent illaka should give active_loans=0"


# ── 4. Collections Sheet with illaka_id filter ───────────────────────────────

class TestCollectionsSheetIllakaFilter:
    """GET /api/collections/sheet?illaka_id="""

    def test_collection_sheet_without_filter(self, admin_session):
        """Collection sheet without illaka_id returns valid structure"""
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet")
        assert resp.status_code == 200
        data = resp.json()
        assert "month" in data
        assert "total" in data
        assert "collected" in data
        assert "illakas" in data
        assert isinstance(data["illakas"], list)

    def test_collection_sheet_with_illaka_id(self, admin_session):
        """Collection sheet filtered by illaka_id returns structure"""
        illakas_resp = admin_session.get(f"{BASE_URL}/api/illakas")
        assert illakas_resp.status_code == 200
        illakas = illakas_resp.json()

        if not illakas:
            pytest.skip("No illakas in database")

        illaka_id = illakas[0]["id"]
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet?illaka_id={illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "illakas" in data
        # If data exists, all illakas in result should match the filter
        for il in data["illakas"]:
            assert il["illaka_id"] == illaka_id, (
                f"Collection sheet returned illaka_id={il['illaka_id']}, expected {illaka_id}"
            )

    def test_collection_sheet_nonexistent_illaka_returns_empty(self, admin_session):
        """Collection sheet with non-existent illaka_id should return empty list"""
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet?illaka_id=nonexistent999")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert len(data["illakas"]) == 0

    def test_collection_sheet_with_month_param(self, admin_session):
        """Collection sheet accepts month parameter"""
        from datetime import date
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
        resp = admin_session.get(f"{BASE_URL}/api/collections/sheet?month={month}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["month"] == month


# ── 5. Loans list with illaka_id filter ──────────────────────────────────────

class TestLoansIllakaFilter:
    """GET /api/loans?illaka_id="""

    def test_loans_without_illaka_filter(self, admin_session):
        """Loans without filter returns all"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "loans" in data
        assert "total" in data
        assert isinstance(data["loans"], list)

    def test_loans_with_valid_illaka_id(self, admin_session):
        """Loans filtered by valid illaka_id returns 200"""
        illakas_resp = admin_session.get(f"{BASE_URL}/api/illakas")
        illakas = illakas_resp.json()

        if not illakas:
            pytest.skip("No illakas in database")

        illaka_id = illakas[0]["id"]
        resp = admin_session.get(f"{BASE_URL}/api/loans?illaka_id={illaka_id}&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "loans" in data

    def test_loans_nonexistent_illaka_returns_empty(self, admin_session):
        """Loans filtered by non-existent illaka_id returns empty list"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?illaka_id=nonexistent999&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert len(data["loans"]) == 0


# ── 6. KYCs list with illaka_id filter ──────────────────────────────────────

class TestKYCsIllakaFilter:
    """GET /api/kycs?illaka_id="""

    def test_kycs_without_illaka_filter(self, admin_session):
        """KYCs without filter returns all"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "kycs" in data
        assert "total" in data

    def test_kycs_with_valid_illaka_id(self, admin_session):
        """KYCs filtered by valid illaka_id returns 200"""
        illakas_resp = admin_session.get(f"{BASE_URL}/api/illakas")
        illakas = illakas_resp.json()

        if not illakas:
            pytest.skip("No illakas in database")

        illaka_id = illakas[0]["id"]
        resp = admin_session.get(f"{BASE_URL}/api/kycs?illaka_id={illaka_id}&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "kycs" in data

    def test_kycs_nonexistent_illaka_returns_empty(self, admin_session):
        """KYCs filtered by non-existent illaka_id returns empty list"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs?illaka_id=nonexistent999&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert len(data["kycs"]) == 0
