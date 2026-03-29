import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, CheckCircle } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;

export default function FullJournalEntryModal({ open, onClose, onSave, heads, illakaId, eligibleIllakas }) {
  const today = new Date().toISOString().split("T")[0];
  const [date, setDate] = useState(today);
  const [narration, setNarration] = useState("");
  const [selectedIllakaId, setSelectedIllakaId] = useState("");
  const [lines, setLines] = useState([
    { account_head_id: "", debit: "", credit: "" },
    { account_head_id: "", debit: "", credit: "" },
  ]);
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  const effectiveIllakaId = illakaId || selectedIllakaId;
  const needsIllakaSelect = !illakaId;

  const totalDr = lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
  const totalCr = lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
  const isBalanced = Math.abs(totalDr - totalCr) < 0.01 && totalDr > 0;

  const addLine = () => setLines(l => [...l, { account_head_id: "", debit: "", credit: "" }]);
  const removeLine = (i) => setLines(l => l.filter((_, idx) => idx !== i));
  const updateLine = (i, key, val) => setLines(l => l.map((row, idx) => idx === i ? { ...row, [key]: val } : row));

  const grouped = heads.reduce((acc, h) => {
    const g = h.group_name;
    if (!acc[g]) acc[g] = [];
    acc[g].push(h);
    return acc;
  }, {});

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!effectiveIllakaId) { toast.error("Select an Illaka"); return; }
    if (!narration.trim()) { toast.error("Enter narration"); return; }
    if (!isBalanced) { toast.error(`Entry not balanced: Dr ₹${totalDr.toFixed(0)} ≠ Cr ₹${totalCr.toFixed(0)}`); return; }
    const validLines = lines.filter(l => l.account_head_id && (parseFloat(l.debit) > 0 || parseFloat(l.credit) > 0));
    if (validLines.length < 2) { toast.error("Add at least 2 lines"); return; }

    setSaving(true);
    try {
      const res = await fetch(`${API}/api/accounts/entries`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({
          date, illaka_id: effectiveIllakaId, narration,
          lines: validLines.map(l => ({
            account_head_id: l.account_head_id,
            debit: parseFloat(l.debit) || 0,
            credit: parseFloat(l.credit) || 0,
          })),
        }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Failed"); }
      toast.success("Journal entry saved");
      onSave();
      onClose();
      setLines([{ account_head_id: "", debit: "", credit: "" }, { account_head_id: "", debit: "", credit: "" }]);
      setNarration(""); setDate(today); setSelectedIllakaId("");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative bg-card rounded-2xl shadow-2xl w-full max-w-2xl mx-4 flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="p-5 border-b border-border">
          <h2 className="text-lg font-bold">Journal Entry</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Double-entry — total debits must equal total credits</p>
        </div>

        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Date + Illaka */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-muted-foreground mb-1">Date</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)}
                className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                data-testid="jv-date-input" />
            </div>
            {needsIllakaSelect ? (
              <div>
                <label className="block text-xs font-semibold text-muted-foreground mb-1">Illaka</label>
                <select value={selectedIllakaId} onChange={e => setSelectedIllakaId(e.target.value)}
                  className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                  data-testid="jv-illaka-select">
                  <option value="">Select Illaka...</option>
                  {(eligibleIllakas || []).map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
                </select>
              </div>
            ) : (
              <div className="flex items-end">
                <div className="w-full rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                  {(eligibleIllakas || []).find(i => i.id === illakaId)?.name || "Selected Illaka"}
                </div>
              </div>
            )}
          </div>

          {/* Narration */}
          <div>
            <label className="block text-xs font-semibold text-muted-foreground mb-1">Narration</label>
            <input value={narration} onChange={e => setNarration(e.target.value)}
              placeholder="Brief description of the transaction"
              className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="jv-narration-input" />
          </div>

          {/* Lines table */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-semibold text-muted-foreground">Entry Lines</label>
              <button onClick={addLine} type="button"
                className="flex items-center gap-1 text-xs text-primary font-semibold hover:underline"
                data-testid="jv-add-line-btn">
                <Plus size={13} /> Add Line
              </button>
            </div>
            <div className="rounded-xl border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/50 border-b border-border">
                    <th className="text-left px-3 py-2 text-xs font-semibold text-muted-foreground">Account Head</th>
                    <th className="text-right px-3 py-2 text-xs font-semibold text-green-600 w-28">Debit (Dr)</th>
                    <th className="text-right px-3 py-2 text-xs font-semibold text-red-600 w-28">Credit (Cr)</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, i) => (
                    <tr key={i} className="border-b border-border">
                      <td className="px-2 py-1.5">
                        <select value={line.account_head_id} onChange={e => updateLine(i, "account_head_id", e.target.value)}
                          className="w-full rounded-lg border border-border px-2 py-1 text-sm bg-background focus:outline-none focus:ring-1 focus:ring-primary/30"
                          data-testid={`jv-head-${i}`}>
                          <option value="">Select head...</option>
                          {Object.entries(grouped).map(([gname, items]) => (
                            <optgroup key={gname} label={gname}>
                              {items.map(h => <option key={h.id} value={h.id}>{h.name}</option>)}
                            </optgroup>
                          ))}
                        </select>
                      </td>
                      <td className="px-2 py-1.5">
                        <input type="number" min="0" step="1" value={line.debit}
                          onChange={e => { updateLine(i, "debit", e.target.value); if (e.target.value) updateLine(i, "credit", ""); }}
                          placeholder="0"
                          className="w-full rounded-lg border border-border px-2 py-1 text-sm bg-background text-right focus:outline-none focus:ring-1 focus:ring-green-400/50"
                          data-testid={`jv-debit-${i}`} />
                      </td>
                      <td className="px-2 py-1.5">
                        <input type="number" min="0" step="1" value={line.credit}
                          onChange={e => { updateLine(i, "credit", e.target.value); if (e.target.value) updateLine(i, "debit", ""); }}
                          placeholder="0"
                          className="w-full rounded-lg border border-border px-2 py-1 text-sm bg-background text-right focus:outline-none focus:ring-1 focus:ring-red-400/50"
                          data-testid={`jv-credit-${i}`} />
                      </td>
                      <td className="px-1">
                        {lines.length > 2 && (
                          <button onClick={() => removeLine(i)} type="button"
                            className="p-1 text-destructive hover:bg-destructive/10 rounded">
                            <Trash2 size={13} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className={`border-t-2 ${isBalanced ? "border-green-300 bg-green-50" : "border-red-200 bg-red-50"}`}>
                    <td className="px-3 py-2 text-xs font-bold">
                      {isBalanced ? (
                        <span className="flex items-center gap-1 text-green-700"><CheckCircle size={13} /> Balanced</span>
                      ) : (
                        <span className="text-red-600">Not balanced</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-green-700">₹{totalDr.toLocaleString("en-IN")}</td>
                    <td className="px-3 py-2 text-right font-bold text-red-700">₹{totalCr.toLocaleString("en-IN")}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-border flex gap-3">
          <button onClick={onClose} type="button"
            className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={saving || !isBalanced}
            className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
            data-testid="jv-save-btn">
            {saving ? "Saving..." : "Save Journal Entry"}
          </button>
        </div>
      </div>
    </div>
  );
}
