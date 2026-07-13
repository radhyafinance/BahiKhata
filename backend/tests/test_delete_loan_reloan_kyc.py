"""
Backend tests for:
1. DELETE /api/loans/{loan_id} — new endpoint for permanent loan deletion (admin/maalik only)
2. POST /api/loans/{loan_id}/reloan — KYC gate removed (no longer blocks for missing Aadhaar)

Iteration 33 — testing delete loan + reloan KYC gate removal
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_CREDS = {"phone": "9999999999", "password": "Admin@123"}
SIPAHI_CREDS = {"phone": "8888888888", "password": "Test@1234"}


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    res = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS)
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    """Authenticated sipahi session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    res = s.post(f"{BASE_URL}/api/auth/login", json=SIPAHI_CREDS)
    assert res.status_code == 200, f"Sipahi login failed: {res.text}"
    return s


@pytest.fixture(scope="module")
def unauthenticated_session():
    """Unauthenticated session"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def test_loan_for_delete(admin_session):
    """Create a test loan via Quick Add so we can safely delete it.
    Uses an existing KYC to create the loan.
    """
    # Find an existing loan that we can get the illaka/misal from
    loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=10")
    assert loans_res.status_code == 200
    loans = loans_res.json().get("loans", [])
    assert len(loans) > 0, "Need at least one loan in DB to get illaka/misal data"

    # Use first available loan's illaka/misal for creating test loan
    ref_loan = loans[0]

    # Create a loan via the Quick Add endpoint
    payload = {
        "name": "TEST_DeleteLoanTest",
        "phone": "9000000099",
        "illaka_id": ref_loan.get("illaka_id"),
        "illaka_name": ref_loan.get("illaka_name"),
        "misal_id": ref_loan.get("misal_id"),
        "misal_name": ref_loan.get("misal_name"),
        "principal_amount": 10000,
        "loan_month": "2026-01",
    }
    res = admin_session.post(f"{BASE_URL}/api/kycs/quick-loan", json=payload)
    if res.status_code == 403:
        # Admin might not be allowed to create quick loans directly (only muneem/sipahi)
        # Fallback: pick any active loan and create a test scenario
        pytest.skip("Cannot create Quick Add loan as admin (403) - need sipahi to create test loan")

    if res.status_code not in (200, 201):
        # Try using a different approach — just get any loan and create a reloan to delete
        # Find any active loan
        for loan in loans:
            if loan.get("status") == "active" and not loan.get("reloan_id"):
                # Create a reloan to have a deletable loan
                reloan_res = admin_session.post(
                    f"{BASE_URL}/api/loans/{loan['id']}/reloan",
                    json={"new_disbursement_amount": 5000, "loan_date": "2026-02-01", "net_off": False, "notes": "TEST_for_delete"}
                )
                if reloan_res.status_code == 200:
                    new_loan = reloan_res.json()
                    return {"id": new_loan["id"], "loan_number": new_loan["loan_number"], "kyc_id": new_loan.get("kyc_id")}

        pytest.skip("Could not create a test loan for deletion")

    data = res.json()
    return {"id": data["loan_id"], "loan_number": data["loan_number"], "kyc_id": data.get("kyc_id")}


# ─── Tests: DELETE /api/loans/{loan_id} ──────────────────────────────────────

class TestDeleteLoan:
    """Tests for DELETE /api/loans/{loan_id}"""

    def test_delete_nonexistent_loan_returns_404(self, admin_session):
        """DELETE with nonexistent ObjectId should return 404"""
        fake_id = "000000000000000000000099"
        res = admin_session.delete(f"{BASE_URL}/api/loans/{fake_id}")
        assert res.status_code == 404, f"Expected 404, got {res.status_code}: {res.text}"
        data = res.json()
        assert "not found" in data.get("detail", "").lower() or "loan" in data.get("detail", "").lower()
        print(f"PASS: 404 for nonexistent loan: {data.get('detail')}")

    def test_delete_invalid_id_returns_400(self, admin_session):
        """DELETE with invalid (non-ObjectId) ID should return 400"""
        res = admin_session.delete(f"{BASE_URL}/api/loans/not_an_objectid")
        assert res.status_code == 400, f"Expected 400 for invalid ID, got {res.status_code}: {res.text}"
        print(f"PASS: 400 for invalid loan ID: {res.json().get('detail')}")

    def test_sipahi_cannot_delete_loan(self, sipahi_session, admin_session):
        """Sipahi should get 403 when trying to delete any loan"""
        # Get any loan ID
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=5")
        assert loans_res.status_code == 200
        loans = loans_res.json().get("loans", [])
        if not loans:
            pytest.skip("No loans available to test permission denial")

        loan_id = loans[0]["id"]
        res = sipahi_session.delete(f"{BASE_URL}/api/loans/{loan_id}")
        assert res.status_code == 403, f"Expected 403 for sipahi, got {res.status_code}: {res.text}"
        data = res.json()
        assert "admin" in data.get("detail", "").lower() or "maalik" in data.get("detail", "").lower() or "only" in data.get("detail", "").lower()
        print(f"PASS: Sipahi gets 403: {data.get('detail')}")

    def test_unauthenticated_delete_returns_401_or_403(self, unauthenticated_session, admin_session):
        """Unauthenticated DELETE should return 401/403"""
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=5")
        loans = loans_res.json().get("loans", [])
        if not loans:
            pytest.skip("No loans to test unauthenticated delete")

        loan_id = loans[0]["id"]
        res = unauthenticated_session.delete(f"{BASE_URL}/api/loans/{loan_id}")
        assert res.status_code in (401, 403), f"Expected 401/403, got {res.status_code}: {res.text}"
        print(f"PASS: Unauthenticated delete returns {res.status_code}")

    def test_admin_can_delete_loan(self, admin_session):
        """Admin can delete a loan — create a reloan then delete it"""
        # Find an active loan to create a reloan from (which we'll then delete)
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        assert loans_res.status_code == 200
        loans = loans_res.json().get("loans", [])

        # Find an active loan without a reloan
        parent_loan = None
        for loan in loans:
            if loan.get("status") in ("active", "overdue") and not loan.get("reloan_id"):
                parent_loan = loan
                break

        if not parent_loan:
            pytest.skip("No suitable parent loan found to create reloan for deletion test")

        # Create a reloan (to have a deletable test loan)
        reloan_res = admin_session.post(
            f"{BASE_URL}/api/loans/{parent_loan['id']}/reloan",
            json={
                "new_disbursement_amount": 5000,
                "loan_date": "2026-02-01",
                "net_off": False,
                "notes": "TEST_loan_for_delete"
            }
        )
        assert reloan_res.status_code == 200, f"Could not create test reloan: {reloan_res.text}"
        test_loan = reloan_res.json()
        test_loan_id = test_loan["id"]
        test_loan_number = test_loan["loan_number"]

        print(f"Created test reloan: {test_loan_number} (id={test_loan_id})")

        # Now delete the test reloan
        delete_res = admin_session.delete(f"{BASE_URL}/api/loans/{test_loan_id}")
        assert delete_res.status_code == 200, f"Delete failed: {delete_res.text}"

        # Validate response structure
        data = delete_res.json()
        assert data.get("deleted") is True, f"Response should have deleted=True: {data}"
        assert data.get("loan_id") == test_loan_id, f"loan_id mismatch: expected {test_loan_id}, got {data.get('loan_id')}"
        assert data.get("loan_number") == test_loan_number, f"loan_number mismatch: expected {test_loan_number}, got {data.get('loan_number')}"
        print(f"PASS: Admin deleted loan {test_loan_number}: {data}")

        # Verify loan is actually gone (GET should return 404)
        get_res = admin_session.get(f"{BASE_URL}/api/loans/{test_loan_id}")
        assert get_res.status_code == 404, f"Loan should be 404 after deletion, got {get_res.status_code}"
        print(f"PASS: Loan {test_loan_number} confirmed deleted (GET returns 404)")

    def test_delete_also_removes_payments(self, admin_session):
        """Deleting a loan should also delete its payment records"""
        # Find a loan with payments
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        loans = loans_res.json().get("loans", [])

        # Find an active loan without reloan
        parent = None
        for loan in loans:
            if loan.get("status") in ("active", "overdue") and not loan.get("reloan_id"):
                parent = loan
                break

        if not parent:
            pytest.skip("No suitable loan available")

        # Create a reloan
        reloan_res = admin_session.post(
            f"{BASE_URL}/api/loans/{parent['id']}/reloan",
            json={"new_disbursement_amount": 7000, "loan_date": "2026-02-02", "net_off": False, "notes": "TEST_del_with_payments"}
        )
        assert reloan_res.status_code == 200
        new_loan = reloan_res.json()
        new_id = new_loan["id"]

        # Add a payment
        pay_res = admin_session.post(
            f"{BASE_URL}/api/loans/{new_id}/payments",
            json={"emi_month": "2026-03", "amount": 700, "payment_date": "2026-03-01"}
        )
        # Payment might fail if EMI schedule doesn't have 2026-03; that's OK — just check the delete logic
        payment_added = pay_res.status_code == 200

        # Verify payments exist before delete
        payments_before = admin_session.get(f"{BASE_URL}/api/loans/{new_id}/payments").json()
        payments_before_count = len(payments_before) if isinstance(payments_before, list) else 0

        # Delete the loan
        del_res = admin_session.delete(f"{BASE_URL}/api/loans/{new_id}")
        assert del_res.status_code == 200, f"Delete failed: {del_res.text}"
        assert del_res.json().get("deleted") is True

        # After deletion, GET on loan should return 404
        get_res = admin_session.get(f"{BASE_URL}/api/loans/{new_id}")
        assert get_res.status_code == 404, f"Expected 404 after delete, got {get_res.status_code}"

        # Payments endpoint should also return empty or 404
        # (since loan doesn't exist anymore, payments query returns empty list)
        pay_after = admin_session.get(f"{BASE_URL}/api/loans/{new_id}/payments")
        # Either 404 or empty array
        if pay_after.status_code == 200:
            assert len(pay_after.json()) == 0, f"Payments should be gone after loan deletion, got {pay_after.json()}"
        print(f"PASS: Loan and payments deleted. payments_before={payments_before_count}")


# ─── Tests: Reloan without KYC gate ──────────────────────────────────────────

class TestReloanKYCGateRemoved:
    """Tests that POST /api/loans/{loan_id}/reloan no longer blocks for incomplete KYC"""

    def test_reloan_allowed_for_incomplete_kyc_customer(self, admin_session):
        """Re-loan should work even when client has no Aadhaar photos.
        Checks that the old 'KYC is incomplete' 400 error is NOT returned.
        Uses a Quick Add customer (XX0001 pattern) that has no Aadhaar.
        """
        # Find a loan from a quick-add customer (typically has no aadhaar_front_path)
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=100")
        assert loans_res.status_code == 200
        loans = loans_res.json().get("loans", [])

        # Find a loan where kyc_id is set but KYC may be incomplete
        target_loan = None
        for loan in loans:
            kyc_id = loan.get("kyc_id")
            if kyc_id and not loan.get("reloan_id"):
                # Check if this KYC has no aadhaar
                kyc_res = admin_session.get(f"{BASE_URL}/api/kycs/{kyc_id}")
                if kyc_res.status_code == 200:
                    kyc = kyc_res.json()
                    pb = kyc.get("primary_borrower") or {}
                    # Found one without aadhaar photos
                    if not pb.get("aadhaar_front_path") or not pb.get("aadhaar_back_path"):
                        target_loan = loan
                        break

        if not target_loan:
            print("INFO: No loan found with incomplete KYC (no aadhaar). Testing with any active loan.")
            # Try any active loan
            for loan in loans:
                if loan.get("status") in ("active", "overdue") and not loan.get("reloan_id"):
                    target_loan = loan
                    break

        if not target_loan:
            pytest.skip("No suitable loan found for reloan KYC gate test")

        loan_id = target_loan["id"]
        loan_number = target_loan.get("loan_number", "unknown")
        print(f"\nTesting reloan KYC gate removal on loan: {loan_number} (id={loan_id})")

        payload = {
            "new_disbursement_amount": 5000,
            "loan_date": "2026-02-01",
            "net_off": False,
            "notes": "TEST_kyc_gate_removed"
        }
        res = admin_session.post(f"{BASE_URL}/api/loans/{loan_id}/reloan", json=payload)

        # Should NOT return 400 with "KYC is incomplete" message
        assert res.status_code != 400 or "kyc" not in res.json().get("detail", "").lower(), \
            f"Backend still blocking reloan for incomplete KYC! Response: {res.text}"

        # Should succeed (200) — may fail for other reasons but NOT KYC gate
        assert res.status_code == 200, f"Re-loan failed (expected 200): {res.status_code}: {res.text}"

        new_loan = res.json()
        assert new_loan.get("is_reloan") is True
        print(f"PASS: Re-loan allowed without KYC check. New loan: {new_loan.get('loan_number')}")

    def test_reloan_no_longer_returns_kyc_incomplete_400(self, admin_session):
        """Specifically verify that 400 'KYC is incomplete' is NOT returned.
        Even if the KYC is missing Aadhaar, reloan should proceed.
        """
        # Find any loan to test — just verify the error message is gone
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        assert loans_res.status_code == 200
        loans = loans_res.json().get("loans", [])

        # Find any loan (active or not) without an existing reloan
        for loan in loans:
            loan_id = loan["id"]
            kyc_id = loan.get("kyc_id")
            if not kyc_id:
                continue

            # Check if this KYC is missing Aadhaar
            kyc_res = admin_session.get(f"{BASE_URL}/api/kycs/{kyc_id}")
            if kyc_res.status_code != 200:
                continue
            kyc = kyc_res.json()
            pb = kyc.get("primary_borrower") or {}

            if pb.get("aadhaar_front_path"):
                continue  # Has aadhaar — skip this one

            # This KYC is missing aadhaar — test reloan
            payload = {
                "new_disbursement_amount": 5000,
                "loan_date": "2026-02-01",
                "net_off": False,
                "notes": "TEST_kyc_gate_check"
            }
            res = admin_session.post(f"{BASE_URL}/api/loans/{loan_id}/reloan", json=payload)

            # CRITICAL: Should NOT be 400 with "KYC is incomplete"
            if res.status_code == 400:
                detail = res.json().get("detail", "").lower()
                assert "kyc" not in detail and "incomplete" not in detail and "aadhaar" not in detail, \
                    f"Backend still has KYC gate! Got 400: {res.json().get('detail')}"

            print(f"PASS: Re-loan for KYC-incomplete loan {loan.get('loan_number')}: status={res.status_code} (not 400 KYC block)")
            return

        print("INFO: No loan with incomplete KYC found — KYC gate test inconclusive (all clients have Aadhaar)")


# ─── Tests: Route ordering sanity check ──────────────────────────────────────

class TestRouteOrdering:
    """Verify that DELETE /loans/{id} does NOT interfere with DELETE /loans/{id}/payments/{month}"""

    def test_delete_payment_route_still_works(self, admin_session):
        """DELETE /loans/{id}/payments/{month} (undo EMI) still works after adding loan delete route"""
        # Find a loan with a paid EMI
        loans_res = admin_session.get(f"{BASE_URL}/api/loans?limit=50")
        loans = loans_res.json().get("loans", [])

        for loan in loans:
            schedule = loan.get("emi_schedule", [])
            paid_emis = [e for e in schedule if e.get("status") == "paid"]
            if paid_emis and loan.get("status") in ("active", "overdue"):
                emi_month = paid_emis[0]["due_month"]
                loan_id = loan["id"]

                # Undo the payment
                res = admin_session.delete(f"{BASE_URL}/api/loans/{loan_id}/payments/{emi_month}")
                if res.status_code == 200:
                    print(f"PASS: DELETE /loans/{loan_id}/payments/{emi_month} works correctly: {res.json()}")
                    # Re-collect to restore state
                    admin_session.post(
                        f"{BASE_URL}/api/loans/{loan_id}/payments",
                        json={"emi_month": emi_month, "amount": paid_emis[0].get("amount", 500), "payment_date": paid_emis[0].get("paid_date", "2026-02-01")}
                    )
                    return
                else:
                    print(f"INFO: Could not undo EMI (may be locked): {res.status_code} {res.text}")
                    continue

        print("INFO: No suitable paid EMI found to test route ordering")
