from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from pymongo.errors import DuplicateKeyError
from datetime import datetime, timezone, timedelta, date as date_type
from typing import Optional
import calendar
import re
import contextlib
import logging
from core.database import db
from core.auth import get_current_user
from helpers import (
    _doc, generate_loan_number, _build_emi_schedule,
    _get_loan_status, _apply_overdue_to_schedule, _add_months, _loan_query_for_user,
    get_admin_maalik_filter_ids, apply_illaka_scope, permitted_illaka_ids,
    create_journal_entry_internal, _get_system_heads, _make_head_line, book_loan_disbursement,
    _import_baseline, _total_paid_with_baseline, is_valid_month,
    loan_lock, kyc_lock, entity_lock, prepare_loan_people, assert_people_not_gyal,
    assert_client_not_gyal, validate_phone, clean_person, person_is_gyal_linked,
    assert_open_period, latest_closing_date, loan_status, valid_date, OWED_TOLERANCE, _day,
    assert_no_old_debt, client_loans, paid_so_far,
)
from models import LoanCreate, LoanStatusUpdate, PaymentCreate, PaymentEdit, EmiNoteUpdate, ReLoanRequest, YearEndClosingRequest, YearEndUndoRequest

router = APIRouter()

BUSY_ILLAKA = ("A year-end closing or undo is already running for this Illaka. Please try again "
               "in a moment. / इस इलाके का साल-अंत समापन अभी चल रहा है।")


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


async def _abort_if_loan_gone(
    oid: ObjectId,
    loan_id: str,
    detail: str = "This loan was deleted while the change was being saved. Nothing was recorded.",
) -> None:
    """If the loan no longer exists, remove every payment and entry of it, then 409.

    A write that books money — a collection, a payment edit, a write-off — can
    land after a concurrent delete has already swept the loan's records. Once
    the loan row is gone nothing of it may survive, so rather than trying to
    undo exactly what this request wrote, everything keyed to the loan goes.
    Called after the last write, not only before it: the write itself is what a
    delete can slip in front of.
    """
    if await db.loans.find_one({"_id": oid}, {"_id": 1}):
        return
    await db.payments.delete_many({"loan_id": loan_id})
    await db.journal_entries.delete_many({"reference_id": loan_id})
    raise HTTPException(status_code=409, detail=detail)


def _loan_ref(loan_id: str) -> tuple:
    """(ObjectId, canonical id string) for a loan id taken from a URL, or 400.

    Mongo accepts an ObjectId in upper or lower case, but the id text was also
    stored and compared as typed: a collection through an upper-cased URL wrote
    payments.loan_id in upper case, a re-loan wrote parent_loan_id in upper
    case, and a delete through one swept nothing because its clean-up matched
    the typed text. Every write now uses the canonical form. An id that is not
    an ObjectId at all was a 500; it is a 400.
    """
    try:
        oid = ObjectId(str(loan_id).strip())
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid loan ID")
    return oid, str(oid)


def _id_ci(loan_id: str) -> dict:
    """Match an id field case-insensitively — for records written by older code."""
    return {"$regex": f"^\\s*{re.escape(loan_id)}\\s*$", "$options": "i"}


async def _release_netoff_parent(parent_oid: ObjectId, child_id: str):
    """Reopen a loan that was closed by a net-off into `child_id`.

    Must be called while holding the parent's loan lock. Each netoff instalment
    goes back to pending (overdue once its month has ended), and the note the
    user had on it before the net-off is put back — the net-off used to
    overwrite it with "Net-off: ...", and the release then blanked it for good.
    Returns the parent's new status, or None if there was nothing to release.
    """
    parent = await db.loans.find_one({"_id": parent_oid})
    if not parent or not parent.get("netoff_closed") or str(parent.get("reloan_id") or "") != child_id:
        return None
    today = date_type.today()
    this_month = f"{today.year}-{today.month:02d}"
    now_iso = datetime.now(timezone.utc).isoformat()
    schedule = parent.get("emi_schedule", [])
    sets, unsets = {"updated_at": now_iso}, {"netoff_closed": "", "netoff_date": "", "reloan_id": ""}
    for i, row in enumerate(schedule):
        if row.get("status") != "netoff":
            continue
        status = "overdue" if (row.get("due_month") or "") < this_month else "pending"
        sets[f"emi_schedule.{i}.status"] = status
        sets[f"emi_schedule.{i}.note"] = row.get("pre_netoff_note") or ""
        unsets[f"emi_schedule.{i}.pre_netoff_note"] = ""
        row["status"] = status
    sets["status"] = _get_loan_status(schedule, parent.get("total_paid") or 0, parent.get("total_repayable"))
    await db.loans.update_one({"_id": parent_oid, "reloan_id": child_id},
                              {"$set": sets, "$unset": unsets})
    return sets["status"]


def _gyal_outstanding(loan: dict) -> float:
    return round(float(loan.get("total_repayable") or 0) - paid_so_far(loan), 2)


def _normalise_closing_date(value: str) -> str:
    """A closing date as YYYY-MM-DD, or 400.

    fromisoformat() also accepts "20260331", which was stored as typed: it
    compared as a different string from "2026-03-31", so the same day could be
    closed twice and the newer-closing check that guards undo could be
    bypassed.
    """
    try:
        return date_type.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise HTTPException(status_code=400, detail="closing_date must be YYYY-MM-DD")


def _positive_amount(value, label: str) -> float:
    """Money lent must be more than zero. Negative principals were accepted and
    stored a negative total_repayable."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0
    if not amount > 0:
        raise HTTPException(status_code=400, detail=f"{label} must be more than zero")
    return amount


def _typed_phone(value, stored, label: str) -> str:
    """A phone sent with a loan or re-loan, if it differs from the one on file.

    The loan screens send the client's phone back pre-filled. An older client
    whose phone predates format checks ("98234 (wife)", two numbers) could then
    never be lent to or re-loaned, though nobody had touched the number. Only a
    number that was actually changed is validated — and it is then added to the
    borrower's identity, not substituted for it.
    """
    if str(value or "").strip() == str(stored or "").strip():
        return ""
    return validate_phone(value, label)


async def _assert_illaka_permitted(current_user: dict, illaka_id: str) -> None:
    allowed = await permitted_illaka_ids(current_user)
    if allowed is not None and illaka_id not in allowed:
        raise HTTPException(status_code=403, detail="This Illaka is not assigned to you")


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
    _positive_amount(data.principal_amount, "Principal amount")
    data.loan_date = valid_date(data.loan_date, "Loan date")
    # Lending is limited to the agent's own illakas; a sipahi with none lent
    # into another illaka.
    await _assert_illaka_permitted(current_user, data.illaka_id)
    await assert_open_period(data.illaka_id, data.loan_date, what="This loan")
    async with kyc_lock(data.kyc_id):
        return await _create_loan(data, current_user)


async def _create_loan(data: LoanCreate, current_user: dict):
    try:
        _kyc_now = await db.kycs.find_one({"_id": ObjectId(str(data.kyc_id).strip())}, {"primary_borrower.phone": 1})
    except Exception:
        _kyc_now = None
    _pb_now = (_kyc_now or {}).get("primary_borrower")
    phone = _typed_phone(data.client_phone, _pb_now.get("phone") if isinstance(_pb_now, dict) else "",
                         "Client phone")
    # The loan must belong to a client that exists, with the borrower's Aadhaar,
    # and nobody on it may be linked to a Gyal loan. The people are recorded on
    # the loan as they stand now.
    kyc, people = await prepare_loan_people(
        data.kyc_id,
        overrides={"borrower": {"phone": phone}} if phone else None,
        require_kyc=True, require_aadhaar=True,
    )
    kyc_id = str(kyc["_id"])
    await assert_no_old_debt(kyc_id, people=people)
    if kyc.get("illaka_id") and kyc.get("illaka_id") != data.illaka_id:
        await _assert_illaka_permitted(current_user, kyc.get("illaka_id"))
    now = datetime.now(timezone.utc).isoformat()
    loan_date_obj = date_type.fromisoformat(data.loan_date)
    emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)

    customer_id = kyc.get("customer_id") or "—"
    pb = kyc.get("primary_borrower") or {}
    if not isinstance(pb, dict):
        pb = {}
    loan_number = await generate_loan_number(customer_id, kyc_id)

    doc = {
        "kyc_id": kyc_id,
        "customer_id": customer_id,
        "loan_number": loan_number,
        "relative_name": pb.get("relative_name") or "",
        "relative_name_hindi": pb.get("relative_name_hindi") or "",
        "client_name": data.client_name,
        "client_name_hindi": pb.get("name_hindi") or "",
        "client_phone": phone or (_pb_now.get("phone") if isinstance(_pb_now, dict) else None) or data.client_phone,
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
        "people": people,
        "created_at": now, "updated_at": now,
    }
    result = await _insert_loan(doc, customer_id, kyc_id)
    doc["_id"] = result.inserted_id
    await book_loan_disbursement(doc, current_user["id"], current_user["name"])
    return _doc(doc)


@router.get("/loans/{loan_id}")
async def get_loan(loan_id: str, request: Request):
    await get_current_user(request)
    oid, loan_id = _loan_ref(loan_id)
    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    schedule = doc.get("emi_schedule", [])
    if schedule:
        changed = _apply_overdue_to_schedule(schedule)
        new_status = loan_status(doc)
        if changed or new_status != doc.get("status"):
            # Opening a loan brings its overdue months up to date. If someone is
            # changing the loan at this moment, skip it — they hold the loan, and
            # the next view catches up — rather than make a reader wait.
            try:
                async with loan_lock(loan_id, wait=0):
                    today = date_type.today()
                    this_month = f"{today.year}-{today.month:02d}"
                    await db.loans.update_one(
                        {"_id": oid},
                        {"$set": {"emi_schedule.$[o].status": "overdue",
                                  "updated_at": datetime.now(timezone.utc).isoformat()}},
                        array_filters=[{"o.status": "pending", "o.due_month": {"$lt": this_month}}],
                    )
                    fresh = await db.loans.find_one({"_id": oid})
                    if fresh:
                        fresh_status = loan_status(fresh)
                        if fresh_status != fresh.get("status"):
                            await db.loans.update_one({"_id": oid}, {"$set": {"status": fresh_status}})
                            fresh["status"] = fresh_status
                        doc = fresh
            except HTTPException:
                doc["emi_schedule"] = schedule
                doc["status"] = new_status
    return _doc(doc)


async def _update_loan(loan_id: str, data: LoanCreate, request: Request):
    current_user = await get_current_user(request)
    oid, loan_id = _loan_ref(loan_id)
    loan = await db.loans.find_one({"_id": oid})
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
        "client_phone": ("" if not str(data.client_phone or "").strip()
                         else (_typed_phone(data.client_phone, loan.get("client_phone"), "Client phone")
                               or loan.get("client_phone"))),
        "notes": data.notes,
        "updated_at": now,
    }

    if (data.loan_date or "") != (loan.get("loan_date") or ""):
        data.loan_date = valid_date(data.loan_date, "Loan date")
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
        # Changing the terms re-books the disbursement at the new principal, so
        # it pays money out exactly like a new loan. It had no Gyal check at all:
        # raising a written-off loan from 20,000 to 2,00,000 returned 200 and
        # moved the cash, for any role that can edit a loan.
        if loan.get("is_gyal"):
            raise HTTPException(
                status_code=403,
                detail=("This loan has been written off as Gyal. Its amount and date cannot "
                        "be changed. / गयाल कर्ज़ की राशि या तारीख नहीं बदली जा सकती।"),
            )
        # A netted-off loan's balance was settled into its re-loan at the old
        # terms. Changing them afterwards re-booked the disbursement at the new
        # principal while the settlement stayed at the old figure, and left
        # twelve rows nobody could collect.
        if loan.get("netoff_closed"):
            raise HTTPException(
                status_code=400,
                detail=("This loan was closed by a net-off. Delete the re-loan first to change its "
                        "amount or date. / पहले नया कर्ज़ हटाएँ।"),
            )
        # A net-off re-loan's settlement was booked at its amount and date. Changing
        # either left the settlement behind — the rolled-over balance vanished from
        # the books for the months in between. Delete the re-loan and create it again.
        if float(loan.get("netoff_amount") or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail=("This re-loan settled an earlier loan by net-off, so its amount and date cannot be "
                        "changed. Delete it and create the re-loan again. / नेट-ऑफ वाले कर्ज़ की राशि या "
                        "तारीख नहीं बदली जा सकती।"),
            )
        # A field agent may correct a loan's date only while the loan is new — within
        # 30 days of entering it. Re-dating an old unpaid loan to today reset its
        # age, and the year-end closing never wrote it off.
        if (current_user["role"] not in ("admin", "maalik")
                and (data.loan_date or "") != (loan.get("loan_date") or "")):
            try:
                entered = datetime.fromisoformat(str(loan.get("created_at") or "").replace("Z", "+00:00"))
                if entered.tzinfo is None:
                    entered = entered.replace(tzinfo=timezone.utc)
                recent = datetime.now(timezone.utc) - entered <= timedelta(days=30)
            except ValueError:
                recent = False
            if not recent:
                raise HTTPException(
                    status_code=403,
                    detail=("A loan's date can be changed by field staff only within 30 days of entering it. "
                            "Ask an admin or maalik. / 30 दिन बाद कर्ज़ की तारीख केवल एडमिन या मालिक बदल सकते हैं।"),
                )

        # Changing the terms re-books the disbursement on the old and new dates.
        await assert_open_period(loan.get("illaka_id"), loan.get("loan_date"), data.loan_date,
                                 what="This loan")
        _positive_amount(data.principal_amount, "Principal amount")
        # Nobody on this loan may be linked to a Gyal loan. The people recorded on
        # the loan are checked; an older loan with none recorded is checked
        # through its KYC.
        # The client's KYC as it stands now is checked too: changing the KYC to a
        # Gyal-linked person and then raising the amount paid them out.
        if isinstance(loan.get("people"), dict) and loan["people"]:
            await assert_people_not_gyal(loan["people"], own_kyc_id=loan.get("kyc_id"))
        await assert_client_not_gyal(loan.get("kyc_id"), require_kyc=False)
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
        # Raising the amount pays out more money: not to a client with a loan over
        # three years old that still owes.
        if float(data.principal_amount) > float(loan.get("principal_amount") or 0):
            _new_emi, _ = _build_emi_schedule(
                data.principal_amount, date_type.fromisoformat(_day(data.loan_date) or date_type.today().isoformat()))
            await assert_no_old_debt(loan.get("kyc_id"), people=loan.get("people"),
                                     editing=(loan["_id"], _new_emi * 12))

        loan_date_obj = date_type.fromisoformat(data.loan_date)
        emi_amount, schedule = _build_emi_schedule(data.principal_amount, loan_date_obj)
        # Rebuilding the schedule used to drop every note on it silently. A note
        # stays on its month: on the new row for that month if there is one,
        # otherwise beside the schedule.
        old_notes = {e.get("due_month"): str(e.get("note") or "").strip()
                     for e in old_schedule if str(e.get("note") or "").strip()}
        new_months = {e["due_month"] for e in schedule}
        for row in schedule:
            if row["due_month"] in old_notes:
                row["note"] = old_notes[row["due_month"]]
        for month, text in old_notes.items():
            if month not in new_months and is_valid_month(month):
                updates[f"month_notes.{month}"] = text
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

    await db.loans.update_one({"_id": oid}, {"$set": updates})
    updated = await db.loans.find_one({"_id": oid})

    # Keep the books in step with the loan book. Changing the principal used to
    # leave the original disbursement entry untouched, so Loans Portfolio kept
    # the old figure while the loan carried the new one — a divergence no report
    # would ever surface.
    if terms_changed:
        await db.journal_entries.delete_many(
            {"reference_id": _id_ci(loan_id), "entry_type": "loan_disbursement"}
        )
        await book_loan_disbursement(updated, current_user["id"], current_user["name"])
        await _abort_if_loan_gone(oid, loan_id)
        updated = await db.loans.find_one({"_id": oid})

    return _doc(updated)


@router.put("/loans/{loan_id}")
async def update_loan(loan_id: str, data: LoanCreate, request: Request):
    await get_current_user(request)
    try:
        _oid, _lid = _loan_ref(loan_id)
    except HTTPException:
        # An invalid id locks nothing; the handler reports it after its own
        # role checks, so a caller without access still sees 403, not 400.
        return await _update_loan(loan_id, data, request)
    # The client is locked as well as the loan. Raising the amount pays money
    # out, and its Gyal check could pass just before a year-end closing wrote off
    # the client's other loan — the closing takes the same client lock.
    peek = await db.loans.find_one({"_id": _oid}, {"kyc_id": 1})
    async with loan_lock(_lid), kyc_lock((peek or {}).get("kyc_id")):
        return await _update_loan(_lid, data, request)


async def _update_loan_status(loan_id: str, data: LoanStatusUpdate, request: Request):
    current_user = await get_current_user(request)
    # Admin and Maalik only. A muneem could mark an overdue loan "closed" just
    # before year end — the closing skips closed loans — and flip it back after,
    # so a written-off debt was never written off. Nothing in the app calls this.
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can change a loan's status")
    if data.status not in ["active", "closed", "overdue"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    oid, loan_id = _loan_ref(loan_id)
    loan = await db.loans.find_one({"_id": oid})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, loan)
    # A net-off-closed or written-off loan has its status set by that event.
    # Reopening a netted-off loan by hand let the next year-end closing write
    # off a balance that had already been settled into the re-loan.
    if loan.get("netoff_closed") or loan.get("is_gyal"):
        raise HTTPException(
            status_code=400,
            detail="This loan was closed by a net-off or written off as Gyal; its status cannot be set by hand.",
        )
    updates = {"status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if data.notes:
        updates["notes"] = data.notes
    await db.loans.update_one({"_id": oid}, {"$set": updates})
    return _doc(await db.loans.find_one({"_id": oid}))


@router.patch("/loans/{loan_id}/status")
async def update_loan_status(loan_id: str, data: LoanStatusUpdate, request: Request):
    await get_current_user(request)
    try:
        _, _lid = _loan_ref(loan_id)
    except HTTPException:
        # An invalid id locks nothing; the handler reports it after its own
        # role checks, so a caller without access still sees 403, not 400.
        return await _update_loan_status(loan_id, data, request)
    async with loan_lock(_lid):
        return await _update_loan_status(_lid, data, request)


@router.get("/loans/{loan_id}/payments")
async def list_payments(loan_id: str, request: Request):
    await get_current_user(request)
    docs = await db.payments.find({"loan_id": loan_id}).sort("payment_date", -1).to_list(500)
    return [_doc(d) for d in docs]


async def _collect_emi(loan_id: str, data: PaymentCreate, request: Request):
    current_user = await get_current_user(request)
    oid, loan_id = _loan_ref(loan_id)
    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Only staff assigned to this illaka may collect against it. The sheet
    # already hides other illakas, but the endpoint accepted any loan id.
    allowed = await permitted_illaka_ids(current_user)
    if allowed is not None and doc.get("illaka_id") not in allowed:
        raise HTTPException(status_code=403, detail="This client is not in your assigned Illaka")

    # A loan closed by a net-off re-loan owes nothing: its balance moved into
    # the new loan. Only its netoff rows were protected, so a month past the end
    # of its schedule could still take cash — money booked against a debt that no
    # longer exists.
    if doc.get("netoff_closed"):
        raise HTTPException(
            status_code=400,
            detail=("This loan was closed by a net-off re-loan. Record the collection on "
                    "the new loan. / यह कर्ज़ नेट-ऑफ से बंद है — नए कर्ज़ पर वसूली दर्ज करें।"),
        )

    data.payment_date = valid_date(data.payment_date, "Payment date")
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
    # Nothing may be collected into a year that has been closed.
    await assert_open_period(doc.get("illaka_id"), data.payment_date, what="This collection")
    # Validate the month before it can be written into the schedule. Junk values
    # like "2026-13" or "junkmonth" were accepted, marked paid, and then made the
    # delete path 500 forever — a row nothing could clear.
    if not is_valid_month(data.emi_month):
        raise HTTPException(status_code=400, detail="emi_month must be in YYYY-MM format")

    if doc.get("is_gyal"):
        # A recovery is dated on or after the write-off it recovers. One dated
        # earlier was counted twice in that month's Balance Sheet — as a
        # reduction of the portfolio and as recovery income.
        since = str(doc.get("gyal_since") or "")[:10]
        if since and (data.payment_date or "")[:10] < since:
            raise HTTPException(
                status_code=400,
                detail=f"A Gyal recovery cannot be dated before the write-off ({since}).",
            )
        # And never more than the client still owes. An excess had to be split
        # between the portfolio and income when the write-off was undone, and
        # later edits and uncollects — which rebook a recovery whole — drifted
        # the books by exactly that excess.
        _asked = data.amount if data.amount is not None else next(
            (e.get("amount") for e in doc.get("emi_schedule", []) if e.get("due_month") == data.emi_month), 0)
        if float(_asked or 0) > max(0.0, _gyal_outstanding(doc)) + 0.01:
            raise HTTPException(
                status_code=400,
                detail=(f"A Gyal recovery cannot exceed what the client still owes "
                        f"(₹{max(0.0, _gyal_outstanding(doc)):,.2f}). / बकाया से ज़्यादा वसूली नहीं।"),
            )

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
            if round(_repayable - _paid_all, 2) < OWED_TOLERANCE:
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
                # A note already written for this month moves onto the row
                "note": (doc.get("month_notes") or {}).get(data.emi_month, ""),
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
                "note": (doc.get("month_notes") or {}).get(data.emi_month, ""),
            }
        emi_item = new_entry
    else:
        new_entry = None
    if emi_item["status"] == "paid":
        raise HTTPException(status_code=400, detail="This EMI is already paid / यह किस्त पहले से चुकाई जा चुकी है")
    # Fix: use `is not None` so that 0 is treated as a valid explicit amount
    amount = data.amount if data.amount is not None else emi_item["amount"]
    # A negative collection is not a refund — it is money invented in reverse.
    # It credited Cash and debited the portfolio, so the Cash Book, the Bid and
    # the loan's own total_paid all moved the wrong way with nothing to show it.
    if float(amount) < 0:
        raise HTTPException(
            status_code=400,
            detail="Collection amount cannot be negative / वसूली राशि ऋणात्मक नहीं हो सकती",
        )
    # A loan that owes nothing takes no more money. A lump sum recorded against
    # one instalment left the others pending, and collecting them overpaid.
    if (float(amount) > 0 and not doc.get("is_gyal") and doc.get("total_repayable") is not None
            and float(doc.get("total_repayable") or 0) - paid_so_far(doc) < OWED_TOLERANCE):
        raise HTTPException(status_code=400, detail="This loan is fully repaid / यह क़र्ज़ पूरा चुक गया है")
    now = datetime.now(timezone.utc).isoformat()
    # ── Zero-entry: record visit only, keep EMI status unchanged, no journal ──
    if amount == 0:
        await db.payments.insert_one({
            "loan_id": loan_id, "emi_month": data.emi_month,
            "amount": 0, "payment_date": data.payment_date,
            "collected_by_id": current_user["id"], "collected_by_name": current_user["name"],
            "notes": data.notes or "Zero collection / visit recorded", "created_at": now,
        })
        updated_loan = await db.loans.find_one({"_id": oid})
        if not updated_loan:
            # This path had no guard: a loan deleted mid-visit returned a 500
            # and could leave the visit row behind.
            await _abort_if_loan_gone(oid, loan_id)
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
    if new_entry is not None:
        # Appending a month beyond the original schedule races the same way, so
        # guard it on "no entry for this month exists yet". If a concurrent
        # request appended first, its entry is used and this one falls through to
        # the flip below — where exactly one of them will win.
        # A note already written for this month moves onto the new row, so
        # only one copy of it exists.
        await db.loans.update_one(
            {"_id": oid, "emi_schedule.due_month": {"$ne": data.emi_month}},
            {"$push": {"emi_schedule": new_entry},
             "$unset": {f"month_notes.{data.emi_month}": ""}},
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
        },
         # In the same write as the row, so a restart cannot leave total_paid short
         # (a later write-off then booked that shortfall as bad debt).
         "$inc": {"total_paid": float(amount)}},
        # "netoff" is excluded as well as "paid": that instalment was settled by
        # a re-loan, and collecting cash against it books money on a debt that no
        # longer exists.
        array_filters=[{"e.due_month": data.emi_month,
                        "e.status": {"$nin": ["paid", "netoff"]}}],
    )
    if claim.modified_count == 0:
        # Matching nothing means either the instalment is already paid or the
        # loan itself is gone; the second used to be reported as the first.
        await _abort_if_loan_gone(oid, loan_id)
        raise HTTPException(status_code=400, detail="This EMI is already paid / यह किस्त पहले से चुकाई जा चुकी है")

    # The instalment was unpaid until this claim, so any payment or Cash Book entry
    # still recorded for the month is left over from an undo stopped by a restart.
    # It goes now; otherwise this collection booked the cash a second time.
    stale = await db.journal_entries.delete_many(
        {"entry_type": "emi_collection", "reference_id": _id_ci(loan_id), "emi_month": data.emi_month})
    stale_pay = await db.payments.delete_many(
        {"loan_id": _id_ci(loan_id), "emi_month": data.emi_month, "amount": {"$gt": 0}})
    if stale.deleted_count or stale_pay.deleted_count:
        logging.getLogger(__name__).warning(
            "Removed %s stale entr(y/ies) and %s payment(s) for loan %s month %s before collecting",
            stale.deleted_count, stale_pay.deleted_count, loan_id, data.emi_month)

    # Derived totals, recomputed from the authoritative post-claim document.
    claimed = await db.loans.find_one({"_id": oid})
    if not claimed:
        # Deleted between the claim and this read — this crashed with a 500.
        await _abort_if_loan_gone(oid, loan_id)
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
    new_status = _get_loan_status(claimed_schedule, total_paid, doc.get("total_repayable"))
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
    updated_loan = await db.loans.find_one({"_id": oid})
    if not updated_loan:
        await _abort_if_loan_gone(oid, loan_id)
    payment_record = {"amount": amount, "payment_date": data.payment_date, "emi_month": data.emi_month}
    await _book_emi_collection(updated_loan, payment_record, current_user["id"], current_user["name"])
    # The journal entry is the last thing written, so it is the one a delete can
    # slip in front of: the loan was still here a moment ago, the entry has just
    # been booked, and the loan may be gone now. Checking once more AFTER the
    # write is what makes the result exact — if the loan has vanished, nothing
    # of it survives.
    await _abort_if_loan_gone(oid, loan_id)
    return _doc(updated_loan)


@router.post("/loans/{loan_id}/payments")
async def collect_emi(loan_id: str, data: PaymentCreate, request: Request):
    await get_current_user(request)
    try:
        _, _lid = _loan_ref(loan_id)
    except HTTPException:
        # An invalid id locks nothing; the handler reports it after its own
        # role checks, so a caller without access still sees 403, not 400.
        return await _collect_emi(loan_id, data, request)
    async with loan_lock(_lid):
        return await _collect_emi(_lid, data, request)


@router.delete("/loans/{loan_id}")
async def delete_loan(loan_id: str, request: Request):
    """Permanently delete a loan and all its payments and journal entries. Admin and Maalik only."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can delete loans")
    oid, loan_id = _loan_ref(loan_id)
    # A re-loan's parent is locked too, BEFORE anything is deleted. The parent's
    # lock used to be taken only after the re-loan and its entries were gone; if
    # that wait timed out, the parent stayed netted off against a deleted loan.
    peek = await db.loans.find_one({"_id": oid}, {"parent_loan_id": 1, "is_reloan": 1})
    parent_id = _canon_parent_id((peek or {}).get("parent_loan_id")) if (peek or {}).get("is_reloan") else ""
    async with loan_lock(loan_id), (loan_lock(parent_id) if parent_id else contextlib.nullcontext()):
        return await _delete_loan(oid, loan_id, current_user, locked_parent=parent_id)


async def _delete_loan(oid: ObjectId, loan_id: str, current_user: dict, locked_parent: str = ""):
    loan = await db.loans.find_one({"_id": oid})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, loan)

    # A written-off loan is the record that stops the client borrowing again.
    # Undoing the year-end closing is the recorded way to reverse it. A loan
    # IMPORTED as Gyal has no closing to undo, so an import made by mistake could
    # never be removed and blocked that person for good; it can be deleted while
    # nothing has been recovered on it.
    if loan.get("is_gyal"):
        closing = str(loan.get("gyal_since") or "")
        from_import = bool(loan.get("is_import")) and not await db.illaka_closings.find_one(
            {"illaka_id": loan.get("illaka_id"), "closing_date": closing})
        if not from_import:
            raise HTTPException(
                status_code=400,
                detail=("This loan has been written off as Gyal. Undo the year-end closing first if the "
                        "write-off was a mistake. / गयाल कर्ज़ हटाने से पहले साल-अंत समापन वापस लें।"),
            )
        if (any(e.get("status") == "paid" and float(e.get("paid_amount") or 0) > 0
                for e in loan.get("emi_schedule", []))
                or await db.journal_entries.find_one({"reference_id": _id_ci(loan_id),
                                                      "entry_type": "emi_collection"})):
            raise HTTPException(
                status_code=400,
                detail=("Money has been recovered on this Gyal loan. Undo those recoveries first. "
                        "/ पहले वसूली की एंट्री हटाएँ।"),
            )

    # Deleting removes the loan's entries, so none may lie in a closed year.
    closing = await latest_closing_date(loan.get("illaka_id"))
    if closing:
        booked = await db.journal_entries.find_one(
            {"reference_id": _id_ci(loan_id), "date": {"$lt": _next_day(closing)}}, {"date": 1})
        if booked:
            await assert_open_period(loan.get("illaka_id"), booked.get("date"), what="An entry of this loan")

    # A loan that a re-loan was taken against cannot go first: the net-off
    # settlement is booked against the NEW loan, so deleting the old one left it
    # standing — Loans Portfolio fell by the old balance while the surviving loan
    # still owed in full. Deleting the re-loan first unwinds cleanly. A re-loan
    # being created holds this loan's lock until its child exists, so the check
    # cannot miss one.
    # A plain re-loan settled nothing, so the two loans stand independently.
    child = await db.loans.find_one({"parent_loan_id": _id_ci(loan_id), "netoff_amount": {"$gt": 0}},
                                    {"loan_number": 1})
    if child:
        raise HTTPException(
            status_code=400,
            detail=(f"Re-loan {child.get('loan_number') or ''} was taken against this loan. "
                    f"Delete the re-loan first. / पहले नया कर्ज़ हटाएँ।"),
        )

    if loan.get("is_reloan") and _canon_parent_id(loan.get("parent_loan_id")) != locked_parent:
        raise HTTPException(status_code=409, detail="This loan has just changed. Please try again.")
    await db.loans.delete_one({"_id": oid})
    await db.payments.delete_many({"loan_id": _id_ci(loan_id)})
    await db.journal_entries.delete_many({"reference_id": _id_ci(loan_id)})

    # Deleting a re-loan releases the parent it closed — only a parent that
    # points back at THIS child. Its lock is already held.
    reopened = None
    parent_id = _canon_parent_id(loan.get("parent_loan_id"))
    if loan.get("is_reloan") and parent_id:
        if parent_id != locked_parent:
            # The loan changed between the peek and the lock; nothing deleted yet.
            raise HTTPException(status_code=409, detail="This loan has just changed. Please try again.")
        status = await _release_netoff_parent(ObjectId(parent_id), loan_id)
        if status is not None:
            parent = await db.loans.find_one({"_id": ObjectId(parent_id)}, {"loan_number": 1})
            reopened = {
                "loan_id": parent_id,
                "loan_number": (parent or {}).get("loan_number"),
                "status": status,
            }

    return {
        "deleted": True,
        "loan_id": loan_id,
        "loan_number": loan.get("loan_number"),
        "reopened_parent": reopened,
    }


def _next_day(day: str) -> str:
    return (date_type.fromisoformat(day[:10]) + timedelta(days=1)).isoformat()


def _canon_parent_id(value) -> str:
    try:
        return str(ObjectId(str(value).strip()))
    except Exception:
        return ""


async def _assert_may_reduce_collection(current_user: dict, doc: dict, loan_id: str, emi_month: str, emi_item: dict):
    """Once a client has been given new money after a collection was recorded, only
    an admin or maalik may undo or reduce that collection.

    Otherwise a field agent could record an old balance as collected, lend again
    because nothing was owed, then undo the collection: the old loan owed again
    and the new loan stood.
    """
    if current_user["role"] in ("admin", "maalik"):
        return
    pay = await db.payments.find_one({"loan_id": _id_ci(loan_id), "emi_month": emi_month, "amount": {"$gt": 0}},
                                     sort=[("created_at", -1)])
    since = str((pay or {}).get("created_at") or "") or _day(emi_item.get("paid_date"))
    if not since:
        return
    later = [ln for ln in await client_loans(doc.get("kyc_id"), {"created_at": 1, "loan_number": 1})
             if str(ln["_id"]) != loan_id and str(ln.get("created_at") or "") > since]
    if later:
        raise HTTPException(
            status_code=403,
            detail=(f"Loan {later[0].get('loan_number') or ''} was given to this client after this collection was "
                    f"recorded. Only an admin or maalik can undo or reduce it. / नया कर्ज़ देने के बाद यह वसूली "
                    f"केवल एडमिन या मालिक बदल सकते हैं।"),
        )


async def _uncollect_emi(loan_id: str, emi_month: str, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")
    oid, loan_id = _loan_ref(loan_id)
    if not is_valid_month(emi_month):
        raise HTTPException(status_code=400, detail="emi_month must be in YYYY-MM format")
    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, doc)

    # A netted-off loan's figures fed the settlement that closed it. Changing a
    # collection on it afterwards left the settlement at the old figure: the
    # difference sat in Loans Portfolio with no way to collect it, because the
    # loan refuses collections. Delete the re-loan first, then correct.
    if doc.get("netoff_closed"):
        raise HTTPException(
            status_code=400,
            detail=("This loan was closed by a net-off. Delete the re-loan first to correct "
                    "its collections. / पहले नया कर्ज़ हटाएँ।"),
        )

    schedule = doc.get("emi_schedule", [])
    _baseline = _import_baseline(doc)   # before any mutation below
    emi_item = next((e for e in schedule if e["due_month"] == emi_month), None)
    if not emi_item:
        raise HTTPException(status_code=404, detail="EMI month not found")
    if emi_item.get("status") != "paid":
        raise HTTPException(status_code=400, detail="This EMI has not been collected")
    await assert_open_period(doc.get("illaka_id"), emi_item.get("paid_date"), what="This collection",
                             undated_is_closed=True)
    await _assert_may_reduce_collection(current_user, doc, loan_id, emi_month, emi_item)

    old_paid_date = emi_item.get("paid_date") or ""
    now = datetime.now(timezone.utc).isoformat()
    # total_paid is changed in the SAME write as the row. Written separately, a
    # restart in between left it too high — and every later change read the
    # excess as money repaid before import, so it never went away.
    _rows_before = sum(float(e.get("paid_amount") or 0) for e in schedule if e.get("status") == "paid")
    _total_after = round(_baseline + _rows_before - float(emi_item.get("paid_amount") or 0), 2)

    # The payment and its Cash Book entry go FIRST, the row last. The other order
    # left a restart with the row unpaid but the cash still booked: the retry was
    # refused as "not collected", and collecting the month again booked the cash
    # twice. Now a restart leaves the row paid with no entry — reported by the
    # audit, and a retry finishes it.
    await db.payments.delete_one(
        {"loan_id": _id_ci(loan_id), "emi_month": emi_month, "amount": {"$gt": 0}}
    )
    old_entry = await db.journal_entries.find_one({
        "entry_type": "emi_collection",
        "reference_id": _id_ci(loan_id),
        "emi_month": emi_month,
    })
    if not old_entry and old_paid_date:
        # Only an entry from before months were recorded on entries may be matched
        # by date — otherwise a retry deleted another month collected the same day.
        old_entry = await db.journal_entries.find_one({
            "entry_type": "emi_collection",
            "reference_id": _id_ci(loan_id),
            "emi_month": {"$in": [None, ""]},
            "date": old_paid_date,
        })
    if old_entry:
        await db.journal_entries.delete_one({"_id": old_entry["_id"]})

    if emi_item.get("is_gyal_entry") or emi_item.get("is_extra_entry"):
        # A row that only exists because a collection added it — a Gyal
        # recovery, or a month past the original schedule — goes with the
        # collection. Leaving an extra row behind as "pending" invented an
        # instalment that was never scheduled and inflated Utaar. Its note, if
        # any, goes back beside the schedule so it is not lost.
        update = {"$pull": {"emi_schedule": {"due_month": emi_month, "status": "paid"}},
                  "$set": {"updated_at": now, "total_paid": _total_after}}
        note = str(emi_item.get("note") or "").strip()
        if note:
            update["$set"][f"month_notes.{emi_month}"] = note
        await db.loans.update_one({"_id": oid}, update)
    else:
        # Only this row is changed. The whole schedule used to be saved back from
        # the copy read above, overwriting anything recorded on the loan in
        # between — a collection on another month reset to overdue with its money
        # still booked, or a released net-off written back as netoff.
        y, mo = map(int, emi_month.split("-"))
        last_day = calendar.monthrange(y, mo)[1]
        new_emi_status = "overdue" if date_type.today() > date_type(y, mo, last_day) else "pending"
        await db.loans.update_one(
            {"_id": oid},
            {"$set": {
                "emi_schedule.$[e].status": new_emi_status,
                "emi_schedule.$[e].paid_amount": 0.0,
                "emi_schedule.$[e].paid_date": None,
                "emi_schedule.$[e].collected_by_id": None,
                "emi_schedule.$[e].collected_by_name": None,
                "total_paid": _total_after,
                "updated_at": now,
            }},
            array_filters=[{"e.due_month": emi_month, "e.status": "paid"}],
        )

    fresh = await db.loans.find_one({"_id": oid})
    if not fresh:
        await _abort_if_loan_gone(oid, loan_id)
    fresh_schedule = fresh.get("emi_schedule", [])
    _new_total = _total_paid_with_baseline(_baseline, fresh_schedule)
    await db.loans.update_one(
        {"_id": oid},
        {"$set": {"total_paid": _new_total,
                  "status": _get_loan_status(fresh_schedule, _new_total, fresh.get("total_repayable"))}},
    )

    return {"message": f"EMI for {emi_month} uncollected"}


@router.delete("/loans/{loan_id}/payments/{emi_month}")
async def uncollect_emi(loan_id: str, emi_month: str, request: Request):
    await get_current_user(request)
    try:
        _, _lid = _loan_ref(loan_id)
    except HTTPException:
        # An invalid id locks nothing; the handler reports it after its own
        # role checks, so a caller without access still sees 403, not 400.
        return await _uncollect_emi(loan_id, emi_month, request)
    # The client is locked too: a new loan for the same client (which takes the
    # client lock) and this undo used to pass each other, so both went through.
    peek = await db.loans.find_one({"_id": ObjectId(_lid)}, {"kyc_id": 1})
    async with loan_lock(_lid), kyc_lock((peek or {}).get("kyc_id")):
        return await _uncollect_emi(_lid, emi_month, request)


async def _edit_emi_payment(loan_id: str, emi_month: str, data: PaymentEdit, request: Request):
    """Edit a paid EMI entry: update amount and/or payment date.
    Muneem/Sipahi: current month only.
    Admin/Maalik: any month not locked by year-end closing.
    """
    current_user = await get_current_user(request)
    oid, loan_id = _loan_ref(loan_id)
    if not is_valid_month(emi_month):
        raise HTTPException(status_code=400, detail="emi_month must be in YYYY-MM format")

    today = date_type.today()
    current_ym = f"{today.year}-{today.month:02d}"

    doc = await db.loans.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, doc)

    # See uncollect_emi: a netted-off loan's collections fed its settlement.
    if doc.get("netoff_closed"):
        raise HTTPException(
            status_code=400,
            detail=("This loan was closed by a net-off. Delete the re-loan first to correct "
                    "its collections. / पहले नया कर्ज़ हटाएँ।"),
        )

    # Role-based time restriction
    if current_user["role"] in ["muneem", "sipahi"]:
        if emi_month != current_ym:
            raise HTTPException(status_code=403, detail="Muneem/Sipahi can only edit entries for the current month")

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
    if new_amount <= 0:
        # Editing a collection to a negative amount reversed the cash entry and
        # pushed total_paid below what was actually received. Editing it to zero
        # left the payment record behind at ₹0 while the row and the journal moved
        # on — to remove a collection, uncollect it.
        raise HTTPException(
            status_code=400,
            detail=("Payment amount must be more than zero; to remove a collection, undo it. "
                    "/ भुगतान राशि शून्य से अधिक होनी चाहिए।"),
        )
    new_date = data.payment_date if data.payment_date else old_date
    if new_date != old_date:
        # The edit screen sends the stored date back; only a changed one is checked.
        new_date = valid_date(new_date, "Payment date")
    # A collection in a closed year cannot be changed, nor moved into one — for
    # any role. Only the admin's edit of an instalment MONTH in a closed year was
    # refused; removing, back-dating and re-dating all went through.
    await assert_open_period(doc.get("illaka_id"), old_date, what="This collection", undated_is_closed=True)
    if new_amount < old_amount - 0.005:
        await _assert_may_reduce_collection(current_user, doc, loan_id, emi_month, emi_item)
    await assert_open_period(doc.get("illaka_id"), new_date, what="This collection")

    if doc.get("is_gyal"):
        # The same limits as collecting a recovery: not more than the client
        # still owes, and not dated before the write-off.
        if new_amount - old_amount > _gyal_outstanding(doc) + 0.01:
            raise HTTPException(
                status_code=400,
                detail=(f"A Gyal recovery cannot exceed what the client still owes "
                        f"(₹{max(0.0, _gyal_outstanding(doc)) + old_amount:,.2f} for this entry)."),
            )
        since = str(doc.get("gyal_since") or "")[:10]
        if since and (new_date or "")[:10] < since:
            raise HTTPException(
                status_code=400,
                detail=f"A Gyal recovery cannot be dated before the write-off ({since}).",
            )

    # Delete the old journal entry for this specific EMI collection
    old_entry = await db.journal_entries.find_one({
        "entry_type": "emi_collection",
        "reference_id": _id_ci(loan_id),
        "emi_month": emi_month,
    })
    if not old_entry and old_date:
        # Legacy entries only (see uncollect): a retry used to delete another
        # month collected on the same day.
        old_entry = await db.journal_entries.find_one({
            "entry_type": "emi_collection",
            "reference_id": _id_ci(loan_id),
            "emi_month": {"$in": [None, ""]},
            "date": old_date,
        })
    if old_entry:
        await db.journal_entries.delete_one({"_id": old_entry["_id"]})

    # Only this row is changed. The whole schedule used to be saved back from
    # the copy read above, overwriting a collection on another month recorded in
    # between (reset to overdue with its money still booked), or re-marking a
    # just-released net-off parent as netoff.
    now = datetime.now(timezone.utc).isoformat()
    # total_paid moves in the same write as the row (see uncollect).
    _rows_before = sum(float(e.get("paid_amount") or 0) for e in schedule if e.get("status") == "paid")
    _total_after = round(_baseline + _rows_before - float(emi_item.get("paid_amount") or 0) + new_amount, 2)
    await db.loans.update_one(
        {"_id": oid},
        {"$set": {
            "total_paid": _total_after,
            "emi_schedule.$[e].paid_amount": new_amount,
            "emi_schedule.$[e].paid_date": new_date,
            "emi_schedule.$[e].edited_by_id": current_user["id"],
            "emi_schedule.$[e].edited_by_name": current_user["name"],
            "updated_at": now,
        }},
        array_filters=[{"e.due_month": emi_month, "e.status": "paid"}],
    )
    fresh = await db.loans.find_one({"_id": oid})
    if not fresh:
        await _abort_if_loan_gone(oid, loan_id)
    _new_total = _total_paid_with_baseline(_baseline, fresh.get("emi_schedule", []))
    await db.loans.update_one(
        {"_id": oid},
        {"$set": {"total_paid": _new_total,
                  "status": _get_loan_status(fresh.get("emi_schedule", []), _new_total, fresh.get("total_repayable"))}},
    )

    # Update payments record
    await db.payments.update_one(
        {"loan_id": _id_ci(loan_id), "emi_month": emi_month, "amount": {"$gt": 0}},
        {"$set": {"amount": new_amount, "payment_date": new_date, "updated_at": now}}
    )

    # Book new journal entry with corrected values
    updated_loan = await db.loans.find_one({"_id": oid})
    if not updated_loan:
        await _abort_if_loan_gone(oid, loan_id)
    payment_record = {"amount": new_amount, "payment_date": new_date, "emi_month": emi_month}
    await _book_emi_collection(updated_loan, payment_record, current_user["id"], current_user["name"])
    # The replacement entry can be booked just after a concurrent delete has
    # swept the loan's entries; re-check after writing.
    await _abort_if_loan_gone(oid, loan_id)

    return _doc(updated_loan)


_NOTE_MAX = 500


@router.patch("/loans/{loan_id}/payments/{emi_month}")
async def edit_emi_payment(loan_id: str, emi_month: str, data: PaymentEdit, request: Request):
    await get_current_user(request)
    try:
        _, _lid = _loan_ref(loan_id)
    except HTTPException:
        # An invalid id locks nothing; the handler reports it after its own
        # role checks, so a caller without access still sees 403, not 400.
        return await _edit_emi_payment(loan_id, emi_month, data, request)
    peek = await db.loans.find_one({"_id": ObjectId(_lid)}, {"kyc_id": 1})
    async with loan_lock(_lid), kyc_lock((peek or {}).get("kyc_id")):
        return await _edit_emi_payment(_lid, emi_month, data, request)


async def _update_emi_note(loan_id: str, data: EmiNoteUpdate, request: Request):
    """Add or update a note on a specific EMI."""
    current_user = await get_current_user(request)
    oid, loan_id = _loan_ref(loan_id)
    doc = await db.loans.find_one({"_id": oid}, {"illaka_id": 1, "sipahi_id": 1})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, doc)
    if not is_valid_month(data.emi_month):
        raise HTTPException(status_code=400, detail="emi_month must be in YYYY-MM format")
    note = (data.note or "").strip()
    if len(note) > _NOTE_MAX:
        # Unbounded notes were saved at several megabytes; copying one onto a
        # schedule row later pushed the loan past Mongo's 16 MB limit, and that
        # month could not be collected at all.
        raise HTTPException(status_code=400, detail=f"A note can be at most {_NOTE_MAX} characters")
    now = datetime.now(timezone.utc).isoformat()
    field = f"month_notes.{data.emi_month}"

    # One copy of a note, never two.
    #
    # A month with an instalment row keeps its note on that row. A month without
    # one keeps it beside the schedule in month_notes, where nothing can mistake
    # it for an instalment. When a collection creates a row, the note moves onto
    # it; when that row is removed, the note moves back.
    #
    # Written against the row first, conditionally on the row existing at the
    # moment of the write. Deciding from an earlier read lost notes: the row
    # could be removed in between and the update then matched nothing while the
    # request still returned 200.
    on_row = await db.loans.update_one(
        {"_id": oid, "emi_schedule.due_month": data.emi_month},
        {"$set": {"emi_schedule.$[e].note": note, "updated_at": now},
         "$unset": {field: ""}},
        array_filters=[{"e.due_month": data.emi_month}],
    )
    if not on_row.matched_count:
        if note:
            await db.loans.update_one({"_id": oid}, {"$set": {field: note, "updated_at": now}})
        else:
            await db.loans.update_one({"_id": oid}, {"$unset": {field: ""}, "$set": {"updated_at": now}})

    return _doc(await db.loans.find_one({"_id": oid}))


@router.patch("/loans/{loan_id}/emi-note")
async def update_emi_note(loan_id: str, data: EmiNoteUpdate, request: Request):
    await get_current_user(request)
    try:
        _, _lid = _loan_ref(loan_id)
    except HTTPException:
        # An invalid id locks nothing; the handler reports it after its own
        # role checks, so a caller without access still sees 403, not 400.
        return await _update_emi_note(loan_id, data, request)
    async with loan_lock(_lid):
        return await _update_emi_note(_lid, data, request)


@router.post("/loans/{loan_id}/reloan")
async def create_reloan(loan_id: str, data: ReLoanRequest, request: Request):
    """Create a re-loan for an existing client. Optionally net-off outstanding balance."""
    current_user = await get_current_user(request)
    oid, loan_id = _loan_ref(loan_id)
    _positive_amount(data.new_disbursement_amount, "Re-loan amount")
    data.loan_date = valid_date(data.loan_date, "Loan date")
    existing = await db.loans.find_one({"_id": oid}, {"kyc_id": 1, "client_phone": 1, "illaka_id": 1})
    if existing:
        await assert_open_period(existing.get("illaka_id"), data.loan_date, what="This re-loan")
    try:
        _kyc_now = await db.kycs.find_one({"_id": ObjectId(str((existing or {}).get("kyc_id") or "").strip())})
    except Exception:
        _kyc_now = None
    _k = _kyc_now or {}
    _pb = _k.get("primary_borrower") if isinstance(_k.get("primary_borrower"), dict) else {}
    phone = _typed_phone(data.phone, _pb.get("phone") or (existing or {}).get("client_phone"), "Phone")
    # An older client whose KYC has no phone but whose loan does: that phone is
    # still theirs, so it is recorded on the re-loan and checked.
    legacy_phone = "" if str(_pb.get("phone") or "").strip() else str((existing or {}).get("client_phone") or "")
    co_borrower = clean_person(data.co_borrower, "Co-borrower", previous=_k.get("co_borrower"))
    guarantor = clean_person(data.guarantor, "Guarantor", previous=_k.get("guarantor"))
    # The new loan's id is fixed up front so the parent can point at it in the
    # same write that closes it, and so the new loan is locked before it exists.
    new_oid = ObjectId()
    async with loan_lock(loan_id), loan_lock(str(new_oid)), kyc_lock((existing or {}).get("kyc_id")):
        return await _create_reloan(oid, loan_id, new_oid, data, phone, co_borrower, guarantor, current_user,
                                    legacy_phone=legacy_phone)


async def _create_reloan(oid, loan_id, new_oid, data, phone, co_borrower, guarantor, current_user, legacy_phone=""):
    new_id = str(new_oid)
    loan = await db.loans.find_one({"_id": oid})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    await _assert_loan_in_scope(current_user, loan)
    if loan.get("is_gyal"):
        raise HTTPException(
            status_code=403,
            detail="This loan has been written off as Gyal and cannot be re-loaned or netted off.",
        )
    # A loan already closed by a net-off has handed its balance to a re-loan; a
    # second re-loan against it overwrote reloan_id and made later deletes release
    # the parent at the wrong moment.
    if loan.get("netoff_closed"):
        raise HTTPException(
            status_code=400,
            detail=("This loan was already closed by a net-off into a re-loan. Create the new "
                    "loan from that re-loan instead. / नेट-ऑफ से बंद कर्ज़ पर दोबारा कर्ज़ नहीं।"),
        )

    # The people on the NEW loan: the client as on the KYC, with any phone,
    # co-borrower or guarantor named on this request replacing what is there.
    # A re-loan that replaces a Gyal-linked co-borrower with a clean one is
    # checked against the clean one — it used to be refused over the person being
    # replaced. The borrower's Aadhaar is required.
    kyc, people = await prepare_loan_people(
        loan.get("kyc_id"),
        overrides={
            "borrower": ({"phone": " / ".join(p for p in (phone, legacy_phone) if p)}
                         if (phone or legacy_phone) else None),
            "co_borrower": co_borrower if co_borrower and any(co_borrower.values()) else None,
            "guarantor": guarantor if guarantor and any(guarantor.values()) else None,
        },
        require_kyc=False, require_aadhaar=True,
    )
    # Replacing or blanking a co-borrower who is linked to a Gyal loan changes
    # that person's identity on the client's record — the same change PUT /kycs
    # allows only an admin or maalik to make. A muneem could otherwise wipe it
    # through a re-loan.
    if kyc and co_borrower is not None and isinstance(kyc.get("co_borrower"), dict):
        from helpers import _person_snapshot
        if (_person_snapshot(kyc["co_borrower"]) != _person_snapshot(co_borrower)
                and current_user["role"] not in ("admin", "maalik")
                and await person_is_gyal_linked(kyc["co_borrower"])):
            raise HTTPException(
                status_code=403,
                detail=("The current co-borrower is linked to a written-off (Gyal) loan. Only an admin "
                        "or maalik can replace them. / गयाल से जुड़े सह-उधारकर्ता को केवल एडमिन या मालिक "
                        "बदल सकते हैं।"),
            )
    if kyc and guarantor is not None and isinstance(kyc.get("guarantor"), dict):
        from helpers import _person_snapshot
        if (_person_snapshot(kyc["guarantor"]) != _person_snapshot(guarantor)
                and current_user["role"] not in ("admin", "maalik")
                and await person_is_gyal_linked(kyc["guarantor"])):
            raise HTTPException(
                status_code=403,
                detail=("The current guarantor is linked to a written-off (Gyal) loan. Only an admin "
                        "or maalik can replace them. / गयाल से जुड़े गारंटर को केवल एडमिन या मालिक बदल सकते हैं।"),
            )
    previous_reloan_id = loan.get("reloan_id")
    kyc_id = str(kyc["_id"]) if kyc else loan.get("kyc_id")
    customer_id = loan.get("customer_id", "—")
    now = datetime.now(timezone.utc).isoformat()

    schedule = loan.get("emi_schedule", [])
    total_repayable = float(loan.get("total_repayable") or ((loan.get("emi_amount") or 0) * 12))
    baseline = _import_baseline(loan)
    paid_rows = sum(float(e.get("paid_amount") or 0) for e in schedule if e.get("status") == "paid")
    outstanding = round(max(0.0, total_repayable - baseline - paid_rows), 2)
    netoff_amount = 0.0

    # A loan over three years old that still owes is due to be written off. A
    # re-loan on it lent more to a defaulter, and a net-off hid the bad debt in
    # the new loan so the closing never wrote it off.
    if (outstanding >= OWED_TOLERANCE
            and _day(loan.get("loan_date"))
            and _day(loan.get("loan_date")) <= _add_months(date_type.today(), -36).isoformat()):
        raise HTTPException(
            status_code=403,
            detail=("This loan is over three years old and still owes money, so it is due to be written "
                    "off at year end. No re-loan can be given on it. / तीन साल पुराने बकाया कर्ज़ पर नया "
                    "कर्ज़ नहीं दिया जा सकता।"),
        )
    await assert_no_old_debt(loan.get("kyc_id"), people=people)
    # A net-off pays the old balance out of the new loan. A balance bigger than the
    # new loan booked the difference as cash received that nobody paid.
    if data.net_off and outstanding > float(data.new_disbursement_amount) + 0.01:
        raise HTTPException(
            status_code=400,
            detail=(f"The old loan still owes ₹{outstanding:,.2f}, more than the new loan of "
                    f"₹{float(data.new_disbursement_amount):,.2f}, so it cannot be netted off. / पुराना बकाया "
                    f"नए कर्ज़ से ज़्यादा है।"),
        )

    if data.net_off and outstanding > 0:
        # Every unpaid instalment becomes netoff. The note a user had written on
        # it is kept aside and restored if the re-loan is deleted; it used to be
        # overwritten with the net-off text and lost.
        sets = {
            "status": "closed",
            "netoff_closed": True,
            "netoff_date": data.loan_date,
            "reloan_id": new_id,
            "updated_at": now,
        }
        for i, row in enumerate(schedule):
            if row.get("status") == "paid":
                continue
            sets[f"emi_schedule.{i}.status"] = "netoff"
            sets[f"emi_schedule.{i}.pre_netoff_note"] = row.get("note") or ""
            sets[f"emi_schedule.{i}.note"] = f"Net-off: closed via re-loan on {data.loan_date}"
        claim = await db.loans.update_one(
            {"_id": oid, "netoff_closed": {"$ne": True}, "is_gyal": {"$ne": True}}, {"$set": sets}
        )
        if claim.modified_count == 0:
            raise HTTPException(status_code=409, detail="This loan has just changed. Refresh the page and try again.")
        netoff_amount = outstanding
    else:
        await db.loans.update_one({"_id": oid}, {"$set": {"reloan_id": new_id, "updated_at": now}})

    try:
        pb = (kyc or {}).get("primary_borrower") or {}
        if not isinstance(pb, dict):
            pb = {}
        loan_date_obj = date_type.fromisoformat(data.loan_date)
        emi_amount, new_schedule = _build_emi_schedule(data.new_disbursement_amount, loan_date_obj)
        loan_number = await generate_loan_number(customer_id, kyc_id or loan_id)

        new_loan_doc = {
            "_id": new_oid,
            "kyc_id": kyc_id,
            "customer_id": customer_id,
            "loan_number": loan_number,
            "relative_name": pb.get("relative_name") or "",
            "relative_name_hindi": pb.get("relative_name_hindi") or "",
            "client_name": loan.get("client_name"),
            "client_name_hindi": pb.get("name_hindi") or "",
            "client_phone": phone or loan.get("client_phone"),
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
            "people": people,
            "is_reloan": True,
            "parent_loan_id": loan_id,
            "netoff_amount": netoff_amount,
            "net_disbursement_amount": data.new_disbursement_amount - netoff_amount,
            "created_at": now,
            "updated_at": now,
        }
        await _insert_loan(new_loan_doc, customer_id, kyc_id or loan_id)
        loan_number = new_loan_doc["loan_number"]

        await book_loan_disbursement(new_loan_doc, current_user["id"], current_user["name"])

        # The net-off settlement: Dr Cash / Cr Loans Portfolio for the amount rolled
        # over. Its reference_id is the NEW loan, so deleting the re-loan removes it.
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
    except Exception:
        # Anything failing after the parent was claimed — a loan-number clash, a
        # booking error — used to leave the old loan closed with no re-loan behind
        # it and no way back. Undo everything this request did, then report.
        await db.loans.delete_one({"_id": new_oid})
        await db.journal_entries.delete_many({"reference_id": new_id})
        await _release_netoff_parent(oid, new_id)
        # The claim overwrote the parent's pointer to an earlier re-loan; put it
        # back rather than leave it blank. Releasing a net-off has already removed
        # the pointer, so match "missing" as well as this request's own id.
        pointer_filter = {"_id": oid, "$or": [{"reloan_id": new_id}, {"reloan_id": {"$exists": False}}]}
        if previous_reloan_id:
            await db.loans.update_one(pointer_filter, {"$set": {"reloan_id": previous_reloan_id}})
        else:
            await db.loans.update_one({"_id": oid, "reloan_id": new_id}, {"$unset": {"reloan_id": ""}})
        raise

    # The client's record is updated only once the re-loan has gone through; a
    # failed re-loan used to leave its phone and co-borrower changes behind.
    if kyc:
        kyc_updates = {}
        if phone:
            kyc_updates["primary_borrower.phone"] = phone
        if co_borrower:
            co_data = {k: v for k, v in co_borrower.items() if v is not None}
            only_phone = set(k for k, v in co_data.items() if v not in ("", [], None)) <= {"phone", "phone_history"}
            if co_data and only_phone and isinstance(kyc.get("co_borrower"), dict):
                # Replacing the whole co-borrower with {phone} lost their name and Aadhaar.
                if co_data.get("phone"):
                    kyc_updates["co_borrower.phone"] = co_data["phone"]
            elif co_data:
                kyc_updates["co_borrower"] = co_data
        if guarantor:
            g_data = {k: v for k, v in guarantor.items() if v is not None}
            if g_data:
                kyc_updates["guarantor"] = g_data
        if kyc_updates:
            kyc_updates["updated_at"] = now
            await db.kycs.update_one({"_id": kyc["_id"]}, {"$set": kyc_updates})

    return _doc(new_loan_doc)


def _closing_query(illaka_id: str, cutoff_iso: str) -> dict:
    # A net-off-closed loan's balance lives in its re-loan, so it is never written
    # off; nor is a loan that owes nothing (checked per loan, below and in preview).
    #
    # Status is not trusted: part-payments used to mark a loan "closed" with money
    # still owed, and the closing skipped it for good.
    #
    # The loan's age is read in Python (_old_enough): older records store dates as
    # "01/10/2025" or "20230110", which compared as text wrote off a 2025 loan and
    # never a real 2023 one.
    return {
        "illaka_id": illaka_id,
        "is_gyal": {"$ne": True},
        "netoff_closed": {"$ne": True},
    }


def _made_by(loan: dict, moment: str, precise: bool = True) -> bool:
    """Whether the loan existed at `moment`. Without an exact moment (a closing
    record from an older version, dated only by its id) compare whole seconds."""
    made = str(loan.get("created_at") or "")
    return made <= moment if precise else made[:19] <= moment[:19]


def _old_enough(loan: dict, cutoff_iso: str) -> bool:
    day = _day(loan.get("loan_date"))
    return bool(day) and day <= cutoff_iso


def _owes_something(loan: dict) -> bool:
    return float(loan.get("total_repayable") or 0) - paid_so_far(loan) >= OWED_TOLERANCE


def _paid_after(loan: dict, closing_date: str) -> float:
    """Collections on this loan dated after the closing date."""
    return round(sum(float(e.get("paid_amount") or 0) for e in loan.get("emi_schedule", [])
                     if e.get("status") == "paid" and _day(e.get("paid_date")) > closing_date), 2)


def _owed_at(loan: dict, closing_date: str) -> float:
    """What the client owed at the end of the closing date.

    The write-off used to take what was owed at the moment the closing RAN. A
    closing for 31 March run in April left out April's collections, so the year's
    bad debt was understated and those collections were counted twice once the
    loan was Gyal.
    """
    return round(float(loan.get("total_repayable") or 0) - paid_so_far(loan)
                 + _paid_after(loan, closing_date), 2)


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
    closing_date = _normalise_closing_date(closing_date)
    closing_date_obj = date_type.fromisoformat(closing_date)
    cutoff = _add_months(closing_date_obj, -36)
    loans = await db.loans.find(_closing_query(illaka_id, cutoff.isoformat()), {
        "client_name": 1, "loan_number": 1, "loan_date": 1,
        "total_repayable": 1, "total_paid": 1, "emi_schedule": 1,
    }).to_list(None)
    # The same filter the closing applies, so the preview count matches.
    loans = [ln for ln in loans if _old_enough(ln, cutoff.isoformat()) and _owed_at(ln, closing_date) >= OWED_TOLERANCE]
    rows = []
    for loan_item in loans[:200]:
        outstanding = max(0.0, _owed_at(loan_item, closing_date))
        rows.append({
            "loan_number": loan_item.get("loan_number") or "—",
            "client_name": loan_item.get("client_name") or "—",
            "loan_date": loan_item.get("loan_date") or "—",
            "outstanding": outstanding,
        })
    return {"count": len(loans), "loans": rows, "cutoff_date": cutoff.isoformat()}


@router.post("/loans/year-end-closing")
async def year_end_closing(data: YearEndClosingRequest, request: Request):
    """Mark eligible loans as Gyal and create write-off journal entries. Always records a closing entry."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin or Maalik can perform year-end closing")
    closing_date = _normalise_closing_date(data.closing_date)
    # A closing dated in the future wrote loans off at once, and every recovery
    # was then refused as "dated before the write-off" until that date came.
    if closing_date > date_type.today().isoformat():
        raise HTTPException(status_code=400, detail="A year-end closing cannot be dated in the future.")
    # One closing or undo at a time per illaka. An undo overlapping a closing (of
    # the same date or a later one) left write-offs no closing record owned, or
    # let a qualifying loan escape. The lock is refreshed every few seconds while
    # the closing runs, so after a restart it is released as soon as it goes stale.
    async with entity_lock(f"closing:{data.illaka_id}", wait=30, stale=180, busy=BUSY_ILLAKA):
        return await _year_end_closing(data.illaka_id, closing_date, current_user)


async def _year_end_closing(illaka_id: str, closing_date: str, current_user: dict):
    now = datetime.now(timezone.utc).isoformat()
    closing_date_obj = date_type.fromisoformat(closing_date)

    # Running a closing for a date that already has one finishes it. A closing
    # used to stop at the first loan it could not lock, leaving some loans written
    # off, a record showing none, and a retry refused as "already exists". Every
    # step is per loan and conditional, so running again only picks up the rest.
    #
    # Closings go in date order. Once a later year is closed, an earlier date can
    # be neither created nor re-run: re-running an older date wrote new loans off
    # into a year already closed, where undoing the later closing could not reach
    # them. Undo the later closing first.
    newer = await db.illaka_closings.find_one({"illaka_id": illaka_id, "closing_date": {"$gt": closing_date}})
    if newer:
        raise HTTPException(
            status_code=400,
            detail=(f"A later year-end closing ({newer['closing_date']}) already exists for this Illaka. "
                    f"Undo it first. / पहले बाद वाला समापन वापस लें।"),
        )
    # The closing is recorded BEFORE its loans are listed. Listing them first let a
    # change slip in while the list was being built — an uncollect passed the
    # closed-year check because no closing existed yet, and that loan was never
    # written off. Once the record exists, the closed year refuses such changes.
    existing_closing = await db.illaka_closings.find_one({"illaka_id": illaka_id, "closing_date": closing_date})
    if existing_closing:
        claim_id = existing_closing["_id"]
    else:
        try:
            claim_id = (await db.illaka_closings.insert_one({
                "illaka_id": illaka_id,
                "closing_date": closing_date,
                "gyal_count": 0,
                "created_by_id": current_user["id"],
                "created_by_name": current_user["name"],
                "created_at": now,
            })).inserted_id
        except DuplicateKeyError:
            existing_closing = await db.illaka_closings.find_one({"illaka_id": illaka_id, "closing_date": closing_date})
            claim_id = existing_closing["_id"]

    heads = await db.account_heads.find(
        {"system_key": {"$in": ["loans_portfolio", "bad_debt_written_off", "gyal_wasool"]}}
    ).to_list(10)
    head_map = {h["system_key"]: h for h in heads}
    portfolio_id = str(head_map["loans_portfolio"]["_id"]) if "loans_portfolio" in head_map else ""
    cutoff = _add_months(closing_date_obj, -36)
    fields = {"_id": 1, "kyc_id": 1, "total_paid": 1, "total_repayable": 1, "emi_schedule": 1, "writeoff_pending": 1,
              "loan_date": 1}

    record = existing_closing or await db.illaka_closings.find_one({"_id": claim_id})
    # A closing record written by an older version may have no created_at; its id
    # still carries the moment it was created.
    recorded_at = str((record or {}).get("created_at") or "") or (
        claim_id.generation_time.isoformat() if isinstance(claim_id, ObjectId) else now)

    async def _qualifying() -> list:
        # Only loans that existed when this closing was first run. A loan added
        # later — an opening balance imported afterwards — belongs to the next
        # closing; writing it off here put a new entry into a closed year.
        return [c for c in await db.loans.find(_closing_query(illaka_id, cutoff.isoformat()),
                                               dict(fields, created_at=1)).to_list(None)
                if _old_enough(c, cutoff.isoformat()) and _owed_at(c, closing_date) >= OWED_TOLERANCE
                and _made_by(c, recorded_at, precise=bool((record or {}).get("created_at")))]

    async def _booked(loan_ref) -> float:
        entries = await db.journal_entries.find(
            {"reference_id": loan_ref, "entry_type": "gyal_writeoff"}, {"total_amount": 1}).to_list(None)
        return round(sum(float(j.get("total_amount") or 0) for j in entries), 2)

    async def _unfinished() -> list:
        """Loans of this closing that a restart, or a half-done undo, left incomplete:
        still marked mid-write-off, missing their write-off entry, or with later
        collections still booked to the portfolio."""
        out = []
        for g in await db.loans.find({"illaka_id": illaka_id, "is_gyal": True, "gyal_since": closing_date},
                                     fields).to_list(None):
            ref = _id_ci(str(g["_id"]))
            # Written off for less than it owed at the closing date: a restart
            # before the entry, an undo stopped part-way, or a closing made by an
            # older version, which wrote off only what was owed when it ran.
            if (g.get("writeoff_pending")
                    or await _booked(ref) < _owed_at(g, closing_date) - 0.01
                    or (portfolio_id and await db.journal_entries.find_one(
                        {"reference_id": ref, "entry_type": "emi_collection",
                         "date": {"$gt": closing_date + "\uffff"}, "lines.account_head_id": portfolio_id},
                        {"_id": 1}))):
                out.append(g)
        return out

    first_pass = await _qualifying() + await _unfinished()
    if existing_closing and not first_pass:
        # A restart after the last write-off but before the count was saved left
        # the history showing 0; bring it up to date before saying it is done.
        await db.illaka_closings.update_one({"_id": claim_id}, {"$set": {"gyal_count": await db.loans.count_documents(
            {"illaka_id": illaka_id, "is_gyal": True, "gyal_since": closing_date})}})
        # Nothing left to finish: running the same closing again used to report
        # success, and the screen listed the date twice.
        raise HTTPException(
            status_code=409,
            detail=f"The year-end closing for {closing_date} has already been done. / यह समापन पहले ही हो चुका है।",
        )

    count = 0
    finished = 0
    skipped = []

    async def _move_later_collections(loan: dict) -> None:
        """Rebook collections dated after the closing date as Gyal recoveries.

        They reduced the portfolio when collected; the write-off is now the
        balance as at the closing date, so from then on the money is recovery
        income — exactly as if it had been collected after the write-off. Undo
        moves them back. Rewriting an entry already rewritten changes nothing.
        """
        if "loans_portfolio" not in head_map or "gyal_wasool" not in head_map:
            return
        portfolio_id = str(head_map["loans_portfolio"]["_id"])
        async for je in db.journal_entries.find({
            "reference_id": _id_ci(str(loan["_id"])), "entry_type": "emi_collection",
            "date": {"$gt": closing_date + "\uffff"}, "lines.account_head_id": portfolio_id,
        }):
            lines = je.get("lines", [])
            new_lines = [_make_head_line(head_map["gyal_wasool"], float(l.get("debit") or 0), float(l.get("credit") or 0))
                         if l.get("account_head_id") == portfolio_id else l for l in lines]
            await db.journal_entries.update_one(
                {"_id": je["_id"], "lines": lines},
                {"$set": {"lines": new_lines,
                          "narration": (je.get("narration") or "").replace("EMI collected from", "Gyal Wasool from", 1),
                          "reclassified_on_closing": closing_date, "updated_at": now}},
            )

    async def _write_off(cand) -> str:
        loan = await db.loans.find_one({"_id": cand["_id"]})
        if not loan:
            return ""
        ref = _id_ci(str(loan["_id"]))
        if loan.get("is_gyal") and loan.get("gyal_since") == closing_date:
            # Written off by this closing already, but left incomplete. Finish it:
            # the entry is booked unless it exists, and later collections move to
            # recovery. An undo stopped part-way is finished the same way — or by
            # running the undo again.
            result = "finished"
            # Book whatever is missing up to what it owed at the closing date.
            outstanding = round(max(0.0, _owed_at(loan, closing_date) - await _booked(ref)), 2)
        elif (loan.get("is_gyal") or loan.get("netoff_closed")
                or _owed_at(loan, closing_date) < OWED_TOLERANCE):
            return ""
        else:
            result = "marked"
            outstanding = _owed_at(loan, closing_date)
            await db.loans.update_one(
                {"_id": loan["_id"]},
                {"$set": {"is_gyal": True, "gyal_since": closing_date, "updated_at": now,
                          "status": loan_status(loan),
                          "writeoff_pending": True, "writeoff_amount": outstanding}},
            )
        await _move_later_collections(loan)
        if "loans_portfolio" in head_map and "bad_debt_written_off" in head_map and outstanding > 0:
            await create_journal_entry_internal(
                illaka_id=illaka_id,
                date=closing_date,
                narration=f"Gyal Write-off: {loan.get('client_name', '')} | Loan# {loan.get('loan_number', '')}",
                lines=[
                    _make_head_line(head_map["bad_debt_written_off"], outstanding, 0.0),
                    _make_head_line(head_map["loans_portfolio"], 0.0, outstanding),
                ],
                entry_type="gyal_writeoff",
                reference_id=str(loan["_id"]),
                created_by_id=current_user["id"],
                created_by_name=current_user["name"],
            )
        await db.loans.update_one({"_id": loan["_id"]}, {"$unset": {"writeoff_pending": "", "writeoff_amount": ""}})
        return result

    async def _process(cands) -> None:
        nonlocal count, finished
        for cand in cands:
            # Each loan is written off under its own lock, from a fresh read. A loan
            # that stays busy is skipped and reported, not allowed to stop the rest —
            # the locks are acquired before anything is written, so a skipped loan is
            # untouched.
            try:
                async with loan_lock(str(cand["_id"]), wait=30), kyc_lock(cand.get("kyc_id"), wait=30):
                    result = await _write_off(cand)
                    count += result == "marked"
                    finished += result == "finished"
            except HTTPException:
                skipped.append(str(cand["_id"]))
            except Exception:
                logging.getLogger(__name__).exception("Year-end closing failed on loan %s", cand["_id"])
                skipped.append(str(cand["_id"]))

    await _process(first_pass)
    # A second look catches a loan that started owing while the first list was
    # being read — a change that had passed its closed-year check just before the
    # closing was recorded.
    seen = {c["_id"] for c in first_pass}
    await _process([c for c in await _qualifying() if c["_id"] not in seen])

    # The count is read from the loans, not accumulated: skips, resumes and
    # partial undos used to leave it wrong.
    await db.illaka_closings.update_one({"_id": claim_id}, {"$set": {"gyal_count": await db.loans.count_documents(
        {"illaka_id": illaka_id, "is_gyal": True, "gyal_since": closing_date})}})

    msg = f"{count} loan(s) marked as Gyal (Bad Debt)" if count > 0 else "Year-end closing recorded. No loans qualified for Gyal."
    if finished:
        msg += f". {finished} loan(s) left unfinished earlier were completed"
    if skipped:
        msg += (f". {len(skipped)} loan(s) were being updated and were not closed — run the closing "
                f"for the same date again to finish.")
    return {"marked_count": count, "skipped": skipped, "message": msg}


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
    closing_date = _normalise_closing_date(data.closing_date)
    async with entity_lock(f"closing:{data.illaka_id}", wait=30, stale=180, busy=BUSY_ILLAKA):
        return await _year_end_closing_undo(data, closing_date, current_user)


async def _year_end_closing_undo(data: YearEndUndoRequest, closing_date: str, current_user: dict):

    closing_record = await db.illaka_closings.find_one(
        {"illaka_id": data.illaka_id, "closing_date": closing_date}
    )
    if not closing_record:
        raise HTTPException(status_code=404, detail="No closing record found for the specified date")

    newer = await db.illaka_closings.find_one({
        "illaka_id": data.illaka_id,
        "closing_date": {"$gt": closing_date},
    })
    if newer:
        raise HTTPException(
            status_code=400,
            detail="Cannot undo: a more recent year-end closing exists for this illaka. Undo that first.",
        )

    # Both heads are needed to move recoveries back into the portfolio. Refuse
    # before anything is changed — carrying on without them deleted the
    # write-off but left every recovery booked as income.
    gyal_head = await db.account_heads.find_one({"system_key": "gyal_wasool"})
    portfolio_head = (await _get_system_heads()).get("loans_portfolio")
    if not gyal_head or not portfolio_head:
        raise HTTPException(
            status_code=400,
            detail=("The Gyal Wasool or Loans Portfolio account head is missing, so recoveries "
                    "could not be moved back into the portfolio. Nothing was changed."),
        )
    gyal_head_id = str(gyal_head["_id"])
    now = datetime.now(timezone.utc).isoformat()

    async def _move_recoveries(loan_id_str: str) -> tuple:
        """Rewrite every Gyal Wasool credit on this loan's collections as Loans Portfolio.

        Money collected while the loan was written off was booked Dr Cash /
        Cr Gyal Wasool. With the write-off reversed the loan is back in the
        portfolio at its full balance, so that money has to reduce the
        portfolio, exactly as an ordinary collection does.

        Every such line moves, whole. Recoveries can no longer exceed what the
        client owed (collection refuses it), so there is never an excess to
        split — and splitting was what made later uncollects and edits drift the
        books, because they rebook a recovery whole.

        Rewriting a line that has already been rewritten changes nothing, so
        this is safe to run twice, concurrently, or again after a failure.
        """
        moved, amount = 0, 0.0
        entries = await db.journal_entries.find({
            "reference_id": _id_ci(loan_id_str),
            "entry_type": "emi_collection",
            "lines.account_head_id": gyal_head_id,
        }).to_list(None)
        for je in entries:
            lines = je.get("lines", [])
            credit = round(sum(float(l.get("credit") or 0) for l in lines
                               if l.get("account_head_id") == gyal_head_id), 2)
            if credit <= 0:
                continue
            new_lines = []
            for line in lines:
                if line.get("account_head_id") == gyal_head_id:
                    new_lines.append(_make_head_line(
                        portfolio_head, float(line.get("debit") or 0), float(line.get("credit") or 0)
                    ))
                else:
                    new_lines.append(line)
            res = await db.journal_entries.update_one(
                {"_id": je["_id"], "lines": lines},
                {"$set": {
                    "lines": new_lines,
                    "narration": (je.get("narration") or "").replace(
                        "Gyal Wasool from", "EMI collected from", 1),
                    "reclassified_on_undo_of": closing_date,
                    "updated_at": now,
                }},
            )
            if res.modified_count:
                moved += 1
                amount += credit
        return moved, amount

    # Order matters so the undo can always be finished by running it again.
    #
    # The closing record used to be deleted FIRST, as a claim. When the request
    # then failed part-way, some loans were restored and others were still Gyal
    # with no closing left to undo — and one variant stranded write-off income
    # that nothing in the app could reach. Now every step is repeatable
    # (recoveries → write-off entries → flag), and the closing record is removed
    # LAST, only once every loan is done. A second, concurrent undo repeats the
    # same steps and changes nothing.
    loans_to_undo = await db.loans.find(
        {"illaka_id": data.illaka_id, "is_gyal": True, "gyal_since": closing_date}
    ).to_list(None)
    count = 0
    moved_entries = 0
    moved_amount = 0.0
    skipped = []
    for loan in loans_to_undo:
        loan_id_str = str(loan["_id"])
        # Under the loan's lock no recovery can be collected or edited while its
        # entries are being moved and the flag flipped — one landing in between
        # used to be booked as income on a loan that was no longer Gyal. A loan
        # that stays busy is skipped and reported; running the undo again finishes.
        try:
            lock = loan_lock(loan_id_str, wait=30)
            await lock.__aenter__()
        except HTTPException:
            skipped.append(loan_id_str)
            continue
        try:
            m, a = await _move_recoveries(loan_id_str)
            moved_entries += m
            moved_amount += a
            await db.journal_entries.delete_many({
                "entry_type": "gyal_writeoff",
                "reference_id": _id_ci(loan_id_str),
            })
            flipped = await db.loans.update_one(
                {"_id": loan["_id"], "is_gyal": True, "gyal_since": closing_date},
                {"$set": {"is_gyal": False, "updated_at": now}, "$unset": {"gyal_since": ""}},
            )
            if flipped.modified_count:
                count += 1
        finally:
            await lock.__aexit__(None, None, None)

    remaining = await db.loans.count_documents(
        {"illaka_id": data.illaka_id, "is_gyal": True, "gyal_since": closing_date})
    if remaining:
        await db.illaka_closings.update_one(
            {"illaka_id": data.illaka_id, "closing_date": closing_date}, {"$set": {"gyal_count": remaining}})
        msg = (f"{count} loan(s) restored from Gyal. {remaining} loan(s) were being updated and are still "
               f"written off — run the undo again to finish.")
    else:
        await db.illaka_closings.delete_one({"illaka_id": data.illaka_id, "closing_date": closing_date})
        msg = (f"{count} loan(s) restored from Gyal. Closing record removed." if count > 0
               else "Year-end closing record removed (no Gyal loans to undo).")
    if moved_entries:
        msg += (f" {moved_entries} recovery entr(y/ies) totalling {moved_amount:,.2f} moved "
                f"from Bad Debt Recovery back to Loans Portfolio.")
    return {
        "undone_count": count,
        "skipped": skipped,
        "reclassified_recoveries": moved_entries,
        "reclassified_amount": round(moved_amount, 2),
        "message": msg,
    }
