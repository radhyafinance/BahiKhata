from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone, date as date_type
from typing import Optional
import calendar
import re
import logging
from core.database import db
from core.auth import get_current_user
from helpers import (
    _doc, generate_loan_number, _build_emi_schedule,
    _get_loan_status, _apply_overdue_to_schedule, _add_months, _loan_query_for_user,
    get_admin_maalik_filter_ids, apply_illaka_scope, permitted_illaka_ids,
    create_journal_entry_internal, _get_system_heads, _make_head_line, book_loan_disbursement,
    _import_baseline, _total_paid_with_baseline,
)
from models import LoanCreate, LoanStatusUpdate, PaymentCreate, PaymentEdit, EmiNoteUpdate, ReLoanRequest, YearEndClosingRequest, YearEndUndoRequest

router = APIRouter()


async def _book_emi_collection(loan_doc: dict, payment: dict, user_id: str, user_name: str):
    """Auto-create journal entry on EMI collection.
    MFI rule: Interest is already recognised at disbursement.
    EMI entry is always a plain 2-line: Dr Cash | Cr Loans Portfolio (full amount, no split).
    Gyal loans credit Gyal Wasool instead.
    """
    try:
        is_gyal = loan_doc.get("is_gyal", False)
        amount = float(payment["amount"])
        emi_month = payment.get("emi_month", "")

        if is_gyal:
            gyal_head = await db.account_heads.find_one({"system_key": "gyal_wasool"})
            cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
            if not gyal_head or not cash_head:
                return
            lines = [
                _make_head_line(cash_head, amount, 0.0),
                _make_head_line(gyal_head, 0.0, amount),
            ]
            narration = f"Gyal Wasool from {loan_doc['client_name']} | {emi_month} | Loan# {loan_doc.get('loan_number', '')}"
        else:
            sys_heads = await _get_system_heads()
            if "cash_in_hand" not in sys_heads or "loans_portfolio" not in sys_heads:
                return
            # Plain 2-line: interest was already booked at disbursement
            lines = [
                _make_head_line(sys_heads["cash_in_hand"], amount, 0.0),
                _make_head_line(sys_heads["loans_portfolio"], 0.0, amount),
            ]
            narration = f"EMI collected from {loan_doc['client_name']} | {emi_month} | Loan# {loan_doc.get('loan_number', '')}"

        await create_journal_entry_internal(
            illaka_id=loan_doc["illaka_id"],
            date=payment["payment_date"],
            narration=narration,
            lines=lines, entry_type="emi_collection",
            reference_id=str(loan_doc["_id"]),
            created_by_id=user_id, created_by_name=user_name,
            misal_id=loan_doc.get("misal_id", ""),
            misal_name=loan_doc.get("misal_name", ""),
            client_name=loan_doc.get("client_name", ""),
            loan_number=loan_doc.get("loan_number", ""),
            emi_month=emi_month,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to book EMI collection entry: {e}")


async def _assert_loan_in_scope(current_user: dict, loan: dict) -> None:
    """Refuse to touch a loan outside the caller's illakas.

    Read endpoints have always been scoped, but most WRITE endpoints only
    checked the role — so a muneem could edit, collect against, re-loan or
    delete a loan belonging to a branch it cannot even list, just by knowing or
    guessing the id. Same rule as the sheet applies: admin is unrestricted,
    everyone else is limited to their assigned illakas.
    """
    allowed = await permitted_illaka_ids(current_user)
    if allowed is not None and loan.get("illaka_id") not in allowed:
        raise HTTPException(
            status_code=403, detail="This client is not in your assigned Illaka"
        )


async def _insert_loan(doc: dict, customer_id: str, kyc_id: str, attempts: int = 6):
    """Insert a loan, re-allocating its number if another request took it first.

    loan_number is unique now, so two simultaneous loans for one customer can
    collide on the same generated number. Without a retry that surfaced as a 500.
    """
    for _ in range(attempts):
        try:
            return await db.loans.insert_one(doc)
        except DuplicateKeyError:
            doc["loan_number"] = await generate_loan_number(customer_id, kyc_id)
    raise HTTPException(
        status_code=409,
        detail="Could not allocate a loan number just now — please try again.",
    )


@router.get("/loans")
async def list_loans(
    request: Request,
    illaka_id: Optional[str] = None,
    misal_id: Optional[str] = None,
    kyc_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    maalik_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
):
    current_user = await get_current_user(request)
    query = await _loan_query_for_user(current_user)
    await apply_illaka_scope(current_user, query, illaka_id, maalik_id)
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
    result = await _insert_loan(doc, customer_id, data.kyc_id)
    doc["_id"] = result.inserted_id
    doc["loan_number"] = doc["loan_number"]
    await book_loan_disbursement(doc, current_user["id"], current_user["name"])
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
    if current_user["role"] not in ["admin", "maalik", "muneem", "sadar_muneem"] and loan.get("sipahi_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await _assert_loan_in_scope(current_user, loan)
    old_schedule = loan.get("emi_schedule", [])
    now = datetime.now(timezone.utc).isoformat()

    # Details anyone may correct at any time — they touch no money.
    updates = {
        "client_name": data.client_name,
        "client_phone": data.client_phone,
        "notes": data.notes,
        "updated_at": now,
    }

    terms_changed = (
        float(data.principal_amount) != float(loan.get("principal_amount") or 0)
        or (data.loan_date or "") != (loan.get("loan_date") or "")
    )

    # The schedule is only rebuilt when the terms actually change.
    #
    # It used to be rebuilt on EVERY edit: always exactly twelve rows from the
    # originated-loan formula, carrying paid instalments across BY INDEX. Fixing
    # a spelling mistake on an imported loan therefore truncated a twenty-row
    # schedule to twelve, deleted the collections recorded in rows thirteen
    # onward, overwrote the opening balance with a computed figure, and left the
    # loan marked closed with money still owed. Nothing warned, and the response
    # was a 200.
    if terms_changed:
        paid_rows = [e for e in old_schedule if e.get("status") == "paid"]
        if loan.get("is_import"):
            raise HTTPException(
                status_code=400,
                detail=("This loan was imported with an opening balance, so its terms "
                        "cannot be recalculated. Correct the name, phone or notes here; "
                        "for a wrong balance, delete the loan and re-import it."),
            )
        if paid_rows:
            raise HTTPException(
                status_code=400,
                detail=(f"{len(paid_rows)} instalment(s) have already been collected on this "
                        f"loan, so the amount and date can no longer be changed — rebuilding "
                        f"the schedule would erase them. Delete the collections first, or "
                        f"delete the loan and create it again."),
            )
        if len(old_schedule) > 12:
            raise HTTPException(
                status_code=400,
                detail=("This loan's schedule is longer than twelve instalments and would be "
                        "truncated by a recalculation. Delete and recreate it instead."),
            )

        loan_date_obj = date_type.fromisoformat(data.loan_date)
        emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)
        updates.update({
            "principal_amount": data.principal_amount,
            "emi_amount": emi_amount,
            "total_repayable": emi_amount * 12,
            "interest_amount": (emi_amount * 12) - data.principal_amount,
            "loan_date": data.loan_date,
            "due_date": _add_months(loan_date_obj, 12).isoformat(),
            "emi_schedule": schedule,
            "status": _get_loan_status(schedule),
        })

    await db.loans.update_one({"_id": ObjectId(loan_id)}, {"$set": updates})
    updated = await db.loans.find_one({"_id": ObjectId(loan_id)})

    # Keep the books in step with the loan book. Changing the principal used to
    # leave the original disbursement entry untouched, so Loans Portfolio kept
    # the old figure while the loan carried the new one — a divergence no report
    # would ever surface.
    if terms_changed:
        await db.journal_entries.delete_many(
            {"reference_id": loan_id, "entry_type": "loan_disbursement"}
        )
        await book_loan_disbursement(updated, current_user["id"], current_user["name"])
        updated = await db.loans.find_one({"_id": ObjectId(loan_id)})

    return _doc(updated)


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

    # Only staff assigned to this illaka may collect against it. The sheet
    # already hides other illakas, but the endpoint accepted any loan id.
    allowed = await permitted_illaka_ids(current_user)
    if allowed is not None and doc.get("illaka_id") not in allowed:
        raise HTTPException(status_code=403, detail="This client is not in your assigned Illaka")

    # Back-dating guard. The sheet freezes past months for muneem/sipahi; that
    # was UI-only, so the same request could be replayed against the API.
    # Keyed on the PAYMENT date, not the EMI month, so collecting arrears
    # (an old EMI paid today) stays allowed.
    if current_user["role"] in ("muneem", "sipahi"):
        today = date_type.today()
        this_month = f"{today.year}-{today.month:02d}"
        if (data.payment_date or "")[:7] < this_month:
            raise HTTPException(
                status_code=403,
                detail="Cannot record a collection for a past month / पिछले महीने की एंट्री नहीं कर सकते",
            )
    # Validate the month before it can be written into the schedule. Junk values
    # like "2026-13" or "junkmonth" were accepted, marked paid, and then made the
    # delete path 500 forever — a row nothing could clear.
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", data.emi_month or ""):
        raise HTTPException(status_code=400, detail="emi_month must be in YYYY-MM format")

    schedule = doc.get("emi_schedule", [])
    emi_item = next((e for e in schedule if e["due_month"] == data.emi_month), None)
    if not emi_item:
        if not doc.get("is_gyal"):
            # A client can keep paying after the original schedule runs out — very
            # common for opening-balance imports, whose schedules are only a few
            # months long. As long as money is still owed, accept the collection
            # and extend the schedule with an entry for that month. Without this
            # the sheet offers the row but the save 404s.
            _repayable = float(doc.get("total_repayable") or 0)
            _paid_all = sum(
                float(e.get("paid_amount") or 0)
                for e in schedule if e.get("status") == "paid"
            )
            if round(_repayable - _paid_all, 2) <= 0.01:
                raise HTTPException(
                    status_code=400,
                    detail="This loan is fully repaid / यह क़र्ज़ पूरा चुक गया है",
                )
            new_entry = {
                "month": len(schedule) + 1,
                "due_month": data.emi_month,
                "amount": float(doc.get("emi_amount") or 0),
                "status": "pending",
                "paid_amount": 0.0,
                "paid_date": None,
                "collected_by_id": None,
                "collected_by_name": None,
                "is_extra_entry": True,
            }
        else:
            # Gyal loan — add a synthetic entry for this month so collection can be recorded
            new_entry = {
                "month": len(schedule) + 1,
                "due_month": data.emi_month,
                "amount": 0,
                "status": "pending",
                "paid_amount": 0.0,
                "paid_date": None,
                "collected_by_id": None,
                "collected_by_name": None,
                "is_gyal_entry": True,
            }
        emi_item = new_entry
    else:
        new_entry = None
    if emi_item["status"] == "paid":
        raise HTTPException(status_code=400, detail="This EMI is already paid / यह किस्त पहले से चुकाई जा चुकी है")
    # Fix: use `is not None` so that 0 is treated as a valid explicit amount
    amount = data.amount if data.amount is not None else emi_item["amount"]
    now = datetime.now(timezone.utc).isoformat()
    # ── Zero-entry: record visit only, keep EMI status unchanged, no journal ──
    if amount == 0:
        await db.payments.insert_one({
            "loan_id": loan_id, "emi_month": data.emi_month,
            "amount": 0, "payment_date": data.payment_date,
            "collected_by_id": current_user["id"], "collected_by_name": current_user["name"],
            "notes": data.notes or "Zero collection / visit recorded", "created_at": now,
        })
        updated_loan = await db.loans.find_one({"_id": ObjectId(loan_id)})
        return _doc(updated_loan)

    # ── Normal payment: mark EMI paid and book journal entry ─────────────────
    # This must be ATOMIC. The check above and the write below are separated by
    # awaits, so two collectors saving the same client at the same moment both
    # read "pending", both pass, and both write — inserting two payments and two
    # journal entries for one instalment. The loan's own schedule showed a single
    # payment (last write wins) while the Cash Book showed double the cash, so the
    # two disagreed and the money looked real.
    #
    # Instead of writing the whole schedule back, flip just this EMI with the
    # "not yet paid" condition inside the query. Mongo applies it atomically, so
    # exactly one of the racing requests can match; the loser matches nothing and
    # is rejected the same way a genuine repeat collection is.
    oid = ObjectId(loan_id)
    if new_entry is not None:
        # Appending a month beyond the original schedule races the same way, so
        # guard it on "no entry for this month exists yet". If a concurrent
        # request appended first, its entry is used and this one falls through to
        # the flip below — where exactly one of them will win.
        await db.loans.update_one(
            {"_id": oid, "emi_schedule.due_month": {"$ne": data.emi_month}},
            {"$push": {"emi_schedule": new_entry}},
        )

    claim = await db.loans.update_one(
        {"_id": oid,
         "emi_schedule": {"$elemMatch": {
             "due_month": data.emi_month,
             "status": {"$nin": ["paid", "netoff"]},
         }}},
        {"$set": {
            "emi_schedule.$[e].status": "paid",
            "emi_schedule.$[e].paid_amount": amount,
            "emi_schedule.$[e].paid_date": data.payment_date,
            "emi_schedule.$[e].collected_by_id": current_user["id"],
            "emi_schedule.$[e].collected_by_name": current_user["name"],
            "updated_at": now,
        }},
        # "netoff" is excluded as well as "paid": that instalment was settled by
        # a re-loan, and collecting cash against it books money on a debt that no
        # longer exists.
        array_filters=[{"e.due_month": data.emi_month,
                        "e.status": {"$nin": ["paid", "netoff"]}}],
    )
    if claim.modified_count == 0:
        raise HTTPException(status_code=400, detail="This EMI is already paid / यह किस्त पहले से चुकाई जा चुकी है")

    # Derived totals, recomputed from the authoritative post-claim document.
    claimed = await db.loans.find_one({"_id": oid})
    claimed_schedule = claimed.get("emi_schedule", [])
    # Preserve repayments that predate the schedule.
    #
    # A loan imported with an opening balance carries the money already repaid
    # inside total_paid, with no dated instalment to match. Recomputing from the
    # schedule alone discarded it — so recording one ordinary collection erased
    # that history and pushed the outstanding balance UP, changing what a PAST
    # month's Balance Sheet reported.
    _sched_paid_before = sum(
        float(e.get("paid_amount") or 0) for e in schedule if e.get("status") == "paid"
    )
    _baseline_paid = max(0.0, float(doc.get("total_paid") or 0) - _sched_paid_before)
    total_paid = _baseline_paid + sum(
        float(e.get("paid_amount") or 0) for e in claimed_schedule if e["status"] == "paid"
    )
    new_status = _get_loan_status(claimed_schedule)
    await db.loans.update_one(
        {"_id": oid},
        {"$set": {"total_paid": total_paid, "status": new_status, "updated_at": now}}
    )
    await db.payments.insert_one({
        "loan_id": loan_id, "emi_month": data.emi_month,
        "amount": amount, "payment_date": data.payment_date,
        "collected_by_id": current_user["id"], "collected_by_name": current_user["name"],
        "notes": data.notes, "created_at": now,
    })
    updated_loan = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not updated_loan:
        # The loan was deleted while this collection was in flight. The payment
        # row is already written, so returning _doc(None) crashed with a 500
        # AFTER the money was recorded — leaving an orphan payment nobody could
        # reach. Undo it and say so.
        await db.payments.delete_one({"loan_id": loan_id, "emi_month": data.emi_month,
                                      "created_at": now})
        raise HTTPException(
            status_code=409,
            detail="This loan was deleted while the collection was being saved. Nothing was recorded.",
        )
    payment_record = {"amount": amount, "payment_date": data.payment_date, "emi_month": data.emi_month}
    await _book_emi_collection(updated_loan, payment_record, current_user["id"], current_user["name"])
    return _doc(updated_loan)


@router.delete("/loans/{loan_id}")
async def delete_loan(loan_id: str, request: Request):
    """Permanently delete a loan and all its payments and journal entries. Admin and Maalik only."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can delete loans")
    try:
        oid = ObjectId(loan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan ID")

    loan = await db.loans.find_one({"_id": oid})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, loan)

    await db.payments.delete_many({"loan_id": loan_id})
    await db.journal_entries.delete_many({"reference_id": loan_id})
    await db.loans.delete_one({"_id": oid})

    # Deleting a re-loan has to release the parent it closed.
    #
    # Creating a re-loan with net-off marks the old loan's instalments "netoff",
    # sets status "closed" and netoff_closed, and points reloan_id at the new
    # loan. Deleting the new loan used to leave every one of those in place: the
    # old loan stayed permanently closed against a re-loan that no longer
    # existed, with no endpoint able to reopen it. The only fix was editing the
    # database by hand.
    reopened = None
    parent_id = str(loan.get("parent_loan_id") or "")
    if loan.get("is_reloan") and parent_id:
        try:
            parent = await db.loans.find_one({"_id": ObjectId(parent_id)})
        except Exception:
            parent = None
        # Only release a parent that points back at THIS child. A parent can
        # have more than one re-loan, and deleting an unrelated later one used to
        # reopen a balance the FIRST child had legitimately absorbed —
        # resurrecting a receivable the client had already had rolled over.
        if (parent and parent.get("netoff_closed")
                and str(parent.get("reloan_id") or "") == loan_id):
            schedule = parent.get("emi_schedule", [])
            for emi in schedule:
                if emi.get("status") == "netoff":
                    # "netoff" carries no memory of what the instalment was
                    # before, so reset to pending and let the normal overdue
                    # rule re-derive it from the due month.
                    emi["status"] = "pending"
                    if str(emi.get("note") or "").startswith("Net-off:"):
                        emi["note"] = ""
            _apply_overdue_to_schedule(schedule)
            await db.loans.update_one(
                {"_id": parent["_id"]},
                {"$set": {
                    "emi_schedule": schedule,
                    "status": _get_loan_status(schedule),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                 "$unset": {"netoff_closed": "", "netoff_date": "", "reloan_id": ""}},
            )
            reopened = {
                "loan_id": parent_id,
                "loan_number": parent.get("loan_number"),
                "status": _get_loan_status(schedule),
            }

    return {
        "deleted": True,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "reopened_parent": reopened,
    }


@router.delete("/loans/{loan_id}/payments/{emi_month}")
async def uncollect_emi(loan_id: str, emi_month: str, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")
    doc = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, doc)
    schedule = doc.get("emi_schedule", [])
    _baseline = _import_baseline(doc)   # before any mutation below
    emi_item = next((e for e in schedule if e["due_month"] == emi_month), None)
    if not emi_item:
        raise HTTPException(status_code=404, detail="EMI month not found")

    # Capture paid_date before it gets cleared — needed for journal entry lookup
    old_paid_date = emi_item.get("paid_date") or ""
    now = datetime.now(timezone.utc).isoformat()

    if emi_item.get("is_gyal_entry"):
        # Synthetic Gyal entries: remove row entirely
        schedule = [e for e in schedule if e["due_month"] != emi_month]
        total_paid = _total_paid_with_baseline(_baseline, schedule)
        await db.loans.update_one(
            {"_id": ObjectId(loan_id)},
            {"$set": {"emi_schedule": schedule, "total_paid": total_paid,
                      "status": _get_loan_status(schedule), "updated_at": now}}
        )
    else:
        y, mo = map(int, emi_month.split("-"))
        last_day = calendar.monthrange(y, mo)[1]
        new_emi_status = "overdue" if date_type.today() > date_type(y, mo, last_day) else "pending"
        emi_item.update({
            "status": new_emi_status, "paid_amount": 0.0,
            "paid_date": None, "collected_by_id": None, "collected_by_name": None
        })
        total_paid = _total_paid_with_baseline(_baseline, schedule)
        await db.loans.update_one(
            {"_id": ObjectId(loan_id)},
            {"$set": {"emi_schedule": schedule, "total_paid": total_paid,
                      "status": _get_loan_status(schedule), "updated_at": now}}
        )

    # Delete the payment record
    await db.payments.delete_one({"loan_id": loan_id, "emi_month": emi_month})

    # Delete the journal entry that was created when this EMI was collected
    old_entry = await db.journal_entries.find_one({
        "entry_type": "emi_collection",
        "reference_id": loan_id,
        "emi_month": emi_month,
    })
    if not old_entry and old_paid_date:
        # Fallback for entries created before the emi_month field was added
        old_entry = await db.journal_entries.find_one({
            "entry_type": "emi_collection",
            "reference_id": loan_id,
            "date": old_paid_date,
        })
    if old_entry:
        await db.journal_entries.delete_one({"_id": old_entry["_id"]})

    return {"message": f"EMI for {emi_month} uncollected"}


@router.patch("/loans/{loan_id}/payments/{emi_month}")
async def edit_emi_payment(loan_id: str, emi_month: str, data: PaymentEdit, request: Request):
    """Edit a paid EMI entry: update amount and/or payment date.
    Muneem/Sipahi: current month only.
    Admin/Maalik: any month not locked by year-end closing.
    """
    current_user = await get_current_user(request)
    try:
        oid = ObjectId(loan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan ID")

    today = date_type.today()
    current_ym = f"{today.year}-{today.month:02d}"

    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, doc)

    # Role-based time restriction
    if current_user["role"] in ["muneem", "sipahi"]:
        if emi_month != current_ym:
            raise HTTPException(status_code=403, detail="Muneem/Sipahi can only edit entries for the current month")
    elif current_user["role"] in ["admin", "maalik"]:
        # Block entries locked by year-end closing
        latest_closing = await db.illaka_closings.find_one(
            {"illaka_id": doc["illaka_id"]},
            sort=[("closing_date", -1)]
        )
        if latest_closing:
            closing_ym = latest_closing["closing_date"][:7]
            if emi_month <= closing_ym:
                raise HTTPException(
                    status_code=403,
                    detail=f"This entry is locked by year-end closing ({latest_closing['closing_date']}). Undo the closing first."
                )

    schedule = doc.get("emi_schedule", [])
    _baseline = _import_baseline(doc)   # before any mutation below
    emi_item = next((e for e in schedule if e.get("due_month") == emi_month), None)
    if not emi_item:
        raise HTTPException(status_code=404, detail=f"EMI month {emi_month} not found in schedule")
    if emi_item.get("status") != "paid":
        raise HTTPException(status_code=400, detail="Only paid EMI entries can be edited")

    old_amount = float(emi_item.get("paid_amount") or emi_item.get("amount") or 0)
    old_date = emi_item.get("paid_date") or ""
    new_amount = float(data.amount) if data.amount is not None else old_amount
    new_date = data.payment_date if data.payment_date else old_date

    # Delete the old journal entry for this specific EMI collection
    # Try by explicit emi_month field (stored on newer entries)
    old_entry = await db.journal_entries.find_one({
        "entry_type": "emi_collection",
        "reference_id": loan_id,
        "emi_month": emi_month,
    })
    if not old_entry and old_date:
        # Fallback: match by reference_id + entry_type + old paid_date
        old_entry = await db.journal_entries.find_one({
            "entry_type": "emi_collection",
            "reference_id": loan_id,
            "date": old_date,
        })
    if old_entry:
        await db.journal_entries.delete_one({"_id": old_entry["_id"]})

    # Update EMI schedule
    now = datetime.now(timezone.utc).isoformat()
    emi_item["paid_amount"] = new_amount
    emi_item["paid_date"] = new_date
    emi_item["edited_by_id"] = current_user["id"]
    emi_item["edited_by_name"] = current_user["name"]

    total_paid = _total_paid_with_baseline(_baseline, schedule)
    await db.loans.update_one(
        {"_id": oid},
        {"$set": {"emi_schedule": schedule, "total_paid": total_paid, "updated_at": now}}
    )

    # Update payments record
    await db.payments.update_one(
        {"loan_id": loan_id, "emi_month": emi_month},
        {"$set": {"amount": new_amount, "payment_date": new_date, "updated_at": now}}
    )

    # Book new journal entry with corrected values
    updated_loan = await db.loans.find_one({"_id": oid})
    payment_record = {"amount": new_amount, "payment_date": new_date, "emi_month": emi_month}
    await _book_emi_collection(updated_loan, payment_record, current_user["id"], current_user["name"])

    return _doc(updated_loan)


@router.patch("/loans/{loan_id}/emi-note")
async def update_emi_note(loan_id: str, data: EmiNoteUpdate, request: Request):
    """Add or update a note on a specific EMI."""
    current_user = await get_current_user(request)
    try:
        oid = ObjectId(loan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan ID")
    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, doc)
    # The month must be a real YYYY-MM. Unvalidated input used to create
    # permanent junk rows in the schedule that nothing could clear.
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", data.emi_month or ""):
        raise HTTPException(status_code=400, detail="emi_month must be in YYYY-MM format")

    schedule = doc.get("emi_schedule", [])
    emi_item = next((e for e in schedule if e["due_month"] == data.emi_month), None)
    now = datetime.now(timezone.utc).isoformat()

    if emi_item:
        emi_item["note"] = data.note.strip()
        await db.loans.update_one(
            {"_id": oid}, {"$set": {"emi_schedule": schedule, "updated_at": now}}
        )
    else:
        # No row for this month — extend the schedule rather than refusing.
        #
        # The Vasuli sheet shows a row for every month of the financial year and
        # offers a note field on each, but a loan whose schedule is shorter than
        # that (an opening-balance import, or any month past the original twelve)
        # has no matching entry. Writing a note then failed with "EMI not found
        # in schedule" on a row the sheet had just displayed. Collections already
        # extend the schedule in this situation; notes now do the same.
        this_month = f"{date_type.today().year}-{date_type.today().month:02d}"
        new_entry = {
            "month": len(schedule) + 1,
            "due_month": data.emi_month,
            "amount": float(doc.get("emi_amount") or 0),
            "status": "overdue" if data.emi_month < this_month else "pending",
            "paid_amount": 0.0,
            "paid_date": None,
            "collected_by_id": None,
            "collected_by_name": None,
            "note": data.note.strip(),
            "is_extra_entry": True,
        }
        # Guarded so two simultaneous notes cannot create two rows for one month.
        pushed = await db.loans.update_one(
            {"_id": oid, "emi_schedule.due_month": {"$ne": data.emi_month}},
            {"$push": {"emi_schedule": new_entry}, "$set": {"updated_at": now}},
        )
        if pushed.modified_count == 0:
            # Another request added the row first — write the note onto it.
            await db.loans.update_one(
                {"_id": oid},
                {"$set": {"emi_schedule.$[e].note": data.note.strip(), "updated_at": now}},
                array_filters=[{"e.due_month": data.emi_month}],
            )

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
    await _assert_loan_in_scope(current_user, loan)

    kyc_id = loan.get("kyc_id")
    customer_id = loan.get("customer_id", "—")
    now = datetime.now(timezone.utc).isoformat()

    # ── KYC completeness gate REMOVED — re-loan allowed even for imported/quick-add clients ──
    # (Previously blocked clients without Aadhaar; removed to allow testing and quick re-loans)

    # Calculate outstanding on existing loan
    schedule = loan.get("emi_schedule", [])
    total_repayable = float(loan.get("total_repayable") or ((loan.get("emi_amount") or 0) * 12))
    total_paid = float(loan.get("total_paid") or 0.0)
    outstanding = max(0.0, total_repayable - total_paid)
    netoff_amount = 0.0

    # Net-off: close existing active/overdue loan.
    #
    # The close is claimed atomically. The guard used to read the loan, decide,
    # then write — with awaits in between — so two simultaneous re-loans both saw
    # an open loan and both proceeded: two child loans, the balance netted off
    # twice, and two settlement entries for one debt. That reproduced 20 times
    # out of 20, on one worker and on four.
    #
    # It also gated on `status != "closed"` rather than on netoff_closed, which
    # meant flipping a closed loan back to active through the status endpoint let
    # the same balance be netted off a second time.
    if data.net_off and outstanding > 0:
        for emi in schedule:
            if emi.get("status") != "paid":
                emi["status"] = "netoff"
                emi["note"] = f"Net-off: closed via re-loan on {data.loan_date}"
        claim = await db.loans.update_one(
            {"_id": oid, "netoff_closed": {"$ne": True}, "status": {"$ne": "closed"}},
            {"$set": {
                "emi_schedule": schedule,
                "status": "closed",
                "netoff_closed": True,
                # The DATE THE NET-OFF HAPPENED, not the moment it was typed in.
                # This was the server clock, so a January net-off recorded in
                # September stayed in the portfolio until September and then
                # dropped out in one step with no repayment behind it.
                "netoff_date": data.loan_date,
                "updated_at": now,
            }}
        )
        if claim.modified_count == 0:
            raise HTTPException(
                status_code=409,
                detail=("This loan has already been closed by a net-off. Refresh the "
                        "page — its balance is already carried into a re-loan."),
            )
        netoff_amount = outstanding

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

    result = await _insert_loan(new_loan_doc, customer_id, kyc_id or loan_id)
    new_id = str(result.inserted_id)
    loan_number = new_loan_doc["loan_number"]

    # Back-link old loan to new loan
    await db.loans.update_one({"_id": oid}, {"$set": {"reloan_id": new_id, "updated_at": now}})

    new_loan_doc["_id"] = result.inserted_id
    # Book accounting entry for the re-loan disbursement
    await book_loan_disbursement(new_loan_doc, current_user["id"], current_user["name"])

    # Book the net-off settlement.
    #
    # A net-off clears the old loan's outstanding balance by rolling it into the
    # new one. That is a real settlement and needs its own entry, but none was
    # ever written — only the new disbursement was booked. Two consequences:
    # Loans Portfolio kept carrying a balance that had been cleared, so the asset
    # was overstated by the netted-off amount; and the cash book showed the full
    # new loan going out with no corresponding receipt, when only the difference
    # actually left the drawer.
    #
    # Dr Cash / Cr Loans Portfolio, for the amount rolled over. Combined with the
    # disbursement entry above, cash nets to the difference actually paid out,
    # and the receipt now appears on the Jama side where it belongs.
    #
    # reference_id is the NEW loan, so deleting the re-loan removes this entry
    # along with the disbursement rather than stranding half the transaction.
    if netoff_amount > 0:
        sys_heads = await _get_system_heads()
        if "cash_in_hand" in sys_heads and "loans_portfolio" in sys_heads:
            await create_journal_entry_internal(
                illaka_id=loan.get("illaka_id", ""),
                date=data.loan_date,
                narration=(
                    f"Net-off settlement of {loan.get('loan_number', '')} "
                    f"against re-loan {loan_number} | {loan.get('client_name', '')}"
                ),
                lines=[
                    _make_head_line(sys_heads["cash_in_hand"], netoff_amount, 0.0),
                    _make_head_line(sys_heads["loans_portfolio"], 0.0, netoff_amount),
                ],
                entry_type="netoff_settlement",
                reference_id=new_id,
                settled_loan_id=loan_id,
                created_by_id=current_user["id"],
                created_by_name=current_user["name"],
            )
        else:
            logging.getLogger(__name__).error(
                "Net-off settlement NOT booked for loan %s — cash_in_hand or "
                "loans_portfolio head missing. Books will not balance.", loan_id
            )

    return _doc(new_loan_doc)



@router.get("/loans/year-end-closing/preview")
async def year_end_closing_preview(
    request: Request,
    illaka_id: str,
    closing_date: str,
):
    """Preview how many loans would be marked Gyal for the given illaka & closing date."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can perform year-end closing")
    closing_date_obj = date_type.fromisoformat(closing_date)
    cutoff = _add_months(closing_date_obj, -36)
    query = {
        "illaka_id": illaka_id,
        "status": {"$nin": ["closed"]},
        "is_gyal": {"$ne": True},
        "loan_date": {"$lte": cutoff.isoformat()},
    }
    count = await db.loans.count_documents(query)
    loans = await db.loans.find(query, {
        "client_name": 1, "loan_number": 1, "loan_date": 1,
        "total_repayable": 1, "total_paid": 1
    }).to_list(200)
    rows = []
    for loan_item in loans:
        outstanding = max(0.0, float(loan_item.get("total_repayable") or 0) - float(loan_item.get("total_paid") or 0))
        rows.append({
            "loan_number": loan_item.get("loan_number") or "—",
            "client_name": loan_item.get("client_name") or "—",
            "loan_date": loan_item.get("loan_date") or "—",
            "outstanding": outstanding,
        })
    return {"count": count, "loans": rows, "cutoff_date": cutoff.isoformat()}


@router.post("/loans/year-end-closing")
async def year_end_closing(data: YearEndClosingRequest, request: Request):
    """Mark eligible loans as Gyal and create write-off journal entries. Always records a closing entry."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can perform year-end closing")

    # Check for duplicate closing
    now = datetime.now(timezone.utc).isoformat()
    # Validate the date BEFORE claiming. The claim used to be inserted first and
    # fromisoformat() called after, so a malformed date left a permanent closing
    # row behind: every later attempt got a 409, and because a junk string sorts
    # above real dates it also froze EMI editing for the whole illaka.
    try:
        closing_date_obj = date_type.fromisoformat(data.closing_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="closing_date must be YYYY-MM-DD")

    # Claim this closing BEFORE writing off a single loan.
    #
    # The check used to read here and the closing row was written at the very
    # end, after the whole write-off loop. Two simultaneous requests both found
    # no closing, both ran the loop, and every qualifying loan was written off
    # twice, leaving two closing rows that broke the undo path. Inserting first
    # means the loser stops here, having changed nothing.
    try:
        claim = await db.illaka_closings.insert_one({
            "illaka_id": data.illaka_id,
            "closing_date": data.closing_date,
            "gyal_count": 0,
            "created_by_id": current_user["id"],
            "created_by_name": current_user["name"],
            "created_at": now,
        })
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail=f"A closing for {data.closing_date} already exists for this Illaka.",
        )

    cutoff = _add_months(closing_date_obj, -36)
    query = {
        "illaka_id": data.illaka_id,
        "status": {"$nin": ["closed"]},
        "is_gyal": {"$ne": True},
        "loan_date": {"$lte": cutoff.isoformat()},
    }
    loans_to_gyal = await db.loans.find(query).to_list(None)

    heads = await db.account_heads.find(
        {"system_key": {"$in": ["loans_portfolio", "bad_debt_written_off"]}}
    ).to_list(10)
    head_map = {h["system_key"]: h for h in heads}
    count = 0

    for loan in loans_to_gyal:
        # Claim the loan itself. The unique index only prevents two closings on
        # the SAME date; two closings at DIFFERENT dates ran concurrently, both
        # selected the same loans, and wrote every one of them off twice —
        # doubling Bad Debt and driving Loans Portfolio negative. Marking is_gyal
        # conditionally means the second closing claims nothing.
        marked = await db.loans.update_one(
            {"_id": loan["_id"], "is_gyal": {"$ne": True}},
            {"$set": {"is_gyal": True, "gyal_since": data.closing_date, "updated_at": now}}
        )
        if marked.modified_count == 0:
            continue
        if "loans_portfolio" in head_map and "bad_debt_written_off" in head_map:
            outstanding = max(0.0, float(loan.get("total_repayable") or 0) - float(loan.get("total_paid") or 0))
            if outstanding > 0:
                lines = [
                    _make_head_line(head_map["bad_debt_written_off"], outstanding, 0.0),
                    _make_head_line(head_map["loans_portfolio"], 0.0, outstanding),
                ]
                await create_journal_entry_internal(
                    illaka_id=data.illaka_id,
                    date=data.closing_date,
                    narration=f"Gyal Write-off: {loan.get('client_name', '')} | Loan# {loan.get('loan_number', '')}",
                    lines=lines,
                    entry_type="gyal_writeoff",
                    reference_id=str(loan["_id"]),
                    created_by_id=current_user["id"],
                    created_by_name=current_user["name"],
                )
        count += 1

    # Record the final Gyal count on the row claimed above.
    await db.illaka_closings.update_one({"_id": claim.inserted_id}, {"$set": {"gyal_count": count}})

    msg = f"{count} loan(s) marked as Gyal (Bad Debt)" if count > 0 else "Year-end closing recorded. No loans qualified for Gyal."
    return {"marked_count": count, "message": msg}


@router.get("/loans/year-end-closing/history")
async def year_end_closing_history(request: Request, illaka_id: str):
    """Return all year-end closing records for an illaka, newest first."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can view closing history")
    closing_docs = await db.illaka_closings.find(
        {"illaka_id": illaka_id},
        {"_id": 0}
    ).sort("closing_date", -1).to_list(200)
    closings = [{"closing_date": c["closing_date"], "count": c.get("gyal_count", 0)} for c in closing_docs]
    return {"closings": closings}


@router.post("/loans/year-end-closing/undo")
async def year_end_closing_undo(data: YearEndUndoRequest, request: Request):
    """Undo a year-end closing — only allowed if it is the most recent closing for the illaka."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can undo year-end closing")

    # Verify this closing exists in illaka_closings
    closing_record = await db.illaka_closings.find_one(
        {"illaka_id": data.illaka_id, "closing_date": data.closing_date}
    )
    if not closing_record:
        raise HTTPException(status_code=404, detail="No closing record found for the specified date")

    # Block if a newer closing exists
    newer = await db.illaka_closings.find_one({
        "illaka_id": data.illaka_id,
        "closing_date": {"$gt": data.closing_date},
    })
    if newer:
        raise HTTPException(
            status_code=400,
            detail="Cannot undo: a more recent year-end closing exists for this illaka. Undo that first.",
        )

    # Undo Gyal loans that were marked on this closing date
    loans_to_undo = await db.loans.find(
        {"illaka_id": data.illaka_id, "is_gyal": True, "gyal_since": data.closing_date}
    ).to_list(None)
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for loan in loans_to_undo:
        loan_id_str = str(loan["_id"])
        await db.loans.update_one(
            {"_id": loan["_id"]},
            {"$set": {"is_gyal": False, "updated_at": now}, "$unset": {"gyal_since": ""}},
        )
        await db.journal_entries.delete_many({
            "entry_type": "gyal_writeoff",
            "reference_id": loan_id_str,
            "illaka_id": data.illaka_id,
        })
        count += 1

    # Delete the closing record
    await db.illaka_closings.delete_one(
        {"illaka_id": data.illaka_id, "closing_date": data.closing_date}
    )

    msg = f"{count} loan(s) restored from Gyal. Closing record removed." if count > 0 else "Year-end closing record removed (no Gyal loans to undo)."
    return {"undone_count": count, "message": msg}
