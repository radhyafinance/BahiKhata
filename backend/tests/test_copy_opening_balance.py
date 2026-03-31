"""
Tests for Copy Opening Balance from Year-End Closing feature.
Covers: GET /api/accounts/closing-balances endpoint,
        GET /api/loans/year-end-closing/history,
        Role-based access (403 for muneem), 404 for missing closing.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
DELHI_ILLAKA_ID = "69c78cf96781e1fb0d95f0dd"
CLOSING_DATE = "2024-03-31"
MISSING_DATE = "2025-03-31"

ADMIN_PHONE = "9999999999"
ADMIN_PASS = "Admin@123"
MUNEEM_PHONE = "7777000001"
MUNEEM_PASS = "Test@1234"


@pytest.fixture(scope="module")
def admin_session():
    """Authenticated session for admin user."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"phone": ADMIN_PHONE, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    print(f"Admin login OK: {r.status_code}")
    return s


@pytest.fixture(scope="module")
def muneem_session():
    """Authenticated session for muneem user."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"phone": MUNEEM_PHONE, "password": MUNEEM_PASS})
    assert r.status_code == 200, f"Muneem login failed: {r.text}"
    print(f"Muneem login OK: {r.status_code}")
    return s


class TestYearEndClosingHistory:
    """Tests for year-end closing history endpoint."""

    def test_closing_history_returns_200(self, admin_session):
        """GET closing history should return 200 for admin."""
        r = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        print(f"Closing history status: {r.status_code}")

    def test_closing_history_has_closings(self, admin_session):
        """History response should have 'closings' list."""
        r = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID},
        )
        data = r.json()
        assert "closings" in data, f"No 'closings' key in response: {data}"
        print(f"Number of closings: {len(data['closings'])}")

    def test_closing_history_contains_2024_03_31(self, admin_session):
        """Delhi illaka should have a closing on 2024-03-31."""
        r = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/history",
            params={"illaka_id": DELHI_ILLAKA_ID},
        )
        data = r.json()
        closings = data.get("closings", [])
        assert len(closings) > 0, "No closings found for Delhi illaka"
        dates = [c.get("closing_date") for c in closings]
        assert CLOSING_DATE in dates, f"Expected {CLOSING_DATE} in closings, got: {dates}"
        print(f"Found closing date {CLOSING_DATE} in history: {dates}")


class TestClosingBalancesEndpoint:
    """Tests for GET /api/accounts/closing-balances."""

    def test_returns_200_for_valid_closing(self, admin_session):
        """Should return 200 when a year-end closing exists on that date."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        print(f"closing-balances status: {r.status_code}")

    def test_response_has_items_key(self, admin_session):
        """Response must include 'items' key."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        data = r.json()
        assert "items" in data, f"No 'items' key: {data}"
        print(f"Items count: {len(data['items'])}")

    def test_items_are_non_empty(self, admin_session):
        """Items list should have at least one entry."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        data = r.json()
        items = data.get("items", [])
        assert len(items) > 0, "Expected non-empty items list"
        print(f"Items: {items}")

    def test_items_have_required_fields(self, admin_session):
        """Each item must have account_head_id, balance, group_type."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        data = r.json()
        items = data.get("items", [])
        for item in items:
            assert "account_head_id" in item, f"Missing account_head_id in: {item}"
            assert "balance" in item, f"Missing balance in: {item}"
            assert "group_type" in item, f"Missing group_type in: {item}"
        print(f"All {len(items)} items have required fields")

    def test_items_exclude_income_expense(self, admin_session):
        """Income and expense group_type items should be excluded."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        data = r.json()
        items = data.get("items", [])
        bad = [i for i in items if i.get("group_type") in ("income", "expense")]
        assert len(bad) == 0, f"Income/expense items found (should be excluded): {bad}"
        print("Income/expense items correctly excluded")

    def test_items_have_positive_balance(self, admin_session):
        """All returned items should have balance > 0 (zero-balance items excluded)."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        data = r.json()
        items = data.get("items", [])
        zero_items = [i for i in items if abs(i.get("balance", 0)) < 0.01]
        assert len(zero_items) == 0, f"Zero-balance items found (should be excluded): {zero_items}"
        print("All items have non-zero balance (correct)")

    def test_response_has_closing_date(self, admin_session):
        """Response should echo back the closing_date."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        data = r.json()
        assert data.get("closing_date") == CLOSING_DATE, f"closing_date mismatch: {data}"
        print(f"closing_date echoed correctly: {data.get('closing_date')}")

    def test_returns_404_for_missing_closing_date(self, admin_session):
        """Should return 404 when no year-end closing exists on that date."""
        r = admin_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": MISSING_DATE},
        )
        assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
        data = r.json()
        assert "detail" in data, f"No detail message in 404 response: {data}"
        print(f"404 correctly returned: {data.get('detail')}")

    def test_returns_403_for_muneem_user(self, muneem_session):
        """Muneem role should be forbidden (403)."""
        r = muneem_session.get(
            f"{BASE_URL}/api/accounts/closing-balances",
            params={"illaka_id": DELHI_ILLAKA_ID, "closing_date": CLOSING_DATE},
        )
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"
        data = r.json()
        assert "detail" in data, f"No detail in 403 response: {data}"
        print(f"403 correctly returned for muneem: {data.get('detail')}")
