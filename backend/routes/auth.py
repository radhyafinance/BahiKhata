from fastapi import APIRouter, HTTPException, Request, Response
from core.database import db
from core.auth import create_access_token, verify_password, _user_from_doc, get_current_user
from models import LoginRequest

router = APIRouter()


@router.post("/auth/login")
async def login(req: LoginRequest, response: Response):
    phone = req.phone.strip()
    user = await db.users.find_one({"phone": phone})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid mobile number or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated.")
    token = create_access_token(str(user["_id"]), phone, user.get("role", "sipahi"))
    response.set_cookie("access_token", token, httponly=True, secure=False, samesite="lax", max_age=36000, path="/")
    return _user_from_doc(user)


@router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out"}


@router.get("/auth/me")
async def get_me(request: Request):
    return await get_current_user(request)
