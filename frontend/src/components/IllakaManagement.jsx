import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import { Plus, Edit, Trash2, ChevronDown, ChevronRight, MapPin, Home, X, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function IllakaModal({ illaka, maaliks, onClose, onSave }) {
  const { user } = useAuth();
  const [form, setForm] = useState({ name: illaka?.name || "", description: illaka?.description || "", maalik_id: illaka?.maalik_id || "" });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (illaka) {
        const res = await axios.put(`${API}/illakas/${illaka.id}`, form, { withCredentials: true });
        onSave(res.data, false);
        toast.success("Illaka updated");
      } else {
        const res = await axios.post(`${API}/illakas`, form, { withCredentials: true });
        onSave(res.data, true);
        toast.success("Illaka created");
      }
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="illaka-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-md border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h2 className="font-bold text-lg font-['Outfit']">{illaka ? "Edit Illaka" : "New Illaka"}</h2>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="bk-label"><span className="bk-label-en">Illaka Name *</span><span className="bk-label-hi">इलाके का नाम</span></label>
            <input type="text" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} className="bk-input" required data-testid="illaka-name-input" />
          </div>
          <div>
            <label className="bk-label"><span className="bk-label-en">Description</span><span className="bk-label-hi">विवरण</span></label>
            <input type="text" value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} className="bk-input" placeholder="Optional" />
          </div>
          {user?.role === "admin" && maaliks.length > 0 && (
            <div>
              <label className="bk-label"><span className="bk-label-en">Assign to Maalik</span><span className="bk-label-hi">मालिक को सौंपें</span></label>
              <select value={form.maalik_id} onChange={e => setForm(p => ({ ...p, maalik_id: e.target.value }))} className="bk-input">
                <option value="">None (Admin-owned)</option>
                {maaliks.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
          )}
          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2" data-testid="save-illaka-btn">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Plus size={18} />}
            {illaka ? "Update Illaka" : "Create Illaka"}
          </button>
        </form>
      </div>
    </div>
  );
}

function MisalModal({ misal, illakaId, illakaName, onClose, onSave }) {
  const [form, setForm] = useState({ name: misal?.name || "", description: misal?.description || "", illaka_id: illakaId || misal?.illaka_id || "" });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (misal) {
        const res = await axios.put(`${API}/misals/${misal.id}`, form, { withCredentials: true });
        onSave(res.data, false);
        toast.success("Misal updated");
      } else {
        const res = await axios.post(`${API}/misals`, form, { withCredentials: true });
        onSave(res.data, true);
        toast.success("Misal created");
      }
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-md border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg font-['Outfit']">{misal ? "Edit Misal" : "New Misal"}</h2>
            {illakaName && <p className="text-xs text-muted-foreground">in {illakaName}</p>}
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="bk-label"><span className="bk-label-en">Misal Name *</span><span className="bk-label-hi">मिसाल का नाम (गांव)</span></label>
            <input type="text" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} className="bk-input" required placeholder="Village/area name" data-testid="misal-name-input" />
          </div>
          <div>
            <label className="bk-label"><span className="bk-label-en">Description</span></label>
            <input type="text" value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))} className="bk-input" placeholder="Optional" />
          </div>
          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2" data-testid="save-misal-btn">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <Home size={18} />}
            {misal ? "Update Misal" : "Add Misal"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function IllakaManagement() {
  const { user } = useAuth();
  const [illakas, setIllakas] = useState([]);
  const [misals, setMisals] = useState({});
  const [expanded, setExpanded] = useState({});
  const [maaliks, setMaaliks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [illakaModal, setIllakaModal] = useState(undefined);
  const [misalModal, setMisalModal] = useState(undefined);

  useEffect(() => {
    const load = async () => {
      try {
        const [iRes] = await Promise.all([
          axios.get(`${API}/illakas`, { withCredentials: true }),
        ]);
        setIllakas(iRes.data);
        if (user?.role === "admin") {
          const uRes = await axios.get(`${API}/users`, { withCredentials: true });
          setMaaliks(uRes.data.filter(u => u.role === "maalik"));
        }
      } catch (e) {
        toast.error("Failed to load data");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [user]);

  const toggleExpand = async (illaka) => {
    const newVal = !expanded[illaka.id];
    setExpanded(p => ({ ...p, [illaka.id]: newVal }));
    if (newVal && !misals[illaka.id]) {
      const res = await axios.get(`${API}/misals?illaka_id=${illaka.id}`, { withCredentials: true });
      setMisals(p => ({ ...p, [illaka.id]: res.data }));
    }
  };

  const deleteIllaka = async (illaka) => {
    if (!window.confirm(`Delete Illaka "${illaka.name}"? This cannot be undone.`)) return;
    await axios.delete(`${API}/illakas/${illaka.id}`, { withCredentials: true });
    setIllakas(p => p.filter(i => i.id !== illaka.id));
    toast.success("Illaka deleted");
  };

  const deleteMisal = async (illaka_id, misal) => {
    if (!window.confirm(`Delete Misal "${misal.name}"?`)) return;
    await axios.delete(`${API}/misals/${misal.id}`, { withCredentials: true });
    setMisals(p => ({ ...p, [illaka_id]: p[illaka_id].filter(m => m.id !== misal.id) }));
    toast.success("Misal deleted");
  };

  const saveMisal = (illaka_id, saved, isNew) => {
    setMisals(p => {
      const list = p[illaka_id] || [];
      return { ...p, [illaka_id]: isNew ? [...list, saved] : list.map(m => m.id === saved.id ? saved : m) };
    });
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground font-['Outfit']">Illakas & Misals</h1>
          <p className="text-muted-foreground text-sm">इलाके और मिसाल</p>
        </div>
        <button
          onClick={() => setIllakaModal(null)}
          className="flex items-center gap-2 bg-primary text-white px-5 py-3 rounded-lg font-semibold hover:bg-primary/90 transition-all text-sm"
          data-testid="add-illaka-btn"
        >
          <Plus size={16} /> New Illaka
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16">
          <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
        </div>
      ) : illakas.length === 0 ? (
        <div className="bk-card text-center py-16 text-muted-foreground" data-testid="no-illakas">
          <MapPin size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">No Illakas yet</p>
          <p className="text-sm">अभी तक कोई इलाका नहीं। Create your first Illaka to get started.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {illakas.map(illaka => (
            <div key={illaka.id} className="bk-card p-0 overflow-hidden" data-testid={`illaka-${illaka.id}`}>
              {/* Illaka Header */}
              <div className="flex items-center gap-3 p-4">
                <button onClick={() => toggleExpand(illaka)} className="flex-1 flex items-center gap-3 text-left">
                  <div className="w-9 h-9 bg-primary/10 rounded-xl flex items-center justify-center flex-shrink-0">
                    <MapPin size={18} className="text-primary" />
                  </div>
                  <div>
                    <h3 className="font-bold text-foreground">{illaka.name}</h3>
                    {illaka.description && <p className="text-xs text-muted-foreground">{illaka.description}</p>}
                    <p className="text-xs text-muted-foreground">
                      {misals[illaka.id] ? `${misals[illaka.id].length} Misals` : "Click to view Misals"}
                    </p>
                  </div>
                  {expanded[illaka.id] ? <ChevronDown size={18} className="ml-auto text-muted-foreground" /> : <ChevronRight size={18} className="ml-auto text-muted-foreground" />}
                </button>
                <div className="flex gap-2 flex-shrink-0">
                  <button onClick={() => setMisalModal({ illakaId: illaka.id, illakaName: illaka.name, misal: null })} className="p-2 rounded-lg hover:bg-primary/10 text-primary" title="Add Misal" data-testid={`add-misal-${illaka.id}`}>
                    <Home size={16} />
                  </button>
                  <button onClick={() => setIllakaModal(illaka)} className="p-2 rounded-lg hover:bg-muted text-muted-foreground" data-testid={`edit-illaka-${illaka.id}`}>
                    <Edit size={15} />
                  </button>
                  {user?.role === "admin" && (
                    <button onClick={() => deleteIllaka(illaka)} className="p-2 rounded-lg hover:bg-destructive/10 text-destructive" data-testid={`delete-illaka-${illaka.id}`}>
                      <Trash2 size={15} />
                    </button>
                  )}
                </div>
              </div>

              {/* Misals */}
              {expanded[illaka.id] && (
                <div className="border-t border-border bg-muted/20">
                  {(misals[illaka.id] || []).length === 0 ? (
                    <p className="px-6 py-4 text-sm text-muted-foreground">No Misals yet. Click the house icon to add one.</p>
                  ) : (
                    <div className="divide-y divide-border">
                      {(misals[illaka.id] || []).map(misal => (
                        <div key={misal.id} className="flex items-center gap-3 px-6 py-3" data-testid={`misal-${misal.id}`}>
                          <Home size={15} className="text-accent flex-shrink-0" />
                          <div className="flex-1">
                            <span className="text-sm font-medium text-foreground">{misal.name}</span>
                            {misal.description && <span className="text-xs text-muted-foreground ml-2">— {misal.description}</span>}
                          </div>
                          <div className="flex gap-1">
                            <button onClick={() => setMisalModal({ illakaId: illaka.id, illakaName: illaka.name, misal })} className="p-1.5 rounded hover:bg-muted text-muted-foreground">
                              <Edit size={13} />
                            </button>
                            <button onClick={() => deleteMisal(illaka.id, misal)} className="p-1.5 rounded hover:bg-destructive/10 text-destructive">
                              <Trash2 size={13} />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="px-6 py-3 border-t border-border">
                    <button
                      onClick={() => setMisalModal({ illakaId: illaka.id, illakaName: illaka.name, misal: null })}
                      className="text-sm text-primary font-semibold hover:underline flex items-center gap-1"
                    >
                      <Plus size={14} /> Add Misal / मिसाल जोड़ें
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {illakaModal !== undefined && (
        <IllakaModal
          illaka={illakaModal}
          maaliks={maaliks}
          onClose={() => setIllakaModal(undefined)}
          onSave={(saved, isNew) => {
            setIllakas(p => isNew ? [...p, saved] : p.map(i => i.id === saved.id ? saved : i));
          }}
        />
      )}

      {misalModal !== undefined && (
        <MisalModal
          misal={misalModal?.misal}
          illakaId={misalModal?.illakaId}
          illakaName={misalModal?.illakaName}
          onClose={() => setMisalModal(undefined)}
          onSave={(saved, isNew) => saveMisal(misalModal.illakaId, saved, isNew)}
        />
      )}
    </div>
  );
}
