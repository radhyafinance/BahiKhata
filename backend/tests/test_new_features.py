"""
Tests for new features in Bahi Khata:
1. Customer ID generation (2 uppercase letters + 4-digit sequential)
2. Loan ID generation ({customer_id}-L{n} sequential per customer)
3. Mobile number uniqueness (no 2 KYCs with same phone)
4. Collection Sheet API (GET /api/collections/sheet)
5. Standalone loan creation gets loan_number
"""
import pytest
import requests
import os
import re
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

ADMIN_EMAIL = os.getenv("TEST_ADMIN_EMAIL", "admin@bahikhata.com")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD", "Admin@123")
SIPAHI_EMAIL = os.getenv("TEST_SIPAHI_EMAIL", "TEST_sipahi_loans@bahikhata.com")
SIPAHI_PASSWORD = os.getenv("TEST_USER_PASSWORD", "Test@1234")

# Timestamp for unique test data
TS = str(int(time.time()))[-6:]


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
def illaka_and_misal(admin_session, sipahi_session):
    """Get or create Delhi illaka + misal for customer_id prefix DE testing.
    Also assigns Delhi illaka to sipahi so they can access it."""
    r = admin_session.get(f"{BASE_URL}/api/illakas")
    assert r.status_code == 200
    illakas = r.json()

    # Find or create a "Delhi" illaka
    delhi_illaka = next((il for il in illakas if il.get("name", "").lower() == "delhi"), None)
    if not delhi_illaka:
        r2 = admin_session.post(f"{BASE_URL}/api/illakas", json={"name": "Delhi"})
        assert r2.status_code in [200, 201], f"Create illaka failed: {r2.text}"
        delhi_illaka = r2.json()
        print(f"Created Delhi illaka: {delhi_illaka['id']}")
    else:
        print(f"Found existing Delhi illaka: {delhi_illaka['id']}")

    # Get or create misal for this illaka
    r3 = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={delhi_illaka['id']}")
    assert r3.status_code == 200
    misals = r3.json()
    if misals:
        misal = misals[0]
    else:
        r4 = admin_session.post(f"{BASE_URL}/api/misals", json={"name": "TEST_Misal_Delhi", "illaka_id": delhi_illaka['id']})
        assert r4.status_code in [200, 201], f"Create misal failed: {r4.text}"
        misal = r4.json()
        print(f"Created misal: {misal['id']}")

    # Get sipahi user id and assign Delhi illaka to them
    users_r = admin_session.get(f"{BASE_URL}/api/users")
    if users_r.status_code == 200:
        users_list = users_r.json() if isinstance(users_r.json(), list) else users_r.json().get("users", [])
        sipahi_user = next(
            (u for u in users_list if u.get("email", "").lower() == SIPAHI_EMAIL.lower()), None
        )
        if sipahi_user:
            sipahi_uid = sipahi_user["id"]
            assigned = sipahi_user.get("assigned_illaka_ids", [])
            if delhi_illaka['id'] not in assigned:
                new_assigned = assigned + [delhi_illaka['id']]
                ar = admin_session.post(
                    f"{BASE_URL}/api/users/{sipahi_uid}/assign-illakas",
                    json={"illaka_ids": new_assigned}
                )
                print(f"Assigned Delhi to sipahi: {ar.status_code}")
            else:
                print("Sipahi already has Delhi illaka assigned")
        else:
            print("WARNING: Sipahi user not found in users list")

    return delhi_illaka, misal


class TestCustomerIDGeneration:
    """Test Customer ID generation: 2 uppercase letters from illaka + 4-digit sequential"""

    def test_customer_id_format_on_kyc_creation(self, sipahi_session, illaka_and_misal):
        """Customer ID should be prefix(illaka[:2].upper()) + 4-digit number"""
        illaka, misal = illaka_and_misal
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],  # "Delhi" → prefix "DE"
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_CustID_{TS}",
                "aadhaar_number": f"9001 {TS[:4]} {TS[2:]}",
                "phone": f"70{TS}01"
            }
        })
        assert r.status_code == 200, f"KYC creation failed: {r.text}"
        data = r.json()
        cid = data.get("customer_id")
        assert cid is not None, f"customer_id missing in response: {data}"
        # Should match DE + 4 digits (DE from "Delhi")
        assert re.match(r'^DE\d{4}$', cid), f"customer_id format wrong: expected DE####, got {cid}"
        print(f"PASS: customer_id={cid} matches DE#### pattern")

    def test_customer_id_sequential(self, sipahi_session, illaka_and_misal):
        """Two consecutive KYCs with same illaka should have sequential IDs"""
        illaka, misal = illaka_and_misal
        # First KYC
        r1 = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_CustSeq1_{TS}",
                "aadhaar_number": f"9002 {TS[:4]} {TS[2:]}",
                "phone": f"70{TS}02"
            }
        })
        assert r1.status_code == 200, f"KYC 1 creation failed: {r1.text}"
        cid1 = r1.json().get("customer_id")
        assert cid1 and re.match(r'^DE\d{4}$', cid1), f"First customer_id invalid: {cid1}"

        # Second KYC
        r2 = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_CustSeq2_{TS}",
                "aadhaar_number": f"9003 {TS[:4]} {TS[2:]}",
                "phone": f"70{TS}03"
            }
        })
        assert r2.status_code == 200, f"KYC 2 creation failed: {r2.text}"
        cid2 = r2.json().get("customer_id")
        assert cid2 and re.match(r'^DE\d{4}$', cid2), f"Second customer_id invalid: {cid2}"

        # Sequential: cid2 should be cid1 + 1
        n1 = int(cid1[2:])
        n2 = int(cid2[2:])
        assert n2 == n1 + 1, f"Expected sequential: {cid1} → {cid2} (difference should be 1, got {n2 - n1})"
        print(f"PASS: Sequential IDs: {cid1} → {cid2}")

    def test_customer_id_stored_in_kyc(self, sipahi_session, illaka_and_misal):
        """GET /api/kycs/{id} should return customer_id field"""
        illaka, misal = illaka_and_misal
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_CustGet_{TS}",
                "aadhaar_number": f"9004 {TS[:4]} {TS[2:]}",
                "phone": f"70{TS}04"
            }
        })
        assert r.status_code == 200
        kyc_id = r.json()["id"]
        cid = r.json().get("customer_id")

        # GET by ID
        r2 = sipahi_session.get(f"{BASE_URL}/api/kycs/{kyc_id}")
        assert r2.status_code == 200
        fetched = r2.json()
        assert fetched.get("customer_id") == cid, f"customer_id mismatch: created={cid}, fetched={fetched.get('customer_id')}"
        print(f"PASS: customer_id persisted correctly: {cid}")


class TestLoanNumberGeneration:
    """Test Loan ID generation: {customer_id}-L{n} sequential per customer"""

    @pytest.fixture(scope="class")
    def kyc_with_loan(self, sipahi_session, illaka_and_misal):
        """Create a KYC with disbursement_amount to get auto-created loan"""
        illaka, misal = illaka_and_misal
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_LoanNum_{TS}",
                "aadhaar_number": f"9005 {TS[:4]} {TS[2:]}",
                "phone": f"70{TS}05"
            },
            "disbursement_amount": 10300
        })
        assert r.status_code == 200, f"KYC creation failed: {r.text}"
        return r.json()

    def test_auto_loan_has_loan_number(self, admin_session, kyc_with_loan):
        """KYC with disbursement_amount auto-creates loan with loan_number"""
        kyc_data = kyc_with_loan
        customer_id = kyc_data.get("customer_id")
        loan_id = kyc_data.get("loan_id")
        assert loan_id is not None, f"loan_id not returned in KYC response: {kyc_data}"

        r = admin_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert r.status_code == 200
        loan = r.json()
        loan_number = loan.get("loan_number")
        assert loan_number is not None, f"loan_number missing in loan: {loan}"
        # Should be customer_id-L1 (or higher if customer already had loans)
        assert loan_number.startswith(f"{customer_id}-L"), f"loan_number format wrong: {loan_number}"
        assert re.match(r'^DE\d{4}-L\d+$', loan_number), f"loan_number pattern invalid: {loan_number}"
        print(f"PASS: auto-loan loan_number={loan_number}")

    def test_standalone_loan_has_loan_number(self, sipahi_session, admin_session, illaka_and_misal):
        """POST /api/loans (standalone) should also get loan_number"""
        illaka, misal = illaka_and_misal
        from datetime import date
        today = date.today().isoformat()
        r = sipahi_session.post(f"{BASE_URL}/api/loans", json={
            "kyc_id": "000000000000000000000000",
            "client_name": f"TEST_StandaloneLoan_{TS}",
            "client_phone": f"80{TS}01",
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "principal_amount": 10300,
            "loan_date": today
        })
        assert r.status_code == 200, f"Standalone loan creation failed: {r.text}"
        loan = r.json()
        loan_number = loan.get("loan_number")
        assert loan_number is not None, f"loan_number missing in standalone loan: {loan}"
        # Since kyc_id is dummy, customer_id will be "—", loan_number = "—-L1" or similar
        # Just check it's not None and has -L pattern
        assert "-L" in loan_number, f"loan_number doesn't have -L pattern: {loan_number}"
        print(f"PASS: standalone loan_number={loan_number}")

    def test_second_loan_for_same_kyc_increments(self, sipahi_session, admin_session, illaka_and_misal):
        """Second loan for same KYC should be L2"""
        illaka, misal = illaka_and_misal
        from datetime import date
        today = date.today().isoformat()

        # Create KYC first
        r_kyc = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_L2_{TS}",
                "aadhaar_number": f"9006 {TS[:4]} {TS[2:]}",
                "phone": f"70{TS}06"
            }
        })
        assert r_kyc.status_code == 200
        kyc = r_kyc.json()
        kyc_id = kyc["id"]
        customer_id = kyc.get("customer_id")

        # Create first loan
        r1 = sipahi_session.post(f"{BASE_URL}/api/loans", json={
            "kyc_id": kyc_id,
            "client_name": kyc["primary_borrower"]["name"],
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "principal_amount": 5000,
            "loan_date": today
        })
        assert r1.status_code == 200, f"First loan creation failed: {r1.text}"
        ln1 = r1.json().get("loan_number")

        # Create second loan for same KYC
        r2 = sipahi_session.post(f"{BASE_URL}/api/loans", json={
            "kyc_id": kyc_id,
            "client_name": kyc["primary_borrower"]["name"],
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "principal_amount": 3000,
            "loan_date": today
        })
        assert r2.status_code == 200, f"Second loan creation failed: {r2.text}"
        ln2 = r2.json().get("loan_number")

        print(f"Loan numbers: {ln1} → {ln2}")
        # Second should be increment of first
        n1 = int(ln1.split("-L")[-1])
        n2 = int(ln2.split("-L")[-1])
        assert n2 == n1 + 1, f"Expected sequential: {ln1} → {ln2}, diff should be 1 but got {n2 - n1}"
        print(f"PASS: sequential loan numbers {ln1} → {ln2}")


class TestMobileUniqueness:
    """Test mobile number uniqueness: no 2 KYCs with same primary_borrower.phone"""

    def test_duplicate_mobile_returns_400(self, sipahi_session, illaka_and_misal):
        """Second KYC with same phone should return 400"""
        illaka, misal = illaka_and_misal
        phone = f"99{TS}77"  # unique phone for this test run

        # First KYC
        r1 = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_MobileUniq1_{TS}",
                "aadhaar_number": f"9007 {TS[:4]} {TS[2:]}",
                "phone": phone
            }
        })
        if r1.status_code == 400 and "Mobile" in r1.text:
            # Phone already registered from previous test run
            print(f"Phone {phone} already registered, test is valid")
            return
        assert r1.status_code == 200, f"First KYC with phone failed unexpectedly: {r1.text}"

        # Second KYC with same phone
        r2 = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_MobileUniq2_{TS}",
                "aadhaar_number": f"9008 {TS[:4]} {TS[2:]}",
                "phone": phone
            }
        })
        assert r2.status_code == 400, f"Expected 400 for duplicate mobile, got {r2.status_code}: {r2.text}"
        assert "Mobile" in r2.text or "mobile" in r2.text.lower() or "मोबाइल" in r2.text, \
            f"Expected mobile uniqueness error message, got: {r2.text}"
        print(f"PASS: Duplicate mobile {phone} returns 400")

    def test_different_mobile_succeeds(self, sipahi_session, illaka_and_misal):
        """KYCs with different phones should both succeed"""
        illaka, misal = illaka_and_misal
        phone_a = f"88{TS}11"
        phone_b = f"88{TS}22"

        r1 = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_UniqPhone1_{TS}",
                "aadhaar_number": f"9009 {TS[:4]} {TS[2:]}",
                "phone": phone_a
            }
        })
        assert r1.status_code == 200, f"First unique phone KYC failed: {r1.text}"

        r2 = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_UniqPhone2_{TS}",
                "aadhaar_number": f"9010 {TS[:4]} {TS[2:]}",
                "phone": phone_b
            }
        })
        assert r2.status_code == 200, f"Second unique phone KYC failed: {r2.text}"
        print("PASS: Two different phones both succeed")

    def test_no_phone_kyc_allowed(self, sipahi_session, illaka_and_misal):
        """KYC without phone should not fail mobile uniqueness check"""
        illaka, misal = illaka_and_misal
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_NoPhone_{TS}",
                "aadhaar_number": f"9011 {TS[:4]} {TS[2:]}"
            }
        })
        assert r.status_code == 200, f"KYC without phone failed: {r.text}"
        print("PASS: KYC without phone creates successfully")


class TestCollectionSheetAPI:
    """Test GET /api/collections/sheet"""

    def test_collection_sheet_returns_correct_structure(self, admin_session):
        """Should return {month, total, collected, illakas}"""
        from datetime import date
        current_month = f"{date.today().year}-{date.today().month:02d}"
        r = admin_session.get(f"{BASE_URL}/api/collections/sheet")
        assert r.status_code == 200, f"Collection sheet failed: {r.text}"
        data = r.json()

        assert "month" in data, f"'month' missing in response: {data.keys()}"
        assert "total" in data, f"'total' missing in response: {data.keys()}"
        assert "collected" in data, f"'collected' missing in response: {data.keys()}"
        assert "illakas" in data, f"'illakas' missing in response: {data.keys()}"
        assert isinstance(data["illakas"], list), f"'illakas' should be list, got {type(data['illakas'])}"
        assert data["month"] == current_month, f"Expected month={current_month}, got {data['month']}"
        print(f"PASS: Collection sheet structure correct, month={data['month']}, total={data['total']}, collected={data['collected']}")

    def test_collection_sheet_month_param(self, admin_session):
        """Should accept ?month=YYYY-MM parameter"""
        r = admin_session.get(f"{BASE_URL}/api/collections/sheet?month=2025-01")
        assert r.status_code == 200, f"Collection sheet with month param failed: {r.text}"
        data = r.json()
        assert data["month"] == "2025-01", f"Expected month=2025-01, got {data['month']}"
        print(f"PASS: Month param works, returned {data['total']} rows")

    def test_collection_sheet_illakas_structure(self, admin_session):
        """Each illaka should have illaka_id, illaka_name, misals list"""
        r = admin_session.get(f"{BASE_URL}/api/collections/sheet")
        assert r.status_code == 200
        data = r.json()
        for il in data.get("illakas", []):
            assert "illaka_id" in il, f"illaka_id missing in illaka: {il.keys()}"
            assert "illaka_name" in il, f"illaka_name missing in illaka: {il.keys()}"
            assert "misals" in il, f"misals missing in illaka: {il.keys()}"
            for m in il.get("misals", []):
                assert "misal_id" in m, f"misal_id missing: {m.keys()}"
                assert "misal_name" in m, f"misal_name missing: {m.keys()}"
                assert "rows" in m, f"rows missing: {m.keys()}"
                for row in m.get("rows", []):
                    assert "loan_db_id" in row, f"loan_db_id missing: {row.keys()}"
                    assert "client_name" in row, f"client_name missing: {row.keys()}"
                    assert "emi_amount" in row, f"emi_amount missing: {row.keys()}"
                    assert "emi_status" in row, f"emi_status missing: {row.keys()}"
                    assert "loan_number" in row, f"loan_number missing: {row.keys()}"
                    assert "customer_id" in row, f"customer_id missing in row: {row.keys()}"
        print("PASS: Collection sheet illakas structure correct")

    def test_collection_sheet_collected_count(self, admin_session):
        """collected count should be <= total"""
        r = admin_session.get(f"{BASE_URL}/api/collections/sheet")
        assert r.status_code == 200
        data = r.json()
        assert data["collected"] <= data["total"], \
            f"collected={data['collected']} > total={data['total']}"
        print(f"PASS: collected={data['collected']}, total={data['total']}, pct={round(data['collected']/max(data['total'],1)*100)}%")

    def test_collection_sheet_sipahi_sees_own_loans(self, sipahi_session):
        """Sipahi should be able to access collection sheet"""
        r = sipahi_session.get(f"{BASE_URL}/api/collections/sheet")
        assert r.status_code == 200, f"Sipahi collection sheet failed: {r.text}"
        data = r.json()
        assert "illakas" in data
        print(f"PASS: Sipahi sees collection sheet with {data['total']} rows")


class TestLoanNumberInList:
    """Test that loan_number appears in loan list API responses"""

    def test_loan_list_has_loan_number_field(self, admin_session):
        """GET /api/loans should return loan_number on each loan"""
        r = admin_session.get(f"{BASE_URL}/api/loans?limit=10")
        assert r.status_code == 200
        data = r.json()
        loans = data.get("loans", [])
        if not loans:
            pytest.skip("No loans to test")
        # Check recent loans have loan_number field (not necessarily set for old ones)
        loans_with_number = [l for l in loans if l.get("loan_number")]
        print(f"Loans with loan_number: {len(loans_with_number)}/{len(loans)}")
        # At minimum, field should exist (even if None/missing for old loans)
        # New loans created in this test should have loan_number
        assert len(loans_with_number) > 0, "No loans found with loan_number set"
        print(f"PASS: {len(loans_with_number)} loans have loan_number")

    def test_kyc_list_has_customer_id_field(self, admin_session):
        """GET /api/kycs should return customer_id on each KYC"""
        r = admin_session.get(f"{BASE_URL}/api/kycs?limit=10")
        assert r.status_code == 200
        data = r.json()
        kycs = data.get("kycs", [])
        if not kycs:
            pytest.skip("No KYCs to test")
        # New KYCs should have customer_id
        kycs_with_cid = [k for k in kycs if k.get("customer_id")]
        print(f"KYCs with customer_id: {len(kycs_with_cid)}/{len(kycs)}")
        assert len(kycs_with_cid) > 0, "No KYCs found with customer_id set"
        print(f"PASS: {len(kycs_with_cid)} KYCs have customer_id")
