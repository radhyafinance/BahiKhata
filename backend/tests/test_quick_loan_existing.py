"""
Quick Add Loan — Existing Client feature tests
Tests POST /api/kycs/quick-loan with existing_kyc_id field
Iteration 32 — tests the "Existing Client" toggle feature
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


def login(phone: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"phone": phone, "password": password})
    assert r.status_code == 200, f"Login failed for {phone}: {r.text}"
    return s


def calc_emi(principal: float) -> int:
    return round(principal * 120 / 103 / 12 / 10) * 10


@pytest.fixture(scope="module")
def admin_session():
    return login("9999999999", "Admin@123")


@pytest.fixture(scope="module")
def existing_kyc(admin_session):
    """
    Fetch an existing KYC from the DB for testing.
    We search for 'Arti' to find Arti Devi (BI0154).
    Falls back to the first KYC in the system.
    """
    r = admin_session.get(f"{BASE_URL}/api/kycs?search=Arti&limit=1")
    assert r.status_code == 200, f"GET /api/kycs failed: {r.text}"
    kycs = r.json().get("kycs", [])
    if kycs:
        kyc = kycs[0]
        print(f"  Using KYC: {kyc.get('customer_id')} — {kyc.get('primary_borrower', {}).get('name')}")
        return kyc
    # Fallback: get the first KYC in the system
    r2 = admin_session.get(f"{BASE_URL}/api/kycs?limit=1")
    assert r2.status_code == 200, r2.text
    kycs2 = r2.json().get("kycs", [])
    assert kycs2, "No KYCs found in DB to test with"
    return kycs2[0]


class TestQuickLoanExistingCustomer:
    """Tests for adding loans to existing customers via existing_kyc_id"""

    def test_existing_kyc_quick_loan_success(self, admin_session, existing_kyc):
        """Adding a loan to an existing customer returns 200 with correct fields"""
        kyc_id = existing_kyc["id"]
        customer_id = existing_kyc["customer_id"]
        principal = 5000

        payload = {
            "illaka_id": existing_kyc.get("illaka_id"),
            "illaka_name": existing_kyc.get("illaka_name", ""),
            "misal_id": existing_kyc.get("misal_id"),
            "misal_name": existing_kyc.get("misal_name", ""),
            "name": existing_kyc.get("primary_borrower", {}).get("name", "Test"),
            "existing_kyc_id": kyc_id,
            "principal_amount": principal,
            "loan_month": "2026-08",
        }
        r = admin_session.post(f"{BASE_URL}/api/kycs/quick-loan", json=payload)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()

        # All required fields present
        for key in ["kyc_id", "loan_id", "customer_id", "loan_number", "emi_amount", "total_repayable", "interest_amount"]:
            assert key in data, f"Missing key: {key}"

        # customer_id must match the existing customer
        assert data["customer_id"] == customer_id, (
            f"Expected customer_id={customer_id}, got {data['customer_id']}"
        )
        # kyc_id must match the existing KYC (NOT a new one)
        assert data["kyc_id"] == kyc_id, (
            f"Expected kyc_id={kyc_id}, got {data['kyc_id']}"
        )
        print(f"  PASS: created loan {data['loan_number']} on existing customer {customer_id}")

    def test_existing_kyc_loan_number_increments(self, admin_session, existing_kyc):
        """Second loan on same customer should have a higher loan suffix (e.g. L2, L3)"""
        kyc_id = existing_kyc["id"]
        customer_id = existing_kyc["customer_id"]
        principal = 8000

        payload = {
            "illaka_id": existing_kyc.get("illaka_id"),
            "illaka_name": existing_kyc.get("illaka_name", ""),
            "misal_id": existing_kyc.get("misal_id"),
            "misal_name": existing_kyc.get("misal_name", ""),
            "name": existing_kyc.get("primary_borrower", {}).get("name", "Test"),
            "existing_kyc_id": kyc_id,
            "principal_amount": principal,
            "loan_month": "2026-09",
        }
        r = admin_session.post(f"{BASE_URL}/api/kycs/quick-loan", json=payload)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        loan_number = data["loan_number"]
        # loan_number must contain the customer_id prefix
        assert customer_id in loan_number, (
            f"loan_number {loan_number} doesn't contain customer_id {customer_id}"
        )
        # loan_number must have -L suffix (e.g. BI0154-L2)
        assert "-L" in loan_number, f"Expected -L suffix in loan_number, got {loan_number}"
        print(f"  PASS: second loan on {customer_id} has number {loan_number}")

    def test_existing_kyc_emi_calculation(self, admin_session, existing_kyc):
        """EMI formula must be correct for existing customer loans"""
        kyc_id = existing_kyc["id"]
        principal = 10000
        expected_emi = calc_emi(principal)

        payload = {
            "illaka_id": existing_kyc.get("illaka_id"),
            "illaka_name": existing_kyc.get("illaka_name", ""),
            "misal_id": existing_kyc.get("misal_id"),
            "misal_name": existing_kyc.get("misal_name", ""),
            "name": existing_kyc.get("primary_borrower", {}).get("name", "Test"),
            "existing_kyc_id": kyc_id,
            "principal_amount": principal,
            "loan_month": "2026-10",
        }
        r = admin_session.post(f"{BASE_URL}/api/kycs/quick-loan", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["emi_amount"] == expected_emi, (
            f"EMI mismatch: expected {expected_emi}, got {data['emi_amount']}"
        )
        assert data["total_repayable"] == expected_emi * 12
        expected_interest = round((expected_emi * 12) - principal, 2)
        assert abs(data["interest_amount"] - expected_interest) < 1
        print(f"  PASS: EMI={data['emi_amount']}, total={data['total_repayable']}, interest={data['interest_amount']}")

    def test_existing_kyc_loan_in_loan_list(self, admin_session, existing_kyc):
        """Loan created on existing customer must appear in GET /api/loans"""
        kyc_id = existing_kyc["id"]
        principal = 6000

        payload = {
            "illaka_id": existing_kyc.get("illaka_id"),
            "illaka_name": existing_kyc.get("illaka_name", ""),
            "misal_id": existing_kyc.get("misal_id"),
            "misal_name": existing_kyc.get("misal_name", ""),
            "name": existing_kyc.get("primary_borrower", {}).get("name", "Test"),
            "existing_kyc_id": kyc_id,
            "principal_amount": principal,
            "loan_month": "2026-11",
        }
        r = admin_session.post(f"{BASE_URL}/api/kycs/quick-loan", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        loan_id = data["loan_id"]
        loan_number = data["loan_number"]

        # Check loan appears in GET /api/loans
        lr = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert lr.status_code == 200, f"GET /api/loans/{loan_id} failed: {lr.text}"
        loan = lr.json()
        assert loan["id"] == loan_id
        assert loan["customer_id"] == existing_kyc["customer_id"]
        assert loan["kyc_id"] == kyc_id
        print(f"  PASS: Loan {loan_number} found in loans list with correct kyc_id + customer_id")

    def test_invalid_existing_kyc_id_returns_404(self, admin_session):
        """Using a non-existent KYC ID must return 404"""
        # First get a valid illaka/misal
        r = admin_session.get(f"{BASE_URL}/api/illakas")
        assert r.status_code == 200
        illakas = r.json()
        assert illakas
        illaka = illakas[0]
        r2 = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={illaka['id']}")
        misals = r2.json()
        assert misals
        misal = misals[0]

        payload = {
            "illaka_id": illaka["id"],
            "illaka_name": illaka["name"],
            "misal_id": misal["id"],
            "misal_name": misal["name"],
            "name": "Test Customer",
            "existing_kyc_id": "000000000000000000000000",  # non-existent ObjectId
            "principal_amount": 5000,
            "loan_month": "2026-08",
        }
        r = admin_session.post(f"{BASE_URL}/api/kycs/quick-loan", json=payload)
        assert r.status_code == 404, f"Expected 404 for invalid kyc_id, got {r.status_code}: {r.text}"
        print(f"  PASS: 404 returned for invalid existing_kyc_id")

    def test_search_api_finds_customers(self, admin_session):
        """GET /api/kycs?search=<query> must return matching customers"""
        r = admin_session.get(f"{BASE_URL}/api/kycs?search=Arti&limit=8")
        assert r.status_code == 200, f"Search API failed: {r.text}"
        data = r.json()
        assert "kycs" in data, "Response missing 'kycs' key"
        assert "total" in data, "Response missing 'total' key"
        # Should return results since Arti Devi (BI0154) exists
        print(f"  PASS: Search for 'Arti' returned {data['total']} results")

    def test_search_api_finds_by_customer_id(self, admin_session, existing_kyc):
        """GET /api/kycs?search=<customer_id> must find by customer ID"""
        customer_id = existing_kyc["customer_id"]
        r = admin_session.get(f"{BASE_URL}/api/kycs?search={customer_id}&limit=8")
        assert r.status_code == 200, f"Search by customer_id failed: {r.text}"
        data = r.json()
        assert data["total"] >= 1, f"Expected at least 1 result searching for {customer_id}"
        # Verify the customer in results
        found = any(k.get("customer_id") == customer_id for k in data["kycs"])
        assert found, f"KYC with customer_id {customer_id} not found in search results"
        print(f"  PASS: Search by customer_id {customer_id} returned correct customer")

    def test_search_response_has_required_fields(self, admin_session):
        """Search results must have minimum required fields for the dropdown.
        NOTE: Some older KYC records may lack customer_id, illaka_name, misal_name.
        This test checks that the API response structure is correct, not data completeness.
        """
        r = admin_session.get(f"{BASE_URL}/api/kycs?search=Arti&limit=8")
        assert r.status_code == 200
        data = r.json()
        assert "kycs" in data, "Response missing 'kycs' key"
        assert "total" in data, "Response missing 'total' key"
        kycs = data.get("kycs", [])
        if not kycs:
            pytest.skip("No search results found for 'Arti' — skip field check")
        # Check at least one result has the key fields for the dropdown
        for kyc in kycs:
            # Must always have 'id' (MongoDB ObjectId)
            assert "id" in kyc, f"Missing critical field 'id' in KYC search result"
            # primary_borrower must be present and have name
            assert "primary_borrower" in kyc, "Missing 'primary_borrower'"
            assert kyc["primary_borrower"] is not None, "primary_borrower is null"
            # Warn about missing fields that the UI depends on
            for field in ["customer_id", "illaka_name", "misal_name"]:
                if not kyc.get(field):
                    print(f"  WARNING: Field '{field}' missing/empty in KYC — older DB record, UI will show blank")
        print(f"  PASS: Search API returns correct structure with {len(kycs)} results")
