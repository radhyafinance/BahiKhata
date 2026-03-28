from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone
from core.database import db
from core.auth import get_current_user, hash_password, _user_from_doc
from models import UserCreate, UserUpdate, AssignIllakas

router = APIRouter()


@router.get("/users")
async def list_users(request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        docs = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    elif user["role"] == "maalik":
        docs = await db.users.find(
            {"maalik_id": user["id"], "role": {"$in": ["muneem", "sipahi"]}},
            {"password_hash": 0}
        ).to_list(1000)
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    return [_user_from_doc(d) for d in docs]


@router.post("/users")
async def create_user(data: UserCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        pass
    elif user["role"] == "maalik":
        if data.role not in ["muneem", "sipahi"]:
            raise HTTPException(status_code=403, detail="Maalik can only create Muneem or Sipahi")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    if await db.users.find_one({"phone": data.phone}):
        raise HTTPException(status_code=400, detail="Mobile number already registered")

    maalik_id = data.maalik_id
    if user["role"] == "maalik" and data.role in ["muneem", "sipahi"]:
        maalik_id = user["id"]

    doc = {
        "name": data.name, "phone": data.phone,
        "password_hash": hash_password(data.password),
        "role": data.role,
        "assigned_illaka_ids": data.assigned_illaka_ids or [],
        "maalik_id": maalik_id,
        "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()
    }
    # Only include email if provided — sparse unique index indexes null but not missing fields
    if data.email:
        doc["email"] = data.email.lower().strip()
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _user_from_doc(doc)


@router.put("/users/{uid}")
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


@router.delete("/users/{uid}")
async def delete_user(uid: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"is_active": False}})
    return {"message": "User deactivated"}


@router.post("/users/{uid}/assign-illakas")
async def assign_illakas(uid: str, data: AssignIllakas, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Access denied")
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"assigned_illaka_ids": data.illaka_ids}})
    return {"message": "Illakas assigned", "illaka_ids": data.illaka_ids}
