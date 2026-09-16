#!/usr/bin/env python3
"""Show what is attached to each duplicate row, so the right one can be kept.

check_duplicates.py says WHICH values are duplicated. This says WHAT hangs off
each copy — payments, journal entries, loans, KYCs — which is the only basis on
which it is safe to choose. A loan with collections against it is real money; a
loan with none is almost always a test artifact.

    cd backend && python inspect_duplicates.py

Read-only. It changes nothing and deletes nothing.
"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv(".env")
except ImportError:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

db = None


def _s(v, n=28):
    t = "—" if v in (None, "") else str(v)
    return t if len(t) <= n else t[: n - 1] + "…"


async def _dup_groups(coll, keys, filt):
    group_id = {k.replace(".", "_"): f"${k}" for k in keys}
    pipeline = ([{"$match": filt}] if filt else []) + [
        {"$group": {"_id": group_id, "n": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"n": {"$gt": 1}}},
    ]
    return await db[coll].aggregate(pipeline).to_list(500)


async def loans_report():
    print("\n" + "=" * 78)
    print("LOANS — duplicate loan_number")
    print("=" * 78)
    groups = await _dup_groups("loans", ["loan_number"], {"loan_number": {"$type": "string"}})
    if not groups:
        print("  none")
        return
    for g in groups:
        print(f"\n  loan_number: {g['_id']['loan_number']!r}   ({g['n']} copies)")
        for oid in g["ids"]:
            lid = str(oid)
            loan = await db.loans.find_one({"_id": oid})
            pays = await db.payments.find({"loan_id": lid}).to_list(1000)
            real = [p for p in pays if (p.get("amount") or 0) > 0]
            paid_sum = sum(p.get("amount") or 0 for p in real)
            jes = await db.journal_entries.count_documents({"reference_id": lid})
            kids = await db.loans.count_documents({"parent_loan_id": lid})
            sched = loan.get("emi_schedule") or []
            done = sum(1 for r in sched if r.get("status") == "paid")
            print(f"    _id {lid}")
            print(f"       client      {_s(loan.get('client_name'))}   kyc {_s(loan.get('kyc_id'), 26)}")
            print(f"       illaka      {_s(loan.get('illaka_id'), 26)}   date {_s(loan.get('loan_date'), 12)}")
            print(f"       principal   {loan.get('principal_amount')}   status {_s(loan.get('status'), 12)}"
                  f"   import {bool(loan.get('is_import'))}   gyal {bool(loan.get('is_gyal'))}")
            print(f"       total_paid  {loan.get('total_paid')}   schedule {len(sched)} rows, {done} paid")
            print(f"       netoff      closed={bool(loan.get('netoff_closed'))} date={_s(loan.get('netoff_date'), 12)}"
                  f" reloan_id={_s(loan.get('reloan_id'), 26)}")
            print(f"       reloan      is_reloan={bool(loan.get('is_reloan'))} parent={_s(loan.get('parent_loan_id'), 26)}")
            print(f"       ATTACHED    {len(pays)} payment row(s), {len(real)} with money "
                  f"totalling {paid_sum}; {jes} journal entr(y/ies); {kids} child loan(s)")
            print(f"       created_at  {_s(loan.get('created_at'), 34)}")
            if real:
                for p in real[:6]:
                    print(f"                   {_s(p.get('emi_month'), 9)} {p.get('amount')} on "
                          f"{_s(p.get('payment_date'), 12)} by {_s(p.get('collected_by_name'), 18)}")
                if len(real) > 6:
                    print(f"                   … and {len(real) - 6} more")


async def kycs_report():
    print("\n" + "=" * 78)
    print("KYCs — duplicate Aadhaar")
    print("=" * 78)
    groups = await _dup_groups("kycs", ["primary_borrower.aadhaar_number"],
                               {"primary_borrower.aadhaar_number": {"$gt": ""}})
    if not groups:
        print("  none")
        return
    for g in groups:
        print(f"\n  aadhaar: {list(g['_id'].values())[0]!r}   ({g['n']} copies)")
        for oid in g["ids"]:
            kid = str(oid)
            k = await db.kycs.find_one({"_id": oid})
            pb = k.get("primary_borrower") or {}
            loans = await db.loans.find({"kyc_id": kid}).to_list(200)
            live = [l for l in loans if l.get("status") != "closed"]
            paid = sum(l.get("total_paid") or 0 for l in loans)
            print(f"    _id {kid}")
            print(f"       customer_id {_s(k.get('customer_id'))}   status {_s(k.get('status'), 14)}")
            print(f"       name        {_s(pb.get('name'))}   phone {_s(pb.get('phone'), 14)}")
            print(f"       illaka      {_s(k.get('illaka_id'), 26)}   misal {_s(k.get('misal_id'), 26)}")
            print(f"       ATTACHED    {len(loans)} loan(s), {len(live)} not closed, total_paid {paid}")
            for l in loans[:6]:
                print(f"                   {_s(l.get('loan_number'), 14)} {l.get('principal_amount')} "
                      f"{_s(l.get('status'), 10)} {_s(l.get('loan_date'), 12)}")
            print(f"       created_at  {_s(k.get('created_at'), 34)}")


async def illakas_report():
    print("\n" + "=" * 78)
    print("ILLAKAS — duplicate name")
    print("=" * 78)
    groups = await _dup_groups("illakas", ["name"], {})
    if not groups:
        print("  none")
        return
    for g in groups:
        print(f"\n  name: {g['_id']['name']!r}   ({g['n']} copies)")
        for oid in g["ids"]:
            iid = str(oid)
            il = await db.illakas.find_one({"_id": oid})
            counts = {
                "loans": await db.loans.count_documents({"illaka_id": iid}),
                "kycs": await db.kycs.count_documents({"illaka_id": iid}),
                "misals": await db.misals.count_documents({"illaka_id": iid}),
                "journal_entries": await db.journal_entries.count_documents({"illaka_id": iid}),
                "closings": await db.illaka_closings.count_documents({"illaka_id": iid}),
                "expense_sheets": await db.expense_submissions.count_documents({"illaka_id": iid}),
            }
            users = await db.users.count_documents({"assigned_illaka_ids": iid})
            print(f"    _id {iid}")
            print(f"       maalik_id   {_s(il.get('maalik_id'), 26)}   created {_s(il.get('created_at'), 34)}")
            print(f"       ATTACHED    " + ", ".join(f"{k}={v}" for k, v in counts.items())
                  + f", users_assigned={users}")
            if sum(counts.values()) == 0 and users == 0:
                print("       >>> EMPTY — nothing references this illaka")


async def main():
    global db
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "bahikhata_db")
    ]
    await loans_report()
    await kycs_report()
    await illakas_report()
    print("\n" + "=" * 78)
    print("Nothing was changed. Send this whole output back before deleting anything.")
    print("=" * 78)


if __name__ == "__main__":
    asyncio.run(main())
