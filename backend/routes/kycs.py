from fastapi import APIRouter, HTTPException, Request, Query
from bson import ObjectId
from datetime import datetime, timezone, date as date_type
from typing import Optional
import re
from core.database import db
from core.auth import get_current_user
from helpers import (
    _doc, generate_customer_id, generate_loan_number,
    _build_emi_schedule, _get_loan_status, _add_months, _kyc_query_for_user,
    get_admin_maalik_filter_ids, book_loan_disbursement, apply_illaka_scope,
)
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
        ([old_phone] if old_phone and old_phone != new_phone else [])
        + (old_person.get("phone_history") or [])
        + (new_person.get("phone_history") or [])
    )
    for p in candidates:
        p = (p or "").strip()
        if p and p != new_phone and p not in seen:
            seen.add(p)
            combined.append(p)
    new_person["phone_history"] = combined
    return new_person

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

    # Duplicate Aadhaar check
    pb_aadhaar = data.primary_borrower.aadhaar_number
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
    pb_phone = (data.primary_borrower.phone or "").strip()
    if pb_phone:
        if await db.kycs.find_one({"primary_borrower.phone": pb_phone}):
            raise HTTPException(
                status_code=400,
                detail=f"Mobile {pb_phone} is already registered with another KYC. / यह मोबाइल नंबर पहले से दर्ज है।"
            )

    customer_id = await generate_customer_id(data.illaka_name)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "customer_id": customer_id,
        "kyc_number": customer_id,
        "status": "active",
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "primary_borrower": data.primary_borrower.model_dump(),
        "co_borrower": data.co_borrower.model_dump() if data.co_borrower else None,
        "guarantor": data.guarantor.model_dump() if data.guarantor else None,
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
    result = await db.kycs.insert_one(doc)
    doc["_id"] = result.inserted_id

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
            "client_phone": data.primary_borrower.phone,
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
            "created_at": now, "updated_at": now,
        }
        loan_res = await db.loans.insert_one(loan_doc)
        loan_id = str(loan_res.inserted_id)
        loan_doc["_id"] = loan_res.inserted_id
        await db.kycs.update_one({"_id": result.inserted_id}, {"$set": {"loan_id": loan_id}})
        doc["loan_id"] = loan_id
        await book_loan_disbursement(loan_doc, current_user["id"], current_user["name"])

    return _doc(doc)


@router.post("/kycs/quick-loan")
async def quick_add_loan(data: QuickLoanCreate, request: Request):
    """Create a minimal KYC + Loan without Aadhaar/photo. Admin and Maalik only.
    If existing_kyc_id is provided, adds a new loan to that existing customer."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can use Quick Add Loan")

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
        existing_kyc = await db.kycs.find_one({"_id": ObjectId(data.existing_kyc_id)})
        if not existing_kyc:
            raise HTTPException(status_code=404, detail="Customer KYC not found")

        customer_id = existing_kyc["customer_id"]
        kyc_id_str = str(existing_kyc["_id"])
        pb = existing_kyc.get("primary_borrower") or {}
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
            "source": "quick_add",
            "created_at": now, "updated_at": now,
        }
        loan_res = await db.loans.insert_one(loan_doc)
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

    # ── New customer path (original behavior) ──
    # For new customer, illaka_id, misal_id, name are required
    if not data.illaka_id or not data.misal_id or not data.name or not data.name.strip():
        raise HTTPException(status_code=400, detail="For new customer, illaka_id, misal_id and name are required")

    customer_id = await generate_customer_id(data.illaka_name or "")

    _suffix = (data.suffix or "").strip()
    _cn = ((data.name or "").strip() + (" " + _suffix if _suffix else "")).strip()

    co_borrower = None
    if data.co_borrower_name and data.co_borrower_name.strip():
        co_borrower = {"name": data.co_borrower_name.strip(), "phone": data.co_borrower_phone or ""}

    guarantor = None
    if data.guarantor_name and data.guarantor_name.strip():
        guarantor = {"name": data.guarantor_name.strip(), "phone": data.guarantor_phone or ""}

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
            "phone": data.phone or "",
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
    kyc_result = await db.kycs.insert_one(kyc_doc)
    kyc_id_str = str(kyc_result.inserted_id)

    emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)
    loan_number = await generate_loan_number(customer_id, kyc_id_str)

    loan_doc = {
        "kyc_id": kyc_id_str,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "client_name": _cn,
        "client_name_hindi": "",
        "client_phone": data.phone or "",
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
        "source": "quick_add",
        "created_at": now, "updated_at": now,
    }
    loan_res = await db.loans.insert_one(loan_doc)
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
    doc = await db.kycs.find_one({"_id": ObjectId(kyc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _doc(doc)


@router.put("/kycs/{kyc_id}")
async def update_kyc(kyc_id: str, data: KYCCreate, request: Request):
    await get_current_user(request)

    existing = await db.kycs.find_one({"_id": ObjectId(kyc_id)}, {"_id": 0, "primary_borrower": 1, "co_borrower": 1, "guarantor": 1})

    pb_dict = _merge_phone_history(existing.get("primary_borrower") or {}, data.primary_borrower.model_dump())
    cb_dict = _merge_phone_history(existing.get("co_borrower") or {}, data.co_borrower.model_dump()) if data.co_borrower else None
    gt_dict = _merge_phone_history(existing.get("guarantor") or {}, data.guarantor.model_dump()) if data.guarantor else None

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
    result = await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": updates})
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
            "client_phone": pb.phone or "",
        }}
    )

    return _doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))


@router.patch("/kycs/{kyc_id}/status")
async def update_kyc_status(kyc_id: str, data: KYCStatusUpdate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if data.status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")
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
