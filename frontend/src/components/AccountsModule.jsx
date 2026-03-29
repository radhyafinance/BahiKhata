import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import { toast } from "sonner";
import {
  BookOpen, TrendingUp, TrendingDown, Plus, Trash2,
  ChevronLeft, ChevronRight, Lock, Zap, Settings, RefreshCw,
  ArrowUpCircle, ArrowDownCircle, BarChart3, IndianRupee,
  FileText, Edit3,
} from "lucide-react";
import FullJournalEntryModal from "./FullJournalEntryModal";
import ExpenseSheet from "./ExpenseSheet";

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

// ── Simple Entry Modal (Muneem / quick entry) ─────────────────────────────────
function SimpleEntryModal({ open, onClose, onSave, heads, illakaId, eligibleIllakas, editEntry }) {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [accountHeadId, setAccountHeadId] = useState("");
  const [amount, setAmount] = useState("");
  const [narration, setNarration] = useState("");
  const [selectedIllakaId, setSelectedIllakaId] = useState("");
  const [saving, setSaving] = useState(false);

  const isEditMode = !!editEntry?.id;
  const effectiveIllakaId = (isEditMode ? editEntry.illaka_id : null) || illakaId || selectedIllakaId;
  const needsIllakaSelect = !illakaId && !isEditMode;

  useEffect(() => {
    if (open && editEntry?.id) {
      setDate(editEntry.date || today);
      setAccountHeadId(editEntry.account_head_id || "");
      setAmount(editEntry.amount?.toString() || "");
      setNarration(editEntry.narration || "");
    } else if (!open) {
      setDate(today);
      setAccountHeadId(""); setAmount(""); setNarration(""); setSelectedIllakaId("");
    }
  }, [open, editEntry]);

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
      const url = isEditMode
        ? `${API}/api/accounts/entries/${editEntry.id}`
        : `${API}/api/accounts/entries/expense`;
      const res = await fetch(url, {
        method: isEditMode ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ date, illaka_id: effectiveIllakaId, account_head_id: accountHeadId, amount: parseFloat(amount), narration }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed"); }
      toast.success(isEditMode ? "Entry updated" : "Entry added");
      onSave();
      onClose();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold mb-5">{isEditMode ? "Edit Entry" : "Quick Income / Expense Entry"}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          {needsIllakaSelect && (
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1">Illaka</label>
              <select value={selectedIllakaId} onChange={e => setSelectedIllakaId(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                data-testid="entry-illaka-select" required>
                <option value="">Select Illaka...</option>
                {(eligibleIllakas || []).map(ill => <option key={ill.id} value={ill.id}>{ill.name}</option>)}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Date</label>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="entry-date-input" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Account Head</label>
            <select value={accountHeadId} onChange={e => setAccountHeadId(e.target.value)}
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="entry-head-select" required>
              <option value="">Select head...</option>
              {Object.entries(grouped).map(([gname, items]) => (
                <optgroup key={gname} label={gname}>
                  {items.map(h => <option key={h.id} value={h.id}>{h.name}</option>)}
                </optgroup>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Amount (₹)</label>
            <input type="number" min="1" step="1" value={amount} onChange={e => setAmount(e.target.value)}
              placeholder="Enter amount"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="entry-amount-input" required />
          </div>
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Narration</label>
            <textarea value={narration} onChange={e => setNarration(e.target.value)} rows={2}
              placeholder="Brief description"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
              data-testid="entry-narration-input" required />
          </div>
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors">
              Cancel
            </button>
            <button type="submit" disabled={saving}
              className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-60"
              data-testid="entry-save-btn">
              {saving ? "Saving..." : isEditMode ? "Update Entry" : "Save Entry"}
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
      const res = await fetch(`${API}/api/accounts/heads/${headId}`, { method: "DELETE", credentials: "include" });
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
        </div>
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          <form onSubmit={handleAdd} className="flex gap-2">
            <select value={newGroupId} onChange={e => setNewGroupId(e.target.value)}
              className="flex-1 rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none"
              data-testid="head-group-select">
              <option value="">Group...</option>
              {groups.map(g => <option key={g.id} value={g.id}>{g.name}</option>)}
            </select>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Head name"
              className="flex-[2] rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none"
              data-testid="head-name-input" />
            <button type="submit" disabled={saving}
              className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:bg-primary/90 disabled:opacity-60"
              data-testid="head-add-btn">
              <Plus size={16} />
            </button>
          </form>
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
          <button onClick={onClose} className="w-full py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-muted">Close</button>
        </div>
      </div>
    </div>
  );
}

// ── Two-Column Cash Book ───────────────────────────────────────────────────────
function CashBook({ month, illakaId, refresh, user, onDelete, onEdit }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const canAct = user?.role === "admin" || user?.role === "maalik";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/cashbook?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load cashbook"); }
    finally { setLoading(false); }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const drSections = data?.dr_sections || [];
  const crEntries = data?.cr_entries || [];

  return (
    <div>
      {/* Summary */}
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

      {/* Two-column cashbook */}
      {drSections.length === 0 && crEntries.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <BookOpen size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">No cash transactions this month</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-border rounded-xl overflow-hidden">
          {/* LEFT: Dr / Receipts */}
          <div className="border-b lg:border-b-0 lg:border-r border-border">
            <div className="bg-green-50 dark:bg-green-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <ArrowUpCircle size={15} className="text-green-600" />
                <span className="font-bold text-sm text-green-800 dark:text-green-300">Dr — Receipts</span>
              </div>
              <span className="font-bold text-green-700 dark:text-green-400">{fmt(data?.total_receipts)}</span>
            </div>

            <div className="divide-y divide-border">
              {drSections.map((section, idx) => {
                if (section.type === "emi_group") {
                  return (
                    <div key={idx} className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <Zap size={13} className="text-amber-500" />
                          <span className="text-sm font-bold">EMI Collections</span>
                        </div>
                        <span className="text-sm font-bold text-green-700">{fmt(section.total)}</span>
                      </div>
                      {section.misals?.map((misal, mi) => (
                        <div key={mi} className="ml-4 mb-2">
                          <div className="flex items-center justify-between py-1">
                            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                              {misal.misal_name}
                            </span>
                            <span className="text-xs font-bold text-green-600">{fmt(misal.total)}</span>
                          </div>
                          {misal.entries?.map((e, ei) => (
                            <div key={ei} className="flex items-center justify-between py-0.5 ml-2">
                              <span className="text-xs text-muted-foreground truncate max-w-[160px]">
                                {e.client_name || e.narration}
                              </span>
                              <div className="flex items-center gap-1">
                                <span className="text-xs font-medium">{fmt(e.amount)}</span>
                                {canAct && (
                                  <button onClick={() => onDelete(e.entry_id)}
                                    className="p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                                    title="Delete EMI entry" data-testid={`delete-emi-${e.entry_id}`}>
                                    <Trash2 size={11} />
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  );
                }
                return (
                  <div key={idx} className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{section.narration}</p>
                      <p className="text-xs text-muted-foreground">{section.date}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-2">
                      <span className="text-sm font-bold text-green-700">{fmt(section.amount)}</span>
                      {canAct && (
                        <div className="flex gap-0.5">
                          {section.entry_type === "expense_voucher" && (
                            <button onClick={() => onEdit(section.entry_id)}
                              className="p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded transition-colors"
                              title="Edit entry" data-testid={`edit-entry-${section.entry_id}`}>
                              <Edit3 size={12} />
                            </button>
                          )}
                          <button onClick={() => onDelete(section.entry_id)}
                            className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                            title="Delete entry" data-testid={`delete-entry-${section.entry_id}`}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {drSections.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">No receipts</div>
              )}
            </div>

            <div className="px-4 py-3 bg-green-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL RECEIPTS</span>
              <span className="font-bold text-green-700">{fmt(data?.total_receipts)}</span>
            </div>
          </div>

          {/* RIGHT: Cr / Payments */}
          <div>
            <div className="bg-red-50 dark:bg-red-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <ArrowDownCircle size={15} className="text-red-600" />
                <span className="font-bold text-sm text-red-800 dark:text-red-300">Cr — Payments</span>
              </div>
              <span className="font-bold text-red-700 dark:text-red-400">{fmt(data?.total_payments)}</span>
            </div>

            <div className="divide-y divide-border">
              {crEntries.map((e, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-2.5">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{e.narration}</p>
                    <p className="text-xs text-muted-foreground">{e.date} · {e.contra_account}</p>
                  </div>
                  <div className="flex items-center gap-2 ml-2">
                    <span className="text-sm font-bold text-red-700">{fmt(e.amount)}</span>
                    {canAct && (
                      <div className="flex gap-0.5">
                        {e.entry_type === "expense_voucher" && (
                          <button onClick={() => onEdit(e.entry_id)}
                            className="p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded transition-colors"
                            title="Edit entry" data-testid={`edit-entry-${e.entry_id}`}>
                            <Edit3 size={12} />
                          </button>
                        )}
                        <button onClick={() => onDelete(e.entry_id)}
                          className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                          title="Delete entry" data-testid={`delete-entry-${e.entry_id}`}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {crEntries.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">No payments</div>
              )}
            </div>

            <div className="px-4 py-3 bg-red-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL PAYMENTS</span>
              <span className="font-bold text-red-700">{fmt(data?.total_payments)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Closing balance bar */}
      {(drSections.length > 0 || crEntries.length > 0) && (
        <div className={`mt-3 flex items-center justify-between px-5 py-3 rounded-xl border-2 ${(data?.closing_balance || 0) >= 0 ? "border-primary/30 bg-primary/5" : "border-destructive/30 bg-destructive/5"}`}>
          <span className="font-bold text-sm">Closing Balance</span>
          <span className={`text-xl font-bold ${(data?.closing_balance || 0) >= 0 ? "text-primary" : "text-destructive"}`}>
            {fmt(data?.closing_balance)}
          </span>
        </div>
      )}
    </div>
  );
}

// ── Bid (Monthly Aggregate) ────────────────────────────────────────────────────
function Bid({ month, illakaId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/bid?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load Bid"); }
    finally { setLoading(false); }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const drTotals = data?.dr_totals || [];
  const crTotals = data?.cr_totals || [];
  const isEmpty = drTotals.length === 0 && crTotals.length === 0;

  return (
    <div>
      {/* Header summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {[
          { label: "Opening Balance", value: data?.opening_balance, color: "text-slate-600", icon: BookOpen },
          { label: "Total Receipts", value: data?.total_dr, color: "text-green-600", icon: ArrowUpCircle },
          { label: "Total Payments", value: data?.total_cr, color: "text-red-600", icon: ArrowDownCircle },
          { label: "Closing Balance", value: data?.closing_balance, color: (data?.closing_balance || 0) >= 0 ? "text-primary" : "text-destructive", icon: IndianRupee },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="bg-card border border-border rounded-xl p-4">
            <div className={`flex items-center gap-2 ${color} mb-1`}>
              <Icon size={15} />
              <span className="text-xs font-semibold">{label}</span>
            </div>
            <p className={`text-xl font-bold ${color}`}>{fmt(value)}</p>
          </div>
        ))}
      </div>

      {isEmpty ? (
        <div className="text-center py-16 text-muted-foreground">
          <BarChart3 size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">No transactions this month</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-border rounded-xl overflow-hidden">
          {/* LEFT: Dr totals */}
          <div className="border-b lg:border-b-0 lg:border-r border-border">
            <div className="bg-green-50 dark:bg-green-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <TrendingUp size={15} className="text-green-600" />
                <span className="font-bold text-sm text-green-800">Dr — Receipts (Total)</span>
              </div>
              <span className="font-bold text-green-700">{fmt(data?.total_dr)}</span>
            </div>
            <div className="divide-y divide-border">
              {drTotals.map((item, i) => (
                <div key={i} className="p-4">
                  {item.type === "emi_total" ? (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <Zap size={13} className="text-amber-500" />
                          <span className="font-bold text-sm">EMI Collections</span>
                        </div>
                        <span className="font-bold text-green-700">{fmt(item.total)}</span>
                      </div>
                      {item.misal_breakdown?.map((mb, mi) => (
                        <div key={mi} className="flex items-center justify-between ml-5 py-0.5">
                          <span className="text-xs text-muted-foreground">{mb.misal_name}</span>
                          <span className="text-xs font-semibold text-green-600">{fmt(mb.total)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span className="font-bold text-green-700">{fmt(item.total)}</span>
                    </div>
                  )}
                </div>
              ))}
              {drTotals.length === 0 && <div className="px-4 py-8 text-center text-sm text-muted-foreground">No receipts</div>}
            </div>
            <div className="px-4 py-3 bg-green-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL</span>
              <span className="font-bold text-green-700">{fmt(data?.total_dr)}</span>
            </div>
          </div>

          {/* RIGHT: Cr totals */}
          <div>
            <div className="bg-red-50 dark:bg-red-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <TrendingDown size={15} className="text-red-600" />
                <span className="font-bold text-sm text-red-800">Cr — Payments (Total)</span>
              </div>
              <span className="font-bold text-red-700">{fmt(data?.total_cr)}</span>
            </div>
            <div className="divide-y divide-border">
              {crTotals.map((item, i) => (
                <div key={i} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{item.account_head_name}</p>
                    <p className="text-xs text-muted-foreground">{item.group_name}</p>
                  </div>
                  <span className="font-bold text-red-700">{fmt(item.total)}</span>
                </div>
              ))}
              {crTotals.length === 0 && <div className="px-4 py-8 text-center text-sm text-muted-foreground">No payments</div>}
            </div>
            <div className="px-4 py-3 bg-red-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL</span>
              <span className="font-bold text-red-700">{fmt(data?.total_cr)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Closing balance */}
      {!isEmpty && (
        <div className={`mt-3 flex items-center justify-between px-5 py-3 rounded-xl border-2 ${(data?.closing_balance || 0) >= 0 ? "border-primary/30 bg-primary/5" : "border-destructive/30 bg-destructive/5"}`}>
          <span className="font-bold text-sm">Closing Balance</span>
          <span className={`text-xl font-bold ${(data?.closing_balance || 0) >= 0 ? "text-primary" : "text-destructive"}`}>
            {fmt(data?.closing_balance)}
          </span>
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
      const res = await fetch(`${API}/api/accounts/summary?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load summary"); }
    finally { setLoading(false); }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const income = data?.income || [];
  const expenses = data?.expenses || [];

  return (
    <div className="space-y-5">
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
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-green-50 border-b border-border">
            <TrendingUp size={16} className="text-green-600" />
            <h3 className="font-bold text-green-800 text-sm">Income</h3>
            <span className="ml-auto font-bold text-green-700">{fmt(data?.total_income)}</span>
          </div>
          {income.length === 0 ? <p className="text-center text-sm text-muted-foreground py-8">No income entries</p> : (
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
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border-b border-border">
            <TrendingDown size={16} className="text-red-600" />
            <h3 className="font-bold text-red-800 text-sm">Expenses</h3>
            <span className="ml-auto font-bold text-red-700">{fmt(data?.total_expense)}</span>
          </div>
          {expenses.length === 0 ? <p className="text-center text-sm text-muted-foreground py-8">No expense entries</p> : (
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
  const illakaId = selectedIllaka?.id && selectedIllaka.id !== "all" ? selectedIllaka.id : null;

  const today = new Date();
  const [month, setMonth] = useState(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`);
  const [activeTab, setActiveTab] = useState("cashbook");
  const [heads, setHeads] = useState([]);
  const [groups, setGroups] = useState([]);
  const [showSimpleEntry, setShowSimpleEntry] = useState(false);
  const [showJournalEntry, setShowJournalEntry] = useState(false);
  const [showHeadsModal, setShowHeadsModal] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editEntry, setEditEntry] = useState(null);

  const isAdmin = user?.role === "admin";
  const isMaalik = user?.role === "maalik";
  const isMuneem = user?.role === "muneem";
  const canFullEntry = isAdmin || isMaalik;

  const loadHeads = useCallback(async () => {
    try {
      const [hRes, gRes] = await Promise.all([
        fetch(`${API}/api/accounts/heads`, { credentials: "include" }),
        fetch(`${API}/api/accounts/groups`, { credentials: "include" }),
      ]);
      setHeads(await hRes.json());
      setGroups(await gRes.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => { loadHeads(); }, [loadHeads]);

  const handleSaved = () => { setRefreshKey(k => k + 1); };

  const handleDeleteEntry = useCallback(async (entryId) => {
    if (!window.confirm("Delete this journal entry? This cannot be undone.")) return;
    try {
      const res = await fetch(`${API}/api/accounts/entries/${entryId}`, {
        method: "DELETE", credentials: "include",
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      toast.success("Entry deleted");
      setRefreshKey(k => k + 1);
    } catch (err) { toast.error(err.message); }
  }, []);

  const handleEditEntry = useCallback(async (entryId) => {
    try {
      const res = await fetch(`${API}/api/accounts/entries/${entryId}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load entry");
      const entry = await res.json();
      const nonCashLine = entry.lines?.find(l => l.group_type === "expense" || l.group_type === "income");
      if (!nonCashLine) { toast.error("Cannot edit this entry type. Delete and recreate using Journal Entry."); return; }
      setEditEntry({
        id: entryId,
        date: entry.date,
        narration: entry.narration,
        amount: nonCashLine.debit > 0 ? nonCashLine.debit : nonCashLine.credit,
        account_head_id: nonCashLine.account_head_id,
        illaka_id: entry.illaka_id,
      });
    } catch (err) { toast.error("Could not load entry for editing"); }
  }, []);

  const tabs = [
    { key: "cashbook", label: "Cash Book", icon: BookOpen },
    { key: "bid", label: "Bid", icon: BarChart3 },
    { key: "summary", label: "P&L Summary", icon: TrendingUp },
    { key: "expense", label: "Expense Sheet", icon: FileText },
  ];

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">Accounts / खाता</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {selectedIllaka ? selectedIllaka.name : "All Illakas"} · Cash Book & P&L
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <MonthNav month={month} onChange={setMonth} />
          {isAdmin && (
            <button onClick={() => setShowHeadsModal(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="manage-heads-btn">
              <Settings size={15} />
              <span className="hidden sm:inline">Heads</span>
            </button>
          )}
          {canFullEntry && (
            <button onClick={() => setShowJournalEntry(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="journal-entry-btn">
              <Edit3 size={15} />
              <span className="hidden sm:inline">Journal Entry</span>
            </button>
          )}
          <button onClick={() => setShowSimpleEntry(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors shadow-sm"
            data-testid="add-entry-btn">
            <Plus size={15} />
            Add Entry
          </button>
        </div>
      </div>

      {/* Illaka warning */}
      {!illakaId && activeTab !== "expense" && (
        <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm flex items-center gap-2">
          <RefreshCw size={14} />
          Showing data across all accessible Illakas. Select a specific Illaka for filtered view.
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-muted rounded-xl p-1 mb-5 w-fit overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all whitespace-nowrap ${
              activeTab === key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
            data-testid={`tab-${key}`}>
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "cashbook" && <CashBook month={month} illakaId={illakaId} refresh={refreshKey} user={user} onDelete={handleDeleteEntry} onEdit={handleEditEntry} />}
      {activeTab === "bid" && <Bid month={month} illakaId={illakaId} refresh={refreshKey} />}
      {activeTab === "summary" && <PLSummary month={month} illakaId={illakaId} refresh={refreshKey} />}
      {activeTab === "expense" && (
        <ExpenseSheet
          illakaId={illakaId}
          illakaName={selectedIllaka?.name}
          month={month}
          eligibleIllakas={(eligibleIllakas || []).filter(i => i.id !== "all")}
        />
      )}

      {/* Modals */}
      <SimpleEntryModal
        open={showSimpleEntry || !!editEntry}
        onClose={() => { setShowSimpleEntry(false); setEditEntry(null); }}
        onSave={handleSaved}
        heads={heads}
        illakaId={illakaId}
        eligibleIllakas={(eligibleIllakas || []).filter(i => i.id !== "all")}
        editEntry={editEntry}
      />
      <FullJournalEntryModal
        open={showJournalEntry}
        onClose={() => setShowJournalEntry(false)}
        onSave={handleSaved}
        heads={heads}
        illakaId={illakaId}
        eligibleIllakas={(eligibleIllakas || []).filter(i => i.id !== "all")}
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
