import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import {
  ArrowLeft, Edit, CheckCircle, XCircle, Clock, MapPin, Camera,
  Phone, User, Shield, Users, FileText, TrendingUp, AlertCircle,
  X, Loader2, PlusCircle, BookOpen, Undo2, ExternalLink, Pencil,
  RefreshCw, MinusCircle, Lock
} from "lucide-react";
import ReLoanModal from "./ReLoanModal";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);

const fmtMonth = (ym) => {
  if (!ym) return "—";
  const [y, m] = ym.split("-");
  return new Date(y, m - 1).toLocaleDateString("en-IN", { month: "short", year: "2-digit" });
};

// ─── Shared sub-components ────────────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const map = { pending: "bk-badge-pending", approved: "bk-badge-approved", rejected: "bk-badge-rejected" };
  const labels = { pending: "Pending / लंबित", approved: "Approved / स्वीकृत", rejected: "Rejected / अस्वीकृत" };
  return <span className={map[status] || "bk-badge-pending"}>{labels[status] || status}</span>;
};

const LoanStatusBadge = ({ status }) => {
  const map = {
    active: "bg-green-100 text-green-800",
    overdue: "bg-red-100 text-red-700",
    closed: "bg-gray-100 text-gray-600",
  };
  return <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${map[status] || ""}`}>{status}</span>;
};

const InfoRow = ({ label, value, multiLine }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className={`text-sm font-medium text-foreground ${multiLine ? "whitespace-pre-wrap" : "truncate"}`}>
      {value || "—"}
    </p>
  </div>
);

const SecureImage = ({ path, alt, className }) => {
  if (!path) return (
    <div className={`bg-muted flex items-center justify-center rounded-lg ${className || "w-full h-32"}`}>
      <FileText size={24} className="text-muted-foreground opacity-40" />
    </div>
  );
  return (
    <img
      src={`${API}/files/${path}`}
      alt={alt}
      className={`object-contain rounded-lg border border-border ${className || "w-full h-32"}`}
      onError={(e) => { e.target.style.display = "none"; }}
    />
  );
};

const PersonCard = ({ title, titleHi, data, icon: Icon }) => {
  if (!data || (!data.name && !data.phone)) return null;
  const docLabel = { voter_id: "Voter ID", pan: "PAN Card", ration_card: "Ration Card" };
  return (
    <div className="bk-card space-y-5">
      <div className="flex items-center gap-2 pb-3 border-b border-border">
        <div className="w-9 h-9 bg-primary/10 rounded-xl flex items-center justify-center">
          <Icon size={18} className="text-primary" />
        </div>
        <div>
          <h3 className="font-bold text-foreground font-['Outfit']">{title}</h3>
          <p className="text-xs text-muted-foreground">{titleHi}</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-3">
          <InfoRow label="Full Name / नाम" value={data.name} />
          {data.name_hindi && <InfoRow label="हिंदी नाम" value={data.name_hindi} />}
          <InfoRow label="Phone / फ़ोन" value={data.phone} />
          <InfoRow label="Date of Birth / जन्म तिथि" value={data.dob} />
          <InfoRow label="Gender / लिंग" value={data.gender} />
          <InfoRow label="Husband's / Father's Name / पति-पिता" value={data.relative_name} />
          {data.relative_name_hindi && <InfoRow label="पति/पिता का हिंदी नाम" value={data.relative_name_hindi} />}
          <InfoRow label="Aadhaar Number / आधार" value={data.aadhaar_number} />
          <InfoRow label="Address / पता" value={data.address} multiLine />
        </div>
        <div className="space-y-4">
          {data.aadhaar_front_path && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">Aadhaar Front</p>
              <SecureImage path={data.aadhaar_front_path} alt="Aadhaar Front" className="w-full h-36 object-contain" />
            </div>
          )}
          {data.aadhaar_back_path && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">Aadhaar Back</p>
              <SecureImage path={data.aadhaar_back_path} alt="Aadhaar Back" className="w-full h-36 object-contain" />
            </div>
          )}
          {data.document_type && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">
                {docLabel[data.document_type] || data.document_type} (Front)
              </p>
              <SecureImage path={data.document_front_path} alt="Doc Front" className="w-full h-36 object-contain" />
            </div>
          )}
          {data.document_back_path && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">
                {docLabel[data.document_type]} (Back)
              </p>
              <SecureImage path={data.document_back_path} alt="Doc Back" className="w-full h-36 object-contain" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ─── Passbook: Collect Modal ─────────────────────────────────────────────────
function PassbookCollectModal({ emi, loanId, onClose, onCollected }) {
  const [amount, setAmount] = useState(emi.amount);
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!amount || isNaN(amount) || Number(amount) <= 0) { toast.error("Enter valid amount"); return; }
    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/loans/${loanId}/payments`,
        { emi_month: emi.due_month, amount: Number(amount), payment_date: date },
        { withCredentials: true }
      );
      toast.success(`EMI ${emi.month} collected / किस्त ${emi.month} जमा हुई`);
      onCollected(res.data);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to collect");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="passbook-collect-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg font-['Outfit']">Collect EMI {emi.month}</h2>
            <p className="text-xs text-muted-foreground">{fmtMonth(emi.due_month)} — {emi.status === "overdue" ? "Overdue / बकाया" : "Due"}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="bk-label"><span className="bk-label-en">Amount (₹) *</span><span className="bk-label-hi">राशि</span></label>
            <input type="number" value={amount} onChange={e => setAmount(e.target.value)} className="bk-input" min="1" required data-testid="passbook-collect-amount" />
          </div>
          <div>
            <label className="bk-label"><span className="bk-label-en">Collection Date *</span><span className="bk-label-hi">तारीख</span></label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)} className="bk-input" required data-testid="passbook-collect-date" />
          </div>
          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2 w-full" data-testid="passbook-confirm-collect">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle size={18} />}
            Collect / किस्त जमा करें
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── EMI Style map ────────────────────────────────────────────────────────────
const EMI_S = {
  paid:    { row: "bg-green-50/60",    badge: "bg-green-100 text-green-800",   icon: CheckCircle,  iconCls: "text-green-600"  },
  overdue: { row: "bg-red-50/50",      badge: "bg-red-100 text-red-700",       icon: AlertCircle,  iconCls: "text-red-600"    },
  pending: { row: "",                  badge: "bg-gray-100 text-gray-600",     icon: Clock,        iconCls: "text-gray-400"   },
  netoff:  { row: "bg-purple-50/40",   badge: "bg-purple-100 text-purple-700", icon: MinusCircle,  iconCls: "text-purple-500" },
};

// ─── Passbook: Note Modal ─────────────────────────────────────────────────────
function PassbookNoteModal({ emi, loanId, onClose, onSaved }) {
  const [text, setText] = useState(emi.note || "");
  const [loading, setLoading] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await axios.patch(
        `${API}/loans/${loanId}/emi-note`,
        { emi_month: emi.due_month, note: text },
        { withCredentials: true }
      );
      toast.success("Note saved / टिप्पणी सहेजी गई");
      onSaved(res.data);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save note");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="passbook-note-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg font-['Outfit']">EMI {emi.month} — Note</h2>
            <p className="text-xs text-muted-foreground">{fmtMonth(emi.due_month)} · टिप्पणी</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSave} className="p-5 space-y-4">
          <textarea
            value={text}
            onChange={e => setText(e.target.value)}
            className="bk-input h-24 resize-none w-full"
            placeholder="e.g. Client not home, will pay next week / ग्राहक घर पर नहीं था..."
            data-testid="passbook-note-textarea"
          />
          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2 w-full" data-testid="passbook-save-note-btn">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <Pencil size={16} />}
            Save Note / सहेजें
          </button>
        </form>
      </div>
    </div>
  );
}

// ─── Passbook: Loan Card ──────────────────────────────────────────────────────
function LoanPassbookCard({ loan: initialLoan, navigate, onLoanUpdated }) {
  const { user } = useAuth();
  const [loan, setLoan] = useState(initialLoan);
  const [expanded, setExpanded] = useState(true);
  const [collectingEmi, setCollectingEmi] = useState(null);
  const [undoLoading, setUndoLoading] = useState(null);
  const [notingEmi, setNotingEmi] = useState(null);

  const schedule = loan.emi_schedule || [];
  const paidCount = schedule.filter(e => e.status === "paid").length;
  const overdueCount = schedule.filter(e => e.status === "overdue").length;
  const outstanding = (loan.total_repayable || loan.emi_amount * 12) - (loan.total_paid || 0);
  const today = new Date().toISOString().slice(0, 7);

  const isPastMonthFrozen = (dueMonth) => {
    if (user?.role === "admin" || user?.role === "maalik") return false;
    const now = new Date();
    const currentYM = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    return dueMonth < currentYM;
  };

  const updateLoan = (updatedLoan) => {
    setLoan(updatedLoan);
    onLoanUpdated?.(updatedLoan);
  };

  const handleCollected = (updatedLoan) => updateLoan(updatedLoan);
  const handleNoteSaved = (updatedLoan) => updateLoan(updatedLoan);

  const handleUndo = async (emiMonth) => {
    if (!window.confirm("Undo this EMI collection? / यह किस्त वापस करें?")) return;
    setUndoLoading(emiMonth);
    try {
      await axios.delete(`${API}/loans/${loan.id}/payments/${emiMonth}`, { withCredentials: true });
      const res = await axios.get(`${API}/loans/${loan.id}`, { withCredentials: true });
      updateLoan(res.data);
      toast.success("EMI collection undone");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally {
      setUndoLoading(null);
    }
  };

  return (
    <div className="border border-border rounded-xl overflow-hidden" data-testid={`passbook-loan-${loan.id}`}>
      {/* Loan header — always visible */}
      <div
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3.5 bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer select-none"
        data-testid={`loan-card-toggle-${loan.id}`}
        role="button"
        aria-expanded={expanded}
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
            <TrendingUp size={16} className="text-primary" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-sm font-bold text-foreground">{loan.loan_number || "—"}</span>
              {loan.is_reloan && (
                <span className="text-[10px] px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded-full font-semibold">Re-Loan</span>
              )}
              {loan.netoff_closed && (
                <span className="text-[10px] px-1.5 py-0.5 bg-gray-200 text-gray-600 rounded-full font-semibold">Net-off closed</span>
              )}
              <LoanStatusBadge status={loan.status} />
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              {fmt(loan.principal_amount)} · {loan.loan_date ? new Date(loan.loan_date).toLocaleDateString("en-IN") : "—"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Outstanding</p>
            <p className={`text-sm font-bold ${outstanding > 0 ? "text-red-600" : "text-green-600"}`}>{fmt(outstanding)}</p>
          </div>
          <button
            onClick={e => { e.stopPropagation(); navigate(`/loans/${loan.id}`); }}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground"
            title="Open full loan detail"
            data-testid={`open-loan-${loan.id}`}
          >
            <ExternalLink size={14} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="divide-y divide-border/60">
          {/* 4-stat bar */}
          <div className="grid grid-cols-4 divide-x divide-border/60 text-center bg-muted/10">
            {[
              { label: "Principal", hi: "मूलधन", val: fmt(loan.principal_amount), cls: "text-foreground" },
              { label: "EMI", hi: "किस्त", val: fmt(loan.emi_amount), cls: "text-blue-700" },
              { label: "Paid", hi: "चुकाया", val: fmt(loan.total_paid), cls: "text-green-700" },
              { label: "Balance", hi: "बकाया", val: fmt(outstanding), cls: outstanding > 0 ? "text-red-600" : "text-green-600" },
            ].map(s => (
              <div key={s.label} className="py-2.5 px-1">
                <p className={`text-sm font-bold font-['Outfit'] ${s.cls}`}>{s.val}</p>
                <p className="text-[10px] text-muted-foreground leading-tight">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Progress bar */}
          <div className="px-4 py-2 bg-muted/5">
            <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
              <span>{paidCount}/12 EMIs paid{overdueCount > 0 ? <span className="text-red-600 ml-2">{overdueCount} overdue</span> : ""}</span>
              <span>{Math.round((paidCount / 12) * 100)}%</span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${(paidCount / 12) * 100}%` }} />
            </div>
          </div>

          {/* EMI Schedule header */}
          <div className="grid grid-cols-[32px_1fr_80px_80px] gap-2 px-4 py-2 bg-muted/20 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            <span>#</span>
            <span>Month / Due</span>
            <span className="text-right">Amount</span>
            <span className="text-center">Action</span>
          </div>

          {/* EMI Rows */}
          {schedule.map((emi) => {
            const s = EMI_S[emi.status] || EMI_S.pending;
            const StatusIcon = s.icon;
            const isPaid = emi.status === "paid";
            const isCurrentMonth = emi.due_month === today;

            return (
              <div key={emi.month}>
                <div
                  className={`grid grid-cols-[32px_1fr_80px_80px] gap-2 items-center px-4 py-2 text-sm ${s.row} ${isCurrentMonth && !isPaid ? "ring-1 ring-inset ring-primary/30" : ""}`}
                  data-testid={`emi-row-${loan.id}-${emi.month}`}
                >
                {/* Month # */}
                <span className="text-xs text-muted-foreground font-mono font-semibold">{emi.month}</span>

                {/* Month / Due date */}
                <div>
                  <span className="text-sm font-medium text-foreground">{fmtMonth(emi.due_month)}</span>
                  {isCurrentMonth && !isPaid && (
                    <span className="ml-1.5 text-[10px] px-1.5 py-0.5 bg-primary/10 text-primary rounded font-semibold">This month</span>
                  )}
                  {isPaid && emi.paid_date && (
                    <p className="text-[10px] text-green-600">Paid {new Date(emi.paid_date).toLocaleDateString("en-IN")}</p>
                  )}
                </div>

                {/* Amount */}
                <span className="text-right font-semibold tabular-nums text-foreground">
                  ₹{(emi.amount || 0).toLocaleString("en-IN")}
                </span>

                {/* Action */}
                <div className="flex flex-col items-center justify-center gap-1">
                  {emi.status === "netoff" ? (
                    <span className="text-[10px] px-2 py-1 rounded bg-purple-50 text-purple-600 font-semibold border border-purple-200">Net-off</span>
                  ) : isPaid ? (
                    isPastMonthFrozen(emi.due_month) ? (
                      <div className="flex items-center gap-1 text-[10px] text-muted-foreground" title="Past month locked">
                        <Lock size={10} /> Locked
                      </div>
                    ) : (
                      <button
                        onClick={() => handleUndo(emi.due_month)}
                        disabled={undoLoading === emi.due_month}
                        className="flex items-center gap-1 text-[10px] px-2 py-1 rounded bg-muted hover:bg-red-50 hover:text-red-600 text-muted-foreground transition-colors"
                        title="Undo collection"
                        data-testid={`passbook-undo-${loan.id}-${emi.month}`}
                      >
                        {undoLoading === emi.due_month ? <Loader2 size={10} className="animate-spin" /> : <Undo2 size={10} />}
                        Undo
                      </button>
                    )
                  ) : isPastMonthFrozen(emi.due_month) ? (
                    <div className="flex items-center gap-1 text-[10px] text-muted-foreground" title="Past month — only Maalik/Admin can edit">
                      <Lock size={10} /> Locked
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => setCollectingEmi(emi)}
                        className={`text-[11px] px-2.5 py-1 rounded-lg font-bold transition-colors whitespace-nowrap ${
                          emi.status === "overdue" ? "bg-red-600 text-white hover:bg-red-700" : "bg-primary text-white hover:bg-primary/90"
                        }`}
                        data-testid={`passbook-collect-${loan.id}-${emi.month}`}
                      >
                        Collect
                      </button>
                      <button
                        onClick={() => setNotingEmi(emi)}
                        className="flex items-center gap-0.5 text-[10px] px-2 py-0.5 rounded border border-dashed border-muted-foreground/40 text-muted-foreground hover:border-amber-400 hover:text-amber-700 transition-colors"
                        data-testid={`passbook-note-${loan.id}-${emi.month}`}
                      >
                        <Pencil size={9} /> Note
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Inline note display */}
              {emi.note && (
                <div className="col-span-4 px-4 pb-1.5" data-testid={`passbook-note-display-${loan.id}-${emi.month}`}>
                  <div className="p-1.5 bg-amber-50 border border-amber-200 rounded text-[11px] text-amber-800 break-words">{emi.note}</div>
                </div>
              )}
            </div>
            );
          })}
        </div>
      )}

      {collectingEmi && (
        <PassbookCollectModal
          emi={collectingEmi}
          loanId={loan.id}
          onClose={() => setCollectingEmi(null)}
          onCollected={handleCollected}
        />
      )}

      {notingEmi && (
        <PassbookNoteModal
          emi={notingEmi}
          loanId={loan.id}
          onClose={() => setNotingEmi(null)}
          onSaved={handleNoteSaved}
        />
      )}
    </div>
  );
}

// ─── Main ClientDetail ────────────────────────────────────────────────────────
export default function ClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [kyc, setKyc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusLoading, setStatusLoading] = useState(false);
  const [notes, setNotes] = useState("");
  const [activeTab, setActiveTab] = useState("kyc");
  const [loans, setLoans] = useState(null);
  const [loansLoading, setLoansLoading] = useState(false);
  const [showReloan, setShowReloan] = useState(false);

  useEffect(() => {
    axios
      .get(`${API}/kycs/${id}`, { withCredentials: true })
      .then((r) => { setKyc(r.data); setNotes(r.data.notes || ""); })
      .catch(() => toast.error("Failed to load KYC"))
      .finally(() => setLoading(false));
  }, [id]);

  const fetchLoans = useCallback(async () => {
    if (loans !== null) return; // already fetched
    setLoansLoading(true);
    try {
      const res = await axios.get(`${API}/loans?kyc_id=${id}&limit=20`, { withCredentials: true });
      setLoans(res.data.loans || []);
    } catch {
      toast.error("Failed to load loans");
      setLoans([]);
    } finally {
      setLoansLoading(false);
    }
  }, [id, loans]);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab === "passbook") fetchLoans();
  };

  const handleLoanUpdated = useCallback((updatedLoan) => {
    setLoans(prev => prev ? prev.map(l => l.id === updatedLoan.id ? updatedLoan : l) : prev);
  }, []);

  const updateStatus = async (status) => {
    setStatusLoading(true);
    try {
      const res = await axios.patch(`${API}/kycs/${id}/status`, { status, notes }, { withCredentials: true });
      setKyc(res.data);
      toast.success(`KYC ${status} successfully`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to update status");
    } finally {
      setStatusLoading(false);
    }
  };

  if (loading) return (
    <div className="p-8 flex items-center justify-center min-h-[400px]">
      <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!kyc) return (
    <div className="p-8 text-center text-muted-foreground">
      <p>KYC not found</p>
      <button onClick={() => navigate("/clients")} className="mt-4 text-primary hover:underline">Back to Clients</button>
    </div>
  );

  const canUpdateStatus = user?.role === "admin" || user?.role === "maalik" || user?.role === "muneem";

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/clients")} className="p-2 rounded-lg hover:bg-muted transition-colors" data-testid="back-btn">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-foreground font-['Outfit']">
              {kyc.primary_borrower?.name || "KYC Detail"}
            </h1>
            {kyc.primary_borrower?.name_hindi && (
              <p className="text-sm text-muted-foreground">{kyc.primary_borrower.name_hindi}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-sm text-muted-foreground" data-testid="customer-id-display">{kyc.customer_id || kyc.kyc_number}</span>
              <StatusBadge status={kyc.status} />
            </div>
          </div>
        </div>
        {(user?.role === "sipahi" || user?.role === "muneem" || user?.role === "admin" || user?.role === "maalik") && (
          <button
            onClick={() => navigate(`/kyc/${id}/edit`)}
            className="flex items-center gap-2 bg-muted text-foreground px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-muted/80 border border-border transition-colors"
            data-testid="edit-kyc-btn"
          >
            <Edit size={16} /> Edit
          </button>
        )}
      </div>

      {/* Meta card */}
      <div className="bk-card">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <InfoRow label="Field Agent / एजेंट" value={`${kyc.field_officer_name || "—"} (${kyc.field_officer_role || "—"})`} />
          <InfoRow label="Illaka / इलाका" value={kyc.illaka_name} />
          <InfoRow label="Misal / मिसाल" value={kyc.misal_name} />
          <InfoRow label="Created / बनाया" value={kyc.created_at ? new Date(kyc.created_at).toLocaleDateString("en-IN") : "—"} />
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 p-1 bg-muted rounded-xl w-fit">
        {[
          { id: "kyc", label: "KYC", labelHi: "पहचान", icon: User },
          { id: "passbook", label: "Passbook", labelHi: "पासबुक", icon: BookOpen },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => handleTabChange(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              activeTab === tab.id
                ? "bg-card shadow text-foreground"
                : "text-muted-foreground hover:text-foreground"
            }`}
            data-testid={`tab-${tab.id}`}
          >
            <tab.icon size={15} />
            <span>{tab.label}</span>
            <span className="text-xs opacity-60">/ {tab.labelHi}</span>
          </button>
        ))}
      </div>

      {/* ── KYC Tab ── */}
      {activeTab === "kyc" && (
        <div className="space-y-5">
          {/* Admin status update */}
          {canUpdateStatus && kyc.status === "pending" && (
            <div className="bk-card space-y-3">
              <p className="text-sm font-semibold text-foreground">Update Status / स्थिति अपडेट करें</p>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Add notes... / टिप्पणी"
                className="bk-input h-20 resize-none"
              />
              <div className="flex gap-3">
                <button
                  onClick={() => updateStatus("approved")}
                  disabled={statusLoading}
                  className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-green-700 transition-colors disabled:opacity-50"
                  data-testid="approve-btn"
                >
                  <CheckCircle size={16} /> Approve
                </button>
                <button
                  onClick={() => updateStatus("rejected")}
                  disabled={statusLoading}
                  className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-red-700 transition-colors disabled:opacity-50"
                  data-testid="reject-btn"
                >
                  <XCircle size={16} /> Reject
                </button>
              </div>
            </div>
          )}

          <PersonCard title="Primary Borrower" titleHi="प्राथमिक उधारकर्ता" data={kyc.primary_borrower} icon={User} />
          <PersonCard title="Co-borrower" titleHi="सह-उधारकर्ता" data={kyc.co_borrower} icon={Users} />
          <PersonCard title="Guarantor" titleHi="गारंटर" data={kyc.guarantor} icon={Shield} />

          {(kyc.live_photo_path || kyc.gps_location) && (
            <div className="bk-card grid grid-cols-1 sm:grid-cols-2 gap-6">
              {kyc.live_photo_path && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <Camera size={16} className="text-primary" />
                    <p className="font-semibold text-sm text-foreground">Live Photo</p>
                  </div>
                  <img
                    src={`${API}/files/${kyc.live_photo_path}`}
                    alt="Live Photo"
                    className="w-32 h-32 rounded-full object-cover border-4 border-primary shadow-md mx-auto"
                    data-testid="detail-live-photo"
                  />
                </div>
              )}
              {kyc.gps_location && (user?.role === "admin" || user?.role === "maalik") && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <MapPin size={16} className="text-primary" />
                    <p className="font-semibold text-sm text-foreground">GPS Location <span className="text-xs text-muted-foreground font-normal">(Admin/Maalik only)</span></p>
                  </div>
                  <div className="p-4 bg-green-50 rounded-xl border border-green-200 space-y-2" data-testid="detail-gps">
                    <p className="text-sm text-foreground">Lat: {kyc.gps_location.latitude?.toFixed(6)}</p>
                    <p className="text-sm text-foreground">Lng: {kyc.gps_location.longitude?.toFixed(6)}</p>
                    {kyc.gps_location.accuracy && <p className="text-xs text-muted-foreground">±{kyc.gps_location.accuracy}m accuracy</p>}
                    <a href={`https://www.google.com/maps?q=${kyc.gps_location.latitude},${kyc.gps_location.longitude}`} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline" data-testid="view-on-map-link">View on Google Maps →</a>
                  </div>
                </div>
              )}
            </div>
          )}

          {kyc.notes && (
            <div className="bk-card">
              <p className="text-xs font-semibold text-muted-foreground mb-2">Notes / टिप्पणियाँ</p>
              <p className="text-sm text-foreground">{kyc.notes}</p>
            </div>
          )}
        </div>
      )}

      {/* ── Passbook Tab ── */}
      {activeTab === "passbook" && (
        <div className="space-y-4" data-testid="passbook-tab">
          {/* Passbook header */}
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-bold text-foreground font-['Outfit']">Loan Passbook / ऋण पासबुक</h2>
              <p className="text-xs text-muted-foreground">Complete loan & EMI history for this client</p>
            </div>
            <div className="flex items-center gap-2">
              {loans && loans.length > 0 && (
                <button
                  onClick={() => setShowReloan(true)}
                  className="flex items-center gap-2 bg-primary/10 text-primary border border-primary/20 px-3 py-2 rounded-lg text-sm font-semibold hover:bg-primary/20 transition-colors"
                  data-testid="reloan-btn"
                >
                  <RefreshCw size={14} /> Re-Loan
                </button>
              )}
              {(user?.role === "muneem" || user?.role === "sipahi") && (
                <button
                  onClick={() => navigate(`/loans/new?kyc_id=${id}&client=${encodeURIComponent(kyc.primary_borrower?.name || "")}`)}
                  className="flex items-center gap-2 bk-btn-primary text-sm py-2"
                  data-testid="new-loan-btn"
                >
                  <PlusCircle size={15} />
                  New Loan
                </button>
              )}
            </div>
          </div>

          {/* Loans list */}
          {loansLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : !loans || loans.length === 0 ? (
            <div className="bk-card py-14 text-center" data-testid="passbook-empty">
              <TrendingUp size={36} className="mx-auto mb-3 text-muted-foreground opacity-30" />
              <p className="font-semibold text-foreground">No loans yet / कोई कर्ज नहीं</p>
              <p className="text-sm text-muted-foreground mt-1">Loans created from KYC form will appear here</p>
            </div>
          ) : (
            <>
              {/* Aggregate summary */}
              {loans.length > 1 && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="passbook-aggregate">
                  {(() => {
                    const totalDisbursed = loans.reduce((a, l) => a + (l.principal_amount || 0), 0);
                    const totalRepayable = loans.reduce((a, l) => a + (l.total_repayable || l.emi_amount * 12 || 0), 0);
                    const totalPaid = loans.reduce((a, l) => a + (l.total_paid || 0), 0);
                    const totalOutstanding = totalRepayable - totalPaid;
                    return [
                      { label: "Total Disbursed", hi: "कुल वितरण", val: fmt(totalDisbursed), cls: "bg-primary/10 text-primary" },
                      { label: "Total Repayable", hi: "कुल देय", val: fmt(totalRepayable), cls: "bg-blue-50 text-blue-700" },
                      { label: "Total Paid", hi: "कुल चुकाया", val: fmt(totalPaid), cls: "bg-green-50 text-green-700" },
                      { label: "Total Outstanding", hi: "कुल बकाया", val: fmt(totalOutstanding), cls: totalOutstanding > 0 ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700" },
                    ].map(s => (
                      <div key={s.label} className={`rounded-xl p-3 ${s.cls}`}>
                        <p className="text-base font-bold font-['Outfit']">{s.val}</p>
                        <p className="text-xs font-semibold">{s.label}</p>
                        <p className="text-xs opacity-70">{s.hi}</p>
                      </div>
                    ));
                  })()}
                </div>
              )}

              {[...loans]
                .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
                .map((loan) => (
                  <LoanPassbookCard key={loan.id} loan={loan} navigate={navigate} onLoanUpdated={handleLoanUpdated} />
                ))}
            </>
          )}
        </div>
      )}

      {showReloan && loans && loans.length > 0 && (() => {
        const latestLoan = [...loans].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0];
        return (
          <ReLoanModal
            loanId={latestLoan.id}
            kycId={id}
            clientName={kyc?.primary_borrower?.name}
            currentLoan={latestLoan}
            onClose={() => setShowReloan(false)}
            onSuccess={(newLoan) => navigate(`/loans/${newLoan.id}`)}
          />
        );
      })()}
    </div>
  );
}
