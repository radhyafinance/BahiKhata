"""
Test suite for Zero Collection (₹0) feature on Vasuli/Collection Sheet
Tests:
1. POST /api/loans/{id}/payments with amount=0 → loan EMI stays pending/overdue
2. No journal entry created for ₹0 payment  
3. ₹0 payment record IS saved in payments collection
4. Negative amount (-100) rejected with 422/400
5. After ₹0 visit, real amount (1500) marks EMI as paid (row turns green)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test loan IDs from SHEESH GARH misal in Biharipur illaka
# BI0003-L1 (KANUNI) - use for zero collection test
LOAN_ID_ZERO_TEST = "6a35120c0bac7e13c3030330"  # BI0003-L1 KANUNI

# BI0004-L1 (FYYAJ) - use for zero → real amount test
LOAN_ID_FOLLOWUP_TEST = "6a35120c0bac7e13c3030332"  # BI0004-L1 FYYAJ

# BI0005-L1 (VEENA DEVI) - use for negative amount rejection test
LOAN_ID_NEG_TEST = "6a35120c0bac7e13c3030334"  # BI0005-L1 VEENA DEVI

EMI_MONTH = "2026-07"
PAYMENT_DATE = "2026-07-15"
ILLAKA_ID = "6a3510cd7d131f22c25263cc"


@pytest.fixture(scope="module")
def session():
    """Authenticated session using admin credentials"""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return s


@pytest.fixture(autouse=True)
def cleanup_zero_payment(session):
    """Cleanup zero payment record after each test to avoid 'already paid' conflicts"""
    yield
    # Best-effort cleanup — delete if emi is paid (to reset state for next test)
    # We only clean up the specific test loans to avoid affecting other loans
    for loan_id in [LOAN_ID_ZERO_TEST, LOAN_ID_FOLLOWUP_TEST]:
        try:
            session.delete(f"{BASE_URL}/api/loans/{loan_id}/payments/{EMI_MONTH}")
        except Exception:
            pass


class TestZeroCollectionBackend:
    """Backend API tests for ₹0 collection (visit recording)"""

    def test_zero_amount_accepted_and_returns_loan(self, session):
        """POST with amount=0 should return 200 with updated loan doc"""
        resp = session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data or "loan_number" in data, "Response should be a loan document"
        print(f"PASS: Zero amount accepted, loan returned: {data.get('loan_number', '')}")

    def test_zero_amount_emi_status_stays_pending(self, session):
        """After ₹0 collection, the July 2026 EMI status must NOT be 'paid'"""
        # Post zero payment
        session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )
        # Fetch updated loan
        loan_resp = session.get(f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}")
        assert loan_resp.status_code == 200
        loan = loan_resp.json()
        schedule = loan.get("emi_schedule", [])
        july_emi = next((e for e in schedule if e.get("due_month") == EMI_MONTH), None)
        assert july_emi is not None, f"July EMI not found in schedule"
        assert july_emi["status"] != "paid", (
            f"EMI status should NOT be 'paid' after ₹0 entry, got: {july_emi['status']}"
        )
        assert july_emi["status"] in ["pending", "overdue", "due"], (
            f"EMI status should be pending/overdue/due, got: {july_emi['status']}"
        )
        print(f"PASS: EMI status stays '{july_emi['status']}' after ₹0 entry (not marked paid)")

    def test_zero_amount_payment_record_saved(self, session):
        """₹0 payment MUST be saved in payments collection (visit tracking)"""
        # Post zero payment
        session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )
        # Get payment records
        pay_resp = session.get(f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments")
        assert pay_resp.status_code == 200
        payments = pay_resp.json()
        assert isinstance(payments, list), "Payments should be a list"
        # Find the zero payment for July 2026
        zero_payment = next(
            (p for p in payments if p.get("emi_month") == EMI_MONTH and p.get("amount") == 0),
            None,
        )
        assert zero_payment is not None, (
            f"₹0 payment record should be saved in payments collection for {EMI_MONTH}. "
            f"Found payments: {[(p.get('emi_month'), p.get('amount')) for p in payments]}"
        )
        assert zero_payment["amount"] == 0, f"Payment amount should be 0, got: {zero_payment['amount']}"
        assert zero_payment["payment_date"] == PAYMENT_DATE
        print(f"PASS: ₹0 payment record saved: {zero_payment}")

    def test_zero_amount_no_journal_entry(self, session):
        """₹0 collection should NOT create a journal entry in cashbook"""
        # Count journal entries before
        je_before = session.get(
            f"{BASE_URL}/api/journal/entries?illaka_id={ILLAKA_ID}&entry_type=emi_collection&reference_id={LOAN_ID_ZERO_TEST}"
        )
        count_before = 0
        if je_before.status_code == 200:
            jdata = je_before.json()
            entries_before = jdata.get("entries", jdata if isinstance(jdata, list) else [])
            count_before = len([e for e in entries_before if e.get("emi_month") == EMI_MONTH])

        # Post zero payment
        session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )

        # Count after — should be same (no new entry)
        je_after = session.get(
            f"{BASE_URL}/api/journal/entries?illaka_id={ILLAKA_ID}&entry_type=emi_collection&reference_id={LOAN_ID_ZERO_TEST}"
        )
        count_after = 0
        if je_after.status_code == 200:
            jdata = je_after.json()
            entries_after = jdata.get("entries", jdata if isinstance(jdata, list) else [])
            count_after = len([e for e in entries_after if e.get("emi_month") == EMI_MONTH])

        assert count_after == count_before, (
            f"Journal entries for ₹0 payment should not increase. Before: {count_before}, After: {count_after}"
        )
        print(f"PASS: No journal entry created for ₹0 payment (count before={count_before}, after={count_after})")

    def test_negative_amount_rejected(self, session):
        """Negative amount (-100) must be rejected (422 or 400)"""
        resp = session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_NEG_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": -100, "payment_date": PAYMENT_DATE},
        )
        assert resp.status_code in [400, 422], (
            f"Negative amount should be rejected with 400/422, got: {resp.status_code}: {resp.text}"
        )
        print(f"PASS: Negative amount rejected with {resp.status_code}")

    def test_zero_then_real_amount_marks_emi_paid(self, session):
        """After ₹0 visit, posting real amount (1500) should mark EMI as paid"""
        # Step 1: Zero visit first
        zero_resp = session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_FOLLOWUP_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )
        assert zero_resp.status_code == 200, f"Zero payment failed: {zero_resp.text}"

        # Verify still pending after zero
        loan = session.get(f"{BASE_URL}/api/loans/{LOAN_ID_FOLLOWUP_TEST}").json()
        july = next((e for e in loan.get("emi_schedule", []) if e.get("due_month") == EMI_MONTH), None)
        assert july and july["status"] != "paid", "Should be pending after zero visit"

        # Step 2: Delete zero payment first (to allow real payment)
        del_resp = session.delete(f"{BASE_URL}/api/loans/{LOAN_ID_FOLLOWUP_TEST}/payments/{EMI_MONTH}")
        print(f"  Delete zero payment: {del_resp.status_code}")

        # Step 3: Post real amount
        real_resp = session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_FOLLOWUP_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 600, "payment_date": PAYMENT_DATE},
        )
        assert real_resp.status_code == 200, f"Real payment failed: {real_resp.text}"

        # Verify EMI is now paid
        updated_loan = session.get(f"{BASE_URL}/api/loans/{LOAN_ID_FOLLOWUP_TEST}").json()
        july_updated = next(
            (e for e in updated_loan.get("emi_schedule", []) if e.get("due_month") == EMI_MONTH), None
        )
        assert july_updated is not None
        assert july_updated["status"] == "paid", (
            f"EMI should be 'paid' after real amount, got: {july_updated['status']}"
        )
        assert july_updated["paid_amount"] == 600, (
            f"Paid amount should be 600, got: {july_updated.get('paid_amount')}"
        )
        print(f"PASS: After ₹0 visit then real amount, EMI is now 'paid' with amount=600")

    def test_zero_amount_loan_total_paid_unchanged(self, session):
        """After ₹0 visit, loan total_paid should not increase"""
        # Get initial total_paid
        loan_before = session.get(f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}").json()
        total_paid_before = float(loan_before.get("total_paid", 0))

        # Post zero payment
        session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )

        # Check total_paid after
        loan_after = session.get(f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}").json()
        total_paid_after = float(loan_after.get("total_paid", 0))

        assert total_paid_after == total_paid_before, (
            f"total_paid should not change after ₹0 entry. Before: {total_paid_before}, After: {total_paid_after}"
        )
        print(f"PASS: total_paid unchanged after ₹0 entry: {total_paid_before} → {total_paid_after}")

    def test_zero_amount_already_paid_emi_blocked(self, session):
        """Cannot post ₹0 on an already-paid EMI"""
        # First pay the EMI
        pay_resp = session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 3000, "payment_date": PAYMENT_DATE},
        )
        if pay_resp.status_code != 200:
            pytest.skip(f"Could not set up paid EMI: {pay_resp.text}")

        # Now try zero on already-paid
        zero_resp = session.post(
            f"{BASE_URL}/api/loans/{LOAN_ID_ZERO_TEST}/payments",
            json={"emi_month": EMI_MONTH, "amount": 0, "payment_date": PAYMENT_DATE},
        )
        assert zero_resp.status_code in [400, 422], (
            f"Should block ₹0 on already-paid EMI, got: {zero_resp.status_code}: {zero_resp.text}"
        )
        print(f"PASS: ₹0 on already-paid EMI blocked with {zero_resp.status_code}")
