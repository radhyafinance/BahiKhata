import { useState, useEffect } from "react";
import { toast } from "sonner";
import { API } from "./utils";

export function SimpleEntryModal({ open, onClose, onSave, heads, illakaId, eligibleIllakas, editEntry }) {
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
