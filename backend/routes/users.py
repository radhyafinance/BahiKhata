from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId
from datetime import datetime, timezone
from core.database import db
from helpers import _get_maalik_illaka_ids
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
    try:
        target = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if user["role"] == "admin":
        pass
    elif user["role"] == "maalik":
        if target.get("maalik_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    updates = {k: v for k, v in data.model_dump().items() if v is not None}

    # ── Privilege escalation guards ───────────────────────────────────────────
    # POST /users refuses to let a maalik create anything above sipahi, but this
    # endpoint applied no such limit: a maalik could promote one of their own
    # muneems to admin and then act through them. Nobody may change their own
    # role either, which is the other route to the same place.
    if "role" in updates and updates["role"] != target.get("role"):
        if user["role"] != "admin":
            if updates["role"] not in ("muneem", "sipahi"):
                raise HTTPException(
                    status_code=403,
                    detail="Maalik can only set a user's role to Muneem or Sipahi",
                )
        if str(target["_id"]) == user["id"]:
            raise HTTPException(status_code=403, detail="You cannot change your own role")

    # Reassigning a user to a different maalik is an ownership transfer.
    if "maalik_id" in updates and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only an Admin can reassign a user's Maalik")

    # Illakas must be ones the caller actually holds — same rule as assign-illakas.
    if "assigned_illaka_ids" in updates and user["role"] != "admin":
        allowed = set(await _get_maalik_illaka_ids(user))
        bad = [i for i in updates["assigned_illaka_ids"] if i not in allowed]
        if bad:
            raise HTTPException(
                status_code=403,
                detail="You can only assign Illakas that belong to you",
            )

    if "is_active" in updates and updates["is_active"] is False:
        await _guard_deactivation(user, target)

    if "password" in updates:
        updates["password_hash"] = hash_password(updates.pop("password"))
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": updates})
    doc = await db.users.find_one({"_id": ObjectId(uid)}, {"password_hash": 0})
    return _user_from_doc(doc)


async def _guard_deactivation(actor: dict, target: dict) -> None:
    """Refuse deactivations that lock people out or remove the last way back in."""
    if str(target["_id"]) == actor["id"]:
        raise HTTPException(status_code=403, detail="You cannot deactivate your own account")
    # A maalik could previously deactivate anyone at all, including the super
    # admin — with a single admin account that locked the whole system.
    if actor["role"] == "maalik" and target.get("maalik_id") != actor["id"]:
        raise HTTPException(status_code=403, detail="You can only deactivate your own staff")
    if target.get("role") == "admin":
        others = await db.users.count_documents(
            {"role": "admin", "is_active": {"$ne": False}, "_id": {"$ne": target["_id"]}}
        )
        if others == 0:
            raise HTTPException(
                status_code=400,
                detail="This is the last active Admin — deactivating it would lock everyone out.",
            )


@router.delete("/users/{uid}")
async def delete_user(uid: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        target = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # There was no check on the target at all.
    await _guard_deactivation(user, target)
    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"is_active": False}})
    return {"message": "User deactivated"}


@router.post("/users/{uid}/assign-illakas")
async def assign_illakas(uid: str, data: AssignIllakas, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        target = await db.users.find_one({"_id": ObjectId(uid)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Neither side used to be checked: a maalik could assign ANY illaka in the
    # system to ANY user, including themselves — which is a read of every other
    # branch's borrowers, balances and cash book.
    if user["role"] == "maalik":
        if target.get("maalik_id") != user["id"]:
            raise HTTPException(status_code=403, detail="You can only assign Illakas to your own staff")
        allowed = set(await _get_maalik_illaka_ids(user))
        bad = [i for i in data.illaka_ids if i not in allowed]
        if bad:
            raise HTTPException(
                status_code=403, detail="You can only assign Illakas that belong to you"
            )

    await db.users.update_one({"_id": ObjectId(uid)}, {"$set": {"assigned_illaka_ids": data.illaka_ids}})
    return {"message": "Illakas assigned", "illaka_ids": data.illaka_ids}
