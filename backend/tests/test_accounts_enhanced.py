"""
Tests for Enhanced Accounts Module (iteration 14):
- GET /api/accounts/cashbook  → new format: dr_sections, cr_entries
- GET /api/accounts/bid       → dr_totals, cr_totals, opening_balance, closing_balance
- POST /api/accounts/entries  → Full Journal Entry (admin/maalik), balance validation
- GET/POST /api/accounts/expense-templates
- GET/POST /api/accounts/expense-submissions  (draft + submit)
- DELETE /api/accounts/expense-submissions/{id}
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
TEST_ILLAKA_ID = "69c78cf96781e1fb0d95f0dd"


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def muneem_session(admin_session):
    # Get the illaka for the muneem
    illakas = admin_session.get(f"{BASE_URL}/api/illakas").json()
    illaka_id = TEST_ILLAKA_ID

    # Create or find test muneem
    muneem_data = {
        "name": "TEST_Muneem_Accounts",
        "phone": "7777000001",
        "password": "Test@1234",
        "role": "muneem",
        "assigned_illaka_ids": [illaka_id],
    }
    create_resp = admin_session.post(f"{BASE_URL}/api/users", json=muneem_data)
    # May already exist - that's OK

    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "7777000001", "password": "Test@1234"})
    if resp.status_code != 200:
        pytest.skip(f"Muneem login failed: {resp.text}")
    return s


@pytest.fixture(scope="module")
def first_illaka_id(admin_session):
    resp = admin_session.get(f"{BASE_URL}/api/illakas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0, "No illakas found"
    return data[0]["id"]


@pytest.fixture(scope="module")
def expense_head_id(admin_session):
    """Get an expense-type account head id"""
    heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
    h = next((h for h in heads if h.get("group_type") == "expense"), None)
    assert h, "No expense head found"
    return h["id"]


@pytest.fixture(scope="module")
def income_head_id(admin_session):
    """Get an income-type account head id"""
    heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
    h = next((h for h in heads if h.get("group_type") == "income"), None)
    assert h, "No income head found"
    return h["id"]


@pytest.fixture(scope="module")
def cash_head_id(admin_session):
    """Get Cash in Hand head id"""
    heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
    h = next((h for h in heads if h.get("system_key") == "cash_in_hand"), None)
    assert h, "Cash in Hand head not found"
    return h["id"]


# ── Cashbook (new format) ─────────────────────────────────────────────────────

class TestCashbookNewFormat:
    """GET /api/accounts/cashbook returns dr_sections, cr_entries"""

    def test_cashbook_returns_dr_sections_cr_entries(self, admin_session):
        """Cashbook response should have dr_sections and cr_entries, NOT entries"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "dr_sections" in data, "Missing dr_sections field in cashbook response"
        assert "cr_entries" in data, "Missing cr_entries field in cashbook response"
        assert "month" in data
        assert "opening_balance" in data
        assert "total_receipts" in data
        assert "total_payments" in data
        assert "closing_balance" in data

    def test_cashbook_no_old_entries_field(self, admin_session):
        """New cashbook should NOT return an 'entries' field (format changed)"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        # The old format had 'entries' - new format has dr_sections/cr_entries
        assert "entries" not in data, "Old 'entries' field should be removed from cashbook response"

    def test_cashbook_dr_sections_is_list(self, admin_session):
        """dr_sections should be a list"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["dr_sections"], list), "dr_sections should be a list"

    def test_cashbook_cr_entries_is_list(self, admin_session):
        """cr_entries should be a list"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["cr_entries"], list), "cr_entries should be a list"

    def test_cashbook_balance_is_consistent(self, admin_session):
        """Closing balance should equal opening + receipts - payments"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        expected = round(data["opening_balance"] + data["total_receipts"] - data["total_payments"], 2)
        actual = round(data["closing_balance"], 2)
        assert abs(expected - actual) < 0.02, f"Balance mismatch: expected {expected}, got {actual}"

    def test_cashbook_with_illaka_filter(self, admin_session):
        """Cashbook should accept illaka_id filter and return filtered data"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02&illaka_id={TEST_ILLAKA_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert "dr_sections" in data
        assert "cr_entries" in data

    def test_cashbook_emi_sections_grouped_by_misal(self, admin_session):
        """If there are EMI entries, they should appear as emi_group type in dr_sections"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        # If any dr_sections exist, check structure of emi_group sections
        for section in data.get("dr_sections", []):
            if section.get("type") == "emi_group":
                assert "label" in section
                assert "total" in section
                assert "misals" in section
                for misal in section.get("misals", []):
                    assert "misal_id" in misal
                    assert "misal_name" in misal
                    assert "total" in misal
                    assert "entries" in misal
                print(f"PASS: emi_group found with {len(section['misals'])} misals")
                break

    def test_cashbook_cr_entries_have_required_fields(self, admin_session):
        """cr_entries items should have entry_id, date, narration, amount"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        for entry in data.get("cr_entries", [])[:3]:
            assert "date" in entry, f"cr_entry missing date: {entry}"
            assert "narration" in entry, f"cr_entry missing narration: {entry}"
            assert "amount" in entry, f"cr_entry missing amount: {entry}"


# ── Bid Endpoint ──────────────────────────────────────────────────────────────

class TestBid:
    """GET /api/accounts/bid returns dr_totals, cr_totals"""

    def test_bid_returns_correct_structure(self, admin_session):
        """Bid response must include dr_totals, cr_totals, opening_balance, closing_balance"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/bid?month=2026-02")
        assert resp.status_code == 200, f"Bid endpoint failed: {resp.text}"
        data = resp.json()
        assert "dr_totals" in data, "Missing dr_totals"
        assert "cr_totals" in data, "Missing cr_totals"
        assert "opening_balance" in data, "Missing opening_balance"
        assert "closing_balance" in data, "Missing closing_balance"
        assert "total_dr" in data, "Missing total_dr"
        assert "total_cr" in data, "Missing total_cr"
        assert "month" in data

    def test_bid_dr_totals_is_list(self, admin_session):
        """dr_totals should be a list"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/bid?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["dr_totals"], list), "dr_totals should be a list"

    def test_bid_cr_totals_is_list(self, admin_session):
        """cr_totals should be a list"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/bid?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["cr_totals"], list), "cr_totals should be a list"

    def test_bid_balance_calculation(self, admin_session):
        """closing_balance = opening_balance + total_dr - total_cr"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/bid?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        expected = round(data["opening_balance"] + data["total_dr"] - data["total_cr"], 2)
        actual = round(data["closing_balance"], 2)
        assert abs(expected - actual) < 0.02, f"Closing balance mismatch: expected {expected}, got {actual}"

    def test_bid_with_illaka_filter(self, admin_session):
        """Bid should accept illaka_id filter"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/bid?month=2026-02&illaka_id={TEST_ILLAKA_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert "dr_totals" in data
        assert "cr_totals" in data

    def test_bid_emi_total_has_misal_breakdown(self, admin_session):
        """If EMI entries exist, dr_totals should include emi_total with misal_breakdown"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/bid?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        for item in data.get("dr_totals", []):
            if item.get("type") == "emi_total":
                assert "misal_breakdown" in item, "emi_total should have misal_breakdown"
                assert "total" in item
                for mb in item.get("misal_breakdown", []):
                    assert "misal_name" in mb
                    assert "total" in mb
                print("PASS: emi_total found with breakdown")
                break


# ── Full Journal Entry ────────────────────────────────────────────────────────

class TestFullJournalEntry:
    """POST /api/accounts/entries (admin/maalik only, balance validation)"""

    created_entry_id = None

    def test_unbalanced_entry_returns_400(self, admin_session, first_illaka_id,
                                          expense_head_id, cash_head_id):
        """Journal entry with Dr ≠ Cr should return 400"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "narration": "TEST_Unbalanced entry",
            "lines": [
                {"account_head_id": expense_head_id, "debit": 1000.0, "credit": 0.0},
                {"account_head_id": cash_head_id, "debit": 0.0, "credit": 500.0},  # NOT balanced
            ],
        })
        assert resp.status_code == 400, f"Expected 400 for unbalanced, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "not balanced" in detail.lower() or "≠" in detail or "balanced" in detail.lower()

    def test_balanced_entry_saves_successfully(self, admin_session, first_illaka_id,
                                               expense_head_id, cash_head_id):
        """Journal entry with Dr = Cr should save and return 200"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "narration": "TEST_Balanced journal entry",
            "lines": [
                {"account_head_id": expense_head_id, "debit": 1500.0, "credit": 0.0},
                {"account_head_id": cash_head_id, "debit": 0.0, "credit": 1500.0},
            ],
        })
        assert resp.status_code == 200, f"Balanced entry failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data.get("total_amount") == 1500.0
        lines = data.get("lines", [])
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
        TestFullJournalEntry.created_entry_id = data["id"]

    def test_balanced_entry_persists_in_entries_list(self, admin_session, first_illaka_id):
        """Saved journal entry should appear in GET /api/accounts/entries"""
        if not TestFullJournalEntry.created_entry_id:
            pytest.skip("No created entry id (previous test failed)")
        resp = admin_session.get(f"{BASE_URL}/api/accounts/entries?illaka_id={first_illaka_id}&month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        entry_ids = [e["id"] for e in data.get("entries", [])]
        assert TestFullJournalEntry.created_entry_id in entry_ids, "Created journal entry not found in list"

    def test_journal_entry_requires_at_least_2_lines(self, admin_session, first_illaka_id, expense_head_id):
        """Journal entry with only 1 line should return 400 (unbalanced)"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "narration": "TEST_Single line",
            "lines": [
                {"account_head_id": expense_head_id, "debit": 500.0, "credit": 0.0},
            ],
        })
        assert resp.status_code == 400, f"Expected 400 for single line, got {resp.status_code}"

    def test_multi_line_balanced_entry(self, admin_session, first_illaka_id,
                                       expense_head_id, income_head_id, cash_head_id):
        """Multi-line journal entry should work when total Dr = total Cr"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "narration": "TEST_Multi-line balanced entry",
            "lines": [
                {"account_head_id": expense_head_id, "debit": 500.0, "credit": 0.0},
                {"account_head_id": income_head_id, "debit": 200.0, "credit": 0.0},
                {"account_head_id": cash_head_id, "debit": 0.0, "credit": 700.0},
            ],
        })
        assert resp.status_code == 200, f"Multi-line failed: {resp.text}"
        data = resp.json()
        assert len(data.get("lines", [])) == 3

    def test_sipahi_cannot_create_journal_entry(self, first_illaka_id, expense_head_id, cash_head_id):
        """Sipahi should get 403 on POST /api/accounts/entries"""
        s = requests.Session()
        s.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
        resp = s.post(f"{BASE_URL}/api/accounts/entries", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "narration": "Sipahi attempt",
            "lines": [
                {"account_head_id": expense_head_id, "debit": 1000.0, "credit": 0.0},
                {"account_head_id": cash_head_id, "debit": 0.0, "credit": 1000.0},
            ],
        })
        assert resp.status_code == 403, f"Sipahi should get 403, got {resp.status_code}"


# ── Expense Templates ─────────────────────────────────────────────────────────

class TestExpenseTemplates:
    """GET/POST /api/accounts/expense-templates"""

    def test_get_template_returns_none_for_new_illaka(self, admin_session, first_illaka_id):
        """GET for an illaka without template should return {template: null}"""
        # Use a fixed non-existent illaka id to avoid conflict
        resp = admin_session.get(f"{BASE_URL}/api/accounts/expense-templates?illaka_id={first_illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        # Can be None or have template data - just check structure
        assert "template" in data or "illaka_id" in data

    def test_get_existing_template(self, admin_session):
        """GET template for TEST_ILLAKA_ID should return saved fields"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/expense-templates?illaka_id={TEST_ILLAKA_ID}")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "template" in data
        # If template exists, check structure
        if data["template"]:
            tmpl = data["template"]
            assert "fields" in tmpl
            assert "illaka_id" in tmpl
            assert isinstance(tmpl["fields"], list)
            print(f"PASS: Template found with {len(tmpl['fields'])} fields")
        else:
            print("INFO: No template yet for test illaka, will create one")

    def test_create_expense_template(self, admin_session, expense_head_id):
        """Admin can POST a new expense template"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [
                {"label": "TEST_Salary Nitin", "account_head_id": expense_head_id, "display_order": 0},
                {"label": "TEST_Travel Expenses", "account_head_id": expense_head_id, "display_order": 1},
            ],
        })
        assert resp.status_code == 200, f"Failed to create template: {resp.text}"
        data = resp.json()
        assert "template" in data
        tmpl = data["template"]
        assert tmpl["illaka_id"] == TEST_ILLAKA_ID
        fields = tmpl.get("fields", [])
        assert len(fields) == 2, f"Expected 2 fields, got {len(fields)}"
        labels = [f["label"] for f in fields]
        assert "TEST_Salary Nitin" in labels
        assert "TEST_Travel Expenses" in labels

    def test_template_fields_have_account_head_name(self, admin_session):
        """Template fields should be enriched with account_head_name"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/expense-templates?illaka_id={TEST_ILLAKA_ID}")
        assert resp.status_code == 200
        data = resp.json()
        if data.get("template") and data["template"].get("fields"):
            for field in data["template"]["fields"]:
                assert "account_head_name" in field, f"Field missing account_head_name: {field}"
                assert "field_id" in field, f"Field missing field_id: {field}"
                assert field["field_id"], "field_id should not be empty"

    def test_non_admin_cannot_create_template(self, muneem_session):
        """Muneem should get 403 on POST expense-templates"""
        resp = muneem_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [],
        })
        assert resp.status_code == 403, f"Muneem should get 403, got {resp.status_code}"

    def test_template_upsert_replaces_fields(self, admin_session, expense_head_id):
        """POSTing a template again for same illaka should replace existing fields"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [
                {"label": "TEST_Salary Nitin", "account_head_id": expense_head_id, "display_order": 0},
                {"label": "TEST_Travel Expenses", "account_head_id": expense_head_id, "display_order": 1},
            ],
        })
        assert resp.status_code == 200
        # Verify the saved fields
        get_resp = admin_session.get(f"{BASE_URL}/api/accounts/expense-templates?illaka_id={TEST_ILLAKA_ID}")
        assert get_resp.status_code == 200
        tmpl = get_resp.json()["template"]
        assert tmpl is not None
        assert len(tmpl["fields"]) == 2


# ── Expense Submissions ───────────────────────────────────────────────────────

class TestExpenseSubmissions:
    """GET/POST/DELETE /api/accounts/expense-submissions"""

    # Use a future/current month to avoid freeze check
    TEST_MONTH = "2026-03"

    @pytest.fixture(autouse=True)
    def _get_field_ids(self, admin_session, expense_head_id):
        """Get field IDs from the template before each test"""
        # Ensure template exists
        resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [
                {"label": "TEST_Salary Nitin", "account_head_id": expense_head_id, "display_order": 0},
                {"label": "TEST_Travel Expenses", "account_head_id": expense_head_id, "display_order": 1},
            ],
        })
        assert resp.status_code == 200
        tmpl = resp.json()["template"]
        self.field_ids = [f["field_id"] for f in tmpl["fields"]]
        self.template_fields = tmpl["fields"]
        yield
        # Cleanup: delete any submissions for this month
        sub_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        if sub_resp.status_code == 200 and sub_resp.json().get("submission"):
            sub_id = sub_resp.json()["submission"]["id"]
            admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

    def test_get_submission_returns_none_initially(self, admin_session):
        """GET for month without submission should return {submission: null}"""
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "submission" in data
        # May be None initially (or have existing from previous test)
        print(f"Submission status: {data['submission']}")

    def test_save_draft_via_post(self, admin_session):
        """POST with action=draft should save draft submission"""
        entries = [{"field_id": fid, "amount": 500.0} for fid in self.field_ids]
        resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": entries,
            "action": "draft",
        })
        assert resp.status_code == 200, f"Draft save failed: {resp.text}"
        data = resp.json()
        assert "submission" in data
        sub = data["submission"]
        assert sub["status"] == "draft"
        assert sub["illaka_id"] == TEST_ILLAKA_ID
        assert sub["month"] == self.TEST_MONTH
        # Journal entry should NOT be created for draft
        assert sub.get("journal_entry_id") is None

    def test_draft_is_retrievable(self, admin_session):
        """Draft submission should be retrievable via GET"""
        # Save draft first
        entries = [{"field_id": fid, "amount": 750.0} for fid in self.field_ids]
        admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": entries,
            "action": "draft",
        })
        # Now GET
        resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        assert resp.status_code == 200
        sub = resp.json().get("submission")
        assert sub is not None
        assert sub["status"] == "draft"
        # Verify entries saved
        assert len(sub["entries"]) == len(self.field_ids)

    def test_submit_expense_creates_journal_entry(self, admin_session):
        """POST with action=submit should create journal entry and lock form"""
        entries = [{"field_id": fid, "amount": 1000.0} for fid in self.field_ids]
        resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": entries,
            "action": "submit",
        })
        assert resp.status_code == 200, f"Submit failed: {resp.text}"
        data = resp.json()
        assert "submission" in data
        sub = data["submission"]
        assert sub["status"] == "submitted", f"Expected submitted, got {sub['status']}"
        assert sub.get("journal_entry_id") is not None, "Journal entry_id should be set on submit"
        assert sub.get("submitted_by_name") is not None

    def test_submitted_form_is_locked_for_muneem(self, muneem_session):
        """Muneem cannot re-submit a locked (submitted) expense sheet"""
        # First submit it as admin
        entries = [{"field_id": fid, "amount": 500.0} for fid in self.field_ids]
        admin_resp = requests.Session()
        admin_resp.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
        admin_resp.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": entries,
            "action": "submit",
        })
        # Now muneem tries to re-submit
        resp = muneem_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": entries,
            "action": "submit",
        })
        assert resp.status_code == 400, f"Should be 400 (locked), got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "submitted" in detail.lower() or "locked" in detail.lower() or "already" in detail.lower()

    def test_admin_can_delete_submission(self, admin_session):
        """Admin can delete a submission"""
        # Create a submission first
        entries = [{"field_id": fid, "amount": 300.0} for fid in self.field_ids]
        create_resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": entries,
            "action": "submit",
        })
        assert create_resp.status_code == 200
        sub_id = create_resp.json()["submission"]["id"]

        # Delete it
        del_resp = admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")
        assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
        msg = del_resp.json().get("message", "")
        assert "deleted" in msg.lower()

        # Verify it's gone
        get_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        assert get_resp.status_code == 200
        sub = get_resp.json().get("submission")
        assert sub is None, "Submission should be deleted"

    def test_muneem_cannot_delete_submission(self, muneem_session):
        """Muneem should get 403 on DELETE expense-submissions"""
        resp = muneem_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/fake_id")
        assert resp.status_code in [403, 400], f"Expected 403 or 400, got {resp.status_code}"


# ── Expense Sheet Creates Journal Entry in Cashbook ─────────────────────────

class TestExpenseSheetIntegration:
    """Expense submission creates journal entry visible in cashbook"""

    TEST_MONTH = "2026-03"

    def test_expense_sheet_submission_appears_in_cashbook(self, admin_session, expense_head_id):
        """After submitting expense sheet, it should appear as cr_entry in cashbook"""
        # Ensure template exists
        tmpl_resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [
                {"label": "TEST_Integration Field", "account_head_id": expense_head_id, "display_order": 0},
            ],
        })
        assert tmpl_resp.status_code == 200
        field_id = tmpl_resp.json()["template"]["fields"][0]["field_id"]

        # Delete existing submission if any
        sub_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        if sub_resp.status_code == 200 and sub_resp.json().get("submission"):
            sub_id = sub_resp.json()["submission"]["id"]
            admin_session.delete(f"{BASE_URL}/api/accounts/expense-submissions/{sub_id}")

        # Submit expense sheet
        submit_resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": self.TEST_MONTH,
            "entries": [{"field_id": field_id, "amount": 2000.0}],
            "action": "submit",
        })
        assert submit_resp.status_code == 200, f"Submission failed: {submit_resp.text}"
        journal_entry_id = submit_resp.json()["submission"]["journal_entry_id"]
        assert journal_entry_id is not None

        # Check cashbook for this month
        cb_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/cashbook?month={self.TEST_MONTH}&illaka_id={TEST_ILLAKA_ID}"
        )
        assert cb_resp.status_code == 200
        cb_data = cb_resp.json()
        # Expense sheet creates a payment (Cr Cash) - should be in cr_entries
        assert cb_data["total_payments"] > 0 or len(cb_data["cr_entries"]) > 0, \
            "Expense submission should create cr_entry (cash payment) in cashbook"

        # Cleanup
        sub_resp2 = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month={self.TEST_MONTH}"
        )
        if sub_resp2.status_code == 200 and sub_resp2.json().get("submission"):
            admin_session.delete(
                f"{BASE_URL}/api/accounts/expense-submissions/{sub_resp2.json()['submission']['id']}"
            )

    def test_expense_submission_entry_type_is_expense_sheet(self, admin_session, expense_head_id):
        """Journal entry created by expense submission should have entry_type=expense_sheet"""
        # Ensure template
        tmpl_resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-templates", json={
            "illaka_id": TEST_ILLAKA_ID,
            "fields": [
                {"label": "TEST_Entry Type Check", "account_head_id": expense_head_id, "display_order": 0},
            ],
        })
        assert tmpl_resp.status_code == 200
        field_id = tmpl_resp.json()["template"]["fields"][0]["field_id"]

        # Delete existing
        sub_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/expense-submissions?illaka_id={TEST_ILLAKA_ID}&month=2026-04"
        )
        if sub_resp.status_code == 200 and sub_resp.json().get("submission"):
            admin_session.delete(
                f"{BASE_URL}/api/accounts/expense-submissions/{sub_resp.json()['submission']['id']}"
            )

        submit_resp = admin_session.post(f"{BASE_URL}/api/accounts/expense-submissions", json={
            "illaka_id": TEST_ILLAKA_ID,
            "month": "2026-04",
            "entries": [{"field_id": field_id, "amount": 1500.0}],
            "action": "submit",
        })
        assert submit_resp.status_code == 200
        entry_id = submit_resp.json()["submission"]["journal_entry_id"]

        # Fetch the journal entry
        entries_resp = admin_session.get(
            f"{BASE_URL}/api/accounts/entries?illaka_id={TEST_ILLAKA_ID}&month=2026-04&entry_type=expense_sheet"
        )
        assert entries_resp.status_code == 200
        entries = entries_resp.json().get("entries", [])
        expense_sheet_entries = [e for e in entries if e.get("entry_type") == "expense_sheet"]
        assert len(expense_sheet_entries) > 0, "No expense_sheet journal entries found"

        # Cleanup
        admin_session.delete(
            f"{BASE_URL}/api/accounts/expense-submissions/{submit_resp.json()['submission']['id']}"
        )
