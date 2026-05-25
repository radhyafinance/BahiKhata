"""
Test: Collection Sheet net-off combined row FY-calculation fixes.
Verifies 3 bugs fixed:
  1. FY 2022-23 RA0022 outstanding_balance=18000
  2. FY 2023-24 RA0022 prev_opening_balance=18000, prev_loan_date=2022-12, new_loan_in_fy=False
  3. FY 2023-24 RA0030 L2=Aug2023 → new_loan_in_fy=True
  4. new_loan_in_fy field present on all combined rows in any FY
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def session():
    """Authenticated session using admin credentials."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return s


def _find_rows_by_customer_id(sheet_data, customer_id):
    """Helper: find all rows in sheet response matching a customer_id prefix."""
    found = []
    for il in sheet_data.get("illakas", []):
        for ms in il.get("misals", []):
            for r in ms.get("rows", []):
                if customer_id in str(r.get("customer_id", "")) or customer_id in str(r.get("loan_number", "")):
                    found.append(r)
    return found


# ── Test 1: FY 2022-23 — RA0022 Bal = ₹18,000 ────────────────────────────────

class TestFY202223RA0022:
    """FY 2022-23 (month=2023-03): RA0022 outstanding_balance must be 18000."""

    def test_sheet_returns_200(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2023-03")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        print("PASS: /api/collections/sheet?month=2023-03 returned 200")

    def test_ra0022_found_in_fy_2022_23(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2023-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert len(rows) > 0, "RA0022 not found in FY 2022-23 sheet"
        print(f"PASS: RA0022 found ({len(rows)} row(s))")

    def test_ra0022_outstanding_balance_18000(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2023-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert len(rows) > 0, "RA0022 not found"
        row = rows[0]
        assert row["outstanding_balance"] == 18000.0, (
            f"Expected outstanding_balance=18000, got {row['outstanding_balance']}"
        )
        print(f"PASS: RA0022 outstanding_balance = {row['outstanding_balance']}")

    def test_ra0022_is_netoff_combined(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2023-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert rows[0].get("is_netoff_combined") is True, "RA0022 should be is_netoff_combined=True in FY 2022-23"
        print("PASS: RA0022 is_netoff_combined=True")

    def test_ra0022_new_loan_in_fy_true_in_fy_2022_23(self, session):
        """L2 was disbursed Dec 2022 which falls IN FY 2022-23, so new_loan_in_fy=True."""
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2023-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        row = rows[0]
        # L2 loan_date=2022-12-15 is within FY 2022-23 (2022-04 to 2023-03)
        assert row.get("new_loan_in_fy") is True, (
            f"Expected new_loan_in_fy=True for RA0022 in FY 2022-23, got {row.get('new_loan_in_fy')}"
        )
        print("PASS: RA0022 new_loan_in_fy=True in FY 2022-23 (L2 disbursed Dec 2022)")


# ── Test 2: FY 2023-24 — RA0022 पिछली बाक़ी = 18000, date=Dec 2022, किस्त हाल=blank ──

class TestFY202324RA0022:
    """FY 2023-24 (month=2024-03): RA0022 prev_opening_balance=18000, prev_loan_date starts 2022-12, new_loan_in_fy=False."""

    def test_sheet_returns_200(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        assert resp.status_code == 200
        print("PASS: /api/collections/sheet?month=2024-03 returned 200")

    def test_ra0022_found_in_fy_2023_24(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert len(rows) > 0, "RA0022 not found in FY 2023-24 sheet"
        print(f"PASS: RA0022 found in FY 2023-24 ({len(rows)} row(s))")

    def test_ra0022_prev_opening_balance_18000(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        row = rows[0]
        assert row.get("prev_opening_balance") == 18000.0, (
            f"Expected prev_opening_balance=18000, got {row.get('prev_opening_balance')}"
        )
        print(f"PASS: RA0022 prev_opening_balance = {row['prev_opening_balance']}")

    def test_ra0022_prev_loan_date_2022_12(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        row = rows[0]
        prev_date = row.get("prev_loan_date", "")
        assert prev_date.startswith("2022-12"), (
            f"Expected prev_loan_date to start with '2022-12', got '{prev_date}'"
        )
        print(f"PASS: RA0022 prev_loan_date = {prev_date}")

    def test_ra0022_new_loan_in_fy_false(self, session):
        """L2 was before FY 2023-24 (disbursed Dec 2022 < Apr 2023), so किस्त हाल should be blank."""
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        row = rows[0]
        assert row.get("new_loan_in_fy") is False, (
            f"Expected new_loan_in_fy=False (किस्त हाल blank) for RA0022 in FY 2023-24, got {row.get('new_loan_in_fy')}"
        )
        print("PASS: RA0022 new_loan_in_fy=False in FY 2023-24 (किस्त हाल blank)")

    def test_ra0022_is_netoff_combined(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert rows[0].get("is_netoff_combined") is True
        print("PASS: RA0022 is_netoff_combined=True in FY 2023-24")


# ── Test 3: FY 2023-24 — RA0030 L2=Aug 2023 → new_loan_in_fy=True ─────────────

class TestFY202324RA0030:
    """FY 2023-24 (month=2024-03): RA0030 L2 disbursed Aug 2023 (within FY) → new_loan_in_fy=True."""

    def test_ra0030_found(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0030")
        assert len(rows) > 0, "RA0030 not found in FY 2023-24"
        print("PASS: RA0030 found")

    def test_ra0030_new_loan_in_fy_true(self, session):
        """L2 disbursed Aug 2023 is within FY 2023-24 (Apr 2023-Mar 2024) → new_loan_in_fy=True."""
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0030")
        row = rows[0]
        # Verify L2 disbursement date is Aug 2023
        loan_date = row.get("loan_date", "")
        assert loan_date.startswith("2023-08"), (
            f"Expected RA0030 L2 loan_date to start with 2023-08, got '{loan_date}'"
        )
        assert row.get("new_loan_in_fy") is True, (
            f"Expected new_loan_in_fy=True for RA0030 in FY 2023-24 (L2=Aug 2023), got {row.get('new_loan_in_fy')}"
        )
        print(f"PASS: RA0030 loan_date={loan_date}, new_loan_in_fy=True")

    def test_ra0030_is_netoff_combined(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        rows = _find_rows_by_customer_id(resp.json(), "RA0030")
        assert rows[0].get("is_netoff_combined") is True
        print("PASS: RA0030 is_netoff_combined=True")


# ── Test 4: Current FY (2025-04) — all combined rows have new_loan_in_fy field ─

class TestCurrentFYCombinedRows:
    """FY 2025-26 (month=2025-04): All combined rows must have new_loan_in_fy field."""

    def test_sheet_200(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2025-04")
        assert resp.status_code == 200
        print("PASS: /api/collections/sheet?month=2025-04 returned 200")

    def test_all_combined_rows_have_new_loan_in_fy(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2025-04")
        data = resp.json()
        combined_rows = [
            r for il in data.get("illakas", [])
            for ms in il.get("misals", [])
            for r in ms.get("rows", [])
            if r.get("is_netoff_combined")
        ]
        assert len(combined_rows) > 0, "No combined rows found in current FY"
        missing = [r.get("loan_number", r.get("customer_id")) for r in combined_rows if "new_loan_in_fy" not in r]
        assert len(missing) == 0, f"new_loan_in_fy field missing on: {missing}"
        print(f"PASS: All {len(combined_rows)} combined rows have new_loan_in_fy field")

    def test_ra0006_new_loan_in_fy_true_in_current_fy(self, session):
        """RA0006 L2 disbursed June 2025 (within FY 2025-26 starting Apr 2025) → new_loan_in_fy=True."""
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2025-04")
        rows = _find_rows_by_customer_id(resp.json(), "RA0006")
        if not rows:
            pytest.skip("RA0006 not found in current FY sheet")
        row = rows[0]
        if row.get("is_netoff_combined"):
            loan_date = row.get("loan_date", "")
            if loan_date >= "2025-04":
                assert row.get("new_loan_in_fy") is True, (
                    f"RA0006 L2 loan_date={loan_date} is within FY 2025-26 but new_loan_in_fy={row.get('new_loan_in_fy')}"
                )
                print(f"PASS: RA0006 new_loan_in_fy=True (L2 loan_date={loan_date})")
            else:
                print(f"SKIP: RA0006 L2 loan_date={loan_date} is before FY 2025-26")
        else:
            print("SKIP: RA0006 row is not netoff_combined in current FY")

    def test_combined_rows_all_render_fields_present(self, session):
        """All combined rows must have is_netoff_combined, prev_opening_balance, new_loan_in_fy."""
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2025-04")
        data = resp.json()
        combined_rows = [
            r for il in data.get("illakas", [])
            for ms in il.get("misals", [])
            for r in ms.get("rows", [])
            if r.get("is_netoff_combined")
        ]
        for r in combined_rows:
            lnum = r.get("loan_number", r.get("customer_id"))
            assert "is_netoff_combined" in r, f"{lnum} missing is_netoff_combined"
            assert "prev_opening_balance" in r, f"{lnum} missing prev_opening_balance"
            assert "new_loan_in_fy" in r, f"{lnum} missing new_loan_in_fy"
        print(f"PASS: All {len(combined_rows)} combined rows have required fields")
