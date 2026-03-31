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

    # Compute financial year months (April → March) for the selected month
    year_n, mo_n = map(int, month.split("-"))
    fy_start_year = year_n if mo_n >= 4 else year_n - 1
    fy_months = []
    for i in range(12):
        fm = ((3 + i) % 12) + 1   # 4, 5, 6, ..., 12, 1, 2, 3
        fy_y = fy_start_year if fm >= 4 else fy_start_year + 1
        fy_months.append(f"{fy_y}-{fm:02d}")

    query = await _loan_query_for_user(current_user)
    query["status"] = {"$ne": "closed"}
    if illaka_id:
        query["illaka_id"] = illaka_id

    loans = await db.loans.find(query).sort(
        [("illaka_id", 1), ("misal_id", 1), ("created_at", 1)]
    ).to_list(5000)

    # Bulk-fetch live illaka & misal names (source of truth)
    unique_illaka_ids = list({loan.get("illaka_id") for loan in loans if loan.get("illaka_id")})
    unique_misal_ids = list({loan.get("misal_id") for loan in loans if loan.get("misal_id")})
    illaka_name_map: dict = {}
    misal_name_map: dict = {}
    if unique_illaka_ids:
        try:
            oids = [ObjectId(i) for i in unique_illaka_ids]
            raw_illakas = await db.illakas.find({"_id": {"$in": oids}}, {"_id": 1, "name": 1}).to_list(500)
            illaka_name_map = {str(d["_id"]): d["name"] for d in raw_illakas}
        except Exception:
            pass
    if unique_misal_ids:
        try:
            oids = [ObjectId(i) for i in unique_misal_ids]
            raw_misals = await db.misals.find({"_id": {"$in": oids}}, {"_id": 1, "name": 1}).to_list(500)
            misal_name_map = {str(d["_id"]): d["name"] for d in raw_misals}
        except Exception:
            pass

    # Bulk-fetch KYC data for relative_name / guarantor
    kyc_ids = [loan.get("kyc_id") for loan in loans if loan.get("kyc_id")]
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

    # Bulk-fetch payments for Gyal loans across the full FY (for 12-month strip)
    gyal_loan_ids = [str(loan["_id"]) for loan in loans if loan.get("is_gyal")]
    gyal_payment_map: dict = {}   # {loan_id: payment_for_current_month}
    gyal_year_map: dict = {}      # {loan_id: {emi_month: payment}}
    if gyal_loan_ids:
        gyal_payments_fy = await db.payments.find(
            {"loan_id": {"$in": gyal_loan_ids}, "emi_month": {"$in": fy_months}}
        ).to_list(5000)
        for p in gyal_payments_fy:
            lid = p["loan_id"]
            if lid not in gyal_year_map:
                gyal_year_map[lid] = {}
            gyal_year_map[lid][p["emi_month"]] = p
        # Derive current-month map for the emi object
        for lid, months_data in gyal_year_map.items():
            if month in months_data:
                gyal_payment_map[lid] = months_data[month]

    # Group by illaka → misal
    illakas_map = {}
    illaka_order = []
    misal_order = {}

    for loan in loans:
        schedule = loan.get("emi_schedule", [])
        loan_id_str = str(loan["_id"])
        emi = next((e for e in schedule if e.get("due_month") == month), None)

        # Gyal loans always appear regardless of selected month
        if not emi or emi.get("is_gyal_entry"):
            if loan.get("is_gyal"):
                gyal_payment = gyal_payment_map.get(loan_id_str)
                preserved_note = emi.get("note", "") if emi else ""
                emi = {
                    "due_month": month,
                    "amount": gyal_payment["amount"] if gyal_payment else 0,
                    "status": "paid" if gyal_payment else "pending",
                    "note": preserved_note,
                    "paid_amount": gyal_payment["amount"] if gyal_payment else 0,
                    "paid_date": gyal_payment.get("payment_date", "") if gyal_payment else "",
                }
            elif not emi:
                continue

        loan_illaka_id = loan.get("illaka_id", "unknown")
        illaka_name = illaka_name_map.get(loan_illaka_id) or loan.get("illaka_name", "Unknown Illaka")
        misal_id = loan.get("misal_id", "unknown")
        misal_name = misal_name_map.get(misal_id) or loan.get("misal_name", "Unknown Misal")
        kyc_id = loan.get("kyc_id", "")

        kyc = kyc_map.get(kyc_id, {})
        relative_name = (kyc.get("primary_borrower") or {}).get("relative_name") or ""
        relative_name_hindi = (kyc.get("primary_borrower") or {}).get("relative_name_hindi") or ""
        guarantor_name = (kyc.get("guarantor") or {}).get("name") or ""
        guarantor_name_hindi = (kyc.get("guarantor") or {}).get("name_hindi") or ""
        customer_id = loan.get("customer_id") or kyc.get("customer_id") or "—"

        total_repayable = loan.get("total_repayable") or ((loan.get("emi_amount") or 0) * 12)
        outstanding = total_repayable - (loan.get("total_paid") or 0)

        # Build 12-month year data for the FY strip
        is_gyal = loan.get("is_gyal", False)
        loan_gyal_year = gyal_year_map.get(loan_id_str, {})
        emi_year_data = []
        for fy_m in fy_months:
            sched_item = next(
                (e for e in schedule if e.get("due_month") == fy_m and not e.get("is_gyal_entry")),
                None
            )
            if is_gyal:
                gyal_pmt = loan_gyal_year.get(fy_m)
                if gyal_pmt:
                    emi_year_data.append({
                        "month": fy_m, "status": "paid",
                        "paid_amount": float(gyal_pmt.get("amount") or 0), "note": "",
                    })
                elif sched_item:
                    emi_year_data.append({
                        "month": fy_m, "status": sched_item.get("status", "pending"),
                        "paid_amount": float(sched_item.get("paid_amount") or 0),
                        "note": sched_item.get("note") or "",
                    })
                else:
                    emi_year_data.append({"month": fy_m, "status": "na", "paid_amount": 0.0, "note": ""})
            else:
                if sched_item:
                    emi_year_data.append({
                        "month": fy_m, "status": sched_item.get("status", "pending"),
                        "paid_amount": float(sched_item.get("paid_amount") or 0),
                        "note": sched_item.get("note") or "",
                    })
                else:
                    emi_year_data.append({"month": fy_m, "status": "na", "paid_amount": 0.0, "note": ""})

        row = {
            "loan_db_id": loan_id_str,
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
            "emi_paid_amount": float(emi.get("paid_amount") or 0) if emi.get("status") == "paid" else 0,
            "emi_paid_date": emi.get("paid_date") or "",
            "outstanding_balance": outstanding,
            "loan_date": loan.get("loan_date") or "",
            "is_gyal": is_gyal,
            "gyal_since": loan.get("gyal_since") or "",
            "emi_year_data": emi_year_data,
        }

        if loan_illaka_id not in illakas_map:
            illakas_map[loan_illaka_id] = {"illaka_id": loan_illaka_id, "illaka_name": illaka_name, "misals": {}}
            illaka_order.append(loan_illaka_id)
            misal_order[loan_illaka_id] = []
        if misal_id not in illakas_map[loan_illaka_id]["misals"]:
            illakas_map[loan_illaka_id]["misals"][misal_id] = {"misal_id": misal_id, "misal_name": misal_name, "rows": []}
            misal_order[loan_illaka_id].append(misal_id)
        illakas_map[loan_illaka_id]["misals"][misal_id]["rows"].append(row)

    result = []
    for il_id in illaka_order:
        il = illakas_map[il_id]
        misals_list = [il["misals"][m_id] for m_id in misal_order[il_id]]
        result.append({"illaka_id": il["illaka_id"], "illaka_name": il["illaka_name"], "misals": misals_list})

    # Attach the latest year-end closing YYYY-MM per illaka (for edit permission checks)
    result_illaka_ids = [il["illaka_id"] for il in result]
    latest_closings: dict = {}
    if result_illaka_ids:
        gyal_loans_q = await db.loans.find(
            {"illaka_id": {"$in": result_illaka_ids}, "is_gyal": True,
             "gyal_since": {"$exists": True, "$ne": ""}},
            {"illaka_id": 1, "gyal_since": 1}
        ).to_list(5000)
        for gl in gyal_loans_q:
            il_id = gl.get("illaka_id", "")
            gs = gl.get("gyal_since", "")
            if gs and (il_id not in latest_closings or gs > latest_closings[il_id]):
                latest_closings[il_id] = gs
    for il in result:
        closing = latest_closings.get(il["illaka_id"], "")
        il["latest_closing_ym"] = closing[:7] if closing else ""

    total_rows = sum(len(m["rows"]) for il in result for m in il["misals"])
    collected = sum(1 for il in result for m in il["misals"] for r in m["rows"] if r["emi_status"] == "paid")
    return {"month": month, "total": total_rows, "collected": collected, "illakas": result}
