import { useState, useEffect, useCallback } from "react";
import { useAuth } from "./AuthContext";
import { toast } from "sonner";
import { Plus, Trash2, CheckCircle, Lock, FileText, Settings } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;
const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function fmt(n) {
  return `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 0 })}`;
}

// ── Template Editor (Admin only) ──────────────────────────────────────────────
function TemplateEditor({ illakaId, illakaName, expenseHeads, onSaved }) {
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const loadTemplate = useCallback(async () => {
    if (!illakaId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/accounts/expense-templates?illaka_id=${illakaId}`, { credentials: "include" });
      const data = await res.json();
      if (data.template?.fields) {
        setFields(data.template.fields.map(f => ({ ...f })));
      } else {
        setFields([]);
      }
    } catch { toast.error("Failed to load template"); }
    finally { setLoading(false); }
  }, [illakaId]);

  useEffect(() => { loadTemplate(); }, [loadTemplate]);

  const addField = () => setFields(f => [...f, { field_id: "", label: "", account_head_id: "", display_order: f.length }]);
  const removeField = (i) => setFields(f => f.filter((_, idx) => idx !== i));
  const updateField = (i, key, val) => setFields(f => f.map((row, idx) => idx === i ? { ...row, [key]: val } : row));

  const handleSave = async () => {
    const valid = fields.filter(f => f.label.trim() && f.account_head_id);
    if (valid.length === 0) { toast.error("Add at least one field"); return; }
    setSaving(true);
    try {
      const res = await fetch(`${API}/api/accounts/expense-templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({
          illaka_id: illakaId,
          fields: valid.map((f, i) => ({
            field_id: f.field_id || undefined,
            label: f.label.trim(),
            account_head_id: f.account_head_id,
            display_order: i,
          })),
        }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      toast.success("Template saved for " + illakaName);
      await loadTemplate();
      if (onSaved) onSaved();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  if (loading) return <div className="py-8 text-center text-sm text-muted-foreground">Loading template...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-bold text-sm">Expense Fields for {illakaName}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Define what Muneems fill each month. Each field maps to an account head.</p>
        </div>
        <button onClick={addField}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:bg-primary/90"
          data-testid="add-template-field-btn">
          <Plus size={13} /> Add Field
        </button>
      </div>

      {fields.length === 0 ? (
        <div className="text-center py-10 border-2 border-dashed border-border rounded-xl text-muted-foreground">
          <FileText size={32} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">No fields yet. Click "Add Field" to start.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {fields.map((field, i) => (
            // key={i} intentional: ordered form rows with no external stable ID
            <div key={i} className="flex items-center gap-2 p-3 bg-muted/30 rounded-xl border border-border">
              <span className="text-xs text-muted-foreground w-5 text-center font-mono">{i + 1}</span>
              <input value={field.label} onChange={e => updateField(i, "label", e.target.value)}
                placeholder="Field label (e.g. Salary Nitin)"
                className="flex-[2] rounded-lg border border-border px-3 py-1.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                data-testid={`template-field-label-${i}`} />
              <select value={field.account_head_id} onChange={e => updateField(i, "account_head_id", e.target.value)}
                className="flex-[3] rounded-lg border border-border px-3 py-1.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
                data-testid={`template-field-head-${i}`}>
                <option value="">Map to account head...</option>
                {expenseHeads.map(h => (
                  <option key={h.id} value={h.id}>{h.name} ({h.group_name})</option>
                ))}
              </select>
              <button onClick={() => removeField(i)}
                className="p-1.5 text-destructive hover:bg-destructive/10 rounded-lg transition-colors">
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <button onClick={handleSave} disabled={saving}
        className="w-full py-2.5 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 disabled:opacity-60 transition-colors"
        data-testid="save-template-btn">
        {saving ? "Saving..." : "Save Template"}
      </button>
    </div>
  );
}

// ── Monthly Expense Form (Muneem fills) ────────────────────────────────────────
function MonthlyExpenseForm({ illakaId, illakaName, month, onSubmitted }) {
  const { user } = useAuth();
  const [template, setTemplate] = useState(null);
  const [submission, setSubmission] = useState(null);
  const [amounts, setAmounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [unlocking, setUnlocking] = useState(false);

  const [y, m] = month.split("-").map(Number);
  const monthLabel = `${MONTHS[m - 1]} ${y}`;

  const load = useCallback(async () => {
    if (!illakaId) return;
    setLoading(true);
    try {
      const [tRes, sRes] = await Promise.all([
        fetch(`${API}/api/accounts/expense-templates?illaka_id=${illakaId}`, { credentials: "include" }),
        fetch(`${API}/api/accounts/expense-submissions?illaka_id=${illakaId}&month=${month}`, { credentials: "include" }),
      ]);
      const tData = await tRes.json();
      const sData = await sRes.json();
      setTemplate(tData.template || null);
      setSubmission(sData.submission || null);
      // Pre-fill amounts from draft or submission
      if (sData.submission?.entries) {
        const a = {};
        for (const e of sData.submission.entries) {
          a[e.field_id] = e.amount.toString();
        }
        setAmounts(a);
      } else if (tData.template?.fields) {
        const a = {};
        for (const f of tData.template.fields) { a[f.field_id] = ""; }
        setAmounts(a);
      }
    } catch { toast.error("Failed to load expense form"); }
    finally { setLoading(false); }
  }, [illakaId, month]);

  useEffect(() => { load(); }, [load]);

  const handleSaveDraft = async () => {
    if (!template) return;
    setSaving(true);
    try {
      const entries = template.fields.map(f => ({
        field_id: f.field_id,
        amount: parseFloat(amounts[f.field_id]) || 0,
      }));
      const res = await fetch(`${API}/api/accounts/expense-submissions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ illaka_id: illakaId, month, entries, action: "draft" }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      toast.success("Draft saved");
      await load();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  const handleSubmit = async () => {
    if (!template) return;
    setSaving(true);
    setShowConfirm(false);
    try {
      const entries = template.fields.map(f => ({
        field_id: f.field_id,
        amount: parseFloat(amounts[f.field_id]) || 0,
      }));
      const res = await fetch(`${API}/api/accounts/expense-submissions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify({ illaka_id: illakaId, month, entries, action: "submit" }),
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      toast.success(`Expense sheet for ${monthLabel} submitted!`);
      await load();
      if (onSubmitted) onSubmitted();
    } catch (err) { toast.error(err.message); }
    finally { setSaving(false); }
  };

  const handleUnlock = async () => {
    if (!submission?.id) return;
    if (!window.confirm("Unlock this expense sheet? The submitted journal entry will be removed and Muneem can re-edit.")) return;
    setUnlocking(true);
    try {
      const res = await fetch(`${API}/api/accounts/expense-submissions/${submission.id}/unlock`, {
        method: "PATCH", credentials: "include",
      });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
      toast.success("Expense sheet unlocked. Muneem can now re-edit and re-submit.");
      await load();
    } catch (err) { toast.error(err.message); }
    finally { setUnlocking(false); }
  };

  const totalAmount = template?.fields?.reduce((s, f) => s + (parseFloat(amounts[f.field_id]) || 0), 0) || 0;
  const isSubmitted = submission?.status === "submitted";

  if (loading) return <div className="py-12 text-center text-sm text-muted-foreground">Loading expense form...</div>;
  if (!template) return (
    <div className="text-center py-16 text-muted-foreground">
      <FileText size={40} className="mx-auto mb-3 opacity-30" />
      <p className="font-medium">No expense template for this Illaka</p>
      <p className="text-sm mt-1">Ask Admin to set up the expense fields for {illakaName || "this Illaka"}</p>
    </div>
  );

  return (
    <div className="max-w-lg">
      {/* Status bar */}
      {isSubmitted && (
        <div className="mb-4 flex items-center justify-between p-3 rounded-xl bg-green-50 border border-green-200 text-green-800 text-sm">
          <div className="flex items-center gap-2 min-w-0">
            <Lock size={14} className="flex-shrink-0" />
            <span className="truncate">Submitted on {submission.submitted_at?.slice(0, 10)} by {submission.submitted_by_name}.</span>
          </div>
          {(user?.role === "admin" || user?.role === "maalik") && (
            <button onClick={handleUnlock} disabled={unlocking}
              className="ml-3 px-3 py-1.5 bg-amber-600 text-white rounded-lg text-xs font-semibold hover:bg-amber-700 disabled:opacity-60 transition-colors flex-shrink-0"
              data-testid="unlock-expense-btn">
              {unlocking ? "Unlocking..." : "Unlock"}
            </button>
          )}
        </div>
      )}
      {submission?.status === "draft" && (
        <div className="mb-4 flex items-center gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <FileText size={14} />
          Draft saved. Fill all fields and submit.
        </div>
      )}

      {/* Month header */}
      <div className="mb-5 flex items-center justify-between">
        <div>
          <h3 className="font-bold text-base">Monthly Expense — {monthLabel}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{illakaName} • {template.fields.length} fields</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Total</p>
          <p className="text-xl font-bold text-primary">{fmt(totalAmount)}</p>
        </div>
      </div>

      {/* Fields */}
      <div className="space-y-3 mb-5">
        {template.fields.map((field) => (
          <div key={field.field_id}
            className="flex items-center justify-between gap-4 p-3 bg-muted/30 rounded-xl border border-border">
            <div className="flex-1">
              <p className="text-sm font-semibold">{field.label}</p>
              <p className="text-xs text-muted-foreground">{field.account_head_name}</p>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-sm text-muted-foreground">₹</span>
              <input
                type="number" min="0" step="1"
                value={amounts[field.field_id] || ""}
                onChange={e => setAmounts(a => ({ ...a, [field.field_id]: e.target.value }))}
                disabled={isSubmitted}
                placeholder="0"
                className="w-28 rounded-lg border border-border px-3 py-2 text-sm text-right bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-60 disabled:cursor-not-allowed font-semibold"
                data-testid={`expense-field-${field.field_id}`}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Total row */}
      <div className="flex items-center justify-between px-3 py-3 bg-primary/5 rounded-xl border border-primary/20 mb-5">
        <span className="font-bold text-sm">Total Expense</span>
        <span className="text-xl font-bold text-primary">{fmt(totalAmount)}</span>
      </div>

      {/* Actions */}
      {!isSubmitted && (
        <div className="flex gap-3">
          <button onClick={handleSaveDraft} disabled={saving}
            className="flex-1 py-2.5 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors disabled:opacity-60"
            data-testid="save-draft-btn">
            {saving ? "Saving..." : "Save Draft"}
          </button>
          <button onClick={() => setShowConfirm(true)} disabled={saving || totalAmount === 0}
            className="flex-1 py-2.5 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors disabled:opacity-60"
            data-testid="submit-expense-btn">
            Submit for {monthLabel}
          </button>
        </div>
      )}

      {/* Confirm dialog */}
      {showConfirm && (
        <div className="fixed inset-0 z-60 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowConfirm(false)} />
          <div className="relative bg-card rounded-2xl p-6 w-80 shadow-2xl text-center">
            <CheckCircle size={40} className="text-primary mx-auto mb-3" />
            <h3 className="font-bold text-base mb-1">Confirm Submission</h3>
            <p className="text-sm text-muted-foreground mb-4">
              Submit expense sheet for <strong>{monthLabel}</strong>?<br />
              Total: <strong>{fmt(totalAmount)}</strong><br />
              This cannot be undone.
            </p>
            <div className="flex gap-2">
              <button onClick={() => setShowConfirm(false)}
                className="flex-1 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted">
                Cancel
              </button>
              <button onClick={handleSubmit} disabled={saving}
                className="flex-1 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 disabled:opacity-60"
                data-testid="confirm-submit-btn">
                {saving ? "Submitting..." : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Export ────────────────────────────────────────────────────────────────
export default function ExpenseSheet({ illakaId, illakaName, month, eligibleIllakas }) {
  const { user } = useAuth();
  const [activeIllakaId, setActiveIllakaId] = useState(illakaId || "");
  const [activeIllakaName, setActiveIllakaName] = useState(illakaName || "");
  const [adminView, setAdminView] = useState("form"); // "form" | "template"
  const [refreshKey, setRefreshKey] = useState(0);

  const isAdmin = user?.role === "admin";
  const isMuneem = user?.role === "muneem";

  // Expense-type account heads only
  const [expenseHeads, setExpenseHeads] = useState([]);
  useEffect(() => {
    fetch(`${API}/api/accounts/heads?group_type=expense`, { credentials: "include" })
      .then(r => r.json()).then(data => setExpenseHeads(Array.isArray(data) ? data : []));
  }, []);

  const handleIllakaChange = (id) => {
    const ill = (eligibleIllakas || []).find(i => i.id === id);
    setActiveIllakaId(id);
    setActiveIllakaName(ill?.name || "");
  };

  const showIllakaSelect = !illakaId || isAdmin;

  return (
    <div>
      {/* Illaka selector for admin or when no illaka chosen */}
      <div className="flex items-center justify-between gap-4 mb-5 flex-wrap">
        {showIllakaSelect && (
          <div className="flex items-center gap-3">
            <label className="text-sm font-semibold whitespace-nowrap">Illaka:</label>
            <select value={activeIllakaId} onChange={e => handleIllakaChange(e.target.value)}
              className="rounded-xl border border-border px-3 py-2 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              data-testid="expense-illaka-select">
              <option value="">Select Illaka...</option>
              {(eligibleIllakas || []).filter(i => i.id !== "all").map(i => (
                <option key={i.id} value={i.id}>{i.name}</option>
              ))}
            </select>
          </div>
        )}
        {isAdmin && activeIllakaId && (
          <div className="flex items-center gap-2 bg-muted rounded-xl p-1">
            <button onClick={() => setAdminView("form")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all ${adminView === "form" ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              data-testid="expense-view-form">
              <FileText size={14} /> Monthly Form
            </button>
            <button onClick={() => setAdminView("template")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold transition-all ${adminView === "template" ? "bg-card shadow-sm text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              data-testid="expense-view-template">
              <Settings size={14} /> Manage Fields
            </button>
          </div>
        )}
      </div>

      {!activeIllakaId ? (
        <div className="text-center py-16 text-muted-foreground">
          <FileText size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">Select an Illaka to view the expense sheet</p>
        </div>
      ) : isAdmin && adminView === "template" ? (
        <TemplateEditor
          illakaId={activeIllakaId}
          illakaName={activeIllakaName}
          expenseHeads={expenseHeads}
          onSaved={() => setRefreshKey(k => k + 1)}
        />
      ) : (
        <MonthlyExpenseForm
          key={`${activeIllakaId}-${month}-${refreshKey}`}
          illakaId={activeIllakaId}
          illakaName={activeIllakaName}
          month={month}
          onSubmitted={() => setRefreshKey(k => k + 1)}
        />
      )}
    </div>
  );
}
