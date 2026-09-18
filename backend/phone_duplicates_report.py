#!/usr/bin/env python3
"""Report phone numbers shared by people who are not a borrower / co-borrower pair.

The rule: no two people share a phone number, except a borrower and their
co-borrower — and that pair may share it on more than one KYC, in either role.

Before that rule is enforced when a KYC is saved, existing data has to satisfy
it, or real clients would suddenly be unable to save their KYC. This lists every
number that breaks it, so each can be corrected by hand first.

    cd backend && python phone_duplicates_report.py

Read-only. It changes nothing.

How people are told apart: by Aadhaar when one is recorded, otherwise by name
plus relative's name. Phones are compared on their 10 digits, so "+91 91111
11111" and "9111111111" are one number. Blank and placeholder numbers
(too short, all one digit, not starting 6-9) are counted separately and never
treated as shared.
"""
import asyncio, os, re, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv(".env")
except ImportError:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

ROLES = (("primary_borrower", "borrower"), ("co_borrower", "co-borrower"), ("guarantor", "guarantor"))


def norm_phone(v):
    d = re.sub(r"[^0-9]", "", str(v or ""))
    if len(d) < 10:
        return ""
    d = d[-10:]
    return "" if d[0] not in "6789" or len(set(d)) == 1 else d


def norm_aadhaar(v):
    d = re.sub(r"[^0-9]", "", str(v or ""))
    return "" if len(d) != 12 or len(set(d)) == 1 else d


def person_key(p):
    a = norm_aadhaar(p.get("aadhaar_number"))
    if a:
        return f"aadhaar:{a}"
    name = re.sub(r"\s+", " ", str(p.get("name") or "")).strip().lower()
    rel = re.sub(r"\s+", " ", str(p.get("relative_name") or "")).strip().lower()
    return f"name:{name}|{rel}" if name else ""


async def main():
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "bahikhata_db")
    ]
    illakas = {str(i["_id"]): i.get("name", "?") async for i in db.illakas.find({}, {"name": 1})}

    by_phone = defaultdict(list)       # phone -> [occurrence]
    pairs = set()                      # frozenset({borrower_key, co_borrower_key}) seen on one KYC
    blank = placeholder = 0

    async for k in db.kycs.find({}, {"customer_id": 1, "illaka_id": 1, "primary_borrower": 1,
                                     "co_borrower": 1, "guarantor": 1}):
        keys = {}
        for field, role in ROLES:
            p = k.get(field) or {}
            if not p:
                continue
            raw = str(p.get("phone") or "").strip()
            ph = norm_phone(raw)
            key = person_key(p)
            keys[field] = key
            if not raw:
                blank += 1
                continue
            if not ph:
                placeholder += 1
                continue
            by_phone[ph].append({
                "role": role, "person": key, "name": p.get("name") or "(no name)",
                "customer_id": k.get("customer_id") or "—", "kyc_id": str(k["_id"]),
                "illaka": illakas.get(k.get("illaka_id"), "?"), "typed": raw,
            })
        if keys.get("primary_borrower") and keys.get("co_borrower"):
            pairs.add(frozenset({keys["primary_borrower"], keys["co_borrower"]}))

    problems = []
    for ph, occ in by_phone.items():
        people = {o["person"] or f"unnamed:{o['kyc_id']}:{o['role']}" for o in occ}
        if len(people) <= 1:
            continue
        if len(people) == 2 and frozenset(people) in pairs:
            continue
        problems.append((ph, occ, people))

    print("=" * 78)
    print("PHONE NUMBERS SHARED BY PEOPLE WHO ARE NOT A BORROWER/CO-BORROWER PAIR")
    print("=" * 78)
    if not problems:
        print("\n  None. Every shared number belongs to one person or to a borrower/co-borrower pair.")
    for ph, occ, people in sorted(problems, key=lambda x: -len(x[2])):
        print(f"\n  {ph}  — {len(people)} different people")
        for o in sorted(occ, key=lambda o: (o["illaka"], o["customer_id"])):
            typed = f"  (typed {o['typed']!r})" if o["typed"] != ph else ""
            print(f"      {o['illaka']:<14} {o['customer_id']:<10} {o['role']:<12} {o['name']}{typed}")

    print("\n" + "=" * 78)
    print(f"  {len(problems)} number(s) to resolve before the one-phone-per-person rule can be enforced")
    print(f"  {blank} blank phone field(s), {placeholder} placeholder/invalid number(s) — not counted as shared")
    print("  Nothing was changed.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
