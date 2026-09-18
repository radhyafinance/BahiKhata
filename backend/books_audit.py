#!/usr/bin/env python3
"""Find — and optionally repair — records left half-finished by an interrupted request.

The app changes a loan in several steps (loan row, payment, journal entry, the
old loan of a re-loan). Locks stop two requests interleaving, but if the server
process itself stops mid-request — a restart during a deploy while someone is
saving — the steps already written stay written. The trial balance still
balances in every one of these cases, so nothing in the app shows them.

Run after any restart that might have caught a request in flight:

    cd backend && python books_audit.py            # report only, changes nothing
    cd backend && python books_audit.py --apply    # also repairs what is safe to repair

What --apply repairs (each has exactly one correct state, so it is safe):
  1. Old loans still closed by a net-off whose re-loan does not exist → reopened.
  3. Lock records not refreshed for 3 minutes → removed. A working request
     refreshes its lock every 10 seconds, so these belong to a stopped server.
  9. Loans marked closed that still owe money → reopened (active or overdue).
 12. Year-end closing records whose Gyal count does not match their loans → count corrected.

What it only reports (each needs a person to decide):
  2. Paid instalments with no Cash Book entry. Not repaired automatically: loans
     entered straight into the database (seed or migration scripts) never had
     entries, and booking them would change the books in bulk.
  4. Re-loans with no disbursement entry, or a net-off re-loan with no settlement.
  5. Cash Book collection entries whose instalment is not marked paid.
  6. Payment records (above ₹0) whose instalment is not marked paid.
  7. Journal entries or payments that belong to a loan that no longer exists.
  8. Loans whose total_paid does not match what their paid instalments add up to.
 10. Loans written off at a closing that were left incomplete — no write-off entry,
     a write-off half-done, or later collections still in Loans Portfolio → run
     that closing again for the same date (or, if you were undoing it, the undo).
 11. Loans written off at a closing that has no closing record → run the closing
     for that date again to restore the record.
 13. Loans created since the audit fixes with no disbursement entry.
 14. Loans that should have been written off at an Illaka's latest closing but
     were not (a restart stopped the closing part-way) → run that closing again.
 15. Clients who cannot be given new money because a loan of theirs over three
     years old still owes (these are written off at the next closing).
"""
import asyncio, os, sys
from datetime import datetime, timezone, timedelta, date as date_type
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv(".env")
except ImportError:
    pass
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

APPLY = "--apply" in sys.argv

# Net-off settlement entries have been booked since the audit fixes went live on
# Emergent (commit b15df16, 16 Sep 2026). Older net-off re-loans never had one, so
# they are not reported as missing it.
SETTLEMENT_SINCE = "2026-09-16"


def day(value):
    """A stored date as YYYY-MM-DD, read the way the app reads it ("" if unreadable)."""
    import re
    text = str(value or "").strip()
    for cand in (text[:10], text):
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", cand):
                return date_type.fromisoformat(cand).isoformat()
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


def paid_total(ln):
    """total_paid, or the paid instalments when an older record has none."""
    if ln.get("total_paid") is None:
        return sum(float(r.get("paid_amount") or 0) for r in ln.get("emi_schedule", []) if r.get("status") == "paid")
    return float(ln.get("total_paid") or 0)


def cutoff_36(cdate):
    import calendar
    y, m, d = map(int, cdate.split("-"))
    mm = m - 1 - 36
    cy, cm = y + mm // 12, mm % 12 + 1
    return f"{cy}-{cm:02d}-{min(d, calendar.monthrange(cy, cm)[1]):02d}"


def canon(value):
    try:
        return str(ObjectId(str(value).strip()))
    except Exception:
        return ""


async def main():
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))[
        os.environ.get("DB_NAME", "bahikhata_db")
    ]
    print(f"database : {db.name}")
    print(f"mode     : {'APPLY — repairs will be written' if APPLY else 'REPORT ONLY — nothing is changed'}\n")

    loans = {str(l["_id"]): l async for l in db.loans.find({})}
    heads = {h.get("system_key"): h async for h in db.account_heads.find({"system_key": {"$ne": None}})}
    issues = 0

    def line(head, amount):
        return {"account_head_id": str(head["_id"]), "account_head_name": head.get("name", ""),
                "group_name": head.get("group_name", ""), "group_type": head.get("group_type", ""),
                "debit": amount[0], "credit": amount[1]}

    # 1. Stranded net-offs
    print("1. Loans closed by a net-off with no live net-off re-loan")
    today = date_type.today()
    this_month = f"{today.year}-{today.month:02d}"
    # A loan's net-off is live when some existing loan names it as parent and
    # carries a net-off amount. The reloan_id pointer is not trusted: older builds
    # let a plain re-loan overwrite it, so a pointer can dangle while the real
    # net-off re-loan still exists — reopening that loan would count its balance
    # twice — or point at a live plain re-loan while the net-off one is gone.
    netoff_children = {}
    for child in loans.values():
        pid = canon(child.get("parent_loan_id"))
        if pid and float(child.get("netoff_amount") or 0) > 0:
            netoff_children.setdefault(pid, []).append(child)
    found = 0
    for lid, ln in loans.items():
        if not ln.get("netoff_closed"):
            continue
        if netoff_children.get(lid):
            continue
        found += 1
        print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  — no existing net-off re-loan "
              f"(pointer: {ln.get('reloan_id') or 'none'})")
        if APPLY:
            # Take the app's own lock on the loan, so a repair cannot interleave
            # with someone working on it. If it is busy, leave it for the next run.
            token = f"books_audit-{datetime.now(timezone.utc).timestamp()}"
            try:
                await db.locks.insert_one({"_id": f"loan:{lid}", "token": token, "at": datetime.now(timezone.utc)})
            except Exception:
                print("      busy — skipped, run again later")
                continue
            try:
                fresh = await db.loans.find_one({"_id": ln["_id"]})
                if not fresh or not fresh.get("netoff_closed") or await db.loans.find_one(
                        {"parent_loan_id": {"$regex": f"^\\s*{lid}\\s*$", "$options": "i"},
                         "netoff_amount": {"$gt": 0}}):
                    print("      changed meanwhile — skipped")
                    continue
                ln = fresh
                sets, unsets = {"updated_at": datetime.now(timezone.utc).isoformat()}, {
                    "netoff_closed": "", "netoff_date": "", "reloan_id": ""}
                schedule = ln.get("emi_schedule", [])
                for i, row in enumerate(schedule):
                    if row.get("status") == "netoff":
                        status = "overdue" if (row.get("due_month") or "") < this_month else "pending"
                        sets[f"emi_schedule.{i}.status"] = status
                        sets[f"emi_schedule.{i}.note"] = row.get("pre_netoff_note") or ""
                        unsets[f"emi_schedule.{i}.pre_netoff_note"] = ""
                        row["status"] = status
                rows = schedule
                if rows and all(r.get("status") in ("paid", "netoff") for r in rows):
                    sets["status"] = "closed"
                elif any(r.get("status") == "overdue" for r in rows):
                    sets["status"] = "overdue"
                else:
                    sets["status"] = "active"
                await db.loans.update_one({"_id": ln["_id"], "netoff_closed": True}, {"$set": sets, "$unset": unsets})
                print("      reopened")
            finally:
                await db.locks.delete_one({"_id": f"loan:{lid}", "token": token})
    print(f"   {found} found\n"); issues += found

    # 2. Paid instalments with no Cash Book entry
    print("2. Paid instalments with no Cash Book entry (report only)")
    entries_by_loan = {}
    async for je in db.journal_entries.find({"entry_type": "emi_collection"},
                                            {"reference_id": 1, "emi_month": 1, "date": 1, "total_amount": 1}):
        entries_by_loan.setdefault(canon(je.get("reference_id")), []).append(je)
    found = 0
    for lid, ln in loans.items():
        jes = entries_by_loan.get(lid, [])
        booked = {je.get("emi_month") for je in jes if je.get("emi_month")}
        # Entries written before emi_month was recorded are matched by date and amount
        undated = [(str(je.get("date") or "")[:10], round(float(je.get("total_amount") or 0), 2))
                   for je in jes if not je.get("emi_month")]
        for row in ln.get("emi_schedule", []):
            if row.get("status") != "paid" or float(row.get("paid_amount") or 0) <= 0:
                continue
            if row.get("due_month") in booked:
                continue
            key = (str(row.get("paid_date") or "")[:10], round(float(row["paid_amount"]), 2))
            if key in undated:
                undated.remove(key)
                continue
            found += 1
            amt = float(row["paid_amount"])
            if found <= 50:
                print(f"   {ln.get('loan_number')}  {row.get('due_month')}  ₹{amt:,.2f} paid {row.get('paid_date')}  — no entry")
    if found > 50:
        print(f"   … and {found - 50} more")
    print(f"   {found} found\n"); issues += found

    # 3. Stale locks
    print("3. Lock records not refreshed for 3 minutes")
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=3)
    stale = [l async for l in db.locks.find({"at": {"$lt": cutoff}})]
    for l in stale:
        print(f"   {l['_id']}  since {l.get('at')}")
    if APPLY and stale:
        await db.locks.delete_many({"_id": {"$in": [l["_id"] for l in stale]}, "at": {"$lt": cutoff}})
        print("      removed")
    print(f"   {len(stale)} found\n"); issues += len(stale)

    # 4. Re-loans missing their disbursement or settlement
    print("4. Re-loans with no disbursement entry, or a net-off with no settlement (report only)")
    disb = {canon(j.get("reference_id")) async for j in db.journal_entries.find({"entry_type": "loan_disbursement"}, {"reference_id": 1})}
    settle = {canon(j.get("reference_id")) async for j in db.journal_entries.find({"entry_type": "netoff_settlement"}, {"reference_id": 1})}
    found = 0
    for lid, ln in loans.items():
        if not ln.get("is_reloan") or ln.get("is_import"):
            continue
        missing = []
        if lid not in disb:
            missing.append("disbursement")
        if (float(ln.get("netoff_amount") or 0) > 0 and lid not in settle
                and str(ln.get("created_at") or "") >= SETTLEMENT_SINCE):
            missing.append("net-off settlement")
        if missing:
            found += 1
            print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  — no {' or '.join(missing)} entry")
    print(f"   {found} found\n"); issues += found

    # 5-6. Money recorded for an instalment that is not paid
    print("5. Cash Book collection entries whose instalment is not paid (report only)")
    found = 0
    for lid, jes in entries_by_loan.items():
        ln = loans.get(lid)
        if not ln:
            continue
        paid = {r.get("due_month") for r in ln.get("emi_schedule", []) if r.get("status") == "paid"}
        for je in jes:
            if je.get("emi_month") and je["emi_month"] not in paid:
                found += 1
                print(f"   {ln.get('loan_number')}  {je.get('emi_month')}  ₹{float(je.get('total_amount') or 0):,.2f}  entry {je['_id']}")
    print(f"   {found} found\n"); issues += found

    print("6. Payment records above ₹0 whose instalment is not paid (report only)")
    found = 0
    async for p in db.payments.find({"amount": {"$gt": 0}}):
        ln = loans.get(canon(p.get("loan_id")))
        if not ln:
            continue
        paid = {r.get("due_month") for r in ln.get("emi_schedule", []) if r.get("status") == "paid"}
        if p.get("emi_month") not in paid:
            found += 1
            print(f"   {ln.get('loan_number')}  {p.get('emi_month')}  ₹{float(p['amount']):,.2f}  payment {p['_id']}")
    print(f"   {found} found\n"); issues += found

    # 7. Records belonging to a loan that no longer exists
    print("7. Journal entries or payments for a loan that no longer exists (report only)")
    found = 0
    async for je in db.journal_entries.find({"reference_id": {"$nin": [None, ""]}},
                                            {"reference_id": 1, "entry_type": 1, "total_amount": 1, "date": 1}):
        rid = canon(je.get("reference_id"))
        if rid and rid not in loans and je.get("entry_type") in (
                "emi_collection", "loan_disbursement", "netoff_settlement", "gyal_writeoff"):
            found += 1
            print(f"   entry {je['_id']}  {je.get('entry_type')}  ₹{float(je.get('total_amount') or 0):,.2f}  {je.get('date')}")
    async for p in db.payments.find({}, {"loan_id": 1, "amount": 1, "emi_month": 1}):
        if canon(p.get("loan_id")) not in loans:
            found += 1
            print(f"   payment {p['_id']}  ₹{float(p.get('amount') or 0):,.2f}  {p.get('emi_month')}")
    print(f"   {found} found\n"); issues += found

    # 8. total_paid below the paid instalments
    print("8. Loans whose total_paid does not match their paid instalments (report only)")
    found = 0
    for lid, ln in loans.items():
        rows = sum(float(r.get("paid_amount") or 0) for r in ln.get("emi_schedule", []) if r.get("status") == "paid")
        # Below the instalments, or — for a loan that was not imported, so has no
        # repayments from before the app — above them (a change interrupted by a
        # restart before this build).
        tp = float(ln.get("total_paid") or 0)
        if tp < rows - 0.01 or (not ln.get("is_import") and "total_paid" in ln and tp > rows + 0.01):
            found += 1
            print(f"   {ln.get('loan_number')}  total_paid ₹{float(ln.get('total_paid') or 0):,.2f}  rows ₹{rows:,.2f}")
    print(f"   {found} found\n"); issues += found

    # 9. Closed loans that still owe
    print("9. Loans marked closed that still owe money")
    found = 0
    for lid, ln in loans.items():
        if (ln.get("status") != "closed" or ln.get("netoff_closed") or ln.get("is_gyal")
                or ln.get("total_repayable") is None):
            continue
        owed = round(float(ln.get("total_repayable") or 0) - float(ln.get("total_paid") or 0), 2)
        if owed < 1.0 or "total_paid" not in ln:
            continue
        found += 1
        print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  owes ₹{owed:,.2f}")
        if APPLY:
            token = f"books_audit-{datetime.now(timezone.utc).timestamp()}"
            try:
                await db.locks.insert_one({"_id": f"loan:{lid}", "token": token, "at": datetime.now(timezone.utc)})
            except Exception:
                print("      busy — skipped, run again later")
                continue
            try:
                fresh = await db.loans.find_one({"_id": ln["_id"]})
                rows = (fresh or {}).get("emi_schedule") or []
                if (not fresh or fresh.get("status") != "closed" or fresh.get("netoff_closed") or fresh.get("is_gyal")
                        or float(fresh.get("total_repayable") or 0) - float(fresh.get("total_paid") or 0) < 1.0):
                    print("      changed meanwhile — skipped")
                    continue
                last = max((str(r.get("due_month") or "") for r in rows), default="")
                status = "overdue" if last < this_month or any(r.get("status") == "overdue" for r in rows) else "active"
                await db.loans.update_one({"_id": ln["_id"], "status": "closed"},
                                          {"$set": {"status": status,
                                                    "updated_at": datetime.now(timezone.utc).isoformat()}})
                print(f"      reopened as {status}")
            finally:
                await db.locks.delete_one({"_id": f"loan:{lid}", "token": token})
    print(f"   {found} found\n"); issues += found

    # 10-12. Year-end closings
    closings = {}
    async for c in db.illaka_closings.find({}):
        closings[(c.get("illaka_id"), c.get("closing_date"))] = c
    writeoffs = {}
    async for j in db.journal_entries.find({"entry_type": "gyal_writeoff"}, {"reference_id": 1, "total_amount": 1}):
        rid = canon(j.get("reference_id"))
        writeoffs[rid] = writeoffs.get(rid, 0.0) + float(j.get("total_amount") or 0)

    def owed_at(ln, cdate):
        after = sum(float(r.get("paid_amount") or 0) for r in ln.get("emi_schedule", [])
                    if r.get("status") == "paid" and day(r.get("paid_date")) > cdate)
        return float(ln.get("total_repayable") or 0) - paid_total(ln) + after
    print("10. Loans written off at a closing but left incomplete (report only)")
    portfolio_id = str(heads["loans_portfolio"]["_id"]) if "loans_portfolio" in heads else ""
    later_in_portfolio = set()
    if portfolio_id:
        async for je in db.journal_entries.find({"entry_type": "emi_collection", "lines.account_head_id": portfolio_id},
                                                {"reference_id": 1, "date": 1}):
            ln = loans.get(canon(je.get("reference_id")))
            since = str((ln or {}).get("gyal_since") or "")
            if ln and ln.get("is_gyal") and len(since) == 10 and str(je.get("date") or "")[:10] > since:
                later_in_portfolio.add(canon(je.get("reference_id")))
    found = 0
    for lid, ln in loans.items():
        since = str(ln.get("gyal_since") or "")
        if not ln.get("is_gyal") or len(since) != 10:
            continue   # imported as Gyal (month only): no write-off entry is booked
        reason = ("half-done" if ln.get("writeoff_pending")
                  else "written off for less than it owed at the closing date"
                  if writeoffs.get(lid, 0.0) < owed_at(ln, since) - 0.01
                  else "later collections still in Loans Portfolio" if lid in later_in_portfolio
                  else "WRITTEN OFF FOR MORE than it owed at the closing date — needs a data fix, "
                       "re-running the closing will not correct it"
                  if writeoffs.get(lid, 0.0) > max(owed_at(ln, since), 0.0) + 0.01
                  else "")
        if reason:
            found += 1
            print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  closing {since}  ({reason})"
                  f"  → run the closing for {since} again, or the undo if you were undoing it")
    print(f"   {found} found\n"); issues += found

    print("11. Loans written off at a closing that has no closing record (report only)")
    found = 0
    for lid, ln in loans.items():
        since = str(ln.get("gyal_since") or "")
        if ln.get("is_gyal") and len(since) == 10 and (ln.get("illaka_id"), since) not in closings:
            found += 1
            print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  closing {since}  → run the closing for {since} again")
    print(f"   {found} found\n"); issues += found

    print("12. Closing records whose Gyal count does not match their loans")
    found = 0
    for (iid, cdate), c in closings.items():
        actual = sum(1 for ln in loans.values()
                     if ln.get("is_gyal") and ln.get("illaka_id") == iid and ln.get("gyal_since") == cdate)
        if int(c.get("gyal_count") or 0) != actual:
            found += 1
            print(f"   illaka {iid}  {cdate}  recorded {c.get('gyal_count')}  actual {actual}")
            if APPLY:
                await db.illaka_closings.update_one({"_id": c["_id"]}, {"$set": {"gyal_count": actual}})
                print("      corrected")
    print(f"   {found} found\n"); issues += found

    print("13. Loans created since the audit fixes with no disbursement entry (report only)")
    found = 0
    for lid, ln in loans.items():
        if ln.get("is_reloan") or ln.get("is_import") or str(ln.get("created_at") or "") < SETTLEMENT_SINCE:
            continue
        if lid not in disb:
            found += 1
            print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  created {str(ln.get('created_at'))[:10]}")
    print(f"   {found} found\n"); issues += found

    print("14. Loans that should have been written off at their Illaka's latest closing (report only)")
    latest = {}
    for (iid, cdate) in closings:
        if cdate > latest.get(iid, ""):
            latest[iid] = cdate
    found = 0
    for lid, ln in loans.items():
        cdate = latest.get(ln.get("illaka_id"))
        if not cdate or ln.get("is_gyal") or ln.get("netoff_closed") or ln.get("total_repayable") is None:
            continue
        if not day(ln.get("loan_date")) or day(ln.get("loan_date")) > cutoff_36(cdate):
            continue
        owed = owed_at(ln, cdate)
        # Only loans that existed when the closing was run; one added later
        # belongs to the next closing.
        made = str(ln.get("created_at") or "")
        rec = closings[(ln.get("illaka_id"), cdate)]
        run_at = str(rec.get("created_at") or "") or rec["_id"].generation_time.isoformat()
        existed = made <= run_at if rec.get("created_at") else made[:19] <= run_at[:19]
        if owed >= 1.0 and existed:
            found += 1
            print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  owed ₹{owed:,.2f} at {cdate}"
                  f"  → run the closing for {cdate} again — unless you were UNDOING that closing"
                  f" when the server stopped: then run the undo again instead")
    print(f"   {found} found\n"); issues += found

    print("15. Clients who cannot be given new money because a loan over three years old still owes"
          " — written off at the next year-end closing (report only)")
    today_cut = cutoff_36(date_type.today().isoformat())
    found = 0
    for lid, ln in loans.items():
        if ln.get("is_gyal") or ln.get("netoff_closed") or ln.get("total_repayable") is None:
            continue
        owed = float(ln.get("total_repayable") or 0) - paid_total(ln)
        if day(ln.get("loan_date")) and day(ln.get("loan_date")) <= today_cut and owed >= 1.0:
            found += 1
            if found <= 50:
                print(f"   {ln.get('loan_number')}  {ln.get('client_name')}  dated {day(ln.get('loan_date'))}"
                      f"  owes ₹{owed:,.2f}{'  (imported)' if ln.get('is_import') else ''}")
    if found > 50:
        print(f"   … and {found - 50} more")
    print(f"   {found} found\n")

    print("=" * 70)
    print(f"{issues} issue(s) found." + ("" if APPLY else " Nothing was changed."))


if __name__ == "__main__":
    asyncio.run(main())
