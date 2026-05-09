"""
CRIF High Mark INDV 2.0 Integration
UAT endpoint for credit bureau checks
"""
import os
import re
import uuid
import logging
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId

from core.database import db
from core.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crif", tags=["crif"])

# ── Config ─────────────────────────────────────────────────────────────────────
_CRIF_ENV = os.environ.get("CRIF_ENV", "UAT").upper()   # UAT or PROD

# UAT
_UAT_URL      = os.environ.get("CRIF_URL")
_UAT_USER_ID  = os.environ.get("CRIF_USER_ID")
_UAT_PASSWORD = os.environ.get("CRIF_PASSWORD")
_UAT_MBRID    = os.environ.get("CRIF_MBRID")

# PROD
_PROD_URL      = os.environ.get("CRIF_PROD_URL")
_PROD_USER_ID  = os.environ.get("CRIF_PROD_USER_ID")
_PROD_PASSWORD = os.environ.get("CRIF_PROD_PASSWORD")
_PROD_MBRID    = os.environ.get("CRIF_PROD_MBRID")

CRIF_SUB_MBR_ID = os.environ.get("CRIF_SUB_MBR_ID", "RADHYA MICRO FINANCE PRIVATE LIMITED")

def _active_config():
    """Return (url, user_id, password, mbrid, env_label) for the active environment."""
    if _CRIF_ENV == "PROD":
        return _PROD_URL, _PROD_USER_ID, _PROD_PASSWORD, _PROD_MBRID, "PROD"
    return _UAT_URL, _UAT_USER_ID, _UAT_PASSWORD, _UAT_MBRID, "UAT"

# Indian state name → 2-letter code mapping
STATE_MAP = {
    "andhra pradesh": "AP", "arunachal pradesh": "AR", "assam": "AS", "bihar": "BR",
    "chhattisgarh": "CG", "goa": "GA", "gujarat": "GJ", "haryana": "HR",
    "himachal pradesh": "HP", "jharkhand": "JH", "karnataka": "KA", "kerala": "KL",
    "madhya pradesh": "MP", "maharashtra": "MH", "manipur": "MN", "meghalaya": "ML",
    "mizoram": "MZ", "nagaland": "NL", "odisha": "OD", "punjab": "PB",
    "rajasthan": "RJ", "sikkim": "SK", "tamil nadu": "TN", "telangana": "TS",
    "tripura": "TR", "uttar pradesh": "UP", "uttarakhand": "UK", "west bengal": "WB",
    "delhi": "DL", "jammu and kashmir": "JK", "ladakh": "LA",
    "andaman and nicobar": "AN", "chandigarh": "CH", "dadra": "DD",
    "daman and diu": "DD", "lakshadweep": "LD", "pondicherry": "PY", "puducherry": "PY",
}

# ID type codes
ID_TYPES = {
    "aadhaar": "ID08",
    "pan": "ID07",
    "voter_id": "ID02",
    "driving_license": "ID03",
    "passport": "ID01",
    "ration_card": "ID04",
}


def _extract_pin(address: str) -> str:
    """Extract 6-digit PIN code from address string."""
    if not address:
        return ""
    pins = re.findall(r'\b[1-9]\d{5}\b', address)
    return pins[-1] if pins else ""


def _extract_state(address: str) -> str:
    """Try to detect state code from address text."""
    if not address:
        return ""
    lower = address.lower()
    for name, code in STATE_MAP.items():
        if name in lower:
            return code
    return ""


def _build_crif_xml(kyc: dict, loan_amount: int = 50000, mbrid: str = "", env: str = "UAT") -> str:
    """Build CRIF INDV 2.0 request XML from KYC document."""
    now = datetime.now()
    inq_dt = now.strftime("%d-%m-%Y %H:%M:%S")
    unique_ref = f"BK{kyc.get('customer_id', 'XX')}{now.strftime('%m%d%H%M%S')}"[:20]

    pb = kyc.get("primary_borrower", {})
    name = (pb.get("name") or "").upper().strip()
    dob = pb.get("dob") or ""
    # DOB format normalization: accept YYYY-MM-DD or DD/MM/YYYY → output DD-MM-YYYY
    if dob and len(dob) == 10:
        if "-" in dob:
            parts = dob.split("-")
            if len(parts[0]) == 4:  # YYYY-MM-DD
                dob = f"{parts[2]}-{parts[1]}-{parts[0]}"
        elif "/" in dob:
            parts = dob.split("/")
            if len(parts[2]) == 4:  # DD/MM/YYYY
                dob = f"{parts[0]}-{parts[1]}-{parts[2]}"

    phone = (pb.get("phone") or "").strip().replace("+91", "").replace(" ", "")[-10:]
    address = (pb.get("address") or "").strip()
    aadhaar = (pb.get("aadhaar_number") or "").replace(" ", "").strip()

    pin = _extract_pin(address)
    state = _extract_state(address)

    # Use misal_name as city fallback (MFI clients are in villages)
    city = kyc.get("misal_name") or kyc.get("illaka_name") or ""
    city = city.upper().strip()[:30]

    # Build IDs segment
    if aadhaar and len(aadhaar) >= 8:
        ids_xml = f"<ID><TYPE>ID08</TYPE><VALUE>{aadhaar[:12]}</VALUE></ID>"
    else:
        ids_xml = "<ID><TYPE>ID08</TYPE><VALUE></VALUE></ID>"

    # Illaka/Misal as kendra/branch IDs
    illaka_id = str(kyc.get("illaka_id") or "001")[:8]
    misal_id = str(kyc.get("misal_id") or "001")[:8]
    loan_id = str(kyc.get("loan_id") or kyc.get("customer_id") or "BK001")[:20]

    xml = (
        f"<REQUEST-REQUEST-FILE>"
        f"<HEADER-SEGMENT>"
        f"<SUB-MBR-ID>{CRIF_SUB_MBR_ID}</SUB-MBR-ID>"
        f"<INQ-DT-TM>{inq_dt}</INQ-DT-TM>"
        f"<REQ-VOL-TYP>C01</REQ-VOL-TYP>"
        f"<REQ-ACTN-TYP>SUBMIT</REQ-ACTN-TYP>"
        f"<TEST-FLG>{'HMTEST' if env == 'UAT' else 'N'}</TEST-FLG>"
        f"<AUTH-FLG>Y</AUTH-FLG>"
        f"<AUTH-TITLE>USER</AUTH-TITLE>"
        f"<RES-FRMT>XML/HTML</RES-FRMT>"
        f"<MEMBER-PRE-OVERRIDE>N</MEMBER-PRE-OVERRIDE>"
        f"<RES-FRMT-EMBD>Y</RES-FRMT-EMBD>"
        f"<LOS-NAME>BahiKhata</LOS-NAME>"
        f"<LOS-VENDER>Emergent</LOS-VENDER>"
        f"<LOS-VERSION>1.0</LOS-VERSION>"
        f"<REQ-SERVICE-TYPE>PAN|DL|VOTERID</REQ-SERVICE-TYPE>"
        f"<MFI><INDV>true</INDV><SCORE>true</SCORE><GROUP>true</GROUP></MFI>"
        f"<CONSUMER><INDV>true</INDV><SCORE>true</SCORE></CONSUMER>"
        f"<IOI>true</IOI>"
        f"</HEADER-SEGMENT>"
        f"<INQUIRY>"
        f"<APPLICANT-SEGMENT>"
        f"<APPLICANT-NAME><NAME1>{name}</NAME1><NAME2></NAME2><NAME3></NAME3></APPLICANT-NAME>"
        f"<DOB><DOB-DATE>{dob}</DOB-DATE><AGE></AGE><AGE-AS-ON></AGE-AS-ON></DOB>"
        f"<IDS>{ids_xml}</IDS>"
        f"<RELATIONS><RELATION><TYPE></TYPE><NAME></NAME></RELATION></RELATIONS>"
        f"<KEY-PERSON><TYPE></TYPE><NAME></NAME></KEY-PERSON>"
        f"<NOMINEE><TYPE></TYPE><NAME></NAME></NOMINEE>"
        f"<PHONES><PHONE><TELE-NO-TYPE>P01</TELE-NO-TYPE><TELE-NO>{phone}</TELE-NO></PHONE></PHONES>"
        f"<INCOME>0</INCOME>"
        f"<EMPLOYMENT-TYPE>ET01</EMPLOYMENT-TYPE>"
        f"<EMPLOYER-NAME></EMPLOYER-NAME>"
        f"</APPLICANT-SEGMENT>"
        f"<ADDRESS-SEGMENT>"
        f"<ADDRESS><TYPE>D01</TYPE>"
        f"<ADDRESS-1>{address[:80]}</ADDRESS-1>"
        f"<CITY>{city}</CITY>"
        f"<STATE>{state}</STATE>"
        f"<PIN>{pin}</PIN>"
        f"</ADDRESS>"
        f"</ADDRESS-SEGMENT>"
        f"<EMAIL></EMAIL>"
        f"<APPLICATION-SEGMENT>"
        f"<INQUIRY-UNIQUE-REF-NO>{unique_ref}</INQUIRY-UNIQUE-REF-NO>"
        f"<CREDT-RPT-ID>001</CREDT-RPT-ID>"
        f"<CREDT-REQ-TYP>INDV</CREDT-REQ-TYP>"
        f"<CREDT-RPT-TRN-ID>001</CREDT-RPT-TRN-ID>"
        f"<CREDT-INQ-PURPS-TYP>ACCT-ORIG</CREDT-INQ-PURPS-TYP>"
        f"<CREDT-INQ-PURPS-TYP-DESC>Housing Loan</CREDT-INQ-PURPS-TYP-DESC>"
        f"<CREDIT-INQUIRY-STAGE>PRE-DISB</CREDIT-INQUIRY-STAGE>"
        f"<CREDT-RPT-TRN-DT-TM>{inq_dt}</CREDT-RPT-TRN-DT-TM>"
        f"<MBR-ID>{mbrid}</MBR-ID>"
        f"<KENDRA-ID>{illaka_id}</KENDRA-ID>"
        f"<BRANCH-ID>{misal_id}</BRANCH-ID>"
        f"<LOS-APP-ID>{loan_id}</LOS-APP-ID>"
        f"<LOAN-AMOUNT>{loan_amount}</LOAN-AMOUNT>"
        f"</APPLICATION-SEGMENT>"
        f"</INQUIRY>"
        f"</REQUEST-REQUEST-FILE>"
    )
    return xml


def _get_text(elem, tag: str, default="") -> str:
    """Safe text extraction from XML element."""
    node = elem.find(tag)
    if node is None:
        return default
    return (node.text or "").strip() or default


def _parse_crif_response(xml_text: str) -> dict:
    """Parse CRIF XML response into structured dict — handles both UAT and PROD formats."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        # Truncated XML (commonly inside <PRINTABLE-REPORT> CDATA): drop the report
        # section and retry. Loan/score data lives BEFORE the printable report.
        cleaned = xml_text
        idx = cleaned.find("<PRINTABLE-REPORT")
        if idx > 0:
            cleaned = cleaned[:idx] + "</INDV-REPORT></INDV-REPORTS></INDV-REPORT-FILE>"
        try:
            root = ET.fromstring(cleaned)
        except ET.ParseError:
            # Last resort: aggressive CDATA strip
            import re as _re
            cleaned2 = _re.sub(r'<!\[CDATA\[[^\]]*$', '', xml_text, flags=_re.DOTALL)
            try:
                root = ET.fromstring(cleaned2 + "</INDV-REPORT></INDV-REPORTS></INDV-REPORT-FILE>")
            except ET.ParseError:
                return {"error": f"XML parse error: {e}", "raw_xml": xml_text[:2000]}

    # Handle error response
    inquiry_status = root.find(".//INQUIRY-STATUS")
    if inquiry_status is not None:
        errors = [{"code": _get_text(e, "CODE"), "description": _get_text(e, "DESCRIPTION")}
                  for e in inquiry_status.findall(".//ERROR")]
        return {"status": "error", "errors": errors,
                "response_type": _get_text(root, ".//RESPONSE-TYPE", "ERROR")}

    report = root.find(".//INDV-REPORT")
    if report is None:
        return {"status": "no_report", "raw_xml": xml_text[:500]}

    # Header
    header = report.find("HEADER") or ET.Element("HEADER")
    result = {
        "status": "success",
        "report_id": _get_text(header, "REPORT-ID"),
        "batch_id": _get_text(header, "BATCH-ID"),
        "date_of_issue": _get_text(header, "DATE-OF-ISSUE"),
        "date_of_request": _get_text(header, "DATE-OF-REQUEST"),
        "prepared_for": _get_text(header, "PREPARED-FOR"),
    }

    # Service statuses
    statuses = {}
    for s in report.findall(".//STATUS-DETAILS/STATUS"):
        option = _get_text(s, "OPTION")
        if option:
            statuses[option] = _get_text(s, "OPTION-STATUS")
    result["service_statuses"] = statuses

    # Scores — works for both UAT and PROD
    scores = []
    for score in report.findall(".//SCORES/SCORE"):
        name  = _get_text(score, "NAME") or _get_text(score, "SCORE-TYPE")
        value = _get_text(score, "VALUE") or _get_text(score, "SCORE-VALUE")
        desc  = _get_text(score, "DESCRIPTION") or _get_text(score, "SCORE-COMMENTS") or _get_text(score, "SCORE-FACTORS")
        if name:
            scores.append({"name": name, "value": value, "description": desc})
    result["scores"] = scores

    # Account summary (DERIVED-ATTRIBUTES — same in both UAT & PROD)
    acc_summary = report.find(".//ACCOUNTS-SUMMARY")
    if acc_summary is not None:
        derived  = acc_summary.find("DERIVED-ATTRIBUTES") or ET.Element("X")
        mfi_summ = acc_summary.find("MFI-SUMMARY")        or ET.Element("X")
        cns_summ = acc_summary.find("CNS-SUMMARY")        or ET.Element("X")
        cns_data = cns_summ.find("CNS-ACCOUNT-DETAILS")   or ET.Element("X")
        result["account_summary"] = {
            "inquiries_last_6m":      _get_text(derived, "INQUIRIES-IN-LAST-SIX-MONTHS", "0"),
            "credit_history_months":  _get_text(derived, "LENGTH-OF-CREDIT-HISTORY-MONTH", "0"),
            "credit_history_years":   _get_text(derived, "LENGTH-OF-CREDIT-HISTORY-YEAR", "0"),
            "new_accounts_6m":        _get_text(derived, "NEW-ACCOUNTS-IN-LAST-SIX-MONTHS", "0"),
            "delinquent_accounts_6m": _get_text(derived, "NEW-DELINQ-ACCOUNT-IN-LAST-SIX-MONTHS", "0"),
            "mfi_total_accounts":     _get_text(mfi_summ, "TOTAL-NO-OF-ACCOUNTS"),
            "mfi_active_accounts":    _get_text(mfi_summ, "NO-OF-ACTIVE-ACCOUNTS"),
            "mfi_disbursed_amount":   _get_text(mfi_summ, "TOTAL-DISBURSED-AMOUNT"),
            "mfi_current_balance":    _get_text(mfi_summ, "CURRENT-BALANCE"),
            "mfi_overdue_amount":     _get_text(mfi_summ, "OVERDUE-AMOUNT"),
            "cns_total_accounts":     _get_text(cns_data, "TOTAL-NO-OF-ACCOUNTS"),
            "cns_active_accounts":    _get_text(cns_data, "NO-OF-ACTIVE-ACCOUNTS"),
            "cns_disbursed_amount":   _get_text(cns_data, "TOTAL-DISBURSED-AMOUNT"),
            "cns_current_balance":    _get_text(cns_data, "CURRENT-BALANCE"),
            "cns_overdue_amount":     _get_text(cns_data, "OVERDUE-AMOUNT"),
            "cns_write_off_amount":   _get_text(cns_data, "TOTAL-WRITE-OFF-AMOUNT"),
        }

    # ── PROD format: <INDV-RESPONSE> / <LOAN-DETAIL> ──────────────────────────
    # Each INDV-RESPONSE = one MFI lender's record for this borrower
    prod_accounts = []
    for resp_node in report.findall(".//INDV-RESPONSE"):
        lender = _get_text(resp_node, "MFI")               # lender name
        branch = _get_text(resp_node, "BRANCH")
        kendra = _get_text(resp_node, "KENDRA")
        loan   = resp_node.find("LOAN-DETAIL")
        group  = resp_node.find("GROUP-DETAILS")
        if loan is not None:
            prod_accounts.append({
                "lender":         lender,
                "loan_type":      _get_text(loan, "ACCT-TYPE"),
                "frequency":      _get_text(loan, "FREQ"),
                "status":         _get_text(loan, "STATUS"),
                "acct_number":    _get_text(loan, "ACCT-NUMBER"),
                "disbursed":      _get_text(loan, "DISBURSED-AMT"),
                "current_balance": _get_text(loan, "CURRENT-BAL"),
                "overdue":        _get_text(loan, "OVERDUE-AMT"),
                "write_off":      _get_text(loan, "WRITE-OFF-AMT"),
                "installment":    _get_text(loan, "INSTALLMENT-AMT"),
                "term_months":    _get_text(loan, "ORIGINAL-TERM"),
                "fldg":           _get_text(loan, "FLDG"),
                "dispute":        _get_text(loan, "ACCT-IN-DISPUTE"),
                "info_as_on":     _get_text(loan, "INFO-AS-ON"),
                "loan_cycle":     _get_text(loan, "LOAN-CYCLE-ID"),
                "worst_delinq":   _get_text(loan, "WORST-DELEQUENCY-AMOUNT"),
                "date_disbursed": _get_text(loan, "DISBURSED-DT"),
                "date_closed":    _get_text(loan, "CLOSED-DT"),
                "last_payment":   _get_text(loan, "LAST-PAYMENT-DATE"),
                "dpd":            _get_text(loan, "DPD"),
                # Combined Payment History has DPD values per month — preferred for grid
                "payment_history": _get_text(loan, "COMBINED-PAYMENT-HISTORY") or _get_text(loan, "AMOUNT-PAID-HISTORY"),
                "branch":         branch,
                "kendra":         kendra,
                "group_tot_balance": _get_text(group, "TOT-CURRENT-BAL") if group is not None else "",
                "group_tot_disbursed": _get_text(group, "TOT-DISBURSED-AMT") if group is not None else "",
            })
    result["prod_accounts"] = prod_accounts

    # ── UAT / CONSUMER=true: <MFI-ACCOUNTS> / <CNS-ACCOUNTS> ─────────────────
    mfi_accounts = []
    for acct in report.findall(".//MFI-ACCOUNTS//INDV-ACCOUNT-DETAILS"):
        mfi_accounts.append({
            "lender":          _get_text(acct, "CREDIT-GRANTOR-NAME"),
            "loan_type":       _get_text(acct, "ACCT-TYPE"),
            "status":          _get_text(acct, "ACCT-STATUS"),
            "disbursed":       _get_text(acct, "DISBURSED-AMOUNT"),
            "current_balance": _get_text(acct, "CURRENT-BALANCE"),
            "overdue":         _get_text(acct, "OVERDUE-AMOUNT"),
            "date_opened":     _get_text(acct, "OPEN-DATE"),
            "date_closed":     _get_text(acct, "CLOSE-DATE"),
        })
    result["mfi_accounts"] = mfi_accounts

    cns_accounts = []
    for acct in report.findall(".//CNS-ACCOUNTS//INDV-ACCOUNT-DETAILS"):
        cns_accounts.append({
            "lender":          _get_text(acct, "CREDIT-GRANTOR-NAME"),
            "loan_type":       _get_text(acct, "ACCT-TYPE"),
            "status":          _get_text(acct, "ACCT-STATUS"),
            "disbursed":       _get_text(acct, "DISBURSED-AMOUNT"),
            "current_balance": _get_text(acct, "CURRENT-BALANCE"),
            "overdue":         _get_text(acct, "OVERDUE-AMOUNT"),
            "date_opened":     _get_text(acct, "OPEN-DATE"),
        })
    result["cns_accounts"] = cns_accounts

    # ── UAT IOI: <RESPONSES>/<RESPONSE>/<LOAN-DETAILS> ───────────────────────
    ioi_accounts = []
    for resp_node in report.findall(".//RESPONSES/RESPONSE"):
        loan = resp_node.find("LOAN-DETAILS")
        if loan is None:
            continue
        ioi_accounts.append({
            "lender":          _get_text(loan, "CREDIT-GUARANTOR"),
            "loan_type":       _get_text(loan, "ACCT-TYPE"),
            "status":          _get_text(loan, "ACCOUNT-STATUS"),
            "disbursed":       _get_text(loan, "DISBURSED-AMT"),
            "current_balance": _get_text(loan, "CURRENT-BAL"),
            "overdue":         _get_text(loan, "OVERDUE-AMT"),
            "write_off":       _get_text(loan, "WRITE-OFF-AMT"),
            "date_disbursed":  _get_text(loan, "DISBURSED-DATE"),
            "date_closed":     _get_text(loan, "CLOSED-DATE"),
            "last_payment":    _get_text(loan, "LAST-PAYMENT-DATE"),
            "installment":     _get_text(loan, "INSTALLMENT-AMT"),
            "interest_rate":   _get_text(loan, "INTEREST-RATE"),
            "term_months":     _get_text(loan, "ORIGINAL-TERM"),
            "payment_history": _get_text(loan, "COMBINED-PAYMENT-HISTORY"),
        })
    result["ioi_accounts"] = ioi_accounts

    # Primary account summary (IOI format)
    primary_summ = report.find(".//PRIMARY-ACCOUNTS-SUMMARY")
    if primary_summ is not None:
        result["primary_summary"] = {
            "total_accounts":    _get_text(primary_summ, "PRIMARY-NUMBER-OF-ACCOUNTS"),
            "active_accounts":   _get_text(primary_summ, "PRIMARY-ACTIVE-NUMBER-OF-ACCOUNTS"),
            "overdue_accounts":  _get_text(primary_summ, "PRIMARY-OVERDUE-NUMBER-OF-ACCOUNTS"),
            "current_balance":   _get_text(primary_summ, "PRIMARY-CURRENT-BALANCE"),
            "sanctioned_amount": _get_text(primary_summ, "PRIMARY-SANCTIONED-AMOUNT"),
            "disbursed_amount":  _get_text(primary_summ, "PRIMARY-DISBURSED-AMOUNT"),
        }

    # Inquiry history (same tag in both UAT & PROD)
    inq_history = []
    for h in report.findall(".//INQUIRY-HISTORY/HISTORY"):
        inq_history.append({
            "member":  _get_text(h, "MEMBER-NAME"),
            "date":    _get_text(h, "INQUIRY-DATE"),
            "purpose": _get_text(h, "PURPOSE"),
            "amount":  _get_text(h, "AMOUNT"),
        })
    result["inquiry_history"] = inq_history

    # Personal info variations
    piv = report.find(".//PERSONAL-INFO-VARIATION")
    if piv is not None:
        variations = {}
        for section in piv:
            items = [{"value": _get_text(v, "VALUE"), "reported_date": _get_text(v, "REPORTED-DATE")}
                     for v in section.findall("VARIATION") if _get_text(v, "VALUE")]
            if items:
                variations[section.tag] = items
        result["personal_info_variations"] = variations

    # Verification responses
    verifications = {}
    for v in report.findall(".//VERIFICATION-RESPONSES/RESPONSE"):
        svc = _get_text(v, "REQ-SERVICE-TYPE")
        if svc:
            verifications[svc] = {"status": _get_text(v, "STATUS"), "description": _get_text(v, "DESCRIPTION")}
    result["verifications"] = verifications

    # HTML report
    printable = report.find(".//PRINTABLE-REPORT")
    if printable is not None:
        html_content = ""
        for child in printable:
            if child.tag in ("HTML", "html"):
                html_content = ET.tostring(child, encoding="unicode")
                break
        if not html_content and printable.text:
            html_content = printable.text.strip()
        result["html_report"] = html_content[:500000] if html_content else ""

    return result


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/check/{kyc_id}")
async def run_crif_check(kyc_id: str, current_user: dict = Depends(get_current_user)):
    """Run a CRIF INDV 2.0 credit check for a KYC record."""
    crif_url, crif_user_id, crif_password, crif_mbrid, env_label = _active_config()
    if not all([crif_url, crif_user_id, crif_password, crif_mbrid]):
        raise HTTPException(status_code=503, detail="CRIF credentials not configured")

    # Fetch KYC
    try:
        kyc = await db.kycs.find_one({"_id": ObjectId(kyc_id)})
    except Exception:
        kyc = await db.kycs.find_one({"kyc_number": kyc_id})
    if not kyc:
        raise HTTPException(status_code=404, detail="KYC not found")

    # Check DOB is present (CRIF requires it)
    pb = kyc.get("primary_borrower", {})
    if not pb.get("dob"):
        raise HTTPException(
            status_code=422,
            detail="Date of Birth is required for CRIF check. Please update the KYC with DOB first."
        )

    # Get loan amount from associated loan
    loan_amount = 50000
    loan = await db.loans.find_one({"kyc_id": kyc_id})
    if loan:
        loan_amount = int(loan.get("principal_amount", 50000))

    # Build request XML
    request_xml = _build_crif_xml(kyc, loan_amount=loan_amount, mbrid=crif_mbrid, env=env_label)

    # Call CRIF API
    headers = {
        "requestXML": request_xml,
        "userId": crif_user_id,
        "password": crif_password,
        "mbrid": crif_mbrid,
        "productType": "INDV",
        "productVersion": "2.0",
        "reqVolType": "INDV",
    }
    try:
        response = requests.post(crif_url, headers=headers, timeout=45)
        response.raise_for_status()
    except requests.Timeout:
        raise HTTPException(status_code=504, detail="CRIF API timeout. Please retry.")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CRIF API error: {str(e)}")

    # Parse response
    parsed = _parse_crif_response(response.text)

    # Save to DB
    check_doc = {
        "kyc_id": kyc_id,
        "customer_id": kyc.get("customer_id"),
        "env": env_label,
        "checked_by": current_user.get("id") or current_user.get("_id"),
        "checked_by_name": current_user.get("name"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result": parsed,
        "raw_xml_request": request_xml,
        "raw_xml_response": response.text[:5_000_000],   # 5 MB cap (Mongo limit is 16 MB)
    }
    await db.crif_checks.insert_one(check_doc)

    return {
        "kyc_id": kyc_id,
        "customer_id": kyc.get("customer_id"),
        "env": env_label,
        "checked_at": check_doc["checked_at"],
        "checked_by_name": check_doc["checked_by_name"],
        "result": parsed,
    }


@router.get("/env")
async def get_crif_env(current_user: dict = Depends(get_current_user)):
    """Get current CRIF environment (UAT / PROD)."""
    _, _, _, _, env_label = _active_config()
    return {
        "env": env_label,
        "uat_url": _UAT_URL,
        "prod_url": _PROD_URL,
        "active_url": _active_config()[0],
        "active_mbrid": _active_config()[3],
    }


@router.get("/result/{kyc_id}")
async def get_crif_result(kyc_id: str, current_user: dict = Depends(get_current_user)):
    """Get the most recent CRIF check result for a KYC."""
    check = await db.crif_checks.find_one(
        {"kyc_id": kyc_id},
        sort=[("checked_at", -1)],
        projection={"raw_xml_request": 0, "_id": 0}
    )
    if not check:
        return {"has_result": False}
    result = check.get("result", {})
    _, _, _, _, current_env = _active_config()
    return {
        "has_result": True,
        "kyc_id": check.get("kyc_id"),
        "customer_id": check.get("customer_id"),
        "checked_at": check.get("checked_at"),
        "checked_by_name": check.get("checked_by_name"),
        "env": check.get("env", "UAT"),
        "current_env": current_env,
        "result": result,
    }


@router.get("/report-html/{kyc_id}")
async def get_crif_html_report(kyc_id: str, current_user: dict = Depends(get_current_user)):
    """Get the HTML report from the most recent CRIF check."""
    check = await db.crif_checks.find_one(
        {"kyc_id": kyc_id},
        sort=[("checked_at", -1)],
        projection={"raw_xml_response": 1, "_id": 0}
    )
    if not check:
        raise HTTPException(status_code=404, detail="No CRIF check found")

    # Re-parse to get HTML
    xml_text = check.get("raw_xml_response", "")
    if not xml_text:
        raise HTTPException(status_code=404, detail="No XML response stored")

    parsed = _parse_crif_response(xml_text)
    html = parsed.get("html_report", "")
    if not html:
        raise HTTPException(status_code=404, detail="No HTML report in response")

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
