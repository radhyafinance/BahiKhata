#!/usr/bin/env python3
"""Delete the testing illakas and everything filed under them.

Scoped deliberately narrowly. It touches ONLY the nine illakas listed in
TARGETS, each of which is checked by name before anything is removed — if a
name does not match, the script aborts rather than guess, which is what stops
it doing damage if it is ever run against a different database.

Shyamnagar, Biharipur and Rampur Testing are named in PROTECTED and must be
present and intact; the script refuses to run otherwise, and asserts at the end
of planning that not one of their records is in the set.

    cd backend && python delete_test_illakas.py            # dry run — the plan
    cd backend && python delete_test_illakas.py --apply    # carries it out

The cascade covers KYCs, loans, payments, journal entries, CRIF checks, misals,
year-end closings, expense sheets and templates. Users are never removed — the
dead illaka is pulled out of their assigned list instead.

This is not reversible. Take Emergent's database backup first.
"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv(".env")
except ImportError:
    pass
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

APPLY = "--apply" in sys.argv

TARGETS = {
    "69c78cf96781e1fb0d95f0dd": "Delhi",                 # every client in it is TEST_*
    "69c6902e2eb75a3158e9a20c": "TEST_Illaka_Central",
    "69c69052cacaed4c87d40eed": "TEST_Illaka_Central",
    "69c69086b10b69f01861c3aa": "TEST_Illaka_Central",
    "69c6909719255638e787e8ee": "TEST_Illaka_Central",
    "69c6966c79bbf6e6f187777a": "Test Illaka ",          # the trailing space is real
    "69c79ef013468e318755957e": "Test Illaka 2",
    "69c690e119255638e787e8f1": "UI_Test_Illaka",
    "6a352fa7e3693e6773b5001f": "Unique Test Illaka",
}

PROTECTED = {
    "6a5885a3c735dd49ad91ef41": "Shyamnagar",
    "6a3510cd7d131f22c25263cc": "Biharipur",
    "69cbbd24af2f8a0e30d6f3af": "Rampur Testing",
}

# Records stamped with an illaka_id that was never an illaka at all
JUNK_ILLAKA_IDS = {"i1", "test"}

db = None


async def _check_guards():
    ok = True
    for iid, name in PROTECTED.items():
        try:
            doc = await db.illakas.find_one({"_id": ObjectId(iid)})
        except Exception:
            doc = None
        if not doc:
            print(f"  ABORT  protected illaka {name} ({iid}) is not in this database")
            ok = False
        elif (doc.get("name") or "") != name:
            print(f"  ABORT  {iid} should be {name!r} but is {doc.get('name')!r}")
            ok = False
        else:
            print(f"  guard  {name} present and untouched")
    live = {}
    for iid, name in TARGETS.items():
        try:
            doc = await db.illakas.find_one({"_id": ObjectId(iid)})
        except Exception:
            doc = None
        if not doc:
            print(f"  skip   {name} ({iid}) — already gone")
            continue
        if (doc.get("name") or "") != name:
            print(f"  ABORT  {iid} should be {name!r} but is {doc.get('name')!r} — "
                  f"refusing to act on an illaka I cannot identify")
            ok = False
            continue
        live[iid] = name
    return ok, live


async def main():
    global db
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "bahikhata_db")
    ]

    print("=" * 78)
    print("SAFETY CHECKS")
    print("=" * 78)
    ok, live = await _check_guards()
    if not ok:
        print("\nAborted. Nothing was changed.")
        sys.exit(1)

    scope = list(live) + sorted(JUNK_ILLAKA_IDS)
    kyc_ids, loan_ids, misal_ids = [], [], []
    print("\n" + "=" * 78)
    print("WHAT WOULD GO")
    print("=" * 78)
    for iid in scope:
        name = live.get(iid) or f"(stray illaka_id {iid!r})"
        kycs = await db.kycs.find({"illaka_id": iid}, {"_id": 1}).to_list(10000)
        kids = [str(k["_id"]) for k in kycs]
        loans = await db.loans.find(
            {"$or": [{"illaka_id": iid}, {"kyc_id": {"$in": kids}}]},
            {"_id": 1, "total_paid": 1, "client_name": 1},
        ).to_list(10000)
        lids = [str(l["_id"]) for l in loans]
        misals = await db.misals.find({"illaka_id": iid}, {"_id": 1}).to_list(1000)
        money = sum(l.get("total_paid") or 0 for l in loans)
        pays = await db.payments.count_documents({"loan_id": {"$in": lids}}) if lids else 0
        jes = await db.journal_entries.count_documents(
            {"$or": [{"illaka_id": iid}, {"reference_id": {"$in": lids}}]})
        crif = await db.crif_checks.count_documents({"kyc_id": {"$in": kids}}) if kids else 0
        closings = await db.illaka_closings.count_documents({"illaka_id": iid})
        sheets = await db.expense_submissions.count_documents({"illaka_id": iid})
        templates = await db.expense_templates.count_documents({"illaka_id": iid})
        users = await db.users.count_documents({"assigned_illaka_ids": iid})
        print(f"\n  {name}  [{iid}]")
        print(f"    {len(loans)} loan(s) carrying {money} collected, {len(kycs)} KYC(s), "
              f"{len(misals)} misal(s)")
        print(f"    {pays} payment(s), {jes} journal entr(y/ies), {crif} CRIF check(s), "
              f"{closings} closing(s), {sheets} expense sheet(s), {templates} template(s)")
        if users:
            print(f"    {users} user(s) have this illaka assigned — it is taken out of "
                  f"their list; no user is removed")
        kyc_ids += kids
        loan_ids += lids
        misal_ids += [str(m["_id"]) for m in misals]

    # Nothing protected may end up in the set, whatever the queries did
    bad = await db.loans.count_documents(
        {"_id": {"$in": [ObjectId(i) for i in loan_ids]}, "illaka_id": {"$in": list(PROTECTED)}}
    ) if loan_ids else 0
    bad += await db.kycs.count_documents(
        {"_id": {"$in": [ObjectId(i) for i in kyc_ids]}, "illaka_id": {"$in": list(PROTECTED)}}
    ) if kyc_ids else 0
    if bad:
        print(f"\n  ABORT — {bad} record(s) in a protected illaka landed in the set.")
        sys.exit(1)
    print("\n  guard  no record from Shyamnagar, Biharipur or Rampur Testing is in the set")

    # A surviving loan pointing at one about to vanish would be left dangling
    dangling = await db.loans.find(
        {"$or": [{"parent_loan_id": {"$in": loan_ids}}, {"reloan_id": {"$in": loan_ids}}],
         "_id": {"$nin": [ObjectId(i) for i in loan_ids]}},
        {"_id": 1, "loan_number": 1, "illaka_id": 1},
    ).to_list(200) if loan_ids else []
    if dangling:
        print(f"\n  WARNING — {len(dangling)} surviving loan(s) point at a loan in the set:")
        for d in dangling:
            print(f"    {d['_id']}  {d.get('loan_number')}  illaka {d.get('illaka_id')}")

    print("\n" + "=" * 78)
    print(f"TOTAL: {len(loan_ids)} loans, {len(kyc_ids)} KYCs, {len(misal_ids)} misals, "
          f"{len(live)} illakas")
    print("=" * 78)

    if not APPLY:
        print("\nDRY RUN — nothing was changed. Re-run with --apply to carry this out.")
        return

    print("\nAPPLYING")
    oids = [ObjectId(i) for i in loan_ids]
    r = await db.payments.delete_many({"loan_id": {"$in": loan_ids}}) if loan_ids else None
    print(f"  payments          {r.deleted_count if r else 0}")
    r = await db.journal_entries.delete_many(
        {"$or": [{"illaka_id": {"$in": scope}}, {"reference_id": {"$in": loan_ids}}]})
    print(f"  journal_entries   {r.deleted_count}")
    r = await db.crif_checks.delete_many({"kyc_id": {"$in": kyc_ids}}) if kyc_ids else None
    print(f"  crif_checks       {r.deleted_count if r else 0}")
    r = await db.loans.delete_many({"_id": {"$in": oids}}) if oids else None
    print(f"  loans             {r.deleted_count if r else 0}")
    r = await db.kycs.delete_many({"_id": {"$in": [ObjectId(i) for i in kyc_ids]}}) if kyc_ids else None
    print(f"  kycs              {r.deleted_count if r else 0}")
    r = await db.misals.delete_many({"illaka_id": {"$in": scope}})
    print(f"  misals            {r.deleted_count}")
    r = await db.illaka_closings.delete_many({"illaka_id": {"$in": scope}})
    print(f"  illaka_closings   {r.deleted_count}")
    r = await db.expense_submissions.delete_many({"illaka_id": {"$in": scope}})
    print(f"  expense_sheets    {r.deleted_count}")
    r = await db.expense_templates.delete_many({"illaka_id": {"$in": scope}})
    print(f"  expense_templates {r.deleted_count}")
    r = await db.users.update_many({"assigned_illaka_ids": {"$in": scope}},
                                   {"$pull": {"assigned_illaka_ids": {"$in": scope}}})
    print(f"  users unassigned  {r.modified_count}")
    r = await db.illakas.delete_many({"_id": {"$in": [ObjectId(i) for i in live]}})
    print(f"  illakas           {r.deleted_count}")

    print("\nDone. Restart the backend so the unique indexes build, then check the logs "
          "for any remaining \"Could not create unique index\" line.")


if __name__ == "__main__":
    asyncio.run(main())
