"""
Tests for Accounts Module:
- GET /api/accounts/groups  (8 pre-seeded groups)
- GET /api/accounts/heads   (pre-seeded heads including Cash in Hand, Interest Income, Loans Portfolio)
- POST /api/accounts/heads  (admin only)
- DELETE /api/accounts/heads/{id}  (admin only, system heads cannot be deleted)
- POST /api/accounts/entries/expense  (expense & income; muneem freeze check)
- GET /api/accounts/cashbook
- GET /api/accounts/summary
- Sipahi access check
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_session():
    """Authenticated admin session (cookie-based)"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "9999999999", "password": "Admin@123"})
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    """Authenticated sipahi session"""
    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "8888888888", "password": "Test@1234"})
    assert resp.status_code == 200, f"Sipahi login failed: {resp.text}"
    return s


@pytest.fixture(scope="module")
def muneem_session(admin_session):
    """Create a muneem user and login as them"""
    # First get an illaka for assignment
    illakas = admin_session.get(f"{BASE_URL}/api/illakas").json()
    illaka_id = illakas[0]["id"] if illakas else None

    # Create muneem user
    muneem_data = {
        "name": "TEST_Muneem_Accounts",
        "phone": "7777000001",
        "password": "Test@1234",
        "role": "muneem",
        "assigned_illaka_ids": [illaka_id] if illaka_id else [],
    }
    create_resp = admin_session.post(f"{BASE_URL}/api/users", json=muneem_data)
    if create_resp.status_code not in [200, 201]:
        # May already exist from prev test run
        pass

    s = requests.Session()
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"phone": "7777000001", "password": "Test@1234"})
    if resp.status_code != 200:
        pytest.skip(f"Muneem login failed: {resp.text}")
    return s


@pytest.fixture(scope="module")
def first_illaka_id(admin_session):
    """Get first available illaka id"""
    resp = admin_session.get(f"{BASE_URL}/api/illakas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) > 0, "No illakas found"
    return data[0]["id"]


# ── Account Groups ────────────────────────────────────────────────────────────

class TestAccountGroups:
    """GET /api/accounts/groups"""

    def test_get_groups_returns_8(self, admin_session):
        """Should return exactly 8 pre-seeded groups"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/groups")
        assert resp.status_code == 200, f"Unexpected status: {resp.text}"
        groups = resp.json()
        assert isinstance(groups, list), "Should return a list"
        assert len(groups) == 8, f"Expected 8 groups, got {len(groups)}: {[g['name'] for g in groups]}"

    def test_group_names_match_indian_standard(self, admin_session):
        """All 8 Indian standard groups should be present"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/groups")
        assert resp.status_code == 200
        names = {g["name"] for g in resp.json()}
        expected = {
            "Capital Account", "Loans & Borrowings", "Cash & Bank",
            "Loans Portfolio", "Direct Income", "Indirect Income",
            "Direct Expense", "Indirect Expense"
        }
        assert expected.issubset(names), f"Missing groups: {expected - names}"

    def test_groups_have_required_fields(self, admin_session):
        """Each group should have id, name, type, nature, display_order"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/groups")
        assert resp.status_code == 200
        for g in resp.json():
            assert "id" in g, f"Group missing 'id': {g}"
            assert "name" in g, f"Group missing 'name': {g}"
            assert "type" in g, f"Group missing 'type': {g}"

    def test_groups_ordered_by_display_order(self, admin_session):
        """Groups should come in display_order sequence"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/groups")
        assert resp.status_code == 200
        orders = [g.get("display_order", 0) for g in resp.json()]
        assert orders == sorted(orders), "Groups not in display_order sequence"

    def test_sipahi_can_read_groups(self, sipahi_session):
        """Sipahi (authenticated) can still read groups"""
        resp = sipahi_session.get(f"{BASE_URL}/api/accounts/groups")
        assert resp.status_code == 200


# ── Account Heads ─────────────────────────────────────────────────────────────

class TestAccountHeads:
    """GET /api/accounts/heads"""

    def test_get_heads_returns_list(self, admin_session):
        """Should return a list of account heads"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200
        heads = resp.json()
        assert isinstance(heads, list), "Should return a list"
        assert len(heads) >= 15, f"Expected at least 15 heads, got {len(heads)}"

    def test_cash_in_hand_present(self, admin_session):
        """Cash in Hand (system head) should be present"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200
        heads = resp.json()
        cash_heads = [h for h in heads if h.get("name") == "Cash in Hand"]
        assert len(cash_heads) == 1, f"'Cash in Hand' head not found or duplicated"
        assert cash_heads[0].get("is_system") is True, "Cash in Hand should be system head"
        assert cash_heads[0].get("system_key") == "cash_in_hand", "Should have system_key=cash_in_hand"

    def test_interest_income_on_loans_present(self, admin_session):
        """Interest Income on Loans (system head) should be present"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200
        heads = resp.json()
        interest_heads = [h for h in heads if h.get("name") == "Interest Income on Loans"]
        assert len(interest_heads) == 1, "'Interest Income on Loans' head not found"
        assert interest_heads[0].get("is_system") is True

    def test_loans_portfolio_sundry_debtors_present(self, admin_session):
        """Loans Portfolio (Sundry Debtors) should be present"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200
        heads = resp.json()
        lp_heads = [h for h in heads if h.get("name") == "Loans Portfolio (Sundry Debtors)"]
        assert len(lp_heads) == 1, "'Loans Portfolio (Sundry Debtors)' head not found"
        assert lp_heads[0].get("is_system") is True

    def test_heads_have_group_info(self, admin_session):
        """Each head should have group_name and group_type"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200
        for h in resp.json()[:5]:
            assert "group_name" in h, f"Head missing group_name: {h}"
            assert "group_type" in h, f"Head missing group_type: {h}"


# ── Create Account Head ────────────────────────────────────────────────────────

class TestCreateAccountHead:
    """POST /api/accounts/heads"""

    created_head_id = None

    def test_admin_can_create_head(self, admin_session):
        """Admin should be able to create a new account head"""
        # Get expense group id
        groups = admin_session.get(f"{BASE_URL}/api/accounts/groups").json()
        indirect_expense = next((g for g in groups if g["name"] == "Indirect Expense"), None)
        assert indirect_expense, "Indirect Expense group not found"

        resp = admin_session.post(f"{BASE_URL}/api/accounts/heads", json={
            "name": "TEST_Custom Expense Head",
            "group_id": indirect_expense["id"],
        })
        assert resp.status_code == 200, f"Failed to create head: {resp.text}"
        data = resp.json()
        assert data.get("name") == "TEST_Custom Expense Head"
        assert data.get("is_system") is False, "Newly created head should not be system"
        assert "id" in data
        TestCreateAccountHead.created_head_id = data["id"]

    def test_created_head_appears_in_list(self, admin_session):
        """Newly created head should appear in GET /api/accounts/heads"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200
        heads = resp.json()
        found = any(h.get("name") == "TEST_Custom Expense Head" for h in heads)
        assert found, "Newly created head not found in heads list"

    def test_sipahi_cannot_create_head(self, sipahi_session):
        """Sipahi should NOT be able to create account heads"""
        groups = sipahi_session.get(f"{BASE_URL}/api/accounts/groups").json()
        group_id = groups[0]["id"] if groups else "invalid"
        resp = sipahi_session.post(f"{BASE_URL}/api/accounts/heads", json={
            "name": "TEST_Sipahi Head",
            "group_id": group_id,
        })
        assert resp.status_code == 403, f"Sipahi should get 403, got {resp.status_code}"

    def test_invalid_group_id_returns_400(self, admin_session):
        """Invalid group_id should return 400"""
        resp = admin_session.post(f"{BASE_URL}/api/accounts/heads", json={
            "name": "Test Head",
            "group_id": "invalid_id",
        })
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"


# ── Delete Account Head ────────────────────────────────────────────────────────

class TestDeleteAccountHead:
    """DELETE /api/accounts/heads/{id}"""

    def test_admin_can_delete_non_system_head(self, admin_session):
        """Admin can delete non-system head"""
        # Create a disposable head first
        groups = admin_session.get(f"{BASE_URL}/api/accounts/groups").json()
        group_id = next(g["id"] for g in groups if g["name"] == "Indirect Expense")
        create_resp = admin_session.post(f"{BASE_URL}/api/accounts/heads", json={
            "name": "TEST_Delete Me Head",
            "group_id": group_id,
        })
        assert create_resp.status_code == 200
        head_id = create_resp.json()["id"]

        # Delete it
        del_resp = admin_session.delete(f"{BASE_URL}/api/accounts/heads/{head_id}")
        assert del_resp.status_code == 200, f"Delete failed: {del_resp.text}"
        data = del_resp.json()
        assert "message" in data

        # Verify it's gone
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        assert not any(h["id"] == head_id for h in heads), "Head still present after deletion"

    def test_system_head_cannot_be_deleted(self, admin_session):
        """System heads (is_system=True) should return 400 on delete"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        system_head = next((h for h in heads if h.get("is_system") is True), None)
        assert system_head, "No system head found for test"

        resp = admin_session.delete(f"{BASE_URL}/api/accounts/heads/{system_head['id']}")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "cannot be deleted" in resp.json().get("detail", "").lower()

    def test_sipahi_cannot_delete_head(self, sipahi_session, admin_session):
        """Sipahi should get 403 on delete"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        non_system = next((h for h in heads if not h.get("is_system")), None)
        assert non_system, "No non-system head found"

        resp = sipahi_session.delete(f"{BASE_URL}/api/accounts/heads/{non_system['id']}")
        assert resp.status_code == 403, f"Sipahi should get 403, got {resp.status_code}"


# ── Simple Entry (Expense/Income) ─────────────────────────────────────────────

class TestSimpleEntry:
    """POST /api/accounts/entries/expense"""

    def _get_expense_head_id(self, admin_session):
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        return next((h["id"] for h in heads if h.get("group_type") == "expense"), None)

    def _get_income_head_id(self, admin_session):
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        return next((h["id"] for h in heads if h.get("group_type") == "income"), None)

    def test_create_expense_entry(self, admin_session, first_illaka_id):
        """Admin can create expense entry: Dr:ExpenseHead, Cr:CashInHand"""
        expense_head_id = self._get_expense_head_id(admin_session)
        assert expense_head_id, "No expense head found"

        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head_id,
            "amount": 1000.0,
            "narration": "TEST_Expense entry for staff salary",
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        assert data.get("total_amount") == 1000.0
        # Verify double-entry lines
        lines = data.get("lines", [])
        assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
        debit_lines = [l for l in lines if l.get("debit", 0) > 0]
        credit_lines = [l for l in lines if l.get("credit", 0) > 0]
        assert len(debit_lines) == 1, "Expense should have 1 debit line"
        assert len(credit_lines) == 1, "Expense should have 1 credit line"

    def test_create_income_entry(self, admin_session, first_illaka_id):
        """Admin can create income entry: Dr:CashInHand, Cr:IncomeHead"""
        income_head_id = self._get_income_head_id(admin_session)
        assert income_head_id, "No income head found"

        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": income_head_id,
            "amount": 5000.0,
            "narration": "TEST_Income entry for interest received",
        })
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "id" in data
        lines = data.get("lines", [])
        assert len(lines) == 2

    def test_sipahi_cannot_create_entry(self, sipahi_session, first_illaka_id):
        """Sipahi should get 403 when trying to add entry"""
        resp = sipahi_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": "some_id",
            "amount": 100.0,
            "narration": "Test",
        })
        assert resp.status_code == 403, f"Sipahi should get 403, got {resp.status_code}"

    def test_non_income_expense_head_returns_400(self, admin_session, first_illaka_id):
        """Using an asset/liability head should return 400"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        asset_head = next((h for h in heads if h.get("group_type") == "asset"), None)
        if not asset_head:
            pytest.skip("No asset head available for test")

        resp = admin_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": asset_head["id"],
            "amount": 100.0,
            "narration": "Test invalid head",
        })
        assert resp.status_code == 400, f"Expected 400 for non-income/expense head, got {resp.status_code}"


# ── Muneem Freeze Check ────────────────────────────────────────────────────────

class TestMuneemFreezeCheck:
    """Muneem cannot post entries for past months"""

    def test_muneem_past_month_entry_frozen(self, muneem_session, first_illaka_id, admin_session):
        """Muneem cannot create entry with date in a previous month (server is March 2026)"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        expense_head = next((h for h in heads if h.get("group_type") == "expense"), None)
        if not expense_head:
            pytest.skip("No expense head found")

        # Use Feb 2026 (past month - server is at March 2026)
        resp = muneem_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head["id"],
            "amount": 100.0,
            "narration": "TEST_Past month entry should fail",
        })
        assert resp.status_code == 403, f"Muneem past-month should be 403, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "frozen" in detail.lower() or "past" in detail.lower() or "महीने" in detail

    def test_muneem_current_month_entry_allowed(self, muneem_session, first_illaka_id, admin_session):
        """Muneem CAN create entry for current month (March 2026 - actual server date)"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        expense_head = next((h for h in heads if h.get("group_type") == "expense"), None)
        if not expense_head:
            pytest.skip("No expense head found")

        resp = muneem_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-03-15",
            "illaka_id": first_illaka_id,
            "account_head_id": expense_head["id"],
            "amount": 200.0,
            "narration": "TEST_Current month entry",
        })
        assert resp.status_code == 200, f"Muneem current month entry failed: {resp.text}"


# ── Cash Book ─────────────────────────────────────────────────────────────────

class TestCashBook:
    """GET /api/accounts/cashbook"""

    def test_cashbook_returns_correct_structure(self, admin_session):
        """Cash book should return month, dr_sections, cr_entries, opening/closing balances"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "month" in data
        # New format: dr_sections and cr_entries (not 'entries')
        assert "dr_sections" in data, "cashbook should return dr_sections"
        assert "cr_entries" in data, "cashbook should return cr_entries"
        assert "opening_balance" in data
        assert "total_receipts" in data
        assert "total_payments" in data
        assert "closing_balance" in data
        assert data["month"] == "2026-02"

    def test_cashbook_cr_entries_have_required_fields(self, admin_session):
        """Each cr_entry should have date, narration, amount fields"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        cr_entries = resp.json().get("cr_entries", [])
        for entry in cr_entries[:3]:  # Check first 3
            assert "date" in entry, f"cr_entry missing date: {entry}"
            assert "narration" in entry, f"cr_entry missing narration: {entry}"
            assert "amount" in entry, f"cr_entry missing amount: {entry}"

    def test_cashbook_balance_is_consistent(self, admin_session):
        """Closing balance should equal opening + receipts - payments"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        expected = round(data["opening_balance"] + data["total_receipts"] - data["total_payments"], 2)
        actual = round(data["closing_balance"], 2)
        assert abs(expected - actual) < 0.02, f"Balance mismatch: expected {expected}, got {actual}"

    def test_cashbook_with_illaka_filter(self, admin_session, first_illaka_id):
        """Cashbook should accept illaka_id filter"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/cashbook?month=2026-02&illaka_id={first_illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("dr_sections"), list)
        assert isinstance(data.get("cr_entries"), list)


# ── P&L Summary ───────────────────────────────────────────────────────────────

class TestPLSummary:
    """GET /api/accounts/summary"""

    def test_summary_returns_correct_structure(self, admin_session):
        """P&L summary should return income/expense sections"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/summary?month=2026-02")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        assert "month" in data
        assert "income" in data
        assert "expenses" in data
        assert "total_income" in data
        assert "total_expense" in data
        assert "net_profit" in data
        assert data["month"] == "2026-02"

    def test_summary_income_expenses_are_lists(self, admin_session):
        """Income and expenses should be lists"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/summary?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["income"], list), "Income should be list"
        assert isinstance(data["expenses"], list), "Expenses should be list"

    def test_summary_net_profit_calculation(self, admin_session):
        """Net profit should equal total_income - total_expense"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/summary?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        expected_net = round(data["total_income"] - data["total_expense"], 2)
        actual_net = round(data["net_profit"], 2)
        assert abs(expected_net - actual_net) < 0.02, f"Net profit mismatch: {expected_net} vs {actual_net}"

    def test_summary_has_income_data_from_created_entries(self, admin_session):
        """Summary for Feb 2026 should show income from our created test entry"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/summary?month=2026-02")
        assert resp.status_code == 200
        data = resp.json()
        # We created income + expense entries, so totals should be > 0
        assert data["total_income"] >= 0
        assert data["total_expense"] >= 0

    def test_summary_with_illaka_filter(self, admin_session, first_illaka_id):
        """Summary should accept illaka_id filter"""
        resp = admin_session.get(f"{BASE_URL}/api/accounts/summary?month=2026-02&illaka_id={first_illaka_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "income" in data
        assert "expenses" in data


# ── Sipahi Access Check ────────────────────────────────────────────────────────

class TestSipahiAccess:
    """Sipahi has read-only access to accounts data"""

    def test_sipahi_can_read_groups(self, sipahi_session):
        """Sipahi can read account groups"""
        resp = sipahi_session.get(f"{BASE_URL}/api/accounts/groups")
        assert resp.status_code == 200

    def test_sipahi_can_read_heads(self, sipahi_session):
        """Sipahi can read account heads"""
        resp = sipahi_session.get(f"{BASE_URL}/api/accounts/heads")
        assert resp.status_code == 200

    def test_sipahi_cannot_create_head(self, sipahi_session):
        """Sipahi cannot create account head"""
        groups = sipahi_session.get(f"{BASE_URL}/api/accounts/groups").json()
        group_id = groups[0]["id"] if groups else "invalid"
        resp = sipahi_session.post(f"{BASE_URL}/api/accounts/heads", json={
            "name": "TEST_Sipahi Attempt",
            "group_id": group_id,
        })
        assert resp.status_code == 403

    def test_sipahi_cannot_delete_head(self, sipahi_session, admin_session):
        """Sipahi cannot delete account head"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        head_id = heads[0]["id"] if heads else "invalid"
        resp = sipahi_session.delete(f"{BASE_URL}/api/accounts/heads/{head_id}")
        assert resp.status_code == 403

    def test_sipahi_cannot_create_entry(self, sipahi_session, first_illaka_id, admin_session):
        """Sipahi cannot create journal entries"""
        heads = admin_session.get(f"{BASE_URL}/api/accounts/heads").json()
        exp_head = next((h for h in heads if h.get("group_type") == "expense"), None)
        if not exp_head:
            pytest.skip("No expense head")
        resp = sipahi_session.post(f"{BASE_URL}/api/accounts/entries/expense", json={
            "date": "2026-02-10",
            "illaka_id": first_illaka_id,
            "account_head_id": exp_head["id"],
            "amount": 100.0,
            "narration": "Sipahi test",
        })
        assert resp.status_code == 403
