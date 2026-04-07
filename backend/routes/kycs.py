from fastapi import APIRouter, HTTPException, Request, Query
from bson import ObjectId
from datetime import datetime, timezone, date as date_type
from typing import Optional
import re
from core.database import db
from core.auth import get_current_user
from helpers import (
    _doc, generate_customer_id, generate_loan_number,
    _build_emi_schedule, _get_loan_status, _add_months, _kyc_query_for_user, book_loan_disbursement,
)
from models import KYCCreate, KYCStatusUpdate

router = APIRouter()


@router.get("/kycs")
async def list_kycs(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    illaka_id: Optional[str] = None,
    misal_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    current_user = await get_current_user(request)
    query = await _kyc_query_for_user(current_user)
    if status:
        query["status"] = status
    if illaka_id:
        query["illaka_id"] = illaka_id
    if misal_id:
        query["misal_id"] = misal_id
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
        loan_doc = {
            "kyc_id": kyc_id_str,
            "customer_id": customer_id,
            "loan_number": loan_number,
            "relative_name": data.primary_borrower.relative_name or "",
            "relative_name_hindi": data.primary_borrower.relative_name_hindi or "",
            "client_name": data.primary_borrower.name or "",
            "client_name_hindi": data.primary_borrower.name_hindi or "",
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
    updates = {
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "primary_borrower": data.primary_borrower.model_dump(),
        "co_borrower": data.co_borrower.model_dump() if data.co_borrower else None,
        "guarantor": data.guarantor.model_dump() if data.guarantor else None,
        "live_photo_path": data.live_photo_path,
        "gps_location": data.gps_location.model_dump() if data.gps_location else None,
        "notes": data.notes,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": updates})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="KYC not found")
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
