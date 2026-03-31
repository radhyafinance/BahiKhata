import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Lock } from "lucide-react";
import { API } from "./utils";

export function ManageHeadsModal({ open, onClose, heads, groups, onRefresh }) {
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
