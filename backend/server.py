from dotenv import load_dotenv
load_dotenv()

import os, jwt, bcrypt, uuid, requests, logging, json, re, tempfile
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
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
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

ROLES = ["admin", "maalik", "muneem", "sipahi"]

# ─── Models ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str

class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str  # admin | maalik | muneem | sipahi
    phone: Optional[str] = None
    assigned_illaka_ids: Optional[List[str]] = []
    maalik_id: Optional[str] = None  # For muneem/sipahi — which maalik they report to

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    assigned_illaka_ids: Optional[List[str]] = None
    maalik_id: Optional[str] = None
    is_active: Optional[bool] = None

class IllakaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    maalik_id: Optional[str] = None  # Admin can assign to a Maalik

class MisalCreate(BaseModel):
    name: str
    illaka_id: str
    description: Optional[str] = None

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
    illaka_id: str
    illaka_name: str
    misal_id: str
    misal_name: str
    primary_borrower: PersonKYCData
    co_borrower: Optional[PersonKYCData] = None
    guarantor: Optional[PersonKYCData] = None
    live_photo_path: Optional[str] = None
    gps_location: Optional[GPSLocation] = None
    notes: Optional[str] = None

class KYCStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None

class OCRRequest(BaseModel):
    path: str

class AssignIllakas(BaseModel):
    illaka_ids: List[str]

# ─── Doc Helpers ──────────────────────────────────────────────────────────────
def _doc(d: dict) -> dict:
    d = dict(d)
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

# ─── Auth ─────────────────────────────────────────────────────────────────────
@api_router.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    email = req.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated.")
    token = create_access_token(str(user["_id"]), email, user.get("role", "sipahi"))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=36000, path="/")
    return _user_from_doc(user)

@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out"}

@api_router.get("/auth/me")
async def get_me(request: Request):
    return await get_current_user(request)

# ─── Users ────────────────────────────────────────────────────────────────────
@api_router.get("/users")
async def list_users(request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        docs = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    elif user["role"] == "maalik":
        docs = await db.users.find({"maalik_id": user["id"], "role": {"$in": ["muneem", "sipahi"]}}, {"password_hash": 0}).to_list(1000)
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    return [_user_from_doc(d) for d in docs]

@api_router.post("/users")
async def create_user(data: UserCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        pass  # Admin can create any role
    elif user["role"] == "maalik":
        if data.role not in ["muneem", "sipahi"]:
            raise HTTPException(status_code=403, detail="Maalik can only create Muneem or Sipahi")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    if await db.users.find_one({"email": data.email.lower()}):
        raise HTTPException(status_code=400, detail="Email already exists")

    maalik_id = data.maalik_id
    if user["role"] == "maalik" and data.role in ["muneem", "sipahi"]:
        maalik_id = user["id"]

    doc = {
        "name": data.name, "email": data.email.lower().strip(),
        "password_hash": hash_password(data.password),
        "role": data.role, "phone": data.phone,
        "assigned_illaka_ids": data.assigned_illaka_ids or [],
        "maalik_id": maalik_id,
        "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _user_from_doc(doc)

@api_router.put("/users/{uid}")
async def update_user(uid: str, data: UserUpdate, request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        pass
    elif user["role"] == "maalik":
        target = await db.users.find_one({"_id": ObjectId(uid)})
        if not target or target.get("maalik_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

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
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"is_active": False}})
    return {"message": "User deactivated"}

@api_router.post("/users/{uid}/assign-illakas")
async def assign_illakas(uid: str, data: AssignIllakas, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"assigned_illaka_ids": data.illaka_ids}})
    return {"message": "Illakas assigned", "illaka_ids": data.illaka_ids}

# ─── Illakas ──────────────────────────────────────────────────────────────────
@api_router.get("/illakas")
async def list_illakas(request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        query = {}
    elif user["role"] == "maalik":
        query = {"maalik_id": user["id"]}
    else:
        # Muneem / Sipahi — return their assigned Illakas
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            return []
        try:
            oids = [ObjectId(i) for i in assigned]
            query = {"_id": {"$in": oids}}
        except Exception:
            return []
    docs = await db.illakas.find(query).sort("name", 1).to_list(1000)
    return [_doc(d) for d in docs]

@api_router.post("/illakas")
async def create_illaka(data: IllakaCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    maalik_id = user["id"] if user["role"] == "maalik" else data.maalik_id
    doc = {
        "name": data.name, "description": data.description,
        "maalik_id": maalik_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.illakas.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc(doc)

@api_router.put("/illakas/{illaka_id}")
async def update_illaka(illaka_id: str, data: IllakaCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    updates = {"name": data.name, "description": data.description, "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.illakas.update_one({"_id": ObjectId(illaka_id)}, {"$set": updates})
    doc = await db.illakas.find_one({"_id": ObjectId(illaka_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Illaka not found")
    return _doc(doc)

@api_router.delete("/illakas/{illaka_id}")
async def delete_illaka(illaka_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    await db.illakas.delete_one({"_id": ObjectId(illaka_id)})
    return {"message": "Illaka deleted"}

# ─── Misals ───────────────────────────────────────────────────────────────────
@api_router.get("/misals")
async def list_misals(request: Request, illaka_id: Optional[str] = Query(None)):
    await get_current_user(request)
    query = {}
    if illaka_id:
        query["illaka_id"] = illaka_id
    docs = await db.misals.find(query).sort("name", 1).to_list(1000)
    return [_doc(d) for d in docs]

@api_router.post("/misals")
async def create_misal(data: MisalCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    doc = {
        "name": data.name, "illaka_id": data.illaka_id,
        "description": data.description,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    result = await db.misals.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc(doc)

@api_router.put("/misals/{misal_id}")
async def update_misal(misal_id: str, data: MisalCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    updates = {"name": data.name, "illaka_id": data.illaka_id, "description": data.description}
    await db.misals.update_one({"_id": ObjectId(misal_id)}, {"$set": updates})
    doc = await db.misals.find_one({"_id": ObjectId(misal_id)})
    return _doc(doc)

@api_router.delete("/misals/{misal_id}")
async def delete_misal(misal_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    await db.misals.delete_one({"_id": ObjectId(misal_id)})
    return {"message": "Misal deleted"}

# ─── KYCs ─────────────────────────────────────────────────────────────────────
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
    else:  # sipahi — see all KYCs in their assigned Illakas (per product requirements)
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            query["field_officer_id"] = user["id"]  # Fallback: only their own
        else:
            query["illaka_id"] = {"$in": assigned}
    return query

@api_router.get("/kycs")
async def list_kycs(
    request: Request,
    status: Optional[str] = None,
    search: Optional[str] = None,
    illaka_id: Optional[str] = None,
    misal_id: Optional[str] = None,
    limit: int = 50,
    skip: int = 0
):
    current_user = await get_current_user(request)
    query = await _kyc_query_for_user(current_user)
    if status:
        query["status"] = status
    if illaka_id:
        query["illaka_id"] = illaka_id
    if misal_id:
        query["misal_id"] = misal_id
    if search:
        query["$or"] = [
            {"kyc_number": {"$regex": search, "$options": "i"}},
            {"primary_borrower.name": {"$regex": search, "$options": "i"}},
            {"primary_borrower.phone": {"$regex": search, "$options": "i"}},
        ]
    total = await db.kycs.count_documents(query)
    docs = await db.kycs.find(query).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "kycs": [_doc(d) for d in docs]}

@api_router.post("/kycs")
async def create_kyc(data: KYCCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["muneem", "sipahi"]:
        raise HTTPException(status_code=403, detail="Only field agents can create KYCs")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "kyc_number": generate_kyc_number(),
        "status": "pending",
        "illaka_id": data.illaka_id,
        "illaka_name": data.illaka_name,
        "misal_id": data.misal_id,
        "misal_name": data.misal_name,
        "primary_borrower": data.primary_borrower.model_dump(),
        "co_borrower": data.co_borrower.model_dump() if data.co_borrower else None,
        "guarantor": data.guarantor.model_dump() if data.guarantor else None,
        "live_photo_path": data.live_photo_path,
        "gps_location": data.gps_location.model_dump() if data.gps_location else None,
        "field_officer_id": current_user["id"],
        "field_officer_name": current_user["name"],
        "field_officer_role": current_user["role"],
        "notes": data.notes,
        "created_at": now, "updated_at": now
    }
    result = await db.kycs.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc(doc)

@api_router.get("/kycs/{kyc_id}")
async def get_kyc(kyc_id: str, request: Request):
    await get_current_user(request)
    doc = await db.kycs.find_one({"_id": ObjectId(kyc_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="KYC not found")
    return _doc(doc)

@api_router.put("/kycs/{kyc_id}")
async def update_kyc(kyc_id: str, data: KYCCreate, request: Request):
    await get_current_user(request)
    updates = {
        "illaka_id": data.illaka_id, "illaka_name": data.illaka_name,
        "misal_id": data.misal_id, "misal_name": data.misal_name,
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
    return _doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))

@api_router.patch("/kycs/{kyc_id}/status")
async def update_kyc_status(kyc_id: str, data: KYCStatusUpdate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
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
    return _doc(await db.kycs.find_one({"_id": ObjectId(kyc_id)}))

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

# ─── OCR ──────────────────────────────────────────────────────────────────────
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
            system_message="You are an expert OCR system for Indian Aadhaar cards. Extract all visible text accurately."
        ).with_model("gemini", "gemini-2.5-flash")

        img = FileContentWithMimeType(file_path=tmp_path, mime_type=ct or "image/jpeg")
        msg = UserMessage(
            text="""Carefully examine this Indian Aadhaar card image and extract the following details.

On Aadhaar cards:
- The cardholder's NAME is printed in English (sometimes also in regional script)
- DATE OF BIRTH is shown after "DOB:" or "Date of Birth:" in DD/MM/YYYY format
- GENDER is printed as "MALE" or "FEMALE"
- ADDRESS appears in the lower portion, often spanning multiple lines: house/door no, street/mohalla, village/town, district, state, PIN code
- AADHAAR NUMBER is the 12-digit number printed prominently (may have spaces like XXXX XXXX XXXX)

Return ONLY a valid JSON object — no markdown, no code blocks, no explanation:
{
  "name": "full name exactly as printed in English",
  "dob": "DD/MM/YYYY",
  "address": "complete address — house no, street, village, district, state, PIN — all on one line",
  "aadhaar_number": "12-digit number with spaces",
  "gender": "Male or Female"
}

Use null for any field that is not clearly readable.""",
            file_contents=[img]
        )
        raw = await chat.send_message(msg)
        # Strip any markdown code fences
        raw = re.sub(r'```[a-z]*\n?', '', raw).strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        extracted = json.loads(m.group()) if m else {}
        return extracted
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return {"name": None, "dob": None, "address": None, "aadhaar_number": None, "gender": None}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

# ─── Loans ────────────────────────────────────────────────────────────────────
class LoanCreate(BaseModel):
    kyc_id: str
    client_name: str
    client_phone: Optional[str] = None
    illaka_id: str
    illaka_name: str
    misal_id: str
    misal_name: str
    principal_amount: float
    interest_rate: float          # per month %
    loan_date: str                # YYYY-MM-DD
    due_date: Optional[str] = None
    notes: Optional[str] = None

class LoanStatusUpdate(BaseModel):
    status: str  # active | closed | overdue
    notes: Optional[str] = None

class PaymentCreate(BaseModel):
    amount: float
    payment_date: str             # YYYY-MM-DD
    notes: Optional[str] = None

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
    else:  # sipahi — see loans in their assigned Illakas
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            return {"sipahi_id": user["id"]}  # Fallback: only their own loans
        return {"illaka_id": {"$in": assigned}}

@api_router.get("/loans")
async def list_loans(
    request: Request,
    illaka_id: Optional[str] = None,
    misal_id: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    skip: int = 0,
):
    current_user = await get_current_user(request)
    query = await _loan_query_for_user(current_user)
    if illaka_id:
        query["illaka_id"] = illaka_id
    if misal_id:
        query["misal_id"] = misal_id
    if status:
        query["status"] = status
    if search:
        query["$or"] = [
            {"client_name": {"$regex": search, "$options": "i"}},
            {"client_phone": {"$regex": search, "$options": "i"}},
        ]
    total = await db.loans.count_documents(query)
    docs = await db.loans.find(query).sort("loan_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "loans": [_doc(d) for d in docs]}

@api_router.post("/loans")
async def create_loan(data: LoanCreate, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["muneem", "sipahi"]:
        raise HTTPException(status_code=403, detail="Only field agents can create loans")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "kyc_id": data.kyc_id,
        "client_name": data.client_name,
        "client_phone": data.client_phone,
        "illaka_id": data.illaka_id,
        "illaka_name": data.illaka_name,
        "misal_id": data.misal_id,
        "misal_name": data.misal_name,
        "principal_amount": data.principal_amount,
        "interest_rate": data.interest_rate,
        "loan_date": data.loan_date,
        "due_date": data.due_date,
        "status": "active",
        "sipahi_id": current_user["id"],
        "sipahi_name": current_user["name"],
        "total_paid": 0.0,
        "notes": data.notes,
        "created_at": now, "updated_at": now,
    }
    result = await db.loans.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _doc(doc)

@api_router.get("/loans/{loan_id}")
async def get_loan(loan_id: str, request: Request):
    await get_current_user(request)
    doc = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Loan not found")
    return _doc(doc)

@api_router.put("/loans/{loan_id}")
async def update_loan(loan_id: str, data: LoanCreate, request: Request):
    current_user = await get_current_user(request)
    loan = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if current_user["role"] not in ["admin", "maalik", "muneem"] and loan.get("sipahi_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    updates = {
        "client_name": data.client_name, "client_phone": data.client_phone,
        "principal_amount": data.principal_amount, "interest_rate": data.interest_rate,
        "loan_date": data.loan_date, "due_date": data.due_date, "notes": data.notes,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.loans.update_one({"_id": ObjectId(loan_id)}, {"$set": updates})
    return _doc(await db.loans.find_one({"_id": ObjectId(loan_id)}))

@api_router.patch("/loans/{loan_id}/status")
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

# ─── Payments ─────────────────────────────────────────────────────────────────
@api_router.get("/loans/{loan_id}/payments")
async def list_payments(loan_id: str, request: Request):
    await get_current_user(request)
    docs = await db.payments.find({"loan_id": loan_id}).sort("payment_date", -1).to_list(500)
    return [_doc(d) for d in docs]

@api_router.post("/loans/{loan_id}/payments")
async def add_payment(loan_id: str, data: PaymentCreate, request: Request):
    current_user = await get_current_user(request)
    loan = await db.loans.find_one({"_id": ObjectId(loan_id)})
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.get("status") == "closed":
        raise HTTPException(status_code=400, detail="Cannot add payment to a closed loan")
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "loan_id": loan_id,
        "amount": data.amount,
        "payment_date": data.payment_date,
        "collected_by_id": current_user["id"],
        "collected_by_name": current_user["name"],
        "notes": data.notes,
        "created_at": now,
    }
    result = await db.payments.insert_one(doc)
    doc["_id"] = result.inserted_id
    # Update total_paid on the loan
    total_paid = loan.get("total_paid", 0.0) + data.amount
    await db.loans.update_one({"_id": ObjectId(loan_id)}, {"$set": {"total_paid": total_paid, "updated_at": now}})
    return _doc(doc)

@api_router.delete("/loans/{loan_id}/payments/{payment_id}")
async def delete_payment(loan_id: str, payment_id: str, request: Request):
    current_user = await get_current_user(request)
    if current_user["role"] not in ["admin", "maalik", "muneem"]:
        raise HTTPException(status_code=403, detail="Access denied")
    payment = await db.payments.find_one({"_id": ObjectId(payment_id), "loan_id": loan_id})
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    await db.payments.delete_one({"_id": ObjectId(payment_id)})
    # Recalculate total_paid
    payments = await db.payments.find({"loan_id": loan_id}).to_list(1000)
    total_paid = sum(p["amount"] for p in payments)
    await db.loans.update_one({"_id": ObjectId(loan_id)}, {"$set": {"total_paid": total_paid, "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"message": "Payment deleted"}

# ─── Dashboard Stats ──────────────────────────────────────────────────────────
@api_router.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    current_user = await get_current_user(request)
    kyc_query = await _kyc_query_for_user(current_user)
    loan_query = await _loan_query_for_user(current_user)
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return {
        "total": await db.kycs.count_documents(kyc_query),
        "pending": await db.kycs.count_documents({**kyc_query, "status": "pending"}),
        "approved": await db.kycs.count_documents({**kyc_query, "status": "approved"}),
        "rejected": await db.kycs.count_documents({**kyc_query, "status": "rejected"}),
        "today": await db.kycs.count_documents({**kyc_query, "created_at": {"$gte": today}}),
        "sipahi_count": await db.users.count_documents({"role": "sipahi", "is_active": True}),
        "muneem_count": await db.users.count_documents({"role": "muneem", "is_active": True}),
        "active_loans": await db.loans.count_documents({**loan_query, "status": "active"}),
        "total_loans": await db.loans.count_documents(loan_query),
    }

# ─── App ──────────────────────────────────────────────────────────────────────
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
    await db.kycs.create_index("illaka_id")
    await db.kycs.create_index("misal_id")
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
