from dotenv import load_dotenv
load_dotenv()

import os, logging
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core.database import client, db
from core.auth import hash_password, verify_password
from core.storage import init_storage
from routes import auth, users, illakas, kycs, loans, ocr, collections, dashboard, accounts, passkeys, import_data, crif

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── App & Router ─────────────────────────────────────────────────────────────
app = FastAPI(title="Bahi Khata API")
api_router = APIRouter(prefix="/api")

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(illakas.router)
api_router.include_router(kycs.router)
api_router.include_router(loans.router)
api_router.include_router(ocr.router)
api_router.include_router(collections.router)
api_router.include_router(dashboard.router)
api_router.include_router(accounts.router)
api_router.include_router(passkeys.router)
api_router.include_router(import_data.router)
api_router.include_router(crif.router)

app.include_router(api_router)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")
origins = ["*"] if CORS_ORIGINS == "*" else [o.strip() for o in CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    try:
        await db.users.drop_index("email_1")
    except Exception:
        pass
    try:
        await db.users.drop_index("phone_1")
    except Exception:
        pass
    await db.users.create_index("email", unique=True, sparse=True)
    await db.users.create_index(
        "phone", unique=True,
        partialFilterExpression={"phone": {"$gt": ""}}
    )
    await db.kycs.create_index([("created_at", -1)])
    await db.kycs.create_index("field_officer_id")
    await db.kycs.create_index("status")
    await db.kycs.create_index("illaka_id")
    await db.kycs.create_index("misal_id")
    await db.kycs.create_index("primary_borrower.aadhaar_number")
    await db.kycs.create_index("customer_id")
    await db.kycs.create_index("primary_borrower.phone")
    await db.illakas.create_index("maalik_id")
    await db.misals.create_index("illaka_id")
    await db.loans.create_index("kyc_id")
    await db.loans.create_index("sipahi_id")
    await db.loans.create_index("illaka_id")
    await db.loans.create_index("status")
    await db.loans.create_index([("loan_date", -1)])
    await db.payments.create_index("loan_id")
    await db.webauthn_challenges.create_index("session_id", unique=True)
    # Auto-expire challenges after 10 minutes
    await db.webauthn_challenges.create_index("created_at", expireAfterSeconds=600)

    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_phone = os.environ.get("ADMIN_PHONE")
    admin_password = os.environ.get("ADMIN_PASSWORD")
    existing = await db.users.find_one({"$or": [{"email": admin_email}, {"phone": admin_phone}]})
    if not existing:
        await db.users.insert_one({
            "name": "Super Admin", "email": admin_email, "phone": admin_phone,
            "password_hash": hash_password(admin_password),
            "role": "admin", "assigned_illaka_ids": [], "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Admin created: {admin_email} / {admin_phone}")
    else:
        updates = {}
        if not existing.get("phone") and admin_phone:
            updates["phone"] = admin_phone
        if not verify_password(admin_password, existing.get("password_hash", "")):
            updates["password_hash"] = hash_password(admin_password)
        if updates:
            await db.users.update_one({"_id": existing["_id"]}, {"$set": updates})

    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")

    await _seed_account_groups_and_heads()
    await _migrate_add_gyal_heads()


async def _migrate_add_gyal_heads():
    """Ensure Gyal-related account heads exist. Safe to run multiple times."""
    needed = ["gyal_wasool", "bad_debt_written_off"]
    existing = await db.account_heads.find({"system_key": {"$in": needed}}).to_list(10)
    existing_keys = {h["system_key"] for h in existing}
    if len(existing_keys) >= 2:
        return
    income_group = await db.account_groups.find_one({"name": "Direct Income"})
    expense_group = await db.account_groups.find_one({"name": "Direct Expense"})
    if not income_group or not expense_group:
        logger.warning("Account groups missing, skipping Gyal heads migration")
        return
    now = datetime.now(timezone.utc).isoformat()
    if "gyal_wasool" not in existing_keys:
        await db.account_heads.insert_one({
            "name": "Gyal Wasool (Bad Debt Recovery)",
            "group_id": str(income_group["_id"]),
            "group_name": "Direct Income",
            "group_type": "income",
            "is_system": True,
            "system_key": "gyal_wasool",
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        })
        logger.info("Added Gyal Wasool account head")
    if "bad_debt_written_off" not in existing_keys:
        await db.account_heads.insert_one({
            "name": "Bad Debt Written Off (Gyal)",
            "group_id": str(expense_group["_id"]),
            "group_name": "Direct Expense",
            "group_type": "expense",
            "is_system": True,
            "system_key": "bad_debt_written_off",
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        })
        logger.info("Added Bad Debt Written Off account head")


async def _seed_account_groups_and_heads():
    """Seed default Indian-standard account groups and heads if not present."""
    if await db.account_groups.count_documents({}) > 0:
        return  # Already seeded

    GROUPS = [
        {"name": "Capital Account",       "type": "equity",     "nature": "credit", "display_order": 1},
        {"name": "Loans & Borrowings",     "type": "liability",  "nature": "credit", "display_order": 2},
        {"name": "Cash & Bank",            "type": "asset",      "nature": "debit",  "display_order": 3},
        {"name": "Loans Portfolio",        "type": "asset",      "nature": "debit",  "display_order": 4},
        {"name": "Direct Income",          "type": "income",     "nature": "credit", "display_order": 5},
        {"name": "Indirect Income",        "type": "income",     "nature": "credit", "display_order": 6},
        {"name": "Direct Expense",         "type": "expense",    "nature": "debit",  "display_order": 7},
        {"name": "Indirect Expense",       "type": "expense",    "nature": "debit",  "display_order": 8},
    ]
    result = await db.account_groups.insert_many(GROUPS)
    id_map = {GROUPS[i]["name"]: str(result.inserted_ids[i]) for i in range(len(GROUPS))}
    logger.info(f"Seeded {len(GROUPS)} account groups")

    now = datetime.now(timezone.utc).isoformat()
    HEADS = [
        # Capital Account
        {"name": "Owner's Capital",              "group": "Capital Account",      "system_key": None},
        # Loans & Borrowings
        {"name": "Bank Borrowings",              "group": "Loans & Borrowings",   "system_key": None},
        {"name": "Unsecured Loans from Promoters", "group": "Loans & Borrowings", "system_key": None},
        # Cash & Bank
        {"name": "Cash in Hand",                 "group": "Cash & Bank",          "system_key": "cash_in_hand",    "is_system": True},
        {"name": "Bank Account",                 "group": "Cash & Bank",          "system_key": None},
        # Loans Portfolio
        {"name": "Loans Portfolio (Sundry Debtors)", "group": "Loans Portfolio",  "system_key": "loans_portfolio", "is_system": True},
        # Direct Income
        {"name": "Interest Income on Loans",     "group": "Direct Income",        "system_key": "interest_income", "is_system": True},
        {"name": "Processing Fees Received",     "group": "Direct Income",        "system_key": None},
        # Indirect Income
        {"name": "Late Payment Charges",         "group": "Indirect Income",      "system_key": None},
        {"name": "Other Income",                 "group": "Indirect Income",      "system_key": None},
        # Direct Expense
        {"name": "Interest on Borrowings",       "group": "Direct Expense",       "system_key": None},
        {"name": "Loan Processing Charges",      "group": "Direct Expense",       "system_key": None},
        # Indirect Expense
        {"name": "Staff Salaries",               "group": "Indirect Expense",     "system_key": None},
        {"name": "Travel & Conveyance",          "group": "Indirect Expense",     "system_key": None},
        {"name": "Office Rent",                  "group": "Indirect Expense",     "system_key": None},
        {"name": "Stationary & Printing",        "group": "Indirect Expense",     "system_key": None},
        {"name": "Communication Charges",        "group": "Indirect Expense",     "system_key": None},
        {"name": "Audit & Professional Fees",    "group": "Indirect Expense",     "system_key": None},
        {"name": "Miscellaneous Expense",        "group": "Indirect Expense",     "system_key": None},
    ]
    head_docs = []
    for h in HEADS:
        g = h["group"]
        head_docs.append({
            "name": h["name"],
            "group_id": id_map[g],
            "group_name": g,
            "group_type": next(gr["type"] for gr in GROUPS if gr["name"] == g),
            "is_system": h.get("is_system", False),
            "system_key": h.get("system_key"),
            "is_active": True,
            "created_by": "system",
            "created_at": now,
        })
    await db.account_heads.insert_many(head_docs)
    await db.account_groups.create_index("type")
    await db.account_heads.create_index("group_id")
    await db.account_heads.create_index("system_key", sparse=True)
    await db.account_heads.create_index("is_active")
    await db.journal_entries.create_index("illaka_id")
    await db.journal_entries.create_index("date")
    await db.journal_entries.create_index("entry_type")
    await db.journal_entries.create_index([("date", -1)])
    logger.info(f"Seeded {len(head_docs)} account heads")


@app.on_event("shutdown")
async def shutdown():
    client.close()
