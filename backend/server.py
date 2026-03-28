from dotenv import load_dotenv
load_dotenv()

import os, logging
from datetime import datetime, timezone
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

from core.database import client, db
from core.auth import hash_password, verify_password
from core.storage import init_storage
from routes import auth, users, illakas, kycs, loans, ocr, collections, dashboard

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

app.include_router(api_router)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "https://vasuli-collection.preview.emergentagent.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
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

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@bahikhata.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "name": "Super Admin", "email": admin_email,
            "password_hash": hash_password(admin_password),
            "role": "admin", "assigned_illaka_ids": [], "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Admin created: {admin_email}")
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()
