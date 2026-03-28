import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import { ArrowLeft, Edit, CheckCircle, AlertCircle, Clock, X, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);

const fmtMonth = (ym) => {
  if (!ym) return "—";
  const [y, m] = ym.split("-");
  return new Date(y, m - 1).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
};

const EMI_STYLE = {
  paid: { card: "bg-green-50 border-green-200", badge: "bg-green-100 text-green-800", icon: CheckCircle, iconCls: "text-green-600" },
  overdue: { card: "bg-red-50 border-red-200", badge: "bg-red-100 text-red-700", icon: AlertCircle, iconCls: "text-red-600" },
  pending: { card: "bg-card border-border", badge: "bg-gray-100 text-gray-600", icon: Clock, iconCls: "text-gray-400" },
};

function CollectModal({ emi, loanId, onClose, onCollected }) {
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
      toast.success(`EMI ${emi.month} collected! / किस्त ${emi.month} जमा हुई`);
      onCollected(res.data);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to collect");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="collect-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg font-['Outfit']">Collect EMI {emi.month}</h2>
            <p className="text-xs text-muted-foreground">{fmtMonth(emi.due_month)} — {emi.status === "overdue" ? "Overdue / बकाया" : "Due this month"}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="bk-label"><span className="bk-label-en">Amount (₹) *</span><span className="bk-label-hi">राशि</span></label>
            <input type="number" value={amount} onChange={e => setAmount(e.target.value)} className="bk-input" min="1" required data-testid="collect-amount-input" />
          </div>
          <div>
            <label className="bk-label"><span className="bk-label-en">Collection Date *</span><span className="bk-label-hi">तारीख</span></label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)} className="bk-input" required data-testid="collect-date-input" />
          </div>
          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2 w-full" data-testid="confirm-collect-btn">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle size={18} />}
            Collect EMI / किस्त जमा करें
          </button>
        </form>
      </div>
    </div>
  );
}

export default function LoanDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loan, setLoan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collectingEmi, setCollectingEmi] = useState(null);
  const [undoLoading, setUndoLoading] = useState(null);

  useEffect(() => {
    axios.get(`${API}/loans/${id}`, { withCredentials: true })
      .then(r => setLoan(r.data))
      .catch(() => toast.error("Failed to load loan"))
      .finally(() => setLoading(false));
  }, [id]);

  const handleCollected = (updatedLoan) => setLoan(updatedLoan);

  const handleUndo = async (emiMonth) => {
    if (!window.confirm("Undo this EMI collection?")) return;
    setUndoLoading(emiMonth);
    try {
      await axios.delete(`${API}/loans/${id}/payments/${emiMonth}`, { withCredentials: true });
      const res = await axios.get(`${API}/loans/${id}`, { withCredentials: true });
      setLoan(res.data);
      toast.success("EMI collection undone");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally {
      setUndoLoading(null);
    }
  };

  if (loading) return (
    <div className="p-8 flex items-center justify-center min-h-[400px]">
      <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!loan) return (
    <div className="p-8 text-center text-muted-foreground">
      <p>Loan not found</p>
      <button onClick={() => navigate("/loans")} className="mt-4 text-primary hover:underline">Back to Loans</button>
    </div>
  );

  const schedule = loan.emi_schedule || [];
  const paidCount = schedule.filter(e => e.status === "paid").length;
  const overdueCount = schedule.filter(e => e.status === "overdue").length;
  const outstanding = (loan.total_repayable || loan.emi_amount * 12) - (loan.total_paid || 0);
  const canManage = user?.role === "admin" || user?.role === "maalik" || user?.role === "muneem";
  const canEdit = canManage || loan.sipahi_id === user?.id;

  const STATUS_BADGE = {
    active: "bg-green-100 text-green-800",
    overdue: "bg-red-100 text-red-700",
    closed: "bg-gray-100 text-gray-600",
  };

  const today = new Date().toISOString().slice(0, 7); // YYYY-MM

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/loans")} className="p-2 rounded-lg hover:bg-muted" data-testid="back-btn">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold font-['Outfit']">
              {(user?.role === "muneem" || user?.role === "sipahi")
                ? (loan.client_name_hindi || loan.client_name)
                : loan.client_name}
            </h1>
            {(user?.role === "muneem" || user?.role === "sipahi") && loan.client_name_hindi && (
              <p className="text-sm text-muted-foreground">{loan.client_name}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-sm text-muted-foreground">{loan.loan_number || "—"}</span>
              <span className="text-sm text-muted-foreground">{loan.illaka_name} / {loan.misal_name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_BADGE[loan.status] || ""}`} data-testid="loan-status-badge">
                {loan.status}
              </span>
            </div>
          </div>
        </div>
        {canEdit && loan.status !== "closed" && (
          <button onClick={() => navigate(`/loans/${id}/edit`)} className="flex items-center gap-2 bg-muted text-foreground px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-muted/80 border border-border" data-testid="edit-loan-btn">
            <Edit size={16} /> Edit
          </button>
        )}
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Principal", hi: "मूलधन", value: fmt(loan.principal_amount), cls: "bg-primary/10 text-primary" },
          { label: "Monthly EMI", hi: "मासिक किस्त", value: fmt(loan.emi_amount), cls: "bg-blue-50 text-blue-700" },
          { label: "Total Paid", hi: "चुकाया", value: fmt(loan.total_paid), cls: "bg-green-50 text-green-700" },
          { label: "Outstanding", hi: "बकाया", value: fmt(outstanding), cls: outstanding > 0 ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700" },
        ].map(c => (
          <div key={c.label} className={`rounded-xl p-4 ${c.cls}`}>
            <p className="text-lg font-bold font-['Outfit']">{c.value}</p>
            <p className="text-xs font-semibold">{c.label}</p>
            <p className="text-xs opacity-70">{c.hi}</p>
          </div>
        ))}
      </div>

      {/* Loan Info */}
      <div className="bk-card">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          {[
            { label: "Interest Rate", value: "17% flat p.a." },
            { label: "Total Repayable", value: fmt(loan.total_repayable || loan.emi_amount * 12) },
            { label: "Loan Date", value: loan.loan_date ? new Date(loan.loan_date).toLocaleDateString("en-IN") : "—" },
            { label: "Final EMI Due", value: loan.due_date ? new Date(loan.due_date).toLocaleDateString("en-IN") : "—" },
            { label: "Agent", value: loan.sipahi_name },
            { label: "Client Phone", value: loan.client_phone || "—" },
          ].map(r => (
            <div key={r.label}>
              <p className="text-xs text-muted-foreground">{r.label}</p>
              <p className="text-sm font-medium">{r.value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* EMI Schedule */}
      <div className="bk-card space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold font-['Outfit']">EMI Schedule / किस्त अनुसूची</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              {paidCount}/12 paid · {overdueCount > 0 ? <span className="text-red-600">{overdueCount} overdue</span> : "no overdue"}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-muted-foreground">Progress</p>
            <p className="text-sm font-bold text-primary">{paidCount}/12</p>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="h-2.5 bg-muted rounded-full overflow-hidden">
          <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: `${(paidCount / 12) * 100}%` }} />
        </div>

        {schedule.length === 0 ? (
          <div className="py-6 text-center text-muted-foreground text-sm" data-testid="no-schedule">
            No EMI schedule found. This may be an older loan record.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {schedule.map(emi => {
              const style = EMI_STYLE[emi.status] || EMI_STYLE.pending;
              const Icon = style.icon;
              const isCurrentMonth = emi.due_month === today;
              const canCollect = emi.status !== "paid" && loan.status !== "closed";

              return (
                <div
                  key={emi.month}
                  className={`rounded-xl border p-3 space-y-2 ${style.card} ${isCurrentMonth && emi.status !== "paid" ? "ring-2 ring-primary" : ""}`}
                  data-testid={`emi-card-${emi.month}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-muted-foreground">EMI {emi.month}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded-full font-semibold ${style.badge}`}>
                      {emi.status === "paid" ? "Paid" : emi.status === "overdue" ? "Overdue" : isCurrentMonth ? "Due Now" : "Pending"}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{fmtMonth(emi.due_month)}</p>
                  <div className="flex items-center gap-1.5">
                    <Icon size={14} className={style.iconCls} />
                    <p className="text-base font-bold font-['Outfit']">{fmt(emi.amount)}</p>
                  </div>

                  {emi.status === "paid" ? (
                    <div className="space-y-1">
                      <p className="text-xs text-green-700">
                        {emi.paid_date ? new Date(emi.paid_date).toLocaleDateString("en-IN") : "—"}
                      </p>
                      <p className="text-xs text-muted-foreground truncate">{emi.collected_by_name}</p>
                      {canManage && (
                        <button
                          onClick={() => handleUndo(emi.due_month)}
                          disabled={undoLoading === emi.due_month}
                          className="text-xs text-red-600 hover:underline mt-1"
                          data-testid={`undo-emi-${emi.month}`}
                        >
                          {undoLoading === emi.due_month ? "..." : "Undo"}
                        </button>
                      )}
                    </div>
                  ) : canCollect ? (
                    <button
                      onClick={() => setCollectingEmi(emi)}
                      className={`w-full text-xs py-1.5 rounded-lg font-semibold mt-1 transition-colors ${
                        emi.status === "overdue"
                          ? "bg-red-600 text-white hover:bg-red-700"
                          : "bg-primary text-white hover:bg-primary/90"
                      }`}
                      data-testid={`collect-emi-${emi.month}`}
                    >
                      Collect / जमा करें
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {loan.notes && (
        <div className="bk-card">
          <p className="text-xs text-muted-foreground">Notes</p>
          <p className="text-sm text-foreground mt-1">{loan.notes}</p>
        </div>
      )}

      {collectingEmi && (
        <CollectModal
          emi={collectingEmi}
          loanId={id}
          onClose={() => setCollectingEmi(null)}
          onCollected={handleCollected}
        />
      )}
    </div>
  );
}
