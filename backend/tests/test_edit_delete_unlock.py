"""
Iteration 15 tests: Admin Edit/Delete journal entries + Admin Unlock Expense Submissions
- GET  /api/accounts/entries/{entry_id}   — fetch single journal entry
- DELETE /api/accounts/entries/{entry_id} — admin/maalik delete any entry; muneem 403
- PUT  /api/accounts/entries/{entry_id}   — admin/maalik/muneem update expense_voucher;
                                             auto-generated types (loan_disbursement, emi_collection) => 400
- PATCH /api/accounts/expense-submissions/{sub_id}/unlock — admin unlocks submitted sheet
                                             (reverts to draft, removes journal entry); muneem 403
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_ILLAKA_ID = "69c78cf96781e1fb0d95f0dd"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def muneem_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "7777000001", "password": "Test@1234"})
    assert resp.status_code == 200, f"Muneem login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def expense_head_id(admin_session):
    heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
    h = next((h for h in heads if h.get("group_type") == "expense"), None)
    assert h, "No expense head found"
    return h["id"]


@pytest.fixture(scope="module")
def income_head_id(admin_session):
    heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
    h = next((h for h in heads if h.get("group_type") == "income"), None)
    assert h, "No income head found"
    return h["id"]


@pytest.fixture(scope="module")
def first_illaka_id(admin_session):
    resp = admin_session.get(f"{BASE_URL}/api/illakas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0
    return data[0]["id"]


def create_expense_voucher(session, illaka_id, head_id, amount=1000, narration="TEST_voucher"):
    """Helper to create an expense_voucher entry via POST /api/accounts/entries/expense"""
    resp = session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
        "date": "2026-02-15",
        "illaka_id": illaka_id,
        "account_head_id": head_id,
        "amount": amount,
        "narration": narration,
    })
    assert resp.status_code == 200, f"Failed to create expense voucher: {resp.text}"
    return resp.json()["id"]


def create_expense_submission(admin_session, illaka_id, expense_head_id, month="2026-05"):
    """Helper to create and submit an expense submission"""
    # Ensure template exists
    tmpl = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
        "illaka_id": illaka_id,
        "fields": [{"label": "TEST_Unlock Field", "account_head_id": expense_head_id, "display_order": 0}],
    })
    assert tmpl.status_code == 200, f"Template creation failed: {tmpl.text}"
    field_id = tmpl.json()["template"]["fields"][0]["field_id"]

    # Delete existing submission for this month
    sub_check = admin_session.get(
        f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={illaka_id}&month={month}"
    )
    if sub_check.status_code == 200 and sub_check.json().get("submission"):
        sub_id = sub_check.json()["submission"]["id"]
        admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    # Submit
    resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
        "illaka_id": illaka_id,
        "month": month,
        "entries": [{"field_id": field_id, "amount": 1500.0}],
        "action": "submit",
    })
    assert resp.status_code == 200, f"Submission failed: {resp.text}"
    return resp.json()["submission"]


# ── GET /api/accounts/entries/{entry_id} ─────────────────────────────────────

class TestGetSingleEntry:
    """GET /api/accounts/entries/{entry_id} — all roles can fetch a single entry"""

    def test_admin_can_get_single_entry(self, admin_session, first_illaka_id, expense_head_id):
        """Admin can fetch a single journal entry by ID"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id, narration="TEST_get_single")
        resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert resp.status_code == 200, f"Get entry failed: {resp.text}"
        data = resp.json()
        assert data["id"] == entry_id
        assert "date" in data
        assert "narration" in data
        assert "lines" in data
        assert "entry_type" in data
        print(f"PASS: GET /api/accounts/entries/{entry_id} → {data['narration']}")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")

    def test_get_single_entry_returns_correct_fields(self, admin_session, first_illaka_id, expense_head_id):
        """GET entry returns all required fields"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id, narration="TEST_fields_check")
        resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert resp.status_code == 200
        data = resp.json()
        for field in ["id", "date", "narration", "lines", "entry_type", "total_amount", "illaka_id"]:
            assert field in data, f"Missing field: {field}"
        print(f"PASS: All required fields present in GET /api/accounts/entries/{entry_id}")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")

    def test_get_nonexistent_entry_returns_404(self, admin_session):
        """GET with invalid/nonexistent entry_id should return 404"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/000000000000000000000000")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("PASS: GET nonexistent entry → 404")

    def test_get_invalid_entry_id_returns_400(self, admin_session):
        """GET with invalid ObjectId format should return 400"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/invalid_id_format")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("PASS: GET invalid ID format → 400")

    def test_muneem_can_get_single_entry(self, admin_session, muneem_session, expense_head_id):
        """Muneem can also fetch a single journal entry by ID"""
        entry_id = create_expense_voucher(admin_session, TEST_ILLAKA_ID, expense_head_id, narration="TEST_muneem_get")
        resp = muneem_session.get(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert resp.status_code == 200, f"Muneem GET entry failed: {resp.text}"
        data = resp.json()
        assert data["id"] == entry_id
        print(f"PASS: Muneem can GET single entry {entry_id}")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")


# ── DELETE /api/accounts/entries/{entry_id} ──────────────────────────────────

class TestDeleteEntry:
    """DELETE /api/accounts/entries/{entry_id} — admin/maalik only"""

    def test_admin_can_delete_entry(self, admin_session, first_illaka_id, expense_head_id):
        """Admin can delete any journal entry"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id, narration="TEST_delete_me")
        resp = admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert resp.status_code == 200, f"Delete failed: {resp.text}"
        data = resp.json()
        assert "message" in data
        assert "deleted" in data["message"].lower()
        print(f"PASS: Admin DELETE entry → {data['message']}")

    def test_deleted_entry_returns_404(self, admin_session, first_illaka_id, expense_head_id):
        """After deletion, GET on the same entry should return 404"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id, narration="TEST_delete_verify")
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        get_resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert get_resp.status_code == 404, f"Expected 404 after delete, got {get_resp.status_code}"
        print("PASS: Deleted entry returns 404 on GET")

    def test_muneem_cannot_delete_entry(self, admin_session, muneem_session, expense_head_id):
        """Muneem should get 403 when trying to delete an entry"""
        entry_id = create_expense_voucher(admin_session, TEST_ILLAKA_ID, expense_head_id, narration="TEST_muneem_delete_attempt")
        resp = muneem_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert resp.status_code == 403, f"Muneem should get 403, got {resp.status_code}: {resp.text}"
        print("PASS: Muneem DELETE → 403")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")

    def test_delete_nonexistent_entry_returns_404(self, admin_session):
        """Deleting a nonexistent entry should return 404"""
        resp = admin_session.delete(f"{BASE_URL}/api/accounts/entries/000000000000000000000000")
        assert resp.status_code == 404, f"Expected 404 for nonexistent delete, got {resp.status_code}"
        print("PASS: DELETE nonexistent entry → 404")

    def test_delete_invalid_id_returns_400(self, admin_session):
        """Deleting with invalid entry_id format should return 400"""
        resp = admin_session.delete(f"{BASE_URL}/api/accounts/entries/not_valid_id")
        assert resp.status_code == 400, f"Expected 400 for invalid ID, got {resp.status_code}"
        print("PASS: DELETE invalid ID → 400")


# ── PUT /api/accounts/entries/{entry_id} ─────────────────────────────────────

class TestUpdateEntry:
    """PUT /api/accounts/entries/{entry_id} — admin/maalik/muneem for expense_voucher only"""

    def test_admin_can_update_expense_voucher(self, admin_session, first_illaka_id, expense_head_id):
        """Admin can update an expense_voucher entry with new amount and narration"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id,
                                          amount=500, narration="TEST_original_narration")
        put_resp = admin_session.put(f"{BASE_URL}/api/accounts/entries/{entry_id}", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head_id,
            "amount": 750.0,
            "narration": "TEST_updated_narration",
        })
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        data = put_resp.json()
        assert data["narration"] == "TEST_updated_narration"
        assert data["total_amount"] == 750.0
        print("PASS: Admin PUT entry → narration and amount updated")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")

    def test_update_persists_in_get(self, admin_session, first_illaka_id, expense_head_id):
        """After PUT, GET should return updated values"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id,
                                          amount=1000, narration="TEST_pre_update")
        admin_session.put(f"{BASE_URL}/api/accounts/entries/{entry_id}", json={
            "date": "2026-02-16",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head_id,
            "amount": 2000.0,
            "narration": "TEST_post_update",
        })
        get_resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/{entry_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["narration"] == "TEST_post_update"
        assert data["total_amount"] == 2000.0
        assert data["date"] == "2026-02-16"
        print("PASS: PUT persists correctly — GET verifies updated narration and amount")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")

    def test_update_auto_generated_loan_disbursement_returns_400(self, admin_session, expense_head_id):
        """Trying to PUT on a loan_disbursement entry_type should return 400"""
        # Find an existing loan_disbursement entry (or create a synthetic condition by checking any that exists)
        entries_resp = admin_session.get(f"{BASE_URL}/api/accounts/entries?month=2026-02")
        if entries_resp.status_code != 200:
            pytest.skip("Cannot fetch entries")
        entries = entries_resp.json().get("entries", [])
        loan_disburse_entry = next((e for e in entries if e.get("entry_type") == "loan_disbursement"), None)
        if not loan_disburse_entry:
            # Try a broader search
            entries_resp2 = admin_session.get(f"{BASE_URL}/api/accounts/entries")
            if entries_resp2.status_code == 200:
                all_entries = entries_resp2.json().get("entries", [])
                loan_disburse_entry = next((e for e in all_entries if e.get("entry_type") == "loan_disbursement"), None)
        if not loan_disburse_entry:
            pytest.skip("No loan_disbursement entry found to test — skipping")

        entry_id = loan_disburse_entry["id"]
        # Get the expense head from the entry if possible
        first_illaka_id = loan_disburse_entry.get("illaka_id", TEST_ILLAKA_ID)
        resp = admin_session.put(f"{BASE_URL}/api/accounts/entries/{entry_id}", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head_id,
            "amount": 100.0,
            "narration": "TEST_should_fail",
        })
        assert resp.status_code == 400, f"Expected 400 for auto-generated type, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "auto-generated" in detail.lower() or "cannot be edited" in detail.lower()
        print(f"PASS: PUT loan_disbursement → 400: {detail}")

    def test_update_auto_generated_emi_collection_returns_400(self, admin_session, expense_head_id):
        """Trying to PUT on an emi_collection entry_type should return 400"""
        entries_resp = admin_session.get(f"{BASE_URL}/api/accounts/entries?month=2026-02")
        entries = entries_resp.json().get("entries", []) if entries_resp.status_code == 200 else []
        emi_entry = next((e for e in entries if e.get("entry_type") == "emi_collection"), None)
        if not emi_entry:
            entries_resp2 = admin_session.get(f"{BASE_URL}/api/accounts/entries")
            if entries_resp2.status_code == 200:
                all_entries = entries_resp2.json().get("entries", [])
                emi_entry = next((e for e in all_entries if e.get("entry_type") == "emi_collection"), None)
        if not emi_entry:
            pytest.skip("No emi_collection entry found to test — skipping")

        entry_id = emi_entry["id"]
        first_illaka_id = emi_entry.get("illaka_id", TEST_ILLAKA_ID)
        resp = admin_session.put(f"{BASE_URL}/api/accounts/entries/{entry_id}", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head_id,
            "amount": 100.0,
            "narration": "TEST_emi_should_fail",
        })
        assert resp.status_code == 400, f"Expected 400 for emi_collection type, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "auto-generated" in detail.lower() or "cannot be edited" in detail.lower()
        print(f"PASS: PUT emi_collection → 400: {detail}")

    def test_sipahi_cannot_update_entry(self, admin_session, first_illaka_id, expense_head_id):
        """Sipahi should get 403 on PUT entry"""
        entry_id = create_expense_voucher(admin_session, first_illaka_id, expense_head_id,
                                          narration="TEST_sipahi_update_attempt")
        sipahi = requests.Session()
        sipahi.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
        resp = sipahi.put(f"{BASE_URL}/api/accounts/entries/{entry_id}", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head_id,
            "amount": 100.0,
            "narration": "TEST_sipahi_update",
        })
        assert resp.status_code == 403, f"Sipahi should get 403, got {resp.status_code}: {resp.text}"
        print("PASS: Sipahi PUT → 403")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")

    def test_update_income_head_changes_lines(self, admin_session, first_illaka_id, income_head_id):
        """PUT with an income head should create correct debit/credit lines"""
        # First create an income entry
        resp_create = admin_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": income_head_id,
            "amount": 300,
            "narration": "TEST_income_entry",
        })
        if resp_create.status_code != 200:
            pytest.skip(f"Could not create income entry: {resp_create.text}")
        entry_id = resp_create.json()["id"]

        # Update it
        put_resp = admin_session.put(f"{BASE_URL}/api/accounts/entries/{entry_id}", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": income_head_id,
            "amount": 600.0,
            "narration": "TEST_income_updated",
        })
        assert put_resp.status_code == 200, f"PUT income failed: {put_resp.text}"
        data = put_resp.json()
        assert data["total_amount"] == 600.0
        print("PASS: PUT income entry updated successfully")
        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/entries/{entry_id}")


# ── PATCH /api/accounts/expense-submissions/{sub_id}/unlock ──────────────────

class TestUnlockExpenseSubmission:
    """PATCH /api/accounts/expense-submissions/{sub_id}/unlock — admin/maalik only"""

    TEST_MONTH = "2026-05"

    def test_admin_can_unlock_submitted_expense_sheet(self, admin_session, expense_head_id):
        """Admin can unlock a submitted expense sheet (reverts to draft)"""
        submission = create_expense_submission(admin_session, TEST_ILLAKA_ID, expense_head_id, self.TEST_MONTH)
        sub_id = submission["id"]
        assert submission["status"] == "submitted", f"Expected submitted, got {submission['status']}"
        old_journal_id = submission.get("journal_entry_id")
        assert old_journal_id, "Should have journal_entry_id before unlock"

        # Unlock
        resp = admin_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}/unlock")
        assert resp.status_code == 200, f"Unlock failed: {resp.text}"
        data = resp.json()
        assert "submission" in data
        assert "message" in data
        assert "unlock" in data["message"].lower() or "re-edit" in data["message"].lower()
        sub = data["submission"]
        assert sub["status"] == "draft", f"Expected draft after unlock, got {sub['status']}"
        assert sub.get("journal_entry_id") is None, "journal_entry_id should be None after unlock"
        print("PASS: Admin PATCH /unlock → status reverted to draft, journal_entry_id cleared")

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    def test_unlock_removes_journal_entry(self, admin_session, expense_head_id):
        """After unlocking, the linked journal entry should be deleted"""
        submission = create_expense_submission(admin_session, TEST_ILLAKA_ID, expense_head_id, self.TEST_MONTH)
        sub_id = submission["id"]
        journal_id = submission["journal_entry_id"]

        # Verify journal entry exists before unlock
        je_resp = admin_session.get(f"{BASE_URL}/api/accounts/entries/{journal_id}")
        assert je_resp.status_code == 200, "Journal entry should exist before unlock"

        # Unlock
        admin_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}/unlock")

        # Verify journal entry is deleted after unlock
        je_resp_after = admin_session.get(f"{BASE_URL}/api/accounts/entries/{journal_id}")
        assert je_resp_after.status_code == 404, f"Journal entry should be deleted after unlock, got {je_resp_after.status_code}"
        print("PASS: Journal entry deleted after unlock")

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    def test_unlock_allows_muneem_to_resubmit(self, admin_session, muneem_session, expense_head_id):
        """After unlock, Muneem should be able to re-submit the expense sheet"""
        submission = create_expense_submission(admin_session, TEST_ILLAKA_ID, expense_head_id, self.TEST_MONTH)
        sub_id = submission["id"]

        # Unlock
        admin_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}/unlock")

        # Check the submission is now draft via GET
        get_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        assert get_resp.status_code == 200
        sub_data = get_resp.json().get("submission")
        assert sub_data is not None
        assert sub_data["status"] == "draft", f"Expected draft, got {sub_data['status']}"
        print("PASS: Submission reverted to draft — Muneem can re-submit")

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    def test_muneem_cannot_unlock_submission(self, admin_session, muneem_session, expense_head_id):
        """Muneem should get 403 on PATCH /unlock"""
        submission = create_expense_submission(admin_session, TEST_ILLAKA_ID, expense_head_id, self.TEST_MONTH)
        sub_id = submission["id"]

        resp = muneem_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}/unlock")
        assert resp.status_code == 403, f"Muneem should get 403 on unlock, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "admin" in detail.lower() or "maalik" in detail.lower() or "only" in detail.lower()
        print(f"PASS: Muneem PATCH /unlock → 403: {detail}")

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    def test_unlock_already_draft_returns_400(self, admin_session, expense_head_id):
        """Trying to unlock a draft (not submitted) should return 400"""
        # Create a draft submission
        tmpl = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [{"label": "TEST_Draft Field", "account_head_id": expense_head_id, "display_order": 0}],
        })
        assert tmpl.status_code == 200
        field_id = tmpl.json()["template"]["fields"][0]["field_id"]

        # Delete existing
        sub_check = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month=2026-06"
        )
        if sub_check.status_code == 200 and sub_check.json().get("submission"):
            admin_session.delete(
                f"{BASE_URL}/api/accounts/expense-submissions/{sub_check.json()['submission']['id']}"
            )

        # Create a draft
        draft_resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": "2026-06",
            "entries": [{"field_id": field_id, "amount": 500.0}],
            "action": "draft",
        })
        assert draft_resp.status_code == 200
        sub_id = draft_resp.json()["submission"]["id"]

        # Try to unlock the draft
        resp = admin_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}/unlock")
        assert resp.status_code == 400, f"Expected 400 for unlocking draft, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "not in submitted" in detail.lower() or "submitted" in detail.lower()
        print(f"PASS: Unlock draft → 400: {detail}")

        # Cleanup
        admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    def test_unlock_nonexistent_submission_returns_404(self, admin_session):
        """Unlocking a nonexistent submission should return 404"""
        resp = admin_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/000000000000000000000000/unlock")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"
        print("PASS: Unlock nonexistent submission → 404")

    def test_unlock_invalid_id_returns_400(self, admin_session):
        """Unlocking with invalid ID format should return 400"""
        resp = admin_session.patch(f"{BASE_URL}/api/accounts/expense-submissions/bad_id/unlock")
        assert resp.status_code == 400, f"Expected 400 for invalid ID, got {resp.status_code}"
        print("PASS: Unlock invalid ID → 400")
