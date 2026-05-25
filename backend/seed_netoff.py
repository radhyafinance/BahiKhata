"""
Net-off re-loans for 10 clients in Rampur Testing (RA0021–RA0030).
Old loan: remaining overdue EMIs → status="netoff", loan closed.
New loan: principal ₹20,600 disbursed after the old loan's last paid EMI.
"""
import asyncio, calendar, random  # noqa: S311 — intentional: seeded PRNG for reproducible test data
from datetime import date as date_type, timedelta
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import os

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.environ.get("DB_NAME", "bahikhata_db")
random.seed(99)

def add_months(dt, n):
    m = dt.month - 1 + n
    year = dt.year + m // 12
    month = m % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))

def build_emi_schedule(principal, loan_date):
    emi_amount = round(principal * 120 / 103 / 12 / 100) * 100
    schedule = []
    today = date_type.today()
    for i in range(12):
        due = add_months(loan_date, i + 1)
        due_ym = due.strftime("%Y-%m")
        last_day = calendar.monthrange(due.year, due.month)[1]
        status = "overdue" if today > date_type(due.year, due.month, last_day) else "pending"
        schedule.append({
            "month": i + 1, "due_month": due_ym,
            "amount": emi_amount, "status": status,
            "paid_amount": 0.0, "paid_date": None,
            "collected_by_id": None, "collected_by_name": None,
        })
    return emi_amount, schedule

def get_loan_status(schedule):
    if all(e["status"] in ("paid", "netoff") for e in schedule):
        return "closed"
    if any(e["status"] == "overdue" for e in schedule):
        return "overdue"
    return "active"

async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    now = datetime.now(timezone.utc).isoformat()

    illaka = await db.illakas.find_one({"name": "Rampur Testing"})
    illaka_id_str = str(illaka["_id"])

    misal = await db.misals.find_one({"name": "Delhi Road Testing", "illaka_id": illaka_id_str})
    misal_id_str = str(misal["_id"])

    # Pick RA0021–RA0030 L1 loans (no existing re-loan)
    target_ids = [f"RA{i:04d}" for i in range(21, 31)]
    loans = await db.loans.find({
        "illaka_id": illaka_id_str,
        "customer_id": {"$in": target_ids},
        "loan_number": {"$regex": "-L1$"},
    }).to_list(100)

    print(f"Found {len(loans)} loans to net-off\n")

    for loan in loans:
        loan_id_str = str(loan["_id"])
        customer_id = loan["customer_id"]
        client_name = loan.get("client_name", "")
        schedule = loan.get("emi_schedule", [])
        total_repayable = float(loan.get("total_repayable", 12000))
        total_paid = float(loan.get("total_paid", 0))
        outstanding = max(0.0, total_repayable - total_paid)

        # Find last paid EMI date to anchor the new loan date
        paid_emis = [e for e in schedule if e.get("status") == "paid"]
        last_paid_ym = paid_emis[-1]["due_month"] if paid_emis else loan.get("loan_date", "")[:7]
        y, m = map(int, last_paid_ym.split("-"))
        # New loan disbursed 1–3 months after the last paid EMI
        offset = random.randint(1, 3)
        reloan_date = add_months(date_type(y, m, 15), offset)
        # Cap at today
        if reloan_date > date_type.today():
            reloan_date = date_type.today() - timedelta(days=30)

        # ── Net-off the old loan ──────────────────────────────────────────
        netoff_note = f"Net-off: closed via re-loan on {reloan_date}"
        for emi in schedule:
            if emi.get("status") != "paid":
                emi["status"] = "netoff"
                emi["note"] = netoff_note

        await db.loans.update_one(
            {"_id": loan["_id"]},
            {"$set": {
                "emi_schedule": schedule,
                "status": "closed",
                "netoff_closed": True,
                "netoff_amount": outstanding,
                "netoff_date": now,
                "updated_at": now,
            }}
        )

        # ── Create new re-loan (₹20,600) ─────────────────────────────────
        emi_amount2, schedule2 = build_emi_schedule(20600.0, reloan_date)

        # Pay 0–4 EMIs on the new loan
        num_to_pay = random.randint(0, 4)
        total_paid2 = 0.0
        for j, emi in enumerate(schedule2):
            if j >= num_to_pay:
                break
            pay_date = add_months(reloan_date, j + 1)
            if pay_date > date_type.today():
                pay_date = date_type.today()
            emi["status"] = "paid"
            emi["paid_amount"] = float(emi["amount"])
            emi["paid_date"] = pay_date.strftime("%Y-%m-%d")
            total_paid2 += emi["paid_amount"]

        # Count existing loans for this customer to generate loan number
        existing_count = await db.loans.count_documents({"customer_id": customer_id})
        loan_number2 = f"{customer_id}-L{existing_count + 1}"

        reloan_oid = ObjectId()
        reloan_doc = {
            "_id": reloan_oid,
            "loan_number": loan_number2,
            "customer_id": customer_id,
            "kyc_id": loan.get("kyc_id"),
            "client_name": client_name,
            "client_name_hindi": None,
            "illaka_id": illaka_id_str, "illaka_name": "Rampur Testing",
            "misal_id": misal_id_str,   "misal_name": "Delhi Road Testing",
            "principal_amount": 20600.0,
            "interest_rate": 17.0,
            "emi_amount": emi_amount2,
            "total_repayable": float(emi_amount2 * 12),
            "netoff_amount": outstanding,       # how much was carried over
            "loan_date": reloan_date.strftime("%Y-%m-%d"),
            "status": get_loan_status(schedule2),
            "emi_schedule": schedule2,
            "total_paid": total_paid2,
            "is_gyal": False,
            "is_reloan": True,
            "parent_loan_id": loan_id_str,
            "created_at": now, "updated_at": now,
        }
        await db.loans.insert_one(reloan_doc)

        # Back-link old loan → new loan
        await db.loans.update_one(
            {"_id": loan["_id"]},
            {"$set": {"reloan_id": str(reloan_oid)}}
        )

        print(f"  {customer_id}: old loan netoff'd (₹{outstanding:.0f} outstanding) → new loan {loan_number2} @ {reloan_date} (paid {num_to_pay}/12 EMIs)")

    print("\nDone. Verifying...")
    netoff_closed = await db.loans.count_documents({"illaka_id": illaka_id_str, "netoff_closed": True})
    total = await db.loans.count_documents({"illaka_id": illaka_id_str})
    print(f"Total loans in Rampur Testing: {total}")
    print(f"Net-off closed loans: {netoff_closed}")
    client.close()

asyncio.run(main())
