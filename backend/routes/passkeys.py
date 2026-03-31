"""WebAuthn / Passkey routes — optional biometric login for Bahi Khata."""
import os
import json
import secrets
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request, Response

from core.auth import create_access_token, get_current_user, _user_from_doc
from core.database import db

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorAttestationResponse,
    AuthenticatorAssertionResponse,
    AuthenticatorSelectionCriteria,
    AuthenticationCredential,
    RegistrationCredential,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)
from webauthn.helpers.cose import COSEAlgorithmIdentifier
from webauthn.helpers import bytes_to_base64url, base64url_to_bytes

router = APIRouter()

RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Bahi Khata")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "http://localhost:3000")


def _parse_registration(body: dict) -> RegistrationCredential:
    resp = body.get("response", {})
    return RegistrationCredential(
        id=body["id"],
        raw_id=base64url_to_bytes(body["rawId"]),
        response=AuthenticatorAttestationResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            attestation_object=base64url_to_bytes(resp["attestationObject"]),
            transports=resp.get("transports") or [],
        ),
        type=body.get("type", "public-key"),
    )


def _parse_authentication(body: dict) -> AuthenticationCredential:
    resp = body.get("response", {})
    user_handle = resp.get("userHandle")
    return AuthenticationCredential(
        id=body["id"],
        raw_id=base64url_to_bytes(body["rawId"]),
        response=AuthenticatorAssertionResponse(
            client_data_json=base64url_to_bytes(resp["clientDataJSON"]),
            authenticator_data=base64url_to_bytes(resp["authenticatorData"]),
            signature=base64url_to_bytes(resp["signature"]),
            user_handle=base64url_to_bytes(user_handle) if user_handle else None,
        ),
        type=body.get("type", "public-key"),
    )


# ── Registration ─────────────────────────────────────────────────────────────

@router.post("/auth/passkey/register-options")
async def passkey_register_options(request: Request):
    """Generate registration options. Requires existing auth (cookie)."""
    user = await get_current_user(request)
    user_id_str = user["id"]

    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_name=user.get("phone", user_id_str),
        user_id=user_id_str.encode(),
        user_display_name=user.get("name") or user.get("phone", ""),
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        supported_pub_key_algs=[
            COSEAlgorithmIdentifier.ECDSA_SHA_256,
            COSEAlgorithmIdentifier.RSASSA_PKCS1_v1_5_SHA_256,
        ],
    )

    await db.users.update_one(
        {"_id": ObjectId(user_id_str)},
        {
            "$set": {
                "webauthn_reg_challenge": bytes_to_base64url(options.challenge),
                "webauthn_reg_challenge_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )

    return json.loads(options_to_json(options))


@router.post("/auth/passkey/register-verify")
async def passkey_register_verify(request: Request):
    """Verify registration response and persist the passkey."""
    user = await get_current_user(request)
    user_id_str = user["id"]

    body = await request.json()

    user_doc = await db.users.find_one(
        {"_id": ObjectId(user_id_str)},
        {"webauthn_reg_challenge": 1},
    )
    if not user_doc or not user_doc.get("webauthn_reg_challenge"):
        raise HTTPException(
            status_code=400,
            detail="No registration session found. Please start again.",
        )

    expected_challenge = base64url_to_bytes(user_doc["webauthn_reg_challenge"])

    try:
        credential = _parse_registration(body)
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Verification failed: {exc}")

    passkey = {
        "credential_id": bytes_to_base64url(verification.credential_id),
        "public_key": bytes_to_base64url(verification.credential_public_key),
        "sign_count": verification.sign_count,
        "name": body.get("passkeyName", "Passkey"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "transports": (body.get("response") or {}).get("transports") or [],
    }

    await db.users.update_one(
        {"_id": ObjectId(user_id_str)},
        {
            "$push": {"passkeys": passkey},
            "$unset": {
                "webauthn_reg_challenge": "",
                "webauthn_reg_challenge_at": "",
            },
        },
    )

    return {"success": True, "message": "Passkey registered successfully"}


# ── Authentication ────────────────────────────────────────────────────────────

@router.post("/auth/passkey/auth-options")
async def passkey_auth_options(response: Response):
    """Generate authentication challenge (discoverable credentials)."""
    options = generate_authentication_options(
        rp_id=RP_ID,
        user_verification=UserVerificationRequirement.PREFERRED,
    )

    session_id = secrets.token_urlsafe(32)
    await db.webauthn_challenges.insert_one(
        {
            "session_id": session_id,
            "challenge": bytes_to_base64url(options.challenge),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    response.set_cookie(
        "wauthn_session",
        session_id,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=300,
        path="/",
    )

    return json.loads(options_to_json(options))


@router.post("/auth/passkey/auth-verify")
async def passkey_auth_verify(request: Request, response: Response):
    """Verify assertion, issue JWT cookie, return user data."""
    body = await request.json()

    credential_id = body.get("id")
    if not credential_id:
        raise HTTPException(status_code=400, detail="Missing credential ID")

    session_id = request.cookies.get("wauthn_session")
    if not session_id:
        raise HTTPException(
            status_code=400,
            detail="Authentication session not found. Please try again.",
        )

    challenge_doc = await db.webauthn_challenges.find_one({"session_id": session_id})
    if not challenge_doc:
        raise HTTPException(
            status_code=400,
            detail="Authentication session expired. Please try again.",
        )

    user_doc = await db.users.find_one({"passkeys.credential_id": credential_id})
    if not user_doc:
        raise HTTPException(
            status_code=401,
            detail="Passkey not registered. Please log in with your password first.",
        )

    matching_pk = next(
        (pk for pk in user_doc.get("passkeys", []) if pk["credential_id"] == credential_id),
        None,
    )
    if not matching_pk:
        raise HTTPException(status_code=401, detail="Passkey not found")

    if not user_doc.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account deactivated.")

    expected_challenge = base64url_to_bytes(challenge_doc["challenge"])

    try:
        credential = _parse_authentication(body)
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=base64url_to_bytes(matching_pk["public_key"]),
            credential_current_sign_count=matching_pk["sign_count"],
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Passkey verification failed: {exc}")

    # Update sign count
    await db.users.update_one(
        {"_id": user_doc["_id"], "passkeys.credential_id": credential_id},
        {"$set": {"passkeys.$.sign_count": verification.sign_count}},
    )
    await db.webauthn_challenges.delete_one({"_id": challenge_doc["_id"]})
    response.delete_cookie("wauthn_session", path="/")

    token = create_access_token(
        str(user_doc["_id"]),
        user_doc.get("phone", ""),
        user_doc.get("role", "sipahi"),
    )
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=36000,
        path="/",
    )

    return _user_from_doc(user_doc)


# ── Management ────────────────────────────────────────────────────────────────

@router.get("/auth/passkey/list")
async def passkey_list(request: Request):
    """Return the current user's registered passkeys (no private data)."""
    user = await get_current_user(request)
    user_doc = await db.users.find_one(
        {"_id": ObjectId(user["id"])}, {"passkeys": 1}
    )
    return [
        {
            "credential_id": pk["credential_id"],
            "name": pk.get("name", "Passkey"),
            "created_at": pk.get("created_at"),
            "transports": pk.get("transports", []),
        }
        for pk in (user_doc or {}).get("passkeys", [])
    ]


@router.delete("/auth/passkey/{credential_id}")
async def passkey_delete(credential_id: str, request: Request):
    """Remove a passkey from the current user's account."""
    user = await get_current_user(request)
    result = await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {"$pull": {"passkeys": {"credential_id": credential_id}}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Passkey not found")
    return {"success": True}
