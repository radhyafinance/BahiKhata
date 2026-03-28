from fastapi import APIRouter, HTTPException, Request, Query
from bson import ObjectId
from datetime import datetime, timezone
from typing import Optional
from core.database import db
from core.auth import get_current_user
from helpers import _doc
from models import IllakaCreate, MisalCreate

router = APIRouter()


@router.get("/illakas")
async def list_illakas(request: Request):
    user = await get_current_user(request)
    if user["role"] == "admin":
        query = {}
    elif user["role"] == "maalik":
        query = {"maalik_id": user["id"]}
    else:
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


@router.post("/illakas")
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


@router.put("/illakas/{illaka_id}")
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


@router.delete("/illakas/{illaka_id}")
async def delete_illaka(illaka_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    await db.illakas.delete_one({"_id": ObjectId(illaka_id)})
    return {"message": "Illaka deleted"}


@router.get("/misals")
async def list_misals(request: Request, illaka_id: Optional[str] = Query(None)):
    await get_current_user(request)
    query = {}
    if illaka_id:
        query["illaka_id"] = illaka_id
    docs = await db.misals.find(query).sort("name", 1).to_list(1000)
    return [_doc(d) for d in docs]


@router.post("/misals")
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


@router.put("/misals/{misal_id}")
async def update_misal(misal_id: str, data: MisalCreate, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    updates = {"name": data.name, "illaka_id": data.illaka_id, "description": data.description}
    await db.misals.update_one({"_id": ObjectId(misal_id)}, {"$set": updates})
    doc = await db.misals.find_one({"_id": ObjectId(misal_id)})
    return _doc(doc)


@router.delete("/misals/{misal_id}")
async def delete_misal(misal_id: str, request: Request):
    user = await get_current_user(request)
    if user["role"] not in ["admin", "maalik"]:
        raise HTTPException(status_code=403, detail="Admin or Maalik only")
    await db.misals.delete_one({"_id": ObjectId(misal_id)})
    return {"message": "Misal deleted"}
