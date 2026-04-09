from fastapi import APIRouter, Request
from typing import Optional
from datetime import datetime, timezone, date as date_type
from core.database import db
from core.auth import get_current_user
from helpers import _kyc_query_for_user, _loan_query_for_user, get_admin_maalik_filter_ids, _add_months

router = APIRouter()


def _get_fy_months(ref_month: str) -> list[str]:
    """Return list of 12 YYYY-MM strings for the FY containing ref_month."""
    y, m = int(ref_month[:4]), int(ref_month[5:7])
    fy_start_year = y if m >= 4 else y - 1
    return [
        f"{fy_start_year + (1 if mo > 12 else 0)}-{((mo - 1) % 12) + 1:02d}"
        for mo in range(4, 16)
        for fy_start_year in [fy_start_year]
    ]


def _fy_months(fy_start_year: int) -> list[str]:
    months = []
    for i in range(12):
        m = 4 + i
        y = fy_start_year if m <= 12 else fy_start_year + 1
        m = m if m <= 12 else m - 12
        months.append(f"{y}-{m:02d}")
    return months


@router.get("/dashboard/stats")
async def dashboard_stats(request: Request, illaka_id: Optional[str] = None, maalik_id: Optional[str] = None):
    current_user = await get_current_user(request)
    kyc_query = await _kyc_query_for_user(current_user)
    loan_query = await _loan_query_for_user(current_user)
    if illaka_id:
        kyc_query["illaka_id"] = illaka_id
        loan_query["illaka_id"] = illaka_id
    elif maalik_id and current_user["role"] == "admin":
        ids = await get_admin_maalik_filter_ids(maalik_id)
        kyc_query["illaka_id"] = {"$in": ids}
        loan_query["illaka_id"] = {"$in": ids}
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    return {
        "total": await db.kycs.count_documents(kyc_query),
        "pending": await db.kycs.count_documents({**kyc_query, "status": "pending"}),
        "approved": await db.kycs.count_documents({**kyc_query, "status": "approved"}),
        "rejected": await db.kycs.count_documents({**kyc_query, "status": "rejected"}),
        "today": await db.kycs.count_documents({**kyc_query, "created_at": {"$gte": today}}),
        "sipahi_count": await db.users.count_documents({"role": "sipahi", "is_active": True}),
        "muneem_count": await db.users.count_documents({"role": "muneem", "is_active": True}),
        "active_loans": await db.loans.count_documents({**loan_query, "status": "active"}),
        "total_loans": await db.loans.count_documents(loan_query),
    }


@router.get("/dashboard/overview")
async def dashboard_overview(
    request: Request,
    illaka_id: Optional[str] = None,
    maalik_id: Optional[str] = None,
):
    """Rich dashboard data: portfolio, monthly stats, year recovery graph — all illaka-wise."""
    current_user = await get_current_user(request)
    loan_query = await _loan_query_for_user(current_user)

    if illaka_id:
        loan_query["illaka_id"] = illaka_id
    elif maalik_id and current_user["role"] == "admin":
        ids = await get_admin_maalik_filter_ids(maalik_id)
        loan_query["illaka_id"] = {"$in": ids}

    today = date_type.today()
    current_ym = f"{today.year}-{today.month:02d}"
    fy_start_year = today.year if today.month >= 4 else today.year - 1
    fy_months = _fy_months(fy_start_year)

    # Fetch all relevant loans
    loans = await db.loans.find(loan_query).to_list(50000)

    # Fetch illaka names
    illaka_ids_in_data = list({l["illaka_id"] for l in loans if l.get("illaka_id")})
    illakas_docs = await db.illakas.find(
        {"_id": {"$in": []}}, {"_id": 1, "name": 1}
    ).to_list(1000) if not illaka_ids_in_data else \
        await db.illakas.find({}, {"_id": 1, "name": 1}).to_list(1000)
    illaka_name_map = {str(d["_id"]): d["name"] for d in illakas_docs}

    # ── Per-Illaka accumulators ──────────────────────────────────────────────
    illaka_data: dict = {}

    def get_ia(iid: str) -> dict:
        if iid not in illaka_data:
            illaka_data[iid] = {
                "illaka_id": iid,
                "name": illaka_name_map.get(iid, iid),
                "bakaya": 0.0,
                "active_clients": set(),
                "utaar": 0.0,
                "utaar_count": 0,
                "vayda": 0.0,
                "vayda_count": 0,
                "den": 0.0,
                "den_count": 0,
                # FY monthly: {ym: {utaar, vayda}}
                "fy": {ym: {"utaar": 0.0, "vayda": 0.0} for ym in fy_months},
            }
        return illaka_data[iid]

    total_bakaya = 0.0
    total_active_clients: set = set()
    total_utaar = 0.0
    total_utaar_count = 0
    total_vayda = 0.0
    total_vayda_count = 0
    total_den = 0.0
    total_den_count = 0
    total_fy: dict = {ym: {"utaar": 0.0, "vayda": 0.0} for ym in fy_months}

    for loan in loans:
        iid = loan.get("illaka_id", "")
        ia = get_ia(iid)
        kyc_id = loan.get("kyc_id", "")
        is_gyal = loan.get("is_gyal", False)
        status = loan.get("status", "")
        schedule = loan.get("emi_schedule", [])

        # ── Bakaya (outstanding) — active/overdue non-gyal loans ──
        if not is_gyal and status not in ("closed",):
            outstanding = max(0.0, float(loan.get("total_repayable") or 0) - float(loan.get("total_paid") or 0))
            ia["bakaya"] += outstanding
            total_bakaya += outstanding
            if kyc_id:
                ia["active_clients"].add(kyc_id)
                total_active_clients.add(kyc_id)

        # ── EMI schedule processing ──
        for emi in schedule:
            due_ym = (emi.get("due_month") or "")[:7]
            paid_date = emi.get("paid_date") or ""
            paid_ym = paid_date[:7] if paid_date else ""
            amt = float(emi.get("amount") or 0)

            # Utaar — EMIs scheduled this month
            if due_ym == current_ym:
                ia["utaar"] += amt
                ia["utaar_count"] += 1
                total_utaar += amt
                total_utaar_count += 1

            # Vayda — EMIs physically collected this month
            if paid_ym == current_ym and emi.get("status") == "paid":
                ia["vayda"] += amt
                ia["vayda_count"] += 1
                total_vayda += amt
                total_vayda_count += 1

            # FY graph — Utaar
            if due_ym in total_fy:
                ia["fy"][due_ym]["utaar"] += amt
                total_fy[due_ym]["utaar"] += amt

            # FY graph — Vayda (by paid_date)
            if paid_ym in total_fy and emi.get("status") == "paid":
                ia["fy"][paid_ym]["vayda"] += amt
                total_fy[paid_ym]["vayda"] += amt

        # ── देन (Disbursements this month) ──
        loan_date = loan.get("loan_date") or ""
        if loan_date[:7] == current_ym:
            principal = float(loan.get("principal_amount") or 0)
            ia["den"] += principal
            ia["den_count"] += 1
            total_den += principal
            total_den_count += 1

    # ── Build illaka rows for response ──────────────────────────────────────
    MONTH_LABELS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
    illaka_rows = []
    for ia in illaka_data.values():
        rec_pct = round((ia["vayda"] / ia["utaar"] * 100), 1) if ia["utaar"] > 0 else None
        illaka_rows.append({
            "illaka_id": ia["illaka_id"],
            "name": ia["name"],
            "bakaya": round(ia["bakaya"], 2),
            "active_clients": len(ia["active_clients"]),
            "utaar": round(ia["utaar"], 2),
            "utaar_count": ia["utaar_count"],
            "vayda": round(ia["vayda"], 2),
            "vayda_count": ia["vayda_count"],
            "recovery_pct": rec_pct,
            "den": round(ia["den"], 2),
            "den_count": ia["den_count"],
        })
    illaka_rows.sort(key=lambda x: x["name"])

    # ── Year graph data ──────────────────────────────────────────────────────
    year_graph = []
    for i, ym in enumerate(fy_months):
        u = round(total_fy[ym]["utaar"], 2)
        v = round(total_fy[ym]["vayda"], 2)
        rec = round(v / u * 100, 1) if u > 0 else 0
        year_graph.append({
            "month": MONTH_LABELS[i],
            "ym": ym,
            "utaar": u,
            "vayda": v,
            "recovery_pct": rec,
        })

    total_rec_pct = round((total_vayda / total_utaar * 100), 1) if total_utaar > 0 else None

    return {
        "current_month": current_ym,
        "fy_start_year": fy_start_year,
        # Portfolio
        "bakaya": round(total_bakaya, 2),
        "active_clients": len(total_active_clients),
        # Monthly
        "utaar": round(total_utaar, 2),
        "utaar_count": total_utaar_count,
        "vayda": round(total_vayda, 2),
        "vayda_count": total_vayda_count,
        "recovery_pct": total_rec_pct,
        "den": round(total_den, 2),
        "den_count": total_den_count,
        # Illaka breakdown
        "illakas": illaka_rows,
        # Year graph
        "year_graph": year_graph,
    }
