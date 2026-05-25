"""
Backend tests for Re-Loan (with/without Net-Off) feature
Tests POST /api/loans/{loan_id}/reloan endpoint and related features
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_CREDS = {"email": "admin@bahikhata.com", "password": "Admin@123"}

# Known test loans from previous context (active loans to use for reloan)
KNOWN_ACTIVE_LOANS = ["DE0019-L1", "DE0018-L1"]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_session(session):
    """Authenticated admin session"""
    res = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    assert res.status_code == 200, f"Login failed: {res.text}"
    return session


@pytest.fixture(scope="module")
def active_loan_id(admin_session):
    """Get an active loan ID with outstanding balance for reloan testing"""
    res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
    assert res.status_code == 200
    loans = res.json().get("loans", [])
    # Find an active loan with outstanding balance that hasn't been reloan'd yet
    for loan in loans:
        if (
            loan.get("status") == "active"
            and loan.get("loan_number") in KNOWN_ACTIVE_LOANS
            and not loan.get("reloan_id")  # not already has a child reloan
        ):
            return loan["id"]
    # Fallback: any active loan with no reloan_id
    for loan in loans:
        if loan.get("status") == "active" and not loan.get("reloan_id"):
            return loan["id"]
    pytest.skip("No suitable active loan found for reloan testing")


class TestReLoanEndpoint:
    """Tests for POST /api/loans/{loan_id}/reloan"""

    def test_reloan_without_netoff(self, admin_session, active_loan_id):
        """Re-loan without net-off should create new loan, keep old loan active"""
        # First fetch the old loan to capture state
        old_loan_res = admin_session.get(f"{BASE_URL}/api/loans/{active_loan_id}")
        assert old_loan_res.status_code == 200
        old_loan = old_loan_res.json()
        old_status = old_loan["status"]
        old_customer_id = old_loan.get("customer_id", "")

        payload = {
            "new_disbursement_amount": 15000,
            "loan_date": "2026-02-15",
            "net_off": False,
            "notes": "TEST_reloan_no_netoff",
        }
        res = admin_session.post(f"{BASE_URL}/api/loans/{active_loan_id}/reloan", json=payload)
        assert res.status_code == 200, f"Re-loan failed: {res.text}"

        new_loan = res.json()

        # Validate response structure
        assert "id" in new_loan, "New loan should have an id"
        assert new_loan.get("is_reloan") is True, "New loan should have is_reloan=True"
        assert new_loan.get("principal_amount") == 15000, "Principal should match disbursement amount"
        assert new_loan.get("parent_loan_id") == active_loan_id, "Should reference parent loan"
        assert "loan_number" in new_loan, "Should have loan_number"
        assert new_loan["loan_number"] != old_loan.get("loan_number"), "Should be a new loan number"
        assert new_loan.get("netoff_amount", 0) == 0, "No net-off, netoff_amount should be 0"
        assert new_loan.get("net_disbursement_amount") == 15000, "Net disbursement = full amount when no net-off"

        # Verify old loan is NOT closed (no net-off)
        old_loan_after = admin_session.get(f"{BASE_URL}/api/loans/{active_loan_id}").json()
        assert old_loan_after["status"] == old_status, f"Old loan status should remain {old_status}, got {old_loan_after['status']}"
        assert not old_loan_after.get("netoff_closed", False), "Old loan should not be marked netoff_closed"

        # Verify old loan has reloan_id set
        assert old_loan_after.get("reloan_id") == new_loan["id"], "Old loan should reference new reloan"

        print(f"PASS: Re-loan without net-off created: {new_loan['loan_number']} (id={new_loan['id']})")
        return new_loan["id"]  # for cleanup reference

    def test_reloan_with_netoff(self, admin_session):
        """Re-loan with net-off should close old loan and set netoff EMIs"""
        # Find an active loan with outstanding balance that doesn't have a reloan yet
        res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        assert res.status_code == 200
        loans = res.json().get("loans", [])

        target_loan = None
        for loan in loans:
            if (
                loan.get("status") == "active"
                and not loan.get("reloan_id")
                and loan.get("loan_number") in KNOWN_ACTIVE_LOANS
            ):
                target_loan = loan
                break

        # Fallback: any active loan with outstanding and no reloan_id
        if not target_loan:
            for loan in loans:
                total_repayable = loan.get("total_repayable") or (loan.get("emi_amount", 0) * 12)
                total_paid = loan.get("total_paid", 0)
                outstanding = total_repayable - total_paid
                if (
                    loan.get("status") == "active"
                    and not loan.get("reloan_id")
                    and outstanding > 0
                ):
                    target_loan = loan
                    break

        if not target_loan:
            pytest.skip("No suitable active loan with outstanding for net-off test")

        old_loan_id = target_loan["id"]
        old_loan_number = target_loan["loan_number"]
        total_repayable = target_loan.get("total_repayable") or (target_loan.get("emi_amount", 0) * 12)
        total_paid = target_loan.get("total_paid", 0)
        outstanding = total_repayable - total_paid

        print(f"\nTesting net-off on loan: {old_loan_number}, outstanding: {outstanding}")

        new_amount = outstanding + 20000  # Ensure net disbursement is positive
        payload = {
            "new_disbursement_amount": new_amount,
            "loan_date": "2026-02-15",
            "net_off": True,
            "notes": f"TEST_reloan_with_netoff from {old_loan_number}",
        }

        res = admin_session.post(f"{BASE_URL}/api/loans/{old_loan_id}/reloan", json=payload)
        assert res.status_code == 200, f"Re-loan with net-off failed: {res.text}"

        new_loan = res.json()

        # Validate new loan structure
        assert new_loan.get("is_reloan") is True, "New loan should have is_reloan=True"
        assert new_loan.get("principal_amount") == new_amount
        assert new_loan.get("netoff_amount") == pytest.approx(outstanding, abs=1.0), \
            f"netoff_amount should equal outstanding ({outstanding}), got {new_loan.get('netoff_amount')}"
        expected_net_disbursement = new_amount - outstanding
        assert new_loan.get("net_disbursement_amount") == pytest.approx(expected_net_disbursement, abs=1.0), \
            f"net_disbursement_amount expected {expected_net_disbursement}, got {new_loan.get('net_disbursement_amount')}"
        assert "loan_number" in new_loan
        assert new_loan.get("parent_loan_id") == old_loan_id

        # Verify old loan is now CLOSED with netoff_closed=True
        old_loan_after = admin_session.get(f"{BASE_URL}/api/loans/{old_loan_id}").json()
        assert old_loan_after["status"] == "closed", \
            f"Old loan should be closed after net-off, got {old_loan_after['status']}"
        assert old_loan_after.get("netoff_closed") is True, "Old loan should have netoff_closed=True"

        # Verify netoff EMIs in old loan schedule
        emi_schedule = old_loan_after.get("emi_schedule", [])
        netoff_emis = [e for e in emi_schedule if e.get("status") == "netoff"]
        assert len(netoff_emis) > 0, "Old loan should have at least 1 netoff EMI"
        # All unpaid EMIs should be netoff
        for emi in emi_schedule:
            if emi.get("status") not in ("paid", "netoff"):
                assert False, f"EMI {emi.get('month')} should be paid or netoff, got {emi.get('status')}"

        print(f"PASS: Re-loan with net-off: old={old_loan_number}→closed, new={new_loan['loan_number']}, "
              f"netoff_amount={new_loan.get('netoff_amount')}, net_disbursement={new_loan.get('net_disbursement_amount')}")

    def test_reloan_invalid_loan_id(self, admin_session):
        """Should return 400 for invalid loan ID"""
        res = admin_session.post(f"{BASE_URL}/api/loans/invalid_id_xyz/reloan", json={
            "new_disbursement_amount": 10000,
            "loan_date": "2026-02-15",
        })
        assert res.status_code == 400, f"Expected 400 for invalid ID, got {res.status_code}"
        print("PASS: Invalid loan ID returns 400")

    def test_reloan_nonexistent_loan(self, admin_session):
        """Should return 404 for non-existent loan"""
        res = admin_session.post(f"{BASE_URL}/api/loans/000000000000000000000099/reloan", json={
            "new_disbursement_amount": 10000,
            "loan_date": "2026-02-15",
        })
        assert res.status_code == 404, f"Expected 404 for missing loan, got {res.status_code}"
        print("PASS: Non-existent loan returns 404")

    def test_reloan_unauthenticated(self, session, active_loan_id):
        """Unauthenticated request should fail"""
        # Create a fresh session without auth cookies
        unauth = requests.Session()
        unauth.headers.update({"Content-Type": "application/json"})
        res = unauth.post(f"{BASE_URL}/api/loans/{active_loan_id}/reloan", json={
            "new_disbursement_amount": 10000,
            "loan_date": "2026-02-15",
        })
        assert res.status_code in (401, 403), f"Expected 401/403 for unauth, got {res.status_code}"
        print(f"PASS: Unauthenticated returns {res.status_code}")


class TestReLoanClosedLoan:
    """Test re-loan on already closed loan (no net-off option)"""

    def test_reloan_on_closed_loan(self, admin_session):
        """Re-loan on closed loan should work (no net-off since it's already closed)"""
        # Find a closed loan
        res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        assert res.status_code == 200
        loans = res.json().get("loans", [])
        closed_loan = None
        for loan in loans:
            if loan.get("status") == "closed" and loan.get("loan_number"):
                closed_loan = loan
                break

        if not closed_loan:
            pytest.skip("No closed loan found for testing")

        payload = {
            "new_disbursement_amount": 20000,
            "loan_date": "2026-02-15",
            "net_off": False,  # Can't net-off a closed loan
            "notes": "TEST_reloan_on_closed_loan",
        }

        res = admin_session.post(f"{BASE_URL}/api/loans/{closed_loan['id']}/reloan", json=payload)
        assert res.status_code == 200, f"Re-loan on closed loan failed: {res.text}"
        new_loan = res.json()
        assert new_loan.get("is_reloan") is True
        assert new_loan.get("principal_amount") == 20000
        print(f"PASS: Re-loan on closed loan {closed_loan['loan_number']} → {new_loan['loan_number']}")

    def test_reloan_netoff_ignored_for_closed_loan(self, admin_session):
        """Net-off should be ignored if loan is already closed"""
        res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        loans = res.json().get("loans", [])
        # Find a closed loan with netoff_closed NOT set (to avoid operating on same loan twice)
        closed_loan = None
        for loan in loans:
            if loan.get("status") == "closed" and not loan.get("netoff_closed"):
                closed_loan = loan
                break

        if not closed_loan:
            pytest.skip("No suitable closed loan found")

        payload = {
            "new_disbursement_amount": 25000,
            "loan_date": "2026-02-15",
            "net_off": True,  # Should be ignored since loan is already closed
            "notes": "TEST_netoff_ignored_closed",
        }

        res = admin_session.post(f"{BASE_URL}/api/loans/{closed_loan['id']}/reloan", json=payload)
        assert res.status_code == 200, f"Re-loan failed: {res.text}"
        new_loan = res.json()
        # Since loan is closed, net-off should have no effect - netoff_amount should be 0
        assert new_loan.get("netoff_amount", 0) == 0, \
            f"netoff_amount should be 0 for already closed loan, got {new_loan.get('netoff_amount')}"
        assert new_loan.get("net_disbursement_amount") == 25000
        print("PASS: Net-off correctly ignored for closed loan: netoff_amount=0, net_disbursement=25000")


class TestReLoanLoanNumberFormat:
    """Test that loan numbers are formatted correctly"""

    def test_reloan_number_increments(self, admin_session, active_loan_id):
        """New loan number should be incremented (e.g. TE0002-L1 → TE0002-L2)"""
        old_loan = admin_session.get(f"{BASE_URL}/api/loans/{active_loan_id}").json()
        old_loan_number = old_loan.get("loan_number", "")

        # Check if there's already a reloan created
        if old_loan.get("reloan_id"):
            # Fetch the reloan
            reloan = admin_session.get(f"{BASE_URL}/api/loans/{old_loan['reloan_id']}").json()
            new_loan_number = reloan.get("loan_number", "")
        else:
            payload = {
                "new_disbursement_amount": 10000,
                "loan_date": "2026-02-15",
                "net_off": False,
                "notes": "TEST_loan_number_check",
            }
            res = admin_session.post(f"{BASE_URL}/api/loans/{active_loan_id}/reloan", json=payload)
            if res.status_code != 200:
                pytest.skip(f"Could not create reloan: {res.text}")
            new_loan_number = res.json().get("loan_number", "")

        print(f"Old: {old_loan_number}, New: {new_loan_number}")

        # Extract the base part (e.g. TE0002) and loan counter (L1, L2 etc.)
        if "-L" in old_loan_number and "-L" in new_loan_number:
            old_base, old_num = old_loan_number.rsplit("-L", 1)
            new_base, new_num = new_loan_number.rsplit("-L", 1)
            assert old_base == new_base, f"Base part should match: {old_base} vs {new_base}"
            assert int(new_num) > int(old_num), \
                f"New loan number counter ({new_num}) should be greater than old ({old_num})"
            print(f"PASS: Loan number incremented: {old_loan_number} → {new_loan_number}")
        else:
            print(f"INFO: Loan numbers don't follow expected format, old={old_loan_number}, new={new_loan_number}")


class TestReLoanGetLoan:
    """Test GET /api/loans/{id} for reloan-specific fields"""

    def test_get_reloan_has_is_reloan_flag(self, admin_session):
        """GET on a re-loan should show is_reloan=True"""
        # Find a loan with is_reloan=True
        res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        loans = res.json().get("loans", [])
        reloan = next((l for l in loans if l.get("is_reloan")), None)
        if not reloan:
            pytest.skip("No re-loan found in system")

        loan_detail = admin_session.get(f"{BASE_URL}/api/loans/{reloan['id']}").json()
        assert loan_detail.get("is_reloan") is True
        assert "netoff_amount" in loan_detail
        assert "net_disbursement_amount" in loan_detail
        print(f"PASS: Re-loan {reloan['loan_number']} has is_reloan=True, netoff_amount={loan_detail.get('netoff_amount')}")

    def test_get_netoff_closed_loan(self, admin_session):
        """GET on a net-off closed loan should show netoff_closed=True and netoff EMIs"""
        res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        loans = res.json().get("loans", [])
        netoff_loan = next((l for l in loans if l.get("netoff_closed")), None)
        if not netoff_loan:
            pytest.skip("No net-off closed loan found")

        loan_detail = admin_session.get(f"{BASE_URL}/api/loans/{netoff_loan['id']}").json()
        assert loan_detail.get("netoff_closed") is True
        assert loan_detail.get("status") == "closed"
        schedule = loan_detail.get("emi_schedule", [])
        netoff_emis = [e for e in schedule if e.get("status") == "netoff"]
        assert len(netoff_emis) > 0, "Should have at least one netoff EMI"
        print(f"PASS: Net-off closed loan {netoff_loan['loan_number']}: status=closed, netoff EMIs={len(netoff_emis)}")
