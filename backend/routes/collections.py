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
    # No status filter here — closed loans must remain on the sheet until their EMI
    # schedule ends (end of FY or year-end closing). The EMI schedule lookup below
    # (`emi = next(...)`) naturally hides them for months outside their schedule.
    if illaka_id:
        query["illaka_id"] = illaka_id

    loans = await db.loans.find(query).sort(
        [("illaka_id", 1), ("misal_id", 1), ("loan_date", 1)]
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
                # Non-gyal loan with no EMI for this specific month.
                # Keep if any of these are true:
                #   (a) loan has at least one EMI in the current FY
                #   (b) loan was disbursed in the current FY (first EMI may be next FY)
                #   (c) loan is still active/overdue AND was disbursed before the FY ended
                #       (overdue debt that spans into/beyond this FY must remain visible)
                loan_has_fy_emi = any(e.get("due_month") in fy_months for e in schedule)
                loan_date_ym = (loan.get("loan_date") or "")[:7]
                loan_disbursed_in_fy = loan_date_ym in fy_months
                # Loan existed during this FY only if it was disbursed before the FY ended
                loan_existed_by_fy_end = bool(loan_date_ym) and loan_date_ym <= fy_months[-1]
                loan_has_outstanding = loan.get("status") in ("active", "overdue")
                if not loan_has_fy_emi and not loan_disbursed_in_fy and not (loan_has_outstanding and loan_existed_by_fy_end):
                    continue  # Loan is outside this FY — skip
                if not schedule:
                    continue
                # For newly disbursed loans (first EMI in next FY): use the FIRST EMI
                # For overdue/past-schedule loans: use the LAST EMI (most recent due)
                if loan_disbursed_in_fy and not loan_has_fy_emi:
                    rep_emi = schedule[0]
                else:
                    rep_emi = schedule[-1]
                emi = {
                    "due_month": rep_emi.get("due_month", month),
                    "amount": rep_emi.get("amount", 0),
                    "status": rep_emi.get("status", "pending"),
                    "note": rep_emi.get("note", ""),
                    "paid_amount": float(rep_emi.get("paid_amount") or 0),
                    "paid_date": rep_emi.get("paid_date", ""),
                }

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
        # FY-end balance: only count paid EMIs whose due_month falls ON OR BEFORE the
        # last month of the selected FY.  Using the EMI schedule (not the cached
        # loan.total_paid field) ensures the Bal column reflects the state at the
        # end of the viewed FY rather than the current all-time outstanding.
        paid_through_fy_end = sum(
            float(e.get("paid_amount") or 0)
            for e in schedule
            if e.get("status") == "paid" and (e.get("due_month") or "") <= fy_months[-1]
        )
        outstanding = max(0.0, total_repayable - paid_through_fy_end)

        # Opening balance at the START of the viewed FY (पिछली बाक़ी).
        # = total_repayable minus EMIs that were paid BEFORE the FY began.
        paid_before_fy = sum(
            float(e.get("paid_amount") or 0)
            for e in schedule
            if e.get("status") == "paid" and (e.get("due_month") or "") < fy_months[0]
        )
        opening_balance = max(0.0, total_repayable - paid_before_fy)

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
            "opening_balance": opening_balance,
            "loan_date": loan.get("loan_date") or "",
            "total_repayable": float(loan.get("total_repayable") or 0),
            "netoff_amount": float(loan.get("netoff_amount") or 0),
            "is_gyal": is_gyal,
            "gyal_since": loan.get("gyal_since") or "",
            "emi_year_data": emi_year_data,
            # Net-off merge metadata
            "_is_reloan": loan.get("is_reloan", False),
            "_parent_loan_id": str(loan.get("parent_loan_id") or ""),
            "_netoff_closed": loan.get("netoff_closed", False),
            "_reloan_id": str(loan.get("reloan_id") or ""),
            # Combined fields (filled during post-processing)
            "is_netoff_combined": False,
            "prev_opening_balance": 0.0,
            "new_loan_in_fy": False,
            "extra_kisht_entries": [],
        }

        if loan_illaka_id not in illakas_map:
            illakas_map[loan_illaka_id] = {"illaka_id": loan_illaka_id, "illaka_name": illaka_name, "misals": {}}
            illaka_order.append(loan_illaka_id)
            misal_order[loan_illaka_id] = []
        if misal_id not in illakas_map[loan_illaka_id]["misals"]:
            illakas_map[loan_illaka_id]["misals"][misal_id] = {"misal_id": misal_id, "misal_name": misal_name, "rows": []}
            misal_order[loan_illaka_id].append(misal_id)
        illakas_map[loan_illaka_id]["misals"][misal_id]["rows"].append(row)

    # ── Net-off merge pass ────────────────────────────────────────────────
    # For net-off pairs (L1 netoff-closed → L2 re-loan), merge both into ONE row.
    # L2 is the primary row (active, Collect button targets it).
    # L1's FY strip fills months where L2 has no data ("na").
    # Combined row shows L1's opening balance in पिछली बाक़ी and L2's amount in किस्त हाल.
    all_loans_by_id = {str(l["_id"]): l for l in loans}

    for il_id in illaka_order:
        for m_id in misal_order[il_id]:
            rows = illakas_map[il_id]["misals"][m_id]["rows"]
            row_by_loan_id = {r["loan_db_id"]: r for r in rows}
            to_remove_ids = set()

            for row in rows:
                if not row.get("_is_reloan") or not row.get("_parent_loan_id"):
                    continue
                parent_id = row["_parent_loan_id"]
                parent_row = row_by_loan_id.get(parent_id)

                # Case A: parent also appears as a row in this FY
                if parent_row and parent_row.get("_netoff_closed"):
                    parent_strip = {e["month"]: e for e in parent_row["emi_year_data"]}
                    parent_opening = float(parent_row.get("opening_balance") or 0)
                    parent_loan_date = parent_row.get("loan_date") or ""
                    parent_emi_amount = float(parent_row.get("emi_amount") or 0)
                    to_remove_ids.add(parent_id)

                # Case B: parent is netoff-closed but NOT in this FY's rows
                #         (e.g. L1 schedule ended before this FY)
                elif not parent_row:
                    parent_loan = all_loans_by_id.get(parent_id)
                    if not parent_loan or not parent_loan.get("netoff_closed"):
                        continue
                    parent_sched = parent_loan.get("emi_schedule", [])
                    parent_repayable = float(parent_loan.get("total_repayable") or 0)
                    parent_paid_before_fy = sum(
                        float(e.get("paid_amount") or 0)
                        for e in parent_sched
                        if e.get("status") == "paid" and (e.get("due_month") or "") < fy_months[0]
                    )
                    parent_opening = max(0.0, parent_repayable - parent_paid_before_fy)
                    parent_loan_date = parent_loan.get("loan_date") or ""
                    parent_emi_amount = float(parent_loan.get("emi_amount") or 0)
                    # Build parent FY strip from its schedule
                    parent_strip = {}
                    for ym in fy_months:
                        yd = next((e for e in parent_sched if e.get("due_month") == ym), None)
                        if yd:
                            parent_strip[ym] = {"month": ym, "status": yd["status"], "paid_amount": float(yd.get("paid_amount") or 0), "note": yd.get("note", "")}
                else:
                    continue

                # Merge parent strip into child (L2 takes priority for non-na months).
                # IMPORTANT: skip parent's "netoff" status entries — those mark the old loan
                # closing and must NOT bleed the ↩ symbol into the combined row's FY strip.
                # The ↩ will be injected at L2's actual loan-start month below.
                merged_strip = []
                for entry in row["emi_year_data"]:
                    if entry["status"] != "na":
                        merged_strip.append(entry)
                    elif (entry["month"] in parent_strip
                          and parent_strip[entry["month"]]["status"] not in ("na", "netoff")):
                        merged_strip.append(parent_strip[entry["month"]])
                    else:
                        merged_strip.append(entry)

                # Inject a "chain_start" marker at the month when THIS re-loan was disbursed.
                # This places the ↩ symbol exactly where the net-off transaction occurred,
                # not one month earlier on L1's closing EMI.
                row_start_ym = (row.get("loan_date") or "")[:7]
                row["emi_year_data"] = [
                    {"month": e["month"], "status": "chain_start", "paid_amount": 0.0, "note": ""}
                    if (e["month"] == row_start_ym and e["status"] == "na")
                    else e
                    for e in merged_strip
                ]

                row["is_netoff_combined"] = True
                row["prev_emi_amount"] = parent_emi_amount

                # ── Determine पिछली बाक़ी and किस्त हाल values ──────────────────
                # Gather chain metadata from parent (differs between Case A and Case B)
                if parent_row:  # Case A — parent is a processed row
                    _par_combined   = parent_row.get("is_netoff_combined", False)
                    _par_netoff_amt = float(parent_row.get("netoff_amount") or 0)
                    _par_repayable  = float(parent_row.get("total_repayable") or 0)
                    _par_date       = parent_row.get("loan_date", "")
                    _par_extra      = list(parent_row.get("extra_kisht_entries") or [])
                    _par_root_bal   = float(parent_row.get("prev_opening_balance") or 0)
                    _par_root_date  = parent_row.get("prev_loan_date", "")
                else:  # Case B — parent from all_loans_by_id (raw loan)
                    _par_combined   = False
                    _par_netoff_amt = float(parent_loan.get("netoff_amount") or 0)
                    _par_repayable  = 0.0
                    _par_date       = ""
                    _par_extra      = []
                    _par_root_bal   = 0.0
                    _par_root_date  = ""

                row_loan_ym = (row.get("loan_date") or "")[:7]
                l2_before_fy = bool(row_loan_ym) and row_loan_ym < fy_months[0]

                if l2_before_fy:
                    # This re-loan started BEFORE the selected FY.
                    # पिछली बाक़ी = this loan's own opening balance at FY start + its loan date.
                    # किस्त हाल = blank (not a new loan in this FY).
                    row["prev_opening_balance"] = row.get("opening_balance", 0.0)
                    row["prev_loan_date"]        = row.get("loan_date", "")
                    row["new_loan_in_fy"]        = False
                    row["extra_kisht_entries"]   = []
                else:
                    # This re-loan was disbursed IN the selected FY.
                    # पिछली बाक़ी = the ROOT original loan's netoff amount + its loan date.
                    # किस्त हाल = all re-loans in the chain (extras first, then this row).
                    if _par_combined:
                        # Parent was itself already combined → chain the root data through.
                        row["prev_opening_balance"] = _par_root_bal
                        row["prev_loan_date"]       = _par_root_date
                        # Add parent as a new kisht entry; carry forward its extra entries.
                        row["extra_kisht_entries"] = _par_extra + [
                            {"amount": _par_repayable, "loan_date": _par_date}
                        ]
                    else:
                        # Parent is the uncombined original loan → use its netoff_amount.
                        row["prev_opening_balance"] = _par_netoff_amt
                        row["prev_loan_date"]       = parent_loan_date
                        row["extra_kisht_entries"]  = []
                    row["new_loan_in_fy"] = True

            illakas_map[il_id]["misals"][m_id]["rows"] = [
                r for r in rows if r["loan_db_id"] not in to_remove_ids
            ]

    result = []
    for il_id in illaka_order:
        il = illakas_map[il_id]
        # Strip internal metadata fields before output
        for m in il["misals"].values():
            for r in m["rows"]:
                for k in ("_is_reloan", "_parent_loan_id", "_netoff_closed", "_reloan_id"):
                    r.pop(k, None)
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
