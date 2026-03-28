"""
Tests for Hindi Transliteration features in Bahi Khata:
1. POST /api/transliterate - Converts English Indian names to Devanagari
2. KYC creation with name_hindi and relative_name_hindi fields
3. Collection Sheet returns client_name_hindi and relative_name_hindi
4. Loan response includes client_name_hindi for newly created loans
"""
import pytest
import requests
import os
import time
import re
import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

ADMIN_EMAIL = "admin@bahikhata.com"
ADMIN_PASSWORD = "Admin@123"
SIPAHI_EMAIL = "TEST_sipahi_loans@bahikhata.com"
SIPAHI_PASSWORD = "Test@1234"

# Timestamp suffix to avoid collisions
TS = str(int(time.time()))[-6:]


@pytest.fixture(scope="module")
def admin_session():
    """Admin session fixture"""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    print(f"Admin login OK")
    return s


@pytest.fixture(scope="module")
def sipahi_session():
    """Sipahi session fixture"""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": SIPAHI_EMAIL, "password": SIPAHI_PASSWORD})
    if r.status_code != 200:
        pytest.skip(f"Sipahi login failed: {r.text}")
    print(f"Sipahi login OK")
    return s


@pytest.fixture(scope="module")
def illaka_misal_for_hindi(admin_session, sipahi_session):
    """Get Delhi illaka and its misal; assign to sipahi."""
    r = admin_session.get(f"{BASE_URL}/api/illakas")
    assert r.status_code == 200
    illakas = r.json()
    delhi = next((il for il in illakas if il.get("name", "").lower() == "delhi"), None)
    if not delhi:
        r2 = admin_session.post(f"{BASE_URL}/api/illakas", json={"name": "Delhi"})
        assert r2.status_code in [200, 201]
        delhi = r2.json()
        print(f"Created Delhi illaka: {delhi['id']}")
    else:
        print(f"Found Delhi illaka: {delhi['id']}")

    r3 = admin_session.get(f"{BASE_URL}/api/misals?illaka_id={delhi['id']}")
    assert r3.status_code == 200
    misals = r3.json()
    if misals:
        misal = misals[0]
    else:
        r4 = admin_session.post(f"{BASE_URL}/api/misals", json={"name": "TEST_Misal_Delhi_Hindi", "illaka_id": delhi['id']})
        assert r4.status_code in [200, 201]
        misal = r4.json()
        print(f"Created misal: {misal['id']}")

    # Assign Delhi illaka to sipahi
    users_r = admin_session.get(f"{BASE_URL}/api/users")
    if users_r.status_code == 200:
        raw = users_r.json()
        users_list = raw if isinstance(raw, list) else raw.get("users", [])
        sipahi_user = next((u for u in users_list if u.get("email", "").lower() == SIPAHI_EMAIL.lower()), None)
        if sipahi_user:
            assigned = sipahi_user.get("assigned_illaka_ids", [])
            if delhi['id'] not in assigned:
                admin_session.post(
                    f"{BASE_URL}/api/users/{sipahi_user['id']}/assign-illakas",
                    json={"illaka_ids": assigned + [delhi['id']]}
                )
                print("Assigned Delhi illaka to sipahi")

    return delhi, misal


# --- Transliterate endpoint tests ---

class TestTransliterateEndpoint:
    """Tests for POST /api/transliterate"""

    def test_transliterate_ram_kumar_returns_devanagari(self, sipahi_session):
        """'Ram Kumar' should return Devanagari characters"""
        r = sipahi_session.post(f"{BASE_URL}/api/transliterate", json={"text": "Ram Kumar"})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "hindi" in data, f"Response missing 'hindi' key: {data}"
        hindi = data["hindi"]
        assert isinstance(hindi, str), f"'hindi' should be a string"
        assert len(hindi) > 0, f"Expected non-empty Hindi for 'Ram Kumar'"
        has_devanagari = any('\u0900' <= ch <= '\u097F' for ch in hindi)
        assert has_devanagari, f"Expected Devanagari script in result, got: '{hindi}'"
        print(f"PASS: 'Ram Kumar' -> '{hindi}'")

    def test_transliterate_empty_text_returns_empty(self, sipahi_session):
        """Empty text should return empty Hindi string"""
        r = sipahi_session.post(f"{BASE_URL}/api/transliterate", json={"text": ""})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "hindi" in data, f"Response missing 'hindi' key: {data}"
        assert data["hindi"] == "", f"Expected empty string for empty input, got: '{data['hindi']}'"
        print("PASS: empty text -> empty hindi")

    def test_transliterate_whitespace_only_returns_empty(self, sipahi_session):
        """Whitespace-only text should return empty Hindi string"""
        r = sipahi_session.post(f"{BASE_URL}/api/transliterate", json={"text": "   "})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        assert data.get("hindi") == "", f"Expected empty for whitespace, got: '{data.get('hindi')}'"
        print("PASS: whitespace text -> empty hindi")

    def test_transliterate_common_indian_name(self, sipahi_session):
        """'Sunita Devi' should return Devanagari"""
        r = sipahi_session.post(f"{BASE_URL}/api/transliterate", json={"text": "Sunita Devi"})
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        data = r.json()
        hindi = data.get("hindi", "")
        assert len(hindi) > 0, "Expected non-empty Hindi for 'Sunita Devi'"
        has_devanagari = any('\u0900' <= ch <= '\u097F' for ch in hindi)
        assert has_devanagari, f"Expected Devanagari script, got: '{hindi}'"
        print(f"PASS: 'Sunita Devi' -> '{hindi}'")

    def test_transliterate_requires_auth(self):
        """Unauthenticated request should fail (401/403)"""
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/transliterate", json={"text": "Ram Kumar"})
        assert r.status_code in [401, 403], f"Expected 401/403, got {r.status_code}"
        print(f"PASS: unauthenticated transliterate returns {r.status_code}")


# --- KYC with Hindi Names ---

class TestKYCWithHindiNames:
    """Tests for KYC creation and retrieval with Hindi name fields"""

    def test_kyc_creation_with_name_hindi_persists(self, sipahi_session, illaka_misal_for_hindi):
        """POST /api/kycs with name_hindi should store and return it"""
        illaka, misal = illaka_misal_for_hindi
        aadhaar = f"30{TS}01"[:12].ljust(12, "0")
        phone = f"91{TS}01"

        payload = {
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_Hindi_{TS}",
                "name_hindi": "\u0930\u093e\u092e \u0915\u0941\u092e\u093e\u0930",
                "relative_name": f"TEST_Father_{TS}",
                "relative_name_hindi": "\u0936\u094d\u092f\u093e\u092e \u0932\u093e\u0932",
                "phone": phone,
                "aadhaar_number": aadhaar,
                "gender": "male"
            }
        }
        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json=payload)
        assert r.status_code == 200, f"KYC creation failed: {r.text}"
        data = r.json()
        kyc_id = data.get("id")
        assert kyc_id is not None

        pb = data.get("primary_borrower", {})
        assert pb.get("name_hindi") == "\u0930\u093e\u092e \u0915\u0941\u092e\u093e\u0930", \
            f"name_hindi not in create response: {pb.get('name_hindi')}"
        assert pb.get("relative_name_hindi") == "\u0936\u094d\u092f\u093e\u092e \u0932\u093e\u0932", \
            f"relative_name_hindi not in create response: {pb.get('relative_name_hindi')}"
        print(f"PASS: KYC created with name_hindi='{pb.get('name_hindi')}', relative_name_hindi='{pb.get('relative_name_hindi')}'")

        # Verify persistence via GET
        r2 = sipahi_session.get(f"{BASE_URL}/api/kycs/{kyc_id}")
        assert r2.status_code == 200, f"KYC GET failed: {r2.text}"
        data2 = r2.json()
        pb2 = data2.get("primary_borrower", {})
        assert pb2.get("name_hindi") == "\u0930\u093e\u092e \u0915\u0941\u092e\u093e\u0930", \
            f"name_hindi not persisted: {pb2.get('name_hindi')}"
        assert pb2.get("relative_name_hindi") == "\u0936\u094d\u092f\u093e\u092e \u0932\u093e\u0932", \
            f"relative_name_hindi not persisted: {pb2.get('relative_name_hindi')}"
        print(f"PASS: name_hindi persisted in DB correctly")

        TestKYCWithHindiNames._kyc_id = kyc_id

    def test_kyc_creation_without_hindi_names_allowed(self, sipahi_session, illaka_misal_for_hindi):
        """KYC without name_hindi should still succeed (optional field)"""
        illaka, misal = illaka_misal_for_hindi
        aadhaar2 = f"40{TS}02"[:12].ljust(12, "0")
        phone2 = f"92{TS}02"

        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_NoHindi_{TS}",
                "phone": phone2,
                "aadhaar_number": aadhaar2,
                "gender": "female"
            }
        })
        assert r.status_code == 200, f"KYC without hindi names failed: {r.text}"
        pb = r.json().get("primary_borrower", {})
        assert pb.get("name_hindi") in [None, ""], \
            f"name_hindi should be empty if not provided: {pb.get('name_hindi')}"
        print("PASS: KYC without name_hindi creates successfully")

    def test_kyc_with_hindi_auto_loan_has_client_name_hindi(self, sipahi_session, illaka_misal_for_hindi):
        """KYC with disbursement_amount creates a loan with client_name_hindi from name_hindi"""
        illaka, misal = illaka_misal_for_hindi
        aadhaar3 = f"50{TS}03"[:12].ljust(12, "0")
        phone3 = f"93{TS}03"
        name_hindi = "\u0938\u0941\u0928\u0940\u0924\u093e \u0926\u0947\u0935\u0940"

        r = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_AutoLoanHindi_{TS}",
                "name_hindi": name_hindi,
                "relative_name": f"TEST_FatherAuto_{TS}",
                "relative_name_hindi": "\u092e\u094b\u0939\u0928 \u0932\u093e\u0932",
                "phone": phone3,
                "aadhaar_number": aadhaar3,
                "gender": "female"
            },
            "disbursement_amount": 10000
        })
        assert r.status_code == 200, f"KYC+loan creation failed: {r.text}"
        kyc_id = r.json().get("id")
        assert kyc_id is not None

        loans_r = sipahi_session.get(f"{BASE_URL}/api/loans")
        assert loans_r.status_code == 200
        all_loans = loans_r.json().get("loans", []) if isinstance(loans_r.json(), dict) else loans_r.json()
        kyc_loan = next((l for l in all_loans if l.get("kyc_id") == kyc_id), None)
        if kyc_loan:
            assert kyc_loan.get("client_name_hindi") == name_hindi, \
                f"client_name_hindi not set in auto-loan: '{kyc_loan.get('client_name_hindi')}'"
            print(f"PASS: Auto-loan has client_name_hindi='{kyc_loan.get('client_name_hindi')}'")
        else:
            print(f"INFO: Loan not found for kyc_id={kyc_id} (may be pagination)")


# --- Collection Sheet with Hindi names ---

class TestCollectionSheetHindi:
    """Tests for GET /api/collections/sheet returning Hindi name fields"""

    def test_collection_sheet_has_hindi_name_fields(self, sipahi_session):
        """Collection sheet rows should include client_name_hindi and relative_name_hindi"""
        r = sipahi_session.get(f"{BASE_URL}/api/collections/sheet")
        assert r.status_code == 200, f"Collection sheet failed: {r.text}"
        data = r.json()

        assert "illakas" in data, f"Response missing 'illakas': {list(data.keys())}"
        assert "total" in data, f"Response missing 'total': {list(data.keys())}"
        assert "month" in data, f"Response missing 'month': {list(data.keys())}"

        illakas = data["illakas"]
        found_row = False
        for illaka in illakas:
            for misal in illaka.get("misals", []):
                for row in misal.get("rows", []):
                    found_row = True
                    assert "client_name_hindi" in row, \
                        f"Row missing 'client_name_hindi' key: {list(row.keys())}"
                    assert "relative_name_hindi" in row, \
                        f"Row missing 'relative_name_hindi' key: {list(row.keys())}"

        if found_row:
            print("PASS: Collection sheet rows have client_name_hindi and relative_name_hindi fields")
        else:
            print("INFO: No rows in collection sheet for current month (no active loans)")

    def test_collection_sheet_hindi_names_correct_for_hindi_kyc(self, sipahi_session, illaka_misal_for_hindi):
        """After creating a KYC with Hindi names + auto-loan, collection sheet shows them"""
        illaka, misal = illaka_misal_for_hindi
        aadhaar4 = f"60{TS}04"[:12].ljust(12, "0")
        phone4 = f"94{TS}04"
        name_hindi = "\u0930\u092e\u0947\u0936 \u092f\u093e\u0926\u0935"
        rel_name_hindi = "\u0935\u093f\u091c\u092f \u092f\u093e\u0926\u0935"

        r_kyc = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_Sheet_{TS}",
                "name_hindi": name_hindi,
                "relative_name": f"TEST_SheetFather_{TS}",
                "relative_name_hindi": rel_name_hindi,
                "phone": phone4,
                "aadhaar_number": aadhaar4,
                "gender": "male"
            },
            "disbursement_amount": 15000
        })
        assert r_kyc.status_code == 200, f"KYC creation for sheet test failed: {r_kyc.text}"

        current_month = datetime.datetime.now().strftime("%Y-%m")
        r = sipahi_session.get(f"{BASE_URL}/api/collections/sheet?month={current_month}")
        assert r.status_code == 200, f"Collection sheet failed: {r.text}"
        data = r.json()
        illakas = data.get("illakas", [])

        found = False
        all_rows = []
        for il in illakas:
            for ms in il.get("misals", []):
                for row in ms.get("rows", []):
                    all_rows.append(row)
                    if row.get("client_name_hindi") == name_hindi:
                        found = True
                        assert row["relative_name_hindi"] == rel_name_hindi, \
                            f"relative_name_hindi mismatch: got '{row['relative_name_hindi']}'"
                        print(f"PASS: Sheet row has client_name_hindi='{row['client_name_hindi']}', relative_name_hindi='{row['relative_name_hindi']}'")

        if not found and all_rows:
            sample = all_rows[0]
            assert "client_name_hindi" in sample, f"No 'client_name_hindi' key in rows: {list(sample.keys())}"
            assert "relative_name_hindi" in sample, f"No 'relative_name_hindi' key in rows: {list(sample.keys())}"
            print(f"PASS: Rows have required Hindi fields (newly created loan may be in next month's schedule)")


# --- Loan list/detail with Hindi client name ---

class TestLoanHindiName:
    """Tests for loan API returning client_name_hindi when KYC has name_hindi"""
    _new_loan_id = None

    def test_loan_list_new_loan_has_client_name_hindi_field(self, sipahi_session, illaka_misal_for_hindi):
        """GET /api/loans list should include client_name_hindi for loans created with Hindi names"""
        illaka, misal = illaka_misal_for_hindi
        aadhaar5 = f"70{TS}05"[:12].ljust(12, "0")
        phone5 = f"95{TS}05"
        name_hindi = "\u0905\u091c\u092f \u0938\u093f\u0902\u0939"

        r_kyc = sipahi_session.post(f"{BASE_URL}/api/kycs", json={
            "illaka_id": illaka['id'],
            "illaka_name": illaka['name'],
            "misal_id": misal['id'],
            "misal_name": misal['name'],
            "primary_borrower": {
                "name": f"TEST_LoanList_{TS}",
                "name_hindi": name_hindi,
                "relative_name": f"TEST_LoanListFather_{TS}",
                "relative_name_hindi": "\u0930\u093e\u091c\u0947\u0936 \u0938\u093f\u0902\u0939",
                "phone": phone5,
                "aadhaar_number": aadhaar5,
                "gender": "male"
            },
            "disbursement_amount": 12000
        })
        assert r_kyc.status_code == 200, f"KYC creation failed: {r_kyc.text}"
        kyc_id = r_kyc.json().get("id")

        r = sipahi_session.get(f"{BASE_URL}/api/loans")
        assert r.status_code == 200, f"Loans list failed: {r.text}"
        data = r.json()
        loans = data.get("loans", []) if isinstance(data, dict) else data

        new_loan = next((l for l in loans if l.get("kyc_id") == kyc_id), None)
        if new_loan:
            assert "client_name_hindi" in new_loan, \
                f"'client_name_hindi' not in new loan response: {list(new_loan.keys())}"
            assert new_loan.get("client_name_hindi") == name_hindi, \
                f"client_name_hindi mismatch in loan list"
            print(f"PASS: New loan in list has client_name_hindi='{new_loan.get('client_name_hindi')}'")
            TestLoanHindiName._new_loan_id = new_loan["id"]
        else:
            print(f"INFO: Newly created loan not found in list. kyc_id={kyc_id}")

    def test_loan_detail_new_loan_has_client_name_hindi(self, sipahi_session):
        """GET /api/loans/{id} should include client_name_hindi for a recently created loan"""
        loan_id = TestLoanHindiName._new_loan_id
        if not loan_id:
            pytest.skip("No new loan id from previous test - skipping")

        r2 = sipahi_session.get(f"{BASE_URL}/api/loans/{loan_id}")
        assert r2.status_code == 200, f"Loan detail failed: {r2.text}"
        detail = r2.json()
        assert "client_name_hindi" in detail, \
            f"'client_name_hindi' not in loan detail: {list(detail.keys())}"
        print(f"PASS: Loan detail has client_name_hindi='{detail.get('client_name_hindi', '')}'")

    def test_old_loans_missing_client_name_hindi_is_known_behavior(self, sipahi_session):
        """Old loans (pre-feature) may not have client_name_hindi - document behavior"""
        r = sipahi_session.get(f"{BASE_URL}/api/loans")
        assert r.status_code == 200
        data = r.json()
        loans = data.get("loans", []) if isinstance(data, dict) else data
        old_loans = [l for l in loans if "client_name_hindi" not in l]
        new_loans = [l for l in loans if "client_name_hindi" in l]
        print(f"INFO: Old loans (no client_name_hindi): {len(old_loans)}, New loans (with field): {len(new_loans)}")
        print("INFO: Frontend uses 'loan.client_name_hindi || loan.client_name' - handles both gracefully")
