from fastapi import APIRouter, Request
from typing import Optional
from datetime import date as date_type
from bson import ObjectId
from core.database import db
from core.auth import get_current_user
from helpers import _loan_query_for_user, get_admin_maalik_filter_ids

router = APIRouter()


# ─── Pure helper functions ─────────────────────────────────────────────────────

def _compute_fy_months(month: str) -> list:
    """Return the 12 YYYY-MM strings for the financial year (Apr→Mar) containing `month`."""
    year_n, mo_n = map(int, month.split("-"))
    fy_start_year = year_n if mo_n >= 4 else year_n - 1
    months = []
    for i in range(12):
        fm = ((3 + i) % 12) + 1
        fy_y = fy_start_year if fm >= 4 else fy_start_year + 1
        months.append(f"{fy_y}-{fm:02d}")
    return months


def _compute_fy_balances(schedule: list, fy_months: list, total_repayable: float) -> tuple:
    """
    Returns (outstanding_balance, opening_balance) relative to the selected FY.

    outstanding = balance at the END of the FY (payments up to fy_months[-1] only).
                  Ensures Bal column reflects the FY-end state, not the all-time total.
    opening     = balance at the START of the FY (payments strictly before fy_months[0]).
                  Used for पिछली बाक़ी (previous outstanding) column.
    """
    paid_through_fy_end = sum(
        float(e.get("paid_amount") or 0)
        for e in schedule
        if e.get("status") == "paid" and (e.get("due_month") or "") <= fy_months[-1]
    )
    paid_before_fy = sum(
        float(e.get("paid_amount") or 0)
        for e in schedule
        if e.get("status") == "paid" and (e.get("due_month") or "") < fy_months[0]
    )
    return (
        max(0.0, total_repayable - paid_through_fy_end),
        max(0.0, total_repayable - paid_before_fy),
    )


def _build_emi_year_strip(
    schedule: list, fy_months: list, is_gyal: bool, gyal_year_data: dict
) -> list:
    """Build the 12-entry list (one per FY month) for the horizontal FY strip.

    For non-gyal loans the priority is:
    1. If any EMI was physically COLLECTED in this month (paid_date[:7] == fy_m),
       show it as paid — this handles old overdue loans whose due_month is in a
       past FY but whose payment was received in the current FY.
    2. Fall back to the scheduled due_month match (pending / overdue / etc.).
    3. If nothing matches → "na".
    """
    result = []
    for fy_m in fy_months:
        sched_item = next(
            (e for e in schedule if e.get("due_month") == fy_m and not e.get("is_gyal_entry")),
            None,
        )
        if is_gyal:
            gyal_pmt = gyal_year_data.get(fy_m)
            if gyal_pmt:
                result.append({"month": fy_m, "status": "paid",
                                "paid_amount": float(gyal_pmt.get("amount") or 0), "note": ""})
            elif sched_item:
                result.append({"month": fy_m, "status": sched_item.get("status", "pending"),
                                "paid_amount": float(sched_item.get("paid_amount") or 0),
                                "note": sched_item.get("note") or ""})
            else:
                result.append({"month": fy_m, "status": "na", "paid_amount": 0.0, "note": ""})
        else:
            # Priority 1: EMI physically collected in this FY month (paid_date[:7] == fy_m).
            # This shows the payment in the column matching WHEN MONEY WAS RECEIVED —
            # regardless of which due_month it was for.
            paid_this_month = next(
                (e for e in schedule
                 if e.get("status") == "paid"
                 and (e.get("paid_date") or "")[:7] == fy_m
                 and not e.get("is_gyal_entry")),
                None,
            )
            if paid_this_month:
                result.append({
                    "month": fy_m,
                    "status": "paid",
                    "paid_amount": float(paid_this_month.get("paid_amount") or 0),
                    "note": paid_this_month.get("note") or "",
                })
            elif sched_item:
                # Priority 2: scheduled EMI for this month.
                # If this EMI is paid but its paid_date falls in a DIFFERENT month
                # within this FY, it is already shown there via Priority 1 above.
                # Suppress it here so the entry appears in exactly one column.
                paid_m = (sched_item.get("paid_date") or "")[:7]
                if (sched_item.get("status") == "paid"
                        and paid_m in fy_months
                        and paid_m != fy_m):
                    result.append({"month": fy_m, "status": "na", "paid_amount": 0.0, "note": ""})
                else:
                    result.append({
                        "month": fy_m,
                        "status": sched_item.get("status", "pending"),
                        "paid_amount": float(sched_item.get("paid_amount") or 0),
                        "note": sched_item.get("note") or "",
                    })
            else:
                result.append({"month": fy_m, "status": "na", "paid_amount": 0.0, "note": ""})
    return result


def _merge_netoff_rows(rows: list, all_loans_by_id: dict, fy_months: list) -> list:
    """
    Merge net-off re-loan pairs into a single combined row per misal.

    For each re-loan (L2) whose parent (L1) was netoff-closed:
    - L2 is kept as the primary row (the Collect button targets it).
    - L1's FY strip fills months where L2 has "na" data — parent "netoff"-status
      entries are skipped so the ↩ symbol doesn't bleed into the wrong month.
    - A "chain_start" marker is injected at L2's disbursement month (correct ↩ position).
    - L1 is removed from the rows list.

    For deeper chains (L1→L2→L3):
    - Root पिछली बाक़ी data (opening balance at FY start + loan date) is threaded through
      successive merges via prev_opening_balance / prev_loan_date.
    - extra_kisht_entries accumulates all intermediate re-loans for किस्त हाल display.
    - older_emi_chain accumulates ancestor EMI amounts for the stacked EMI column.

    Returns the filtered rows list (all absorbed parent rows removed).
    """
    row_by_loan_id = {r["loan_db_id"]: r for r in rows}
    to_remove_ids: set = set()

    for row in rows:
        if not row.get("_is_reloan") or not row.get("_parent_loan_id"):
            continue
        parent_id = row["_parent_loan_id"]
        parent_row = row_by_loan_id.get(parent_id)

        # ── Case A: parent appears as a row in this FY ───────────────────────
        if parent_row and parent_row.get("_netoff_closed"):
            parent_strip = {e["month"]: e for e in parent_row["emi_year_data"]}
            parent_opening = float(parent_row.get("opening_balance") or 0)
            parent_loan_date = parent_row.get("loan_date") or ""
            parent_emi_amount = float(parent_row.get("emi_amount") or 0)
            to_remove_ids.add(parent_id)

        # ── Case B: parent is netoff-closed but not in this FY's rows ────────
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
            parent_strip = {}
            for ym in fy_months:
                yd = next((e for e in parent_sched if e.get("due_month") == ym), None)
                if yd:
                    parent_strip[ym] = {
                        "month": ym, "status": yd["status"],
                        "paid_amount": float(yd.get("paid_amount") or 0),
                        "note": yd.get("note", ""),
                    }
        else:
            continue

        # ── Merge FY strips ───────────────────────────────────────────────────
        # L2 takes priority for non-na months.
        # Parent "netoff" entries are skipped — they mark the old loan closing and
        # must not place the ↩ symbol before L2's actual start month.
        merged_strip = []
        for entry in row["emi_year_data"]:
            if entry["status"] != "na":
                merged_strip.append(entry)
            elif (entry["month"] in parent_strip
                  and parent_strip[entry["month"]]["status"] not in ("na", "netoff")):
                merged_strip.append(parent_strip[entry["month"]])
            else:
                merged_strip.append(entry)

        # Inject "chain_start" at L2's disbursement month (shows ↩ at the right spot).
        # "chain_start" is NOT skipped in further merges, unlike "netoff".
        row_start_ym = (row.get("loan_date") or "")[:7]
        row["emi_year_data"] = [
            {"month": e["month"], "status": "chain_start", "paid_amount": 0.0, "note": ""}
            if (e["month"] == row_start_ym and e["status"] == "na")
            else e
            for e in merged_strip
        ]

        row["is_netoff_combined"] = True
        row["prev_emi_amount"] = parent_emi_amount

        # ── पिछली बाक़ी and किस्त हाल chain metadata ─────────────────────────
        if parent_row:  # Case A: parent is a processed row
            _par_combined  = parent_row.get("is_netoff_combined", False)
            _par_repayable = float(parent_row.get("total_repayable") or 0)
            _par_date      = parent_row.get("loan_date", "")
            _par_extra     = list(parent_row.get("extra_kisht_entries") or [])
            _par_root_bal  = float(parent_row.get("prev_opening_balance") or 0)
            _par_root_date = parent_row.get("prev_loan_date", "")
            _par_prev_emi  = float(parent_row.get("prev_emi_amount") or 0)
            _par_older_emi = list(parent_row.get("older_emi_chain") or [])
        else:           # Case B: parent from raw loans dict
            _par_combined  = False
            _par_repayable = 0.0
            _par_date      = ""
            _par_extra     = []
            _par_root_bal  = 0.0
            _par_root_date = ""
            _par_prev_emi  = 0.0
            _par_older_emi = []

        row_loan_ym = (row.get("loan_date") or "")[:7]
        l2_before_fy = bool(row_loan_ym) and row_loan_ym < fy_months[0]

        if l2_before_fy:
            # Re-loan started BEFORE this FY.
            # पिछली बाक़ी = this loan's own opening balance at FY start + its loan date.
            row["prev_opening_balance"] = row.get("opening_balance", 0.0)
            row["prev_loan_date"]       = row.get("loan_date", "")
            row["new_loan_in_fy"]       = False
            row["extra_kisht_entries"]  = []
            row["older_emi_chain"]      = []
        else:
            # Re-loan disbursed IN this FY.
            # पिछली बाक़ी = root original loan's FY-start opening balance (= prev FY closing).
            # किस्त हाल = all chain re-loans oldest-first, then current row.
            if _par_combined:
                # Thread root data from already-combined parent (handles 3+ level chains).
                row["prev_opening_balance"] = _par_root_bal
                row["prev_loan_date"]       = _par_root_date
                row["extra_kisht_entries"]  = _par_extra + [
                    {"amount": _par_repayable, "loan_date": _par_date}
                ]
                row["older_emi_chain"] = _par_older_emi + (
                    [_par_prev_emi] if _par_prev_emi > 0 else []
                )
            else:
                # Direct original parent: use its FY-start opening balance.
                row["prev_opening_balance"] = parent_opening
                row["prev_loan_date"]       = parent_loan_date
                row["extra_kisht_entries"]  = []
                row["older_emi_chain"]      = []
            row["new_loan_in_fy"] = True

    return [r for r in rows if r["loan_db_id"] not in to_remove_ids]


# ─── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/collections/sheet")
async def get_collection_sheet(
    request: Request,
    month: Optional[str] = None,
    illaka_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
):
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    fy_months = _compute_fy_months(month)

    query = await _loan_query_for_user(current_user)
    # No status filter — closed loans must stay visible until their FY schedule ends.
    if illaka_id:
        query["illaka_id"] = illaka_id
    elif maalik_id and current_user["role"] == "admin":
        ids = await get_admin_maalik_filter_ids(maalik_id)
        query["illaka_id"] = {"$in": ids}

    loans = await db.loans.find(query).sort(
        [("illaka_id", 1), ("misal_id", 1), ("loan_date", 1)]
    ).to_list(5000)

    # ── Bulk lookups ──────────────────────────────────────────────────────────
    unique_illaka_ids = list({ln.get("illaka_id") for ln in loans if ln.get("illaka_id")})
    unique_misal_ids  = list({ln.get("misal_id")  for ln in loans if ln.get("misal_id")})
    illaka_name_map: dict = {}
    misal_name_map: dict  = {}
    misal_display_order_map: dict = {}
    if unique_illaka_ids:
        try:
            raw = await db.illakas.find(
                {"_id": {"$in": [ObjectId(i) for i in unique_illaka_ids]}}, {"name": 1}
            ).to_list(500)
            illaka_name_map = {str(d["_id"]): d["name"] for d in raw}
        except Exception:
            pass
    if unique_misal_ids:
        try:
            raw = await db.misals.find(
                {"_id": {"$in": [ObjectId(i) for i in unique_misal_ids]}}, {"name": 1, "display_order": 1}
            ).to_list(500)
            misal_name_map = {str(d["_id"]): d["name"] for d in raw}
            misal_display_order_map = {str(d["_id"]): d.get("display_order") for d in raw}
        except Exception:
            pass

    kyc_ids = [ln.get("kyc_id") for ln in loans if ln.get("kyc_id")]
    valid_kyc_oids = []
    for kid in kyc_ids:
        try:
            valid_kyc_oids.append(ObjectId(kid))
        except Exception:
            pass
    kyc_map: dict = {}
    if valid_kyc_oids:
        raw_kycs = await db.kycs.find(
            {"_id": {"$in": valid_kyc_oids}},
            {"_id": 1, "primary_borrower.relative_name": 1, "primary_borrower.relative_name_hindi": 1,
             "guarantor.name": 1, "guarantor.name_hindi": 1, "customer_id": 1},
        ).to_list(5000)
        kyc_map = {str(k["_id"]): k for k in raw_kycs}

    gyal_loan_ids = [str(ln["_id"]) for ln in loans if ln.get("is_gyal")]
    gyal_payment_map: dict = {}   # loan_id → current-month payment
    gyal_year_map: dict    = {}   # loan_id → {emi_month → payment}
    if gyal_loan_ids:
        gyal_pmts = await db.payments.find(
            {"loan_id": {"$in": gyal_loan_ids}, "emi_month": {"$in": fy_months}}
        ).to_list(5000)
        for p in gyal_pmts:
            lid = p["loan_id"]
            gyal_year_map.setdefault(lid, {})[p["emi_month"]] = p
        for lid, months_data in gyal_year_map.items():
            if month in months_data:
                gyal_payment_map[lid] = months_data[month]

    # ── Build rows grouped by illaka → misal ─────────────────────────────────
    illakas_map: dict = {}
    illaka_order: list = []
    misal_order: dict  = {}

    for loan in loans:
        schedule    = loan.get("emi_schedule", [])
        loan_id_str = str(loan["_id"])
        emi = next((e for e in schedule if e.get("due_month") == month), None)

        # Gyal loans always appear on the sheet regardless of selected month.
        if not emi or emi.get("is_gyal_entry"):
            if loan.get("is_gyal"):
                gyal_pmt = gyal_payment_map.get(loan_id_str)
                preserved_note = emi.get("note", "") if emi else ""
                emi = {
                    "due_month": month,
                    "amount": gyal_pmt["amount"] if gyal_pmt else 0,
                    "status": "paid" if gyal_pmt else "pending",
                    "note": preserved_note,
                    "paid_amount": gyal_pmt["amount"] if gyal_pmt else 0,
                    "paid_date": gyal_pmt.get("payment_date", "") if gyal_pmt else "",
                }
            elif not emi:
                # Non-gyal loan with no EMI for the selected month.
                # Keep if the loan existed during this FY OR had a payment collected in this FY.
                loan_has_fy_emi      = any(e.get("due_month") in fy_months for e in schedule)
                loan_date_ym         = (loan.get("loan_date") or "")[:7]
                loan_disbursed_in_fy = loan_date_ym in fy_months
                loan_existed_by_fy_end = bool(loan_date_ym) and loan_date_ym <= fy_months[-1]
                loan_has_outstanding   = loan.get("status") in ("active", "overdue")
                # Include also when a payment was physically received during this FY
                loan_has_fy_payment  = any(
                    (e.get("paid_date") or "")[:7] in fy_months
                    for e in schedule
                    if e.get("status") == "paid"
                )
                if not (loan_has_fy_emi or loan_disbursed_in_fy
                        or (loan_has_outstanding and loan_existed_by_fy_end)
                        or loan_has_fy_payment):
                    continue
                if not schedule:
                    continue
                rep_emi = schedule[0] if (loan_disbursed_in_fy and not loan_has_fy_emi) else schedule[-1]
                emi = {
                    "due_month":    rep_emi.get("due_month", month),
                    "amount":       rep_emi.get("amount", 0),
                    "status":       rep_emi.get("status", "pending"),
                    "note":         rep_emi.get("note", ""),
                    "paid_amount":  float(rep_emi.get("paid_amount") or 0),
                    "paid_date":    rep_emi.get("paid_date", ""),
                }

        loan_illaka_id = loan.get("illaka_id", "unknown")
        misal_id       = loan.get("misal_id", "unknown")
        illaka_name    = illaka_name_map.get(loan_illaka_id) or loan.get("illaka_name", "Unknown Illaka")
        misal_name     = misal_name_map.get(misal_id)        or loan.get("misal_name",  "Unknown Misal")
        kyc            = kyc_map.get(loan.get("kyc_id", ""), {})
        total_repayable = float(loan.get("total_repayable") or (loan.get("emi_amount") or 0) * 12)
        outstanding, opening_balance = _compute_fy_balances(schedule, fy_months, total_repayable)

        row = {
            "loan_db_id":           loan_id_str,
            "loan_number":          loan.get("loan_number") or "—",
            "customer_id":          loan.get("customer_id") or kyc.get("customer_id") or "—",
            "client_name":          loan.get("client_name") or "",
            "client_name_hindi":    loan.get("client_name_hindi") or "",
            "relative_name":        (kyc.get("primary_borrower") or {}).get("relative_name") or "",
            "relative_name_hindi":  (kyc.get("primary_borrower") or {}).get("relative_name_hindi") or "",
            "guarantor_name":       (kyc.get("guarantor") or {}).get("name") or "",
            "guarantor_name_hindi": (kyc.get("guarantor") or {}).get("name_hindi") or "",
            "emi_amount":           emi.get("amount", 0),
            "emi_month":            emi.get("due_month", month),
            "emi_status":           emi.get("status", "pending"),
            "emi_note":             emi.get("note") or "",
            "emi_paid_amount":      float(emi.get("paid_amount") or 0) if emi.get("status") == "paid" else 0,
            "emi_paid_date":        emi.get("paid_date") or "",
            "outstanding_balance":  outstanding,
            "opening_balance":      opening_balance,
            "loan_date":            loan.get("loan_date") or "",
            "total_repayable":      total_repayable,
            "netoff_amount":        float(loan.get("netoff_amount") or 0),
            "is_gyal":              loan.get("is_gyal", False),
            "gyal_since":           loan.get("gyal_since") or "",
            "emi_year_data":        _build_emi_year_strip(
                                        schedule, fy_months,
                                        loan.get("is_gyal", False),
                                        gyal_year_map.get(loan_id_str, {}),
                                    ),
            # Internal metadata for net-off merge pass (stripped before output)
            "_is_reloan":           loan.get("is_reloan", False),
            "_parent_loan_id":      str(loan.get("parent_loan_id") or ""),
            "_netoff_closed":       loan.get("netoff_closed", False),
            "_reloan_id":           str(loan.get("reloan_id") or ""),
            # Import ordering
            "display_order":        loan.get("display_order"),
            # Combined-row fields (populated by _merge_netoff_rows)
            "is_netoff_combined":   False,
            "prev_opening_balance": 0.0,
            "new_loan_in_fy":       False,
            "older_emi_chain":      [],
            "extra_kisht_entries":  [],
        }

        if loan_illaka_id not in illakas_map:
            illakas_map[loan_illaka_id] = {
                "illaka_id": loan_illaka_id, "illaka_name": illaka_name, "misals": {}
            }
            illaka_order.append(loan_illaka_id)
            misal_order[loan_illaka_id] = []
        if misal_id not in illakas_map[loan_illaka_id]["misals"]:
            illakas_map[loan_illaka_id]["misals"][misal_id] = {
                "misal_id": misal_id, "misal_name": misal_name, "rows": []
            }
            misal_order[loan_illaka_id].append(misal_id)
        illakas_map[loan_illaka_id]["misals"][misal_id]["rows"].append(row)

    # ── Net-off merge pass ────────────────────────────────────────────────────
    all_loans_by_id = {str(ln["_id"]): ln for ln in loans}
    for il_id in illaka_order:
        for m_id in misal_order[il_id]:
            misal = illakas_map[il_id]["misals"][m_id]
            misal["rows"] = _merge_netoff_rows(misal["rows"], all_loans_by_id, fy_months)

    # ── Re-sort rows: display_order (import order) first, then loan_date ────────
    # Combined net-off rows use prev_loan_date as sort key when no display_order.
    def _row_sort_key(r: dict) -> tuple:
        do = r.get("display_order")
        if do is not None:
            return (0, do, "")
        if r.get("is_netoff_combined") and r.get("prev_loan_date"):
            return (1, 0, r["prev_loan_date"])
        return (1, 0, r.get("loan_date") or "")

    for il_id in illaka_order:
        for m_id in misal_order[il_id]:
            illakas_map[il_id]["misals"][m_id]["rows"].sort(key=_row_sort_key)

    # ── Sort misals by display_order (import order), then by name ────────────
    for il_id in illaka_order:
        misal_order[il_id].sort(key=lambda m_id: (
            misal_display_order_map.get(m_id) if misal_display_order_map.get(m_id) is not None else float("inf"),
            misal_name_map.get(m_id, ""),
        ))

    # ── Assemble output ───────────────────────────────────────────────────────
    result = []
    for il_id in illaka_order:
        il = illakas_map[il_id]
        for m in il["misals"].values():
            for r in m["rows"]:
                for k in ("_is_reloan", "_parent_loan_id", "_netoff_closed", "_reloan_id"):
                    r.pop(k, None)
        result.append({
            "illaka_id":   il["illaka_id"],
            "illaka_name": il["illaka_name"],
            "misals":      [il["misals"][m_id] for m_id in misal_order[il_id]],
        })

    # Attach latest year-end closing per illaka (edit permission checks)
    result_illaka_ids = [il["illaka_id"] for il in result]
    latest_closings: dict = {}
    if result_illaka_ids:
        closing_docs = await db.illaka_closings.find(
            {"illaka_id": {"$in": result_illaka_ids}},
            {"illaka_id": 1, "closing_date": 1},
        ).to_list(5000)
        for cd in closing_docs:
            il_id = cd.get("illaka_id", "")
            gs    = cd.get("closing_date", "")
            if gs and (il_id not in latest_closings or gs > latest_closings[il_id]):
                latest_closings[il_id] = gs
    for il in result:
        closing = latest_closings.get(il["illaka_id"], "")
        il["latest_closing_ym"] = closing[:7] if closing else ""

    total_rows = sum(len(m["rows"]) for il in result for m in il["misals"])
    collected  = sum(
        1 for il in result for m in il["misals"] for r in m["rows"] if r["emi_status"] == "paid"
    )
    return {"month": month, "total": total_rows, "collected": collected, "illakas": result}


# ─── Monthly Summary (lightweight — for dashboard) ──────────────────────────
@router.get("/collections/monthly-summary")
async def monthly_summary(request: Request, illaka_id: str, month: str):
    """Misal-wise Utaar (due) + Vayda (collected) + client count for the dashboard."""
    await get_current_user(request)
    from datetime import datetime
    # Validate month format
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    loans = await db.loans.find(
        {"illaka_id": illaka_id, "status": {"$in": ["active", "overdue"]}},
        {"misal_id": 1, "misal_name": 1, "emi_amount": 1, "emi_schedule": 1}
    ).to_list(None)

    misal_map = {}
    for loan in loans:
        mid   = loan.get("misal_id", "")
        mname = loan.get("misal_name", "Unknown")
        if mid not in misal_map:
            misal_map[mid] = {"misal_id": mid, "misal_name": mname, "utaar": 0.0, "vayda": 0.0, "clients": 0, "clients_paid": 0}
        entry = next((e for e in loan.get("emi_schedule", []) if e.get("due_month") == month), None)
        if not entry:
            continue
        misal_map[mid]["clients"] += 1
        misal_map[mid]["utaar"]   += float(loan.get("emi_amount") or 0)
        if entry.get("status") == "paid":
            misal_map[mid]["vayda"] += float(entry.get("paid_amount") or loan.get("emi_amount") or 0)
            misal_map[mid]["clients_paid"] += 1

    misals = sorted(misal_map.values(), key=lambda m: m["misal_name"])
    total  = {
        "utaar":        sum(m["utaar"]        for m in misals),
        "vayda":        sum(m["vayda"]        for m in misals),
        "clients":      sum(m["clients"]      for m in misals),
        "clients_paid": sum(m["clients_paid"] for m in misals),
    }
    return {"month": month, "misals": misals, "total": total}

