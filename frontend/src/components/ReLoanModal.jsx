import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { X, Loader2, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);

export default function ReLoanModal({ loanId, kycId, clientName, currentLoan, onClose, onSuccess }) {
  const today = new Date().toISOString().split("T")[0];
  const [kycLoading, setKycLoading] = useState(!!kycId);
  const [submitting, setSubmitting] = useState(false);
  const [newAmount, setNewAmount] = useState("");
  const [loanDate, setLoanDate] = useState(today);
  const [netOff, setNetOff] = useState(false);
  const [phone, setPhone] = useState(currentLoan?.client_phone || "");
  const [showCoBorrower, setShowCoBorrower] = useState(false);
  const [coBorrower, setCoBorrower] = useState({ name: "", phone: "" });
  const [showGuarantor, setShowGuarantor] = useState(false);
  const [guarantor, setGuarantor] = useState({ name: "", phone: "" });

  const outstanding = Math.max(
    0,
    (currentLoan?.total_repayable || (currentLoan?.emi_amount || 0) * 12) - (currentLoan?.total_paid || 0)
  );
  const canNetOff = currentLoan && currentLoan.status !== "closed" && outstanding > 0;
  const newAmountNum = parseFloat(newAmount) || 0;
  const netDisbursement = netOff ? newAmountNum - outstanding : newAmountNum;

  useEffect(() => {
    if (!kycId) { setKycLoading(false); return; }
    axios.get(`${API}/kycs/${kycId}`, { withCredentials: true })
      .then(r => {
        const pb = r.data.primary_borrower || {};
        setPhone(pb.phone || currentLoan?.client_phone || "");
        if (r.data.co_borrower?.name) {
          setShowCoBorrower(true);
          setCoBorrower({ name: r.data.co_borrower.name || "", phone: r.data.co_borrower.phone || "" });
        }
        if (r.data.guarantor?.name) {
          setShowGuarantor(true);
          setGuarantor({ name: r.data.guarantor.name || "", phone: r.data.guarantor.phone || "" });
        }
      })
      .catch(() => {})
      .finally(() => setKycLoading(false));
  }, [kycId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newAmountNum || newAmountNum <= 0) { toast.error("Enter a valid disbursement amount"); return; }
    if (netOff && netDisbursement < 0) {
      toast.error(`Net disbursement cannot be negative. Outstanding: ${fmt(outstanding)}`); return;
    }
    setSubmitting(true);
    try {
      const payload = {
        new_disbursement_amount: newAmountNum,
        loan_date: loanDate,
        net_off: netOff,
        phone: phone || undefined,
        notes: netOff
          ? `Re-loan with net-off of ${fmt(outstanding)} from ${currentLoan?.loan_number || "previous loan"}`
          : "Re-loan",
      };
      if (showCoBorrower && coBorrower.name) payload.co_borrower = { name: coBorrower.name, phone: coBorrower.phone || undefined };
      if (showGuarantor && guarantor.name) payload.guarantor = { name: guarantor.name, phone: guarantor.phone || undefined };

      const res = await axios.post(`${API}/loans/${loanId}/reloan`, payload, { withCredentials: true });
      toast.success(`Re-loan ${res.data.loan_number} created successfully!`);
      onSuccess(res.data);
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to create re-loan");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" data-testid="reloan-modal">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-card w-full sm:max-w-lg rounded-t-2xl sm:rounded-2xl shadow-2xl border border-border max-h-[92vh] flex flex-col">

        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
              <RefreshCw size={18} className="text-primary" />
            </div>
            <div>
              <h2 className="font-bold text-lg font-['Outfit']">Re-Loan / पुनः ऋण</h2>
              <p className="text-xs text-muted-foreground truncate max-w-[220px]">{clientName}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted" data-testid="reloan-modal-close">
            <X size={18} />
          </button>
        </div>

        {/* Scrollable form body */}
        <form onSubmit={handleSubmit} id="reloan-form" className="overflow-y-auto flex-1 p-5 space-y-5">

          {/* Existing loan summary */}
          {currentLoan && (
            <div
              className={`rounded-xl p-4 border ${
                currentLoan.status === "closed" ? "bg-gray-50 border-gray-200" :
                currentLoan.status === "overdue" ? "bg-red-50 border-red-200" : "bg-blue-50 border-blue-200"
              }`}
              data-testid="reloan-existing-loan"
            >
              <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider mb-2">
                Existing Loan / मौजूदा कर्ज
              </p>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <p className="text-[10px] text-muted-foreground">Loan No.</p>
                  <p className="text-sm font-mono font-bold text-foreground">{currentLoan.loan_number || "—"}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">Status</p>
                  <p className={`text-sm font-semibold capitalize ${
                    currentLoan.status === "closed" ? "text-gray-600" :
                    currentLoan.status === "overdue" ? "text-red-600" : "text-green-700"
                  }`}>{currentLoan.status}</p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">Outstanding</p>
                  <p className={`text-sm font-bold ${outstanding > 0 ? "text-red-600" : "text-green-600"}`}>
                    {fmt(outstanding)}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Net-off toggle */}
          {canNetOff && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 space-y-3" data-testid="reloan-netoff-section">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm font-bold text-amber-900">Net-Off Outstanding / बकाया घटाएं</p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Close old loan &amp; deduct outstanding from new disbursement
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setNetOff(v => !v)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${netOff ? "bg-primary" : "bg-gray-300"}`}
                  data-testid="reloan-netoff-toggle"
                  role="switch"
                  aria-checked={netOff}
                >
                  <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${netOff ? "translate-x-6" : "translate-x-1"}`} />
                </button>
              </div>

              {netOff && newAmountNum > 0 && (
                <div className="bg-white rounded-lg p-3 border border-amber-200 space-y-1.5" data-testid="reloan-netoff-preview">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">New Loan Amount</span>
                    <span className="font-semibold">{fmt(newAmountNum)}</span>
                  </div>
                  <div className="flex justify-between text-sm text-red-600">
                    <span>Outstanding (Net-off)</span>
                    <span className="font-semibold">− {fmt(outstanding)}</span>
                  </div>
                  <div className="border-t border-amber-200 pt-1.5 flex justify-between">
                    <span className="text-sm font-bold text-foreground">Net Disbursement to Client</span>
                    <span className={`text-sm font-bold ${netDisbursement < 0 ? "text-red-600" : "text-green-700"}`}>
                      {fmt(netDisbursement)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* New disbursement amount */}
          <div>
            <label className="bk-label">
              <span className="bk-label-en">New Disbursement Amount (₹) *</span>
              <span className="bk-label-hi">नई ऋण राशि</span>
            </label>
            <input
              type="number"
              value={newAmount}
              onChange={e => setNewAmount(e.target.value)}
              className="bk-input"
              placeholder="e.g. 50000"
              min="1000"
              step="500"
              required
              data-testid="reloan-amount-input"
            />
          </div>

          {/* Loan date */}
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Loan Date *</span>
              <span className="bk-label-hi">ऋण तिथि</span>
            </label>
            <input
              type="date"
              value={loanDate}
              onChange={e => setLoanDate(e.target.value)}
              className="bk-input"
              required
              data-testid="reloan-date-input"
            />
          </div>

          {/* Client phone */}
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Client Phone</span>
              <span className="bk-label-hi">ग्राहक फ़ोन</span>
            </label>
            <input
              type="tel"
              value={phone}
              onChange={e => setPhone(e.target.value)}
              className="bk-input"
              placeholder="10-digit mobile number"
              data-testid="reloan-phone-input"
            />
          </div>

          {/* Co-borrower (collapsible) */}
          <div className="border border-border rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setShowCoBorrower(v => !v)}
              className="w-full flex items-center justify-between px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors"
              data-testid="reloan-coborrower-toggle"
            >
              <span className="text-sm font-semibold text-foreground">
                Co-Borrower / सह-उधारकर्ता{" "}
                <span className="text-xs text-muted-foreground font-normal">(Optional)</span>
              </span>
              {showCoBorrower ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showCoBorrower && (
              <div className="p-4 space-y-3 border-t border-border">
                <div>
                  <label className="bk-label"><span className="bk-label-en">Name</span><span className="bk-label-hi">नाम</span></label>
                  <input
                    type="text"
                    value={coBorrower.name}
                    onChange={e => setCoBorrower(p => ({ ...p, name: e.target.value }))}
                    className="bk-input"
                    placeholder="Co-borrower full name"
                    data-testid="reloan-coborrower-name"
                  />
                </div>
                <div>
                  <label className="bk-label"><span className="bk-label-en">Phone</span><span className="bk-label-hi">फ़ोन</span></label>
                  <input
                    type="tel"
                    value={coBorrower.phone}
                    onChange={e => setCoBorrower(p => ({ ...p, phone: e.target.value }))}
                    className="bk-input"
                    placeholder="Phone number"
                    data-testid="reloan-coborrower-phone"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Guarantor (collapsible) */}
          <div className="border border-border rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setShowGuarantor(v => !v)}
              className="w-full flex items-center justify-between px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors"
              data-testid="reloan-guarantor-toggle"
            >
              <span className="text-sm font-semibold text-foreground">
                Guarantor / गारंटर{" "}
                <span className="text-xs text-muted-foreground font-normal">(Optional)</span>
              </span>
              {showGuarantor ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showGuarantor && (
              <div className="p-4 space-y-3 border-t border-border">
                <div>
                  <label className="bk-label"><span className="bk-label-en">Name</span><span className="bk-label-hi">नाम</span></label>
                  <input
                    type="text"
                    value={guarantor.name}
                    onChange={e => setGuarantor(p => ({ ...p, name: e.target.value }))}
                    className="bk-input"
                    placeholder="Guarantor full name"
                    data-testid="reloan-guarantor-name"
                  />
                </div>
                <div>
                  <label className="bk-label"><span className="bk-label-en">Phone</span><span className="bk-label-hi">फ़ोन</span></label>
                  <input
                    type="tel"
                    value={guarantor.phone}
                    onChange={e => setGuarantor(p => ({ ...p, phone: e.target.value }))}
                    className="bk-input"
                    placeholder="Phone number"
                    data-testid="reloan-guarantor-phone"
                  />
                </div>
              </div>
            )}
          </div>
        </form>

        {/* Footer */}
        <div className="p-5 border-t border-border flex-shrink-0 space-y-3">
          {netOff && outstanding > 0 && (
            <p className="text-xs text-center text-muted-foreground">
              Old loan auto-closed. EMIs based on full {fmt(newAmountNum)}. Client receives{" "}
              <strong className={netDisbursement < 0 ? "text-red-600" : "text-green-700"}>{fmt(netDisbursement)}</strong>.
            </p>
          )}
          <button
            type="submit"
            form="reloan-form"
            disabled={submitting || kycLoading}
            className="bk-btn-primary flex items-center justify-center gap-2 w-full"
            data-testid="reloan-submit-btn"
          >
            {submitting ? <Loader2 size={18} className="animate-spin" /> : <RefreshCw size={18} />}
            {submitting ? "Creating Re-Loan..." : "Create Re-Loan / पुनः ऋण बनाएं"}
          </button>
        </div>
      </div>
    </div>
  );
}
