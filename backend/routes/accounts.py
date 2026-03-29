from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone, date as date_type
from typing import Optional, List
import uuid
from core.database import db
from core.auth import get_current_user
from helpers import _doc, create_journal_entry_internal
from models import (
    AccountHeadCreate, AccountHeadUpdate, JournalEntryCreate, SimpleEntryCreate,
    ExpenseTemplateCreate, ExpenseTemplateField, ExpenseSubmissionCreate,
)

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


@router.get("/accounts/entries/{entry_id}")
async def get_journal_entry(entry_id: str, request: Request):
    """Fetch a single journal entry by ID."""
    await get_current_user(request)
    try:
        entry = await db.journal_entries.find_one({"_id": ObjectId(entry_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid entry ID")
    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return _doc(entry)


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


# ── Cash Book (two-column: Dr left, Cr right, EMIs grouped by Misal) ───────────

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

    cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
    if not cash_head:
        return {"month": month, "opening_balance": 0, "dr_sections": [], "cr_entries": [],
                "total_receipts": 0, "total_payments": 0, "closing_balance": 0}
    cash_head_id = str(cash_head["_id"])

    # Opening balance: cumulative cash before this month
    opening_query = dict(query)
    opening_query["date"] = {"$lt": f"{month}-01"}
    prev_entries = await db.journal_entries.find(opening_query).to_list(10000)
    opening_balance = 0.0
    for e in prev_entries:
        for line in e.get("lines", []):
            if line.get("account_head_id") == cash_head_id:
                opening_balance += float(line.get("debit", 0)) - float(line.get("credit", 0))

    entries = await db.journal_entries.find(query).sort("date", 1).to_list(2000)
    dr_raw = []
    cr_raw = []
    running = opening_balance

    for entry in entries:
        for line in entry.get("lines", []):
            if line.get("account_head_id") == cash_head_id:
                cash_dr = float(line.get("debit", 0))
                cash_cr = float(line.get("credit", 0))
                running += cash_dr - cash_cr
                if cash_dr > 0:
                    dr_raw.append({
                        "entry_id": str(entry["_id"]),
                        "date": entry["date"],
                        "narration": entry.get("narration", ""),
                        "entry_type": entry.get("entry_type", "manual"),
                        "amount": cash_dr,
                        "balance": round(running, 2),
                        "misal_id": entry.get("misal_id", ""),
                        "misal_name": entry.get("misal_name", ""),
                        "client_name": entry.get("client_name", ""),
                        "loan_number": entry.get("loan_number", ""),
                    })
                if cash_cr > 0:
                    contra = [l for l in entry["lines"] if l.get("account_head_id") != cash_head_id]
                    cr_raw.append({
                        "entry_id": str(entry["_id"]),
                        "date": entry["date"],
                        "narration": entry.get("narration", ""),
                        "entry_type": entry.get("entry_type", "manual"),
                        "amount": cash_cr,
                        "contra_account": ", ".join(l.get("account_head_name", "") for l in contra),
                    })

    # Group EMI receipts by Misal for the left column
    emi_entries = [e for e in dr_raw if e["entry_type"] == "emi_collection"]
    other_dr = [e for e in dr_raw if e["entry_type"] != "emi_collection"]

    misal_map: dict = {}
    misal_order: list = []
    for e in emi_entries:
        mid = e.get("misal_id") or "no_misal"
        mname = e.get("misal_name") or "Unknown Misal"
        if mid not in misal_map:
            misal_map[mid] = {"misal_id": mid, "misal_name": mname, "total": 0.0, "entries": []}
            misal_order.append(mid)
        misal_map[mid]["total"] = round(misal_map[mid]["total"] + e["amount"], 2)
        misal_map[mid]["entries"].append(e)

    dr_sections = []
    if emi_entries:
        dr_sections.append({
            "type": "emi_group",
            "label": "EMI Collections",
            "total": round(sum(e["amount"] for e in emi_entries), 2),
            "misals": [misal_map[m] for m in misal_order],
        })
    for e in other_dr:
        dr_sections.append({"type": "regular", **e})

    total_receipts = round(sum(e["amount"] for e in dr_raw), 2)
    total_payments = round(sum(e["amount"] for e in cr_raw), 2)
    return {
        "month": month,
        "opening_balance": round(opening_balance, 2),
        "dr_sections": dr_sections,
        "cr_entries": cr_raw,
        "total_receipts": total_receipts,
        "total_payments": total_payments,
        "closing_balance": round(running if (dr_raw or cr_raw) else opening_balance, 2),
    }


# ── Bid (Monthly Aggregate Cashbook) ──────────────────────────────────────────

@router.get("/accounts/bid")
async def get_bid(
    request: Request,
    illaka_id: Optional[str] = None,
    month: Optional[str] = None,
):
    """Monthly aggregate cashbook — one total row per category/head."""
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id)
    query["date"] = {"$regex": f"^{month}"}

    cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
    cash_head_id = str(cash_head["_id"]) if cash_head else None

    # Opening balance
    opening_query = dict(query)
    opening_query["date"] = {"$lt": f"{month}-01"}
    prev_entries = await db.journal_entries.find(opening_query).to_list(10000)
    opening_balance = 0.0
    if cash_head_id:
        for e in prev_entries:
            for line in e.get("lines", []):
                if line.get("account_head_id") == cash_head_id:
                    opening_balance += float(line.get("debit", 0)) - float(line.get("credit", 0))

    entries = await db.journal_entries.find(query).to_list(2000)

    # Collect all cash movements
    emi_misal_map: dict = {}
    emi_misal_order: list = []
    dr_head_map: dict = {}  # non-EMI income -> grouped by account head
    cr_head_map: dict = {}  # expenses
    total_dr = 0.0
    total_cr = 0.0

    for entry in entries:
        for line in entry.get("lines", []):
            if line.get("account_head_id") != cash_head_id:
                continue
            cash_dr = float(line.get("debit", 0))
            cash_cr = float(line.get("credit", 0))

            if cash_dr > 0:
                total_dr += cash_dr
                if entry.get("entry_type") == "emi_collection":
                    mid = entry.get("misal_id") or "no_misal"
                    mname = entry.get("misal_name") or "Unknown Misal"
                    if mid not in emi_misal_map:
                        emi_misal_map[mid] = {"misal_id": mid, "misal_name": mname, "total": 0.0}
                        emi_misal_order.append(mid)
                    emi_misal_map[mid]["total"] = round(emi_misal_map[mid]["total"] + cash_dr, 2)
                else:
                    # Other income receipts — group by contra account head
                    contra = [l for l in entry["lines"] if l.get("account_head_id") != cash_head_id]
                    for c in contra:
                        hid = c.get("account_head_id", "")
                        hname = c.get("account_head_name", "Other Income")
                        if hid not in dr_head_map:
                            dr_head_map[hid] = {"account_head_name": hname, "total": 0.0}
                        dr_head_map[hid]["total"] = round(dr_head_map[hid]["total"] + cash_dr, 2)

            if cash_cr > 0:
                total_cr += cash_cr
                contra = [l for l in entry["lines"] if l.get("account_head_id") != cash_head_id]
                for c in contra:
                    hid = c.get("account_head_id", "")
                    hname = c.get("account_head_name", "Other Expense")
                    gname = c.get("group_name", "")
                    if hid not in cr_head_map:
                        cr_head_map[hid] = {"account_head_name": hname, "group_name": gname, "total": 0.0}
                    cr_head_map[hid]["total"] = round(cr_head_map[hid]["total"] + cash_cr, 2)

    # Build dr_totals
    dr_totals = []
    if emi_misal_map:
        dr_totals.append({
            "type": "emi_total",
            "label": "EMI Collections",
            "total": round(sum(m["total"] for m in emi_misal_map.values()), 2),
            "misal_breakdown": [emi_misal_map[m] for m in emi_misal_order],
        })
    for h in dr_head_map.values():
        dr_totals.append({"type": "income", "label": h["account_head_name"], "total": h["total"]})

    cr_totals = sorted(cr_head_map.values(), key=lambda x: x["group_name"])

    closing = round(opening_balance + total_dr - total_cr, 2)
    return {
        "month": month,
        "opening_balance": round(opening_balance, 2),
        "dr_totals": dr_totals,
        "cr_totals": list(cr_totals),
        "total_dr": round(total_dr, 2),
        "total_cr": round(total_cr, 2),
        "closing_balance": closing,
    }


# ── Expense Templates (per Illaka, admin-managed) ─────────────────────────────

@router.get("/accounts/expense-templates")
async def get_expense_template(request: Request, illaka_id: str):
    await get_current_user(request)
    template = await db.expense_templates.find_one({"illaka_id": illaka_id, "is_active": True})
    if not template:
        return {"template": None, "illaka_id": illaka_id}
    return {"template": _doc(template)}


@router.post("/accounts/expense-templates")
async def upsert_expense_template(data: ExpenseTemplateCreate, request: Request):
    """Create or replace the expense template for an Illaka (admin only)."""
    current_user = await get_current_user(request)
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can manage expense templates")

    illaka = await db.illakas.find_one({"_id": ObjectId(data.illaka_id)})
    if not illaka:
        raise HTTPException(status_code=404, detail="Illaka not found")

    now = datetime.now(timezone.utc).isoformat()
    # Enrich fields with account head names and auto field_id
    enriched_fields = []
    for i, f in enumerate(data.fields):
        try:
            head = await db.account_heads.find_one({"_id": ObjectId(f.account_head_id)})
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid account head id: {f.account_head_id}")
        if not head:
            raise HTTPException(status_code=404, detail=f"Account head not found: {f.account_head_id}")
        enriched_fields.append({
            "field_id": f.field_id or str(uuid.uuid4()),
            "label": f.label,
            "account_head_id": f.account_head_id,
            "account_head_name": head["name"],
            "group_type": head.get("group_type", ""),
            "display_order": f.display_order if f.display_order else i,
        })

    doc = {
        "illaka_id": data.illaka_id,
        "illaka_name": illaka.get("name", ""),
        "fields": enriched_fields,
        "is_active": True,
        "created_by": current_user["id"],
        "updated_at": now,
    }

    existing = await db.expense_templates.find_one({"illaka_id": data.illaka_id})
    if existing:
        await db.expense_templates.update_one({"_id": existing["_id"]}, {"$set": doc})
        doc["_id"] = existing["_id"]
        doc["created_at"] = existing.get("created_at", now)
    else:
        doc["created_at"] = now
        result = await db.expense_templates.insert_one(doc)
        doc["_id"] = result.inserted_id

    return {"template": _doc(doc)}


# ── Expense Submissions (monthly, per Illaka) ─────────────────────────────────

@router.get("/accounts/expense-submissions")
async def get_expense_submission(request: Request, illaka_id: str, month: str):
    await get_current_user(request)
    sub = await db.expense_submissions.find_one({"illaka_id": illaka_id, "month": month})
    if not sub:
        return {"submission": None}
    return {"submission": _doc(sub)}


@router.post("/accounts/expense-submissions")
async def create_or_update_expense_submission(data: ExpenseSubmissionCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Freeze check for muneem
    if current_user["role"] == "muneem":
        today = date_type.today()
        current_month = f"{today.year}-{today.month:02d}"
        if data.month < current_month:
            raise HTTPException(status_code=403, detail="Past month submissions are frozen for Muneems")

    # Check for existing submission
    existing = await db.expense_submissions.find_one({"illaka_id": data.illaka_id, "month": data.month})
    if existing and existing.get("status") == "submitted" and current_user["role"] == "muneem":
        raise HTTPException(status_code=400, detail="This month's expense has already been submitted and locked")

    # Get template
    template = await db.expense_templates.find_one({"illaka_id": data.illaka_id, "is_active": True})
    if not template:
        raise HTTPException(status_code=404, detail="No expense template found for this Illaka. Ask admin to create one.")

    # Build field map from template
    field_map = {f["field_id"]: f for f in template.get("fields", [])}

    # Validate entries
    enriched_entries = []
    for e in data.entries:
        f = field_map.get(e.field_id)
        if not f:
            raise HTTPException(status_code=400, detail=f"Field {e.field_id} not found in template")
        enriched_entries.append({
            "field_id": e.field_id,
            "field_label": f["label"],
            "account_head_id": f["account_head_id"],
            "account_head_name": f.get("account_head_name", ""),
            "amount": float(e.amount),
        })

    total_amount = round(sum(e["amount"] for e in enriched_entries), 2)
    now = datetime.now(timezone.utc).isoformat()

    if data.action == "submit":
        # Create compound journal entry: Multi-Dr, One-Cr (Cash in Hand)
        cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
        if not cash_head:
            raise HTTPException(status_code=500, detail="Cash in Hand account not found")

        lines = []
        for e in enriched_entries:
            if float(e["amount"]) > 0:
                head = await db.account_heads.find_one({"_id": ObjectId(e["account_head_id"])})
                lines.append({
                    "account_head_id": e["account_head_id"],
                    "account_head_name": e.get("account_head_name", ""),
                    "group_name": head.get("group_name", "") if head else "",
                    "group_type": head.get("group_type", "") if head else "",
                    "debit": float(e["amount"]),
                    "credit": 0.0,
                })
        if lines:
            lines.append({
                "account_head_id": str(cash_head["_id"]),
                "account_head_name": cash_head["name"],
                "group_name": cash_head.get("group_name", ""),
                "group_type": cash_head.get("group_type", ""),
                "debit": 0.0,
                "credit": total_amount,
            })
            illaka_doc = await db.illakas.find_one({"_id": ObjectId(data.illaka_id)})
            illaka_name = illaka_doc.get("name", "") if illaka_doc else ""
            entry_id = await create_journal_entry_internal(
                illaka_id=data.illaka_id,
                date=f"{data.month}-01",  # First of the month as date
                narration=f"Monthly Expense Sheet — {illaka_name} — {data.month}",
                lines=lines,
                entry_type="expense_sheet",
                created_by_id=current_user["id"],
                created_by_name=current_user["name"],
            )
        else:
            entry_id = None

        doc = {
            "template_id": str(template["_id"]),
            "illaka_id": data.illaka_id,
            "illaka_name": template.get("illaka_name", ""),
            "month": data.month,
            "entries": enriched_entries,
            "total_amount": total_amount,
            "status": "submitted",
            "journal_entry_id": entry_id,
            "submitted_by_id": current_user["id"],
            "submitted_by_name": current_user["name"],
            "submitted_at": now,
            "updated_at": now,
        }
        if existing:
            await db.expense_submissions.update_one({"_id": existing["_id"]}, {"$set": doc})
            doc["_id"] = existing["_id"]
            doc["created_at"] = existing.get("created_at", now)
        else:
            doc["created_at"] = now
            result = await db.expense_submissions.insert_one(doc)
            doc["_id"] = result.inserted_id
        return {"submission": _doc(doc), "message": "Expense sheet submitted and journal entry created"}

    else:  # draft
        doc = {
            "template_id": str(template["_id"]),
            "illaka_id": data.illaka_id,
            "illaka_name": template.get("illaka_name", ""),
            "month": data.month,
            "entries": enriched_entries,
            "total_amount": total_amount,
            "status": "draft",
            "journal_entry_id": None,
            "updated_at": now,
        }
        if existing:
            await db.expense_submissions.update_one({"_id": existing["_id"]}, {"$set": doc})
            doc["_id"] = existing["_id"]
            doc["created_at"] = existing.get("created_at", now)
        else:
            doc["created_at"] = now
            result = await db.expense_submissions.insert_one(doc)
            doc["_id"] = result.inserted_id
        return {"submission": _doc(doc), "message": "Draft saved"}


@router.delete("/accounts/expense-submissions/{sub_id}")
async def delete_expense_submission(sub_id: str, request: Request):
    """Admin can delete a submission to allow re-submission."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin/Maalik can delete submissions")
    try:
        sub = await db.expense_submissions.find_one({"_id": ObjectId(sub_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid submission ID")
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    # Also delete the journal entry if it was created
    if sub.get("journal_entry_id"):
        try:
            await db.journal_entries.delete_one({"_id": ObjectId(sub["journal_entry_id"])})
        except Exception:
            pass
    await db.expense_submissions.delete_one({"_id": ObjectId(sub_id)})
    return {"message": "Submission deleted. Muneem can re-submit now."}


@router.patch("/accounts/expense-submissions/{sub_id}/unlock")
async def unlock_expense_submission(sub_id: str, request: Request):
    """Admin/Maalik unlocks a submitted expense sheet back to draft so Muneem can re-edit."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only Admin/Maalik can unlock submissions")
    try:
        sub = await db.expense_submissions.find_one({"_id": ObjectId(sub_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid submission ID")
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.get("status") != "submitted":
        raise HTTPException(status_code=400, detail="Submission is not in submitted state")
    # Delete the associated journal entry
    if sub.get("journal_entry_id"):
        try:
            await db.journal_entries.delete_one({"_id": ObjectId(sub["journal_entry_id"])})
        except Exception:
            pass
    now = datetime.now(timezone.utc).isoformat()
    await db.expense_submissions.update_one(
        {"_id": ObjectId(sub_id)},
        {"$set": {
            "status": "draft",
            "journal_entry_id": None,
            "unlocked_by_id": current_user["id"],
            "unlocked_by_name": current_user["name"],
            "unlocked_at": now,
            "updated_at": now,
        }}
    )
    updated = await db.expense_submissions.find_one({"_id": ObjectId(sub_id)})
    return {"submission": _doc(updated), "message": "Expense sheet unlocked. Muneem can now re-edit and re-submit."}


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
