import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import { toast } from "sonner";
import {
  BookOpen, TrendingUp, TrendingDown, Plus, Pencil, Trash2,
  ChevronLeft, ChevronRight, Lock, Zap, Settings, RefreshCw,
  ArrowUpCircle, ArrowDownCircle, BarChart3, IndianRupee,
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function fmt(n) {
  if (n == null) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function MonthNav({ month, onChange }) {
  const [y, m] = month.split("-").map(Number);
  const prev = () => {
    const d = new Date(y, m - 2, 1);
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };
  const next = () => {
    const d = new Date(y, m, 1);
    onChange(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  };
  return (
    <div className="flex items-center gap-2">
      <button onClick={prev} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
        <ChevronLeft size={16} />
      </button>
      <span className="text-sm font-bold min-w-[90px] text-center">
        {MONTHS[m - 1]} {y}
      </span>
      <button onClick={next} className="p-1.5 rounded-lg hover:bg-muted transition-colors">
        <ChevronRight size={16} />
      </button>
    </div>
  );
}

// ── Simple Entry Modal ─────────────────────────────────────────────────────────
function EntryModal({ open, onClose, onSave, editEntry, heads, illakaId, eligibleIllakas }) {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [accountHeadId, setAccountHeadId] = useState("");
  const [amount, setAmount] = useState("");
  const [narration, setNarration] = useState("");
  const [selectedIllakaId, setSelectedIllakaId] = useState("");
  const [saving, setSaving] = useState(false);

  // Determine effective illaka_id: use prop if set, else user picks
  const effectiveIllakaId = illakaId || selectedIllakaId;
  const needsIllakaSelect = !illakaId;

  useEffect(() => {
    if (editEntry) {
      setDate(editEntry.date || today);
      setNarration(editEntry.narration || "");
      setAmount(editEntry.total_amount || "");
      const nonCash = (editEntry.lines || []).find(l => !["Cash in Hand", "Bank Account"].includes(l.account_head_name));
      if (nonCash) setAccountHeadId(nonCash.account_head_id || "");
    } else {
      setDate(today);
      setAccountHeadId("");
      setAmount("");
      setNarration("");
      setSelectedIllakaId("");
    }
  }, [editEntry, open]);

  if (!open) return null;

  const incomeExpenseHeads = heads.filter(h => h.group_type === "income" || h.group_type === "expense");
  const grouped = incomeExpenseHeads.reduce((acc, h) => {
    const g = h.group_name;
    if (!acc[g]) acc[g] = [];
    acc[g].push(h);
    return acc;
  }, {});

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!accountHeadId || !amount || !narration || !effectiveIllakaId) {
      toast.error("Please fill all fields" + (!effectiveIllakaId ? " including Illaka" : ""));
      return;
    }
    setSaving(true);
    try {
            const url = editEntry
        ? `${API}/api/accounts/entries/${editEntry.id}`
        : `${API}/api/accounts/entries/expense`;
      const method = editEntry ? "PUT" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({
          date, illaka_id: effectiveIllakaId, account_head_id: accountHeadId,
          amount: parseFloat(amount), narration,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed");
      }
      toast.success(editEntry ? "Entry updated" : "Entry added");
      onSave();
      onClose();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold mb-5">
          {editEntry ? "Edit Entry" : "Add Income / Expense Entry"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {needsIllakaSelect && (
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1">Illaka</label>
              <select
                value={selectedIllakaId} onChange={e => setSelectedIllakaId(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                data-testid="entry-illaka-select"
                required
              >
                <option value="">Select Illaka...</option>
                {(eligibleIllakas || []).map(ill => (
                  <option key={ill.id} value={ill.id}>{ill.name}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Date</label>
            <input
              type="date" value={date} onChange={e => setDate(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="entry-date-input"
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Account Head</label>
            <select
              value={accountHeadId} onChange={e => setAccountHeadId(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="entry-head-select"
              required
            >
              <option value="">Select head...</option>
              {Object.entries(grouped).map(([gname, items]) => (
                <optgroup key={gname} label={gname}>
                  {items.map(h => (
                    <option key={h.id} value={h.id}>{h.name}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Amount (₹)</label>
            <input
              type="number" min="1" step="1" value={amount}
              onChange={e => setAmount(e.target.value)}
              placeholder="Enter amount"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="entry-amount-input"
              required
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Narration</label>
            <textarea
              value={narration} onChange={e => setNarration(e.target.value)}
              rows={2} placeholder="Brief description of the entry"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
              data-testid="entry-narration-input"
              required
            />
          </div>
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-60"
              data-testid="entry-save-btn">
              {saving ? "Saving..." : editEntry ? "Update" : "Save Entry"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Manage Heads Modal ─────────────────────────────────────────────────────────
function ManageHeadsModal({ open, onClose, heads, groups, onRefresh }) {
  const [newName, setNewName] = useState("");
  const [newGroupId, setNewGroupId] = useState("");
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newName.trim() || !newGroupId) { toast.error("Fill all fields"); return; }
    setSaving(true);
    try {
            const res = await fetch(`${API}/api/accounts/heads`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ name: newName.trim(), group_id: newGroupId }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      toast.success("Account head added");
      setNewName(""); setNewGroupId("");
      onRefresh();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  const handleDelete = async (headId) => {
    if (!window.confirm("Delete this account head?")) return;
    try {
            const res = await fetch(`${API}/api/accounts/heads/${headId}`, {
        method: "DELETE", credentials: "include",
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      toast.success("Account head deleted");
      onRefresh();
    } catch (err) { toast.error(err.message); }
  };

  const grouped = heads.reduce((acc, h) => {
    const g = h.group_name;
    if (!acc[g]) acc[g] = [];
    acc[g].push(h);
    return acc;
  }, {});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-2xl w-full max-w-lg mx-4 flex flex-col max-h-[85vh]">
        <div className="p-5 border-b border-border">
          <h2 className="text-lg font-bold">Manage Account Heads</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Add custom heads to any group</p>
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Add new head */}
          <form onSubmit={handleAdd} className="flex gap-2">
            <select value={newGroupId} onChange={e => setNewGroupId(e.target.value)}
              className="flex-1 rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="head-group-select">
              <option value="">Select group...</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
            <input value={newName} onChange={e => setNewName(e.target.value)}
              placeholder="Head name"
              className="flex-[2] rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="head-name-input" />
            <button type="submit" disabled={saving}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 disabled:opacity-60"
              data-testid="head-add-btn">
              <Plus size={16} />
            </button>
          </form>
          {/* Heads list by group */}
          {Object.entries(grouped).map(([gname, items]) => (
            <div key={gname}>
              <p className="text-xs font-bold text-muted-foreground uppercase tracking-wider mb-2">{gname}</p>
              <div className="space-y-1">
                {items.map(h => (
                  <div key={h.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/40">
                    <div className="flex items-center gap-2">
                      {h.is_system && <Lock size={11} className="text-amber-500" />}
                      <span className="text-sm">{h.name}</span>
                      {h.is_system && <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded-full">System</span>}
                    </div>
                    {!h.is_system && (
                      <button onClick={() => handleDelete(h.id)}
                        className="p-1 text-destructive hover:bg-destructive/10 rounded transition-colors"
                        data-testid={`delete-head-${h.id}`}>
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="p-4 border-t border-border">
          <button onClick={onClose} className="w-full py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors">
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Cash Book Tab ──────────────────────────────────────────────────────────────
function CashBook({ month, illakaId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
            const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/cashbook?${params}`, {
        credentials: "include",
      });
      setData(await res.json());
    } catch {
      toast.error("Failed to load cashbook");
    } finally {
      setLoading(false);
    }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  const ENTRY_BADGE = {
    loan_disbursement: { label: "Loan", color: "bg-blue-100 text-blue-700" },
    emi_collection: { label: "EMI", color: "bg-green-100 text-green-700" },
    expense_voucher: { label: "Voucher", color: "bg-orange-100 text-orange-700" },
    manual: { label: "Journal", color: "bg-purple-100 text-purple-700" },
  };

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const rows = data?.entries || [];

  return (
    <div>
      {/* Summary bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {[
          { label: "Opening Balance", value: data?.opening_balance, icon: BookOpen, color: "text-slate-600" },
          { label: "Total Receipts", value: data?.total_receipts, icon: ArrowUpCircle, color: "text-green-600" },
          { label: "Total Payments", value: data?.total_payments, icon: ArrowDownCircle, color: "text-red-600" },
          { label: "Closing Balance", value: data?.closing_balance, icon: IndianRupee, color: "text-primary" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-card border border-border rounded-xl p-4">
            <div className={`flex items-center gap-2 ${color} mb-1`}>
              <Icon size={15} />
              <span className="text-xs font-semibold">{label}</span>
            </div>
            <p className={`text-xl font-bold ${color}`}>{fmt(value)}</p>
          </div>
        ))}
      </div>

      {/* Cashbook table */}
      {rows.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <BookOpen size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">No cash transactions this month</p>
          <p className="text-sm mt-1">Add an expense or income entry to get started</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-sm" data-testid="cashbook-table">
            <thead>
              <tr className="bg-muted/50 border-b border-border">
                <th className="text-left px-4 py-3 font-semibold text-xs text-muted-foreground w-24">Date</th>
                <th className="text-left px-4 py-3 font-semibold text-xs text-muted-foreground">Particulars</th>
                <th className="text-left px-4 py-3 font-semibold text-xs text-muted-foreground w-24">Type</th>
                <th className="text-right px-4 py-3 font-semibold text-xs text-green-600 w-28">Receipts (Dr)</th>
                <th className="text-right px-4 py-3 font-semibold text-xs text-red-600 w-28">Payments (Cr)</th>
                <th className="text-right px-4 py-3 font-semibold text-xs text-muted-foreground w-28">Balance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => {
                const badge = ENTRY_BADGE[row.entry_type] || ENTRY_BADGE.manual;
                const isAuto = ["loan_disbursement", "emi_collection"].includes(row.entry_type);
                return (
                  <tr key={i} className="border-b border-border hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">{row.date}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {isAuto && <Zap size={11} className="text-amber-500 flex-shrink-0" />}
                        <div>
                          <p className="font-medium text-foreground leading-tight">{row.narration}</p>
                          {row.contra_account && (
                            <p className="text-xs text-muted-foreground mt-0.5">
                              Contra: {row.contra_account}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-[10px] px-2 py-1 rounded-full font-semibold ${badge.color}`}>
                        {badge.label}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-green-600">
                      {row.receipts > 0 ? fmt(row.receipts) : "—"}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-red-600">
                      {row.payments > 0 ? fmt(row.payments) : "—"}
                    </td>
                    <td className={`px-4 py-3 text-right font-bold ${row.balance >= 0 ? "text-primary" : "text-destructive"}`}>
                      {fmt(row.balance)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="bg-muted/50 border-t-2 border-border">
                <td colSpan={3} className="px-4 py-3 text-xs font-bold text-muted-foreground">CLOSING BALANCE</td>
                <td className="px-4 py-3 text-right font-bold text-green-600">{fmt(data?.total_receipts)}</td>
                <td className="px-4 py-3 text-right font-bold text-red-600">{fmt(data?.total_payments)}</td>
                <td className={`px-4 py-3 text-right font-bold text-lg ${(data?.closing_balance || 0) >= 0 ? "text-primary" : "text-destructive"}`}>
                  {fmt(data?.closing_balance)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}

// ── P&L Summary Tab ────────────────────────────────────────────────────────────
function PLSummary({ month, illakaId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
            const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/summary?${params}`, {
        credentials: "include",
      });
      setData(await res.json());
    } catch {
      toast.error("Failed to load summary");
    } finally {
      setLoading(false);
    }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const income = data?.income || [];
  const expenses = data?.expenses || [];

  return (
    <div className="space-y-5">
      {/* Net P&L Card */}
      <div className={`rounded-2xl p-5 border-2 ${(data?.net_profit || 0) >= 0 ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-muted-foreground">Net Profit / Loss</p>
            <p className={`text-3xl font-bold mt-1 ${(data?.net_profit || 0) >= 0 ? "text-green-700" : "text-red-700"}`}>
              {fmt(data?.net_profit)}
            </p>
          </div>
          <BarChart3 size={40} className={`opacity-20 ${(data?.net_profit || 0) >= 0 ? "text-green-600" : "text-red-600"}`} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Total Income</p>
            <p className="text-lg font-bold text-green-700">{fmt(data?.total_income)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Total Expense</p>
            <p className="text-lg font-bold text-red-700">{fmt(data?.total_expense)}</p>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* Income section */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-green-50 border-b border-border">
            <TrendingUp size={16} className="text-green-600" />
            <h3 className="font-bold text-green-800 text-sm">Income</h3>
            <span className="ml-auto font-bold text-green-700">{fmt(data?.total_income)}</span>
          </div>
          {income.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-8">No income entries this month</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {income.map((h, i) => (
                  <tr key={i} className="border-b border-border hover:bg-muted/30">
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{h.account_head_name}</div>
                      <div className="text-xs text-muted-foreground">{h.group_name}</div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-green-700">
                      {fmt(h.total_credit - h.total_debit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Expense section */}
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border-b border-border">
            <TrendingDown size={16} className="text-red-600" />
            <h3 className="font-bold text-red-800 text-sm">Expenses</h3>
            <span className="ml-auto font-bold text-red-700">{fmt(data?.total_expense)}</span>
          </div>
          {expenses.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground py-8">No expense entries this month</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {expenses.map((h, i) => (
                  <tr key={i} className="border-b border-border hover:bg-muted/30">
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{h.account_head_name}</div>
                      <div className="text-xs text-muted-foreground">{h.group_name}</div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-red-700">
                      {fmt(h.total_debit - h.total_credit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────
export default function AccountsModule() {
  const { user } = useAuth();
  const { selectedIllaka, eligibleIllakas } = useIllaka();
  const illakaId = selectedIllaka?.id || null;

  const today = new Date();
  const [month, setMonth] = useState(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`);
  const [activeTab, setActiveTab] = useState("cashbook");
  const [heads, setHeads] = useState([]);
  const [groups, setGroups] = useState([]);
  const [showEntryModal, setShowEntryModal] = useState(false);
  const [showHeadsModal, setShowHeadsModal] = useState(false);
  const [editEntry, setEditEntry] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const canManageHeads = user?.role === "admin";
  const canAddEntry = ["admin", "maalik", "muneem"].includes(user?.role);

  const loadHeads = useCallback(async () => {
    try {
            const [hRes, gRes] = await Promise.all([
        fetch(`${API}/api/accounts/heads`, { credentials: "include" }),
        fetch(`${API}/api/accounts/groups`, { credentials: "include" }),
      ]);
      setHeads(await hRes.json());
      setGroups(await gRes.json());
    } catch {
      // silent
    }
  }, []);

  useEffect(() => { loadHeads(); }, [loadHeads]);

  const handleSaved = () => {
    setRefreshKey(k => k + 1);
    setEditEntry(null);
  };

  const tabs = [
    { key: "cashbook", label: "Cash Book", icon: BookOpen },
    { key: "summary", label: "P&L Summary", icon: BarChart3 },
  ];

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Accounts / खाता</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {selectedIllaka ? selectedIllaka.name : "All Illakas"} • Cash Book & P&L
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <MonthNav month={month} onChange={setMonth} />
          {canManageHeads && (
            <button onClick={() => setShowHeadsModal(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="manage-heads-btn">
              <Settings size={15} />
              <span className="hidden sm:inline">Manage Heads</span>
            </button>
          )}
          {canAddEntry && (
            <button onClick={() => { setEditEntry(null); setShowEntryModal(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors shadow-sm"
              data-testid="add-entry-btn">
              <Plus size={15} />
              Add Entry
            </button>
          )}
        </div>
      </div>

      {/* Illaka warning */}
      {!illakaId && (
        <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm flex items-center gap-2">
          <RefreshCw size={14} />
          Showing data across all your accessible Illakas. Select a specific Illaka for filtered view.
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-muted rounded-xl p-1 mb-5 w-fit">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
              activeTab === key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
            data-testid={`tab-${key}`}>
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "cashbook" && (
        <CashBook month={month} illakaId={illakaId} refresh={refreshKey} />
      )}
      {activeTab === "summary" && (
        <PLSummary month={month} illakaId={illakaId} refresh={refreshKey} />
      )}

      {/* Modals */}
      <EntryModal
        open={showEntryModal}
        onClose={() => { setShowEntryModal(false); setEditEntry(null); }}
        onSave={handleSaved}
        editEntry={editEntry}
        heads={heads}
        illakaId={illakaId}
        eligibleIllakas={eligibleIllakas}
      />
      <ManageHeadsModal
        open={showHeadsModal}
        onClose={() => setShowHeadsModal(false)}
        heads={heads}
        groups={groups}
        onRefresh={loadHeads}
      />
    </div>
  );
}
