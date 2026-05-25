"""
Tests for Loan EMI feature - Bahi Khata
Covers: EMI creation, schedule, collect, undo, duplicate Aadhaar, loan list
"""
import pytest
import requests
import os
from datetime import date, datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@bahikhata.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "Admin@123")
SIPAHI_EMAIL = os.getenv("TEST_SIPAHI_EMAIL", "TEST_sipahi_loans@bahikhata.com")
SIPAHI_PASSWORD = os.getenv("TEST_USER_PASSWORD", "Test@1234")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SIPAHI_EMAIL, "password": SIPAHI_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Sipahi login failed: {r.text}")
    return s


@pytest.fixture(scope="module")
def illaka_and_misal(admin_session):
    """Get or create illaka/misal for testing"""
    r = admin_session.get(f"{BASE_URL}/api/illakas")
    assert r.status_code == 200
    illakas = r.json()
    if illakas:
        illaka = illakas[0]
    else:
        r2 = admin_session.post(f"{BASE_URL}/api/illakas", json={"name": "TEST_Illaka"})
        assert r2.status_code == 200
        illaka = r2.json()
    
    r3 = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={illaka['id']}")
    assert r3.status_code == 200
    misals = r3.json()
    if misals:
        misal = misals[0]
    else:
        r4 = admin_session.post(f"{BASE_URL}/api/misals", json={"name": "TEST_Misal", "illaka_id": illaka['id']})
        assert r4.status_code == 200
        misal = r4.json()
    
    return illaka, misal


@pytest.fixture(scope="module")
def created_loan(sipahi_session, illaka_and_misal):
    """Create a loan with principal 10300"""
    illaka, misal = illaka_and_misal
    today = date.today().isoformat()
    payload = {
        "kyc_id": "000000000000000000000000",  # dummy
        "client_name": "TEST_LoanClient",
        "client_phone": "9999999999",
        "illaka_id": illaka['id'],
        "illaka_name": illaka['name'],
        "misal_id": misal['id'],
        "misal_name": misal['name'],
        "principal_amount": 10300,
        "loan_date": today,
        "notes": "Test loan"
    }
    r = sipahi_session.post(f"{BASE_URL}/api/loans", json=payload)
    assert r.status_code == 200, f"Loan creation failed: {r.text}"
    return r.json()


class TestLoanEMICalc:
    """Test EMI calculation for principal=10300"""
    
    def test_loan_created_with_correct_emi(self, created_loan):
        loan = created_loan
        assert loan['emi_amount'] == 1000, f"Expected 1000, got {loan['emi_amount']}"
        print(f"PASS: emi_amount={loan['emi_amount']}")
    
    def test_loan_total_repayable(self, created_loan):
        assert created_loan['total_repayable'] == 12000, f"Expected 12000, got {created_loan['total_repayable']}"
        print(f"PASS: total_repayable={created_loan['total_repayable']}")
    
    def test_loan_interest_amount(self, created_loan):
        assert created_loan['interest_amount'] == 1700, f"Expected 1700, got {created_loan['interest_amount']}"
        print(f"PASS: interest_amount={created_loan['interest_amount']}")
    
    def test_emi_schedule_has_12_items(self, created_loan):
        schedule = created_loan.get('emi_schedule', [])
        assert len(schedule) == 12, f"Expected 12 EMIs, got {len(schedule)}"
        print(f"PASS: schedule has {len(schedule)} items")
    
    def test_first_emi_due_month_is_next_month(self, created_loan):
        schedule = created_loan.get('emi_schedule', [])
        assert len(schedule) > 0
        loan_date = date.fromisoformat(created_loan['loan_date'])
        # First EMI should be 1 month after loan_date
        m = loan_date.month % 12 + 1
        y = loan_date.year + (1 if loan_date.month == 12 else 0)
        expected = f"{y}-{m:02d}"
        assert schedule[0]['due_month'] == expected, f"Expected {expected}, got {schedule[0]['due_month']}"
        print(f"PASS: first due_month={schedule[0]['due_month']}")
    
    def test_interest_rate_fixed_17(self, created_loan):
        assert created_loan['interest_rate'] == 17.0
        print(f"PASS: interest_rate={created_loan['interest_rate']}")


class TestLoanGet:
    """Test GET /api/loans/{id} and overdue computation"""
    
    def test_get_loan_returns_emi_schedule(self, admin_session, created_loan):
        loan_id = created_loan['id']
        r = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert r.status_code == 200
        data = r.json()
        assert 'emi_schedule' in data
        assert len(data['emi_schedule']) == 12
        print(f"PASS: GET loan returns 12 EMI items, status={data['status']}")
    
    def test_past_emis_are_overdue(self, admin_session, created_loan):
        """Since loan is created today, all EMIs are past months → should be overdue"""
        # Actually if loan is created TODAY, EMIs start next month forward
        # But if loan_date is today 2026-02, first EMI is 2026-03 which is next month (not past)
        # So this test validates the current status
        loan_id = created_loan['id']
        r = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        data = r.json()
        schedule = data['emi_schedule']
        today = date.today()
        # Check each EMI status is correct
        for emi in schedule:
            y, mo = map(int, emi['due_month'].split('-'))
            import calendar
            last_day = calendar.monthrange(y, mo)[1]
            month_end = date(y, mo, last_day)
            if today > month_end and emi['status'] != 'paid':
                assert emi['status'] == 'overdue', f"EMI {emi['due_month']} should be overdue"
        print("PASS: Overdue logic correct")


class TestCollectEMI:
    """Test POST /api/loans/{id}/payments"""
    
    @pytest.fixture(scope="class")
    def loan_with_future_emi(self, sipahi_session, illaka_and_misal):
        """Create loan with a future date so EMIs are pending"""
        illaka, misal = illaka_and_misal
        # Use date 1 year ago to have overdue EMIs to collect
        from datetime import timedelta
        past_date = (date.today().replace(year=date.today().year - 1)).isoformat()
        payload = {
            "kyc_id": "000000000000000000000000",
            "client_name": "TEST_CollectClient",
            "client_phone": "8888888888",
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "principal_amount": 10300,
            "loan_date": past_date,
        }
        r = sipahi_session.post(f"{BASE_URL}/api/loans", json=payload)
        assert r.status_code == 200
        return r.json()
    
    def test_collect_emi_marks_as_paid(self, sipahi_session, loan_with_future_emi):
        loan = loan_with_future_emi
        schedule = loan['emi_schedule']
        first_emi_month = schedule[0]['due_month']
        r = sipahi_session.post(f"{BASE_URL}/api/loans/{loan['id']}/payments", json={
            "emi_month": first_emi_month,
            "amount": 1000,
            "payment_date": date.today().isoformat()
        })
        assert r.status_code == 200, f"Collect failed: {r.text}"
        data = r.json()
        emi = next(e for e in data['emi_schedule'] if e['due_month'] == first_emi_month)
        assert emi['status'] == 'paid'
        assert data['total_paid'] == 1000
        print(f"PASS: EMI {first_emi_month} collected, total_paid={data['total_paid']}")
    
    def test_double_collect_returns_400(self, sipahi_session, loan_with_future_emi):
        loan = loan_with_future_emi
        first_emi_month = loan['emi_schedule'][0]['due_month']
        r = sipahi_session.post(f"{BASE_URL}/api/loans/{loan['id']}/payments", json={
            "emi_month": first_emi_month,
            "amount": 1000,
            "payment_date": date.today().isoformat()
        })
        assert r.status_code == 400
        print("PASS: Double collect returns 400")


class TestUndoEMI:
    """Test DELETE /api/loans/{id}/payments/{emi_month}"""
    
    def test_undo_emi_admin_allowed(self, admin_session, sipahi_session, illaka_and_misal):
        illaka, misal = illaka_and_misal
        past_date = date.today().replace(year=date.today().year - 1).isoformat()
        # Create loan
        r = sipahi_session.post(f"{BASE_URL}/api/loans", json={
            "kyc_id": "000000000000000000000000",
            "client_name": "TEST_UndoClient",
            "client_phone": "7777777777",
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "principal_amount": 10300,
            "loan_date": past_date,
        })
        assert r.status_code == 200
        loan = r.json()
        emi_month = loan['emi_schedule'][0]['due_month']
        # Collect
        sipahi_session.post(f"{BASE_URL}/api/loans/{loan['id']}/payments", json={
            "emi_month": emi_month, "amount": 1000, "payment_date": date.today().isoformat()
        })
        # Undo via admin
        r2 = admin_session.delete(f"{BASE_URL}/api/loans/{loan['id']}/payments/{emi_month}")
        assert r2.status_code == 200, f"Undo failed: {r2.text}"
        # Verify EMI is back to overdue/pending
        r3 = admin_session.get(f"{BASE_URL}/api/loans/{loan['id']}")
        data = r3.json()
        emi = next(e for e in data['emi_schedule'] if e['due_month'] == emi_month)
        assert emi['status'] in ['overdue', 'pending']
        print(f"PASS: EMI undone, status={emi['status']}")
    
    def test_undo_emi_sipahi_forbidden(self, sipahi_session, created_loan):
        emi_month = created_loan['emi_schedule'][0]['due_month']
        r = sipahi_session.delete(f"{BASE_URL}/api/loans/{created_loan['id']}/payments/{emi_month}")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"
        print("PASS: Sipahi cannot undo EMI")


class TestDuplicateAadhaar:
    """Test duplicate Aadhaar detection"""
    
    def test_duplicate_aadhaar_returns_400(self, sipahi_session, illaka_and_misal):
        illaka, misal = illaka_and_misal
        aadhaar = "1234 5678 9012"
        kyc_payload = {
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": "TEST_DupAadhaar",
                "aadhaar_number": aadhaar
            }
        }
        # First KYC - may or may not succeed (aadhaar may already exist)
        r1 = sipahi_session.post(f"{BASE_URL}/api/kycs", json=kyc_payload)
        if r1.status_code == 400 and "Duplicate" in r1.text:
            print("PASS: Aadhaar already exists, duplicate detected on first call")
            return
        assert r1.status_code == 200, f"First KYC failed: {r1.text}"
        # Second KYC with same Aadhaar
        r2 = sipahi_session.post(f"{BASE_URL}/api/kycs", json=kyc_payload)
        assert r2.status_code == 400
        assert "duplicate" in r2.text.lower() or "KYC already exists" in r2.text
        print("PASS: Duplicate Aadhaar returns 400")


class TestLoanList:
    """Test GET /api/loans"""
    
    def test_list_loans_returns_data(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/loans")
        assert r.status_code == 200
        data = r.json()
        assert 'loans' in data
        assert 'total' in data
        print(f"PASS: Loan list returns {data['total']} loans")
    
    def test_list_loans_have_status(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/loans")
        data = r.json()
        if data['loans']:
            for loan in data['loans'][:5]:
                assert 'status' in loan
                assert loan['status'] in ['active', 'overdue', 'closed']
        print("PASS: All loans have valid status field")
    
    def test_kyc_with_disbursement_creates_loan(self, sipahi_session, illaka_and_misal):
        """Test KYC auto-creates loan if disbursement_amount provided"""
        illaka, misal = illaka_and_misal
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {"name": "TEST_DisburseClient", "phone": "6666666666"},
            "disbursement_amount": 10300
        })
        assert r.status_code == 200, f"KYC create failed: {r.text}"
        data = r.json()
        assert data.get('loan_id') is not None, f"Expected loan_id in KYC response, got: {data}"
        loan_id = data['loan_id']
        print(f"PASS: KYC auto-created loan_id={loan_id}")
        # Verify loan exists
        r2 = sipahi_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert r2.status_code == 200
        loan = r2.json()
        assert loan['emi_amount'] == 1000
        assert loan['total_repayable'] == 12000
        print("PASS: Auto-created loan has correct EMI values")
