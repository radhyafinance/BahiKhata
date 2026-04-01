"""
Iteration 26: Collection Sheet 3-level chain tests.
Tests RA0030 3-chain (L1→L2→L3) and RA0022 regression checks.

New fields verified:
  - extra_kisht_entries: list of {amount, loan_date} for chain entries before current row
  - chain_start status in emi_year_data (renders ↩, NOT skipped in further merges)
  - prev_opening_balance / prev_loan_date / new_loan_in_fy for 3-chain row
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
    """Helper: find all rows matching a customer_id prefix."""
    found = []
    for il in sheet_data.get("illakas", []):
        for ms in il.get("misals", []):
            for r in ms.get("rows", []):
                if customer_id in str(r.get("customer_id", "")) or customer_id in str(r.get("loan_number", "")):
                    found.append(r)
    return found


# ── Test 1: FY 2023-24 — RA0030 3-chain (L1→L2→L3) ─────────────────────────────

class TestFY202324RA0030ThreeChain:
    """
    FY 2023-24 (month=2024-03): RA0030 has L1 (Jul 2022) → L2 (Aug 2023) → L3 (Mar 2024).
    L3 is the visible combined row. Verify all 3-chain fields.
    """

    @pytest.fixture(scope="class")
    def ra0030_row(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        assert resp.status_code == 200
        rows = _find_rows_by_customer_id(resp.json(), "RA0030")
        assert len(rows) > 0, "RA0030 not found in FY 2023-24"
        return rows[0]

    def test_sheet_200(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        assert resp.status_code == 200
        print("PASS: /api/collections/sheet?month=2024-03 returned 200")

    def test_ra0030_is_l3(self, ra0030_row):
        """Visible row should be L3 (the latest loan in chain)."""
        loan_date = ra0030_row.get("loan_date", "")
        assert loan_date.startswith("2024-03"), (
            f"Expected RA0030 visible row to be L3 (loan_date starts 2024-03), got '{loan_date}'"
        )
        print(f"PASS: RA0030 visible row is L3 with loan_date={loan_date}")

    def test_ra0030_is_netoff_combined(self, ra0030_row):
        assert ra0030_row.get("is_netoff_combined") is True
        print("PASS: RA0030 is_netoff_combined=True")

    def test_ra0030_new_loan_in_fy_true(self, ra0030_row):
        """L3 disbursed Mar 2024 is within FY 2023-24 → new_loan_in_fy=True."""
        assert ra0030_row.get("new_loan_in_fy") is True, (
            f"Expected new_loan_in_fy=True for RA0030 L3 in FY 2023-24, got {ra0030_row.get('new_loan_in_fy')}"
        )
        print("PASS: RA0030 new_loan_in_fy=True")

    def test_ra0030_prev_opening_balance_1000(self, ra0030_row):
        """पिछली बाक़ी = L1's netoff_amount = ₹1,000."""
        pob = ra0030_row.get("prev_opening_balance")
        assert pob == 1000.0, (
            f"Expected prev_opening_balance=1000, got {pob}"
        )
        print(f"PASS: RA0030 prev_opening_balance={pob}")

    def test_ra0030_prev_loan_date_jul_2022(self, ra0030_row):
        """पिछली बाक़ी date = L1's loan_date starting 2022-07."""
        prev_date = ra0030_row.get("prev_loan_date", "")
        assert prev_date.startswith("2022-07"), (
            f"Expected prev_loan_date to start with '2022-07', got '{prev_date}'"
        )
        print(f"PASS: RA0030 prev_loan_date={prev_date}")

    def test_ra0030_total_repayable_36000(self, ra0030_row):
        """L3 total_repayable = ₹36,000 (किस्त हाल current row)."""
        tr = ra0030_row.get("total_repayable")
        assert tr == 36000.0, (
            f"Expected total_repayable=36000 for L3, got {tr}"
        )
        print(f"PASS: RA0030 total_repayable={tr}")

    def test_ra0030_extra_kisht_entries_has_l2(self, ra0030_row):
        """extra_kisht_entries must contain exactly one entry: L2 (₹24,000, Aug 2023)."""
        extras = ra0030_row.get("extra_kisht_entries", [])
        assert len(extras) == 1, (
            f"Expected 1 extra_kisht_entry (L2), got {len(extras)}: {extras}"
        )
        print(f"PASS: extra_kisht_entries has {len(extras)} entry")

    def test_ra0030_extra_kisht_l2_amount_24000(self, ra0030_row):
        """extra_kisht_entries[0].amount = 24,000 (L2 total_repayable)."""
        extras = ra0030_row.get("extra_kisht_entries", [])
        assert len(extras) >= 1
        amt = extras[0].get("amount")
        assert amt == 24000.0, (
            f"Expected extra entry amount=24000 (L2 total_repayable), got {amt}"
        )
        print(f"PASS: extra_kisht_entries[0].amount={amt}")

    def test_ra0030_extra_kisht_l2_date_aug_2023(self, ra0030_row):
        """extra_kisht_entries[0].loan_date starts 2023-08 (L2 disbursement)."""
        extras = ra0030_row.get("extra_kisht_entries", [])
        assert len(extras) >= 1
        ld = extras[0].get("loan_date", "")
        assert ld.startswith("2023-08"), (
            f"Expected extra entry loan_date to start with '2023-08' (L2 Aug 2023), got '{ld}'"
        )
        print(f"PASS: extra_kisht_entries[0].loan_date={ld}")

    def test_ra0030_fy_strip_chain_start_aug_2023(self, ra0030_row):
        """FY strip must have chain_start in 2023-08 (L2 start month, ↩ arrow)."""
        strip = {e["month"]: e["status"] for e in ra0030_row.get("emi_year_data", [])}
        assert strip.get("2023-08") == "chain_start", (
            f"Expected 2023-08 to have chain_start in FY strip, got '{strip.get('2023-08')}'. Full strip: {strip}"
        )
        print("PASS: FY strip has chain_start at 2023-08 (L2 start)")

    def test_ra0030_fy_strip_chain_start_mar_2024(self, ra0030_row):
        """FY strip must have chain_start in 2024-03 (L3 start month, ↩ arrow)."""
        strip = {e["month"]: e["status"] for e in ra0030_row.get("emi_year_data", [])}
        assert strip.get("2024-03") == "chain_start", (
            f"Expected 2024-03 to have chain_start in FY strip, got '{strip.get('2024-03')}'. Full strip: {strip}"
        )
        print("PASS: FY strip has chain_start at 2024-03 (L3 start)")

    def test_ra0030_fy_strip_no_netoff_jul_2023(self, ra0030_row):
        """FY strip must NOT have netoff in 2023-07 (old L1 closing month must be gone)."""
        strip = {e["month"]: e["status"] for e in ra0030_row.get("emi_year_data", [])}
        jul_status = strip.get("2023-07", "na")
        assert jul_status != "netoff", (
            f"Expected 2023-07 NOT to have netoff status, got '{jul_status}'"
        )
        print(f"PASS: 2023-07 status={jul_status} (NOT netoff) ✓")

    def test_ra0030_fy_strip_two_chain_starts_total(self, ra0030_row):
        """FY strip must have exactly 2 chain_start entries (one for L2, one for L3)."""
        chain_starts = [e["month"] for e in ra0030_row.get("emi_year_data", [])
                       if e["status"] == "chain_start"]
        assert len(chain_starts) == 2, (
            f"Expected exactly 2 chain_start entries in FY strip, got {len(chain_starts)}: {chain_starts}"
        )
        assert "2023-08" in chain_starts
        assert "2024-03" in chain_starts
        print(f"PASS: FY strip has exactly 2 chain_starts: {chain_starts}")


# ── Test 2: FY 2023-24 — RA0022 regression (no extra_kisht_entries, no special strip) ──

class TestFY202324RA0022Regression:
    """
    FY 2023-24 (month=2024-03): RA0022 L2 was disbursed Dec 2022 (BEFORE this FY).
    Verify: prev_opening_balance=18000, prev_loan_date=2022-12, new_loan_in_fy=False,
    extra_kisht_entries=[], NO chain_start or netoff in FY strip.
    """

    @pytest.fixture(scope="class")
    def ra0022_row_2324(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2024-03")
        assert resp.status_code == 200
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert len(rows) > 0, "RA0022 not found in FY 2023-24"
        return rows[0]

    def test_ra0022_prev_opening_balance_18000(self, ra0022_row_2324):
        pob = ra0022_row_2324.get("prev_opening_balance")
        assert pob == 18000.0, f"Expected prev_opening_balance=18000, got {pob}"
        print(f"PASS: RA0022 FY 2023-24 prev_opening_balance={pob}")

    def test_ra0022_prev_loan_date_2022_12(self, ra0022_row_2324):
        prev_date = ra0022_row_2324.get("prev_loan_date", "")
        assert prev_date.startswith("2022-12"), (
            f"Expected prev_loan_date to start with '2022-12', got '{prev_date}'"
        )
        print(f"PASS: RA0022 FY 2023-24 prev_loan_date={prev_date}")

    def test_ra0022_new_loan_in_fy_false(self, ra0022_row_2324):
        assert ra0022_row_2324.get("new_loan_in_fy") is False, (
            f"Expected new_loan_in_fy=False (किस्त हाल blank), got {ra0022_row_2324.get('new_loan_in_fy')}"
        )
        print("PASS: RA0022 FY 2023-24 new_loan_in_fy=False")

    def test_ra0022_extra_kisht_entries_empty(self, ra0022_row_2324):
        extras = ra0022_row_2324.get("extra_kisht_entries", None)
        assert extras is not None, "extra_kisht_entries field missing on RA0022"
        assert extras == [], f"Expected extra_kisht_entries=[], got {extras}"
        print("PASS: RA0022 FY 2023-24 extra_kisht_entries=[]")

    def test_ra0022_fy_strip_no_chain_start_or_netoff(self, ra0022_row_2324):
        """FY strip should have NO chain_start or netoff entries for RA0022 in FY 2023-24."""
        strip = ra0022_row_2324.get("emi_year_data", [])
        special = [(e["month"], e["status"]) for e in strip
                   if e["status"] in ("chain_start", "netoff")]
        assert len(special) == 0, (
            f"Expected NO chain_start/netoff in FY 2023-24 RA0022 strip, got: {special}"
        )
        print("PASS: RA0022 FY 2023-24 strip has NO chain_start or netoff")


# ── Test 3: FY 2022-23 — RA0022 (L2 new in this FY, L1 netoff=2000, chain_start in Dec 2022) ──

class TestFY202223RA0022Chain:
    """
    FY 2022-23 (month=2023-03): RA0022 L2 (Dec 2022) is NEW in this FY.
    Verify: prev_opening_balance=2000 (L1 netoff), prev_loan_date starts 2022-01,
    chain_start in 2022-12 in FY strip.
    """

    @pytest.fixture(scope="class")
    def ra0022_row_2223(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2023-03")
        assert resp.status_code == 200
        rows = _find_rows_by_customer_id(resp.json(), "RA0022")
        assert len(rows) > 0, "RA0022 not found in FY 2022-23"
        return rows[0]

    def test_ra0022_new_loan_in_fy_true_in_fy_2022_23(self, ra0022_row_2223):
        """L2 disbursed Dec 2022 is within FY 2022-23 (Apr 2022-Mar 2023) → new_loan_in_fy=True."""
        assert ra0022_row_2223.get("new_loan_in_fy") is True, (
            f"Expected new_loan_in_fy=True for RA0022 in FY 2022-23 (L2 Dec 2022), got {ra0022_row_2223.get('new_loan_in_fy')}"
        )
        print("PASS: RA0022 FY 2022-23 new_loan_in_fy=True")

    def test_ra0022_prev_opening_balance_2000(self, ra0022_row_2223):
        """पिछली बाक़ी = L1's netoff_amount = ₹2,000."""
        pob = ra0022_row_2223.get("prev_opening_balance")
        assert pob == 2000.0, (
            f"Expected prev_opening_balance=2000 (L1 netoff amount), got {pob}"
        )
        print(f"PASS: RA0022 FY 2022-23 prev_opening_balance={pob}")

    def test_ra0022_prev_loan_date_jan_2022(self, ra0022_row_2223):
        """पिछली बाक़ी date = L1's loan_date starting 2022-01."""
        prev_date = ra0022_row_2223.get("prev_loan_date", "")
        assert prev_date.startswith("2022-01"), (
            f"Expected prev_loan_date to start with '2022-01' (L1 Jan 2022), got '{prev_date}'"
        )
        print(f"PASS: RA0022 FY 2022-23 prev_loan_date={prev_date}")

    def test_ra0022_fy_strip_chain_start_dec_2022(self, ra0022_row_2223):
        """FY strip must have chain_start in 2022-12 (L2 start month, ↩ arrow)."""
        strip = {e["month"]: e["status"] for e in ra0022_row_2223.get("emi_year_data", [])}
        assert strip.get("2022-12") == "chain_start", (
            f"Expected 2022-12 to have chain_start in FY strip, got '{strip.get('2022-12')}'. Full strip: {strip}"
        )
        print("PASS: RA0022 FY 2022-23 strip has chain_start at 2022-12")

    def test_ra0022_extra_kisht_entries_empty_in_fy_2022_23(self, ra0022_row_2223):
        """For a 2-level chain (L1→L2), extra_kisht_entries should be empty."""
        extras = ra0022_row_2223.get("extra_kisht_entries", None)
        assert extras is not None, "extra_kisht_entries field missing"
        assert extras == [], f"Expected extra_kisht_entries=[] for 2-level chain, got {extras}"
        print("PASS: RA0022 FY 2022-23 extra_kisht_entries=[]")


# ── Test 4: Current FY (2025-04) — all combined rows have extra_kisht_entries field ──

class TestCurrentFYExtraKishtEntriesField:
    """
    FY 2025-26 (month=2025-04): All combined rows must have extra_kisht_entries field.
    No regressions for existing combined rows.
    """

    @pytest.fixture(scope="class")
    def sheet_data_2025(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2025-04")
        assert resp.status_code == 200
        return resp.json()

    def test_sheet_200_current_fy(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet?month=2025-04")
        assert resp.status_code == 200
        print("PASS: /api/collections/sheet?month=2025-04 returned 200")

    def test_all_combined_rows_have_extra_kisht_entries_field(self, sheet_data_2025):
        """All combined rows must have the extra_kisht_entries field (even if empty)."""
        combined_rows = [
            r for il in sheet_data_2025.get("illakas", [])
            for ms in il.get("misals", [])
            for r in ms.get("rows", [])
            if r.get("is_netoff_combined")
        ]
        assert len(combined_rows) > 0, "No combined rows found in FY 2025-26"
        missing = [r.get("loan_number", r.get("customer_id"))
                   for r in combined_rows if "extra_kisht_entries" not in r]
        assert len(missing) == 0, f"extra_kisht_entries field missing on: {missing}"
        print(f"PASS: All {len(combined_rows)} combined rows have extra_kisht_entries field")

    def test_all_combined_rows_have_new_loan_in_fy_field(self, sheet_data_2025):
        combined_rows = [
            r for il in sheet_data_2025.get("illakas", [])
            for ms in il.get("misals", [])
            for r in ms.get("rows", [])
            if r.get("is_netoff_combined")
        ]
        missing = [r.get("loan_number") for r in combined_rows if "new_loan_in_fy" not in r]
        assert len(missing) == 0, f"new_loan_in_fy field missing on: {missing}"
        print(f"PASS: All {len(combined_rows)} combined rows have new_loan_in_fy field")

    def test_ra0030_in_current_fy_has_extra_kisht_entries(self, sheet_data_2025):
        """RA0030 L3 is still active in FY 2025-26 and must have extra_kisht_entries."""
        rows = _find_rows_by_customer_id(sheet_data_2025, "RA0030")
        if not rows:
            pytest.skip("RA0030 not found in FY 2025-26 (may be closed)")
        row = rows[0]
        if row.get("is_netoff_combined"):
            assert "extra_kisht_entries" in row, "RA0030 missing extra_kisht_entries in FY 2025-26"
            # In current FY, RA0030 L3 is still within FY 2025-26 scope; extras should be present
            extras = row.get("extra_kisht_entries", [])
            print(f"PASS: RA0030 in FY 2025-26 has extra_kisht_entries={extras}")
        else:
            print("SKIP: RA0030 is not netoff_combined in FY 2025-26")

    def test_combined_rows_all_required_fields(self, sheet_data_2025):
        """All combined rows must have is_netoff_combined, prev_opening_balance, new_loan_in_fy, extra_kisht_entries."""
        combined_rows = [
            r for il in sheet_data_2025.get("illakas", [])
            for ms in il.get("misals", [])
            for r in ms.get("rows", [])
            if r.get("is_netoff_combined")
        ]
        for r in combined_rows:
            lnum = r.get("loan_number", r.get("customer_id"))
            assert "is_netoff_combined" in r, f"{lnum} missing is_netoff_combined"
            assert "prev_opening_balance" in r, f"{lnum} missing prev_opening_balance"
            assert "new_loan_in_fy" in r, f"{lnum} missing new_loan_in_fy"
            assert "extra_kisht_entries" in r, f"{lnum} missing extra_kisht_entries"
        print(f"PASS: All {len(combined_rows)} combined rows have all required fields")
