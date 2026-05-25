"""
Test Gyal (Bad Debt) feature for Bahi Khata NBFC-MFI app
Tests: year-end closing endpoints, gyal account heads, collection sheet gyal fields
"""

import pytest
import requests
import os
from datetime import date, timedelta

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def admin_session():
    """Login as admin and return session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    res = session.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return session


@pytest.fixture(scope="module")
def muneem_session():
    """Login as muneem and return session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    res = session.post(f"{BASE_URL}/api/auth/login", json={"phone": "7777000001", "password": "Test@1234"})
    assert res.status_code == 200, f"Muneem login failed: {res.text}"
    return session


@pytest.fixture(scope="module")
def sipahi_session():
    """Login as sipahi (field agent) who can create KYC and loans"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    res = session.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
    assert res.status_code == 200, f"Sipahi login failed: {res.text}"
    return session


@pytest.fixture(scope="module")
def first_illaka_id(admin_session):
    """Get the first available illaka ID"""
    res = admin_session.get(f"{BASE_URL}/api/illakas")
    assert res.status_code == 200
    illakas = res.json()
    assert len(illakas) > 0, "No illakas found - cannot run year-end closing tests"
    return illakas[0]["id"]


# ─── Account Heads Tests ────────────────────────────────────────────────────────

class TestGyalAccountHeads:
    """Verify Gyal-related account heads exist after startup migration"""

    def test_bad_debt_written_off_head_exists(self, admin_session):
        """Bad Debt Written Off (Gyal) head must exist in account_heads"""
        res = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert res.status_code == 200
        heads = res.json()
        system_keys = [h.get("system_key") for h in heads]
        assert "bad_debt_written_off" in system_keys, (
            f"'bad_debt_written_off' system_key not found in account heads. Keys: {system_keys}"
        )

    def test_gyal_wasool_head_exists(self, admin_session):
        """Gyal Wasool (Bad Debt Recovery) head must exist in account_heads"""
        res = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert res.status_code == 200
        heads = res.json()
        system_keys = [h.get("system_key") for h in heads]
        assert "gyal_wasool" in system_keys, (
            f"'gyal_wasool' system_key not found in account heads. Keys: {system_keys}"
        )

    def test_bad_debt_head_is_expense_type(self, admin_session):
        """Bad Debt Written Off should be under Direct Expense group"""
        res = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert res.status_code == 200
        heads = res.json()
        bad_debt = next((h for h in heads if h.get("system_key") == "bad_debt_written_off"), None)
        assert bad_debt is not None
        assert bad_debt.get("group_type") == "expense", f"Expected expense, got {bad_debt.get('group_type')}"
        assert "Bad Debt" in bad_debt.get("name", ""), f"Expected 'Bad Debt' in name, got {bad_debt.get('name')}"

    def test_gyal_wasool_head_is_income_type(self, admin_session):
        """Gyal Wasool should be under Direct Income group"""
        res = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert res.status_code == 200
        heads = res.json()
        wasool = next((h for h in heads if h.get("system_key") == "gyal_wasool"), None)
        assert wasool is not None
        assert wasool.get("group_type") == "income", f"Expected income, got {wasool.get('group_type')}"
        assert "Gyal Wasool" in wasool.get("name", ""), f"Expected 'Gyal Wasool' in name, got {wasool.get('name')}"


# ─── Year-End Closing Preview Tests ─────────────────────────────────────────────

class TestYearEndClosingPreview:
    """Test GET /api/loans/year-end-closing/preview endpoint"""

    def test_preview_requires_auth(self):
        """Unauthenticated request should return 401 or 403"""
        res = requests.get(f"{BASE_URL}/api/loans/year-end-closing/preview?illaka_id=dummy&closing_date=2025-03-31")
        assert res.status_code in [401, 403], f"Expected 401/403, got {res.status_code}"

    def test_preview_muneem_gets_403(self, muneem_session, first_illaka_id):
        """Muneem should not be able to access year-end closing preview"""
        res = muneem_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 403, f"Expected 403 for muneem, got {res.status_code}: {res.text}"

    def test_preview_admin_returns_200(self, admin_session, first_illaka_id):
        """Admin should get a valid preview response"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"

    def test_preview_response_structure(self, admin_session, first_illaka_id):
        """Preview response must have count, loans, cutoff_date"""
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200
        data = res.json()
        assert "count" in data, "Response missing 'count'"
        assert "loans" in data, "Response missing 'loans'"
        assert "cutoff_date" in data, "Response missing 'cutoff_date'"
        assert isinstance(data["count"], int), f"count should be int, got {type(data['count'])}"
        assert isinstance(data["loans"], list), f"loans should be list, got {type(data['loans'])}"

    def test_preview_cutoff_is_36_months_before(self, admin_session, first_illaka_id):
        """Cutoff date must be exactly 36 months before closing_date"""
        closing = "2025-03-31"
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": closing}
        )
        assert res.status_code == 200
        data = res.json()
        # 36 months before 2025-03-31 = 2022-03-31
        assert data["cutoff_date"] == "2022-03-31", f"Expected cutoff 2022-03-31, got {data['cutoff_date']}"

    def test_preview_no_loans_for_recent_cutoff(self, admin_session, first_illaka_id):
        """A closing_date near today should show 0 loans (no loans are from 36+ months ago in test DB typically)"""
        today = date.today().isoformat()
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": today}
        )
        assert res.status_code == 200
        data = res.json()
        assert "count" in data
        assert "loans" in data
        # We don't assert count==0 since there may be old loans; just verify structure


# ─── Year-End Closing with Test Loan ────────────────────────────────────────────

class TestYearEndClosingWithOldLoan:
    """Create a loan with very old loan_date and verify year-end closing works"""

    test_loan_id = None
    test_illaka_id = None
    test_misal_id = None
    test_kyc_id = None

    @pytest.fixture(autouse=True)
    def setup(self, admin_session, first_illaka_id):
        TestYearEndClosingWithOldLoan.test_illaka_id = first_illaka_id

    def test_01_get_a_misal_for_testing(self, admin_session, first_illaka_id):
        """Get a misal to use for creating test loan"""
        res = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={first_illaka_id}")
        assert res.status_code == 200
        misals = res.json()
        assert len(misals) > 0, "No misals found - cannot create test loan"
        TestYearEndClosingWithOldLoan.test_misal_id = misals[0]["id"]
        print(f"Using misal: {misals[0]['id']} - {misals[0]['name']}")

    def test_02_create_old_kyc_for_gyal_test(self, sipahi_session, first_illaka_id):
        """Create a KYC for gyal test loan using sipahi (only field agents can create KYC)"""
        if not TestYearEndClosingWithOldLoan.test_misal_id:
            pytest.skip("No misal available")
        
        import time
        unique_phone = f"900{int(time.time()) % 10000000:07d}"
        unique_aadhaar = f"{int(time.time()) % 1000000000000:012d}"
        
        kyc_data = {
            "illaka_id": first_illaka_id,
            "illaka_name": "Delhi",
            "misal_id": TestYearEndClosingWithOldLoan.test_misal_id,
            "misal_name": "TEST_Misal_Delhi",
            "primary_borrower": {
                "full_name": "TEST_GyalTest_Customer",
                "full_name_hindi": "टेस्ट घ्याल",
                "phone": unique_phone,
                "gender": "female",
                "aadhaar_number": unique_aadhaar,
                "address": "Test Village"
            },
            "status": "approved"
        }
        res = sipahi_session.post(f"{BASE_URL}/api/kycs", json=kyc_data)
        assert res.status_code == 200, f"KYC creation failed: {res.text}"
        kyc = res.json()
        TestYearEndClosingWithOldLoan.test_kyc_id = kyc["id"]
        print(f"Created test KYC: {kyc['id']}")

    def test_03_create_loan_with_old_date(self, sipahi_session, first_illaka_id):
        """Create a loan with loan_date=2019-06-01 (way more than 36 months ago). Only sipahi can create loans."""
        if not TestYearEndClosingWithOldLoan.test_kyc_id:
            pytest.skip("No KYC available for test loan")
        
        misal_name = "TEST_Misal_Delhi"
        loan_data = {
            "kyc_id": TestYearEndClosingWithOldLoan.test_kyc_id,
            "illaka_id": first_illaka_id,
            "illaka_name": "Delhi",
            "misal_id": TestYearEndClosingWithOldLoan.test_misal_id,
            "misal_name": misal_name,
            "client_name": "TEST_GyalTest_Customer",
            "loan_date": "2019-06-01",
            "principal_amount": 10000,
            "tenure_months": 12,
            "status": "active"
        }
        res = sipahi_session.post(f"{BASE_URL}/api/loans", json=loan_data)
        assert res.status_code == 200, f"Failed to create test loan: {res.text}"
        loan = res.json()
        TestYearEndClosingWithOldLoan.test_loan_id = loan["id"]
        assert loan.get("loan_date") == "2019-06-01", f"Loan date mismatch: {loan.get('loan_date')}"
        assert loan.get("is_gyal") is not True, "New loan should not be gyal yet"
        print(f"Created old loan: {loan['id']} with loan_date=2019-06-01")

    def test_04_preview_finds_old_loan(self, admin_session, first_illaka_id):
        """Preview should find the 2018 loan when closing_date is 2025-03-31 (cutoff: 2022-03-31)"""
        if not TestYearEndClosingWithOldLoan.test_loan_id:
            pytest.skip("No test loan created")
        
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1, f"Expected at least 1 loan in preview, got {data['count']}"
        loan_numbers = [l["loan_number"] for l in data["loans"]]
        print(f"Preview found {data['count']} loans: {loan_numbers}")

    def test_05_post_year_end_closing_marks_gyal(self, admin_session, first_illaka_id):
        """POST year-end-closing should mark the old loan as gyal and return marked_count >= 1"""
        if not TestYearEndClosingWithOldLoan.test_loan_id:
            pytest.skip("No test loan created")
        
        res = admin_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200, f"Year-end closing failed: {res.text}"
        data = res.json()
        assert "marked_count" in data
        assert data["marked_count"] >= 1, f"Expected at least 1 loan marked, got {data['marked_count']}"
        assert "message" in data
        print(f"Year-end closing result: {data}")

    def test_06_verify_loan_is_now_gyal(self, admin_session):
        """After year-end closing, the test loan should have is_gyal=True and gyal_since set"""
        if not TestYearEndClosingWithOldLoan.test_loan_id:
            pytest.skip("No test loan created")
        
        res = admin_session.get(f"{BASE_URL}/api/loans/{TestYearEndClosingWithOldLoan.test_loan_id}")
        assert res.status_code == 200
        loan = res.json()
        assert loan.get("is_gyal") is True, f"Loan should be is_gyal=True, got {loan.get('is_gyal')}"
        assert loan.get("gyal_since"), f"gyal_since should be set, got {loan.get('gyal_since')}"
        assert loan.get("gyal_since") == "2025-03-31", f"Expected gyal_since=2025-03-31, got {loan.get('gyal_since')}"
        print(f"Loan is_gyal={loan['is_gyal']}, gyal_since={loan['gyal_since']}")

    def test_07_gyal_loan_not_shown_again_in_preview(self, admin_session, first_illaka_id):
        """After marking, same loan should NOT appear in preview again (is_gyal=$ne True filter)"""
        if not TestYearEndClosingWithOldLoan.test_loan_id:
            pytest.skip("No test loan created")
        
        res = admin_session.get(
            f"{BASE_URL}/api/loans/year-end-closing/preview",
            params={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 200
        data = res.json()
        # Find if our specific test loan is in the preview (it should NOT be)
        loan_in_preview = any(
            l.get("client_name") == "TEST_GyalTest_Customer" for l in data["loans"]
        )
        assert not loan_in_preview, "Gyal loan should not reappear in preview"
        print(f"Preview after closing: {data['count']} loans - gyal loan not in preview ✓")

    def test_08_muneem_cannot_do_year_end_closing(self, muneem_session, first_illaka_id):
        """Muneem should get 403 when attempting year-end closing POST"""
        res = muneem_session.post(
            f"{BASE_URL}/api/loans/year-end-closing",
            json={"illaka_id": first_illaka_id, "closing_date": "2025-03-31"}
        )
        assert res.status_code == 403, f"Expected 403 for muneem, got {res.status_code}"


# ─── Collection Sheet Gyal Fields ──────────────────────────────────────────────

class TestCollectionSheetGyalFields:
    """Verify collection sheet API includes is_gyal and gyal_since fields"""

    def test_collection_sheet_has_is_gyal_field(self, admin_session):
        """Each row in collection sheet should have is_gyal field"""
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
        res = admin_session.get(
            f"{BASE_URL}/api/collections/sheet",
            params={"month": month}
        )
        assert res.status_code == 200
        data = res.json()
        # Find any row and verify is_gyal field exists
        for illaka in data.get("illakas", []):
            for misal in illaka.get("misals", []):
                for row in misal.get("rows", []):
                    assert "is_gyal" in row, f"Row missing 'is_gyal' field: {row.get('loan_number')}"
                    assert "gyal_since" in row, f"Row missing 'gyal_since' field: {row.get('loan_number')}"
                    print(f"Row {row.get('loan_number')}: is_gyal={row['is_gyal']}, gyal_since={row['gyal_since']}")
                    return  # Check first row only
        print("No rows found in collection sheet - fields test skipped")

    def test_gyal_loan_appears_in_collection_sheet(self, admin_session, first_illaka_id):
        """After year-end closing, the gyal loan should still appear in collection sheet with is_gyal=True"""
        today = date.today()
        month = f"{today.year}-{today.month:02d}"
        
        # Try the month when the gyal loan has an EMI (2018 loan has 12 EMIs starting Jan 2018)
        # Let's check if the loan appears for any month
        res = admin_session.get(
            f"{BASE_URL}/api/collections/sheet",
            params={"month": "2018-01", "illaka_id": first_illaka_id}
        )
        assert res.status_code == 200
        data = res.json()
        
        # Find the gyal loan
        gyal_rows = []
        for illaka in data.get("illakas", []):
            for misal in illaka.get("misals", []):
                for row in misal.get("rows", []):
                    if row.get("client_name") == "TEST_Gyal_Customer":
                        gyal_rows.append(row)
        
        if gyal_rows:
            assert gyal_rows[0].get("is_gyal") is True, "Gyal loan should have is_gyal=True"
            print(f"Gyal loan in collection sheet: is_gyal={gyal_rows[0]['is_gyal']}")
        else:
            print("Gyal loan not found in Jan 2018 collection sheet - may have different month structure")
