import re
import asyncio
import calendar
import contextlib
import logging
import random
import time
import unicodedata
from datetime import datetime, timezone, timedelta, date as date_type
from bson import ObjectId
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from core.database import db


def _doc(d: dict) -> dict:
    d = dict(d)
    d["id"] = str(d.pop("_id"))
    return d


async def generate_customer_id(illaka_name: str) -> str:
    """Generate Customer ID: 2 uppercase letters from Illaka + 4-digit sequential per prefix."""
    prefix = re.sub(r'[^A-Za-z]', '', illaka_name)[:2].upper()
    if len(prefix) < 2:
        prefix = (prefix + 'XX')[:2]
    last = await db.kycs.find_one(
        {"customer_id": {"$regex": f"^{re.escape(prefix)}\\d{{4}}$"}},
        sort=[("customer_id", -1)]
    )
    num = 1
    if last and last.get("customer_id"):
        try:
            num = int(last["customer_id"][len(prefix):]) + 1
        except (ValueError, IndexError):
            num = 1
    return f"{prefix}{num:04d}"


async def insert_kyc(doc: dict, illaka_name: str, attempts: int = 40):
    """Insert a KYC, taking the next customer id if another request took this one.

    The id is the highest existing one plus one, so two clients created in the
    same Illaka at the same moment both picked the same id; the unique index
    refused the second and it surfaced as a 500.
    """
    # Many requests retrying at once all pick "highest + 1" again; a short random
    # pause spreads them out so each finds a free number.
    for attempt in range(attempts):
        try:
            return await db.kycs.insert_one(doc)
        except DuplicateKeyError as exc:
            if "customer_id" not in str(exc):
                raise
            await asyncio.sleep(random.uniform(0, 0.02 * (attempt + 1)))
            doc["customer_id"] = await generate_customer_id(illaka_name)
            if "kyc_number" in doc:
                doc["kyc_number"] = doc["customer_id"]
    raise HTTPException(status_code=409, detail="Could not allocate a customer id just now — please try again.")


async def generate_loan_number(customer_id: str, kyc_id: str) -> str:
    """Generate Loan ID: {customer_id}-L{n}, one past the highest already used.

    This was count_documents() + 1, which reuses a number as soon as any loan is
    deleted: create two loans, delete the first, and the third is handed the same
    number as the second. That was merely untidy while nothing enforced
    uniqueness — but loan_number now carries a unique index, so the reuse raises
    DuplicateKeyError and the customer can never be given another loan.

    Reading the highest suffix instead means numbers are never reused. Callers
    still retry on collision, since two simultaneous loans can read the same
    highest value. The client's loans are found whatever case their kyc_id was
    stored in — an upper-cased legacy id hid a loan, so its number was handed out
    again and every new loan for that client failed.
    """
    prefix = f"{customer_id}-L"
    highest = 0
    kid = str(kyc_id or "").strip()
    query = ({"kyc_id": {"$regex": rf"^\s*{re.escape(kid)}\s*$", "$options": "i"}} if kid
             else {"loan_number": {"$regex": f"^{re.escape(prefix)}"}})
    async for d in db.loans.find(query, {"loan_number": 1}):
        num = str(d.get("loan_number") or "")
        if num.startswith(prefix):
            try:
                highest = max(highest, int(num[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{highest + 1}"


_MONTH_RE = re.compile(r"(20[0-9]{2})-(0[1-9]|1[0-2])", re.ASCII)


def is_valid_month(value) -> bool:
    """A real YYYY-MM in 2000-2099, written in ASCII digits.

    `\\d` also matches Devanagari and Arabic-Indic digits, and nothing bounded the
    year, so "२०२६-09" and "0000-01" were accepted as collection months: they were
    marked paid, booked to the journal, and year 0000 then crashed every attempt
    to uncollect it — a row nobody could remove.
    """
    return isinstance(value, str) and bool(_MONTH_RE.fullmatch(value))


# ─── One change at a time per loan ────────────────────────────────────────────
#
# Every operation that changes a loan is a sequence — read, check, write several
# documents — and two such sequences on the same loan used to interleave. Each
# acted on a picture of the loan the other had already made stale: cash booked
# for a collection that had just been uncollected, a balance written off at year
# end while a net-off settled it, two recoveries both passing the "not more than
# owed" check. The trial balance still balanced in every case, so nothing
# surfaced it. Patching each pairing with a conditional write did not converge:
# three rounds of testing each found new pairings.
#
# So an operation takes a short lock on the loan first, and does all of its
# reading, checking and writing while it holds it. Different loans never wait
# for each other. The lock is a document in Mongo, so it holds across several
# server processes.
#
# A holder refreshes its lock every few seconds while it works. A lock that has
# not been refreshed for `stale` seconds belongs to a process that died, and is
# taken over. Without the refresh, a request that merely ran long lost its lock
# to the next one and both wrote at once. The refresh runs on the request's own
# worker, so a worker frozen by a blocking call cannot refresh: `stale` is set
# longer than the slowest blocking call the app makes (the photo upload, which
# times out after 120 seconds).

LOCK_WAIT_SECONDS = 10.0
LOCK_STALE_SECONDS = 180.0
LOCK_HEARTBEAT_SECONDS = 10.0
BUSY_CLIENT = ("This client is being updated by someone else. Please try again in a moment. "
               "/ यह ग्राहक अभी अपडेट हो रहा है, थोड़ी देर बाद फिर कोशिश करें।")


@contextlib.asynccontextmanager
async def entity_lock(key: str, wait: float = LOCK_WAIT_SECONDS, stale: float = LOCK_STALE_SECONDS,
                      busy: str = BUSY_CLIENT):
    token = str(ObjectId())
    deadline = time.monotonic() + wait
    delay = 0.01
    while True:
        now = datetime.now(timezone.utc)
        try:
            await db.locks.insert_one({"_id": key, "token": token, "at": now})
            break
        except DuplicateKeyError:
            taken = await db.locks.update_one(
                {"_id": key, "at": {"$lt": now - timedelta(seconds=stale)}},
                {"$set": {"token": token, "at": now}},
            )
            if taken.modified_count:
                logging.getLogger(__name__).warning("Took over a stale lock on %s", key)
                break
            if time.monotonic() >= deadline:
                raise HTTPException(status_code=409, detail=busy)
            await asyncio.sleep(delay + random.uniform(0, delay))
            delay = min(delay * 2, 0.2)

    async def _heartbeat():
        # A failed refresh must not end the heartbeat: one database hiccup used to
        # stop it silently, the lock aged out, and a second request took it over
        # while the first was still writing.
        while True:
            try:
                await asyncio.sleep(LOCK_HEARTBEAT_SECONDS)
                await db.locks.update_one({"_id": key, "token": token},
                                          {"$set": {"at": datetime.now(timezone.utc)}})
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logging.getLogger(__name__).warning("Lock heartbeat for %s failed, retrying: %s", key, exc)

    beat = asyncio.create_task(_heartbeat())
    try:
        yield
    finally:
        beat.cancel()
        await db.locks.delete_one({"_id": key, "token": token})


def loan_lock(loan_id: str, **kw):
    return entity_lock(f"loan:{loan_id}", **kw)


def kyc_lock(kyc_id, **kw):
    """Serialises lending decisions for one client, so a write-off and a new loan
    for the same KYC cannot pass each other. A missing id locks nothing."""
    try:
        return entity_lock(f"kyc:{ObjectId(str(kyc_id).strip())}", **kw)
    except Exception:
        return contextlib.nullcontext()


# ─── Closed years ────────────────────────────────────────────────────────────
#
# Once a year-end closing is recorded for an Illaka, nothing dated on or before
# its date may change: no collection, removal, edit or re-dating of a payment,
# and no loan paid out, re-dated or deleted there. Those books have been closed
# and the write-offs worked out from them. Undo the closing to correct them.

_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)


def valid_date(value, label: str = "Date") -> str:
    """A date as YYYY-MM-DD, or 400.

    Dates were stored as typed. "2026/03/15", "2026-3-15", "20260316" and a blank
    date were all accepted; every check compares dates as text, so those slipped
    past the closed-year lock and the past-month rule, and a loan dated
    "20230110" was never written off.
    """
    text = str(value or "").strip()
    try:
        if _DATE_RE.fullmatch(text):
            return date_type.fromisoformat(text).isoformat()
    except ValueError:
        pass
    raise HTTPException(status_code=400, detail=f"{label} must be a date in YYYY-MM-DD form / तारीख YYYY-MM-DD में लिखें")


def _day(value) -> str:
    """A stored date as YYYY-MM-DD, however an older record wrote it; "" if unreadable.

    Records saved before dates were checked hold "01/10/2025", "20230110" or a
    time after the date. Compared as text they read as a very old date (or a
    very new one), so an old loan looked closed-year or over three years old.
    """
    text = str(value or "").strip()
    for candidate in (text[:10], text):
        try:
            if _DATE_RE.fullmatch(candidate):
                return date_type.fromisoformat(candidate).isoformat()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", text[:10])
    if m:
        try:
            return date_type(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return ""
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text[:8])
    if m:
        try:
            return date_type(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return ""
    return ""


async def latest_closing_date(illaka_id) -> str:
    rec = await db.illaka_closings.find_one({"illaka_id": illaka_id}, sort=[("closing_date", -1)])
    return str((rec or {}).get("closing_date") or "")


async def assert_open_period(illaka_id, *dates, what: str = "This change", undated_is_closed: bool = False) -> None:
    """`undated_is_closed`: an existing payment with no readable date may belong to
    the closed year, so once a year is closed it cannot be changed either."""
    closing = await latest_closing_date(illaka_id)
    if not closing:
        return
    for d in dates:
        if not _day(d) and undated_is_closed:
            raise HTTPException(
                status_code=403,
                detail=(f"{what} has no date on record, so it may belong to a year already closed ({closing}). "
                        f"Undo the year-end closing first to change it. / बंद साल की एंट्री नहीं बदली जा सकती।"),
            )
        if _day(d) and _day(d) <= closing:
            raise HTTPException(
                status_code=403,
                detail=(f"{what} is dated {_day(d)}, in a year already closed ({closing}). Undo the "
                        f"year-end closing first to change it. / बंद साल की एंट्री नहीं बदली जा सकती।"),
            )


# ─── Identity: Aadhaar and phone ──────────────────────────────────────────────

def _ascii_digits(text: str) -> str:
    """Devanagari, full-width and other decimal digits become 0-9."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text)


def _clean_number_text(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        f = float(value)
        return str(int(f)) if f.is_integer() else str(value)
    s = _ascii_digits(str(value)).strip()
    # Spreadsheet cells arrive as "9876543210.0" or "9.87654321E9"
    if re.fullmatch(r"[0-9]+\.0+", s):
        s = s.split(".")[0]
    elif re.fullmatch(r"[0-9]\.[0-9]+[eE]\+?[0-9]+", s):
        try:
            f = float(s)
            if f.is_integer():
                s = str(int(f))
        except ValueError:
            pass
    return s


_PHONE_PREFIXES = ("0091", "091", "91", "0")


def _one_mobile(digits: str) -> str:
    for prefix in _PHONE_PREFIXES:
        if len(digits) == 10 + len(prefix) and digits.startswith(prefix):
            digits = digits[len(prefix):]
            break
    if len(digits) == 10 and digits[0] in "6789" and len(set(digits)) > 1:
        return digits
    return ""


def phone_candidates(value) -> list:
    """Every 10-digit mobile number written in a field, in order.

    The digits are read as runs ("+91 (0) 98765 43210" is 91 / 0 / 98765 / 43210)
    and neighbouring runs are joined until they make a mobile number, with or
    without a +91 / 0 prefix. So "Ph: 9876543210 (self)", "98765 43210" and a
    field holding two numbers all read correctly. A run that belongs to a number
    already found is not reused, and a number with an extra digit is not guessed
    at — guessing matched healthy clients to Gyal ones. Placeholders read as
    nothing, so they never link people.
    """
    s = _clean_number_text(value)
    runs = re.findall(r"[0-9]+", s)
    out, i = [], 0
    while i < len(runs):
        acc, found_at = "", None
        for j in range(i, len(runs)):
            acc += runs[j]
            if len(acc) > 14:
                break
            mobile = _one_mobile(acc)
            if mobile:
                found_at = (j, mobile)
                break
        if found_at:
            j, mobile = found_at
            if mobile not in out:
                out.append(mobile)
            i = j + 1
        else:
            i += 1
    return out


def normalize_phone(value) -> str:
    found = phone_candidates(value)
    return found[0] if found else ""


def normalize_aadhaar(value) -> str:
    """The 12 Aadhaar digits, whatever separators or script were typed, or "".

    Aadhaar numbers never start with 0 or 1; all-one-digit values are placeholders.
    """
    digits = re.sub(r"[^0-9]", "", _clean_number_text(value))
    if len(digits) != 12 or digits[0] in "01" or len(set(digits)) == 1:
        return ""
    return digits


def validate_phone(value, label: str = "Phone") -> str:
    """For saving: blank, or exactly one mobile number. Returns it as 10 digits.

    Words around the number are fine ("Ph: 9876543210 (self)"); two numbers, a
    number with a digit missing or extra, or a landline are not.
    """
    s = _clean_number_text(value)
    digits = re.sub(r"[^0-9]", "", s)
    if not digits:
        return ""
    found = phone_candidates(s)
    # The digits must be written as one number: groups separated only by spaces,
    # dashes, dots or brackets, with an optional + in front, and a +91 / 0 prefix
    # only as its own group. Words may come before or after, but not between the
    # groups — "941501234, 2 members" used to be saved as 9415012342, and an
    # Aadhaar typed into the phone field as a mobile number.
    span = s[re.search(r"[0-9]", s).start(): len(s) - re.search(r"[0-9]", s[::-1]).start()]
    groups = re.split(r"[ .\-()]+", span)
    one_number = bool(re.fullmatch(r"[0-9][0-9 .\-()]*", span)) and bool(found) and (
        len(digits) == 10
        or (len(digits) == 11 and digits.startswith("0"))
        or len(groups) == 1
        or groups[0] in ("0", "91", "091", "0091")
        or s.lstrip().startswith("+")
    )
    if len(found) != 1 or not one_number or len(digits) > len(found[0]) + 4:
        raise HTTPException(
            status_code=400,
            detail=(f"{label} must be one 10-digit mobile number (it may start with +91 or 0). "
                    f"/ {label}: 10 अंकों का एक मोबाइल नंबर डालें।"),
        )
    return found[0]


_VERHOEFF_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
               [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
               [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
               [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VERHOEFF_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
               [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
               [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def aadhaar_checksum_ok(digits: str) -> bool:
    """Every real Aadhaar ends in a Verhoeff check digit, so a made-up or mistyped
    number (one digit wrong, two digits swapped) fails."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def validate_aadhaar(value, label: str = "Aadhaar") -> str:
    """For saving: blank, or a valid 12-digit Aadhaar. Returns it as "XXXX XXXX XXXX".

    Only numbers being entered or changed come here; ones already saved are kept."""
    s = _clean_number_text(value)
    if not re.sub(r"[^0-9]", "", s):
        return ""
    digits = normalize_aadhaar(s)
    if not digits or re.search(r"[A-Za-z]", s):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be a 12-digit Aadhaar number. / {label}: 12 अंकों का आधार नंबर डालें।",
        )
    if not aadhaar_checksum_ok(digits):
        raise HTTPException(
            status_code=400,
            detail=(f"{label} is not a valid Aadhaar number — please check it for a mistyped digit. "
                    f"/ {label}: आधार नंबर सही नहीं है, एक-एक अंक जाँचें।"),
        )
    return f"{digits[0:4]} {digits[4:8]} {digits[8:12]}"


def _as_person_dict(person) -> dict:
    """Anything person-shaped as a dict; anything else as {}.

    One old record with its co-borrower stored as the string "N/A" crashed every
    lending check in the business with a 500.
    """
    if person is None:
        return {}
    if hasattr(person, "model_dump"):
        try:
            return person.model_dump()
        except Exception:
            return {}
    return person if isinstance(person, dict) else {}


def clean_person(person, label: str, previous=None):
    """Validate and normalise a person's phone and Aadhaar before it is saved.

    Only values that are being CHANGED are checked. An older record holding a
    phone typed before format checks existed — "98234 (wife)", two numbers —
    used to make every save of that KYC fail, even an address change. An
    unchanged value is kept exactly as it was.
    """
    if person is None:
        return None
    data = dict(_as_person_dict(person))
    prev = _as_person_dict(previous)
    for field, check in (("phone", validate_phone), ("aadhaar_number", validate_aadhaar)):
        if field not in data:
            continue
        new_raw = str(data.get(field) or "").strip()
        old_raw = str(prev.get(field) or "").strip()
        same = new_raw == old_raw
        if not same and new_raw and field == "aadhaar_number":
            # The same number retyped in another layout is not a change.
            same = bool(normalize_aadhaar(new_raw)) and normalize_aadhaar(new_raw) == normalize_aadhaar(old_raw)
        if new_raw and same:
            data[field] = prev.get(field)
            continue
        data[field] = check(data.get(field), f"{label} {'phone' if field == 'phone' else 'Aadhaar'}")
    return data


def _person_snapshot(person) -> dict:
    p = _as_person_dict(person)
    phones = phone_candidates(p.get("phone"))
    for ph in p.get("phones") or []:
        if ph not in phones:
            phones.append(ph)
    return {
        "name": str(p.get("name") or "").strip(),
        "aadhaar": normalize_aadhaar(p.get("aadhaar_number") or p.get("aadhaar")),
        "phones": phones,
    }


def _merge_snapshots(base: dict, extra: dict) -> dict:
    merged = dict(base)
    if not merged.get("aadhaar") and extra.get("aadhaar"):
        merged["aadhaar"] = extra["aadhaar"]
    merged["phones"] = list(base.get("phones") or [])
    for ph in extra.get("phones") or []:
        if ph not in merged["phones"]:
            merged["phones"].append(ph)
    if not merged.get("name") and extra.get("name"):
        merged["name"] = extra["name"]
    return merged


def loan_people(kyc: dict = None, overrides: dict = None, replace_roles=("co_borrower", "guarantor")) -> dict:
    """Who is on a loan, as recorded at the moment the money goes out.

    Stored on the loan itself, and never changed afterwards except by an admin
    correcting a data-entry mistake.

    A phone typed on the loan or re-loan screen is ADDED to the borrower's
    identity from the KYC, never substituted for it — substituting let a person
    linked to a Gyal loan by phone through just by typing another number.

    For a role in `replace_roles`, a full person supplied with the request (a
    re-loan naming a new co-borrower) replaces the KYC's; a phone-only override
    is merged like the borrower's.
    """
    kyc = kyc or {}
    overrides = overrides or {}
    people = {}
    for role, field in (("borrower", "primary_borrower"), ("co_borrower", "co_borrower"),
                        ("guarantor", "guarantor")):
        base = _person_snapshot(kyc.get(field))
        over = overrides.get(role)
        if not over:
            people[role] = base
            continue
        over_snap = _person_snapshot(over)
        over_dict = _as_person_dict(over)
        full_person = bool(str(over_dict.get("name") or "").strip() or over_snap["aadhaar"])
        if role in replace_roles and full_person:
            people[role] = over_snap
        else:
            people[role] = _merge_snapshots(base, over_snap)
    return people


def _canon_id(value) -> str:
    try:
        return str(ObjectId(str(value).strip()))
    except Exception:
        return ""


def _id_variants(kid: str) -> list:
    """The forms a KYC id may be stored in by older code."""
    out = [kid, kid.upper()]
    try:
        out.append(ObjectId(kid))
    except Exception:
        pass
    return out


def paid_so_far(loan: dict) -> float:
    """What a loan has been repaid. An older record with no total_paid is read from
    its paid instalments — reading it as nothing called a repaid loan fully owed."""
    if loan.get("total_paid") is None:
        return round(sum(float(e.get("paid_amount") or 0) for e in loan.get("emi_schedule") or []
                         if e.get("status") == "paid"), 2)
    return float(loan.get("total_paid") or 0)


def today_local() -> date_type:
    """Today in India. The server clock runs on UTC, so between midnight and 5:30
    in the morning its "today" was still yesterday and a loan dated today was
    refused as a future date."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def assert_field_loan_date(user: dict, loan_date: str) -> None:
    """Field staff date a new loan or re-loan from the first of last month up to
    today. Any date was accepted, years ahead (nothing fell due) or years back (the
    loan was written off within months). Admin and maalik may use any date."""
    if user.get("role") in ("admin", "maalik"):
        return
    today = today_local()
    first_last_month = _add_months(today.replace(day=1), -1).isoformat()
    day = _day(loan_date)
    if not day or day < first_last_month or day > today.isoformat():
        raise HTTPException(
            status_code=403,
            detail=(f"A loan can be dated from {first_last_month} to today. For another date, save it dated "
                    f"today and ask an admin or maalik to correct the date. / कर्ज़ की तारीख पिछले महीने की 1 "
                    f"तारीख से आज तक ही हो सकती है।"),
        )


BORROWER_IDENTITY_REQUIRED = ("A loan needs the borrower's Aadhaar or mobile number. / कर्ज़ के लिए उधारकर्ता का "
                              "आधार या मोबाइल नंबर ज़रूरी है।")


async def assert_misal_in_illaka(misal_id, illaka_id) -> None:
    """A misal must belong to the Illaka it is used with. Nothing checked it, so a
    loan could be put in one Illaka with another Illaka's misal and then vanish
    from that Illaka's lists."""
    try:
        misal = await db.misals.find_one({"_id": ObjectId(str(misal_id).strip())}, {"illaka_id": 1})
    except Exception:
        return
    if misal and misal.get("illaka_id") and str(misal["illaka_id"]) != str(illaka_id):
        raise HTTPException(status_code=400, detail="This Misal belongs to a different Illaka. / यह मिसल दूसरे इलाके की है।")


async def illaka_requires_aadhaar(illaka_id) -> bool:
    """Whether loans in this Illaka need the borrower's Aadhaar. On unless an admin
    has switched it off for the Illaka."""
    try:
        ill = await db.illakas.find_one({"_id": ObjectId(str(illaka_id).strip())}, {"aadhaar_required": 1})
    except Exception:
        return True
    return (ill or {}).get("aadhaar_required") is not False


async def client_loans(kyc_id, projection: dict) -> list:
    """Every loan of one client, however older records stored its KYC id."""
    kid = _canon_id(kyc_id)
    if not kid:
        return []
    return await db.loans.find({"$or": [{"kyc_id": {"$in": _id_variants(kid)}}, {"kyc_id_canon": kid},
                                        {"kyc_id": {"$regex": f"^\\s*{kid}\\s*$", "$options": "i"}}]},
                               projection).to_list(None)


async def assert_no_old_debt(kyc_id, people: dict = None, editing: tuple = None) -> None:
    """Refuse new money to a client with a loan over three years old that still owes.

    Such a loan is due to be written off at year end. Only a re-loan on that one
    loan used to be refused, so the same client still got a new loan, a quick-add,
    a re-loan on a newer loan or a raised amount — the Re-Loan button itself picks
    the newest loan.

    `people`: the borrower of the new money is also matched by Aadhaar and phone
    against the borrower or co-borrower recorded on other clients' loans — the
    same person moved to a fresh KYC was lent to again.
    `editing`: (loan id, its new total repayable) for a loan whose amount is being
    raised, judged at the new amount — shrinking an old loan to nothing, lending,
    then restoring it used to pass.
    """
    cutoff = _add_months(today_local(), -36).isoformat()
    fields = {"loan_number": 1, "loan_date": 1, "total_paid": 1, "total_repayable": 1, "client_name": 1,
              "is_gyal": 1, "netoff_closed": 1, "emi_schedule": 1, "closed_by_admin": 1}
    # The borrower's own loans (by KYC), then — for the borrower, co-borrower and
    # guarantor alike — any loan on which that person is recorded as borrower or
    # co-borrower. A client with old unpaid debt could otherwise still stand as
    # someone else's co-borrower or guarantor.
    own_ids = set()
    loans = {}
    for ln in await client_loans(kyc_id, fields):
        loans[str(ln["_id"])] = (ln, "borrower")
        own_ids.add(str(ln["_id"]))
    matched_kycs: dict = {}   # kyc id -> role, looked up in one go below

    def _other_person(person: dict, given: set) -> bool:
        """The person on record has an Aadhaar and it is not the one given: a
        different person who happens to share the phone (a spouse, a family
        phone) — not a match."""
        rec = {normalize_aadhaar(person.get("aadhaar") or person.get("aadhaar_number"))}
        rec |= set(person.get("other_aadhaars") or [])
        rec.discard("")
        return bool(given) and bool(rec) and not (rec & given)

    for role in ("borrower", "co_borrower", "guarantor"):
        aadhaars, phones = _snapshot_keys((people or {}).get(role))
        # Anyone with an Aadhaar (borrower, co-borrower or guarantor) is matched by
        # it, and by phone only against people on record with no Aadhaar or the
        # same one: a spouse or husband sharing the family phone was blocked over
        # someone else's old debt. (Ignoring the phone altogether let an old
        # debtor through by typing any Aadhaar.)
        aadhaar_first = bool(aadhaars)
        if aadhaars:
            q = [{f"people.{r}.{f}": {"$in": sorted(aadhaars)}}
                 for r in ("borrower", "co_borrower") for f in ("aadhaar", "other_aadhaars")]
            for ln in await db.loans.find({"$or": q, "is_gyal": {"$ne": True}}, dict(fields, people=1)).to_list(None):
                loans.setdefault(str(ln["_id"]), (ln, role))
        if phones:
            q = [{f"people.{r}.phones": {"$in": sorted(phones)}} for r in ("borrower", "co_borrower")]
            for ln in await db.loans.find({"$or": q, "is_gyal": {"$ne": True}}, dict(fields, people=1)).to_list(None):
                if aadhaar_first:
                    holders = [p for p in ((ln.get("people") or {}).get(r) or {} for r in ("borrower", "co_borrower"))
                               if set(p.get("phones") or []) & phones]
                    if holders and all(_other_person(p, aadhaars) for p in holders):
                        continue
                loans.setdefault(str(ln["_id"]), (ln, role))
        # The person's own client records as they stand now. A number added to a
        # KYC afterwards — Add Aadhaar, a changed phone — never reaches the people
        # recorded on the client's old loans, so they were matched only by the
        # numbers typed back then.
        kyc_ors = []
        for a in aadhaars:
            pat = "^\\D*" + "\\D*".join(a) + "\\D*$"
            kyc_ors += [{f"{f}.aadhaar_number": {"$regex": pat}} for f in ("primary_borrower", "co_borrower")]
        for ph in phones:
            # Anywhere in the field, as a whole number: older records hold two
            # numbers in one phone field.
            pat = "(?<![0-9])(?:(?:00)?91|0)?\\D*" + "\\D*".join(ph[-10:]) + "(?![0-9])"
            kyc_ors += [{f"{f}.{k}": {"$regex": pat}} for f in ("primary_borrower", "co_borrower")
                        for k in ("phone", "phone_history")]
        if kyc_ors:
            async for k in db.kycs.find({"$or": kyc_ors}, {"primary_borrower": 1, "co_borrower": 1}):
                if kyc_id and str(k["_id"]) == _canon_id(kyc_id):
                    continue
                if aadhaar_first:
                    ids = []
                    for f in ("primary_borrower", "co_borrower"):
                        snap = _person_snapshot(k.get(f))
                        # A number the person used before counts as theirs too.
                        for old in (_as_person_dict(k.get(f)).get("phone_history") or []):
                            for ph in phone_candidates(old):
                                if ph not in snap["phones"]:
                                    snap["phones"].append(ph)
                        ids.append(snap)
                    by_aadhaar = any(p["aadhaar"] in aadhaars for p in ids if p["aadhaar"])
                    holders = [p for p in ids if set(p["phones"]) & phones]
                    if not by_aadhaar and holders and all(_other_person(p, aadhaars) for p in holders):
                        continue
                matched_kycs.setdefault(str(k["_id"]), role)
    if matched_kycs:
        # One query for every matched client (looked up one by one, a phone
        # shared by thousands of records took minutes).
        variants = [v for kid in matched_kycs for v in _id_variants(kid)]
        ors = [{"kyc_id": {"$in": variants}}, {"kyc_id_canon": {"$in": list(matched_kycs)}}]
        # Older loans stored the id padded with spaces or in capitals.
        ids = list(matched_kycs)
        for i in range(0, len(ids), 300):
            ors.append({"kyc_id": {"$regex": "^\\s*(" + "|".join(ids[i:i + 300]) + ")\\s*$", "$options": "i"}})
        async for ln in db.loans.find({"$or": ors, "is_gyal": {"$ne": True}}, fields):
            kid = _canon_id(ln.get("kyc_id")) or str(ln.get("kyc_id_canon") or "")
            loans.setdefault(str(ln["_id"]), (ln, matched_kycs.get(kid, "borrower")))
    for lid, (ln, role) in loans.items():
        if editing and lid == str(editing[0]):
            ln = dict(ln, total_repayable=editing[1])
        # A loan an admin or maalik closed by hand is settled (owner's rule).
        if (ln.get("is_gyal") or ln.get("netoff_closed") or ln.get("closed_by_admin")
                or ln.get("total_repayable") is None):
            continue
        day = _day(ln.get("loan_date"))
        owed = float(ln.get("total_repayable") or 0) - paid_so_far(ln)
        if day and day <= cutoff and owed >= OWED_TOLERANCE:
            if lid in own_ids:
                whose = f"This client's loan {ln.get('loan_number') or ''} from {day}"
            else:
                person = {"borrower": "The borrower", "co_borrower": "The co-borrower",
                          "guarantor": "The guarantor"}[role]
                whose = (f"{person} is on another client's loan: {ln.get('loan_number') or ''} of "
                         f"{ln.get('client_name') or 'another client'} from {day}. That loan")
            raise HTTPException(
                status_code=403,
                detail=(f"{whose} is over three years old and still owes ₹{owed:,.2f}. It is due to be "
                        f"written off, so no new money can be given with them on the loan."
                        + (" If this is a different person who shares the phone, enter their own Aadhaar."
                           if lid not in own_ids else "") + " "
                        "/ तीन साल पुराने बकाया वाले व्यक्ति के साथ नया कर्ज़ नहीं दिया जा सकता।"),
            )


# ─── Who is Gyal-linked ───────────────────────────────────────────────────────
#
# Asked of the loans themselves, through indexes on the people recorded on each
# loan. An earlier version kept a separate list of Gyal identities; it could
# drift from the loans (a crash between marking a loan Gyal and listing it, a
# rebuild racing an undo) and nothing repaired it. There is nothing to drift now:
# a loan is Gyal-linked the moment it is marked Gyal.

_people_ready = False
_people_lock = asyncio.Lock()


async def ensure_people_recorded() -> None:
    """Indexes for the Gyal check, and people recorded on loans made before this.

    Runs once per process; the flag in app_meta lets later processes skip the
    backfill. Safe to run concurrently or again after a failure — it only fills
    in loans that have no people yet.
    """
    global _people_ready
    if _people_ready:
        return
    async with _people_lock:
        if _people_ready:
            return
        await _record_people()


async def _record_people() -> None:
    global _people_ready
    for field in ("is_gyal", "people.borrower.aadhaar", "people.borrower.phones",
                  "people.co_borrower.aadhaar", "people.co_borrower.phones", "kyc_id_canon",
                  "people.borrower.other_aadhaars", "people.co_borrower.other_aadhaars"):
        await db.loans.create_index(field)
    await db.journal_entries.create_index("reference_id")
    if not await db.app_meta.find_one({"_id": "loan_people_v1"}):
        async for loan in db.loans.find({"people": {"$exists": False}},
                                        {"kyc_id": 1, "client_phone": 1}):
            kid = _canon_id(loan.get("kyc_id"))
            kyc = None
            if kid:
                kyc = await db.kycs.find_one({"_id": ObjectId(kid)},
                                             {"primary_borrower": 1, "co_borrower": 1, "guarantor": 1})
            people = loan_people(kyc, {"borrower": {"phone": loan.get("client_phone")}})
            update = {"people": people}
            if kid:
                update["kyc_id_canon"] = kid
            await db.loans.update_one({"_id": loan["_id"], "people": {"$exists": False}}, {"$set": update})
        await db.app_meta.update_one(
            {"_id": "loan_people_v1"},
            {"$set": {"done_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    _people_ready = True


def _snapshot_keys(snapshot: dict) -> tuple:
    snap = snapshot or {}
    return ({snap["aadhaar"]} if snap.get("aadhaar") else set(), set(snap.get("phones") or []))


async def find_gyal_link(aadhaars: set, phones: set, kyc_ids: set = frozenset(), exclude_loan=None):
    """The Gyal loan a set of identities belongs to, if any."""
    await ensure_people_recorded()
    ors = []
    if aadhaars:
        ors += [{f"people.{role}.{field}": {"$in": sorted(aadhaars)}}
                for role in ("borrower", "co_borrower") for field in ("aadhaar", "other_aadhaars")]
    if phones:
        ors += [{"people.borrower.phones": {"$in": sorted(phones)}},
                {"people.co_borrower.phones": {"$in": sorted(phones)}}]
    variants = [v for kid in kyc_ids if kid for v in _id_variants(kid)]
    if variants:
        ors += [{"kyc_id": {"$in": variants}}, {"kyc_id_canon": {"$in": sorted(kyc_ids)}}]
    if not ors:
        return None
    query = {"is_gyal": {"$in": [True, 1]}, "$or": ors}
    if exclude_loan is not None:
        query["_id"] = {"$ne": exclude_loan}
    return await db.loans.find_one(query, {"loan_number": 1, "client_name": 1, "gyal_since": 1})


def _gyal_label(loan: dict) -> str:
    since = str(loan.get("gyal_since") or "")[:10]
    return (f"{loan.get('client_name') or 'a client'} (Gyal loan {loan.get('loan_number') or ''}"
            f"{' from ' + since if since else ''})")


_ROLE_LABEL = {"borrower": "borrower", "co_borrower": "co-borrower", "guarantor": "guarantor"}


async def assert_people_not_gyal(people: dict, own_kyc_id: str = None) -> None:
    """Refuse if anyone on a loan is linked to a written-off (Gyal) loan.

    A person is Gyal-linked when their Aadhaar or a phone number matches the
    borrower or co-borrower recorded on a Gyal loan. No two people share a phone
    except a borrower and co-borrower pair, and that pair is jointly liable, so a
    phone match is the same debt. The borrower, co-borrower and guarantor of the
    NEW loan are all checked: a Gyal client may not borrow, co-sign or guarantee.
    """
    own = _canon_id(own_kyc_id) if own_kyc_id else ""
    for role in ("borrower", "co_borrower", "guarantor"):
        aadhaars, phones = _snapshot_keys((people or {}).get(role))
        kyc_ids = {own} if (own and role == "borrower") else set()
        hit = await find_gyal_link(aadhaars, phones, kyc_ids)
        if hit:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"The {_ROLE_LABEL[role]} is linked to {_gyal_label(hit)}. A Gyal client cannot be "
                    f"given a new loan or a net-off, or stand as co-borrower or guarantor. "
                    f"/ गयाल ग्राहक को नया कर्ज़ या नेट-ऑफ नहीं दिया जा सकता।"
                ),
            )


async def prepare_loan_people(kyc_id, overrides: dict = None, require_kyc: bool = True,
                              require_aadhaar: bool = True, require_identity: bool = False) -> tuple:
    """Resolve the client, apply the lending rules, and return (kyc, people).

    - `require_kyc`: a brand-new loan must name a KYC that exists.
    - `require_aadhaar`: a loan needs the borrower's Aadhaar.
    - `require_identity`: without Aadhaar, at least a phone — a borrower with
      neither could never be recognised again if the loan went bad.
    - everyone on the loan is checked against the Gyal loans.
    """
    kid = _canon_id(kyc_id)
    kyc = await db.kycs.find_one({"_id": ObjectId(kid)}) if kid else None
    if require_kyc and not kid:
        raise HTTPException(status_code=400, detail="A valid client (KYC) is required")
    if require_kyc and not kyc:
        raise HTTPException(status_code=404, detail="Client KYC not found")
    people = loan_people(kyc, overrides)
    if require_aadhaar and not people["borrower"]["aadhaar"]:
        raise HTTPException(
            status_code=400,
            detail=("The borrower's Aadhaar number is required for a loan. Add it to the client's "
                    "KYC first. / कर्ज़ के लिए उधारकर्ता का आधार नंबर ज़रूरी है।"),
        )
    if require_identity and not people["borrower"]["aadhaar"] and not people["borrower"]["phones"]:
        raise HTTPException(status_code=400, detail=BORROWER_IDENTITY_REQUIRED)
    await assert_people_not_gyal(people, own_kyc_id=kid or None)
    return kyc, people


async def assert_client_not_gyal(kyc_id, extra_people: dict = None, require_kyc: bool = True) -> None:
    """Gyal check alone, for paths that do not record people or need Aadhaar."""
    await prepare_loan_people(kyc_id, overrides=extra_people, require_kyc=require_kyc,
                              require_aadhaar=False)


async def person_is_gyal_linked(person, kyc_id: str = None) -> bool:
    aadhaars, phones = _snapshot_keys(_person_snapshot(person))
    return bool(await find_gyal_link(aadhaars, phones, {_canon_id(kyc_id)} if _canon_id(kyc_id) else set()))


def _identity_diff(old_person, new_person) -> dict:
    old, new = _person_snapshot(old_person), _person_snapshot(new_person)
    return {
        "aadhaar_from": old["aadhaar"], "aadhaar_to": new["aadhaar"],
        "phones_removed": [p for p in old["phones"] if p not in new["phones"]],
        "phones_added": [p for p in new["phones"] if p not in old["phones"]],
    }


def _name_tokens(name) -> list:
    text = "".join(ch.lower() if unicodedata.category(ch)[0] in ("L", "M") else " " for ch in str(name or ""))
    return text.split()


def names_match(a, b) -> bool:
    """Whether two names are the same, ignoring case, spacing and punctuation.

    Nothing looser: allowing a spelling change let "Sita Devi" be replaced by
    "Gita Devi", "Ramesh" by "Rakesh", or anyone by a blank name. A blank name
    matches nothing.
    """
    ta, tb = _name_tokens(a), _name_tokens(b)
    return bool(ta) and "".join(ta) == "".join(tb)


def same_person(recorded: dict, person) -> bool:
    """Whether a recorded snapshot is this person: by Aadhaar, by a shared phone,
    or — when nothing but a name was recorded, as imports do — by name."""
    rec = recorded or {}
    snap = _person_snapshot(person)
    if snap["aadhaar"] and snap["aadhaar"] in ([rec.get("aadhaar")] + list(rec.get("other_aadhaars") or [])):
        return True
    if set(rec.get("phones") or []) & set(snap["phones"]):
        return True
    if not rec.get("aadhaar") and not rec.get("phones") and rec.get("name") and snap["name"]:
        return names_match(rec["name"], snap["name"])
    return False


def apply_identity_correction(recorded: dict, old_person, new_person) -> dict:
    """Add an admin's correction to the person recorded on a Gyal loan — never remove.

    The record is what stops a defaulter borrowing again, so a KYC edit may only
    ADD to it. Every earlier rule that let an edit take something away was
    turned into a way to free a defaulter: replacing the person, renaming them
    first and changing the number next, a near-identical name ("Sita" / "Gita"),
    a blank name, or removing and re-adding them.

    An addition is made only for the same person, under exactly the name the
    loan recorded (or, when it recorded no name, the name on the KYC before the
    edit): a new phone is added, and a new Aadhaar is recorded beside the old
    one. Anything else — another name, a removal — leaves the record as it is.
    A number entered by mistake therefore stays blocked; clearing one is a
    deliberate data fix, not a KYC edit.
    """
    snap = {"name": "", "aadhaar": "", "phones": []}
    snap.update(recorded or {})
    snap["phones"] = list(snap.get("phones") or [])
    snap["other_aadhaars"] = list(snap.get("other_aadhaars") or [])
    if not snap["other_aadhaars"]:
        snap.pop("other_aadhaars")
    new_dict = _as_person_dict(new_person)
    if not new_dict or not same_person(snap, old_person):
        return snap
    recorded_name = snap.get("name") or _as_person_dict(old_person).get("name")
    if not names_match(recorded_name, new_dict.get("name")):
        return snap
    new_snap = _person_snapshot(new_dict)
    if new_snap["aadhaar"]:
        if not snap.get("aadhaar"):
            snap["aadhaar"] = new_snap["aadhaar"]
        elif new_snap["aadhaar"] != snap["aadhaar"] and new_snap["aadhaar"] not in snap.get("other_aadhaars", []):
            snap["other_aadhaars"] = snap.get("other_aadhaars", []) + [new_snap["aadhaar"]]
    for ph in new_snap["phones"]:
        if ph not in snap["phones"]:
            snap["phones"].append(ph)
    if not snap.get("name"):
        snap["name"] = new_snap["name"]
    return snap


def _add_months(dt: date_type, months: int) -> date_type:
    m = dt.month - 1 + months
    year = dt.year + m // 12
    month = m % 12 + 1
    # Clamp to last valid day of the target month (handles Jan 31 → Feb 28, etc.)
    last_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))


def _apply_overdue_to_schedule(schedule: list) -> bool:
    today = date_type.today()
    changed = False
    for item in schedule:
        if item["status"] == "pending":
            y, mo = map(int, item["due_month"].split("-"))
            last_day = calendar.monthrange(y, mo)[1]
            if today > date_type(y, mo, last_day):
                item["status"] = "overdue"
                changed = True
    return changed


# Less than a rupee left is paid. Decimal EMIs on imported loans leave a few
# paise behind when each instalment is collected at the sheet's amount; a loan
# must not stay open, or be written off, over that.
OWED_TOLERANCE = 1.0


def _get_loan_status(schedule: list, total_paid=None, total_repayable=None, netoff_closed: bool = False) -> str:
    """A loan's status from its schedule — and, when given, from what it still owes.

    Every instalment marked paid used to mean "closed", whatever was actually
    paid. Part-payments of ₹100 on each month closed a loan owing thousands: it
    left the Vasuli sheet, the dashboard's Bakaya and the year-end closing, and
    the client could borrow again. A loan with money still owed stays open —
    overdue once its last instalment month has passed. A loan closed by a net-off
    is closed: its balance moved into the re-loan.
    """
    if netoff_closed:
        # Its balance went into the re-loan; reopening it counted that balance twice.
        return "closed"
    if not schedule:
        return "active"
    totals_known = total_paid is not None and total_repayable is not None
    if totals_known and float(total_repayable or 0) - float(total_paid or 0) < OWED_TOLERANCE:
        # Repaid, however it was paid: a lump sum recorded against the first
        # instalment left the loan open, due again every month.
        return "closed"
    if all(e["status"] in ("paid", "netoff") for e in schedule):
        if (totals_known
                and not any(e["status"] == "netoff" for e in schedule)
                and float(total_repayable or 0) - float(total_paid or 0) >= OWED_TOLERANCE):
            today = date_type.today()
            last = max(str(e.get("due_month") or "") for e in schedule)
            return "overdue" if last < f"{today.year}-{today.month:02d}" else "active"
        return "closed"
    if any(e["status"] == "overdue" for e in schedule):
        return "overdue"
    return "active"


def loan_status(loan: dict) -> str:
    """_get_loan_status for a whole loan document."""
    # Closed by hand by an admin or maalik: settled, whatever the figures say.
    if loan.get("closed_by_admin"):
        return "closed"
    # An older record with no total_paid keeps the status its schedule gives.
    return _get_loan_status(loan.get("emi_schedule") or [],
                            loan.get("total_paid") if "total_paid" in loan else None,
                            loan.get("total_repayable"),
                            netoff_closed=bool(loan.get("netoff_closed")))


def _build_emi_schedule(principal: float, loan_date: date_type) -> tuple:
    """Returns (emi_amount, schedule_list).
    Formula: total = principal * 120/103 (interest = principal * 17/103), EMI rounded to nearest ₹10.
    """
    emi_amount = round(principal * 120 / 103 / 12 / 10) * 10
    schedule = []
    for i in range(12):
        due = _add_months(loan_date, i + 1)
        schedule.append({
            "month": i + 1,
            "due_month": due.strftime("%Y-%m"),
            "amount": emi_amount,
            "status": "pending",
            "paid_amount": 0.0,
            "paid_date": None,
            "collected_by_id": None,
            "collected_by_name": None,
        })
    _apply_overdue_to_schedule(schedule)
    return emi_amount, schedule


async def _get_maalik_illaka_ids(user: dict) -> list:
    """Return all illaka IDs accessible to a Maalik: owned (maalik_id) + admin-assigned."""
    owned = await db.illakas.find({"maalik_id": user["id"]}, {"_id": 1}).to_list(1000)
    ids = {str(ill["_id"]) for ill in owned}
    ids.update(user.get("assigned_illaka_ids", []))
    return list(ids)


async def get_admin_maalik_filter_ids(maalik_user_id: str) -> list:
    """For Admin use: given a maalik user ID, return all Illaka IDs that belong to them."""
    try:
        maalik_user = await db.users.find_one({"_id": ObjectId(maalik_user_id)})
        if not maalik_user:
            return []
        owned = await db.illakas.find({"maalik_id": maalik_user_id}, {"_id": 1}).to_list(1000)
        ids = {str(ill["_id"]) for ill in owned}
        ids.update(maalik_user.get("assigned_illaka_ids", []))
        return list(ids)
    except Exception:
        return []


NO_ILLAKA_SENTINEL = "__none__"


async def permitted_illaka_ids(user: dict):
    """Illaka ids this user may access. Returns None when unrestricted (admin)."""
    role = user.get("role")
    if role == "admin":
        return None
    if role == "maalik":
        return await _get_maalik_illaka_ids(user)
    return list(user.get("assigned_illaka_ids", []) or [])


async def apply_illaka_scope(user: dict, query: dict, illaka_id: str = None, maalik_id: str = None) -> dict:
    """Narrow `query` to a requested illaka WITHOUT ever widening it.

    Routes used to do `query["illaka_id"] = illaka_id`, which overwrote the
    role restriction already on the query — so any signed-in user could read
    (and write to) any other illaka just by passing its id. This applies the
    request as a filter only when the user is actually entitled to that illaka;
    otherwise the query is pointed at a sentinel that matches nothing.
    """
    allowed = await permitted_illaka_ids(user)
    if illaka_id:
        if allowed is None or illaka_id in allowed:
            query["illaka_id"] = illaka_id
        else:
            query["illaka_id"] = NO_ILLAKA_SENTINEL
    elif maalik_id and user.get("role") == "admin":
        ids = await get_admin_maalik_filter_ids(maalik_id)
        query["illaka_id"] = {"$in": ids}
    return query


async def _kyc_query_for_user(user: dict) -> dict:
    query = {}
    if user["role"] == "admin":
        pass  # No filter — sees all data
    elif user["role"] == "maalik":
        illaka_ids = await _get_maalik_illaka_ids(user)
        query["illaka_id"] = {"$in": illaka_ids}
    elif user["role"] in ("muneem", "sadar_muneem"):
        assigned = user.get("assigned_illaka_ids", [])
        query["illaka_id"] = {"$in": assigned}
    else:  # sipahi
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            query["field_officer_id"] = user["id"]
        else:
            query["illaka_id"] = {"$in": assigned}
    return query


async def create_journal_entry_internal(
    illaka_id: str,
    date: str,
    narration: str,
    lines: list,
    entry_type: str = "manual",
    reference_id: str = None,
    created_by_id: str = None,
    created_by_name: str = None,
    **extra_fields,
) -> str:
    """Insert a balanced double-entry journal entry. Returns the new entry's id.

    Refuses to write an entry whose debits and credits disagree. Every report in
    the app — trial balance, cash book, Bid, balance sheet — assumes each entry
    balances, and nothing downstream re-checks it. A single unbalanced entry
    silently skews every one of them, and because the Balance Sheet derives
    opening capital as a plug it still reports `is_balanced: true`, so the damage
    would not show up where anyone is looking for it.

    ₹0.01 tolerance, matching the check the manual-entry endpoint already applies
    to user input; this covers the paths that build lines in code.
    """
    now = datetime.now(timezone.utc).isoformat()
    total_amount = round(sum(float(line.get("debit", 0) or 0) for line in lines), 2)
    total_credit = round(sum(float(line.get("credit", 0) or 0) for line in lines), 2)
    if abs(total_amount - total_credit) > 0.01:
        msg = (
            f"Refusing to write unbalanced journal entry "
            f"(Dr {total_amount:.2f} != Cr {total_credit:.2f}, diff {total_amount - total_credit:+.2f}) "
            f"| type={entry_type} | illaka={illaka_id} | date={date} | narration={narration!r}"
        )
        # Logged as well as raised: two internal callers wrap this in a
        # try/except that only warns, so without the log an imbalance there
        # would vanish without trace.
        logging.getLogger(__name__).error(msg)
        raise ValueError(msg)
    doc = {
        "date": date,
        "illaka_id": illaka_id,
        "narration": narration,
        "entry_type": entry_type,
        "reference_id": reference_id,
        "lines": lines,
        "total_amount": total_amount,
        "created_by_id": created_by_id,
        "created_by_name": created_by_name,
        "created_at": now,
        "updated_at": now,
    }
    doc.update(extra_fields)
    result = await db.journal_entries.insert_one(doc)
    return str(result.inserted_id)


async def _loan_query_for_user(user: dict) -> dict:
    if user["role"] == "admin":
        return {}
    elif user["role"] == "maalik":
        ids = await _get_maalik_illaka_ids(user)
        return {"illaka_id": {"$in": ids}}
    elif user["role"] == "muneem":
        assigned = user.get("assigned_illaka_ids", [])
        return {"illaka_id": {"$in": assigned}}
    elif user["role"] == "sadar_muneem":
        assigned = user.get("assigned_illaka_ids", [])
        return {"illaka_id": {"$in": assigned}}
    else:  # sipahi
        assigned = user.get("assigned_illaka_ids", [])
        if not assigned:
            return {"sipahi_id": user["id"]}
        return {"illaka_id": {"$in": assigned}}


def _make_head_line(head: dict, debit: float, credit: float) -> dict:
    return {
        "account_head_id": str(head["_id"]),
        "account_head_name": head.get("name", ""),
        "group_name": head.get("group_name", ""),
        "group_type": head.get("group_type", ""),
        "debit": debit,
        "credit": credit,
    }


async def _get_system_heads() -> dict:
    heads = await db.account_heads.find(
        {"system_key": {"$in": ["cash_in_hand", "loans_portfolio", "interest_income"]}}
    ).to_list(10)
    return {h["system_key"]: h for h in heads}


async def book_loan_disbursement(loan_doc: dict, user_id: str, user_name: str) -> None:
    """Create the journal entry for a loan disbursement.
    MFI rule: Interest = Principal × 17 / 103 (recognised upfront at disbursement).
    Entry: Dr Loans Portfolio (P+I) | Cr Cash (P) | Cr Interest Income (I)
    Safe to call from any route.
    """
    try:
        sys_heads = await _get_system_heads()
        if "loans_portfolio" not in sys_heads or "cash_in_hand" not in sys_heads:
            return
        principal = float(loan_doc.get("principal_amount", 0))
        interest = round(principal * 17 / 103, 2)
        total_outstanding = round(principal + interest, 2)
        lines = [
            _make_head_line(sys_heads["loans_portfolio"], total_outstanding, 0.0),
            _make_head_line(sys_heads["cash_in_hand"], 0.0, principal),
        ]
        if "interest_income" in sys_heads and interest > 0:
            lines.append(_make_head_line(sys_heads["interest_income"], 0.0, interest))
        await create_journal_entry_internal(
            illaka_id=loan_doc.get("illaka_id", ""),
            date=loan_doc.get("loan_date", ""),
            narration=f"Loan disbursed to {loan_doc.get('client_name', '')} | Loan# {loan_doc.get('loan_number', '')}",
            lines=lines,
            entry_type="loan_disbursement",
            reference_id=str(loan_doc.get("_id") or loan_doc.get("id") or ""),
            created_by_id=user_id,
            created_by_name=user_name,
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(f"Failed to book loan disbursement: {exc}")


def _import_baseline(loan_doc: dict) -> float:
    """Repayments that predate the schedule, in rupees.

    A loan imported with an opening balance carries what was already repaid
    inside `total_paid`, with no dated instalment to match it. Anything in the
    stored total beyond what the schedule's own paid rows account for is that
    pre-import money, and it always counts.

    MUST be called before the schedule is modified — the caller mutates the very
    list this reads, so computing it afterwards sees the new state and produces
    a baseline that silently absorbs the change.
    """
    stored = float(loan_doc.get("total_paid") or 0)
    from_schedule = sum(
        float(e.get("paid_amount") or 0)
        for e in (loan_doc.get("emi_schedule") or [])
        if e.get("status") == "paid"
    )
    return max(0.0, stored - from_schedule)


def _total_paid_with_baseline(baseline: float, schedule: list) -> float:
    """Pre-import money plus everything the schedule now records as paid."""
    return baseline + sum(
        float(e.get("paid_amount") or 0)
        for e in schedule if e.get("status") == "paid"
    )
