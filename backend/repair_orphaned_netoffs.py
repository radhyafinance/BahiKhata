#!/usr/bin/env python3
"""Repair loans left netted-off against a re-loan that no longer exists.

Creating a re-loan with net-off closes the old loan: every unpaid instalment is
marked "netoff", status becomes "closed", netoff_closed is set, and reloan_id
points at the new loan. Deleting that new loan used to leave all of it in place,
so the old loan stayed permanently closed against a re-loan that was gone. No
endpoint could reopen it.

`delete_loan` now releases the parent, so this cannot happen again — but loans
already stranded stay stranded. This repairs those.

A loan is considered orphaned when it is netoff_closed and its reloan_id does
not resolve to an existing loan. Loans whose re-loan still exists are left
alone: those are legitimate net-offs.

Reopening restores what the net-off overwrote:
  * instalments marked "netoff" go back to pending, then the normal overdue
    rule re-derives which are actually overdue ("netoff" keeps no memory of
    what an instalment was before, so pending is the honest starting point)
  * the "Net-off: closed via re-loan" note is cleared
  * status is recomputed from the schedule
  * netoff_closed, netoff_date and the dangling reloan_id are removed

Run from the backend directory (it needs .env and helpers.py):

    cd backend
    python repair_orphaned_netoffs.py            # dry run — reports, changes nothing
    python repair_orphaned_netoffs.py --apply    # performs the repair

Safe to run more than once; a second run finds nothing to do.
"""

import asyncio
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(".env")
except ImportError:
    pass

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    from bson import ObjectId
except ImportError:
    sys.exit("motor/pymongo not installed — run this from the backend directory.")

try:
    from helpers import _apply_overdue_to_schedule, _get_loan_status
except ImportError:
    sys.exit("Could not import helpers.py — run this from the backend directory.")

APPLY = "--apply" in sys.argv


async def main():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    dbname = os.environ.get("DB_NAME", "bahikhata_db")
    db = AsyncIOMotorClient(url)[dbname]

    print(f"database : {dbname}")
    print(f"mode     : {'APPLY — will write' if APPLY else 'DRY RUN — no changes'}\n")

    closed = await db.loans.find(
        {"netoff_closed": True},
        {"loan_number": 1, "client_name": 1, "customer_id": 1, "illaka_id": 1,
         "reloan_id": 1, "status": 1, "emi_schedule": 1, "netoff_date": 1,
         "total_repayable": 1, "total_paid": 1},
    ).to_list(100000)

    if not closed:
        print("No net-off-closed loans in this database. Nothing to do.")
        return

    orphans = []
    for ln in closed:
        rid = ln.get("reloan_id")
        target = None
        if rid:
            try:
                target = await db.loans.find_one({"_id": ObjectId(rid)}, {"_id": 1})
            except Exception:
                target = None
        if not target:
            orphans.append(ln)

    print(f"net-off-closed loans     : {len(closed)}")
    print(f"orphaned (re-loan gone)  : {len(orphans)}")
    print(f"healthy (re-loan exists) : {len(closed) - len(orphans)}   <- left untouched\n")

    if not orphans:
        print("Nothing orphaned. Every net-off still points at a live re-loan.")
        return

    ill_names = {
        str(i["_id"]): i.get("name", "?")
        for i in await db.illakas.find({}, {"_id": 1, "name": 1}).to_list(500)
    }
    print("orphaned loans:")
    for ln in orphans:
        sched = ln.get("emi_schedule", [])
        n_netoff = sum(1 for e in sched if e.get("status") == "netoff")
        outstanding = float(ln.get("total_repayable") or 0) - float(ln.get("total_paid") or 0)
        print(f"    {str(ln.get('customer_id') or '—'):<10} "
              f"{str(ln.get('loan_number') or '—'):<14} "
              f"{str(ln.get('client_name'))[:20]:<20} "
              f"{ill_names.get(ln.get('illaka_id'), '?'):<16} "
              f"{n_netoff:>2} netoff instalments  "
              f"balance Rs {outstanding:>9,.0f}")

    if not APPLY:
        print("\nDry run only — nothing was written.")
        print("Re-run with --apply to reopen these loans.")
        return

    print("\nreopening…")
    for ln in orphans:
        sched = ln.get("emi_schedule", [])
        for e in sched:
            if e.get("status") == "netoff":
                e["status"] = "pending"
                if str(e.get("note") or "").startswith("Net-off:"):
                    e["note"] = ""
        _apply_overdue_to_schedule(sched)
        new_status = _get_loan_status(sched)
        await db.loans.update_one(
            {"_id": ln["_id"]},
            {"$set": {"emi_schedule": sched, "status": new_status},
             "$unset": {"netoff_closed": "", "netoff_date": "", "reloan_id": ""}},
        )
        print(f"    {str(ln.get('loan_number') or '—'):<14} -> {new_status}")

    remaining = 0
    for ln in await db.loans.find({"netoff_closed": True}, {"reloan_id": 1}).to_list(100000):
        rid = ln.get("reloan_id")
        try:
            if not rid or not await db.loans.find_one({"_id": ObjectId(rid)}, {"_id": 1}):
                remaining += 1
        except Exception:
            remaining += 1
    print(f"\n  reopened            : {len(orphans)}")
    print(f"  orphans remaining   : {remaining}{'  ✅' if remaining == 0 else '  ⚠️  expected 0'}")
    print("\nDone. These clients are collectable again on the Vasuli sheet.")
    print("Their accounting is unchanged — the settlement entry went with the "
          "deleted re-loan, which is correct, since that money never moved.")


if __name__ == "__main__":
    asyncio.run(main())
