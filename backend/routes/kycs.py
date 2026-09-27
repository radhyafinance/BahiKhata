from fastapi import APIRouter, HTTPException, Request, Query
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone, date as date_type
from typing import Optional
import re
import contextlib
from core.database import db
from core.auth import get_current_user
from helpers import (
    _doc, generate_customer_id, generate_loan_number,
    _build_emi_schedule, _get_loan_status, _add_months, _kyc_query_for_user,
    get_admin_maalik_filter_ids, book_loan_disbursement, apply_illaka_scope,
    assert_people_not_gyal, permitted_illaka_ids, normalize_aadhaar, normalize_phone,
    clean_person, validate_phone, loan_people, prepare_loan_people, person_is_gyal_linked,
    apply_identity_correction, loan_lock, _person_snapshot, same_person, _snapshot_keys,
    insert_kyc, kyc_lock, assert_open_period, assert_no_old_debt, illaka_requires_aadhaar,
    validate_aadhaar, assert_misal_in_illaka, BORROWER_IDENTITY_REQUIRED,
)
from pydantic import BaseModel
from models import KYCCreate, KYCStatusUpdate, QuickLoanCreate

router = APIRouter()

def _merge_phone_history(old_person: dict, new_person: dict) -> dict:
    """Accumulates all historical phone numbers when the primary phone is updated."""
    if not old_person or not new_person:
        return new_person
    old_phone = (old_person.get("phone") or "").strip()
    new_phone = (new_person.get("phone") or "").strip()
    seen: set = set()
    combined: list = []
    candidates = (
        ([old_phone] if old_phone and (normalize_phone(old_phone) or old_phone) != (normalize_phone(new_phone) or new_phone) else [])
        + (old_person.get("phone_history") or [])
        + (new_person.get("phone_history") or [])
    )
    new_key = normalize_phone(new_phone) or new_phone
    for p in candidates:
        p = (p or "").strip()
        key = normalize_phone(p) or p
        if p and key != new_key and key not in seen:
            seen.add(key)
            combined.append(p)
    new_person["phone_history"] = combined
    return new_person

async def _insert_quick_loan(doc: dict, customer_id: str, kyc_id: str, attempts: int = 6):
    """Insert, taking the next loan number if another request (or a legacy loan
    stored under a differently-cased id) already holds this one."""
    for _ in range(attempts):
        try:
            return await db.loans.insert_one(doc)
        except DuplicateKeyError:
            doc.pop("_id", None)
            doc["loan_number"] = await generate_loan_number(customer_id, kyc_id)
    raise HTTPException(status_code=409, detail="Could not allocate a loan number just now — please try again.")


_SUFFIX_HINDI = {
    "Dhobi": "धोबी", "Darji": "दर्जी", "Kumhar": "कुम्हार", "Lohar": "लोहार",
    "Teli": "तेली", "Nai": "नाई", "Kori": "कोरी", "Mallah": "मल्लाह",
    "Kewat": "केवट", "Kahar": "कहार", "Yadav": "यादव", "Maurya": "मौर्य",
    "Prajapati": "प्रजापति", "Kushwaha": "कुशवाहा", "Pasi": "पासी", "Bind": "बिंद",
    "Rajput": "राजपूत", "Thakur": "ठाकुर", "Sharma": "शर्मा", "Gupta": "गुप्त",
    "Dubey": "दुबे", "Mishra": "मिश्रा", "Chamar": "चमार",
}

def _suffix_hindi(suffix: str) -> str:
    """Return Hindi equivalent of suffix. Handles 'Urf XYZ' → 'उर्फ़ XYZ'."""
    if not suffix:
        return ""
    if suffix.startswith("Urf "):
        return "उर्फ़ " + suffix[4:]
    return _SUFFIX_HINDI.get(suffix, suffix)


@router.get("/kycs")
async def list_kycs(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    illaka_id: Optional[str] = None,
    misal_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    current_user = await get_current_user(request)
    query = await _kyc_query_for_user(current_user)
    await apply_illaka_scope(current_user, query, illaka_id, maalik_id)
    if misal_id:
        query["misal_id"] = misal_id
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"customer_id": {"$regex": search, "$options": "i"}},
            {"kyc_number": {"$regex": search, "$options": "i"}},
            {"primary_borrower.name": {"$regex": search, "$options": "i"}},
            {"primary_borrower.phone": {"$regex": search, "$options": "i"}},
        ]
    total = await db.kycs.count_documents(query)
    docs = await db.kycs.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "kycs": [_doc(d) for d in docs]}


@router.post("/kycs")
async def create_kyc(data: KYCCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["muneem", "sipahi"]:
        raise HTTPException(status_code=403, detail="Only field agents can create KYCs")
    allowed = await permitted_illaka_ids(current_user)
    if allowed is not None and data.illaka_id not in allowed:
        raise HTTPException(status_code=403, detail="This Illaka is not assigned to you")
    await assert_misal_in_illaka(data.misal_id, data.illaka_id)

    # Phones and Aadhaar numbers are checked and stored in one form. Nothing
    # checked them before, so "9300000101/9876500001", an extra digit or a
    # Devanagari number could be saved — and slipped past every later match.
    pb_clean = clean_person(data.primary_borrower, "Borrower")
    cb_clean = clean_person(data.co_borrower, "Co-borrower")
    gt_clean = clean_person(data.guarantor, "Guarantor")

    # Duplicate Aadhaar check
    pb_aadhaar = pb_clean.get("aadhaar_number")
    if pb_aadhaar:
        digits = re.sub(r'\D', '', pb_aadhaar)
        if len(digits) == 12:
            pattern = r'\s*'.join(list(digits))
            if await db.kycs.find_one({"primary_borrower.aadhaar_number": {"$regex": pattern}}):
                raise HTTPException(
                    status_code=400,
                    detail=f"KYC already exists for Aadhaar {pb_aadhaar}. Duplicate entry not allowed / इस आधार नंबर से KYC पहले से मौजूद है।"
                )

    # Duplicate mobile check
    pb_phone = pb_clean.get("phone") or ""
    if pb_phone:
        if await db.kycs.find_one({"primary_borrower.phone": pb_phone}):
            raise HTTPException(
                status_code=400,
                detail=f"Mobile {pb_phone} is already registered with another KYC. / यह मोबाइल नंबर पहले से दर्ज है।"
            )

    # A KYC saved with a disbursement amount pays out a loan in the same call,
    # and had no Gyal check at all — only the duplicate phone/Aadhaar checks
    # above, which compare exact strings.
    people = loan_people({"primary_borrower": pb_clean, "co_borrower": cb_clean, "guarantor": gt_clean})
    if data.disbursement_amount and data.disbursement_amount > 0:
        if not people["borrower"]["aadhaar"] and not people["borrower"]["phones"]:
            raise HTTPException(status_code=400, detail=BORROWER_IDENTITY_REQUIRED)
        if not people["borrower"]["aadhaar"] and await illaka_requires_aadhaar(data.illaka_id):
            raise HTTPException(
                status_code=400,
                detail="The borrower's Aadhaar number is required for a loan. / कर्ज़ के लिए आधार नंबर ज़रूरी है।",
            )
        await assert_people_not_gyal(people)
        await assert_no_old_debt(None, people=people)

    customer_id = await generate_customer_id(data.illaka_name)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "customer_id": customer_id,
        "kyc_number": customer_id,
        "status": "active",
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "primary_borrower": pb_clean,
        "co_borrower": cb_clean,
        "guarantor": gt_clean,
        "live_photo_path": data.live_photo_path,
        "gps_location": data.gps_location.model_dump() if data.gps_location else None,
        "field_officer_id": current_user["id"],
        "field_officer_name": current_user["name"],
        "field_officer_role": current_user["role"],
        "notes": data.notes,
        "disbursement_amount": data.disbursement_amount,
        "loan_id": None,
        "created_at": now, "updated_at": now
    }
    try:
        result = await insert_kyc(doc, data.illaka_name)
    except DuplicateKeyError:
        # Two clients saved with the same Aadhaar at the same moment; this was a 500.
        raise HTTPException(
            status_code=400,
            detail=f"KYC already exists for Aadhaar {pb_aadhaar}. Duplicate entry not allowed / इस आधार नंबर से KYC पहले से मौजूद है।",
        )
    doc["_id"] = result.inserted_id
    customer_id = doc["customer_id"]

    # Auto-create loan if disbursement amount provided
    if data.disbursement_amount and data.disbursement_amount > 0:
        kyc_id_str = str(result.inserted_id)
        loan_date_obj = date_type.today()
        emi_amount, schedule = _build_emi_schedule(data.disbursement_amount, loan_date_obj)
        loan_number = await generate_loan_number(customer_id, kyc_id_str)
        pb = data.primary_borrower
        _suffix = (pb.suffix or "").strip()
        _cn = ((pb.name or "").strip() + (" " + _suffix if _suffix else "")).strip()
        _cn_hi = ((pb.name_hindi or "").strip() + (" " + _suffix_hindi(_suffix) if _suffix else "")).strip()
        loan_doc = {
            "kyc_id": kyc_id_str,
            "customer_id": customer_id,
            "loan_number": loan_number,
            "relative_name": pb.relative_name or "",
            "relative_name_hindi": pb.relative_name_hindi or "",
            "client_name": _cn,
            "client_name_hindi": _cn_hi,
            "client_phone": pb_clean.get("phone") or "",
            "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
            "misal_id": data.misal_id, "misal_name": data.misal_name,
            "principal_amount": data.disbursement_amount,
            "interest_rate": 17.0,
            "emi_amount": emi_amount,
            "total_repayable": emi_amount * 12,
            "interest_amount": (emi_amount * 12) - data.disbursement_amount,
            "loan_date": loan_date_obj.isoformat(),
            "due_date": _add_months(loan_date_obj, 12).isoformat(),
            "status": _get_loan_status(schedule),
            "sipahi_id": current_user["id"], "sipahi_name": current_user["name"],
            "total_paid": 0.0, "notes": None,
            "emi_schedule": schedule,
            "people": people,
            "created_at": now, "updated_at": now,
        }
        loan_res = await _insert_quick_loan(loan_doc, customer_id, kyc_id_str)
        loan_number = loan_doc["loan_number"]
        loan_id = str(loan_res.inserted_id)
        loan_doc["_id"] = loan_res.inserted_id
        await db.kycs.update_one({"_id": result.inserted_id}, {"$set": {"loan_id": loan_id}})
        doc["loan_id"] = loan_id
        await book_loan_disbursement(loan_doc, current_user["id"], current_user["name"])

    return _doc(doc)


async def _quick_add_existing(data, existing_oid, q_co_phone, q_gt_phone, loan_date_obj, loan_date_str,
                             now, current_user):
    existing_kyc = await db.kycs.find_one({"_id": existing_oid})
    if not existing_kyc:
        raise HTTPException(status_code=404, detail="Customer KYC not found")
    customer_id = existing_kyc.get("customer_id") or "—"
    kyc_id_str = str(existing_kyc["_id"])
    # Quick-add is the other way a client already on the books gets a loan,
    # so it needs the same Gyal block as POST /loans and the re-loan path.
    _, q_people = await prepare_loan_people(
        kyc_id_str,
        overrides={
            "co_borrower": {"phone": q_co_phone} if q_co_phone else None,
            "guarantor": {"phone": q_gt_phone} if q_gt_phone else None,
        },
        require_kyc=True, require_aadhaar=False,   # quick-add is a temporary testing path
    )
    # No new money for a client with a loan over three years old that still owes.
    await assert_no_old_debt(kyc_id_str, people=q_people)
    pb = existing_kyc.get("primary_borrower")
    pb = pb if isinstance(pb, dict) else {}
    _suffix = (pb.get("suffix") or "").strip()
    _cn = ((pb.get("name") or "").strip() + (" " + _suffix if _suffix else "")).strip()
    _cn_hi = ((pb.get("name_hindi") or "").strip() + (" " + _suffix_hindi(_suffix) if _suffix else "")).strip()

    emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)
    loan_number = await generate_loan_number(customer_id, kyc_id_str)

    loan_doc = {
        "kyc_id": kyc_id_str,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "client_name": _cn,
        "client_name_hindi": _cn_hi,
        "client_phone": pb.get("phone") or "",
        "relative_name": pb.get("relative_name") or "",
        "relative_name_hindi": pb.get("relative_name_hindi") or "",
        "illaka_id": existing_kyc.get("illaka_id"), "illaka_name": existing_kyc.get("illaka_name"),
        "misal_id": existing_kyc.get("misal_id"), "misal_name": existing_kyc.get("misal_name"),
        "principal_amount": data.principal_amount,
        "interest_rate": 17.0,
        "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": round((emi_amount * 12) - data.principal_amount, 2),
        "loan_date": loan_date_str,
        "due_date": _add_months(loan_date_obj, 12).isoformat(),
        "status": _get_loan_status(schedule),
        "sipahi_id": current_user["id"], "sipahi_name": current_user["name"],
        "total_paid": 0.0, "notes": None,
        "emi_schedule": schedule,
        "people": q_people,
        "source": "quick_add",
        "created_at": now, "updated_at": now,
    }
    loan_res = await _insert_quick_loan(loan_doc, customer_id, kyc_id_str)
    loan_number = loan_doc["loan_number"]
    loan_id = str(loan_res.inserted_id)
    loan_doc["_id"] = loan_res.inserted_id
    await book_loan_disbursement(loan_doc, current_user["id"], current_user["name"])

    return {
        "kyc_id": kyc_id_str,
        "loan_id": loan_id,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": round((emi_amount * 12) - data.principal_amount, 2),
    }


@router.post("/kycs/quick-loan")
async def quick_add_loan(data: QuickLoanCreate, request: Request):
    """Create a minimal KYC + Loan without Aadhaar/photo. Admin and Maalik only.
    If existing_kyc_id is provided, adds a new loan to that existing customer."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can use Quick Add Loan")
    if not (data.principal_amount and data.principal_amount > 0):
        raise HTTPException(status_code=400, detail="Principal amount must be more than zero")
    q_phone = validate_phone(data.phone, "Phone")
    q_co_phone = validate_phone(data.co_borrower_phone, "Co-borrower phone")
    q_gt_phone = validate_phone(data.guarantor_phone, "Guarantor phone")

    # Parse loan date (first of month)
    try:
        year, month = map(int, data.loan_month.split("-"))
        loan_date_obj = date_type(year, month, 1)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan_month format. Use YYYY-MM")

    now = datetime.now(timezone.utc).isoformat()
    loan_date_str = loan_date_obj.isoformat()

    # ── Existing customer path ──
    if data.existing_kyc_id:
        try:
            existing_oid = ObjectId(data.existing_kyc_id.strip())
        except Exception:
            # A malformed id crashed here with a 500
            raise HTTPException(status_code=400, detail="Invalid customer KYC id")
        existing_kyc = await db.kycs.find_one({"_id": existing_oid})
        if not existing_kyc:
            raise HTTPException(status_code=404, detail="Customer KYC not found")
        await assert_open_period(existing_kyc.get("illaka_id"), loan_date_str, what="This loan")
        # The client is locked while the loan is decided and paid out, as for
        # POST /loans: the Gyal check could otherwise pass just before a year-end
        # closing wrote off this client's older loan.
        async with kyc_lock(existing_oid):
            return await _quick_add_existing(data, existing_oid, q_co_phone, q_gt_phone,
                                             loan_date_obj, loan_date_str, now, current_user)

    # ── New customer path (original behavior) ──
    # For new customer, illaka_id, misal_id, name are required
    if not data.illaka_id or not data.misal_id or not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="For new customer, illaka_id, misal_id and name are required")
    await assert_open_period(data.illaka_id, loan_date_str, what="This loan")

    # A new KYC is about to be created with a loan in the same call. Created
    # with the same phone as a written-off client, it was a fresh identity that
    # walked straight past the Gyal block. Ask before anything is written.
    q_people = loan_people({
        "primary_borrower": {"name": (data.name or "").strip(), "phone": q_phone},
        "co_borrower": {"name": (data.co_borrower_name or "").strip(), "phone": q_co_phone},
        "guarantor": {"name": (data.guarantor_name or "").strip(), "phone": q_gt_phone},
    })
    await assert_people_not_gyal(q_people)
    await assert_no_old_debt(None, people=q_people)

    customer_id = await generate_customer_id(data.illaka_name or "")

    _suffix = (data.suffix or "").strip()
    _cn = ((data.name or "").strip() + (" " + _suffix if _suffix else "")).strip()

    co_borrower = None
    if data.co_borrower_name and data.co_borrower_name.strip():
        co_borrower = {"name": data.co_borrower_name.strip(), "phone": q_co_phone}

    guarantor = None
    if data.guarantor_name and data.guarantor_name.strip():
        guarantor = {"name": data.guarantor_name.strip(), "phone": q_gt_phone}

    kyc_doc = {
        "customer_id": customer_id,
        "kyc_number": customer_id,
        "status": "active",
        "source": "quick_add",
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "primary_borrower": {
            "name": (data.name or "").strip(),
            "suffix": _suffix,
            "phone": q_phone,
            "phone_history": [],
        },
        "co_borrower": co_borrower,
        "guarantor": guarantor,
        "live_photo_path": None,
        "gps_location": None,
        "field_officer_id": current_user["id"],
        "field_officer_name": current_user["name"],
        "field_officer_role": current_user["role"],
        "notes": None,
        "disbursement_amount": data.principal_amount,
        "loan_id": None,
        "created_at": now, "updated_at": now,
    }
    kyc_result = await insert_kyc(kyc_doc, data.illaka_name or "")
    customer_id = kyc_doc["customer_id"]
    kyc_id_str = str(kyc_result.inserted_id)

    emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)
    loan_number = await generate_loan_number(customer_id, kyc_id_str)

    loan_doc = {
        "kyc_id": kyc_id_str,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "client_name": _cn,
        "client_name_hindi": "",
        "client_phone": q_phone,
        "relative_name": "", "relative_name_hindi": "",
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "principal_amount": data.principal_amount,
        "interest_rate": 17.0,
        "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": round((emi_amount * 12) - data.principal_amount, 2),
        "loan_date": loan_date_str,
        "due_date": _add_months(loan_date_obj, 12).isoformat(),
        "status": _get_loan_status(schedule),
        "sipahi_id": current_user["id"], "sipahi_name": current_user["name"],
        "total_paid": 0.0, "notes": None,
        "emi_schedule": schedule,
        "people": q_people,
        "source": "quick_add",
        "created_at": now, "updated_at": now,
    }
    loan_res = await _insert_quick_loan(loan_doc, customer_id, kyc_id_str)
    loan_number = loan_doc["loan_number"]
    loan_id = str(loan_res.inserted_id)
    loan_doc["_id"] = loan_res.inserted_id

    await db.kycs.update_one({"_id": kyc_result.inserted_id}, {"$set": {"loan_id": loan_id}})
    await book_loan_disbursement(loan_doc, current_user["id"], current_user["name"])

    return {
        "kyc_id": kyc_id_str,
        "loan_id": loan_id,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": round((emi_amount * 12) - data.principal_amount, 2),
    }


@router.get("/kycs/check-aadhaar")
async def check_aadhaar_exists(request: Request, aadhaar_number: str = Query(...)):
    """Check if a KYC already exists for this Aadhaar number. Returns client info if found."""
    await get_current_user(request)
    digits = re.sub(r'\D', '', aadhaar_number)
    if len(digits) != 12:
        return {"exists": False}
    pattern = r'\s*'.join(list(digits))
    doc = await db.kycs.find_one(
        {"primary_borrower.aadhaar_number": {"$regex": pattern}},
        {"_id": 1, "customer_id": 1, "illaka_id": 1, "illaka_name": 1, "primary_borrower": 1}
    )
    if not doc:
        return {"exists": False}
    return {
        "exists": True,
        "kyc_id": str(doc["_id"]),
        "customer_id": doc.get("customer_id", ""),
        "illaka_id": doc.get("illaka_id", ""),
        "illaka_name": doc.get("illaka_name", ""),
        "client_name": (doc.get("primary_borrower") or {}).get("name", ""),
    }


@router.get("/kycs/{kyc_id}")
async def get_kyc(kyc_id: str, request: Request):
    await get_current_user(request)
    try:
        doc = await db.kycs.find_one({"_id": ObjectId(str(kyc_id).strip())})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid KYC id")
    if not doc:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _doc(doc)


@router.put("/kycs/{kyc_id}")
async def update_kyc(kyc_id: str, data: KYCCreate, request: Request):
    current_user = await get_current_user(request)
    try:
        kyc_oid = ObjectId(str(kyc_id).strip())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid KYC id")
    kyc_id = str(kyc_oid)
    # The client is locked for the whole edit. Its Gyal loans were read with no
    # lock, so a year-end closing writing off a loan at that moment was missed:
    # a correction was not recorded on it, and a field agent's identity change
    # passed the "no changes on a Gyal client" check.
    async with kyc_lock(kyc_oid):
        return await _update_kyc(kyc_oid, kyc_id, data, current_user)


async def _update_kyc(kyc_oid, kyc_id: str, data: KYCCreate, current_user: dict):
    existing = await db.kycs.find_one(
        {"_id": kyc_oid},
        {"_id": 0, "primary_borrower": 1, "co_borrower": 1, "guarantor": 1, "illaka_id": 1, "misal_id": 1},
    )
    if not existing:
        # A missing KYC crashed below with a 500
        raise HTTPException(status_code=404, detail="KYC not found")

    # Anyone signed in could edit any KYC, in any illaka. The same illaka scope as
    # every other write now applies, to the KYC's current illaka and to the one
    # it is being moved to.
    allowed = await permitted_illaka_ids(current_user)
    if allowed is not None and (existing.get("illaka_id") not in allowed
                                or data.illaka_id not in allowed):
        raise HTTPException(status_code=403, detail="This client is not in your assigned Illaka")
    if data.illaka_id != existing.get("illaka_id") or data.misal_id != existing.get("misal_id"):
        await assert_misal_in_illaka(data.misal_id, data.illaka_id)
    # Moving a client who has loans to another Illaka is for an admin or maalik:
    # a field agent could move a client into an Illaka where Aadhaar is not
    # required, lend, and move them back.
    if (existing.get("illaka_id") and data.illaka_id != existing.get("illaka_id")
            and current_user["role"] not in ("admin", "maalik")
            and await db.loans.find_one({"$or": [{"kyc_id": kyc_id}, {"kyc_id_canon": kyc_id}]}, {"_id": 1})):
        raise HTTPException(
            status_code=403,
            detail=("This client has loans. Only an admin or maalik can move them to another Illaka. "
                    "/ कर्ज़ वाले ग्राहक का इलाका केवल एडमिन या मालिक बदल सकते हैं।"),
        )

    def _prev(role):
        prev = existing.get(role)
        return prev if isinstance(prev, dict) else {}

    # Only changed values are format-checked; an unchanged legacy value is kept.
    pb_clean = clean_person(data.primary_borrower, "Borrower", previous=_prev("primary_borrower"))
    cb_clean = clean_person(data.co_borrower, "Co-borrower", previous=_prev("co_borrower"))
    gt_clean = clean_person(data.guarantor, "Guarantor", previous=_prev("guarantor"))

    # The same Aadhaar cannot belong to two clients, however either was typed.
    new_digits = normalize_aadhaar((pb_clean or {}).get("aadhaar_number"))
    if new_digits and new_digits != normalize_aadhaar(_prev("primary_borrower").get("aadhaar_number")):
        clash = await db.kycs.find_one({
            "_id": {"$ne": kyc_oid},
            "primary_borrower.aadhaar_number": {"$regex": "^\\D*" + "\\D*".join(new_digits) + "\\D*$"},
        }, {"customer_id": 1})
        if clash:
            raise HTTPException(
                status_code=400,
                detail="This Aadhaar is already registered to another KYC. / यह आधार पहले से दर्ज है।",
            )

    # The Aadhaar and phone of a person linked to a Gyal loan are what stop them
    # borrowing again. Only an admin or maalik may change them — to correct a
    # data-entry mistake. Checked per person, and on identity only: fixing a
    # clean borrower's phone is not refused because their co-borrower is linked,
    # and correcting the spelling of a name is not an identity change.
    #
    # A person counts as linked when their Aadhaar or phone matches a Gyal loan,
    # or when a Gyal loan on this client recorded them — including by name alone,
    # as imports do, so that adding their Aadhaar later is an admin correction
    # that reaches the written-off loan.
    gyal_loans = [gl async for gl in db.loans.find(
        {"$or": [{"kyc_id": {"$regex": "^\\s*" + kyc_id + "\\s*$", "$options": "i"}},
                 {"kyc_id": kyc_oid}, {"kyc_id_canon": kyc_id}],
         "is_gyal": {"$in": [True, 1]}}, {"_id": 1, "people": 1})]
    #
    # The guarantor is protected the same way: a field agent could otherwise
    # change a Gyal-linked guarantor's number and the loan went through. And on a
    # client that HAS a Gyal loan, nobody's Aadhaar or phone may be changed except
    # by an admin or maalik — renaming a person first no longer detaches them.
    role_key = {"primary_borrower": "borrower", "co_borrower": "co_borrower"}
    new_by_role = {"primary_borrower": pb_clean, "co_borrower": cb_clean, "guarantor": gt_clean}
    identity_changed = []
    changed_roles = []
    for role, new in new_by_role.items():
        if _snapshot_keys(_person_snapshot(_prev(role))) == _snapshot_keys(_person_snapshot(new)):
            continue
        identity_changed.append(role)
        linked = await person_is_gyal_linked(_prev(role), kyc_id if role == "primary_borrower" else None)
        if not linked and role in role_key:
            linked = any(same_person((gl.get("people") or {}).get(role_key[role]), _prev(role))
                         for gl in gyal_loans)
        if linked and role in role_key:
            changed_roles.append(role)
        elif linked:
            changed_roles.append(None)
    if ((changed_roles or (gyal_loans and identity_changed))
            and current_user["role"] not in ("admin", "maalik")):
        raise HTTPException(
            status_code=403,
            detail=("This client is linked to a written-off (Gyal) loan. Only an admin or maalik can "
                    "change the Aadhaar or phone of the borrower, co-borrower or guarantor. / गयाल से जुड़े "
                    "ग्राहक का आधार या फ़ोन केवल एडमिन या मालिक बदल सकते हैं।"),
        )
    # A guarantor is not recorded as liable on a Gyal loan, so nothing to correct.
    changed_roles = [r for r in changed_roles if r]

    # The written-off loans are corrected BEFORE the client's record is saved, each
    # under its own lock. Saving the KYC first meant a lock timeout left the KYC
    # corrected and the loans not — and a retry then saw no difference to apply.
    # Only the same recorded person is changed (see apply_identity_correction).
    for gl_ref in (gyal_loans if changed_roles else []):
        async with loan_lock(str(gl_ref["_id"])):
            gl = await db.loans.find_one({"_id": gl_ref["_id"]}, {"people": 1, "is_gyal": 1})
            if not gl or not gl.get("is_gyal"):
                continue
            people = dict(gl.get("people") or {})
            for role in changed_roles:
                people[role_key[role]] = apply_identity_correction(
                    people.get(role_key[role]), _prev(role), new_by_role[role])
            await db.loans.update_one({"_id": gl_ref["_id"]}, {"$set": {"people": people}})

    pb_dict = _merge_phone_history(_prev("primary_borrower"), pb_clean)
    cb_dict = _merge_phone_history(_prev("co_borrower"), cb_clean) if cb_clean else None
    gt_dict = _merge_phone_history(_prev("guarantor"), gt_clean) if gt_clean else None

    updates = {
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "primary_borrower": pb_dict,
        "co_borrower": cb_dict,
        "guarantor": gt_dict,
        "live_photo_path": data.live_photo_path,
        "gps_location": data.gps_location.model_dump() if data.gps_location else None,
        "notes": data.notes,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    try:
        result = await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": updates})
    except DuplicateKeyError:
        # The unique Aadhaar index refused it. This surfaced as a 500.
        raise HTTPException(
            status_code=400,
            detail="This Aadhaar is already registered to another KYC. / यह आधार पहले से दर्ज है।",
        )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="KYC not found")

    # Propagate name+suffix change to denormalized loan fields
    pb = data.primary_borrower
    _suffix = (pb.suffix or "").strip()
    _cn = ((pb.name or "").strip() + (" " + _suffix if _suffix else "")).strip()
    _cn_hi = ((pb.name_hindi or "").strip() + (" " + _suffix_hindi(_suffix) if _suffix else "")).strip()
    await db.loans.update_many(
        {"kyc_id": kyc_id},
        {"$set": {
            "client_name": _cn,
            "client_name_hindi": _cn_hi,
            "relative_name": pb.relative_name or "",
            "relative_name_hindi": pb.relative_name_hindi or "",
            "client_phone": pb_clean.get("phone") or "",
        }}
    )

    return _doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))


class AddAadhaarRequest(BaseModel):
    aadhaar_number: str
    aadhaar_front_path: Optional[str] = None
    aadhaar_back_path: Optional[str] = None


@router.patch("/kycs/{kyc_id}/aadhaar")
async def add_borrower_aadhaar(kyc_id: str, data: AddAadhaarRequest, request: Request):
    """Add the borrower's Aadhaar to a client who has none — photos optional.

    Clients added without Aadhaar (quick-add, imports, or an Illaka where it was
    switched off) could not be given a loan once Aadhaar was required, and the
    KYC form could not add the number without the photos.
    """
    current_user = await get_current_user(request)
    try:
        kyc_oid = ObjectId(str(kyc_id).strip())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid KYC id")
    kyc_id = str(kyc_oid)
    async with kyc_lock(kyc_oid):
        kyc = await db.kycs.find_one({"_id": kyc_oid})
        if not kyc:
            raise HTTPException(status_code=404, detail="KYC not found")
        allowed = await permitted_illaka_ids(current_user)
        if allowed is not None and kyc.get("illaka_id") not in allowed:
            raise HTTPException(status_code=403, detail="This client is not in your assigned Illaka")
        pb = kyc.get("primary_borrower") if isinstance(kyc.get("primary_borrower"), dict) else {}
        if normalize_aadhaar(pb.get("aadhaar_number")):
            raise HTTPException(status_code=400,
                                detail="This client already has an Aadhaar number. Use Edit KYC to change it.")
        aadhaar = validate_aadhaar(data.aadhaar_number, "Borrower Aadhaar")
        if not aadhaar:
            raise HTTPException(status_code=400, detail="Enter the Aadhaar number / आधार नंबर डालें")
        digits = normalize_aadhaar(aadhaar)
        if await db.kycs.find_one({"_id": {"$ne": kyc_oid},
                                   "primary_borrower.aadhaar_number": {"$regex": "^\\D*" + "\\D*".join(digits) + "\\D*$"}}):
            raise HTTPException(status_code=400,
                                detail="This Aadhaar is already registered to another KYC. / यह आधार पहले से दर्ज है।")
        # On a client with a written-off (Gyal) loan — or one linked to a Gyal loan
        # by phone — identity is changed only by an admin or maalik.
        gyal_loans = [gl async for gl in db.loans.find(
            {"$or": [{"kyc_id": {"$regex": "^\\s*" + kyc_id + "\\s*$", "$options": "i"}},
                     {"kyc_id": kyc_oid}, {"kyc_id_canon": kyc_id}],
             "is_gyal": {"$in": [True, 1]}}, {"_id": 1})]
        if ((gyal_loans or await person_is_gyal_linked(pb, kyc_id))
                and current_user["role"] not in ("admin", "maalik")):
            raise HTTPException(
                status_code=403,
                detail=("This client is linked to a written-off (Gyal) loan. Only an admin or maalik can add "
                        "their Aadhaar. / गयाल ग्राहक का आधार केवल एडमिन या मालिक जोड़ सकते हैं।"),
            )
        now = datetime.now(timezone.utc).isoformat()
        if isinstance(kyc.get("primary_borrower"), dict):
            sets = {"primary_borrower.aadhaar_number": aadhaar, "updated_at": now}
            if data.aadhaar_front_path:
                sets["primary_borrower.aadhaar_front_path"] = data.aadhaar_front_path
            if data.aadhaar_back_path:
                sets["primary_borrower.aadhaar_back_path"] = data.aadhaar_back_path
        else:
            # An older record stored the borrower as text or nothing; it becomes a
            # proper record (setting a field inside it failed with a server error).
            sets = {"primary_borrower": {"aadhaar_number": aadhaar,
                                         "aadhaar_front_path": data.aadhaar_front_path,
                                         "aadhaar_back_path": data.aadhaar_back_path},
                    "updated_at": now}
        # The written-off loans are locked first, the client's record is saved next,
        # and the loans' recorded borrower is updated last. Updating the loans first
        # left an innocent person blocked for good when the save then failed because
        # another client had just taken the same Aadhaar.
        async with contextlib.AsyncExitStack() as stack:
            for gl_ref in gyal_loans:
                await stack.enter_async_context(loan_lock(str(gl_ref["_id"])))
            try:
                await db.kycs.update_one({"_id": kyc_oid}, {"$set": sets})
            except DuplicateKeyError:
                raise HTTPException(status_code=400,
                                    detail="This Aadhaar is already registered to another KYC. / यह आधार पहले से दर्ज है।")
            # This is the borrower of the client's own written-off loans, so the
            # number is added to what those loans recorded whatever the name now
            # reads — renaming first used to keep it off the record.
            for gl_ref in gyal_loans:
                gl = await db.loans.find_one({"_id": gl_ref["_id"]}, {"people": 1, "is_gyal": 1})
                if not gl or not gl.get("is_gyal"):
                    continue
                people = dict(gl.get("people") or {})
                rec = dict(people.get("borrower") or {"name": "", "aadhaar": "", "phones": []})
                if not rec.get("aadhaar"):
                    rec["aadhaar"] = digits
                elif rec["aadhaar"] != digits and digits not in (rec.get("other_aadhaars") or []):
                    rec["other_aadhaars"] = list(rec.get("other_aadhaars") or []) + [digits]
                people["borrower"] = rec
                await db.loans.update_one({"_id": gl_ref["_id"]}, {"$set": {"people": people}})
        return _doc(await db.kycs.find_one({"_id": kyc_oid}))


@router.patch("/kycs/{kyc_id}/status")
async def update_kyc_status(kyc_id: str, data: KYCStatusUpdate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if data.status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    try:
        kyc_id = str(ObjectId(str(kyc_id).strip()))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid KYC id")
    updates = {
        "status": data.status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": current_user["name"],
        "reviewed_at": datetime.now(timezone.utc).isoformat()
    }
    if data.notes:
        updates["notes"] = data.notes
    result = await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": updates})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))
