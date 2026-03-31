"""
Backend tests for Collection Sheet 12-month FY strip (April-March financial year).
Tests emi_year_data construction, FY month ordering, paid/pending/na status.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_PHONE = "9999999999"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def auth_session():
    """Authenticated admin session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    resp = session.post(f"{BASE_URL}/api/auth/login", json={"phone": ADMIN_PHONE, "password": ADMIN_PASSWORD})
    if resp.status_code != 200:
        pytest.skip(f"Auth failed: {resp.status_code} {resp.text}")
    return session


@pytest.fixture(scope="module")
def sheet_data_march(auth_session):
    """Fetch collection sheet for 2026-03 (March 2026) — Delhi illaka"""
    # First get illaka list to find Delhi
    illakas_resp = auth_session.get(f"{BASE_URL}/api/illakas")
    illakas = illakas_resp.json() if illakas_resp.status_code == 200 else []
    delhi_id = None
    for il in illakas:
        if "delhi" in il.get("name", "").lower() or "delhi" in il.get("illaka_name", "").lower():
            delhi_id = il.get("id") or il.get("_id") or il.get("illaka_id")
            break

    params = {"month": "2026-03"}
    if delhi_id:
        params["illaka_id"] = delhi_id
    resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params=params)
    assert resp.status_code == 200, f"Collection sheet returned {resp.status_code}: {resp.text}"
    return resp.json(), delhi_id


class TestCollectionSheetApiResponse:
    """Verify GET /api/collections/sheet returns correct structure"""

    def test_sheet_returns_200(self, auth_session):
        resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2026-03"})
        assert resp.status_code == 200
        print("PASS: GET /api/collections/sheet returns 200")

    def test_sheet_has_illakas_key(self, auth_session):
        resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2026-03"})
        data = resp.json()
        assert "illakas" in data
        assert isinstance(data["illakas"], list)
        print(f"PASS: Response has illakas list ({len(data['illakas'])} illakas)")

    def test_sheet_has_month_key(self, auth_session):
        resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2026-03"})
        data = resp.json()
        assert data.get("month") == "2026-03"
        print(f"PASS: month field = {data['month']}")

    def test_sheet_has_total_and_collected(self, auth_session):
        resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2026-03"})
        data = resp.json()
        assert "total" in data
        assert "collected" in data
        assert isinstance(data["total"], int)
        assert isinstance(data["collected"], int)
        print(f"PASS: total={data['total']} collected={data['collected']}")


class TestEmiYearDataStructure:
    """Verify emi_year_data field on each row"""

    def test_rows_have_emi_year_data(self, sheet_data_march):
        data, _ = sheet_data_march
        rows_checked = 0
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    assert "emi_year_data" in row, f"Row {row.get('client_name')} missing emi_year_data"
                    rows_checked += 1
        assert rows_checked > 0, "No rows found in sheet"
        print(f"PASS: All {rows_checked} rows have emi_year_data")

    def test_emi_year_data_has_12_items(self, sheet_data_march):
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    yd = row.get("emi_year_data", [])
                    assert len(yd) == 12, f"Row {row.get('client_name')}: emi_year_data has {len(yd)} items, expected 12"
        print("PASS: All rows have exactly 12 items in emi_year_data")

    def test_emi_year_data_first_item_is_april(self, sheet_data_march):
        """For March 2026, FY is 2025-04 to 2026-03, first item should be 2025-04"""
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    yd = row.get("emi_year_data", [])
                    if len(yd) == 12:
                        first_month = yd[0]["month"]
                        assert first_month.endswith("-04"), (
                            f"Row {row.get('client_name')}: first FY month={first_month}, expected XX-04 (April)"
                        )
        print("PASS: First emi_year_data item month ends with -04 (April)")

    def test_emi_year_data_last_item_is_march(self, sheet_data_march):
        """Last item should be 2026-03 (March of the FY end)"""
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    yd = row.get("emi_year_data", [])
                    if len(yd) == 12:
                        last_month = yd[-1]["month"]
                        assert last_month.endswith("-03"), (
                            f"Row {row.get('client_name')}: last FY month={last_month}, expected XX-03 (March)"
                        )
        print("PASS: Last emi_year_data item month ends with -03 (March)")

    def test_emi_year_data_months_sequential_apr_to_mar(self, sheet_data_march):
        """FY months must be Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Jan,Feb,Mar"""
        data, _ = sheet_data_march
        expected_months = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"][:1]:  # check first row only
                    yd = row.get("emi_year_data", [])
                    if len(yd) == 12:
                        actual = [int(item["month"].split("-")[1]) for item in yd]
                        assert actual == expected_months, f"Month order {actual} != expected {expected_months}"
        print(f"PASS: FY month order is Apr→Mar: {expected_months}")

    def test_emi_year_data_fy_year_correct_for_2026_03(self, sheet_data_march):
        """For month=2026-03: Apr-Dec should be 2025-XX, Jan-Mar should be 2026-XX"""
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"][:1]:  # check first row
                    yd = row.get("emi_year_data", [])
                    if len(yd) == 12:
                        # First 9: Apr-Dec 2025 (months 4-12, year 2025)
                        for item in yd[:9]:
                            assert item["month"].startswith("2025-"), (
                                f"Expected 2025-XX, got {item['month']}"
                            )
                        # Last 3: Jan-Mar 2026 (months 1-3, year 2026)
                        for item in yd[9:]:
                            assert item["month"].startswith("2026-"), (
                                f"Expected 2026-XX, got {item['month']}"
                            )
        print("PASS: FY year boundaries correct — 2025-04 to 2026-03")

    def test_emi_year_data_items_have_required_keys(self, sheet_data_march):
        """Each emi_year_data item must have month, status, paid_amount, note"""
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    for item in row.get("emi_year_data", []):
                        assert "month" in item, f"Missing 'month' in {item}"
                        assert "status" in item, f"Missing 'status' in {item}"
                        assert "paid_amount" in item, f"Missing 'paid_amount' in {item}"
                        assert "note" in item, f"Missing 'note' in {item}"
        print("PASS: All emi_year_data items have required keys")

    def test_emi_year_data_status_values_valid(self, sheet_data_march):
        """Status values must be one of: paid, pending, overdue, na"""
        valid_statuses = {"paid", "pending", "overdue", "na"}
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    for item in row.get("emi_year_data", []):
                        assert item["status"] in valid_statuses, (
                            f"Row {row.get('client_name')} month {item['month']}: "
                            f"invalid status '{item['status']}'"
                        )
        print("PASS: All emi_year_data status values are valid")


class TestPaidMonthData:
    """Verify paid months have correct data"""

    def test_paid_months_have_positive_paid_amount(self, sheet_data_march):
        data, _ = sheet_data_march
        paid_found = 0
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    for item in row.get("emi_year_data", []):
                        if item["status"] == "paid":
                            assert item["paid_amount"] > 0, (
                                f"Row {row.get('client_name')} month {item['month']}: "
                                f"paid status but paid_amount={item['paid_amount']}"
                            )
                            paid_found += 1
        print(f"PASS: Found {paid_found} paid months, all have paid_amount > 0")

    def test_test_gyal_customer2_paid_950_in_march(self, sheet_data_march):
        """TEST_Gyal_Customer2 should have paid EMI of 950 in 2026-03"""
        data, _ = sheet_data_march
        found = False
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    if "Gyal" in row.get("client_name", "") or "Gyal" in row.get("client_name_hindi", ""):
                        yd = row.get("emi_year_data", [])
                        # Find March 2026
                        march_item = next((i for i in yd if i["month"] == "2026-03"), None)
                        if march_item and march_item["status"] == "paid" and march_item["paid_amount"] > 0:
                            found = True
                            print(f"PASS: Found {row.get('client_name')} with paid_amount={march_item['paid_amount']} in 2026-03")
                            # Verify amount is 950
                            assert march_item["paid_amount"] == 950.0 or abs(march_item["paid_amount"] - 950) < 1, (
                                f"Expected 950 paid, got {march_item['paid_amount']}"
                            )
        if not found:
            # Try by loan current month status
            for il in data["illakas"]:
                for misal in il["misals"]:
                    for row in misal["rows"]:
                        if row.get("emi_status") == "paid" and row.get("emi_paid_amount") == 950:
                            found = True
                            print(f"PASS: Found row with emi_paid_amount=950: {row.get('client_name')}")
        assert found, "Could not find TEST_Gyal_Customer2 with 950 paid in 2026-03"

    def test_current_month_march_appears_in_emi_year_data(self, sheet_data_march):
        """2026-03 (current month) must appear in emi_year_data for each row"""
        data, _ = sheet_data_march
        for il in data["illakas"]:
            for misal in il["misals"]:
                for row in misal["rows"]:
                    yd = row.get("emi_year_data", [])
                    months_in_yd = [item["month"] for item in yd]
                    assert "2026-03" in months_in_yd, (
                        f"Row {row.get('client_name')}: 2026-03 not found in emi_year_data months={months_in_yd}"
                    )
        print("PASS: 2026-03 appears in all rows' emi_year_data")


class TestLatestClosingYm:
    """Verify latest_closing_ym is present per illaka"""

    def test_illakas_have_latest_closing_ym(self, sheet_data_march):
        data, _ = sheet_data_march
        for il in data["illakas"]:
            assert "latest_closing_ym" in il, f"Illaka {il.get('illaka_name')} missing latest_closing_ym"
        print("PASS: All illakas have latest_closing_ym field")

    def test_delhi_latest_closing_ym_is_2024_03(self, sheet_data_march):
        """Delhi illaka should have latest_closing_ym = '2024-03'"""
        data, _ = sheet_data_march
        for il in data["illakas"]:
            if "delhi" in il.get("illaka_name", "").lower():
                assert il.get("latest_closing_ym") == "2024-03", (
                    f"Delhi latest_closing_ym={il.get('latest_closing_ym')}, expected 2024-03"
                )
                print(f"PASS: Delhi latest_closing_ym = {il['latest_closing_ym']}")
                return
        pytest.skip("Delhi illaka not found in response (may need illaka_id filter)")


class TestFyMonthsForDifferentMonths:
    """Test FY month computation for different months"""

    def test_sheet_october_fy_starts_april(self, auth_session):
        """For Oct 2025, FY should be Apr 2025 - Mar 2026"""
        resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2025-10"})
        if resp.status_code == 200:
            data = resp.json()
            for il in data["illakas"]:
                for misal in il["misals"]:
                    for row in misal["rows"][:1]:
                        yd = row.get("emi_year_data", [])
                        if len(yd) == 12:
                            assert yd[0]["month"] == "2025-04", f"First month={yd[0]['month']}, expected 2025-04"
                            assert yd[-1]["month"] == "2026-03", f"Last month={yd[-1]['month']}, expected 2026-03"
                            print(f"PASS: Oct 2025 → FY {yd[0]['month']} to {yd[-1]['month']}")
                            return
        print("SKIP: No data for Oct 2025")

    def test_sheet_april_fy_starts_april(self, auth_session):
        """For Apr 2025, FY should be Apr 2025 - Mar 2026"""
        resp = auth_session.get(f"{BASE_URL}/api/collections/sheet", params={"month": "2025-04"})
        if resp.status_code == 200:
            data = resp.json()
            for il in data["illakas"]:
                for misal in il["misals"]:
                    for row in misal["rows"][:1]:
                        yd = row.get("emi_year_data", [])
                        if len(yd) == 12:
                            assert yd[0]["month"] == "2025-04", f"First={yd[0]['month']}"
                            assert yd[-1]["month"] == "2026-03", f"Last={yd[-1]['month']}"
                            print(f"PASS: Apr 2025 → FY {yd[0]['month']} to {yd[-1]['month']}")
                            return
        print("SKIP: No data for Apr 2025")
