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
CRIF_URL = os.environ.get("CRIF_URL")
CRIF_USER_ID = os.environ.get("CRIF_USER_ID")
CRIF_PASSWORD = os.environ.get("CRIF_PASSWORD")
CRIF_MBRID = os.environ.get("CRIF_MBRID")
CRIF_SUB_MBR_ID = os.environ.get("CRIF_SUB_MBR_ID", "RADHYA MICRO FINANCE PRIVATE LIMITED")

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


def _build_crif_xml(kyc: dict, loan_amount: int = 50000) -> str:
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
        f"<TEST-FLG>HMTEST</TEST-FLG>"
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
        f"<MBR-ID>{CRIF_MBRID}</MBR-ID>"
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
    """Parse CRIF XML response into structured dict."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"error": f"XML parse error: {e}", "raw_xml": xml_text[:2000]}

    # Handle error response (REPORT-FILE with INQUIRY-STATUS/ERRORS)
    inquiry_status = root.find(".//INQUIRY-STATUS")
    if inquiry_status is not None:
        errors = []
        for err in inquiry_status.findall(".//ERROR"):
            errors.append({
                "code": _get_text(err, "CODE"),
                "description": _get_text(err, "DESCRIPTION"),
            })
        return {
            "status": "error",
            "errors": errors,
            "response_type": _get_text(root, ".//RESPONSE-TYPE", "ERROR"),
        }

    # Extract from INDV-REPORT
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

    # Status details
    statuses = {}
    for s in report.findall(".//STATUS-DETAILS/STATUS"):
        option = _get_text(s, "OPTION")
        status_val = _get_text(s, "OPTION-STATUS")
        if option:
            statuses[option] = status_val
    result["service_statuses"] = statuses

    # Scores
    scores = []
    for score in report.findall(".//SCORES/SCORE"):
        name = _get_text(score, "NAME") or _get_text(score, "SCORE-TYPE")
        value = _get_text(score, "VALUE") or _get_text(score, "SCORE-VALUE")
        desc = _get_text(score, "DESCRIPTION") or _get_text(score, "SCORE-COMMENTS")
        if name:
            scores.append({"name": name, "value": value, "description": desc})
    # Also check PERFORM-CONSUMER score location
    for score in report.findall(".//CNS-ACCOUNT-DETAILS/PERFORM-CONSUMER-SCORE"):
        name = "PERFORM CONSUMER"
        value = _get_text(score, "SCORE-VALUE")
        desc = _get_text(score, "SCORE-COMMENTS")
        scores.append({"name": name, "value": value, "description": desc})
    result["scores"] = scores

    # Account summary
    acc_summary = report.find(".//ACCOUNTS-SUMMARY")
    if acc_summary is not None:
        derived = acc_summary.find("DERIVED-ATTRIBUTES") or ET.Element("X")
        mfi_summ = acc_summary.find("MFI-SUMMARY") or ET.Element("X")
        cns_summ = acc_summary.find("CNS-SUMMARY") or ET.Element("X")
        cns_data = cns_summ.find("CNS-ACCOUNT-DETAILS") or ET.Element("X")

        result["account_summary"] = {
            "inquiries_last_6m": _get_text(derived, "INQUIRIES-IN-LAST-SIX-MONTHS", "0"),
            "credit_history_months": _get_text(derived, "LENGTH-OF-CREDIT-HISTORY-MONTH", "0"),
            "credit_history_years": _get_text(derived, "LENGTH-OF-CREDIT-HISTORY-YEAR", "0"),
            "new_accounts_6m": _get_text(derived, "NEW-ACCOUNTS-IN-LAST-SIX-MONTHS", "0"),
            "delinquent_accounts_6m": _get_text(derived, "NEW-DELINQ-ACCOUNT-IN-LAST-SIX-MONTHS", "0"),
            # MFI summary
            "mfi_total_accounts": _get_text(mfi_summ, "TOTAL-NO-OF-ACCOUNTS"),
            "mfi_active_accounts": _get_text(mfi_summ, "NO-OF-ACTIVE-ACCOUNTS"),
            "mfi_disbursed_amount": _get_text(mfi_summ, "TOTAL-DISBURSED-AMOUNT"),
            "mfi_current_balance": _get_text(mfi_summ, "CURRENT-BALANCE"),
            "mfi_overdue_amount": _get_text(mfi_summ, "OVERDUE-AMOUNT"),
            # CNS summary
            "cns_total_accounts": _get_text(cns_data, "TOTAL-NO-OF-ACCOUNTS"),
            "cns_active_accounts": _get_text(cns_data, "NO-OF-ACTIVE-ACCOUNTS"),
            "cns_disbursed_amount": _get_text(cns_data, "TOTAL-DISBURSED-AMOUNT"),
            "cns_current_balance": _get_text(cns_data, "CURRENT-BALANCE"),
            "cns_overdue_amount": _get_text(cns_data, "OVERDUE-AMOUNT"),
            "cns_write_off_amount": _get_text(cns_data, "TOTAL-WRITE-OFF-AMOUNT"),
        }

    # MFI Accounts list
    mfi_accounts = []
    for acct in report.findall(".//MFI-ACCOUNTS//INDV-ACCOUNT-DETAILS"):
        mfi_accounts.append({
            "lender": _get_text(acct, "CREDIT-GRANTOR-NAME"),
            "loan_type": _get_text(acct, "ACCT-TYPE"),
            "status": _get_text(acct, "ACCT-STATUS"),
            "disbursed": _get_text(acct, "DISBURSED-AMOUNT"),
            "current_balance": _get_text(acct, "CURRENT-BALANCE"),
            "overdue": _get_text(acct, "OVERDUE-AMOUNT"),
            "date_opened": _get_text(acct, "OPEN-DATE"),
            "date_closed": _get_text(acct, "CLOSE-DATE"),
        })
    result["mfi_accounts"] = mfi_accounts

    # Commercial Accounts list (CNS)
    cns_accounts = []
    for acct in report.findall(".//CNS-ACCOUNTS//INDV-ACCOUNT-DETAILS"):
        cns_accounts.append({
            "lender": _get_text(acct, "CREDIT-GRANTOR-NAME"),
            "loan_type": _get_text(acct, "ACCT-TYPE"),
            "status": _get_text(acct, "ACCT-STATUS"),
            "disbursed": _get_text(acct, "DISBURSED-AMOUNT"),
            "current_balance": _get_text(acct, "CURRENT-BALANCE"),
            "overdue": _get_text(acct, "OVERDUE-AMOUNT"),
            "date_opened": _get_text(acct, "OPEN-DATE"),
        })
    result["cns_accounts"] = cns_accounts

    # Verification responses
    verifications = {}
    for resp in report.findall(".//VERIFICATION-RESPONSES/RESPONSE"):
        svc_type = _get_text(resp, "REQ-SERVICE-TYPE")
        status_v = _get_text(resp, "STATUS")
        desc = _get_text(resp, "DESCRIPTION")
        if svc_type:
            verifications[svc_type] = {"status": status_v, "description": desc}
    result["verifications"] = verifications

    # HTML report
    printable = report.find(".//PRINTABLE-REPORT")
    if printable is not None:
        # Get the raw HTML - it's in a CDATA or child element
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
    if not all([CRIF_URL, CRIF_USER_ID, CRIF_PASSWORD, CRIF_MBRID]):
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
    request_xml = _build_crif_xml(kyc, loan_amount=loan_amount)

    # Call CRIF API
    headers = {
        "requestXML": request_xml,
        "userId": CRIF_USER_ID,
        "password": CRIF_PASSWORD,
        "mbrid": CRIF_MBRID,
        "productType": "INDV",
        "productVersion": "2.0",
        "reqVolType": "INDV",
    }
    try:
        response = requests.post(CRIF_URL, headers=headers, timeout=45)
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
        "checked_by": current_user.get("id") or current_user.get("_id"),
        "checked_by_name": current_user.get("name"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result": parsed,
        "raw_xml_request": request_xml,
        "raw_xml_response": response.text[:100000],  # store first 100KB
    }
    await db.crif_checks.insert_one(check_doc)

    return {
        "kyc_id": kyc_id,
        "customer_id": kyc.get("customer_id"),
        "checked_at": check_doc["checked_at"],
        "checked_by_name": check_doc["checked_by_name"],
        "result": parsed,
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
    # Remove large HTML from list response (frontend can fetch separately)
    result = check.get("result", {})
    return {
        "has_result": True,
        "kyc_id": check.get("kyc_id"),
        "customer_id": check.get("customer_id"),
        "checked_at": check.get("checked_at"),
        "checked_by_name": check.get("checked_by_name"),
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
