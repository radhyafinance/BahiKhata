import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import {
  ArrowLeft, Edit, CheckCircle, XCircle, Clock, Plus, Trash2,
  IndianRupee, TrendingUp, Loader2, X
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function fmt(n) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);
}

const STATUS_COLOR = {
  active: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-600",
  overdue: "bg-red-100 text-red-700",
};

function AddPaymentModal({ onClose, onSave }) {
  const [form, setForm] = useState({ amount: "", payment_date: new Date().toISOString().split("T")[0], notes: "" });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.amount || isNaN(form.amount) || Number(form.amount) <= 0) {
      toast.error("Enter a valid amount"); return;
    }
    setLoading(true);
    try {
      await onSave({ ...form, amount: Number(form.amount) });
      onClose();
    } catch {
      toast.error("Failed to add payment");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="payment-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-md border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg font-['Outfit']">Record Payment</h2>
            <p className="text-xs text-muted-foreground">भुगतान दर्ज करें</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="bk-label"><span className="bk-label-en">Amount (₹) *</span><span className="bk-label-hi">राशि</span></label>
            <input type="number" value={form.amount} onChange={e => setForm(p => ({ ...p, amount: e.target.value }))} className="bk-input" min="1" placeholder="e.g. 5000" required data-testid="payment-amount-input" />
          </div>
          <div>
            <label className="bk-label"><span className="bk-label-en">Payment Date *</span><span className="bk-label-hi">भुगतान तारीख</span></label>
            <input type="date" value={form.payment_date} onChange={e => setForm(p => ({ ...p, payment_date: e.target.value }))} className="bk-input" required data-testid="payment-date-input" />
          </div>
          <div>
            <label className="bk-label"><span className="bk-label-en">Notes</span></label>
            <input type="text" value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} className="bk-input" placeholder="Optional" data-testid="payment-notes-input" />
          </div>
          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2 w-full" data-testid="save-payment-btn">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
            Record Payment
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
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);

  const loadData = async () => {
    try {
      const [lRes, pRes] = await Promise.all([
        axios.get(`${API}/loans/${id}`, { withCredentials: true }),
        axios.get(`${API}/loans/${id}/payments`, { withCredentials: true }),
      ]);
      setLoan(lRes.data);
      setPayments(pRes.data);
    } catch {
      toast.error("Failed to load loan");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); }, [id]);

  const addPayment = async (data) => {
    const res = await axios.post(`${API}/loans/${id}/payments`, data, { withCredentials: true });
    setPayments(p => [res.data, ...p]);
    setLoan(l => ({ ...l, total_paid: (l.total_paid || 0) + data.amount }));
    toast.success("Payment recorded! / भुगतान दर्ज हुआ");
  };

  const deletePayment = async (pid, amount) => {
    if (!window.confirm("Delete this payment?")) return;
    await axios.delete(`${API}/loans/${id}/payments/${pid}`, { withCredentials: true });
    setPayments(p => p.filter(x => x.id !== pid));
    setLoan(l => ({ ...l, total_paid: Math.max(0, (l.total_paid || 0) - amount) }));
    toast.success("Payment deleted");
  };

  const updateStatus = async (status) => {
    setStatusLoading(true);
    try {
      const res = await axios.patch(`${API}/loans/${id}/status`, { status }, { withCredentials: true });
      setLoan(res.data);
      toast.success(`Loan marked as ${status}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally {
      setStatusLoading(false);
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
      <button onClick={() => navigate("/loans")} className="mt-4 text-primary hover:underline">Back</button>
    </div>
  );

  const outstanding = loan.principal_amount - (loan.total_paid || 0);
  const monthlyInterest = (loan.principal_amount * loan.interest_rate) / 100;
  const canManage = user?.role === "admin" || user?.role === "maalik" || user?.role === "muneem";
  const canEdit = canManage || loan.sipahi_id === user?.id;
  const canAddPayment = true; // all roles can record payment

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/loans")} className="p-2 rounded-lg hover:bg-muted" data-testid="back-btn">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold font-['Outfit']">{loan.client_name}</h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-sm text-muted-foreground">{loan.illaka_name} / {loan.misal_name}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${STATUS_COLOR[loan.status] || ""}`} data-testid="loan-status-badge">
                {loan.status}
              </span>
            </div>
          </div>
        </div>
        {canEdit && (
          <button onClick={() => navigate(`/loans/${id}/edit`)} className="flex items-center gap-2 bg-muted text-foreground px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-muted/80 border border-border" data-testid="edit-loan-btn">
            <Edit size={16} /> Edit
          </button>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Principal", labelHi: "मूलधन", value: fmt(loan.principal_amount), color: "bg-primary/10 text-primary" },
          { label: "Outstanding", labelHi: "बकाया", value: fmt(outstanding), color: outstanding > 0 ? "bg-red-50 text-red-700" : "bg-green-50 text-green-700" },
          { label: "Total Paid", labelHi: "चुकाया", value: fmt(loan.total_paid), color: "bg-green-50 text-green-700" },
          { label: "Monthly Interest", labelHi: "मासिक ब्याज", value: fmt(monthlyInterest), color: "bg-yellow-50 text-yellow-700" },
        ].map(c => (
          <div key={c.label} className={`rounded-xl p-4 ${c.color}`} data-testid={`stat-${c.label.toLowerCase().replace(/ /g, "-")}`}>
            <p className="text-lg font-bold font-['Outfit']">{c.value}</p>
            <p className="text-xs font-semibold">{c.label}</p>
            <p className="text-xs opacity-70">{c.labelHi}</p>
          </div>
        ))}
      </div>

      {/* Loan Meta */}
      <div className="bk-card">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          {[
            { label: "Interest Rate", value: `${loan.interest_rate}% / month` },
            { label: "Loan Date", value: loan.loan_date ? new Date(loan.loan_date).toLocaleDateString("en-IN") : "—" },
            { label: "Due Date", value: loan.due_date ? new Date(loan.due_date).toLocaleDateString("en-IN") : "Not set" },
            { label: "Agent (Sipahi)", value: loan.sipahi_name },
            { label: "Client Phone", value: loan.client_phone || "—" },
          ].map(r => (
            <div key={r.label}>
              <p className="text-xs text-muted-foreground">{r.label}</p>
              <p className="text-sm font-medium text-foreground">{r.value}</p>
            </div>
          ))}
        </div>
        {loan.notes && (
          <div className="mt-4 pt-4 border-t border-border">
            <p className="text-xs text-muted-foreground">Notes</p>
            <p className="text-sm text-foreground">{loan.notes}</p>
          </div>
        )}
      </div>

      {/* Status Update */}
      {canManage && (
        <div className="bk-card space-y-3" data-testid="status-panel">
          <h3 className="font-semibold text-foreground text-sm">Update Loan Status / स्थिति बदलें</h3>
          <div className="flex gap-3">
            <button onClick={() => updateStatus("active")} disabled={statusLoading || loan.status === "active"} className="flex-1 flex items-center justify-center gap-2 h-11 bg-green-600 text-white rounded-lg font-semibold hover:bg-green-700 disabled:opacity-40 text-sm" data-testid="mark-active-btn">
              <CheckCircle size={16} /> Active
            </button>
            <button onClick={() => updateStatus("overdue")} disabled={statusLoading || loan.status === "overdue"} className="flex-1 flex items-center justify-center gap-2 h-11 bg-yellow-500 text-white rounded-lg font-semibold hover:bg-yellow-600 disabled:opacity-40 text-sm" data-testid="mark-overdue-btn">
              <Clock size={16} /> Overdue
            </button>
            <button onClick={() => updateStatus("closed")} disabled={statusLoading || loan.status === "closed"} className="flex-1 flex items-center justify-center gap-2 h-11 bg-gray-500 text-white rounded-lg font-semibold hover:bg-gray-600 disabled:opacity-40 text-sm" data-testid="mark-closed-btn">
              <XCircle size={16} /> Close Loan
            </button>
          </div>
        </div>
      )}

      {/* Payments Section */}
      <div className="bk-card space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-foreground font-['Outfit']">Payment History</h3>
            <p className="text-xs text-muted-foreground">भुगतान इतिहास — {payments.length} payments</p>
          </div>
          {canAddPayment && loan.status === "active" && (
            <button onClick={() => setShowPaymentModal(true)} className="flex items-center gap-2 bg-primary text-white px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-primary/90" data-testid="add-payment-btn">
              <Plus size={16} /> Add Payment
            </button>
          )}
        </div>

        {payments.length === 0 ? (
          <div className="py-8 text-center text-muted-foreground" data-testid="no-payments">
            <IndianRupee size={36} className="mx-auto mb-2 opacity-30" />
            <p>No payments recorded yet</p>
            <p className="text-xs">अभी कोई भुगतान नहीं</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {payments.map(p => (
              <div key={p.id} className="flex items-center justify-between py-3" data-testid={`payment-${p.id}`}>
                <div>
                  <p className="font-semibold text-green-700 text-sm">{fmt(p.amount)}</p>
                  <p className="text-xs text-muted-foreground">
                    {p.payment_date ? new Date(p.payment_date).toLocaleDateString("en-IN") : "—"}
                    {" · "}{p.collected_by_name}
                    {p.notes ? ` · ${p.notes}` : ""}
                  </p>
                </div>
                {canManage && (
                  <button onClick={() => deletePayment(p.id, p.amount)} className="p-2 rounded hover:bg-destructive/10 text-destructive" data-testid={`delete-payment-${p.id}`}>
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {showPaymentModal && (
        <AddPaymentModal onClose={() => setShowPaymentModal(false)} onSave={addPayment} />
      )}
    </div>
  );
}
