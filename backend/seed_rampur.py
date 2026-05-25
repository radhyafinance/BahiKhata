"""
Seed script: Rampur Testing Illaka with 50 clients + loans + EMI payments + 20 re-loans.
Run: python seed_rampur.py
"""
import asyncio
import random  # noqa: S311 — intentional: seeded PRNG for reproducible test data, not security use
import calendar
import re
import sys
from datetime import datetime, timezone, date as date_type, timedelta
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.environ.get("DB_NAME", "bahikhata_db")

random.seed(42)

# ── Name pools ──────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Sunita","Geeta","Meena","Rekha","Pushpa","Savita","Radha","Seema","Anita","Kavita",
    "Renu","Poonam","Manju","Usha","Asha","Lata","Priya","Neha","Vandana","Mamta",
    "Sushma","Kusum","Kamlesh","Santosh","Kamla","Prema","Sona","Rita","Nirmala","Shanti",
    "Rani","Bimla","Saroj","Sudha","Vijaya","Lalita","Indira","Sarita","Bindu","Kiran",
    "Manisha","Jyoti","Pooja","Deepa","Rashmi","Swati","Neeraj","Sheela","Champa","Hemlata",
]
LAST_NAMES = ["Devi","Kumari","Bai","Rani","Singh"]
RELATIVE_NAMES = [
    "Ramesh","Suresh","Mahesh","Dinesh","Rakesh","Naresh","Umesh","Rajesh","Viresh","Ganesh",
    "Mukesh","Ritesh","Satish","Harish","Girish","Yogesh","Lokesh","Rupesh","Nilesh","Hitesh",
    "Anil","Sunil","Vinil","Kamlesh","Santosh","Ashok","Vinod","Pramod","Sanjay","Vijay",
]

def add_months(dt: date_type, n: int) -> date_type:
    m = dt.month - 1 + n
    year = dt.year + m // 12
    month = m % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, last_day))

def build_emi_schedule(principal: float, loan_date: date_type):
    emi_amount = round(principal * 120 / 103 / 12 / 100) * 100
    schedule = []
    today = date_type.today()
    for i in range(12):
        due = add_months(loan_date, i + 1)
        due_ym = due.strftime("%Y-%m")
        # auto-mark overdue
        last_day_due = calendar.monthrange(due.year, due.month)[1]
        status = "overdue" if today > date_type(due.year, due.month, last_day_due) else "pending"
        schedule.append({
            "month": i + 1,
            "due_month": due_ym,
            "amount": emi_amount,
            "status": status,
            "paid_amount": 0.0,
            "paid_date": None,
            "collected_by_id": None,
            "collected_by_name": None,
        })
    return emi_amount, schedule

def get_loan_status(schedule):
    if all(e["status"] in ("paid", "netoff") for e in schedule):
        return "closed"
    if any(e["status"] == "overdue" for e in schedule):
        return "overdue"
    return "active"

def random_date(start: date_type, end: date_type) -> date_type:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    now = datetime.now(timezone.utc).isoformat()

    # ── 1. Create Illaka ───────────────────────────────────────────────────
    existing_illaka = await db.illakas.find_one({"name": "Rampur Testing"})
    if existing_illaka:
        illaka_id = existing_illaka["_id"]
        illaka_id_str = str(illaka_id)
        print(f"Illaka already exists: {illaka_id_str}")
    else:
        illaka_doc = {
            "_id": ObjectId(),
            "name": "Rampur Testing",
            "description": "Bulk test illaka",
            "maalik_id": None,
            "created_at": now, "updated_at": now,
        }
        await db.illakas.insert_one(illaka_doc)
        illaka_id = illaka_doc["_id"]
        illaka_id_str = str(illaka_id)
        print(f"Created Illaka: Rampur Testing ({illaka_id_str})")

    # ── 2. Create Misal ────────────────────────────────────────────────────
    existing_misal = await db.misals.find_one({"name": "Delhi Road Testing", "illaka_id": illaka_id_str})
    if existing_misal:
        misal_id = existing_misal["_id"]
        misal_id_str = str(misal_id)
        print(f"Misal already exists: {misal_id_str}")
    else:
        misal_doc = {
            "_id": ObjectId(),
            "name": "Delhi Road Testing",
            "illaka_id": illaka_id_str,
            "description": "Bulk test misal",
            "created_at": now, "updated_at": now,
        }
        await db.misals.insert_one(misal_doc)
        misal_id = misal_doc["_id"]
        misal_id_str = str(misal_id)
        print(f"Created Misal: Delhi Road Testing ({misal_id_str})")

    # ── 3. Figure out starting customer number ─────────────────────────────
    prefix = "RA"
    last_kyc = await db.kycs.find_one(
        {"customer_id": {"$regex": f"^{prefix}\\d{{4}}$"}},
        sort=[("customer_id", -1)]
    )
    seq_start = 1
    if last_kyc:
        try:
            seq_start = int(last_kyc["customer_id"][len(prefix):]) + 1
        except Exception:
            pass

    # ── 4. Create 50 clients + initial loans ──────────────────────────────
    loan_start = date_type(2022, 1, 1)
    loan_end   = date_type(2024, 12, 31)

    created_loans = []   # list of (kyc_id_str, loan_id_str, loan_doc)

    print("\nCreating 50 clients with loans (principal ₹10,300) ...")
    for i in range(50):
        seq = seq_start + i
        customer_id = f"{prefix}{seq:04d}"
        first = FIRST_NAMES[i % len(FIRST_NAMES)]
        last  = LAST_NAMES[i % len(LAST_NAMES)]
        rel   = RELATIVE_NAMES[i % len(RELATIVE_NAMES)]
        name  = f"{first} {last}"
        # unique phone per client
        phone = f"80{seq:08d}"

        loan_date = random_date(loan_start, loan_end)
        emi_amount, schedule = build_emi_schedule(10300.0, loan_date)
        total_repayable = emi_amount * 12
        interest = round(10300.0 * 17 / 103, 2)

        kyc_oid  = ObjectId()
        loan_oid = ObjectId()
        kyc_id_str  = str(kyc_oid)
        loan_id_str = str(loan_oid)
        loan_number = f"{customer_id}-L1"

        kyc_doc = {
            "_id": kyc_oid,
            "customer_id": customer_id,
            "kyc_number": customer_id,
            "status": "active",
            "illaka_id": illaka_id_str, "illaka_name": "Rampur Testing",
            "misal_id": misal_id_str,   "misal_name": "Delhi Road Testing",
            "primary_borrower": {
                "name": name,
                "relative_name": f"{rel} Kumar",
                "gender": "female",
                "phone": phone,
                "aadhaar_number": None,
            },
            "co_borrower": None, "guarantor": None,
            "loan_id": loan_id_str,
            "disbursement_amount": 10300.0,
            "created_at": now, "updated_at": now,
        }

        loan_doc = {
            "_id": loan_oid,
            "loan_number": loan_number,
            "customer_id": customer_id,
            "kyc_id": kyc_id_str,
            "client_name": name,
            "client_name_hindi": None,
            "illaka_id": illaka_id_str, "illaka_name": "Rampur Testing",
            "misal_id": misal_id_str,   "misal_name": "Delhi Road Testing",
            "principal_amount": 10300.0,
            "interest_rate": 17.0,
            "emi_amount": emi_amount,
            "total_repayable": float(total_repayable),
            "netoff_amount": 0.0,
            "loan_date": loan_date.strftime("%Y-%m-%d"),
            "status": get_loan_status(schedule),
            "emi_schedule": schedule,
            "total_paid": 0.0,
            "is_gyal": False,
            "created_at": now, "updated_at": now,
        }

        await db.kycs.insert_one(kyc_doc)
        await db.loans.insert_one(loan_doc)
        created_loans.append((kyc_id_str, loan_id_str, loan_doc, schedule))

        if (i + 1) % 10 == 0:
            print(f"  Created {i+1}/50 clients")

    print("Done creating 50 clients.\n")

    # ── 5. Pay EMIs on random months ───────────────────────────────────────
    print("Paying EMIs (random months, ~30 clients fully/partially paid, ~20 overdue) ...")
    overdue_count = 0
    for idx, (kyc_id_str, loan_id_str, loan_doc, schedule) in enumerate(created_loans):
        # Last 20 clients: leave mostly overdue (0–2 payments)
        if idx >= 30:
            num_to_pay = random.randint(0, 2)
            overdue_count += 1
        else:
            # Pay between 3 and all 12 months, randomly
            # Only pay months that are PAST (overdue or have come due)
            past_indices = [j for j, e in enumerate(schedule) if e["status"] in ("overdue", "pending")]
            # For old loans (2022-2023), most months are past
            num_to_pay = random.randint(max(1, len(past_indices) // 2), len(past_indices))

        # Pick the first num_to_pay months to pay (sequential from start)
        total_paid = 0.0
        for j, emi in enumerate(schedule):
            if j >= num_to_pay:
                break
            pay_date = date_type.fromisoformat(loan_doc["loan_date"])
            pay_date = add_months(pay_date, j + 1)
            # Clamp to today
            if pay_date > date_type.today():
                pay_date = date_type.today()
            emi["status"] = "paid"
            emi["paid_amount"] = float(emi["amount"])
            emi["paid_date"] = pay_date.strftime("%Y-%m-%d")
            total_paid += emi["paid_amount"]

        new_status = get_loan_status(schedule)
        await db.loans.update_one(
            {"_id": ObjectId(loan_id_str)},
            {"$set": {"emi_schedule": schedule, "total_paid": total_paid, "status": new_status}}
        )

    print(f"Done. ~{overdue_count} clients are mostly overdue.\n")

    # ── 6. Re-loan for 20 clients ──────────────────────────────────────────
    print("Creating re-loans for 20 clients (principal ₹20,600) ...")
    reloan_start = date_type(2023, 1, 1)
    reloan_end   = date_type(2026, 3, 31)

    reloan_clients = created_loans[:20]   # first 20 clients

    for idx, (kyc_id_str, orig_loan_id_str, orig_loan_doc, _) in enumerate(reloan_clients):
        customer_id = orig_loan_doc["customer_id"]
        client_name = orig_loan_doc["client_name"]

        # Re-loan date must be after original loan date
        orig_loan_date = date_type.fromisoformat(orig_loan_doc["loan_date"])
        r_start = max(reloan_start, orig_loan_date + timedelta(days=90))
        r_end   = reloan_end
        if r_start > r_end:
            r_start = reloan_start

        reloan_date = random_date(r_start, r_end)
        emi_amount2, schedule2 = build_emi_schedule(20600.0, reloan_date)
        total_repayable2 = emi_amount2 * 12

        reloan_oid = ObjectId()
        reloan_id_str = str(reloan_oid)
        # L2 (second loan for this customer)
        loan_number2 = f"{customer_id}-L2"

        # Pay some EMIs on the re-loan (0–6 months)
        num_to_pay2 = random.randint(0, 6)
        total_paid2 = 0.0
        for j, emi in enumerate(schedule2):
            if j >= num_to_pay2:
                break
            pay_date2 = reloan_date
            pay_date2 = add_months(pay_date2, j + 1)
            if pay_date2 > date_type.today():
                pay_date2 = date_type.today()
            emi["status"] = "paid"
            emi["paid_amount"] = float(emi["amount"])
            emi["paid_date"] = pay_date2.strftime("%Y-%m-%d")
            total_paid2 += emi["paid_amount"]

        reloan_doc = {
            "_id": reloan_oid,
            "loan_number": loan_number2,
            "customer_id": customer_id,
            "kyc_id": kyc_id_str,
            "client_name": client_name,
            "client_name_hindi": None,
            "illaka_id": illaka_id_str, "illaka_name": "Rampur Testing",
            "misal_id": misal_id_str,   "misal_name": "Delhi Road Testing",
            "principal_amount": 20600.0,
            "interest_rate": 17.0,
            "emi_amount": emi_amount2,
            "total_repayable": float(total_repayable2),
            "netoff_amount": 0.0,
            "loan_date": reloan_date.strftime("%Y-%m-%d"),
            "status": get_loan_status(schedule2),
            "emi_schedule": schedule2,
            "total_paid": total_paid2,
            "is_gyal": False,
            "is_reloan": True,
            "parent_loan_id": orig_loan_id_str,
            "created_at": now, "updated_at": now,
        }

        await db.loans.insert_one(reloan_doc)

        # Link re-loan back to original
        await db.loans.update_one(
            {"_id": ObjectId(orig_loan_id_str)},
            {"$set": {"reloan_id": reloan_id_str, "updated_at": now}}
        )

        if (idx + 1) % 5 == 0:
            print(f"  Re-loans: {idx+1}/20")

    print("Done creating 20 re-loans.\n")

    # ── 7. Summary ─────────────────────────────────────────────────────────
    total_loans = await db.loans.count_documents({"illaka_id": illaka_id_str})
    total_kycs  = await db.kycs.count_documents({"illaka_id": illaka_id_str})
    print("=" * 50)
    print(f"Illaka:  Rampur Testing  ({illaka_id_str})")
    print(f"Misal:   Delhi Road Testing ({misal_id_str})")
    print(f"KYCs created:  {total_kycs}")
    print(f"Loans created: {total_loans}  (50 original + 20 re-loans)")
    print("=" * 50)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
