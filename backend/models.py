from pydantic import BaseModel
from typing import Optional, List


class LoginRequest(BaseModel):
    phone: str
    password: str


class UserCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    password: str
    role: str  # admin | maalik | muneem | sipahi
    assigned_illaka_ids: Optional[List[str]] = []
    maalik_id: Optional[str] = None


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    assigned_illaka_ids: Optional[List[str]] = None
    maalik_id: Optional[str] = None
    is_active: Optional[bool] = None


class IllakaCreate(BaseModel):
    name: str
    description: Optional[str] = None
    maalik_id: Optional[str] = None


class MisalCreate(BaseModel):
    name: str
    illaka_id: str
    description: Optional[str] = None


class PersonKYCData(BaseModel):
    name: Optional[str] = None
    name_hindi: Optional[str] = None
    dob: Optional[str] = None
    address: Optional[str] = None
    relative_name: Optional[str] = None
    relative_name_hindi: Optional[str] = None
    gender: Optional[str] = None
    phone: Optional[str] = None
    aadhaar_number: Optional[str] = None
    aadhaar_front_path: Optional[str] = None
    aadhaar_back_path: Optional[str] = None
    document_type: Optional[str] = None
    document_front_path: Optional[str] = None
    document_back_path: Optional[str] = None


class GPSLocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy: Optional[float] = None
    address: Optional[str] = None
    timestamp: Optional[str] = None


class KYCCreate(BaseModel):
    illaka_id: str
    illaka_name: str
    misal_id: str
    misal_name: str
    primary_borrower: PersonKYCData
    co_borrower: Optional[PersonKYCData] = None
    guarantor: Optional[PersonKYCData] = None
    live_photo_path: Optional[str] = None
    gps_location: Optional[GPSLocation] = None
    notes: Optional[str] = None
    disbursement_amount: Optional[float] = None


class KYCStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class OCRRequest(BaseModel):
    path: str


class AssignIllakas(BaseModel):
    illaka_ids: List[str]


class LoanCreate(BaseModel):
    kyc_id: str
    client_name: str
    client_phone: Optional[str] = None
    illaka_id: str
    illaka_name: str
    misal_id: str
    misal_name: str
    principal_amount: float
    loan_date: str
    notes: Optional[str] = None


class LoanStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None


class PaymentCreate(BaseModel):
    emi_month: str
    amount: Optional[float] = None
    payment_date: str
    notes: Optional[str] = None


class EmiNoteUpdate(BaseModel):
    emi_month: str
    note: str


class TransliterateRequest(BaseModel):
    text: str


class ReLoanRequest(BaseModel):
    new_disbursement_amount: float
    loan_date: str
    net_off: bool = False
    phone: Optional[str] = None
    co_borrower: Optional[PersonKYCData] = None
    guarantor: Optional[PersonKYCData] = None
    notes: Optional[str] = None


class AccountHeadCreate(BaseModel):
    name: str
    group_id: str


class AccountHeadUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None


class JournalEntryLine(BaseModel):
    account_head_id: str
    debit: float = 0.0
    credit: float = 0.0


class JournalEntryCreate(BaseModel):
    date: str
    illaka_id: str
    narration: str
    lines: List[JournalEntryLine]


class SimpleEntryCreate(BaseModel):
    date: str
    illaka_id: str
    account_head_id: str
    amount: float
    narration: str
    cash_head_id: Optional[str] = None


class ExpenseTemplateField(BaseModel):
    field_id: Optional[str] = None
    label: str
    account_head_id: str
    display_order: int = 0


class ExpenseTemplateCreate(BaseModel):
    illaka_id: str
    fields: List[ExpenseTemplateField]


class ExpenseSubmissionEntry(BaseModel):
    field_id: str
    amount: float


class ExpenseSubmissionCreate(BaseModel):
    illaka_id: str
    month: str  # YYYY-MM
    entries: List[ExpenseSubmissionEntry]
    action: str = "draft"  # "draft" or "submit"


class YearEndClosingRequest(BaseModel):
    illaka_id: str
    closing_date: str  # "YYYY-MM-DD", typically March 31st


class YearEndUndoRequest(BaseModel):
    illaka_id: str
    closing_date: str
