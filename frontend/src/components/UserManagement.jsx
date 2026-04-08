import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import { UserPlus, Edit, UserX, X, Loader2, MapPin } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROLES = [
  { value: "admin", label: "Admin" },
  { value: "maalik", label: "Maalik (Owner)" },
  { value: "muneem", label: "Muneem (Senior Agent)" },
  { value: "sipahi", label: "Sipahi (Field Agent)" },
];

const ROLE_BADGE = {
  admin: "bg-purple-100 text-purple-800",
  maalik: "bg-amber-100 text-amber-800",
  muneem: "bg-blue-100 text-blue-800",
  sipahi: "bg-green-100 text-green-800",
};

const emptyForm = { name: "", phone: "", email: "", password: "", role: "sipahi", assigned_illaka_ids: [], maalik_id: "" };

function UserModal({ user: editUser, currentUser, illakas, maaliks, onClose, onSave }) {
  const [form, setForm] = useState(editUser ? { ...editUser, password: "", assigned_illaka_ids: editUser.assigned_illaka_ids || [] } : { ...emptyForm });
  const [loading, setLoading] = useState(false);

  const toggleIllaka = (id) => {
    setForm(p => ({
      ...p,
      assigned_illaka_ids: p.assigned_illaka_ids.includes(id)
        ? p.assigned_illaka_ids.filter(i => i !== id)
        : [...p.assigned_illaka_ids, id]
    }));
  };

  const availableRoles = currentUser.role === "admin"
    ? ROLES
    : ROLES.filter(r => r.value === "muneem" || r.value === "sipahi");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...form };
      if (!payload.password) delete payload.password;
      if (editUser) {
        const res = await axios.put(`${API}/users/${editUser.id}`, payload, { withCredentials: true });
        onSave(res.data, false);
        toast.success("User updated");
      } else {
        const res = await axios.post(`${API}/users`, payload, { withCredentials: true });
        onSave(res.data, true);
        toast.success("User created");
      }
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    } finally {
      setLoading(false);
    }
  };

  const showIllakaPicker = form.role === "maalik" || form.role === "muneem" || form.role === "sipahi";
  const showMaalikPicker = currentUser.role === "admin" && (form.role === "muneem" || form.role === "sipahi");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto" data-testid="user-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-lg border border-border my-4">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg font-['Outfit']">{editUser ? "Edit User" : "Add Team Member"}</h2>
            <p className="text-xs text-muted-foreground">{editUser ? "उपयोगकर्ता संपादित करें" : "टीम सदस्य जोड़ें"}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted" data-testid="close-modal-btn"><X size={18} /></button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="bk-label"><span className="bk-label-en">Full Name *</span><span className="bk-label-hi">पूरा नाम</span></label>
              <input type="text" value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))} className="bk-input" required data-testid="user-name-input" />
            </div>
            <div className="col-span-2">
              <label className="bk-label"><span className="bk-label-en">Mobile Number *</span><span className="bk-label-hi">मोबाइल नंबर</span></label>
              <input type="tel" value={form.phone || ""} onChange={e => setForm(p => ({ ...p, phone: e.target.value }))} className="bk-input" required placeholder="10-digit mobile number" data-testid="user-phone-input" />
            </div>
            <div className="col-span-2">
              <label className="bk-label"><span className="bk-label-en">Email (optional)</span><span className="bk-label-hi">ईमेल (वैकल्पिक)</span></label>
              <input type="email" value={form.email || ""} onChange={e => setForm(p => ({ ...p, email: e.target.value }))} className="bk-input" disabled={!!editUser} data-testid="user-email-input" />
            </div>
            <div className="col-span-2">
              <label className="bk-label"><span className="bk-label-en">{editUser ? "New Password" : "Password *"}</span></label>
              <input type="password" value={form.password} onChange={e => setForm(p => ({ ...p, password: e.target.value }))} className="bk-input" required={!editUser} placeholder={editUser ? "Leave blank to keep" : ""} data-testid="user-password-input" />
            </div>
            <div>
              <label className="bk-label"><span className="bk-label-en">Role *</span><span className="bk-label-hi">भूमिका</span></label>
              <select value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))} className="bk-input" required data-testid="user-role-select">
                {availableRoles.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
              </select>
            </div>
          </div>

          {showMaalikPicker && maaliks.length > 0 && (
            <div>
              <label className="bk-label"><span className="bk-label-en">Reports to Maalik</span><span className="bk-label-hi">किस मालिक के अंदर</span></label>
              <select value={form.maalik_id || ""} onChange={e => setForm(p => ({ ...p, maalik_id: e.target.value }))} className="bk-input">
                <option value="">None</option>
                {maaliks.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
              </select>
            </div>
          )}

          {showIllakaPicker && illakas.length > 0 && (
            <div>
              <label className="bk-label">
                <span className="bk-label-en flex items-center gap-1"><MapPin size={13} /> Assign Illakas</span>
                <span className="bk-label-hi">इलाके असाइन करें</span>
              </label>
              <div className="border border-border rounded-lg p-3 max-h-40 overflow-y-auto space-y-2">
                {illakas.map(ill => (
                  <label key={ill.id} className="flex items-center gap-2 cursor-pointer hover:bg-muted/30 px-1 py-0.5 rounded">
                    <input
                      type="checkbox"
                      checked={form.assigned_illaka_ids.includes(ill.id)}
                      onChange={() => toggleIllaka(ill.id)}
                      className="rounded"
                    />
                    <span className="text-sm font-medium">{ill.name}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          <button type="submit" disabled={loading} className="bk-btn-primary flex items-center justify-center gap-2" data-testid="save-user-btn">
            {loading ? <Loader2 size={18} className="animate-spin" /> : <UserPlus size={18} />}
            {editUser ? "Update" : "Create"} User
          </button>
        </form>
      </div>
    </div>
  );
}

export default function UserManagement() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [illakas, setIllakas] = useState([]);
  const [maaliks, setMaaliks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(undefined);

  useEffect(() => {
    const load = async () => {
      try {
        const [uRes, iRes] = await Promise.all([
          axios.get(`${API}/users`, { withCredentials: true }),
          axios.get(`${API}/illakas`, { withCredentials: true }),
        ]);
        setUsers(uRes.data);
        setIllakas(iRes.data);
        setMaaliks(uRes.data.filter(u => u.role === "maalik"));
      } catch { toast.error("Failed to load"); }
      finally { setLoading(false); }
    };
    load();
  }, []);

  const deactivate = async (id) => {
    if (!window.confirm("Deactivate this user?")) return;
    await axios.delete(`${API}/users/${id}`, { withCredentials: true });
    setUsers(p => p.map(u => u.id === id ? { ...u, is_active: false } : u));
    toast.success("User deactivated");
  };

  const handleSave = (saved, isNew) => {
    setUsers(p => isNew ? [saved, ...p] : p.map(u => u.id === saved.id ? saved : u));
  };

  const illakaNames = illakas.reduce((acc, i) => ({ ...acc, [i.id]: i.name }), {});

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold font-['Outfit']">Team / टीम</h1>
          <p className="text-muted-foreground text-sm">{users.length} members</p>
        </div>
        <button onClick={() => setModal(null)} className="flex items-center gap-2 bg-primary text-white px-5 py-3 rounded-lg font-semibold hover:bg-primary/90 text-sm" data-testid="add-user-btn">
          <UserPlus size={16} /> Add Member
        </button>
      </div>

      <div className="bk-card p-0 overflow-hidden">
        {loading ? (
          <div className="p-12 flex items-center justify-center">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="divide-y divide-border">
            {[...users].sort((a, b) => (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0)).map(u => (
              <div key={u.id} className={`px-5 py-4 flex items-start gap-4 ${!u.is_active ? "opacity-50" : ""}`} data-testid={`user-row-${u.id}`}>
                <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0">
                  <span className="text-primary font-bold">{u.name?.charAt(0)?.toUpperCase()}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="font-semibold text-foreground text-sm">{u.name}</p>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${ROLE_BADGE[u.role] || ""}`}>{u.role}</span>
                    {!u.is_active && <span className="text-xs text-destructive">Deactivated</span>}
                  </div>
                  <p className="text-xs text-muted-foreground">{u.email} {u.phone ? `· ${u.phone}` : ""}</p>
                  {u.assigned_illaka_ids?.length > 0 && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
                      <MapPin size={11} />
                      {u.assigned_illaka_ids.map(id => illakaNames[id] || id).join(", ")}
                    </p>
                  )}
                </div>
                <div className="flex gap-2">
                  <button onClick={() => setModal(u)} className="p-2 rounded-lg hover:bg-muted" data-testid={`edit-user-${u.id}`}><Edit size={15} className="text-muted-foreground" /></button>
                  {u.is_active && u.id !== currentUser?.id && (
                    <button onClick={() => deactivate(u.id)} className="p-2 rounded-lg hover:bg-destructive/10" data-testid={`deactivate-user-${u.id}`}><UserX size={15} className="text-destructive" /></button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {modal !== undefined && (
        <UserModal
          user={modal}
          currentUser={currentUser}
          illakas={illakas}
          maaliks={maaliks}
          onClose={() => setModal(undefined)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
