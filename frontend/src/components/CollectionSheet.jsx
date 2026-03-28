import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import {
  ChevronDown, ChevronRight, CheckCircle, AlertCircle, Clock,
  X, Loader2, ExternalLink, IndianRupee, Pencil, Lock
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (n) =>
  new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);

const fmtMonth = (ym) => {
  if (!ym) return "—";
  const [y, m] = ym.split("-");
  return new Date(y, m - 1).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
};

const EMI_STATUS = {
  paid: { cls: "bg-green-100 text-green-800", label: "Collected", icon: CheckCircle, iconCls: "text-green-600" },
  overdue: { cls: "bg-red-100 text-red-700", label: "Overdue", icon: AlertCircle, iconCls: "text-red-600" },
  pending: { cls: "bg-gray-100 text-gray-600", label: "Pending", icon: Clock, iconCls: "text-gray-400" },
};

function CollectModal({ row, onClose, onCollected }) {
  const [amount, setAmount] = useState(row.emi_amount);
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
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
      onCollected(row.loan_db_id, res.data);
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

function MisalSection({ misal, month, isFrozen, onCollect, onNote }) {
  const [expanded, setExpanded] = useState(true);
  const navigate = useNavigate();
  const total = misal.rows.length;
  const collected = misal.rows.filter((r) => r.emi_status === "paid").length;

  return (
    <div className="border border-border rounded-xl overflow-hidden">
      {/* Misal Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 bg-muted/40 hover:bg-muted/60 transition-colors"
        data-testid={`misal-header-${misal.misal_id}`}
      >
        <div className="flex items-center gap-2">
          {expanded ? <ChevronDown size={16} className="text-muted-foreground" /> : <ChevronRight size={16} className="text-muted-foreground" />}
          <span className="font-semibold text-sm text-foreground">{misal.misal_name}</span>
          <span className="text-xs text-muted-foreground">({total})</span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${collected === total ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
          {collected}/{total}
        </span>
      </button>

      {expanded && (
        <div className="divide-y divide-border/60">
          {/* Column Header */}
          <div className="grid grid-cols-[52px_1fr_72px_68px] gap-0 px-3 py-1.5 bg-muted/20 text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            <span className="text-right pr-2">EMI</span>
            <span className="pl-1">नाम</span>
            <span className="text-right pr-2">शेष राशि</span>
            <span className="text-center">Action</span>
          </div>

          {misal.rows.map((row) => {
            const status = EMI_STATUS[row.emi_status] || EMI_STATUS.pending;
            const StatusIcon = status.icon;
            const isPaid = row.emi_status === "paid";
            const clientName = row.client_name_hindi || row.client_name || "—";
            const husbandName = row.relative_name_hindi || row.relative_name || "";
            const guarantorName = row.guarantor_name_hindi || row.guarantor_name || "";

            return (
              <div
                key={row.loan_db_id}
                className={`transition-colors ${isPaid ? "bg-green-50/50" : row.emi_status === "overdue" ? "bg-red-50/40" : ""}`}
                data-testid={`collection-row-${row.loan_db_id}`}
              >
                <div className="grid grid-cols-[52px_1fr_72px_68px] gap-0 items-start px-3 py-2.5 text-sm">
                {/* EMI Amount */}
                <div className="text-right pr-2 pt-0.5 flex-shrink-0">
                  <p className="font-bold text-foreground text-sm leading-tight">
                    {new Intl.NumberFormat("en-IN").format(row.emi_amount)}
                  </p>
                  <div className={`inline-flex items-center justify-center mt-1 w-full`}>
                    <StatusIcon size={12} className={status.iconCls} />
                  </div>
                </div>

                {/* Names column: Client / Husband / Guarantor */}
                <div className="pl-1 min-w-0">
                  <p className="font-semibold text-foreground text-sm leading-snug break-words" data-testid={`client-name-${row.loan_db_id}`}>
                    {clientName}
                  </p>
                  {husbandName && (
                    <p className="text-xs text-muted-foreground leading-snug break-words mt-0.5" data-testid={`husband-name-${row.loan_db_id}`}>
                      {husbandName}
                    </p>
                  )}
                  {guarantorName && (
                    <p className="text-xs text-blue-600 leading-snug break-words mt-0.5" data-testid={`guarantor-name-${row.loan_db_id}`}>
                      {guarantorName}
                    </p>
                  )}
                </div>

                {/* Balance + Month */}
                <div className="text-right pr-2 pt-0.5">
                  <p className="font-semibold text-foreground text-sm leading-tight tabular-nums">
                    {fmt(row.outstanding_balance)}
                  </p>
                  <p className="text-[11px] text-muted-foreground leading-tight mt-0.5 whitespace-nowrap">
                    {fmtMonth(row.emi_month)}
                  </p>
                </div>

                {/* Action */}
                <div className="flex flex-col items-center gap-1 pt-0.5">
                  {isPaid ? (
                    <CheckCircle size={20} className="text-green-500" />
                  ) : isFrozen ? (
                    <div className="flex flex-col items-center gap-0.5">
                      <Lock size={14} className="text-muted-foreground" />
                      <span className="text-[9px] text-muted-foreground">Locked</span>
                    </div>
                  ) : (
                    <>
                      <button
                        onClick={() => onCollect(row)}
                        className={`text-xs px-2 py-1.5 rounded-lg font-bold w-full text-center transition-colors ${
                          row.emi_status === "overdue"
                            ? "bg-red-600 text-white hover:bg-red-700"
                            : "bg-primary text-white hover:bg-primary/90"
                        }`}
                        data-testid={`collect-btn-${row.loan_db_id}`}
                      >
                        Collect
                      </button>
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

              {/* Note display below row */}
              {row.emi_note && (
                <div className="px-3 pb-2" data-testid={`vasuli-note-display-${row.loan_db_id}`}>
                  <div className="p-1.5 bg-amber-50 border border-amber-200 rounded text-[11px] text-amber-800 break-words leading-snug">
                    {row.emi_note}
                  </div>
                </div>
              )}
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function CollectionSheet() {
  const { user } = useAuth();
  const today = new Date();
  const defaultMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
  const [month, setMonth] = useState(defaultMonth);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [collectingRow, setCollectingRow] = useState(null);
  const [notingRow, setNotingRow] = useState(null);

  const fetchSheet = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/collections/sheet?month=${month}`, { withCredentials: true });
      setData(res.data);
    } catch (e) {
      toast.error("Failed to load collection sheet");
    } finally {
      setLoading(false);
    }
  }, [month]);

  useEffect(() => { fetchSheet(); }, [fetchSheet]);

  const handleCollected = (loanDbId, updatedLoan) => {
    // Update the row's EMI status in local state
    setData((prev) => {
      if (!prev) return prev;
      const updated = { ...prev };
      for (const il of updated.illakas) {
        for (const m of il.misals) {
          for (const row of m.rows) {
            if (row.loan_db_id === loanDbId) {
              row.emi_status = "paid";
              const newPaid = (updatedLoan.total_paid || 0);
              const totalRep = updatedLoan.total_repayable || (updatedLoan.emi_amount * 12);
              row.outstanding_balance = totalRep - newPaid;
            }
          }
        }
      }
      updated.collected = prev.illakas.reduce(
        (acc, il) => acc + il.misals.reduce((a, m) => a + m.rows.filter((r) => r.emi_status === "paid").length, 0), 0
      );
      return { ...updated };
    });
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

  const totalRows = data?.total || 0;
  const collected = data?.collected || 0;
  const pct = totalRows > 0 ? Math.round((collected / totalRows) * 100) : 0;

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground font-['Outfit']">Vasuli / वसूली</h1>
          <p className="text-sm text-muted-foreground">Collection Sheet — {fmtMonth(month)}</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-muted-foreground">Month:</label>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="bk-input sm:w-44"
            data-testid="month-picker"
          />
        </div>
      </div>

      {/* Summary Bar */}
      {data && (
        <div className="bk-card p-4 space-y-3" data-testid="collection-summary">
          <div className="flex items-center justify-between text-sm">
            <span className="font-semibold text-foreground">{collected} of {totalRows} EMIs collected</span>
            <span className="font-bold text-primary">{pct}%</span>
          </div>
          <div className="h-2.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><CheckCircle size={12} className="text-green-600" /> {collected} Collected</span>
            <span className="flex items-center gap-1"><AlertCircle size={12} className="text-red-500" /> {data.illakas.reduce((a, il) => a + il.misals.reduce((b, m) => b + m.rows.filter((r) => r.emi_status === "overdue").length, 0), 0)} Overdue</span>
            <span className="flex items-center gap-1"><Clock size={12} className="text-gray-400" /> {totalRows - collected} Remaining</span>
          </div>
        </div>
      )}

      {/* Sheet Content */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !data || data.illakas.length === 0 ? (
        <div className="bk-card py-16 text-center text-muted-foreground" data-testid="empty-sheet">
          <IndianRupee size={40} className="mx-auto mb-3 opacity-20" />
          <p className="font-medium text-foreground">No EMIs due for {fmtMonth(month)}</p>
          <p className="text-sm mt-1">इस महीने कोई किस्त नहीं</p>
        </div>
      ) : (
        <div className="space-y-6">
          {data.illakas.map((illaka) => (
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
                    onCollect={setCollectingRow}
                    onNote={setNotingRow}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {collectingRow && (
        <CollectModal
          row={collectingRow}
          onClose={() => setCollectingRow(null)}
          onCollected={handleCollected}
        />
      )}

      {notingRow && (
        <NoteModal
          row={notingRow}
          onClose={() => setNotingRow(null)}
          onSaved={handleNoteSaved}
        />
      )}
    </div>
  );
}
