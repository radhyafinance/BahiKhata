#!/usr/bin/env python3
"""Report duplicates that would stop the new unique indexes from building.

The audit fixes add seven unique indexes. Index creation is deliberately
lenient — a failure is logged and the server still starts — but the constraint
then silently does not apply, which is the situation it was meant to end.

Run this BEFORE deploying the fixes to see whether anything needs cleaning:

    cd backend && python check_duplicates.py

Read-only. It changes nothing.
"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv(".env")
except ImportError:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

CHECKS = [
    ("loans",               ["loan_number"],                        {"loan_number": {"$type": "string"}},   "uq_loan_number"),
    ("kycs",                ["customer_id"],                        {"customer_id": {"$type": "string"}},   "uq_customer_id"),
    ("kycs",                ["primary_borrower.aadhaar_number"],    {"primary_borrower.aadhaar_number": {"$gt": ""}}, "uq_primary_aadhaar"),
    ("illakas",             ["name"],                               {},                                     "uq_illaka_name"),
    ("illaka_closings",     ["illaka_id", "closing_date"],          {},                                     "uq_illaka_closing"),
    ("expense_submissions", ["illaka_id", "month"],                 {},                                     "uq_expense_submission"),
    ("journal_entries",     ["illaka_id", "date"],                  {"entry_type": "opening_balance"},      "uq_opening_balance_entry"),
]


async def main():
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "bahikhata_db")
    ]
    total = 0
    for coll, keys, filt, name in CHECKS:
        group_id = {k.replace(".", "_"): f"${k}" for k in keys}
        pipeline = ([{"$match": filt}] if filt else []) + [
            {"$group": {"_id": group_id, "n": {"$sum": 1},
                        "ids": {"$push": "$_id"}}},
            {"$match": {"n": {"$gt": 1}}},
            {"$sort": {"n": -1}},
        ]
        dups = await db[coll].aggregate(pipeline).to_list(500)
        label = f"{coll}({', '.join(keys)})"
        if not dups:
            print(f"  OK    {label:<52} no duplicates")
            continue
        extra = sum(d["n"] - 1 for d in dups)
        total += extra
        print(f"  DUP   {label:<52} {len(dups)} value(s), {extra} extra row(s)")
        for d in dups[:5]:
            vals = " / ".join(str(v) for v in d["_id"].values())
            print(f"          {vals}  x{d['n']}")
        if len(dups) > 5:
            print(f"          … and {len(dups) - 5} more")

    print()
    if total:
        print(f"  {total} row(s) block a unique index.")
        print("  The server will still start — index creation is lenient and logs the")
        print("  failure — but that constraint will not be enforced until these are")
        print("  cleaned up. Decide per case which row to keep; do NOT bulk-delete,")
        print("  since some carry real money.")
    else:
        print("  Nothing blocks the new unique indexes. Safe to deploy as is.")


if __name__ == "__main__":
    asyncio.run(main())
