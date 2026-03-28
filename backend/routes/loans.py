from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone, date as date_type
from typing import Optional
import calendar
from core.database import db
from core.auth import get_current_user
from helpers import (
    _doc, generate_loan_number, _build_emi_schedule,
    _get_loan_status, _apply_overdue_to_schedule, _add_months, _loan_query_for_user
)
from models import LoanCreate, LoanStatusUpdate, PaymentCreate, EmiNoteUpdate, ReLoanRequest

router = APIRouter()


@router.get("/loans")
async def list_loans(
    request: Request,
    illaka_id: Optional[str] = None,
    misal_id: Optional[str] = None,
    kyc_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
):
    current_user = await get_current_user(request)
    query = await _loan_query_for_user(current_user)
    if illaka_id:
        query["illaka_id"] = illaka_id
    if misal_id:
        query["misal_id"] = misal_id
    if kyc_id:
        query["kyc_id"] = kyc_id
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_phone": {"$regex": search, "$options": "i"}},
        ]
    total = await db.loans.count_documents(query)
    docs = await db.loans.find(query).sort("loan_date", 1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "loans": [_doc(d) for d in docs]}


@router.post("/loans")
async def create_loan(data: LoanCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["muneem", "sipahi"]:
        raise HTTPException(status_code=403, detail="Only field agents can create loans")
    now = datetime.now(timezone.utc).isoformat()
    loan_date_obj = date_type.fromisoformat(data.loan_date)
    emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)

    customer_id = "—"
    relative_name = ""
    relative_name_hindi = ""
    client_name_hindi = ""
    if data.kyc_id:
        try:
            kyc = await db.kycs.find_one(
                {"_id": ObjectId(data.kyc_id)},
                {"customer_id": 1, "primary_borrower.relative_name": 1,
                 "primary_borrower.relative_name_hindi": 1, "primary_borrower.name_hindi": 1}
            )
            if kyc:
                customer_id = kyc.get("customer_id") or "—"
                pb = kyc.get("primary_borrower") or {}
                relative_name = pb.get("relative_name") or ""
                relative_name_hindi = pb.get("relative_name_hindi") or ""
                client_name_hindi = pb.get("name_hindi") or ""
        except Exception:
            pass

    loan_number = await generate_loan_number(customer_id, data.kyc_id)

    doc = {
        "kyc_id": data.kyc_id,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "relative_name": relative_name,
        "relative_name_hindi": relative_name_hindi,
        "client_name": data.client_name,
        "client_name_hindi": client_name_hindi,
        "client_phone": data.client_phone,
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
        "principal_amount": data.principal_amount,
        "interest_rate": 17.0,
        "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": (emi_amount * 12) - data.principal_amount,
        "loan_date": data.loan_date,
        "due_date": _add_months(loan_date_obj, 12).isoformat(),
        "status": _get_loan_status(schedule),
        "sipahi_id": current_user["id"], "sipahi_name": current_user["name"],
        "total_paid": 0.0, "notes": data.notes,
        "emi_schedule": schedule,
        "created_at": now, "updated_at": now,
    }
    result = await db.loans.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc(doc)


@router.get("/loans/{loan_id}")
async def get_loan(loan_id: str, request: Request):
    await get_current_user(request)
    doc = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    schedule = doc.get("emi_schedule", [])
    if schedule:
        changed = _apply_overdue_to_schedule(schedule)
        new_status = _get_loan_status(schedule)
        if changed or new_status != doc.get("status"):
            await db.loans.update_one(
                {"_id": ObjectId(loan_id)},
                {"$set": {"emi_schedule": schedule, "status": new_status,
                          "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            doc["emi_schedule"] = schedule
            doc["status"] = new_status
    return _doc(doc)


@router.put("/loans/{loan_id}")
async def update_loan(loan_id: str, data: LoanCreate, request: Request):
    current_user = await get_current_user(request)
    loan = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if current_user["role"] not in ["admin", "maalik", "muneem"] and loan.get("sipahi_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    loan_date_obj = date_type.fromisoformat(data.loan_date)
    emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)
    old_schedule = loan.get("emi_schedule", [])
    for i, item in enumerate(schedule):
        if i < len(old_schedule) and old_schedule[i]["status"] == "paid":
            schedule[i] = old_schedule[i]
    updates = {
        "client_name": data.client_name, "client_phone": data.client_phone,
        "principal_amount": data.principal_amount, "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": (emi_amount * 12) - data.principal_amount,
        "loan_date": data.loan_date,
        "due_date": _add_months(loan_date_obj, 12).isoformat(),
        "notes": data.notes, "emi_schedule": schedule,
        "status": _get_loan_status(schedule),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.loans.update_one({"_id": ObjectId(loan_id)}, {"$set": updates})
    return _doc(await db.loans.find_one({"_id": ObjectId(loan_id)}))


@router.patch("/loans/{loan_id}/status")
async def update_loan_status(loan_id: str, data: LoanStatusUpdate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if data.status not in ["active", "closed", "overdue"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates = {"status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if data.notes:
        updates["notes"] = data.notes
    result = await db.loans.update_one({"_id": ObjectId(loan_id)}, {"$set": updates})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Loan not found")
    return _doc(await db.loans.find_one({"_id": ObjectId(loan_id)}))


@router.get("/loans/{loan_id}/payments")
async def list_payments(loan_id: str, request: Request):
    await get_current_user(request)
    docs = await db.payments.find({"loan_id": loan_id}).sort("payment_date", -1).to_list(500)
    return [_doc(d) for d in docs]


@router.post("/loans/{loan_id}/payments")
async def collect_emi(loan_id: str, data: PaymentCreate, request: Request):
    current_user = await get_current_user(request)
    doc = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    schedule = doc.get("emi_schedule", [])
    emi_item = next((e for e in schedule if e["due_month"] == data.emi_month), None)
    if not emi_item:
        raise HTTPException(status_code=404, detail=f"EMI month {data.emi_month} not found in loan schedule")
    if emi_item["status"] == "paid":
        raise HTTPException(status_code=400, detail="This EMI is already paid / यह किस्त पहले से चुकाई जा चुकी है")
    amount = data.amount if data.amount else emi_item["amount"]
    emi_item.update({
        "status": "paid",
        "paid_amount": amount,
        "paid_date": data.payment_date,
        "collected_by_id": current_user["id"],
        "collected_by_name": current_user["name"],
    })
    total_paid = sum(e.get("paid_amount", 0) for e in schedule if e["status"] == "paid")
    new_status = _get_loan_status(schedule)
    now = datetime.now(timezone.utc).isoformat()
    await db.loans.update_one(
        {"_id": ObjectId(loan_id)},
        {"$set": {"emi_schedule": schedule, "total_paid": total_paid, "status": new_status, "updated_at": now}}
    )
    await db.payments.insert_one({
        "loan_id": loan_id, "emi_month": data.emi_month,
        "amount": amount, "payment_date": data.payment_date,
        "collected_by_id": current_user["id"], "collected_by_name": current_user["name"],
        "notes": data.notes, "created_at": now,
    })
    return _doc(await db.loans.find_one({"_id": ObjectId(loan_id)}))


@router.delete("/loans/{loan_id}/payments/{emi_month}")
async def uncollect_emi(loan_id: str, emi_month: str, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")
    doc = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    schedule = doc.get("emi_schedule", [])
    emi_item = next((e for e in schedule if e["due_month"] == emi_month), None)
    if not emi_item:
        raise HTTPException(status_code=404, detail="EMI month not found")
    y, mo = map(int, emi_month.split("-"))
    last_day = calendar.monthrange(y, mo)[1]
    new_emi_status = "overdue" if date_type.today() > date_type(y, mo, last_day) else "pending"
    emi_item.update({
        "status": new_emi_status, "paid_amount": 0.0,
        "paid_date": None, "collected_by_id": None, "collected_by_name": None
    })
    total_paid = sum(e.get("paid_amount", 0) for e in schedule if e["status"] == "paid")
    now = datetime.now(timezone.utc).isoformat()
    await db.loans.update_one(
        {"_id": ObjectId(loan_id)},
        {"$set": {"emi_schedule": schedule, "total_paid": total_paid,
                  "status": _get_loan_status(schedule), "updated_at": now}}
    )
    await db.payments.delete_one({"loan_id": loan_id, "emi_month": emi_month})
    return {"message": f"EMI for {emi_month} uncollected"}


@router.patch("/loans/{loan_id}/emi-note")
async def update_emi_note(loan_id: str, data: EmiNoteUpdate, request: Request):
    """Add or update a note on a specific EMI."""
    await get_current_user(request)
    try:
        oid = ObjectId(loan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan ID")
    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    schedule = doc.get("emi_schedule", [])
    emi_item = next((e for e in schedule if e["due_month"] == data.emi_month), None)
    if not emi_item:
        raise HTTPException(status_code=404, detail=f"EMI {data.emi_month} not found in schedule")
    emi_item["note"] = data.note.strip()
    now = datetime.now(timezone.utc).isoformat()
    await db.loans.update_one({"_id": oid}, {"$set": {"emi_schedule": schedule, "updated_at": now}})
    return _doc(await db.loans.find_one({"_id": oid}))


@router.post("/loans/{loan_id}/reloan")
async def create_reloan(loan_id: str, data: ReLoanRequest, request: Request):
    """Create a re-loan for an existing client. Optionally net-off outstanding balance."""
    current_user = await get_current_user(request)
    try:
        oid = ObjectId(loan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan ID")

    loan = await db.loans.find_one({"_id": oid})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    kyc_id = loan.get("kyc_id")
    customer_id = loan.get("customer_id", "—")
    now = datetime.now(timezone.utc).isoformat()

    # Calculate outstanding on existing loan
    schedule = loan.get("emi_schedule", [])
    total_repayable = float(loan.get("total_repayable") or ((loan.get("emi_amount") or 0) * 12))
    total_paid = float(loan.get("total_paid") or 0.0)
    outstanding = max(0.0, total_repayable - total_paid)
    netoff_amount = 0.0

    # Net-off: close existing active/overdue loan
    if data.net_off and outstanding > 0 and loan.get("status") != "closed":
        for emi in schedule:
            if emi.get("status") != "paid":
                emi["status"] = "netoff"
                emi["note"] = f"Net-off: closed via re-loan on {data.loan_date}"
        netoff_amount = outstanding
        await db.loans.update_one(
            {"_id": oid},
            {"$set": {
                "emi_schedule": schedule,
                "status": "closed",
                "netoff_closed": True,
                "netoff_date": now,
                "updated_at": now,
            }}
        )

    # Update KYC phone / co_borrower / guarantor if provided
    if kyc_id:
        kyc_updates = {}
        if data.phone:
            kyc_updates["primary_borrower.phone"] = data.phone
        if data.co_borrower:
            co_data = {k: v for k, v in data.co_borrower.model_dump().items() if v is not None}
            if co_data:
                kyc_updates["co_borrower"] = co_data
        if data.guarantor:
            g_data = {k: v for k, v in data.guarantor.model_dump().items() if v is not None}
            if g_data:
                kyc_updates["guarantor"] = g_data
        if kyc_updates:
            kyc_updates["updated_at"] = now
            try:
                await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": kyc_updates})
            except Exception:
                pass

    # Fetch KYC fields for the new loan record
    relative_name, relative_name_hindi, client_name_hindi = "", "", ""
    if kyc_id:
        try:
            kyc_doc = await db.kycs.find_one(
                {"_id": ObjectId(kyc_id)},
                {"primary_borrower.relative_name": 1,
                 "primary_borrower.relative_name_hindi": 1,
                 "primary_borrower.name_hindi": 1}
            )
            if kyc_doc:
                pb = kyc_doc.get("primary_borrower") or {}
                relative_name = pb.get("relative_name") or ""
                relative_name_hindi = pb.get("relative_name_hindi") or ""
                client_name_hindi = pb.get("name_hindi") or ""
        except Exception:
            pass

    # Build and insert new loan
    loan_date_obj = date_type.fromisoformat(data.loan_date)
    emi_amount, new_schedule = _build_emi_schedule(data.new_disbursement_amount, loan_date_obj)
    loan_number = await generate_loan_number(customer_id, kyc_id or loan_id)
    net_disbursement = data.new_disbursement_amount - netoff_amount

    new_loan_doc = {
        "kyc_id": kyc_id,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "relative_name": relative_name,
        "relative_name_hindi": relative_name_hindi,
        "client_name": loan.get("client_name"),
        "client_name_hindi": client_name_hindi,
        "client_phone": data.phone or loan.get("client_phone"),
        "illaka_id": loan.get("illaka_id"),
        "illaka_name": loan.get("illaka_name"),
        "misal_id": loan.get("misal_id"),
        "misal_name": loan.get("misal_name"),
        "principal_amount": data.new_disbursement_amount,
        "interest_rate": 17.0,
        "emi_amount": emi_amount,
        "total_repayable": emi_amount * 12,
        "interest_amount": (emi_amount * 12) - data.new_disbursement_amount,
        "loan_date": data.loan_date,
        "due_date": _add_months(loan_date_obj, 12).isoformat(),
        "status": _get_loan_status(new_schedule),
        "sipahi_id": current_user["id"],
        "sipahi_name": current_user["name"],
        "total_paid": 0.0,
        "notes": data.notes,
        "emi_schedule": new_schedule,
        "is_reloan": True,
        "parent_loan_id": loan_id,
        "netoff_amount": netoff_amount,
        "net_disbursement_amount": net_disbursement,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.loans.insert_one(new_loan_doc)
    new_id = str(result.inserted_id)

    # Back-link old loan to new loan
    await db.loans.update_one({"_id": oid}, {"$set": {"reloan_id": new_id, "updated_at": now}})

    new_loan_doc["_id"] = result.inserted_id
    return _doc(new_loan_doc)
