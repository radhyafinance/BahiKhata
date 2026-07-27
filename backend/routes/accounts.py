from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone, date as date_type
from typing import Optional, List
import uuid, re
from core.database import db
from core.auth import get_current_user
from helpers import (_doc, create_journal_entry_internal, _get_maalik_illaka_ids,
                     get_admin_maalik_filter_ids, apply_illaka_scope, permitted_illaka_ids)
from models import (
    AccountHeadCreate, AccountHeadUpdate, JournalEntryCreate, SimpleEntryCreate,
    ExpenseTemplateCreate, ExpenseTemplateField, ExpenseSubmissionCreate,
    OpeningBalanceLine, OpeningBalanceCreate,
)

router = APIRouter()


async def _illaka_filter_for_user(user: dict, illaka_id: Optional[str], maalik_id: Optional[str] = None) -> dict:
    """Return query fragment to restrict journal entries by user's accessible illakas."""
    query = {}
    if user["role"] in ("admin", "sadar_muneem"):
        if illaka_id:
            query["illaka_id"] = illaka_id
        elif maalik_id and user["role"] == "admin":
            ids = await get_admin_maalik_filter_ids(maalik_id)
            query["illaka_id"] = {"$in": ids}
    elif user["role"] == "maalik":
        ids = await _get_maalik_illaka_ids(user)
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
    else:
        # sipahi — and any role added later. This used to fall through with an
        # empty query, i.e. NO filter at all, so a sipahi saw every illaka's
        # books without even asking for them. Default to deny.
        assigned = user.get("assigned_illaka_ids", []) or []
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
    maalik_id: Optional[str] = None,
    month: Optional[str] = None,
    entry_type: Optional[str] = None,
    limit: int = 200,
    skip: int = 0,
):
    current_user = await get_current_user(request)
    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)
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
    maalik_id: Optional[str] = None,
    month: Optional[str] = None,
):
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)
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

    # Live misal name lookup to reflect any renames
    _unique_misal_ids = list({e.get("misal_id") for e in entries if e.get("misal_id")})
    _misal_name_map: dict = {}
    if _unique_misal_ids:
        try:
            _moids = [ObjectId(i) for i in _unique_misal_ids]
            _raw = await db.misals.find({"_id": {"$in": _moids}}, {"_id": 1, "name": 1}).to_list(500)
            _misal_name_map = {str(d["_id"]): d["name"] for d in _raw}
        except Exception:
            pass

    dr_raw = []
    cr_raw = []
    running = opening_balance

    for entry in entries:
        for line in entry.get("lines", []):
            if line.get("account_head_id") == cash_head_id:
                cash_dr = float(line.get("debit", 0))
                cash_cr = float(line.get("credit", 0))
                running += cash_dr - cash_cr
                _mid = entry.get("misal_id", "")
                if cash_dr > 0:
                    dr_raw.append({
                        "entry_id": str(entry["_id"]),
                        "date": entry["date"],
                        "narration": entry.get("narration", ""),
                        "entry_type": entry.get("entry_type", "manual"),
                        "amount": cash_dr,
                        "balance": round(running, 2),
                        "misal_id": _mid,
                        "misal_name": _misal_name_map.get(_mid) or entry.get("misal_name", ""),
                        "client_name": entry.get("client_name", ""),
                        "loan_number": entry.get("loan_number", ""),
                    })
                if cash_cr > 0:
                    contra = [l for l in entry["lines"] if l.get("account_head_id") != cash_head_id]
                    # Keep the contra head's identity so payments can be grouped
                    # into an "Expenses" section (total + breakup) below.
                    _exp = next((l for l in contra if l.get("group_type") == "expense"), None)
                    cr_raw.append({
                        "entry_id": str(entry["_id"]),
                        "date": entry["date"],
                        "narration": entry.get("narration", ""),
                        "entry_type": entry.get("entry_type", "manual"),
                        "amount": cash_cr,
                        "contra_account": ", ".join(l.get("account_head_name", "") for l in contra),
                        "expense_head_id": (_exp or {}).get("account_head_id", ""),
                        "expense_head_name": (_exp or {}).get("account_head_name", ""),
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
    # An opening-balance entry belongs at the TOP of the receipts side, the way a
    # cash book reads ("To Balance b/d" first). It used to fall in with the other
    # entries after the EMI group and so rendered at the very bottom.
    ob_dr = [e for e in other_dr if e["entry_type"] == "opening_balance"]
    other_dr = [e for e in other_dr if e["entry_type"] != "opening_balance"]
    for e in ob_dr:
        dr_sections.append({"type": "regular", **e})
    if emi_entries:
        dr_sections.append({
            "type": "emi_group",
            "label": "EMI Collections",
            "total": round(sum(e["amount"] for e in emi_entries), 2),
            "misals": [misal_map[m] for m in misal_order],
        })
    for e in other_dr:
        dr_sections.append({"type": "regular", **e})

    # ── Payments side: roll expenses up into one section with a breakup ────────
    exp_rows = [e for e in cr_raw if e.get("expense_head_id")]
    non_exp = [e for e in cr_raw if not e.get("expense_head_id")]
    cr_sections = []
    for e in non_exp:
        cr_sections.append({"type": "regular", **e})
    if exp_rows:
        head_map: dict = {}
        head_order: list = []
        for e in exp_rows:
            hid = e["expense_head_id"]
            if hid not in head_map:
                head_map[hid] = {"head_id": hid, "head_name": e["expense_head_name"], "total": 0.0, "entries": []}
                head_order.append(hid)
            head_map[hid]["total"] = round(head_map[hid]["total"] + e["amount"], 2)
            head_map[hid]["entries"].append(e)
        cr_sections.append({
            "type": "expense_group",
            "label": "Expenses",
            "total": round(sum(e["amount"] for e in exp_rows), 2),
            "heads": [head_map[h] for h in head_order],
        })

    total_receipts = round(sum(e["amount"] for e in dr_raw), 2)
    total_payments = round(sum(e["amount"] for e in cr_raw), 2)
    return {
        "month": month,
        "opening_balance": round(opening_balance, 2),
        "dr_sections": dr_sections,
        "cr_entries": cr_raw,
        "cr_sections": cr_sections,
        "total_receipts": total_receipts,
        "total_payments": total_payments,
        "closing_balance": round(running if (dr_raw or cr_raw) else opening_balance, 2),
    }


# ── Bid (Monthly Aggregate Cashbook) ──────────────────────────────────────────

def _allocate_cash_to_contra(contra_lines: list, cash_amount: float, side: str) -> list:
    """Split one entry's cash movement across its contra heads.

    Returns [(line, amount), …] whose amounts sum to exactly `cash_amount`.

    The Bid used to add the FULL cash amount to EVERY contra head, so a single
    ₹2,000 receipt split over two heads was reported as ₹4,000 — overstating
    receipts and, because closing = opening + Jama − Kharch, handing the next
    month a wrong opening figure. Each head must instead take only its own share.

    `side` is the column the contra lines carry: "credit" for a cash receipt
    (Dr Cash / Cr heads), "debit" for a cash payment (Cr Cash / Dr heads).

    Amounts are taken from the lines themselves and normalised so the side still
    totals the actual cash moved. For a balanced entry the weights already sum to
    the cash amount and normalising is a no-op; for a mixed entry (cash receipt
    plus an expense in the same voucher) it keeps the Bid's closing balance equal
    to the real cash position instead of drifting.
    """
    if not contra_lines or cash_amount <= 0:
        return []

    other = "debit" if side == "credit" else "credit"
    weights = [float(l.get(side, 0) or 0) for l in contra_lines]
    if sum(weights) <= 0:
        # Degenerate entry — fall back to the opposite column, then to an even split.
        weights = [float(l.get(other, 0) or 0) for l in contra_lines]
    if sum(weights) <= 0:
        weights = [1.0] * len(contra_lines)

    total_w = sum(weights)
    out = []
    for line, w in zip(contra_lines, weights):
        out.append([line, round(cash_amount * w / total_w, 2)])

    # Push any rounding remainder onto the largest share so the column still
    # totals the cash actually moved.
    drift = round(cash_amount - sum(a for _, a in out), 2)
    if drift:
        out.sort(key=lambda p: -p[1])
        out[0][1] = round(out[0][1] + drift, 2)

    return [(l, a) for l, a in out if a > 0]


@router.get("/accounts/bid")
async def get_bid(
    request: Request,
    illaka_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
    month: Optional[str] = None,
):
    """Monthly aggregate Bahi Khata (Bid) — MFI format.

    Jama (Dr / Left):
      - EMI Collections: full amount received, grouped by Misal
      - Interest Income: interest booked from loans disbursed THIS month (recognised at disbursement)
      - Other cash receipts

    Kharch (Cr / Right):
      - Loans Portfolio: total outstanding (Principal + Interest) of loans disbursed this month
      - Other expenses / payments

    Closing balance = Opening + Jama total - Kharch total
    (equivalent to actual cash position because the interest maths cancel out)
    """
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)
    query["date"] = {"$regex": f"^{month}"}

    cash_head = await db.account_heads.find_one({"system_key": "cash_in_hand"})
    cash_head_id = str(cash_head["_id"]) if cash_head else None

    # Opening balance (cumulative cash position before this month)
    opening_query = dict(query)
    opening_query["date"] = {"$lt": f"{month}-01"}
    prev_entries = await db.journal_entries.find(opening_query).to_list(10000)
    opening_balance = 0.0
    if cash_head_id:
        for e in prev_entries:
            for line in e.get("lines", []):
                if line.get("account_head_id") == cash_head_id:
                    opening_balance += float(line.get("debit", 0)) - float(line.get("credit", 0))
        # An opening-balance entry dated INSIDE this month is the month's opening
        # cash, not a receipt. It is skipped in the transaction loop below, so
        # fold it in here — otherwise this month's closing understates the cash
        # and the next month opens on a different figure than this one closed.
        ob_this_month = await db.journal_entries.find(
            {**query, "entry_type": "opening_balance"}
        ).to_list(100)
        for e in ob_this_month:
            for line in e.get("lines", []):
                if line.get("account_head_id") == cash_head_id:
                    opening_balance += float(line.get("debit", 0)) - float(line.get("credit", 0))

    entries = await db.journal_entries.find(query).to_list(2000)

    # Live misal name lookup to reflect any renames
    _unique_misal_ids_bid = list({e.get("misal_id") for e in entries if e.get("misal_id")})
    _misal_name_map_bid: dict = {}
    if _unique_misal_ids_bid:
        try:
            _moids = [ObjectId(i) for i in _unique_misal_ids_bid]
            _raw = await db.misals.find({"_id": {"$in": _moids}}, {"_id": 1, "name": 1}).to_list(500)
            _misal_name_map_bid = {str(d["_id"]): d["name"] for d in _raw}
        except Exception:
            pass

    emi_misal_map: dict = {}
    emi_misal_order: list = []
    dr_head_map: dict = {}   # non-EMI dr items (interest income, other receipts)
    cr_head_map: dict = {}   # loans portfolio + expenses

    for entry in entries:
        entry_type = entry.get("entry_type", "manual")
        lines = entry.get("lines", [])

        # ── EMI Collections ──────────────────────────────────────────────────
        if entry_type == "emi_collection":
            cash_dr = sum(
                float(l.get("debit", 0))
                for l in lines if l.get("account_head_id") == cash_head_id
            )
            if cash_dr > 0:
                mid = entry.get("misal_id") or "no_misal"
                mname = _misal_name_map_bid.get(mid) or entry.get("misal_name") or "Unknown Misal"
                if mid not in emi_misal_map:
                    emi_misal_map[mid] = {"misal_id": mid, "misal_name": mname, "total": 0.0}
                    emi_misal_order.append(mid)
                emi_misal_map[mid]["total"] = round(emi_misal_map[mid]["total"] + cash_dr, 2)

        # ── Loan Disbursements ───────────────────────────────────────────────
        elif entry_type == "loan_disbursement":
            for line in lines:
                if line.get("account_head_id") == cash_head_id:
                    continue  # Skip cash line
                hid = line.get("account_head_id", "")
                hname = line.get("account_head_name", "")
                gname = line.get("group_name", "")
                gtype = line.get("group_type", "")
                line_dr = float(line.get("debit", 0))
                line_cr = float(line.get("credit", 0))

                if line_dr > 0:
                    # Loans Portfolio (asset Dr) → Kharch/Credit side of Bid (sort_order=0 → always first)
                    if hid not in cr_head_map:
                        cr_head_map[hid] = {"account_head_name": hname, "group_name": gname, "total": 0.0, "sort_order": 0}
                    cr_head_map[hid]["total"] = round(cr_head_map[hid]["total"] + line_dr, 2)

                if line_cr > 0 and gtype == "income":
                    # Interest Income (income Cr) → Jama/Debit side of Bid
                    if hid not in dr_head_map:
                        dr_head_map[hid] = {"account_head_name": hname, "total": 0.0}
                    dr_head_map[hid]["total"] = round(dr_head_map[hid]["total"] + line_cr, 2)

        # ── All Other Entries (expenses, manual, expense_sheet, gyal_writeoff…) ─
        else:
            # Skip opening_balance entries — they belong to BS/TB, not the Bid
            if entry_type == "opening_balance":
                continue
            cash_dr = sum(float(l.get("debit", 0)) for l in lines if l.get("account_head_id") == cash_head_id)
            cash_cr = sum(float(l.get("credit", 0)) for l in lines if l.get("account_head_id") == cash_head_id)

            contra = [l for l in lines if l.get("account_head_id") != cash_head_id]

            if cash_dr > 0:
                # Cash received → Jama/Debit side (group by contra head).
                # Each head takes its OWN share, not the whole receipt.
                for c, amt in _allocate_cash_to_contra(contra, cash_dr, "credit"):
                    hid = c.get("account_head_id", "")
                    hname = c.get("account_head_name", "Other Income")
                    if hid not in dr_head_map:
                        dr_head_map[hid] = {"account_head_name": hname, "total": 0.0}
                    dr_head_map[hid]["total"] = round(dr_head_map[hid]["total"] + amt, 2)

            if cash_cr > 0:
                # Cash paid → Kharch/Credit side, likewise split by contra share.
                for c, amt in _allocate_cash_to_contra(contra, cash_cr, "debit"):
                    hid = c.get("account_head_id", "")
                    hname = c.get("account_head_name", "Other Expense")
                    gname = c.get("group_name", "")
                    if hid not in cr_head_map:
                        cr_head_map[hid] = {
                            "account_head_name": hname, "group_name": gname,
                            "group_type": c.get("group_type", ""),
                            "total": 0.0, "sort_order": 1,
                        }
                    cr_head_map[hid]["total"] = round(cr_head_map[hid]["total"] + amt, 2)

    # ── Build response ──────────────────────────────────────────────────────
    dr_totals = []
    if emi_misal_map:
        dr_totals.append({
            "type": "emi_total",
            "label": "EMI Collections",
            "total": round(sum(m["total"] for m in emi_misal_map.values()), 2),
            "misal_breakdown": [emi_misal_map[m] for m in emi_misal_order],
        })
    for h in dr_head_map.values():
        if h["total"] > 0:
            dr_totals.append({"type": "income", "label": h["account_head_name"], "total": h["total"]})

    cr_totals = sorted(
        [h for h in cr_head_map.values() if h["total"] > 0],
        key=lambda x: (x.get("sort_order", 1), x["group_name"])
    )

    # Roll expense heads up into a single "Expenses" line carrying its own
    # breakup, so the Bid shows the total and the detail rather than a flat list.
    exp_heads = [h for h in cr_totals if h.get("group_type") == "expense"]
    cr_display = [h for h in cr_totals if h.get("group_type") != "expense"]
    if exp_heads:
        cr_display.append({
            "type": "expense_group",
            "account_head_name": "Expenses",
            "group_name": "Expenses",
            "total": round(sum(h["total"] for h in exp_heads), 2),
            "breakdown": [
                {"account_head_name": h["account_head_name"], "group_name": h["group_name"], "total": h["total"]}
                for h in sorted(exp_heads, key=lambda x: -x["total"])
            ],
        })

    total_dr = round(sum(item["total"] for item in dr_totals), 2)
    total_cr = round(sum(h["total"] for h in cr_totals), 2)
    closing = round(opening_balance + total_dr - total_cr, 2)

    return {
        "month": month,
        "opening_balance": round(opening_balance, 2),
        "dr_totals": dr_totals,
        "cr_totals": cr_display,
        "total_dr": total_dr,
        "total_cr": total_cr,
        "closing_balance": closing,
    }


# ── Trial Balance ──────────────────────────────────────────────────────────────

@router.get("/accounts/trial-balance")
async def get_trial_balance(
    request: Request,
    illaka_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
    month: Optional[str] = None,
):
    """Cumulative trial balance as of the last day of the selected month.
    Aggregates ALL journal entries from inception up to end of `month`.
    """
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)

    # Include everything up to (but not including) the first day of the NEXT month
    y, m = map(int, month.split("-"))
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    next_month_start = f"{next_y}-{next_m:02d}-01"
    query["date"] = {"$lt": next_month_start}

    entries = await db.journal_entries.find(query).to_list(50000)

    head_totals: dict = {}
    for entry in entries:
        for line in entry.get("lines", []):
            hid = line.get("account_head_id")
            if not hid:
                continue
            if hid not in head_totals:
                head_totals[hid] = {
                    "account_head_id": hid,
                    "account_head_name": line.get("account_head_name", ""),
                    "group_name": line.get("group_name", ""),
                    "group_type": line.get("group_type", ""),
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                }
            head_totals[hid]["total_debit"] += float(line.get("debit", 0))
            head_totals[hid]["total_credit"] += float(line.get("credit", 0))

    type_order = {"asset": 0, "liability": 1, "equity": 2, "income": 3, "expense": 4}
    rows = sorted(
        head_totals.values(),
        key=lambda x: (type_order.get(x["group_type"], 9), x["group_name"], x["account_head_name"])
    )
    for row in rows:
        row["total_debit"] = round(row["total_debit"], 2)
        row["total_credit"] = round(row["total_credit"], 2)
        row["net_balance"] = round(row["total_debit"] - row["total_credit"], 2)

    total_dr = round(sum(r["total_debit"] for r in rows), 2)
    total_cr = round(sum(r["total_credit"] for r in rows), 2)

    return {
        "month": month,
        "rows": list(rows),
        "total_debit": total_dr,
        "total_credit": total_cr,
        "is_balanced": abs(total_dr - total_cr) < 0.01,
    }


# ── Balance Sheet ───────────────────────────────────────────────────────────────

@router.get("/accounts/balance-sheet")
async def get_balance_sheet(
    request: Request,
    illaka_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
    month: Optional[str] = None,
):
    """Balance Sheet as of the last day of the selected month.
    Assets = Liabilities + Capital + Net Profit.
    Aasami Khata is computed from the loans collection (includes imported loans).
    Opening/Unrecorded Capital is derived as the balancing figure.
    """
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)
    y, m = map(int, month.split("-"))
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)
    next_month_start = f"{next_y}-{next_m:02d}-01"
    query["date"] = {"$lt": next_month_start}

    entries = await db.journal_entries.find(query).to_list(50000)

    # Find the loans_portfolio account head id so we can skip it from journal aggregation
    # (we replace it with the computed outstanding from the loans collection)
    lp_head = await db.account_heads.find_one({"system_key": "loans_portfolio"})
    lp_head_id = str(lp_head["_id"]) if lp_head else None

    head_totals: dict = {}
    for entry in entries:
        for line in entry.get("lines", []):
            hid = line.get("account_head_id")
            if not hid:
                continue
            # Skip loans_portfolio — replaced by computed Aasami Khata below
            if hid == lp_head_id:
                continue
            if hid not in head_totals:
                head_totals[hid] = {
                    "account_head_name": line.get("account_head_name", ""),
                    "group_name": line.get("group_name", ""),
                    "group_type": line.get("group_type", ""),
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                }
            head_totals[hid]["total_debit"] += float(line.get("debit", 0))
            head_totals[hid]["total_credit"] += float(line.get("credit", 0))

    # ── Compute Aasami Khata from loans collection ────────────────────────────
    # Outstanding = sum of (total_repayable - total_paid) for non-gyal active/overdue loans
    # that were disbursed on or before end of the selected month.
    # Scope by role FIRST, then narrow to any requested illaka. Previously an
    # explicit illaka_id short-circuited the role branches below it, so this
    # query — which is what produces the Aasami figure — ignored the caller's
    # permissions entirely.
    loan_query: dict = {"loan_date": {"$lt": next_month_start}}
    _allowed = await permitted_illaka_ids(current_user)
    if _allowed is not None:
        loan_query["illaka_id"] = {"$in": _allowed}
    await apply_illaka_scope(current_user, loan_query, illaka_id, maalik_id)

    loans = await db.loans.find(
        loan_query,
        {"total_repayable": 1, "total_paid": 1, "is_gyal": 1, "status": 1}
    ).to_list(50000)

    aasami_balance = round(sum(
        max(0.0, float(ln.get("total_repayable") or 0) - float(ln.get("total_paid") or 0))
        for ln in loans
        if not ln.get("is_gyal") and ln.get("status") in ("active", "overdue")
    ), 2)

    assets, liabilities, equity_items = [], [], []
    income_total = 0.0
    expense_total = 0.0

    for h in head_totals.values():
        dr = round(h["total_debit"], 2)
        cr = round(h["total_credit"], 2)
        gtype = h["group_type"]
        if gtype == "asset":
            assets.append({
                "account_head_name": h["account_head_name"],
                "group_name": h["group_name"],
                "amount": round(dr - cr, 2),
            })
        elif gtype == "liability":
            liabilities.append({
                "account_head_name": h["account_head_name"],
                "group_name": h["group_name"],
                "amount": round(cr - dr, 2),
            })
        elif gtype == "equity":
            equity_items.append({
                "account_head_name": h["account_head_name"],
                "group_name": h["group_name"],
                "amount": round(cr - dr, 2),
            })
        elif gtype == "income":
            income_total += round(cr - dr, 2)
        elif gtype == "expense":
            expense_total += round(dr - cr, 2)

    # Inject Aasami Khata as computed asset (always present, even if zero)
    assets.append({
        "account_head_name": "Aasami Khata (आसामी खाता)",
        "group_name": "Loans Portfolio",
        "amount": aasami_balance,
        "is_aasami_khata": True,
    })

    net_profit = round(income_total - expense_total, 2)
    total_assets = round(sum(a["amount"] for a in assets), 2)
    total_liabilities = round(sum(l["amount"] for l in liabilities), 2)
    total_equity = round(sum(e["amount"] for e in equity_items), 2)

    # Opening/Unrecorded Capital = balancing figure
    opening_capital = round(total_assets - total_liabilities - total_equity - net_profit, 2)

    assets.sort(key=lambda x: (0 if x.get("is_aasami_khata") else 1, x["group_name"]))
    liabilities.sort(key=lambda x: x["group_name"])
    equity_items.sort(key=lambda x: x["group_name"])

    total_capital_side = round(total_liabilities + total_equity + net_profit + opening_capital, 2)

    return {
        "month": month,
        "assets": assets,
        "liabilities": liabilities,
        "equity_items": equity_items,
        "net_profit": net_profit,
        "opening_capital": opening_capital,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "total_capital_side": total_capital_side,
        "is_balanced": abs(total_assets - total_capital_side) < 0.01,
    }


# ── Opening Balance ────────────────────────────────────────────────────────────


PARTY_GROUPS = {
    "debtor":   {"name": "Sundry Debtors",   "type": "asset",     "nature": "debit",  "display_order": 45},
    "creditor": {"name": "Sundry Creditors", "type": "liability", "nature": "credit", "display_order": 25},
}


async def _find_or_create_party_head(name: str, kind: str, created_by: str) -> dict:
    """Return the account head for a named sundry debtor/creditor, creating the
    head (and its group, first time round) if it doesn't exist yet.

    Matching is case-insensitive on the name within the group, so re-entering
    "Ramesh Traders" reuses the same head instead of duplicating the party.
    """
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Party name cannot be empty")
    spec = PARTY_GROUPS.get(kind)
    if not spec:
        raise HTTPException(status_code=400, detail=f"Unknown party kind: {kind}")

    group = await db.account_groups.find_one({"name": spec["name"]})
    if not group:
        res = await db.account_groups.insert_one({
            "name": spec["name"],
            "type": spec["type"],
            "nature": spec["nature"],
            "display_order": spec["display_order"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        group = await db.account_groups.find_one({"_id": res.inserted_id})

    existing = await db.account_heads.find_one({
        "group_name": spec["name"],
        "name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
    })
    if existing:
        if existing.get("is_active") is False:
            await db.account_heads.update_one({"_id": existing["_id"]}, {"$set": {"is_active": True}})
            existing["is_active"] = True
        return existing

    doc = {
        "name": name,
        "group_id": str(group["_id"]),
        "group_name": group["name"],
        "group_type": group["type"],
        "is_system": False,
        "system_key": None,
        "is_active": True,
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await db.account_heads.insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


@router.get("/accounts/aasami-balance")
async def get_aasami_balance(
    request: Request,
    illaka_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
    as_of: Optional[str] = None,
):
    """Total outstanding across client loans — the Aasami Khata figure used to
    pre-fill Loans Portfolio (Sundry Debtors) on the opening balance.

    `as_of` (YYYY-MM-DD) reconstructs the position on that date, which is what an
    opening balance needs: only loans disbursed on or before it count, and only
    payments received on or before it are deducted. Without it the figure would
    be today's balance posted against a back-dated opening entry.

    Gyal (written-off) loans are excluded — carried under Bad Debt, not the loan
    portfolio — but only if they were already written off by `as_of`.
    """
    current_user = await get_current_user(request)
    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)
    if as_of:
        query["loan_date"] = {"$lte": as_of}
    else:
        query["status"] = {"$in": ["active", "overdue"]}
        query["is_gyal"] = {"$ne": True}

    loans = await db.loans.find(
        query,
        {"total_repayable": 1, "total_paid": 1, "emi_schedule": 1,
         "is_gyal": 1, "gyal_since": 1, "status": 1},
    ).to_list(20000)

    as_of_ym = (as_of or "")[:7]
    total = 0.0
    counted = 0
    for ln in loans:
        if ln.get("is_gyal"):
            # Written off before the date → already out of the portfolio then.
            since = ln.get("gyal_since") or ""
            if not as_of or not since or since <= as_of_ym:
                continue
        repayable = float(ln.get("total_repayable") or 0)
        if as_of:
            paid = sum(
                float(e.get("paid_amount") or 0)
                for e in ln.get("emi_schedule", [])
                if e.get("status") == "paid" and (e.get("paid_date") or "") <= as_of
            )
        else:
            paid = float(ln.get("total_paid") or 0)
        outstanding = round(max(0.0, repayable - paid), 2)
        if outstanding <= 0:
            continue          # settled by this date — not part of the portfolio
        total += outstanding
        counted += 1

    head = await db.account_heads.find_one({"system_key": "loans_portfolio"})
    return {
        "total": round(total, 2),
        "loan_count": counted,
        "as_of": as_of,
        "account_head_id": str(head["_id"]) if head else None,
    }


@router.get("/accounts/opening-balance")
async def get_opening_balance(
    request: Request,
    illaka_id: Optional[str] = None,
):
    """Return the opening balance journal entry for an illaka, if it exists."""
    current_user = await get_current_user(request)
    query: dict = {"entry_type": "opening_balance"}
    _allowed = await permitted_illaka_ids(current_user)
    if _allowed is not None:
        query["illaka_id"] = {"$in": _allowed}
    await apply_illaka_scope(current_user, query, illaka_id)
    entry = await db.journal_entries.find_one(query)
    if not entry:
        return {"entry": None}
    return {"entry": _doc(entry)}


@router.post("/accounts/opening-balance")
async def create_opening_balance(data: OpeningBalanceCreate, request: Request):
    """Create (or overwrite) the opening balance for an illaka.
    Any non-zero line is included; the difference is auto-posted to Opening Capital.
    """
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only admin or maalik can set opening balances")

    # Delete previous opening balance for this illaka (allow re-entry)
    await db.journal_entries.delete_one({
        "entry_type": "opening_balance",
        "illaka_id": data.illaka_id,
    })

    # Ensure Opening Capital equity head exists
    capital_head = await db.account_heads.find_one({"system_key": "opening_capital"})
    if not capital_head:
        group = await db.account_groups.find_one({"group_type": "equity"})
        doc = {
            "name": "Opening Capital",
            "group_name": group["name"] if group else "Owner's Capital",
            "group_type": "equity",
            "system_key": "opening_capital",
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        res = await db.account_heads.insert_one(doc)
        capital_head = await db.account_heads.find_one({"_id": res.inserted_id})

    lines = []
    total_dr = 0.0
    total_cr = 0.0

    for line in data.lines:
        dr = round(float(line.debit), 2)
        cr = round(float(line.credit), 2)
        if dr == 0.0 and cr == 0.0:
            continue

        # A named party creates (or reuses) a real account head, so the party
        # shows up in the Trial Balance / Balance Sheet and can be posted to
        # again later — not just a label on this one entry.
        if not line.account_head_id and line.new_head_name:
            head = await _find_or_create_party_head(
                line.new_head_name, line.new_head_kind or "debtor", current_user["id"]
            )
        else:
            try:
                head = await db.account_heads.find_one({"_id": ObjectId(line.account_head_id)})
            except Exception:
                raise HTTPException(status_code=400, detail=f"Invalid account head: {line.account_head_id}")
            if not head:
                raise HTTPException(status_code=404, detail=f"Account head not found: {line.account_head_id}")
        lines.append({
            "account_head_id": str(head["_id"]),
            "account_head_name": head["name"],
            "group_name": head.get("group_name", ""),
            "group_type": head.get("group_type", ""),
            "debit": dr,
            "credit": cr,
        })
        total_dr += dr
        total_cr += cr

    if not lines:
        raise HTTPException(status_code=400, detail="No non-zero lines provided")

    # Auto-balance via Opening Capital
    diff = round(total_dr - total_cr, 2)
    if abs(diff) > 0.01:
        lines.append({
            "account_head_id": str(capital_head["_id"]),
            "account_head_name": capital_head["name"],
            "group_name": capital_head.get("group_name", "Owner's Capital"),
            "group_type": capital_head.get("group_type", "equity"),
            "debit": 0.0 if diff > 0 else abs(diff),
            "credit": diff if diff > 0 else 0.0,
        })

    await create_journal_entry_internal(
        illaka_id=data.illaka_id,
        date=data.date,
        narration="Opening Balance",
        lines=lines,
        entry_type="opening_balance",
        reference_id=None,
        created_by_id=current_user["id"],
        created_by_name=current_user.get("name", ""),
    )
    return {"message": "Opening balance saved"}


@router.delete("/accounts/opening-balance")
async def delete_opening_balance(
    request: Request,
    illaka_id: str,
):
    """Delete the opening balance for an illaka."""
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only admin or maalik can delete opening balances")
    result = await db.journal_entries.delete_one({
        "entry_type": "opening_balance",
        "illaka_id": illaka_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="No opening balance found for this illaka")
    return {"message": "Opening balance deleted"}


@router.get("/accounts/closing-balances")
async def get_closing_balances(
    request: Request,
    illaka_id: str,
    closing_date: str,
):
    """Return per-account closing balances (with head IDs) as of closing_date.
    Only succeeds when a year-end closing exists for this illaka.
    Used to pre-fill opening balances for the next fiscal year.
    Income/expense accounts and the auto-calculated Opening Capital are excluded.
    """
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Only admin or maalik can copy closing balances")

    # Verify a year-end closing actually exists for this illaka on this date
    gyal_loan = await db.loans.find_one({"illaka_id": illaka_id, "is_gyal": True, "gyal_since": closing_date})
    if not gyal_loan:
        raise HTTPException(status_code=404, detail="No year-end closing found for this date and illaka")

    # Build system_key lookup to skip opening_capital
    all_heads = await db.account_heads.find({}, {"_id": 1, "system_key": 1}).to_list(1000)
    system_key_map = {str(h["_id"]): h.get("system_key", "") for h in all_heads}

    # All journal entries for this illaka up to and including the closing date
    entries = await db.journal_entries.find(
        {"illaka_id": illaka_id, "date": {"$lte": closing_date}}
    ).to_list(50000)

    head_totals: dict = {}
    for entry in entries:
        for line in entry.get("lines", []):
            hid = line.get("account_head_id")
            if not hid:
                continue
            if hid not in head_totals:
                head_totals[hid] = {
                    "account_head_id": hid,
                    "account_head_name": line.get("account_head_name", ""),
                    "group_name": line.get("group_name", ""),
                    "group_type": line.get("group_type", ""),
                    "total_debit": 0.0,
                    "total_credit": 0.0,
                }
            head_totals[hid]["total_debit"] += float(line.get("debit", 0))
            head_totals[hid]["total_credit"] += float(line.get("credit", 0))

    items = []
    for hid, h in head_totals.items():
        gtype = h["group_type"]
        # Skip income & expense — closed at year-end; skip auto-calculated capital plug
        if gtype in ("income", "expense"):
            continue
        if system_key_map.get(hid) == "opening_capital":
            continue
        dr = round(h["total_debit"], 2)
        cr = round(h["total_credit"], 2)
        # balance = natural side: Dr for assets, Cr for liabilities/equity
        balance = round(dr - cr, 2) if gtype == "asset" else round(cr - dr, 2)
        if abs(balance) < 0.01:
            continue  # skip zero-balance heads
        items.append({
            "account_head_id": hid,
            "account_head_name": h["account_head_name"],
            "group_name": h["group_name"],
            "group_type": gtype,
            "balance": balance,
        })

    return {"closing_date": closing_date, "items": items}


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
    maalik_id: Optional[str] = None,
    month: Optional[str] = None,
):
    current_user = await get_current_user(request)
    if not month:
        today = date_type.today()
        month = f"{today.year}-{today.month:02d}"

    query = await _illaka_filter_for_user(current_user, illaka_id, maalik_id)
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
