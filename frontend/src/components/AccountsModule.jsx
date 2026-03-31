import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import { toast } from "sonner";
import {
  BookOpen, TrendingUp, TrendingDown, Plus, Trash2,
  ChevronLeft, ChevronRight, Lock, Zap, Settings, RefreshCw,
  ArrowUpCircle, ArrowDownCircle, BarChart3, IndianRupee,
  FileText, Edit3, Scale, Table, Landmark,
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

// ── Opening Balance Modal ──────────────────────────────────────────────────────
function OpeningBalanceModal({ illakaId, onClose, onSaved }) {
  const [heads, setHeads] = useState([]);
  const [existing, setExisting] = useState(null);
  const [loadingHeads, setLoadingHeads] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [date, setDate] = useState(() => {
    // Default: April 1 of current fiscal year (Indian FY: Apr-Mar)
    const now = new Date();
    const fy = now.getMonth() < 3 ? now.getFullYear() - 1 : now.getFullYear();
    return `${fy}-04-01`;
  });
  const [amounts, setAmounts] = useState({});

  const typeLabel = { asset: "Assets", liability: "Liabilities", equity: "Capital & Equity" };
  const typeHint = { asset: "Debit balance", liability: "Credit balance", equity: "Credit balance" };

  useEffect(() => {
    async function load() {
      setLoadingHeads(true);
      try {
        // Load all balance-sheet account heads (exclude income/expense)
        const res = await fetch(`${API}/api/accounts/heads`, { credentials: "include" });
        const data = await res.json();
        const filtered = (data.heads || data || []).filter(
          h => ["asset", "liability", "equity"].includes(h.group_type)
            && h.is_active !== false
            && h.system_key !== "opening_capital"  // auto-calculated, not user-entered
        );
        setHeads(filtered);

        // Load existing opening balance
        const params = new URLSearchParams();
        if (illakaId) params.set("illaka_id", illakaId);
        const eRes = await fetch(`${API}/api/accounts/opening-balance?${params}`, { credentials: "include" });
        const eData = await eRes.json();
        if (eData.entry) {
          setExisting(eData.entry);
          // Pre-fill amounts from existing entry
          const prefill = {};
          for (const line of eData.entry.lines || []) {
            if (line.account_head_id) {
              prefill[line.account_head_id] = line.debit > 0 ? line.debit : line.credit > 0 ? line.credit : 0;
            }
          }
          setAmounts(prefill);
          if (eData.entry.date) setDate(eData.entry.date);
        }
      } catch { toast.error("Failed to load account heads"); }
      finally { setLoadingHeads(false); }
    }
    load();
  }, [illakaId]);

  const totalDr = heads
    .filter(h => h.group_type === "asset")
    .reduce((s, h) => s + (parseFloat(amounts[h.id] || amounts[h._id] || 0) || 0), 0);
  const totalCr = heads
    .filter(h => ["liability", "equity"].includes(h.group_type))
    .reduce((s, h) => s + (parseFloat(amounts[h.id] || amounts[h._id] || 0) || 0), 0);
  const capitalPlug = Math.round((totalDr - totalCr) * 100) / 100;

  async function handleSave() {
    if (!illakaId) { toast.error("Please select an Illaka before entering opening balance"); return; }
    setSaving(true);
    try {
      const lines = heads
        .filter(h => parseFloat(amounts[h.id || h._id] || 0) > 0)
        .map(h => {
          const hid = h.id || h._id;
          const amt = parseFloat(amounts[hid] || 0);
          return h.group_type === "asset"
            ? { account_head_id: hid, debit: amt, credit: 0 }
            : { account_head_id: hid, debit: 0, credit: amt };
        });
      if (lines.length === 0) { toast.error("Enter at least one non-zero amount"); setSaving(false); return; }
      const res = await fetch(`${API}/api/accounts/opening-balance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ illaka_id: illakaId, date, lines }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Failed to save"); return; }
      toast.success("Opening balance saved");
      onSaved();
      onClose();
    } catch { toast.error("Failed to save opening balance"); }
    finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!illakaId) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API}/api/accounts/opening-balance?illaka_id=${illakaId}`, {
        method: "DELETE", credentials: "include",
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Failed to delete"); return; }
      toast.success("Opening balance deleted");
      setExisting(null);
      setAmounts({});
      onSaved();
    } catch { toast.error("Failed to delete"); }
    finally { setDeleting(false); }
  }

  const typeOrder = ["asset", "liability", "equity"];
  const grouped = heads.reduce((acc, h) => {
    const t = h.group_type;
    if (!acc[t]) acc[t] = [];
    acc[t].push(h);
    return acc;
  }, {});

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-background rounded-2xl w-full max-w-xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Landmark className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="font-bold text-base">Opening Balance</h2>
              <p className="text-xs text-muted-foreground">Set the starting balances for your books</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xl leading-none">&times;</button>
        </div>

        {loadingHeads ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            <div className="overflow-y-auto flex-1 px-5 py-4 space-y-5">
              {/* Date */}
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide block mb-1.5">
                  As of Date
                </label>
                <input
                  type="date"
                  value={date}
                  onChange={e => setDate(e.target.value)}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background"
                  data-testid="ob-date-input"
                />
              </div>

              {/* Account head groups */}
              {typeOrder.filter(t => grouped[t]?.length).map(t => (
                <div key={t}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{typeLabel[t]}</span>
                    <span className="text-xs text-muted-foreground">({typeHint[t]})</span>
                  </div>
                  <div className="space-y-2">
                    {grouped[t].map(h => {
                      const hid = h.id || h._id;
                      return (
                        <div key={hid} className="flex items-center gap-3">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">{h.name}</p>
                            <p className="text-xs text-muted-foreground">{h.group_name}</p>
                          </div>
                          <div className="relative w-36 shrink-0">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">₹</span>
                            <input
                              type="number"
                              min="0"
                              placeholder="0"
                              value={amounts[hid] || ""}
                              onChange={e => setAmounts(a => ({ ...a, [hid]: e.target.value }))}
                              className="w-full pl-7 pr-3 py-2 border border-border rounded-lg text-sm bg-background text-right"
                              data-testid={`ob-amount-${hid}`}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* Auto-calculated opening capital */}
              <div className="rounded-xl border border-dashed border-primary/40 bg-primary/5 p-4 space-y-2">
                <p className="text-xs font-bold text-primary uppercase tracking-wide">Auto-calculated</p>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Total Assets (Dr)</span>
                  <span className="font-bold font-mono">{fmt(totalDr)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Total Liabilities &amp; Equity (Cr)</span>
                  <span className="font-bold font-mono">{fmt(totalCr)}</span>
                </div>
                <div className="border-t border-primary/20 pt-2 flex justify-between text-sm">
                  <span className="font-semibold">Opening Capital (plug)</span>
                  <span className={`font-bold font-mono ${capitalPlug < 0 ? "text-red-600" : "text-green-700"}`}>
                    {fmt(Math.abs(capitalPlug))}
                    {capitalPlug < 0 && <span className="text-xs ml-1">(Dr — unusual)</span>}
                  </span>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="px-5 py-4 border-t border-border flex items-center gap-3">
              {existing && (
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex items-center gap-2 text-sm text-red-600 hover:text-red-700 border border-red-200 rounded-lg px-3 py-2 hover:bg-red-50 transition-colors disabled:opacity-50"
                  data-testid="ob-delete-btn"
                >
                  <Trash2 className="w-4 h-4" />
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              )}
              <div className="flex-1" />
              <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors">
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !illakaId}
                className="px-5 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
                data-testid="ob-save-btn"
              >
                {saving ? "Saving…" : existing ? "Update" : "Save Opening Balance"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Trial Balance ──────────────────────────────────────────────────────────────
function TrialBalance({ month, illakaId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [y, m] = month.split("-").map(Number);
  const label = `${MONTHS[m - 1]} ${y}`;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/trial-balance?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load Trial Balance"); }
    finally { setLoading(false); }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const rows = data?.rows || [];
  const typeLabel = { asset: "Assets", liability: "Liabilities", equity: "Equity / Capital", income: "Income", expense: "Expenses" };
  const typeColor = { asset: "text-blue-700", liability: "text-orange-700", equity: "text-purple-700", income: "text-green-700", expense: "text-red-700" };
  const typeBg = { asset: "bg-blue-50/60", liability: "bg-orange-50/60", equity: "bg-purple-50/60", income: "bg-green-50/60", expense: "bg-red-50/60" };

  // Group rows by type
  const grouped = rows.reduce((acc, r) => {
    const t = r.group_type || "other";
    if (!acc[t]) acc[t] = [];
    acc[t].push(r);
    return acc;
  }, {});
  const typeOrder = ["asset", "liability", "equity", "income", "expense"];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Trial Balance</h2>
          <p className="text-sm text-muted-foreground">Cumulative as of {label}</p>
        </div>
        {data && (
          <span className={`text-xs font-bold px-3 py-1 rounded-full ${data.is_balanced ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
            {data.is_balanced ? "✓ Balanced" : "⚠ Out of Balance"}
          </span>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-12 text-xs font-bold text-muted-foreground uppercase tracking-wide px-4 py-2.5 bg-muted/50 border-b border-border">
          <div className="col-span-5">Account Head</div>
          <div className="col-span-3 text-center">Group</div>
          <div className="col-span-2 text-right">Debit</div>
          <div className="col-span-2 text-right">Credit</div>
        </div>

        {rows.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground py-10">No entries found</p>
        ) : (
          typeOrder.filter(t => grouped[t]?.length).map(t => (
            <div key={t}>
              {/* Group header */}
              <div className={`px-4 py-2 ${typeBg[t]} border-b border-border`}>
                <span className={`text-xs font-bold uppercase tracking-wide ${typeColor[t]}`}>{typeLabel[t]}</span>
              </div>
              {grouped[t].map((row, i) => (
                <div key={i} className="grid grid-cols-12 px-4 py-2.5 border-b border-border hover:bg-muted/20 text-sm">
                  <div className="col-span-5 font-medium truncate">{row.account_head_name}</div>
                  <div className="col-span-3 text-center text-xs text-muted-foreground truncate">{row.group_name}</div>
                  <div className="col-span-2 text-right text-blue-700 font-mono">
                    {row.total_debit > 0 ? fmt(row.total_debit) : "—"}
                  </div>
                  <div className="col-span-2 text-right text-red-700 font-mono">
                    {row.total_credit > 0 ? fmt(row.total_credit) : "—"}
                  </div>
                </div>
              ))}
            </div>
          ))
        )}

        {/* Totals footer */}
        {rows.length > 0 && (
          <div className="grid grid-cols-12 px-4 py-3 bg-muted/70 border-t-2 border-border font-bold text-sm">
            <div className="col-span-8">TOTAL</div>
            <div className="col-span-2 text-right text-blue-800">{fmt(data?.total_debit)}</div>
            <div className="col-span-2 text-right text-red-800">{fmt(data?.total_credit)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Balance Sheet ──────────────────────────────────────────────────────────────
function BalanceSheet({ month, illakaId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [y, m] = month.split("-").map(Number);
  const label = `${MONTHS[m - 1]} ${y}`;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/balance-sheet?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load Balance Sheet"); }
    finally { setLoading(false); }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const assets = data?.assets || [];
  const liabilities = data?.liabilities || [];
  const equityItems = data?.equity_items || [];
  const netProfit = data?.net_profit || 0;
  const openingCapital = data?.opening_capital || 0;

  function SideSection({ title, color, items, footer }) {
    return (
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className={`px-4 py-3 ${color} border-b border-border`}>
          <span className="font-bold text-sm">{title}</span>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-b border-border hover:bg-muted/20">
                <td className="px-4 py-2.5">
                  <div className="font-medium">{item.account_head_name}</div>
                  <div className="text-xs text-muted-foreground">{item.group_name}</div>
                </td>
                <td className={`px-4 py-2.5 text-right font-bold font-mono ${item.amount < 0 ? "text-red-600" : ""}`}>
                  {fmt(Math.abs(item.amount))}
                  {item.amount < 0 && <span className="text-xs ml-1">(Dr)</span>}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={2} className="px-4 py-6 text-center text-muted-foreground text-xs">Nil</td></tr>}
          </tbody>
        </table>
        {footer}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Balance Sheet</h2>
          <p className="text-sm text-muted-foreground">As of {label}</p>
        </div>
        {data && (
          <span className={`text-xs font-bold px-3 py-1 rounded-full ${data.is_balanced ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
            {data.is_balanced ? "✓ Balanced" : "✓ Balanced (with capital plug)"}
          </span>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* LEFT: Capital & Liabilities */}
        <div className="space-y-4">
          {/* Owner's Capital */}
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-purple-50 border-b border-border">
              <span className="font-bold text-sm text-purple-800">Capital & Reserves</span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {equityItems.map((e, i) => (
                  <tr key={i} className="border-b border-border hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-medium">{e.account_head_name}</td>
                    <td className="px-4 py-2.5 text-right font-bold font-mono">{fmt(e.amount)}</td>
                  </tr>
                ))}
                {openingCapital !== 0 && (
                  <tr className="border-b border-border hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-medium">
                      Opening / Owner's Capital
                      <div className="text-xs text-muted-foreground">Balancing figure</div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold font-mono">{fmt(Math.abs(openingCapital))}</td>
                  </tr>
                )}
                <tr className="border-b border-border bg-green-50/40">
                  <td className="px-4 py-2.5 font-medium">
                    {netProfit >= 0 ? "Net Profit (Current Period)" : "Net Loss (Current Period)"}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-bold font-mono ${netProfit < 0 ? "text-red-600" : "text-green-700"}`}>
                    {fmt(Math.abs(netProfit))}
                  </td>
                </tr>
              </tbody>
            </table>
            <div className="px-4 py-2.5 bg-purple-50/50 border-t border-border flex justify-between font-bold text-sm">
              <span>Total Capital</span>
              <span className="font-mono">{fmt((data?.total_equity || 0) + openingCapital + netProfit)}</span>
            </div>
          </div>

          {/* Liabilities */}
          <SideSection
            title="Liabilities"
            color="bg-orange-50"
            items={liabilities}
            footer={
              <div className="px-4 py-2.5 bg-orange-50/50 border-t border-border flex justify-between font-bold text-sm">
                <span>Total Liabilities</span>
                <span className="font-mono">{fmt(data?.total_liabilities)}</span>
              </div>
            }
          />

          <div className="px-5 py-3 bg-muted rounded-xl flex justify-between font-bold">
            <span>Total Capital &amp; Liabilities</span>
            <span className="text-lg font-mono">{fmt(data?.total_capital_side)}</span>
          </div>
        </div>

        {/* RIGHT: Assets */}
        <div className="space-y-4">
          <SideSection
            title="Assets"
            color="bg-blue-50"
            items={assets}
            footer={null}
          />
          <div className="px-5 py-3 bg-muted rounded-xl flex justify-between font-bold">
            <span>Total Assets</span>
            <span className="text-lg font-mono">{fmt(data?.total_assets)}</span>
          </div>
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
  const [showOpeningBalance, setShowOpeningBalance] = useState(false);
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
    { key: "trial", label: "Trial Balance", icon: Scale },
    { key: "balancesheet", label: "Balance Sheet", icon: Table },
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
            <button onClick={() => setShowOpeningBalance(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="opening-balance-btn">
              <Landmark size={15} />
              <span className="hidden sm:inline">Opening Balance</span>
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
      {activeTab === "trial" && <TrialBalance month={month} illakaId={illakaId} refresh={refreshKey} />}
      {activeTab === "balancesheet" && <BalanceSheet month={month} illakaId={illakaId} refresh={refreshKey} />}
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
      {showOpeningBalance && (
        <OpeningBalanceModal
          illakaId={illakaId}
          onClose={() => setShowOpeningBalance(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
