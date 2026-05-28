from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import Response as FastResponse
import uuid
import tempfile
import os
import re
import json
import logging
import io
import jwt
from PIL import Image
from core.storage import get_object, put_object, APP_NAME, MIME_TYPES, EMERGENT_KEY
from core.auth import get_current_user, JWT_ALGORITHM, get_jwt_secret
from models import OCRRequest, TransliterateRequest
from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_DIMENSION = 1920   # px — long edge cap
JPEG_QUALITY  = 78     # good balance of clarity vs size


def compress_image(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Resize to MAX_DIMENSION on the long edge and re-encode as JPEG.
    Returns (compressed_bytes, 'image/jpeg').  PDFs pass through unchanged."""
    if content_type == "application/pdf":
        return data, content_type
    try:
        img = Image.open(io.BytesIO(data))
        # Convert palette / RGBA → RGB so JPEG encoding works
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        # Resize only if larger than MAX_DIMENSION
        w, h = img.size
        if max(w, h) > MAX_DIMENSION:
            scale = MAX_DIMENSION / max(w, h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        compressed = buf.getvalue()
        logger.info(f"Image compressed: {len(data)/1024:.0f}KB → {len(compressed)/1024:.0f}KB")
        return compressed, "image/jpeg"
    except Exception as e:
        logger.warning(f"Compression failed, storing original: {e}")
        return data, content_type


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    await get_current_user(request)
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "bin"
    ct = MIME_TYPES.get(ext, file.content_type or "application/octet-stream")
    data = await file.read()
    original_size = len(data)
    # Compress images before storing
    data, ct = compress_image(data, ct)
    # Always store as .jpg after compression (unless PDF)
    store_ext = ext if ct == "application/pdf" else "jpg"
    path = f"{APP_NAME}/uploads/{uuid.uuid4()}.{store_ext}"
    result = put_object(path, data, ct)
    return {
        "path": result["path"],
        "size": len(data),
        "original_size": original_size,
        "content_type": ct,
    }


@router.get("/files/{path:path}")
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


@router.post("/verify-face")
async def verify_face(data: OCRRequest, request: Request):
    """Check whether the uploaded photo contains a real human face (KYC live photo validation)."""
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
            session_id=f"face-verify-{uuid.uuid4()}",
            system_message="You are a face verification assistant for KYC compliance. Analyse photos strictly and objectively."
        ).with_model("gemini", "gemini-2.5-flash")

        img = FileContentWithMimeType(file_path=tmp_path, mime_type=ct or "image/jpeg")
        msg = UserMessage(
            text="""Look at this photo carefully and answer these questions:
1. Does the photo contain a clearly visible human face of a real person?
2. Is the face of a real live person (not a photo of a photo, drawing, or ID card)?
3. Is the face reasonably well-lit and in focus enough for identity verification?

Return ONLY a valid JSON object — no markdown, no explanation:
{
  "has_face": true or false,
  "is_real_person": true or false,
  "is_clear_enough": true or false,
  "reason": "one short sentence explaining the result"
}""",
            file_contents=[img]
        )
        raw = await chat.send_message(msg)
        raw = re.sub(r'```[a-z]*\n?', '', raw).strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        result = json.loads(m.group()) if m else {}
        has_face = bool(result.get("has_face")) and bool(result.get("is_real_person"))
        return {
            "has_face": has_face,
            "is_clear_enough": bool(result.get("is_clear_enough", True)),
            "reason": result.get("reason", ""),
        }
    except Exception as e:
        logger.error(f"Face verification error: {e}")
        # Fail open on API errors to avoid blocking the workflow
        return {"has_face": True, "is_clear_enough": True, "reason": "Verification skipped (service error)"}
    finally:
        os.unlink(tmp_path)


@router.post("/ocr/aadhaar")
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


@router.post("/ocr/aadhaar-back")
async def ocr_aadhaar_back(data: OCRRequest, request: Request):
    """OCR for Aadhaar card back side — extracts Address and Husband/Father name."""
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
            session_id=f"ocr-back-{uuid.uuid4()}",
            system_message="You are an expert OCR system for Indian Aadhaar cards. Extract all visible text accurately."
        ).with_model("gemini", "gemini-2.5-flash")

        img = FileContentWithMimeType(file_path=tmp_path, mime_type=ct or "image/jpeg")
        msg = UserMessage(
            text="""Examine this image of the BACK side of an Indian Aadhaar card.

The back of an Aadhaar card typically contains:
- RELATIVE'S NAME: printed as "S/O" (Son of), "W/O" (Wife of), "D/O" (Daughter of), or "C/O" (Care of) followed by the relative's name. This is the husband's or father's name.
- ADDRESS: full residential address spanning multiple lines — house/door no, street/mohalla/locality, village/town/city, district, state, PIN code.
- AADHAAR NUMBER: 12-digit number (may appear as text or encoded in the barcode/QR code — look for any 12-digit number).

Extract these fields and return ONLY a valid JSON object — no markdown, no code blocks, no explanation:
{
  "relative_name": "full name of the relative as printed (without the S/O W/O D/O prefix)",
  "address": "complete address — all components joined on one line separated by commas",
  "aadhaar_number": "12-digit Aadhaar number formatted as XXXX XXXX XXXX or null if not visible"
}

Use null if a field is not clearly readable.""",
            file_contents=[img]
        )
        raw = await chat.send_message(msg)
        raw = re.sub(r'```[a-z]*\n?', '', raw).strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        extracted = json.loads(m.group()) if m else {}
        return extracted
    except Exception as e:
        logger.error(f"Aadhaar back OCR error: {e}")
        return {"relative_name": None, "address": None}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/transliterate")
async def transliterate_to_hindi(data: TransliterateRequest, request: Request):
    """Transliterate an English Indian name to Hindi (Devanagari script) using Gemini."""
    await get_current_user(request)
    if not data.text or not data.text.strip():
        return {"hindi": ""}
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            session_id=f"trans-{uuid.uuid4()}",
            system_message="You are an expert transliterator for Indian names. Your only task is to convert English text to Hindi Devanagari script phonetically."
        ).with_model("gemini", "gemini-2.5-flash")
        msg = UserMessage(
            text=f"""Transliterate the following Indian person name from English into Hindi (Devanagari script).
Return ONLY the Devanagari transliteration — nothing else, no explanation, no punctuation.
Name: {data.text.strip()}"""
        )
        result = await chat.send_message(msg)
        return {"hindi": result.strip()}
    except Exception as e:
        logger.error(f"Transliteration error: {e}")
        return {"hindi": ""}
