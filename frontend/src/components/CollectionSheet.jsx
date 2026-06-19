import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import {
  ChevronDown, ChevronRight, CheckCircle, AlertCircle, Clock,
  X, Loader2, ExternalLink, IndianRupee, Pencil, Lock, Edit3, Printer, Trash2
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);

// Full amount: 2500 → "2,500", 3000 → "3,000"
const fmtK = (n) => {
  if (!n) return "";
  return new Intl.NumberFormat("en-IN").format(Math.round(n));
};

// Returns the 12 YYYY-MM strings for the financial year containing `ym` (April → March)
function getFyMonths(ym) {
  const [y, m] = ym.split("-").map(Number);
  const fyStart = m >= 4 ? y : y - 1;
  const result = [];
  for (let i = 0; i < 12; i++) {
    const fm = ((3 + i) % 12) + 1;
    const fy = fm >= 4 ? fyStart : fyStart + 1;
    result.push(`${fy}-${String(fm).padStart(2, "0")}`);
  }
  return result;
}

// FY selector helpers
function getCurrentFyStart() {
  const today = new Date();
  const m = today.getMonth() + 1;
  return m >= 4 ? today.getFullYear() : today.getFullYear() - 1;
}

function getFyLabel(fyStart) {
  return `${fyStart}-${String(fyStart + 1).slice(-2)}`;
}

// Active month to send to the API for a given FY start year
function getApiMonthForFy(fyStart) {
  const curFyStart = getCurrentFyStart();
  if (fyStart === curFyStart) {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  }
  return `${fyStart + 1}-03`;
}

const fmtMonth = (ym) => {
  if (!ym) return "—";
  const [y, m] = ym.split("-");
  return new Date(y, m - 1).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
};

const fmtLoanDate = (dateStr) => {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
};

const EMI_STATUS = {
  paid: { cls: "bg-green-100 text-green-800", label: "Collected", icon: CheckCircle, iconCls: "text-green-600" },
  netoff: { cls: "bg-blue-50 text-blue-700", label: "Net-off", icon: CheckCircle, iconCls: "text-blue-500" },
  overdue: { cls: "bg-red-100 text-red-700", label: "Overdue", icon: AlertCircle, iconCls: "text-red-600" },
  pending: { cls: "bg-gray-100 text-gray-600", label: "Pending", icon: Clock, iconCls: "text-gray-400" },
};

function CollectModal({ row, onClose, onCollected, defaultDate }) {
  const [amount, setAmount] = useState(row.emi_amount);
  const [date, setDate] = useState(defaultDate || new Date().toISOString().split("T")[0]);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!amount || isNaN(amount) || Number(amount) <= 0) {
      toast.error("Enter valid amount");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post(
        `${API}/loans/${row.loan_db_id}/payments`,
        { emi_month: row.emi_month, amount: Number(amount), payment_date: date },
        { withCredentials: true }
      );
      toast.success(`Collected from ${row.client_name} / किस्त जमा हुई`);
      onCollected(row.loan_db_id, res.data, row.emi_month, Number(amount));
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to collect");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="collect-modal">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <p className="font-bold text-base font-['Outfit']">{row.client_name}</p>
            <p className="text-xs text-muted-foreground">
              {row.loan_number} · {fmtMonth(row.emi_month)}
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted">
            <X size={18} />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Amount (₹) *</span>
              <span className="bk-label-hi">राशि</span>
            </label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="bk-input"
              min="1"
              required
              data-testid="collect-amount-input"
            />
          </div>
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Collection Date *</span>
              <span className="bk-label-hi">तारीख</span>
            </label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="bk-input"
              required
              data-testid="collect-date-input"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="bk-btn-primary flex items-center justify-center gap-2 w-full"
            data-testid="confirm-collect-btn"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle size={18} />}
            Collect / किस्त जमा करें
          </button>
        </form>
      </div>
    </div>
  );
}

function NoteModal({ row, onClose, onSaved }) {
  const [text, setText] = useState(row.emi_note || "");
  const [loading, setLoading] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.patch(
        `${API}/loans/${row.loan_db_id}/emi-note`,
        { emi_month: row.emi_month, note: text },
        { withCredentials: true }
      );
      toast.success("Note saved / टिप्पणी सहेजी गई");
      onSaved(row.loan_db_id, row.emi_month, text);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save note");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="vasuli-note-modal">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <p className="font-bold text-base font-['Outfit']">{row.client_name_hindi || row.client_name}</p>
            <p className="text-xs text-muted-foreground">{row.loan_number} · {fmtMonth(row.emi_month)}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSave} className="p-4 space-y-4">
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Note / Reason EMI not collected</span>
              <span className="bk-label-hi">कारण / टिप्पणी</span>
            </label>
            <textarea
              value={text}
              onChange={e => setText(e.target.value)}
              className="bk-input h-24 resize-none"
              placeholder="e.g. Client not home, will pay next week / ग्राहक घर पर नहीं था..."
              data-testid="vasuli-note-textarea"
              autoFocus
            />
          </div>
          <div className="flex gap-3">
            {text && (
              <button type="button" onClick={() => setText("")}
                className="flex-1 py-2.5 rounded-lg border border-border text-sm font-semibold text-muted-foreground hover:bg-muted">
                Clear
              </button>
            )}
            <button type="submit" disabled={loading}
              className="flex-1 bk-btn-primary flex items-center justify-center gap-2"
              data-testid="vasuli-save-note-btn">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Pencil size={16} />}
              Save / सहेजें
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EditEmiModal({ row, onClose, onEdited, onDeleted }) {
  const [amount, setAmount] = useState(row.emi_paid_amount || row.emi_amount);
  const [date, setDate] = useState(row.emi_paid_date || new Date().toISOString().split("T")[0]);
  const [loading, setLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!amount || isNaN(amount) || Number(amount) <= 0) {
      toast.error("Enter a valid amount");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.patch(
        `${API}/loans/${row.loan_db_id}/payments/${row.emi_month}`,
        { amount: Number(amount), payment_date: date },
        { withCredentials: true }
      );
      toast.success(`Entry updated for ${row.client_name}`);
      onEdited(row.loan_db_id, row.emi_month, Number(amount), date, res.data);
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to update entry");
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    setLoading(true);
    try {
      await axios.delete(
        `${API}/loans/${row.loan_db_id}/payments/${row.emi_month}`,
        { withCredentials: true }
      );
      toast.success(`Entry deleted for ${row.client_name} — ${fmtMonth(row.emi_month)}`);
      onDeleted();
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to delete entry");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="edit-emi-modal">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <div>
            <p className="font-bold text-base font-['Outfit']">{row.client_name}</p>
            <p className="text-xs text-muted-foreground">
              {row.loan_number} · {fmtMonth(row.emi_month)} · Edit Entry
            </p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted">
            <X size={18} />
          </button>
        </div>

        {confirmDelete ? (
          <div className="p-4 space-y-4">
            <div className="bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
              <p className="font-semibold mb-1">Delete this collection entry?</p>
              <p>This will mark <span className="font-semibold">{fmtMonth(row.emi_month)}</span> as unpaid for <span className="font-semibold">{row.client_name}</span>. This cannot be undone.</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setConfirmDelete(false)}
                className="flex-1 bk-btn-secondary"
                disabled={loading}
                data-testid="cancel-delete-emi-btn"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={loading}
                className="flex-1 flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white rounded-lg px-4 py-2 font-semibold text-sm transition-colors"
                data-testid="confirm-delete-emi-btn"
              >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                हाँ, Delete करें
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-4 space-y-4">
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Amount (₹) *</span>
                <span className="bk-label-hi">राशि</span>
              </label>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="bk-input"
                min="1"
                required
                data-testid="edit-emi-amount-input"
              />
            </div>
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Collection Date *</span>
                <span className="bk-label-hi">तारीख</span>
              </label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="bk-input"
                required
                data-testid="edit-emi-date-input"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="bk-btn-primary flex items-center justify-center gap-2 w-full"
              data-testid="confirm-edit-emi-btn"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <Edit3 size={18} />}
              Update Entry / बदलाव सहेजें
            </button>
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              disabled={loading}
              className="flex items-center justify-center gap-2 w-full border border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg px-4 py-2 text-sm font-semibold transition-colors"
              data-testid="delete-emi-btn"
            >
              <Trash2 size={15} />
              Delete Entry / हटाएं
            </button>
          </form>
        )}
      </div>
    </div>
  );
}


function MisalSection({ misal, month, isFrozen, userRole, currentMonth, latestClosingYm, fyMonths, onCollect, onNote, onEdit, collectDate, onCollected }) {
  const [expanded, setExpanded] = useState(true);
  const navigate = useNavigate();

  const regularRows = misal.rows.filter((r) => !r.is_gyal);
  const gyalRows = misal.rows.filter((r) => r.is_gyal);
  const total = misal.rows.length;
  const collected = misal.rows.filter((r) => r.emi_status === "paid").length;

  const renderRow = (row, isGyal) => {
    const status = EMI_STATUS[row.emi_status] || EMI_STATUS.pending;
    const StatusIcon = status.icon;
    const isPaid = row.emi_status === "paid" || row.emi_status === "netoff";
    const clientName = row.client_name_hindi || row.client_name || "—";
    const husbandName = row.relative_name_hindi || row.relative_name || "";
    const guarantorName = row.guarantor_name_hindi || row.guarantor_name || "";

    // Edit permission: paid rows only (not netoff — those were closed via re-loan)
    const canEditRow = row.emi_status === "paid" && (() => {
      if (userRole === "muneem" || userRole === "sipahi") {
        return row.emi_month === currentMonth;
      }
      if (userRole === "admin" || userRole === "maalik") {
        return !latestClosingYm || row.emi_month > latestClosingYm;
      }
      return false;
    })();

    return (
      <div
        key={row.loan_db_id}
        className={`transition-colors ${
          isGyal
            ? "bg-gray-100/70"
            : isPaid && row.emi_status === "netoff"
            ? "bg-blue-50/40"
            : isPaid
            ? "bg-green-50/50"
            : row.emi_status === "overdue"
            ? "bg-red-50/40"
            : ""
        }`}
        data-testid={`collection-row-${row.loan_db_id}`}
      >
        <div className="grid grid-cols-[52px_1fr_68px_80px] lg:grid-cols-[52px_130px_88px_88px_1fr_68px_80px] landscape:grid-cols-[52px_130px_88px_88px_1fr_68px_80px] gap-0 items-stretch text-sm">
          {/* EMI Amount */}
          <div className="text-right pr-2 pl-3 py-3 flex flex-col justify-center flex-shrink-0">
            {/* Older ancestor EMIs (3+ level chains) — oldest first, all strikethrough */}
            {(row.older_emi_chain || []).map((amt, i) => (
              <p key={i} className="text-[11px] tabular-nums text-muted-foreground line-through mb-0.5">
                {new Intl.NumberFormat("en-IN").format(amt)}
              </p>
            ))}
            {/* Immediate parent's EMI */}
            {row.is_netoff_combined && row.prev_emi_amount > 0 && (
              <p className="text-[11px] tabular-nums text-muted-foreground line-through mb-0.5">
                {new Intl.NumberFormat("en-IN").format(row.prev_emi_amount)}
              </p>
            )}
            <p className="font-bold text-sm leading-tight text-foreground">
              {new Intl.NumberFormat("en-IN").format(row.emi_amount)}
            </p>
            <div className="inline-flex items-center justify-center mt-1 w-full">
              <StatusIcon size={12} className={status.iconCls} />
            </div>
          </div>

          {/* Names column */}
          <div className="pl-2 pr-2 py-2.5 min-w-0 flex flex-col justify-center">
            <p className={`font-semibold text-sm leading-snug break-words text-foreground`} data-testid={`client-name-${row.loan_db_id}`}>
              {clientName}
            </p>
            {husbandName && (
              <p className={`text-xs leading-snug break-words mt-0.5 text-muted-foreground`} data-testid={`husband-name-${row.loan_db_id}`}>
                {husbandName}
              </p>
            )}
            {guarantorName && (
              <p className={`text-xs leading-snug break-words mt-0.5 text-blue-600`} data-testid={`guarantor-name-${row.loan_db_id}`}>
                {guarantorName}
              </p>
            )}
            {/* Show loan date on mobile only (not desktop or landscape) */}
            <p className="lg:hidden landscape:hidden text-[10px] text-muted-foreground/70 mt-0.5">{fmtLoanDate(row.loan_date)}</p>
          </div>

          {/* पिछली बाक़ी — desktop only: loan from a PREVIOUS FY (or L1 opening balance for net-off combined) */}
          {(() => {
            const loanYm = row.loan_date ? row.loan_date.substring(0, 7) : null;
            const isOldLoan = loanYm && loanYm < fyMonths[0];
            // For net-off combined rows: always show L1's opening balance in this column
            const showPrev = row.is_netoff_combined
              ? (row.prev_opening_balance > 0)
              : isOldLoan;
            const prevAmount = row.is_netoff_combined ? row.prev_opening_balance : row.opening_balance;
            return (
              <div className="hidden lg:flex landscape:flex flex-col justify-center text-right pr-2 pl-1 py-2.5">
                {showPrev ? (
                  <>
                    <p className="font-semibold text-sm tabular-nums text-foreground">{fmt(prevAmount)}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {row.is_netoff_combined
                        ? fmtLoanDate(row.prev_loan_date)
                        : fmtLoanDate(row.loan_date)}
                    </p>
                  </>
                ) : null}
              </div>
            );
          })()}

          {/* किस्त हाल — desktop only: new loan disbursed IN the selected FY */}
          {(() => {
            const loanYm = row.loan_date ? row.loan_date.substring(0, 7) : null;
            const isNewLoan = loanYm && loanYm >= fyMonths[0];
            // For net-off combined rows: only show if L2 was disbursed in THIS FY
            // (backend sets new_loan_in_fy=true only when L2 started in the viewed FY)
            const showNew = row.is_netoff_combined ? (row.new_loan_in_fy === true) : isNewLoan;
            const extras = row.extra_kisht_entries || [];
            return (
              <div className="hidden lg:flex landscape:flex flex-col justify-center text-right pr-2 pl-1 py-2.5">
                {showNew ? (
                  <>
                    {/* Extra chain entries (older re-loans) shown above the current one */}
                    {extras.map((entry, idx) => (
                      <div key={idx} className={idx > 0 ? "mt-1 pt-1 border-t border-border/30" : ""}>
                        <p className="font-semibold text-sm tabular-nums text-foreground">{fmt(entry.amount)}</p>
                        <p className="text-[10px] text-muted-foreground">
                          <span className="text-blue-600">↩ {fmtLoanDate(entry.loan_date)}</span>
                        </p>
                      </div>
                    ))}
                    {/* Current new loan */}
                    <div className={extras.length > 0 ? "mt-1 pt-1 border-t border-border/30" : ""}>
                      <p className="font-semibold text-sm tabular-nums text-foreground">{fmt(row.total_repayable)}</p>
                      <p className="text-[10px] text-muted-foreground mt-0.5">
                        {row.is_netoff_combined ? (
                          <span className="text-blue-600">↩ {fmtLoanDate(row.loan_date)}</span>
                        ) : (
                          fmtLoanDate(row.loan_date)
                        )}
                      </p>
                    </div>
                  </>
                ) : null}
              </div>
            );
          })()}

          {/* 12-month FY strip — desktop or landscape, expands to fill all available space */}
          <div className="hidden lg:flex landscape:flex self-stretch border-x border-border divide-x divide-border/50">
            {(row.emi_year_data || []).map((yd) => {
              const isCurr = yd.month === month;

              if (yd.status === "na") {
                return (
                  <div key={yd.month} className={`flex-1 ${isCurr ? "bg-primary/5" : "bg-muted/10"}`} />
                );
              }
              if (yd.status === "paid") {
                const hasNote = !!yd.note;
                return (
                  <div
                    key={yd.month}
                    title={hasNote ? `₹${yd.paid_amount} — ${yd.note}` : `Paid ₹${yd.paid_amount}`}
                    className={`flex-1 flex flex-col items-center justify-center gap-0.5 ${isCurr ? "bg-green-200" : "bg-green-100"}`}
                  >
                    <span className="text-green-800 text-sm font-bold leading-none">✓</span>
                    <span className="text-green-700 text-xs font-bold leading-none">{fmtK(yd.paid_amount)}</span>
                    {hasNote && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                  </div>
                );
              }
              if (yd.status === "netoff" || yd.status === "chain_start") {
                return (
                  <div
                    key={yd.month}
                    title={yd.status === "chain_start" ? "Net-off — new loan starts here" : "Net-off (closed via re-loan)"}
                    className={`flex-1 flex flex-col items-center justify-center gap-0.5 ${isCurr ? "bg-blue-100" : "bg-blue-50/60"}`}
                  >
                    <span className="text-blue-600 text-xs font-bold leading-none">↩</span>
                  </div>
                );
              }
              if (yd.note) {
                return (
                  <div
                    key={yd.month}
                    title={yd.note}
                    className={`flex-1 flex flex-col items-center justify-center gap-1 px-1 ${isCurr ? "bg-amber-100" : "bg-amber-50/70"}`}
                  >
                    <Pencil size={11} className="text-amber-600 shrink-0" />
                    <span className="text-amber-700 text-[9px] font-semibold leading-tight text-center line-clamp-2">{yd.note}</span>
                  </div>
                );
              }
              if (yd.status === "overdue") {
                return (
                  <div key={yd.month} className={`flex-1 flex items-center justify-center ${isCurr ? "bg-red-100" : ""}`}>
                    <span className="text-red-400 text-base font-bold">!</span>
                  </div>
                );
              }
              // pending
              return (
                <div key={yd.month} className={`flex-1 flex items-center justify-center ${isCurr ? "bg-primary/5" : ""}`}>
                  <span className="text-muted-foreground/20 text-xl leading-none">·</span>
                </div>
              );
            })}
          </div>

          {/* Balance — amount only, date moved to new columns */}
          <div className="text-right pr-3 pl-1 py-2.5 flex flex-col justify-center">
            <p className={`font-semibold text-sm leading-tight tabular-nums text-foreground`}>
              {fmt(row.outstanding_balance)}
            </p>
          </div>

          {/* Action */}
          <div className="flex flex-col items-center justify-center gap-1 py-2.5 px-1">
            {isPaid ? (
              <div className="flex flex-col items-center gap-1">
                <CheckCircle size={20} className={row.emi_status === "netoff" ? "text-blue-400" : "text-green-500"} />
                {row.emi_status === "netoff" ? (
                  <span className="text-[9px] text-blue-500 font-semibold">Net-off</span>
                ) : canEditRow ? (
                  <button
                    onClick={() => onEdit(row)}
                    className="flex items-center justify-center gap-0.5 text-[10px] w-full py-1 rounded border border-dashed border-primary/40 text-primary hover:bg-primary/10 transition-colors"
                    data-testid={`edit-emi-btn-${row.loan_db_id}`}
                  >
                    <Edit3 size={9} />
                    Edit
                  </button>
                ) : null}
                <button
                  onClick={() => navigate(`/loans/${row.loan_db_id}`)}
                  className="p-1 rounded hover:bg-muted text-muted-foreground"
                  title="View"
                  data-testid={`view-loan-btn-paid-${row.loan_db_id}`}
                >
                  <ExternalLink size={12} />
                </button>
              </div>
            ) : isFrozen ? (
              <div className="flex flex-col items-center gap-1">
                <Lock size={14} className="text-muted-foreground" />
                <span className="text-[9px] text-muted-foreground">Locked</span>
                <button
                  onClick={() => navigate(`/loans/${row.loan_db_id}`)}
                  className="p-1 rounded hover:bg-muted text-muted-foreground"
                  title="View"
                  data-testid={`view-loan-btn-frozen-${row.loan_db_id}`}
                >
                  <ExternalLink size={12} />
                </button>
              </div>
            ) : (
              <>
                {/* Mobile: tap button → CollectModal (avoids mis-entry on small screen) */}
                <button
                  onClick={() => onCollect(row)}
                  className={`lg:hidden landscape:hidden text-xs font-bold w-full py-2 rounded-lg transition-colors ${
                    row.emi_status === "overdue"
                      ? "bg-red-500 hover:bg-red-600 text-white"
                      : "bg-primary hover:bg-primary/90 text-primary-foreground"
                  }`}
                  data-testid={`collect-btn-mobile-${row.loan_db_id}`}
                >
                  Collect
                </button>

                {/* Desktop / Landscape: inline input with Enter-key rapid entry */}
                <input
                  type="number"
                  defaultValue={row.emi_amount}
                  min="1"
                  data-action-input={isGyal ? undefined : "true"}
                  onFocus={(e) => e.target.select()}
                  onKeyDown={async (e) => {
                    if (e.key !== "Enter") return;
                    e.preventDefault();
                    const amount = Number(e.target.value);
                    if (!amount || amount <= 0) {
                      toast.error("Enter valid amount");
                      return;
                    }
                    try {
                      await axios.post(
                        `${API}/loans/${row.loan_db_id}/payments`,
                        { emi_month: row.emi_month, amount, payment_date: collectDate },
                        { withCredentials: true }
                      );
                      toast.success(`किस्त जमा — ${row.client_name_hindi || row.client_name}`);
                      onCollected(row.loan_db_id, null, row.emi_month, amount);
                      // Focus next uncollected row's input (skip Gyal rows)
                      const allInputs = [...document.querySelectorAll('[data-action-input="true"]')];
                      const idx = allInputs.indexOf(e.target);
                      if (idx >= 0 && idx < allInputs.length - 1) {
                        allInputs[idx + 1].focus();
                        allInputs[idx + 1].select();
                      }
                    } catch (err) {
                      toast.error(err.response?.data?.detail || "Failed to collect");
                    }
                  }}
                  className={`hidden lg:block landscape:block bk-input h-9 text-center text-sm font-bold w-full tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none ${
                    row.emi_status === "overdue"
                      ? "border-red-400 focus:ring-red-200"
                      : ""
                  }`}
                  data-testid={`collect-amount-input-${row.loan_db_id}`}
                />
                <button
                  onClick={() => onNote(row)}
                  className="flex items-center justify-center gap-0.5 text-[10px] w-full py-1 rounded border border-dashed border-muted-foreground/40 text-muted-foreground hover:border-amber-400 hover:text-amber-700 hover:bg-amber-50 transition-colors"
                  data-testid={`note-btn-${row.loan_db_id}`}
                >
                  <Pencil size={9} />
                  {row.emi_note ? "Edit" : "Note"}
                </button>
                <button
                  onClick={() => navigate(`/loans/${row.loan_db_id}`)}
                  className="p-1 rounded hover:bg-muted text-muted-foreground"
                  title="View"
                  data-testid={`view-loan-btn-${row.loan_db_id}`}
                >
                  <ExternalLink size={12} />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Note display */}
        {row.emi_note && (
          <div className="px-3 pb-2" data-testid={`vasuli-note-display-${row.loan_db_id}`}>
            <div className="p-1.5 bg-amber-50 border border-amber-200 rounded text-[11px] text-amber-800 break-words leading-snug">
              {row.emi_note}
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="border border-border rounded-xl overflow-clip">
      {/* Misal Header — sticky below the page controls bar */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className={`w-full flex items-center justify-between px-4 py-3 bg-muted/40 hover:bg-muted/60 transition-colors sm:sticky sm:top-14 z-20 ${expanded ? "rounded-t-xl" : "rounded-xl"}`}
        data-testid={`misal-header-${misal.misal_id}`}
      >
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDown size={16} className="text-muted-foreground" /> : <ChevronRight size={16} className="text-muted-foreground" />}
          <span className="font-semibold text-sm text-foreground">{misal.misal_name}</span>
          <span className="text-xs text-muted-foreground">({total})</span>
          {gyalRows.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 bg-gray-200 text-gray-500 rounded font-semibold">
              {gyalRows.length} Gyal
            </span>
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${collected === total ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
          {collected}/{total}
        </span>
      </button>

      {expanded && (
        <div className="divide-y divide-border/60">
          {/* Column Header — sticky below toggle */}
          <div className="grid grid-cols-[52px_1fr_68px_80px] lg:grid-cols-[52px_130px_88px_88px_1fr_68px_80px] landscape:grid-cols-[52px_130px_88px_88px_1fr_68px_80px] gap-0 items-stretch bg-muted/50 border-b border-border text-[10px] font-bold text-muted-foreground uppercase tracking-wider sm:sticky sm:top-[100px] z-10">
            <span className="text-right pr-2 pl-3 py-2 self-center">EMI</span>
            <span className="pl-2 py-2 self-center">नाम / Name</span>
            {/* New columns — desktop or landscape */}
            <span className="hidden lg:flex landscape:flex items-center justify-end pr-2 pl-1 py-2 text-right leading-tight">पिछली बाक़ी</span>
            <span className="hidden lg:flex landscape:flex items-center justify-end pr-2 pl-1 py-2 text-right leading-tight">किस्त हाल</span>
            {/* 12-month headers — desktop or landscape, boxy */}
            <div className="hidden lg:flex landscape:flex self-stretch border-x border-border divide-x divide-border/50 bg-muted/20">
              {fyMonths.map(ym => {
                const mo = parseInt(ym.split("-")[1], 10);
                const isCurr = ym === month;
                return (
                  <div key={ym} className={`flex-1 flex items-center justify-center py-2 text-[11px] font-bold tracking-wide ${isCurr ? "text-primary bg-primary/8" : "text-muted-foreground/60"}`}>
                    {MONTH_ABBR[mo - 1]}
                  </div>
                );
              })}
            </div>
            <span className="text-right pr-3 pl-1 py-2 self-center">शेष / Bal</span>
            <span className="text-center py-2 self-center">Action</span>
          </div>

          {/* Regular rows */}
          {regularRows.map((row) => renderRow(row, false))}

          {/* Gyal separator + rows */}
          {gyalRows.length > 0 && (
            <>
              <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100/60" data-testid="gyal-separator">
                <div className="h-px flex-1 bg-gray-300" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 whitespace-nowrap">
                  Gyal — घ्याल (Bad Debt)
                </span>
                <div className="h-px flex-1 bg-gray-300" />
              </div>
              {gyalRows.map((row) => renderRow(row, true))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function CollectionSheet() {
  const { user } = useAuth();
  const { selectedIllaka, selectedMaalik } = useIllaka();
  const today = new Date();
  const defaultMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

  // FY selector state — default to current FY
  const [selectedFyStart, setSelectedFyStart] = useState(getCurrentFyStart);
  // Derive the "active month" for API calls and Collect button from the selected FY
  const month = getApiMonthForFy(selectedFyStart);
  const currentFyStart = getCurrentFyStart();
  // All FYs from 2019-20 up to the current FY (newest first)
  const availableFys = Array.from(
    { length: currentFyStart - 2019 + 1 },
    (_, i) => currentFyStart - i
  );

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collectingRow, setCollectingRow] = useState(null);
  const [notingRow, setNotingRow] = useState(null);
  const [editingRow, setEditingRow] = useState(null);
  const [selectedMisalId, setSelectedMisalId] = useState("all");
  const [collectDate, setCollectDate] = useState(new Date().toISOString().split("T")[0]);
  const [printModalOpen, setPrintModalOpen] = useState(false);
  // Per-misal blank rows map: { [misalId]: count }
  const [blankRowsMap, setBlankRowsMap] = useState({});

  const fyMonths = getFyMonths(month);

  const fetchSheet = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (selectedIllaka) params.append("illaka_id", selectedIllaka.id);
      else if (selectedMaalik) params.append("maalik_id", selectedMaalik.id);
      const res = await axios.get(`${API}/collections/sheet?${params}`, { withCredentials: true });
      setData(res.data);
    } catch (e) {
      toast.error("Failed to load collection sheet");
    } finally {
      setLoading(false);
    }
  }, [month, selectedIllaka, selectedMaalik]);

  // Silent background re-fetch — no loading spinner, just syncs data with server
  const silentFetch = useCallback(async () => {
    try {
      const params = new URLSearchParams({ month });
      if (selectedIllaka) params.append("illaka_id", selectedIllaka.id);
      else if (selectedMaalik) params.append("maalik_id", selectedMaalik.id);
      const res = await axios.get(`${API}/collections/sheet?${params}`, { withCredentials: true });
      setData(res.data);
    } catch (_) {}
  }, [month, selectedIllaka, selectedMaalik]);

  useEffect(() => { fetchSheet(); }, [fetchSheet]);

  // Reset Misal filter whenever the Illaka or FY changes
  useEffect(() => { setSelectedMisalId("all"); }, [selectedIllaka, selectedFyStart]);

  const handleCollected = (_loanDbId, _updatedLoan, _emiMonth, _collectedAmount) => {
    silentFetch();
  };

  const handleNoteSaved = (loanDbId, emiMonth, note) => {
    setData((prev) => {
      if (!prev) return prev;
      const updated = JSON.parse(JSON.stringify(prev));
      for (const il of updated.illakas) {
        for (const m of il.misals) {
          for (const row of m.rows) {
            if (row.loan_db_id === loanDbId && row.emi_month === emiMonth) {
              row.emi_note = note;
            }
          }
        }
      }
      return updated;
    });
  };

  const handleEdited = (_loanDbId, _emiMonth, _newAmount, _newDate) => {
    silentFetch();
  };

  const handleDeleted = () => {
    silentFetch();
  };

  // Flat list of all Misals for the filter dropdown
  const allMisals = useMemo(() => {
    if (!data) return [];
    const list = [];
    for (const il of data.illakas) {
      for (const ms of il.misals) {
        list.push({ id: ms.misal_id, name: ms.misal_name });
      }
    }
    return list;
  }, [data]);

  // Filtered illakas/misals for rendering
  const filteredIllakas = useMemo(() => {
    if (!data) return [];
    if (selectedMisalId === "all") return data.illakas;
    return data.illakas
      .map((il) => ({ ...il, misals: il.misals.filter((ms) => ms.misal_id === selectedMisalId) }))
      .filter((il) => il.misals.length > 0);
  }, [data, selectedMisalId]);

  // Active-month stats derived from filtered data
  const filteredStats = useMemo(() => {
    let totalRows = 0, collected = 0, overdue = 0, totalCollectedAmount = 0;
    for (const il of filteredIllakas) {
      for (const ms of il.misals) {
        for (const r of ms.rows) {
          totalRows++;
          if (r.emi_status === "paid") {
            collected++;
            totalCollectedAmount += r.emi_paid_amount || r.emi_amount || 0;
          }
          if (r.emi_status === "overdue") overdue++;
        }
      }
    }
    return { totalRows, collected, overdue, remaining: totalRows - collected, totalCollectedAmount };
  }, [filteredIllakas]);


  // FY-level stats computed from the 12-month strip data (filtered)
  const fyStats = useMemo(() => {
    let total = 0, paid = 0;
    for (const il of filteredIllakas) {
      for (const ms of il.misals) {
        for (const row of ms.rows) {
          for (const yd of (row.emi_year_data || [])) {
            if (yd.status !== "na") {
              total++;
              if (yd.status === "paid" || yd.status === "netoff") paid++;
            }
          }
        }
      }
    }
    return { total, paid };
  }, [filteredIllakas]);

  return (
    <div>
      {/* ── STICKY CONTROLS BAR ── */}
      <div className="sticky top-0 z-30 bg-background/95 backdrop-blur-sm border-b border-border" data-testid="vasuli-sticky-header">
        {/* Row 1: Title + FY badge — always full width */}
        <div className="px-4 sm:px-6 pt-2.5 pb-0 sm:pt-0 sm:pb-0 sm:h-14 flex items-center gap-2.5 sm:justify-between">
          <h1 className="text-xl font-bold text-foreground font-['Outfit'] whitespace-nowrap">Vasuli / वसूली</h1>
          <span className="text-xs px-2 py-0.5 bg-primary/10 text-primary font-semibold rounded-full whitespace-nowrap">
            FY {getFyLabel(selectedFyStart)}
          </span>
          {/* Desktop: controls inline in the same row */}
          <div className="hidden sm:flex items-center gap-2 ml-auto flex-shrink-0" data-testid="sheet-controls">
            {allMisals.length > 1 && (
              <select
                value={selectedMisalId}
                onChange={(e) => setSelectedMisalId(e.target.value)}
                className="bk-input h-9 py-0 pr-8 text-sm font-semibold max-w-[160px]"
                data-testid="misal-filter-select"
              >
                <option value="all">All Misals</option>
                {allMisals.map((ms) => (
                  <option key={ms.id} value={ms.id}>{ms.name}</option>
                ))}
              </select>
            )}
            <input
              type="date"
              value={collectDate}
              onChange={(e) => setCollectDate(e.target.value)}
              className="bk-input h-9 py-0 text-sm w-[7.5rem]"
              data-testid="global-collect-date"
            />
            <select
              value={selectedFyStart}
              onChange={(e) => setSelectedFyStart(Number(e.target.value))}
              className="bk-input h-9 py-0 pr-8 text-sm font-semibold"
              data-testid="fy-select"
            >
              {availableFys.map((fy) => (
                <option key={fy} value={fy}>
                  {getFyLabel(fy)}{fy === currentFyStart ? " (Current)" : ""}
                </option>
              ))}
            </select>
            {user?.role === "admin" && (
              <button
                onClick={() => setPrintModalOpen(true)}
                className="flex items-center gap-1.5 bk-btn-secondary h-9 px-3 text-sm font-semibold"
                title="Print / PDF — FY Collection Sheet"
                data-testid="print-sheet-btn"
              >
                <Printer size={15} />
                <span>Print</span>
              </button>
            )}
          </div>
        </div>

        {/* Row 2: Controls — mobile only, stacked for clarity */}
        <div className="sm:hidden px-4 pb-2.5 space-y-2" data-testid="sheet-controls">
          {/* Line 1: Misal filter — full width */}
          {allMisals.length > 1 && (
            <select
              value={selectedMisalId}
              onChange={(e) => setSelectedMisalId(e.target.value)}
              className="bk-input h-9 py-0 text-sm font-semibold w-full"
              data-testid="misal-filter-select"
            >
              <option value="all">All Misals</option>
              {allMisals.map((ms) => (
                <option key={ms.id} value={ms.id}>{ms.name}</option>
              ))}
            </select>
          )}
          {/* Line 2: Date + FY selector + Print */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={collectDate}
              onChange={(e) => setCollectDate(e.target.value)}
              className="bk-input h-9 py-0 text-sm flex-1 min-w-0"
              data-testid="global-collect-date"
            />
            <select
              value={selectedFyStart}
              onChange={(e) => setSelectedFyStart(Number(e.target.value))}
              className="bk-input h-9 py-0 text-sm font-semibold shrink-0 w-24"
              data-testid="fy-select"
            >
              {availableFys.map((fy) => (
                <option key={fy} value={fy}>{getFyLabel(fy)}</option>
              ))}
            </select>
            {user?.role === "admin" && (
              <button
                onClick={() => setPrintModalOpen(true)}
                className="flex items-center justify-center bk-btn-secondary h-9 w-9 p-0 shrink-0"
                title="Print"
                data-testid="print-sheet-btn"
              >
                <Printer size={15} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── PAGE CONTENT (non-sticky) ── */}
      <div className="px-4 sm:px-6 pt-4 pb-6 landscape:min-w-[1024px] space-y-5">

      {/* Summary Bar */}
      {data && (
        <div className="bk-card p-4 space-y-3" data-testid="collection-summary">
          {/* Total collected amount — prominent headline */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-0.5">
                {fmtMonth(month)} — वसूली / Collected
              </p>
              <p className="text-3xl font-black tabular-nums text-green-600 leading-none" data-testid="total-collected-amount">
                {fmt(filteredStats.totalCollectedAmount)}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                {filteredStats.collected} of {filteredStats.totalRows} EMIs &nbsp;·&nbsp;
                <span className="text-red-500">{filteredStats.overdue} overdue</span> &nbsp;·&nbsp;
                <span className="text-gray-400">{filteredStats.remaining} remaining</span>
              </p>
            </div>
            <div className="text-right shrink-0">
              <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-0.5">
                FY {getFyLabel(selectedFyStart)}
              </p>
              <p className="text-2xl font-black text-primary tabular-nums leading-none">
                {fyStats.total > 0 ? Math.round((fyStats.paid / fyStats.total) * 100) : 0}%
              </p>
              <p className="text-xs text-muted-foreground mt-1">{fyStats.paid}/{fyStats.total} EMIs</p>
            </div>
          </div>
          {/* FY progress bar */}
          <div className="h-2 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${fyStats.total > 0 ? Math.round((fyStats.paid / fyStats.total) * 100) : 0}%` }}
            />
          </div>
        </div>
      )}

      {/* Sheet Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data || filteredIllakas.length === 0 ? (
        <div className="bk-card py-16 text-center text-muted-foreground" data-testid="empty-sheet">
          <IndianRupee size={40} className="mx-auto mb-3 opacity-20" />
          <p className="font-medium text-foreground">
            {!data ? `No loans found for FY ${getFyLabel(selectedFyStart)}` : `No records for selected Misal in FY ${getFyLabel(selectedFyStart)}`}
          </p>
          <p className="text-sm mt-1">इस वर्ष कोई कर्ज़ नहीं</p>
        </div>
      ) : (
        <div className="space-y-6">
          {filteredIllakas.map((illaka) => (
            <div key={illaka.illaka_id} className="space-y-3" data-testid={`illaka-section-${illaka.illaka_id}`}>
              {/* Illaka Header */}
              <div className="flex items-center gap-3">
                <div className="h-px flex-1 bg-border" />
                <span className="text-xs font-bold uppercase tracking-widest text-primary px-3 py-1 bg-primary/10 rounded-full whitespace-nowrap">
                  {illaka.illaka_name}
                </span>
                <div className="h-px flex-1 bg-border" />
              </div>

              {/* Misals */}
              <div className="space-y-3">
                {illaka.misals.map((misal) => (
                  <MisalSection
                    key={misal.misal_id}
                    misal={misal}
                    month={month}
                    isFrozen={
                      (user?.role === "muneem" || user?.role === "sipahi") &&
                      month < defaultMonth
                    }
                    userRole={user?.role}
                    currentMonth={defaultMonth}
                    latestClosingYm={illaka.latest_closing_ym || ""}
                    fyMonths={fyMonths}
                    onCollect={setCollectingRow}
                    onNote={setNotingRow}
                    onEdit={setEditingRow}
                    collectDate={collectDate}
                    onCollected={handleCollected}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      </div>{/* end non-sticky content */}

      {collectingRow && (
        <CollectModal
          row={collectingRow}
          onClose={() => setCollectingRow(null)}
          onCollected={handleCollected}
          defaultDate={collectDate}
        />
      )}

      {/* ── Print Options Modal (Admin only) ── */}
      {printModalOpen && user?.role === "admin" && (() => {
        // Build flat list of misals with gyal count for the modal
        const allMisalsForPrint = (data?.illakas || []).flatMap(il =>
          (il.misals || []).map(ms => ({
            misalId:   ms.misal_id,
            misalName: ms.misal_name,
            gyalCount: (ms.rows || []).filter(r => r.is_gyal).length,
          }))
        );
        const buildUrl = (duplex) => {
          const encoded = encodeURIComponent(JSON.stringify(blankRowsMap));
          return `/collections/print?illaka_id=${selectedIllaka?.id}&fy_start=${selectedFyStart}&duplex=${duplex}&blank_rows=${encoded}`;
        };
        return (
          <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" data-testid="print-modal">
            <div className="bk-card w-full max-w-md flex flex-col max-h-[90vh]">
              {/* Header */}
              <div className="flex items-center justify-between p-5 pb-3 flex-shrink-0">
                <div>
                  <h2 className="text-lg font-bold font-['Outfit']">Print Collection Sheet</h2>
                  <p className="text-xs text-muted-foreground">FY {getFyLabel(selectedFyStart)} · Legal size · 10 clients/page</p>
                </div>
                <button onClick={() => setPrintModalOpen(false)} className="p-1.5 hover:bg-muted rounded-lg"><X size={18} /></button>
              </div>

              {/* Per-Misal blank rows — scrollable */}
              <div className="flex-1 overflow-y-auto px-5 pb-2 space-y-2 min-h-0">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  घ्याल से पहले खाली पंक्तियाँ (Blank rows before Gyal per Misal)
                </p>
                {allMisalsForPrint.length === 0 && (
                  <p className="text-xs text-muted-foreground">कोई मिसाल नहीं मिली।</p>
                )}
                {allMisalsForPrint.map(ms => (
                  <div key={ms.misalId} className="rounded-xl border border-border overflow-hidden">
                    {/* Misal name header */}
                    <div className="bg-muted/60 px-4 py-2 flex items-center justify-between gap-2">
                      <span className="text-sm font-bold">{ms.misalName}</span>
                      {ms.gyalCount > 0 && (
                        <span className="text-xs text-muted-foreground bg-background border border-border px-2 py-0.5 rounded-full flex-shrink-0">
                          {ms.gyalCount} Gyal
                        </span>
                      )}
                    </div>
                    {/* Blank rows input */}
                    <div className="px-4 py-2 flex items-center justify-between gap-3 bg-card">
                      <span className="text-xs text-muted-foreground whitespace-nowrap">खाली पंक्तियाँ</span>
                      <input
                        type="number"
                        min={0}
                        value={blankRowsMap[ms.misalId] ?? 0}
                        onChange={(e) => setBlankRowsMap(prev => ({
                          ...prev,
                          [ms.misalId]: Math.max(0, Number(e.target.value) || 0),
                        }))}
                        className="bk-input w-20 text-center font-bold text-base h-9 flex-shrink-0"
                        data-testid={`blank-rows-input-${ms.misalId}`}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Print buttons */}
              <div className="px-5 pb-5 pt-3 space-y-3 flex-shrink-0 border-t border-border mt-2">
                <div className="flex gap-3">
                  <button
                    onClick={() => { window.open(buildUrl(false), "_blank"); setPrintModalOpen(false); }}
                    className="flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border-2 border-border hover:border-primary hover:bg-primary/5 transition-all group"
                    data-testid="print-simplex-btn"
                  >
                    <Printer size={17} className="text-muted-foreground group-hover:text-primary" />
                    <span className="font-semibold text-sm">Single-sided</span>
                  </button>
                  <button
                    onClick={() => { window.open(buildUrl(true), "_blank"); setPrintModalOpen(false); }}
                    className="flex-1 flex items-center justify-center gap-2 p-3 rounded-xl border-2 border-border hover:border-violet-500 hover:bg-violet-50 transition-all group"
                    data-testid="print-duplex-btn"
                  >
                    <Printer size={17} className="text-muted-foreground group-hover:text-violet-600" />
                    <span className="font-semibold text-sm">Double-sided</span>
                  </button>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  A new tab will open. Click <strong>Print / PDF</strong> there, or use <kbd className="px-1 py-0.5 bg-muted rounded text-[10px]">Ctrl+P</kbd>.
                  Legal landscape · Blank Bal. and Sign columns for manual use. Gyal section starts on a new page.
                </p>
              </div>
            </div>
          </div>
        );
      })()}

      {notingRow && (
        <NoteModal
          row={notingRow}
          onClose={() => setNotingRow(null)}
          onSaved={handleNoteSaved}
        />
      )}

      {editingRow && (
        <EditEmiModal
          row={editingRow}
          onClose={() => setEditingRow(null)}
          onEdited={handleEdited}
          onDeleted={handleDeleted}
        />
      )}
    </div>
  );
}
