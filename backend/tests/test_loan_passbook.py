"""
Backend tests for Loan Passbook feature:
- GET /api/loans?kyc_id={id} filtering
- kyc_id filter for admin and sipahi roles
- Collect (POST /api/loans/{id}/payments) and Undo (DELETE) flows
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "admin@bahikhata.com"
ADMIN_PASS = "Admin@123"
SIPAHI_EMAIL = "TEST_sipahi_loans@bahikhata.com"
SIPAHI_PASS = "Test@1234"

# Known KYC that has loan DE0019-L1 (₹12,000 active)
KNOWN_KYC_ID = "69c7a5bd39829d51f492f556"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    if resp.status_code != 200:
        pytest.skip(f"Admin login failed: {resp.status_code} {resp.text}")
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    """Authenticated sipahi session"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": SIPAHI_EMAIL, "password": SIPAHI_PASS})
    if resp.status_code != 200:
        pytest.skip(f"Sipahi login failed: {resp.status_code} {resp.text}")
    return s


# ─── Health Check ─────────────────────────────────────────────────────────────

class TestHealthCheck:
    """Verify backend is reachable"""

    def test_backend_reachable(self):
        # Backend doesn't have /api/health - test auth endpoint instead
        resp = requests.post(f"{BASE_URL}/api/auth/login",
                             json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert resp.status_code == 200, f"Backend not reachable: {resp.status_code}"
        print("PASS: Backend is reachable and auth works")


# ─── kyc_id Filter Tests ──────────────────────────────────────────────────────

class TestKycIdFilter:
    """GET /api/loans?kyc_id={id} - filtering by kyc_id"""

    def test_kyc_id_filter_admin_returns_loans(self, admin_session):
        """GET /api/loans?kyc_id=KNOWN_KYC_ID returns only that client's loans (admin)"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "loans" in data, "Response must have 'loans' key"
        assert "total" in data, "Response must have 'total' key"
        print(f"PASS: GET /api/loans?kyc_id={KNOWN_KYC_ID} returned {data['total']} loans")

        # All returned loans must have kyc_id == KNOWN_KYC_ID
        loans = data["loans"]
        assert len(loans) > 0, f"Expected at least 1 loan for kyc_id={KNOWN_KYC_ID}, got 0"
        for loan in loans:
            assert loan.get("kyc_id") == KNOWN_KYC_ID, \
                f"Loan {loan.get('id')} has wrong kyc_id: {loan.get('kyc_id')}"
        print(f"PASS: All {len(loans)} loans have matching kyc_id")

    def test_kyc_id_filter_returns_loan_number(self, admin_session):
        """Loan returned for KNOWN_KYC_ID has expected loan_number format"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        data = resp.json()
        loans = data["loans"]
        assert len(loans) >= 1

        # At least one should have a loan_number
        loan_numbers = [l.get("loan_number") for l in loans]
        assert any(ln for ln in loan_numbers), f"No loan_number found. Numbers: {loan_numbers}"
        print(f"PASS: Loan numbers found: {loan_numbers}")

    def test_kyc_id_filter_loan_has_emi_schedule(self, admin_session):
        """Loans returned include emi_schedule field with 12 entries"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        data = resp.json()
        loans = data["loans"]
        assert len(loans) >= 1

        loan = loans[0]
        assert "emi_schedule" in loan, f"Loan missing 'emi_schedule' key: {list(loan.keys())}"
        schedule = loan["emi_schedule"]
        assert isinstance(schedule, list), f"emi_schedule should be list, got {type(schedule)}"
        assert len(schedule) == 12, f"Expected 12 EMI entries, got {len(schedule)}"
        print(f"PASS: emi_schedule has {len(schedule)} entries")

    def test_kyc_id_filter_loan_has_required_fields(self, admin_session):
        """Loans returned include all required passbook fields"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        data = resp.json()
        loans = data["loans"]
        assert len(loans) >= 1

        loan = loans[0]
        required_fields = ["id", "loan_number", "status", "principal_amount", "emi_amount",
                           "total_paid", "total_repayable", "emi_schedule", "kyc_id"]
        missing = [f for f in required_fields if f not in loan]
        assert len(missing) == 0, f"Missing fields in loan response: {missing}"
        print(f"PASS: All required fields present: {required_fields}")

    def test_kyc_id_filter_unknown_returns_empty(self, admin_session):
        """GET /api/loans?kyc_id={unknown_id} returns empty list for non-existent KYC"""
        import uuid
        # Use a guaranteed-unique kyc_id that no loan will have
        # Combine random hex to ensure 24 chars valid MongoDB ObjectId-like string
        unique_fake_id = "ff" + uuid.uuid4().hex[:22]
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={unique_fake_id}&limit=20")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

        data = resp.json()
        assert "loans" in data
        assert data["total"] == 0, f"Expected 0 loans for unknown KYC '{unique_fake_id}', got {data['total']}"
        assert data["loans"] == [], f"Expected empty list, got {data['loans']}"
        print(f"PASS: Truly unique fake kyc_id returns 0 loans")

    def test_kyc_id_filter_not_mixing_other_kycs(self, admin_session):
        """Loans from other kyc_ids are NOT returned when kyc_id filter is set"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        data = resp.json()
        loans = data["loans"]
        # Ensure no loan has a different kyc_id
        wrong_loans = [l for l in loans if l.get("kyc_id") != KNOWN_KYC_ID]
        assert len(wrong_loans) == 0, \
            f"Found {len(wrong_loans)} loans with wrong kyc_id: {[l['kyc_id'] for l in wrong_loans]}"
        print("PASS: No cross-KYC contamination in filtered results")

    def test_kyc_id_filter_sipahi_can_access(self, sipahi_session):
        """Sipahi role can also filter loans by kyc_id"""
        resp = sipahi_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200, f"Sipahi got {resp.status_code}: {resp.text}"

        data = resp.json()
        assert "loans" in data
        print(f"PASS: Sipahi can filter loans by kyc_id, got {data['total']} results")

    def test_kyc_id_filter_unauthenticated_fails(self):
        """GET /api/loans?kyc_id=... without auth returns 401/403"""
        resp = requests.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code in [401, 403], \
            f"Expected 401/403 for unauthenticated request, got {resp.status_code}"
        print("PASS: Unauthenticated request rejected")


# ─── Loan Response Structure ──────────────────────────────────────────────────

class TestLoanResponseStructure:
    """Verify loan response has all fields needed for passbook display"""

    def test_loan_status_badge_values(self, admin_session):
        """Loan status is one of expected values"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        data = resp.json()
        loans = data["loans"]
        valid_statuses = {"active", "closed", "overdue", "pending"}

        for loan in loans:
            status = loan.get("status")
            assert status in valid_statuses, f"Unexpected status: {status}"
        print(f"PASS: All loans have valid status values")

    def test_emi_schedule_entry_structure(self, admin_session):
        """Each EMI entry has required fields for passbook table"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        loans = resp.json()["loans"]
        assert loans

        schedule = loans[0]["emi_schedule"]
        assert schedule

        first_emi = schedule[0]
        emi_required = ["month", "due_month", "amount", "status"]
        missing = [f for f in emi_required if f not in first_emi]
        assert len(missing) == 0, f"EMI entry missing fields: {missing}"

        # Verify valid EMI statuses
        valid_emi_statuses = {"pending", "paid", "overdue"}
        for emi in schedule:
            assert emi["status"] in valid_emi_statuses, f"Invalid EMI status: {emi['status']}"
        print(f"PASS: EMI schedule entries have all required fields")

    def test_loan_financial_fields_are_numbers(self, admin_session):
        """principal_amount, emi_amount, total_paid, total_repayable are numeric"""
        resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=20")
        assert resp.status_code == 200

        loans = resp.json()["loans"]
        assert loans

        loan = loans[0]
        numeric_fields = ["principal_amount", "emi_amount", "total_paid", "total_repayable"]
        for field in numeric_fields:
            val = loan.get(field)
            assert isinstance(val, (int, float)), \
                f"Field '{field}' should be numeric, got {type(val)}: {val}"
        print("PASS: All financial fields are numeric")


# ─── Payment (Collect / Undo) via Admin ──────────────────────────────────────

class TestCollectAndUndo:
    """Test POST /api/loans/{id}/payments and DELETE for passbook collect/undo"""

    def _get_first_loan(self, session):
        resp = session.get(f"{BASE_URL}/api/loans?kyc_id={KNOWN_KYC_ID}&limit=5")
        assert resp.status_code == 200
        loans = resp.json()["loans"]
        assert loans, "No loans found for test KYC"
        return loans[0]

    def test_get_loan_payments(self, admin_session):
        """GET /api/loans/{id}/payments returns list"""
        loan = self._get_first_loan(admin_session)
        loan_id = loan["id"]

        resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}/payments")
        assert resp.status_code == 200, f"GET payments failed: {resp.status_code} {resp.text}"
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"PASS: GET /api/loans/{loan_id}/payments returned {len(data)} payments")

    def test_collect_emi_and_verify(self, admin_session):
        """POST payment for a pending EMI, then verify it becomes paid in loan response"""
        loan = self._get_first_loan(admin_session)
        loan_id = loan["id"]
        schedule = loan.get("emi_schedule", [])

        # Find a pending EMI to collect
        pending_emis = [e for e in schedule if e["status"] == "pending"]
        if not pending_emis:
            pytest.skip("No pending EMIs available to collect - all may be paid already")

        emi = pending_emis[-1]  # Use last pending to avoid disrupting earliest
        emi_month = emi["due_month"]
        emi_amount = emi["amount"]

        print(f"  Collecting EMI month={emi_month}, amount={emi_amount} for loan={loan_id}")

        # POST payment
        resp = admin_session.post(
            f"{BASE_URL}/api/loans/{loan_id}/payments",
            json={"emi_month": emi_month, "amount": emi_amount, "payment_date": "2026-02-01"}
        )
        assert resp.status_code == 200, f"POST payment failed: {resp.status_code} {resp.text}"

        updated_loan = resp.json()
        assert "emi_schedule" in updated_loan, "Updated loan missing emi_schedule"

        # Verify the collected EMI is now paid
        emi_entry = next((e for e in updated_loan["emi_schedule"] if e["due_month"] == emi_month), None)
        assert emi_entry is not None, f"EMI for month {emi_month} not found in updated schedule"
        assert emi_entry["status"] == "paid", \
            f"EMI status after collection should be 'paid', got '{emi_entry['status']}'"

        print(f"PASS: EMI {emi_month} is now 'paid' after collection")

        # Undo the payment
        resp2 = admin_session.delete(f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}")
        assert resp2.status_code in [200, 204], f"DELETE payment failed: {resp2.status_code} {resp2.text}"
        print(f"PASS: EMI {emi_month} payment undone successfully")

        # Verify EMI is back to pending/overdue
        get_resp = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert get_resp.status_code == 200
        final_loan = get_resp.json()
        reverted_emi = next((e for e in final_loan["emi_schedule"] if e["due_month"] == emi_month), None)
        assert reverted_emi is not None
        assert reverted_emi["status"] in ["pending", "overdue"], \
            f"EMI should revert to pending/overdue after undo, got '{reverted_emi['status']}'"
        print(f"PASS: EMI {emi_month} reverted to '{reverted_emi['status']}' after undo")

    def test_collect_already_paid_emi_fails(self, admin_session):
        """POST payment for an already paid EMI should fail (4xx)"""
        loan = self._get_first_loan(admin_session)
        loan_id = loan["id"]
        schedule = loan.get("emi_schedule", [])

        paid_emis = [e for e in schedule if e["status"] == "paid"]
        if not paid_emis:
            pytest.skip("No paid EMIs found - cannot test duplicate collection")

        emi = paid_emis[0]
        emi_month = emi["due_month"]
        emi_amount = emi["amount"]

        resp = admin_session.post(
            f"{BASE_URL}/api/loans/{loan_id}/payments",
            json={"emi_month": emi_month, "amount": emi_amount, "payment_date": "2026-02-01"}
        )
        assert resp.status_code in [400, 409, 422], \
            f"Expected 4xx for duplicate collect, got {resp.status_code}: {resp.text}"
        print(f"PASS: Duplicate EMI collection rejected with {resp.status_code}")


# ─── KYC Detail for Passbook ─────────────────────────────────────────────────

class TestKycEndpoint:
    """Verify KYC detail used in passbook header loads correctly"""

    def test_get_known_kyc(self, admin_session):
        """GET /api/kycs/{id} returns client KYC data"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs/{KNOWN_KYC_ID}")
        assert resp.status_code == 200, f"GET KYC failed: {resp.status_code}"

        data = resp.json()
        assert "primary_borrower" in data, "KYC missing 'primary_borrower'"
        assert "status" in data, "KYC missing 'status'"
        pb = data["primary_borrower"]
        assert pb.get("name"), "primary_borrower.name is empty"
        print(f"PASS: KYC loaded successfully: {pb.get('name')}, status={data['status']}")

    def test_kyc_id_format_matches_loan_filter(self, admin_session):
        """KYC id returned from GET /api/kycs matches what's used in loan filter"""
        resp = admin_session.get(f"{BASE_URL}/api/kycs/{KNOWN_KYC_ID}")
        assert resp.status_code == 200

        kyc = resp.json()
        kyc_id = kyc.get("id")
        assert kyc_id == KNOWN_KYC_ID, f"KYC id mismatch: {kyc_id} != {KNOWN_KYC_ID}"

        # Now use that id to filter loans
        loans_resp = admin_session.get(f"{BASE_URL}/api/loans?kyc_id={kyc_id}&limit=20")
        assert loans_resp.status_code == 200
        loans_data = loans_resp.json()
        print(f"PASS: KYC id {kyc_id} returns {loans_data['total']} loans")


# ─── Run all ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
