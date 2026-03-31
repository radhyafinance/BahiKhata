import os, jwt, bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request
from bson import ObjectId
from core.database import db

JWT_ALGORITHM = "HS256"
ROLES = ["admin", "maalik", "muneem", "sipahi"]


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(user_id: str, phone: str, role: str) -> str:
    return jwt.encode(
        {"sub": user_id, "phone": phone, "role": role,
         "exp": datetime.now(timezone.utc) + timedelta(hours=10), "type": "access"},
        get_jwt_secret(), algorithm=JWT_ALGORITHM
    )


def _user_from_doc(doc: dict) -> dict:
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    d.pop("password_hash", None)
    # Passkey fields: expose only a boolean flag, never raw credential data
    d["has_passkeys"] = len(d.pop("passkeys", [])) > 0
    d.pop("webauthn_reg_challenge", None)
    d.pop("webauthn_reg_challenge_at", None)
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
