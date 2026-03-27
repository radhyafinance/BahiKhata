from dotenv import load_dotenv
load_dotenv()

import os
import jwt
import bcrypt
import uuid
import requests
import logging
import json
import re
import tempfile
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, UploadFile, File, Query
from fastapi.responses import Response as FastResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from bson import ObjectId
from starlette.middleware.cors import CORSMiddleware

from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType

# ─── MongoDB ──────────────────────────────────────────────────────────────────
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ─── Object Storage ───────────────────────────────────────────────────────────
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "bahikhata"
_storage_key = None

def init_storage():
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ─── JWT & Auth ───────────────────────────────────────────────────────────────
JWT_ALGORITHM = "HS256"

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: str, email: str, role: str) -> str:
    return jwt.encode(
        {"sub": user_id, "email": email, "role": role,
         "exp": datetime.now(timezone.utc) + timedelta(hours=10), "type": "access"},
        get_jwt_secret(), algorithm=JWT_ALGORITHM
    )

def _user_from_doc(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    d.pop("password_hash", None)
    return d

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return _user_from_doc(user)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ─── Pydantic Models ──────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    branch: Optional[str] = None
    phone: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    branch: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None

class PersonKYCData(BaseModel):
    name: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    aadhaar_number: Optional[str] = None
    aadhaar_front_path: Optional[str] = None
    aadhaar_back_path: Optional[str] = None
    document_type: Optional[str] = None
    document_front_path: Optional[str] = None
    document_back_path: Optional[str] = None

class GPSLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    address: Optional[str] = None
    timestamp: Optional[str] = None

class KYCCreate(BaseModel):
    primary_borrower: PersonKYCData
    co_borrower: Optional[PersonKYCData] = None
    guarantor: Optional[PersonKYCData] = None
    live_photo_path: Optional[str] = None
    gps_location: Optional[GPSLocation] = None
    notes: Optional[str] = None
    branch: Optional[str] = None

class KYCStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

class OCRRequest(BaseModel):
    path: str

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _kyc_from_doc(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d

def generate_kyc_number() -> str:
    return f"BK{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4()).replace('-','')[:6].upper()}"

MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "webp": "image/webp", "pdf": "application/pdf"
}

# ─── App & Router ─────────────────────────────────────────────────────────────
app = FastAPI(title="Bahi Khata API")
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Auth Endpoints ───────────────────────────────────────────────────────────
@api_router.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated. Contact admin.")
    token = create_access_token(str(user["_id"]), email, user.get("role", "field_officer"))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=36000, path="/")
    return _user_from_doc(user)

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def get_me(request: Request):
    return await get_current_user(request)

# ─── User Endpoints ───────────────────────────────────────────────────────────
@api_router.get("/users")
async def list_users(request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "branch_manager"]:
        raise HTTPException(status_code=403, detail="Access denied")
    docs = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    return [_user_from_doc(d) for d in docs]

@api_router.post("/users")
async def create_user(data: UserCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if await db.users.find_one({"email": data.email.lower()}):
        raise HTTPException(status_code=400, detail="Email already exists")
    doc = {
        "name": data.name, "email": data.email.lower().strip(),
        "password_hash": hash_password(data.password),
        "role": data.role, "branch": data.branch, "phone": data.phone,
        "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _user_from_doc(doc)

@api_router.put("/users/{uid}")
async def update_user(uid: str, data: UserUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if "password" in updates:
        updates["password_hash"] = hash_password(updates.pop("password"))
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": updates})
    doc = await db.users.find_one({"_id": ObjectId(uid)}, {"password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_from_doc(doc)

@api_router.delete("/users/{uid}")
async def delete_user(uid: str, request: Request):
    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"is_active": False}})
    return {"message": "User deactivated"}

# ─── KYC Endpoints ────────────────────────────────────────────────────────────
@api_router.get("/kycs")
async def list_kycs(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    current_user = await get_current_user(request)
    query = {}
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"kyc_number": {"$regex": search, "$options": "i"}},
            {"primary_borrower.name": {"$regex": search, "$options": "i"}},
            {"primary_borrower.phone": {"$regex": search, "$options": "i"}},
        ]
    if current_user["role"] == "field_officer":
        query["field_officer_id"] = current_user["id"]
    total = await db.kycs.count_documents(query)
    docs = await db.kycs.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "kycs": [_kyc_from_doc(d) for d in docs]}

@api_router.post("/kycs")
async def create_kyc(data: KYCCreate, request: Request):
    current_user = await get_current_user(request)
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "kyc_number": generate_kyc_number(),
        "status": "pending",
        "primary_borrower": data.primary_borrower.model_dump(),
        "co_borrower": data.co_borrower.model_dump() if data.co_borrower else None,
        "guarantor": data.guarantor.model_dump() if data.guarantor else None,
        "live_photo_path": data.live_photo_path,
        "gps_location": data.gps_location.model_dump() if data.gps_location else None,
        "field_officer_id": current_user["id"],
        "field_officer_name": current_user["name"],
        "branch": data.branch or current_user.get("branch"),
        "notes": data.notes,
        "created_at": now, "updated_at": now
    }
    result = await db.kycs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _kyc_from_doc(doc)

@api_router.get("/kycs/{kyc_id}")
async def get_kyc(kyc_id: str, request: Request):
    await get_current_user(request)
    doc = await db.kycs.find_one({"_id": ObjectId(kyc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _kyc_from_doc(doc)

@api_router.put("/kycs/{kyc_id}")
async def update_kyc(kyc_id: str, data: KYCCreate, request: Request):
    await get_current_user(request)
    updates = {
        "primary_borrower": data.primary_borrower.model_dump(),
        "co_borrower": data.co_borrower.model_dump() if data.co_borrower else None,
        "guarantor": data.guarantor.model_dump() if data.guarantor else None,
        "live_photo_path": data.live_photo_path,
        "gps_location": data.gps_location.model_dump() if data.gps_location else None,
        "notes": data.notes,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": updates})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _kyc_from_doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))

@api_router.patch("/kycs/{kyc_id}/status")
async def update_kyc_status(kyc_id: str, data: KYCStatusUpdate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "branch_manager"]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    if data.status not in ["pending", "approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    updates = {
        "status": data.status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "reviewed_by": current_user["name"],
        "reviewed_at": datetime.now(timezone.utc).isoformat()
    }
    if data.notes:
        updates["notes"] = data.notes
    result = await db.kycs.update_one({"_id": ObjectId(kyc_id)}, {"$set": updates})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _kyc_from_doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))

# ─── File Upload & Serve ──────────────────────────────────────────────────────
@api_router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    await get_current_user(request)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    ct = MIME_TYPES.get(ext, file.content_type or "application/octet-stream")
    path = f"{APP_NAME}/uploads/{uuid.uuid4()}.{ext}"
    data = await file.read()
    result = put_object(path, data, ct)
    return {"path": result["path"], "size": result.get("size", len(data)), "content_type": ct}

@api_router.get("/files/{path:path}")
async def serve_file(path: str, request: Request, auth: str = Query(None)):
    token = request.cookies.get("access_token") or auth
    if not token:
        h = request.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            token = h[7:]
    if token:
        try:
            jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
    try:
        data, ct = get_object(path)
        return FastResponse(content=data, media_type=ct)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

# ─── OCR Endpoint ─────────────────────────────────────────────────────────────
@api_router.post("/ocr/aadhaar")
async def ocr_aadhaar(data: OCRRequest, request: Request):
    await get_current_user(request)
    try:
        file_data, ct = get_object(data.path)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found in storage")

    ext = data.path.rsplit(".", 1)[-1] if "." in data.path else "jpg"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"ocr-{uuid.uuid4()}",
            system_message="You are an expert OCR system for Indian government documents. Extract text with high accuracy."
        ).with_model("gemini", "gemini-2.5-flash")

        img = FileContentWithMimeType(file_path=tmp_path, mime_type=ct or "image/jpeg")
        msg = UserMessage(
            text="""Extract information from this Aadhaar card image. Return ONLY valid JSON (no markdown, no explanation):
{
  "name": "full name of cardholder",
  "dob": "DD/MM/YYYY",
  "address": "full address",
  "aadhaar_number": "XXXX XXXX XXXX",
  "gender": "Male or Female or Other"
}
Use null for any field not visible or unreadable.""",
            file_contents=[img]
        )
        raw = await chat.send_message(msg)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        extracted = json.loads(m.group()) if m else {}
        return extracted
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return {"name": None, "dob": None, "address": None, "aadhaar_number": None, "gender": None, "error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

# ─── Dashboard Stats ──────────────────────────────────────────────────────────
@api_router.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    current_user = await get_current_user(request)
    query = {}
    if current_user["role"] == "field_officer":
        query["field_officer_id"] = current_user["id"]
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return {
        "total": await db.kycs.count_documents(query),
        "pending": await db.kycs.count_documents({**query, "status": "pending"}),
        "approved": await db.kycs.count_documents({**query, "status": "approved"}),
        "rejected": await db.kycs.count_documents({**query, "status": "rejected"}),
        "today": await db.kycs.count_documents({**query, "created_at": {"$gte": today}}),
        "field_officers": await db.users.count_documents({"role": "field_officer", "is_active": True}),
    }

# ─── App Configuration ────────────────────────────────────────────────────────
app.include_router(api_router)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:3000", "https://lending-kyc.preview.emergentagent.com"],
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

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@bahikhata.com")
    admin_password = os.environ.get("ADMIN_PASSWORD", "Admin@123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        await db.users.insert_one({
            "name": "Super Admin", "email": admin_email,
            "password_hash": hash_password(admin_password),
            "role": "admin", "branch": "HQ", "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        })
        logger.info(f"Admin created: {admin_email}")
    elif not verify_password(admin_password, existing.get("password_hash", "")):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")

@app.on_event("shutdown")
async def shutdown():
    client.close()
