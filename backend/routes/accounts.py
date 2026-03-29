from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone, date as date_type
from typing import Optional
from core.database import db
from core.auth import get_current_user
from helpers import _doc, create_journal_entry_internal
from models import AccountHeadCreate, AccountHeadUpdate, JournalEntryCreate, SimpleEntryCreate

router = APIRouter()


async def _illaka_filter_for_user(user: dict, illaka_id: Optional[str]) -> dict:
    """Return query fragment to restrict journal entries by user's accessible illakas."""
    query = {}
    if user["role"] == "admin":
        if illaka_id:
            query["illaka_id"] = illaka_id
    elif user["role"] == "maalik":
        illakas = await db.illakas.find({"maalik_id": user["id"]}, {"_id": 1}).to_list(1000)
        ids = [str(i["_id"]) for i in illakas]
        if illaka_id:
            if illaka_id not in ids:
                query["illaka_id"] = "__none__"
            else:
                query["illaka_id"] = illaka_id
        else:
            query["illaka_id"] = {"$in": ids}
    elif user["role"] == "muneem":
        assigned = user.get("assigned_illaka_ids", [])
        if illaka_id:
            query["illaka_id"] = illaka_id if illaka_id in assigned else "__none__"
        else:
            query["illaka_id"] = {"$in": assigned}
    return query


async def _enrich_lines(lines: list) -> list:
    enriched = []
    for line in lines:
        head_id = line.get("account_head_id")
        try:
            head = await db.account_heads.find_one({"_id": ObjectId(head_id)})
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid account head id: {head_id}")
        if not head:
            raise HTTPException(status_code=404, detail=f"Account head {head_id} not found")
        enriched.append({
            "account_head_id": head_id,
            "account_head_name": head["name"],
            "group_name": head.get("group_name", ""),
            "group_type": head.get("group_type", ""),
            "debit": float(line.get("debit", 0)),
            "credit": float(line.get("credit", 0)),
        })
    return enriched


# ── Account Groups ─────────────────────────────────────────────────────────────

@router.get("/accounts/groups")
async def get_account_groups(request: Request):
    await get_current_user(request)
    groups = await db.account_groups.find({}).sort("display_order", 1).to_list(100)
    return [_doc(g) for g in groups]


# ── Account Heads ──────────────────────────────────────────────────────────────

@router.get("/accounts/heads")
async def get_account_heads(
    request: Request,
    group_type: Optional[str] = None,
    is_active: Optional[bool] = None,
):
    await get_current_user(request)
    query = {}
    if group_type:
        query["group_type"] = group_type
    if is_active is not None:
        query["is_active"] = is_active
    else:
        query["is_active"] = True
    heads = await db.account_heads.find(query).sort([("group_name", 1), ("name", 1)]).to_list(500)
    return [_doc(h) for h in heads]


@router.post("/accounts/heads")
async def create_account_head(data: AccountHeadCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can create account heads")
    try:
        group = await db.account_groups.find_one({"_id": ObjectId(data.group_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid group ID")
    if not group:
        raise HTTPException(status_code=404, detail="Account group not found")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "name": data.name,
        "group_id": data.group_id,
        "group_name": group["name"],
        "group_type": group["type"],
        "is_system": False,
        "system_key": None,
        "is_active": True,
        "created_by": current_user["id"],
        "created_at": now,
    }
    result = await db.account_heads.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc(doc)


@router.put("/accounts/heads/{head_id}")
async def update_account_head(head_id: str, data: AccountHeadUpdate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can update account heads")
    try:
        head = await db.account_heads.find_one({"_id": ObjectId(head_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid head ID")
    if not head:
        raise HTTPException(status_code=404, detail="Account head not found")
    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.is_active is not None:
        if head.get("is_system") and not data.is_active:
            raise HTTPException(status_code=400, detail="System account heads cannot be deactivated")
        updates["is_active"] = data.is_active
    if updates:
        await db.account_heads.update_one({"_id": ObjectId(head_id)}, {"$set": updates})
    return _doc(await db.account_heads.find_one({"_id": ObjectId(head_id)}))


@router.delete("/accounts/heads/{head_id}")
async def delete_account_head(head_id: str, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete account heads")
    try:
        head = await db.account_heads.find_one({"_id": ObjectId(head_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid head ID")
    if not head:
        raise HTTPException(status_code=404, detail="Account head not found")
    if head.get("is_system"):
        raise HTTPException(status_code=400, detail="System account heads cannot be deleted")
    usage = await db.journal_entries.count_documents({"lines.account_head_id": head_id})
    if usage > 0:
        raise HTTPException(
            status_code=400,
            detail=f"This head is used in {usage} journal entries and cannot be deleted. Deactivate it instead."
        )
    await db.account_heads.delete_one({"_id": ObjectId(head_id)})
    return {"message": "Account head deleted"}


# ── Journal Entries ────────────────────────────────────────────────────────────

@router.get("/accounts/entries")
async def list_entries(
    request: Request,
    illaka_id: Optional[str] = None,
    month: Optional[str] = None,
    entry_type: Optional[str] = None,
    limit: int = 200,
    skip: int = 0,
):
    current_user = await get_current_user(request)
    query = await _illaka_filter_for_user(current_user, illaka_id)
    if month:
        query["date"] = {"$regex": f"^{month}"}
    if entry_type:
        query["entry_type"] = entry_type
    total = await db.journal_entries.count_documents(query)
    docs = await db.journal_entries.find(query).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "entries": [_doc(d) for d in docs]}


@router.post("/accounts/entries")
async def create_journal_entry(data: JournalEntryCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin and Maalik can create full journal entries")
    lines_raw = [{"account_head_id": l.account_head_id, "debit": l.debit, "credit": l.credit} for l in data.lines]
    total_dr = sum(l["debit"] for l in lines_raw)
    total_cr = sum(l["credit"] for l in lines_raw)
    if abs(total_dr - total_cr) > 0.01:
        raise HTTPException(status_code=400, detail=f"Entry is not balanced: Dr ₹{total_dr:.2f} ≠ Cr ₹{total_cr:.2f}")
    enriched = await _enrich_lines(lines_raw)
    entry_id = await create_journal_entry_internal(
        illaka_id=data.illaka_id, date=data.date, narration=data.narration,
        lines=enriched, entry_type="manual",
        created_by_id=current_user["id"], created_by_name=current_user["name"],
    )
    return _doc(await db.journal_entries.find_one({"_id": ObjectId(entry_id)}))


@router.post("/accounts/entries/expense")
async def create_simple_entry(data: SimpleEntryCreate, request: Request):
    """Simplified Income/Expense entry — Muneem, Maalik, Admin."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Freeze check for muneem
    if current_user["role"] == "muneem":
        today = date_type.today()
        current_month = f"{today.year}-{today.month:02d}"
        if data.date[:7] < current_month:
            raise HTTPException(status_code=403, detail="Past month entries are frozen for Muneems / पिछले महीने के एंट्री बंद हैं")

    try:
        expense_head = await db.account_heads.find_one({"_id": ObjectId(data.account_head_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid account head ID")
    if not expense_head:
        raise HTTPException(status_code=404, detail="Account head not found")

    cash_head_id = data.cash_head_id
    if not cash_head_id:
        cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
        if not cash_head:
            raise HTTPException(status_code=500, detail="Cash in Hand account not seeded")
        cash_head_id = str(cash_head["_id"])

    group_type = expense_head.get("group_type", "")
    if group_type == "expense":
        lines_raw = [
            {"account_head_id": data.account_head_id, "debit": data.amount, "credit": 0.0},
            {"account_head_id": cash_head_id, "debit": 0.0, "credit": data.amount},
        ]
    elif group_type == "income":
        lines_raw = [
            {"account_head_id": cash_head_id, "debit": data.amount, "credit": 0.0},
            {"account_head_id": data.account_head_id, "debit": 0.0, "credit": data.amount},
        ]
    else:
        raise HTTPException(status_code=400, detail="Selected account is not an income or expense head")

    enriched = await _enrich_lines(lines_raw)
    entry_id = await create_journal_entry_internal(
        illaka_id=data.illaka_id, date=data.date, narration=data.narration,
        lines=enriched, entry_type="expense_voucher",
        created_by_id=current_user["id"], created_by_name=current_user["name"],
    )
    return _doc(await db.journal_entries.find_one({"_id": ObjectId(entry_id)}))


@router.put("/accounts/entries/{entry_id}")
async def update_journal_entry(entry_id: str, data: SimpleEntryCreate, request: Request):
    """Edit a simple entry (expense_voucher or manual)."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        entry = await db.journal_entries.find_one({"_id": ObjectId(entry_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entry ID")
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    if entry.get("entry_type") in ("loan_disbursement", "emi_collection"):
        raise HTTPException(status_code=400, detail="Auto-generated entries cannot be edited")

    if current_user["role"] == "muneem":
        today = date_type.today()
        current_month = f"{today.year}-{today.month:02d}"
        if entry["date"][:7] < current_month:
            raise HTTPException(status_code=403, detail="Past month entries are frozen for Muneems")

    try:
        expense_head = await db.account_heads.find_one({"_id": ObjectId(data.account_head_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid account head ID")
    if not expense_head:
        raise HTTPException(status_code=404, detail="Account head not found")

    cash_head_id = data.cash_head_id
    if not cash_head_id:
        cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
        cash_head_id = str(cash_head["_id"]) if cash_head else None

    group_type = expense_head.get("group_type", "")
    if group_type == "expense":
        lines_raw = [
            {"account_head_id": data.account_head_id, "debit": data.amount, "credit": 0.0},
            {"account_head_id": cash_head_id, "debit": 0.0, "credit": data.amount},
        ]
    elif group_type == "income":
        lines_raw = [
            {"account_head_id": cash_head_id, "debit": data.amount, "credit": 0.0},
            {"account_head_id": data.account_head_id, "debit": 0.0, "credit": data.amount},
        ]
    else:
        raise HTTPException(status_code=400, detail="Selected account is not an income or expense head")

    enriched = await _enrich_lines(lines_raw)
    now = datetime.now(timezone.utc).isoformat()
    await db.journal_entries.update_one(
        {"_id": ObjectId(entry_id)},
        {"$set": {
            "date": data.date, "narration": data.narration,
            "lines": enriched, "total_amount": data.amount,
            "updated_at": now,
        }}
    )
    return _doc(await db.journal_entries.find_one({"_id": ObjectId(entry_id)}))


@router.delete("/accounts/entries/{entry_id}")
async def delete_journal_entry(entry_id: str, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin and Maalik can delete entries")
    try:
        entry = await db.journal_entries.find_one({"_id": ObjectId(entry_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entry ID")
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    await db.journal_entries.delete_one({"_id": ObjectId(entry_id)})
    return {"message": "Entry deleted"}


# ── Cash Book ──────────────────────────────────────────────────────────────────

@router.get("/accounts/cashbook")
async def get_cashbook(
    request: Request,
    illaka_id: Optional[str] = None,
    month: Optional[str] = None,
):
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id)
    query["date"] = {"$regex": f"^{month}"}

    # Opening balance: sum of all cash movements before this month
    cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
    if not cash_head:
        return {"month": month, "entries": [], "opening_balance": 0, "total_receipts": 0, "total_payments": 0, "closing_balance": 0}
    cash_head_id = str(cash_head["_id"])

    opening_query = dict(query)
    opening_query["date"] = {"$lt": f"{month}-01"}
    prev_entries = await db.journal_entries.find(opening_query).to_list(10000)
    opening_balance = 0.0
    for e in prev_entries:
        for line in e.get("lines", []):
            if line.get("account_head_id") == cash_head_id:
                opening_balance += float(line.get("debit", 0)) - float(line.get("credit", 0))

    entries = await db.journal_entries.find(query).sort("date", 1).to_list(2000)
    rows = []
    running = opening_balance
    for entry in entries:
        for line in entry.get("lines", []):
            if line.get("account_head_id") == cash_head_id:
                cash_dr = float(line.get("debit", 0))
                cash_cr = float(line.get("credit", 0))
                running += cash_dr - cash_cr
                contra = [l for l in entry["lines"] if l.get("account_head_id") != cash_head_id]
                contra_names = ", ".join(l.get("account_head_name", "") for l in contra)
                rows.append({
                    "entry_id": str(entry["_id"]),
                    "date": entry["date"],
                    "narration": entry.get("narration", ""),
                    "contra_account": contra_names,
                    "entry_type": entry.get("entry_type", "manual"),
                    "receipts": cash_dr,
                    "payments": cash_cr,
                    "balance": round(running, 2),
                    "created_by_name": entry.get("created_by_name", ""),
                })

    total_receipts = sum(r["receipts"] for r in rows)
    total_payments = sum(r["payments"] for r in rows)
    return {
        "month": month,
        "opening_balance": round(opening_balance, 2),
        "entries": rows,
        "total_receipts": round(total_receipts, 2),
        "total_payments": round(total_payments, 2),
        "closing_balance": round(running if rows else opening_balance, 2),
    }


# ── Monthly P&L Summary ────────────────────────────────────────────────────────

@router.get("/accounts/summary")
async def get_monthly_summary(
    request: Request,
    illaka_id: Optional[str] = None,
    month: Optional[str] = None,
):
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id)
    query["date"] = {"$regex": f"^{month}"}

    entries = await db.journal_entries.find(query).to_list(2000)
    head_totals: dict = {}
    for entry in entries:
        for line in entry.get("lines", []):
            hid = line.get("account_head_id")
            if hid not in head_totals:
                head_totals[hid] = {
                    "account_head_id": hid,
                    "account_head_name": line.get("account_head_name", ""),
                    "group_name": line.get("group_name", ""),
                    "group_type": line.get("group_type", ""),
                    "total_debit": 0.0, "total_credit": 0.0,
                }
            head_totals[hid]["total_debit"] += float(line.get("debit", 0))
            head_totals[hid]["total_credit"] += float(line.get("credit", 0))

    income_heads = sorted(
        [h for h in head_totals.values() if h["group_type"] == "income"],
        key=lambda x: x["group_name"]
    )
    expense_heads = sorted(
        [h for h in head_totals.values() if h["group_type"] == "expense"],
        key=lambda x: x["group_name"]
    )
    # For income: net = credit - debit (normal balance is credit)
    total_income = sum(h["total_credit"] - h["total_debit"] for h in income_heads)
    # For expenses: net = debit - credit (normal balance is debit)
    total_expense = sum(h["total_debit"] - h["total_credit"] for h in expense_heads)

    return {
        "month": month,
        "income": income_heads,
        "expenses": expense_heads,
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "net_profit": round(total_income - total_expense, 2),
    }
