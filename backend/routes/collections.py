from fastapi import APIRouter, Request
from typing import Optional
from datetime import date as date_type
from bson import ObjectId
from core.database import db
from core.auth import get_current_user
from helpers import _loan_query_for_user

router = APIRouter()


@router.get("/collections/sheet")
async def get_collection_sheet(request: Request, month: Optional[str] = None, illaka_id: Optional[str] = None):
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _loan_query_for_user(current_user)
    query["status"] = {"$ne": "closed"}
    if illaka_id:
        query["illaka_id"] = illaka_id

    loans = await db.loans.find(query).sort(
        [("illaka_id", 1), ("misal_id", 1), ("created_at", 1)]
    ).to_list(5000)

    # Bulk-fetch KYC data for relative_name
    kyc_ids = [l.get("kyc_id") for l in loans if l.get("kyc_id")]
    valid_oids = []
    for kid in kyc_ids:
        try:
            valid_oids.append(ObjectId(kid))
        except Exception:
            pass
    kyc_map = {}
    if valid_oids:
        raw_kycs = await db.kycs.find(
            {"_id": {"$in": valid_oids}},
            {"_id": 1, "primary_borrower.relative_name": 1, "primary_borrower.relative_name_hindi": 1,
             "guarantor.name": 1, "guarantor.name_hindi": 1, "customer_id": 1}
        ).to_list(5000)
        kyc_map = {str(k["_id"]): k for k in raw_kycs}

    # Group by illaka → misal
    illakas_map = {}
    illaka_order = []
    misal_order = {}

    for loan in loans:
        schedule = loan.get("emi_schedule", [])
        emi = next((e for e in schedule if e.get("due_month") == month), None)
        if not emi:
            continue

        illaka_id = loan.get("illaka_id", "unknown")
        illaka_name = loan.get("illaka_name", "Unknown Illaka")
        misal_id = loan.get("misal_id", "unknown")
        misal_name = loan.get("misal_name", "Unknown Misal")
        kyc_id = loan.get("kyc_id", "")

        kyc = kyc_map.get(kyc_id, {})
        relative_name = (kyc.get("primary_borrower") or {}).get("relative_name") or ""
        relative_name_hindi = (kyc.get("primary_borrower") or {}).get("relative_name_hindi") or ""
        guarantor_name = (kyc.get("guarantor") or {}).get("name") or ""
        guarantor_name_hindi = (kyc.get("guarantor") or {}).get("name_hindi") or ""
        customer_id = loan.get("customer_id") or kyc.get("customer_id") or "—"

        total_repayable = loan.get("total_repayable") or ((loan.get("emi_amount") or 0) * 12)
        outstanding = total_repayable - (loan.get("total_paid") or 0)

        row = {
            "loan_db_id": str(loan["_id"]),
            "loan_number": loan.get("loan_number") or "—",
            "customer_id": customer_id,
            "client_name": loan.get("client_name") or "",
            "client_name_hindi": loan.get("client_name_hindi") or "",
            "relative_name": relative_name,
            "relative_name_hindi": relative_name_hindi,
            "guarantor_name": guarantor_name,
            "guarantor_name_hindi": guarantor_name_hindi,
            "emi_amount": emi.get("amount", 0),
            "emi_month": emi.get("due_month", month),
            "emi_status": emi.get("status", "pending"),
            "emi_note": emi.get("note") or "",
            "outstanding_balance": outstanding,
        }

        if illaka_id not in illakas_map:
            illakas_map[illaka_id] = {"illaka_id": illaka_id, "illaka_name": illaka_name, "misals": {}}
            illaka_order.append(illaka_id)
            misal_order[illaka_id] = []
        if misal_id not in illakas_map[illaka_id]["misals"]:
            illakas_map[illaka_id]["misals"][misal_id] = {"misal_id": misal_id, "misal_name": misal_name, "rows": []}
            misal_order[illaka_id].append(misal_id)
        illakas_map[illaka_id]["misals"][misal_id]["rows"].append(row)

    result = []
    for il_id in illaka_order:
        il = illakas_map[il_id]
        misals_list = [il["misals"][m_id] for m_id in misal_order[il_id]]
        result.append({"illaka_id": il["illaka_id"], "illaka_name": il["illaka_name"], "misals": misals_list})

    total_rows = sum(len(m["rows"]) for il in result for m in il["misals"])
    collected = sum(1 for il in result for m in il["misals"] for r in m["rows"] if r["emi_status"] == "paid")
    return {"month": month, "total": total_rows, "collected": collected, "illakas": result}
