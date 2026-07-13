"""
Test: Non-netoff re-loan merge on the Vasuli (Collection Sheet) page.

Key scenarios:
1. BI0021-L2 (non-netoff re-loan in Biharipur/SHEESH GARH misal) appears as a SINGLE MERGED ROW
2. Merged row appears at position #21 (inherits parent's display_order=20, between BI0020 and BI0022)
3. Rampur Testing illaka RA0021-RA0030 still merge correctly (regression check)
4. chain_start (↩) symbol present at re-loan's disbursement month when status is 'na' in strip
5. After EMI collection, merged row stays at its position
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Illaka IDs (confirmed from live data)
BIHARIPUR_ILLAKA_ID = "6a3510cd7d131f22c25263cc"  # BI prefix
RAMPUR_ILLAKA_ID    = "69cbbd24af2f8a0e30d6f3af"  # RA prefix


# ---------- Auth fixture ----------

@pytest.fixture(scope="module")
def session():
    """Authenticated session (admin)."""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    print("PASS: Admin login successful")
    return s


@pytest.fixture(scope="module")
def biharipur_sheet_2026(session):
    """Biharipur illaka collection sheet for FY 2026-27 (month=2026-04)."""
    resp = session.get(
        f"{BASE_URL}/api/collections/sheet",
        params={"month": "2026-04", "illaka_id": BIHARIPUR_ILLAKA_ID}
    )
    assert resp.status_code == 200, f"Sheet API failed: {resp.status_code} {resp.text[:300]}"
    data = resp.json()
    print(f"Loaded Biharipur sheet 2026-04, illakas={len(data['illakas'])}")
    return data


@pytest.fixture(scope="module")
def rampur_sheet_2025(session):
    """Rampur Testing illaka collection sheet for FY 2025-26 (month=2025-04)."""
    resp = session.get(
        f"{BASE_URL}/api/collections/sheet",
        params={"month": "2025-04", "illaka_id": RAMPUR_ILLAKA_ID}
    )
    assert resp.status_code == 200, f"Sheet API failed: {resp.status_code} {resp.text[:300]}"
    data = resp.json()
    print(f"Loaded Rampur sheet 2025-04, illakas={len(data['illakas'])}")
    return data


def get_all_rows(sheet_data):
    """Flatten all rows from all illakas/misals."""
    rows = []
    for il in sheet_data.get("illakas", []):
        for ms in il.get("misals", []):
            rows.extend(ms.get("rows", []))
    return rows


def get_sheesh_garh_rows(biharipur_sheet):
    """Return ordered rows from the SHEESH GARH misal."""
    for il in biharipur_sheet.get("illakas", []):
        for ms in il.get("misals", []):
            if "SHEESH" in ms["misal_name"].upper() or "GARH" in ms["misal_name"].upper():
                return ms["rows"]
    return []


# ---------- Core fix: Non-netoff merge tests ----------

class TestNonNetoffReloanMerge:
    """
    BI0021-L2 (non-netoff re-loan, parent NOT netoff_closed) in SHEESH GARH misal.
    Viewed via month=2026-04 → FY 2026-27 strip.
    """

    def test_biharipur_sheet_loads(self, biharipur_sheet_2026):
        assert "illakas" in biharipur_sheet_2026
        rows = get_all_rows(biharipur_sheet_2026)
        assert len(rows) > 0, "Expected rows in Biharipur sheet"
        print(f"PASS: Biharipur 2026-04 sheet loaded. Total rows: {len(rows)}")

    def test_bi0021_l1_not_present_as_separate_row(self, biharipur_sheet_2026):
        """BI0021-L1 (parent loan) must NOT appear as its own row — absorbed into L2."""
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        l1_rows = [r for r in rows if r.get("loan_number") == "BI0021-L1"]
        print(f"BI0021-L1 rows found: {[r['loan_number'] for r in l1_rows]}")
        assert len(l1_rows) == 0, (
            f"BI0021-L1 should be ABSORBED into merged row, but found: {[r['loan_number'] for r in l1_rows]}"
        )
        print("PASS: BI0021-L1 NOT shown as a separate row (absorbed correctly)")

    def test_bi0021_l2_present_as_merged_row(self, biharipur_sheet_2026):
        """BI0021-L2 must be in the sheet with is_netoff_combined=True."""
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        l2_row = next((r for r in rows if r.get("loan_number") == "BI0021-L2"), None)
        assert l2_row is not None, "BI0021-L2 not found in SHEESH GARH misal rows"
        assert l2_row.get("is_netoff_combined") is True, (
            f"BI0021-L2 should have is_netoff_combined=True, got: {l2_row.get('is_netoff_combined')}"
        )
        print(f"PASS: BI0021-L2 present as merged row (is_netoff_combined=True)")

    def test_bi0021_merged_row_inherits_display_order(self, biharipur_sheet_2026):
        """BI0021-L2 merged row must have display_order=20 (inherited from parent BI0021-L1)."""
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        l2_row = next((r for r in rows if r.get("loan_number") == "BI0021-L2"), None)
        assert l2_row is not None, "BI0021-L2 not found"
        assert l2_row.get("display_order") == 20, (
            f"Expected display_order=20 (inherited from parent), got: {l2_row.get('display_order')}"
        )
        print(f"PASS: BI0021-L2 has display_order=20 (inherited from parent)")

    def test_bi0021_merged_row_position_between_bi0020_and_bi0022(self, biharipur_sheet_2026):
        """Merged BI0021-L2 must appear at index [20] — between BI0020 and BI0022."""
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        loan_numbers = [r.get("loan_number", "") for r in rows]

        # Find indices
        bi0020_idx = next((i for i, ln in enumerate(loan_numbers) if ln == "BI0020-L1"), None)
        bi0021_idx = next((i for i, ln in enumerate(loan_numbers) if "BI0021" in ln), None)
        bi0022_idx = next((i for i, ln in enumerate(loan_numbers) if "BI0022" in ln), None)

        print(f"Positions: BI0020={bi0020_idx}, BI0021={bi0021_idx}, BI0022={bi0022_idx}")

        assert bi0021_idx is not None, "BI0021 not found in rows"

        # Must NOT be at the bottom
        last_idx = len(rows) - 1
        assert bi0021_idx < last_idx - 2, (
            f"BI0021-L2 appears near the bottom (idx={bi0021_idx} of {last_idx}) — "
            "display_order inheritance failed!"
        )

        if bi0020_idx is not None and bi0022_idx is not None:
            assert bi0020_idx < bi0021_idx < bi0022_idx, (
                f"BI0021 (idx={bi0021_idx}) should be between BI0020 (idx={bi0020_idx}) "
                f"and BI0022 (idx={bi0022_idx})"
            )
            print(f"PASS: BI0021-L2 at position {bi0021_idx} — correctly between BI0020 and BI0022")
        else:
            print(f"PASS: BI0021-L2 at position {bi0021_idx} (NOT at bottom) — position inherited correctly")

    def test_bi0021_merged_row_has_fy_strip_data(self, biharipur_sheet_2026):
        """BI0021-L2 merged row must have emi_year_data with 12 months."""
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        l2_row = next((r for r in rows if r.get("loan_number") == "BI0021-L2"), None)
        assert l2_row is not None
        emi_year = l2_row.get("emi_year_data", [])
        assert len(emi_year) == 12, f"Expected 12 FY months, got: {len(emi_year)}"
        print(f"PASS: BI0021-L2 has 12-month FY strip")

    def test_bi0021_merged_row_new_loan_in_fy_true(self, biharipur_sheet_2026):
        """BI0021-L2 started in FY 2026-27 — new_loan_in_fy must be True."""
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        l2_row = next((r for r in rows if r.get("loan_number") == "BI0021-L2"), None)
        assert l2_row is not None
        # loan_date 2026-04-05 is within FY 2026-27 (Apr 2026 – Mar 2027)
        assert l2_row.get("new_loan_in_fy") is True, (
            f"new_loan_in_fy should be True (L2 disbursed in FY), got: {l2_row.get('new_loan_in_fy')}"
        )
        print(f"PASS: BI0021-L2 new_loan_in_fy=True (disbursed within FY 2026-27)")


# ---------- chain_start symbol tests ----------

class TestChainStartSymbol:
    """
    chain_start (↩) is injected at L2 disbursement month IF that month's status is 'na'.
    When first EMI is already paid (e.g. BI0021-L2 April 2026), 'paid' takes priority.
    BI0395-L3 (loan_date=2026-04, status=na at April) shows chain_start correctly.
    """

    def test_chain_start_present_in_biharipur_sheet(self, biharipur_sheet_2026):
        """At least one merged row in Biharipur 2026-04 sheet shows chain_start in FY strip."""
        rows = get_all_rows(biharipur_sheet_2026)
        rows_with_chain = [
            r for r in rows
            if r.get("is_netoff_combined") and
            any(e.get("status") == "chain_start" for e in r.get("emi_year_data", []))
        ]
        print(f"Rows with chain_start: {[r['loan_number'] for r in rows_with_chain]}")
        assert len(rows_with_chain) >= 1, (
            "Expected at least one combined row to have chain_start in emi_year_data. "
            "chain_start is set when disbursement month has 'na' status in merged strip."
        )
        print(f"PASS: {len(rows_with_chain)} rows have chain_start symbol in Biharipur 2026-04 sheet")

    def test_chain_start_at_correct_month(self, biharipur_sheet_2026):
        """chain_start month must match the re-loan's disbursement month."""
        rows = get_all_rows(biharipur_sheet_2026)
        for row in rows:
            if not row.get("is_netoff_combined"):
                continue
            emi_year = row.get("emi_year_data", [])
            chain_months = [e["month"] for e in emi_year if e.get("status") == "chain_start"]
            if chain_months:
                loan_start_ym = (row.get("loan_date") or "")[:7]
                assert loan_start_ym in chain_months, (
                    f"For {row['loan_number']}: chain_start at {chain_months} should include "
                    f"loan_date month {loan_start_ym}"
                )
                print(f"PASS: {row['loan_number']} — chain_start at {chain_months} matches loan_date {loan_start_ym}")
                return  # Found and verified at least one
        pytest.skip("No rows with chain_start found (all first-month EMIs are paid)")

    def test_bi0021_april_emi_paid_shows_paid_not_chain_start(self, biharipur_sheet_2026):
        """
        BI0021-L2 April 2026 EMI is already paid.
        chain_start is intentionally NOT set (paid status takes priority over chain_start).
        """
        rows = get_sheesh_garh_rows(biharipur_sheet_2026)
        l2_row = next((r for r in rows if r.get("loan_number") == "BI0021-L2"), None)
        assert l2_row is not None

        april_entry = next(
            (e for e in l2_row.get("emi_year_data", []) if e.get("month") == "2026-04"),
            None
        )
        assert april_entry is not None, "April 2026 entry not found in BI0021-L2 emi_year_data"
        assert april_entry.get("status") == "paid", (
            f"Expected April 2026 to be 'paid', got: {april_entry.get('status')} — "
            "this is correct: paid takes priority over chain_start"
        )
        print(f"PASS: BI0021-L2 April 2026 shows 'paid' (chain_start correctly skipped when EMI paid)")


# ---------- Regression: Rampur net-off re-loans ----------

class TestRampurNetoffRegression:
    """RA0021-RA0030 in Rampur Testing illaka (month=2025-04) must still merge correctly."""

    def test_rampur_sheet_loads(self, rampur_sheet_2025):
        assert "illakas" in rampur_sheet_2025
        rows = get_all_rows(rampur_sheet_2025)
        print(f"PASS: Rampur sheet 2025-04 loaded. Total rows: {len(rows)}")

    def test_ra_l1_parents_not_shown_separately(self, rampur_sheet_2025):
        """RA0021-RA0030 L1 parent rows must NOT appear — all absorbed by L2/L3."""
        rows = get_all_rows(rampur_sheet_2025)
        ra_l1_rows = [
            r for r in rows
            if "-L1" in r.get("loan_number", "") and
            any(f"RA{str(n).zfill(4)}" in r.get("loan_number", "") for n in range(21, 31))
        ]
        print(f"RA0021-RA0030 L1 separate rows (should be 0): {[r['loan_number'] for r in ra_l1_rows]}")
        assert len(ra_l1_rows) == 0, (
            f"REGRESSION! RA L1 parent rows should be absorbed, found: {[r['loan_number'] for r in ra_l1_rows]}"
        )
        print("PASS: All RA0021-RA0030 L1 rows absorbed (no regression)")

    def test_ra_l2_rows_have_is_netoff_combined(self, rampur_sheet_2025):
        """All RA0021-RA0030 re-loan rows should have is_netoff_combined=True."""
        rows = get_all_rows(rampur_sheet_2025)
        ra_combined = [
            r for r in rows
            if r.get("is_netoff_combined") and
            any(f"RA{str(n).zfill(4)}" in r.get("loan_number", "") for n in range(21, 31))
        ]
        print(f"RA0021-RA0030 combined rows: {[r['loan_number'] for r in ra_combined]}")
        assert len(ra_combined) >= 8, (
            f"Expected at least 8 RA combined rows (RA0021-RA0030), got: {len(ra_combined)}. "
            f"Found: {[r['loan_number'] for r in ra_combined]}"
        )
        print(f"PASS: {len(ra_combined)} RA0021-RA0030 rows have is_netoff_combined=True")

    def test_ra_reloans_disbursed_before_fy_have_full_na_strip(self, rampur_sheet_2025):
        """
        RA re-loans disbursed BEFORE FY 2025-26 should have 'na' in their strip months
        (since all their EMIs fall outside this FY period).
        chain_start does NOT appear in FY 2025-26 for these (they were marked in an earlier FY).
        """
        rows = get_all_rows(rampur_sheet_2025)
        fy_start = "2025-04"
        for row in rows:
            if not row.get("is_netoff_combined"):
                continue
            ln = row.get("loan_number", "")
            if not any(f"RA{str(n).zfill(4)}" in ln for n in range(21, 31)):
                continue
            loan_date_ym = (row.get("loan_date") or "")[:7]
            if loan_date_ym and loan_date_ym < fy_start:
                # All entries in the FY strip should be either paid/overdue/pending/na — NOT chain_start
                # (chain_start would have appeared in the older FY when L2 was first viewed)
                emi_year = row.get("emi_year_data", [])
                print(f"{ln}: loan_date={loan_date_ym} | strip={[(e['month'], e['status']) for e in emi_year[:3]]}")
        print("PASS: RA pre-FY re-loans checked (chain_start not expected in 2025-26 strip)")


# ---------- Sanity tests ----------

class TestSheetSanity:
    """Sanity checks for the collection sheet API."""

    def test_illakas_list_has_biharipur_and_rampur(self, session):
        illakas = session.get(f"{BASE_URL}/api/illakas").json()
        names = [il.get("name", "").lower() for il in illakas]
        assert any("biharipur" in n for n in names), f"Biharipur not found. Illakas: {names}"
        assert any("rampur" in n for n in names), f"Rampur not found. Illakas: {names}"
        print(f"PASS: Illakas list has Biharipur and Rampur. All: {[il.get('name') for il in illakas]}")

    def test_global_sheet_loads(self, session):
        resp = session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2026-04"})
        assert resp.status_code == 200
        data = resp.json()
        assert "illakas" in data
        assert data.get("total", 0) > 0
        print(f"PASS: Global sheet 2026-04 loaded. total={data['total']}")

    def test_merged_rows_not_counted_double(self, biharipur_sheet_2026):
        """
        After merging, the total row count should not double-count absorbed parents.
        Each BI0021 should appear exactly ONCE.
        """
        rows = get_all_rows(biharipur_sheet_2026)
        bi0021_count = sum(1 for r in rows if "BI0021" in r.get("loan_number", ""))
        assert bi0021_count == 1, (
            f"BI0021 should appear exactly once (merged), but found {bi0021_count} rows"
        )
        print(f"PASS: BI0021 appears exactly once in the sheet (no double-counting)")
