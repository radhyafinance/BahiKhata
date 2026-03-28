from fastapi import APIRouter, Request
from datetime import datetime, timezone
from core.database import db
from core.auth import get_current_user
from helpers import _kyc_query_for_user, _loan_query_for_user

router = APIRouter()


@router.get("/dashboard/stats")
async def dashboard_stats(request: Request):
    current_user = await get_current_user(request)
    kyc_query = await _kyc_query_for_user(current_user)
    loan_query = await _loan_query_for_user(current_user)
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
