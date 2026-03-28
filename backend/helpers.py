import re, calendar
from datetime import date as date_type
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
    return dt.replace(year=dt.year + m // 12, month=m % 12 + 1)


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
    """Returns (emi_amount, schedule_list)."""
    emi_amount = round(principal * 1.17 / 12 / 100) * 100
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


async def _kyc_query_for_user(user: dict) -> dict:
    query = {}
    if user["role"] == "admin":
        pass
    elif user["role"] == "maalik":
        illakas = await db.illakas.find({"maalik_id": user["id"]}, {"_id": 1}).to_list(1000)
        illaka_ids = [str(ill["_id"]) for ill in illakas]
        query["illaka_id"] = {"$in": illaka_ids}
    elif user["role"] == "muneem":
        assigned = user.get("assigned_illaka_ids", [])
        query["illaka_id"] = {"$in": assigned}
    else:  # sipahi
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            query["field_officer_id"] = user["id"]
        else:
            query["illaka_id"] = {"$in": assigned}
    return query


async def _loan_query_for_user(user: dict) -> dict:
    if user["role"] == "admin":
        return {}
    elif user["role"] == "maalik":
        illakas = await db.illakas.find({"maalik_id": user["id"]}, {"_id": 1}).to_list(1000)
        ids = [str(i["_id"]) for i in illakas]
        return {"illaka_id": {"$in": ids}}
    elif user["role"] == "muneem":
        assigned = user.get("assigned_illaka_ids", [])
        return {"illaka_id": {"$in": assigned}}
    else:  # sipahi
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            return {"sipahi_id": user["id"]}
        return {"illaka_id": {"$in": assigned}}
