import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { UserPlus, Edit, UserX, X, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const ROLES = [
  { value: "admin", label: "Admin / व्यवस्थापक" },
  { value: "branch_manager", label: "Branch Manager / शाखा प्रबंधक" },
  { value: "field_officer", label: "Field Officer / फील्ड अधिकारी" },
];

const roleBadge = {
  admin: "bg-purple-100 text-purple-800",
  branch_manager: "bg-blue-100 text-blue-800",
  field_officer: "bg-green-100 text-green-800",
};

const emptyForm = { name: "", email: "", password: "", role: "field_officer", branch: "", phone: "" };

function UserModal({ user, onClose, onSave }) {
  const [form, setForm] = useState(user ? { ...user, password: "" } : { ...emptyForm });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (user) {
        const updates = { ...form };
        if (!updates.password) delete updates.password;
        const res = await axios.put(`${API}/users/${user.id}`, updates, { withCredentials: true });
        onSave(res.data, false);
        toast.success("User updated successfully");
      } else {
        const res = await axios.post(`${API}/users`, form, { withCredentials: true });
        onSave(res.data, true);
        toast.success("User created successfully");
      }
      onClose();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save user");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" data-testid="user-modal">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-card rounded-xl shadow-2xl w-full max-w-md border border-border">
        <div className="flex items-center justify-between p-5 border-b border-border">
          <div>
            <h2 className="font-bold text-lg text-foreground font-['Outfit']">
              {user ? "Edit User" : "Add New User"}
            </h2>
            <p className="text-xs text-muted-foreground">{user ? "उपयोगकर्ता संपादित करें" : "नया उपयोगकर्ता जोड़ें"}</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted" data-testid="close-modal-btn">
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Full Name *</span>
              <span className="bk-label-hi">पूरा नाम</span>
            </label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              className="bk-input"
              required
              data-testid="user-name-input"
            />
          </div>

          <div>
            <label className="bk-label">
              <span className="bk-label-en">Email *</span>
              <span className="bk-label-hi">ईमेल</span>
            </label>
            <input
              type="email"
              value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
              className="bk-input"
              required={!user}
              disabled={!!user}
              data-testid="user-email-input"
            />
          </div>

          <div>
            <label className="bk-label">
              <span className="bk-label-en">{user ? "New Password (leave blank to keep)" : "Password *"}</span>
              <span className="bk-label-hi">पासवर्ड</span>
            </label>
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))}
              className="bk-input"
              required={!user}
              placeholder={user ? "Leave blank to keep current" : ""}
              data-testid="user-password-input"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Role *</span>
                <span className="bk-label-hi">भूमिका</span>
              </label>
              <select
                value={form.role}
                onChange={(e) => setForm((p) => ({ ...p, role: e.target.value }))}
                className="bk-input"
                required
                data-testid="user-role-select"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>{r.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="bk-label">
                <span className="bk-label-en">Branch</span>
                <span className="bk-label-hi">शाखा</span>
              </label>
              <input
                type="text"
                value={form.branch || ""}
                onChange={(e) => setForm((p) => ({ ...p, branch: e.target.value }))}
                className="bk-input"
                placeholder="e.g. Mumbai"
                data-testid="user-branch-input"
              />
            </div>
          </div>

          <div>
            <label className="bk-label">
              <span className="bk-label-en">Phone</span>
              <span className="bk-label-hi">फ़ोन</span>
            </label>
            <input
              type="tel"
              value={form.phone || ""}
              onChange={(e) => setForm((p) => ({ ...p, phone: e.target.value }))}
              className="bk-input"
              data-testid="user-phone-input"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="bk-btn-primary flex items-center justify-center gap-2 mt-2"
            data-testid="save-user-btn"
          >
            {loading ? <Loader2 size={18} className="animate-spin" /> : <UserPlus size={18} />}
            {user ? "Update User" : "Create User"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function UserManagement() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalUser, setModalUser] = useState(undefined); // undefined=closed, null=new, obj=edit

  const fetchUsers = async () => {
    try {
      const res = await axios.get(`${API}/users`, { withCredentials: true });
      setUsers(res.data);
    } catch (e) {
      toast.error("Failed to load users");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const handleSave = (saved, isNew) => {
    if (isNew) {
      setUsers((p) => [saved, ...p]);
    } else {
      setUsers((p) => p.map((u) => (u.id === saved.id ? saved : u)));
    }
  };

  const deactivateUser = async (userId) => {
    if (!window.confirm("Deactivate this user?")) return;
    try {
      await axios.delete(`${API}/users/${userId}`, { withCredentials: true });
      setUsers((p) => p.map((u) => (u.id === userId ? { ...u, is_active: false } : u)));
      toast.success("User deactivated");
    } catch {
      toast.error("Failed to deactivate user");
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground font-['Outfit']">
            User Management / उपयोगकर्ता प्रबंधन
          </h1>
          <p className="text-muted-foreground text-sm">{users.length} users registered</p>
        </div>
        <button
          onClick={() => setModalUser(null)}
          className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-3 rounded-lg font-semibold hover:bg-primary/90 active:scale-[0.98] transition-all shadow-sm text-sm"
          data-testid="add-user-btn"
        >
          <UserPlus size={16} /> Add User / उपयोगकर्ता जोड़ें
        </button>
      </div>

      {/* Table */}
      <div className="bk-card overflow-hidden p-0">
        <div className="hidden sm:grid grid-cols-[1fr_1fr_auto_auto_auto] gap-4 px-5 py-3 bg-muted/50 border-b border-border text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <span>Name / नाम</span>
          <span>Email</span>
          <span>Role</span>
          <span>Branch</span>
          <span>Actions</span>
        </div>

        {loading ? (
          <div className="p-12 flex items-center justify-center">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <div className="divide-y divide-border">
            {users.map((u) => (
              <div
                key={u.id}
                className={`flex sm:grid sm:grid-cols-[1fr_1fr_auto_auto_auto] gap-4 items-center px-5 py-4 ${!u.is_active ? "opacity-50" : ""}`}
                data-testid={`user-row-${u.id}`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-primary font-bold text-sm">
                      {u.name?.charAt(0)?.toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <p className="font-semibold text-sm text-foreground">{u.name}</p>
                    {!u.is_active && (
                      <span className="text-xs text-destructive">Deactivated</span>
                    )}
                    <p className="text-xs text-muted-foreground sm:hidden">{u.email}</p>
                  </div>
                </div>
                <span className="text-sm text-muted-foreground hidden sm:block truncate">{u.email}</span>
                <span className={`inline-flex px-2 py-1 rounded-full text-xs font-semibold ${roleBadge[u.role] || ""}`}>
                  {u.role?.replace("_", " ")}
                </span>
                <span className="text-sm text-muted-foreground hidden sm:block">{u.branch || "—"}</span>
                <div className="flex gap-2 ml-auto sm:ml-0">
                  <button
                    onClick={() => setModalUser(u)}
                    className="p-2 rounded-lg hover:bg-muted transition-colors"
                    data-testid={`edit-user-${u.id}`}
                  >
                    <Edit size={15} className="text-muted-foreground" />
                  </button>
                  {u.is_active && (
                    <button
                      onClick={() => deactivateUser(u.id)}
                      className="p-2 rounded-lg hover:bg-destructive/10 transition-colors"
                      data-testid={`deactivate-user-${u.id}`}
                    >
                      <UserX size={15} className="text-destructive" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {modalUser !== undefined && (
        <UserModal
          user={modalUser}
          onClose={() => setModalUser(undefined)}
          onSave={handleSave}
        />
      )}
    </div>
  );
}
