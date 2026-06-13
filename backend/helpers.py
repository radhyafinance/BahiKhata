import re
import calendar
import logging
from datetime import datetime, timezone, date as date_type
from bson import ObjectId
from core.database import db


def _doc(d: dict) -> dict:
    d = dict(d)
    d["id"] = str(d.pop("_id"))
    return d


async def generate_customer_id(illaka_name: str) -> str:
    """Generate Customer ID: 2 uppercase letters from Illaka + 4-digit sequential per prefix."""
    prefix = re.sub(r'[^A-Za-z]', '', illaka_name)[:2].upper()
    if len(prefix) < 2:
        prefix = (prefix + 'XX')[:2]
    last = await db.kycs.find_one(
        {"customer_id": {"$regex": f"^{re.escape(prefix)}\\d{{4}}$"}},
        sort=[("customer_id", -1)]
    )
    num = 1
    if last and last.get("customer_id"):
        try:
            num = int(last["customer_id"][len(prefix):]) + 1
        except (ValueError, IndexError):
            num = 1
    return f"{prefix}{num:04d}"


async def generate_loan_number(customer_id: str, kyc_id: str) -> str:
    """Generate Loan ID: {customer_id}-L{n} sequential per customer."""
    count = await db.loans.count_documents({"kyc_id": kyc_id})
    return f"{customer_id}-L{count + 1}"


def _add_months(dt: date_type, months: int) -> date_type:
    m = dt.month - 1 + months
    year = dt.year + m // 12
    month = m % 12 + 1
    # Clamp to last valid day of the target month (handles Jan 31 → Feb 28, etc.)
    last_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))


def _apply_overdue_to_schedule(schedule: list) -> bool:
    today = date_type.today()
    changed = False
    for item in schedule:
        if item["status"] == "pending":
            y, mo = map(int, item["due_month"].split("-"))
            last_day = calendar.monthrange(y, mo)[1]
            if today > date_type(y, mo, last_day):
                item["status"] = "overdue"
                changed = True
    return changed


def _get_loan_status(schedule: list) -> str:
    if not schedule:
        return "active"
    if all(e["status"] in ("paid", "netoff") for e in schedule):
        return "closed"
    if any(e["status"] == "overdue" for e in schedule):
        return "overdue"
    return "active"


def _build_emi_schedule(principal: float, loan_date: date_type) -> tuple:
    """Returns (emi_amount, schedule_list).
    Formula: total = principal * 120/103 (interest = principal * 17/103), EMI rounded to nearest ₹10.
    """
    emi_amount = round(principal * 120 / 103 / 12 / 10) * 10
    schedule = []
    for i in range(12):
        due = _add_months(loan_date, i + 1)
        schedule.append({
            "month": i + 1,
            "due_month": due.strftime("%Y-%m"),
            "amount": emi_amount,
            "status": "pending",
            "paid_amount": 0.0,
            "paid_date": None,
            "collected_by_id": None,
            "collected_by_name": None,
        })
    _apply_overdue_to_schedule(schedule)
    return emi_amount, schedule


async def _get_maalik_illaka_ids(user: dict) -> list:
    """Return all illaka IDs accessible to a Maalik: owned (maalik_id) + admin-assigned."""
    owned = await db.illakas.find({"maalik_id": user["id"]}, {"_id": 1}).to_list(1000)
    ids = {str(ill["_id"]) for ill in owned}
    ids.update(user.get("assigned_illaka_ids", []))
    return list(ids)


async def get_admin_maalik_filter_ids(maalik_user_id: str) -> list:
    """For Admin use: given a maalik user ID, return all Illaka IDs that belong to them."""
    try:
        maalik_user = await db.users.find_one({"_id": ObjectId(maalik_user_id)})
        if not maalik_user:
            return []
        owned = await db.illakas.find({"maalik_id": maalik_user_id}, {"_id": 1}).to_list(1000)
        ids = {str(ill["_id"]) for ill in owned}
        ids.update(maalik_user.get("assigned_illaka_ids", []))
        return list(ids)
    except Exception:
        return []


async def _kyc_query_for_user(user: dict) -> dict:
    query = {}
    if user["role"] == "admin":
        pass  # No filter — sees all data
    elif user["role"] == "maalik":
        illaka_ids = await _get_maalik_illaka_ids(user)
        query["illaka_id"] = {"$in": illaka_ids}
    elif user["role"] in ("muneem", "sadar_muneem"):
        assigned = user.get("assigned_illaka_ids", [])
        query["illaka_id"] = {"$in": assigned}
    else:  # sipahi
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            query["field_officer_id"] = user["id"]
        else:
            query["illaka_id"] = {"$in": assigned}
    return query


async def create_journal_entry_internal(
    illaka_id: str,
    date: str,
    narration: str,
    lines: list,
    entry_type: str = "manual",
    reference_id: str = None,
    created_by_id: str = None,
    created_by_name: str = None,
    **extra_fields,
) -> str:
    """Insert a balanced double-entry journal entry. Returns the new entry's id."""
    now = datetime.now(timezone.utc).isoformat()
    total_amount = sum(float(line.get("debit", 0)) for line in lines)
    doc = {
        "date": date,
        "illaka_id": illaka_id,
        "narration": narration,
        "entry_type": entry_type,
        "reference_id": reference_id,
        "lines": lines,
        "total_amount": total_amount,
        "created_by_id": created_by_id,
        "created_by_name": created_by_name,
        "created_at": now,
        "updated_at": now,
    }
    doc.update(extra_fields)
    result = await db.journal_entries.insert_one(doc)
    return str(result.inserted_id)


async def _loan_query_for_user(user: dict) -> dict:
    if user["role"] == "admin":
        return {}
    elif user["role"] == "maalik":
        ids = await _get_maalik_illaka_ids(user)
        return {"illaka_id": {"$in": ids}}
    elif user["role"] == "muneem":
        assigned = user.get("assigned_illaka_ids", [])
        return {"illaka_id": {"$in": assigned}}
    elif user["role"] == "sadar_muneem":
        assigned = user.get("assigned_illaka_ids", [])
        return {"illaka_id": {"$in": assigned}}
    else:  # sipahi
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            return {"sipahi_id": user["id"]}
        return {"illaka_id": {"$in": assigned}}


def _make_head_line(head: dict, debit: float, credit: float) -> dict:
    return {
        "account_head_id": str(head["_id"]),
        "account_head_name": head.get("name", ""),
        "group_name": head.get("group_name", ""),
        "group_type": head.get("group_type", ""),
        "debit": debit,
        "credit": credit,
    }


async def _get_system_heads() -> dict:
    heads = await db.account_heads.find(
        {"system_key": {"$in": ["cash_in_hand", "loans_portfolio", "interest_income"]}}
    ).to_list(10)
    return {h["system_key"]: h for h in heads}


async def book_loan_disbursement(loan_doc: dict, user_id: str, user_name: str) -> None:
    """Create the journal entry for a loan disbursement.
    MFI rule: Interest = Principal × 17 / 103 (recognised upfront at disbursement).
    Entry: Dr Loans Portfolio (P+I) | Cr Cash (P) | Cr Interest Income (I)
    Safe to call from any route.
    """
    try:
        sys_heads = await _get_system_heads()
        if "loans_portfolio" not in sys_heads or "cash_in_hand" not in sys_heads:
            return
        principal = float(loan_doc.get("principal_amount", 0))
        interest = round(principal * 17 / 103, 2)
        total_outstanding = round(principal + interest, 2)
        lines = [
            _make_head_line(sys_heads["loans_portfolio"], total_outstanding, 0.0),
            _make_head_line(sys_heads["cash_in_hand"], 0.0, principal),
        ]
        if "interest_income" in sys_heads and interest > 0:
            lines.append(_make_head_line(sys_heads["interest_income"], 0.0, interest))
        await create_journal_entry_internal(
            illaka_id=loan_doc.get("illaka_id", ""),
            date=loan_doc.get("loan_date", ""),
            narration=f"Loan disbursed to {loan_doc.get('client_name', '')} | Loan# {loan_doc.get('loan_number', '')}",
            lines=lines,
            entry_type="loan_disbursement",
            reference_id=str(loan_doc.get("_id") or loan_doc.get("id") or ""),
            created_by_id=user_id,
            created_by_name=user_name,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Failed to book loan disbursement: {exc}")
