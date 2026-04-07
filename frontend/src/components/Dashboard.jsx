import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import {
  UserPlus, FileText, Clock, CheckCircle, XCircle, Users,
  TrendingUp, Calendar, BookOpen, Receipt, Gavel, ClipboardList,
  IndianRupee, ChevronRight
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const fmt = (n) =>
  Number(n || 0).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

// ── Current active month (same logic as collection sheet) ──────────────────
function getActiveMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function fmtMonth(ym) {
  if (!ym) return "";
  const [y, m] = ym.split("-");
  return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "long", year: "numeric" });
}

// ── Stat card (for Admin/Maalik dashboard) ────────────────────────────────
const StatCard = ({ icon: Icon, label, labelHi, value, color, testId }) => (
  <div className="bk-card flex items-center gap-4" data-testid={testId}>
    <div className={`w-14 h-14 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
      <Icon size={24} className="text-white" />
    </div>
    <div>
      <p className="text-2xl font-bold text-foreground font-['Outfit']">{value ?? "—"}</p>
      <p className="text-sm font-semibold text-foreground">{label}</p>
      <p className="text-xs text-muted-foreground">{labelHi}</p>
    </div>
  </div>
);

const StatusBadge = ({ status }) => {
  const map = { pending: "bk-badge-pending", approved: "bk-badge-approved", rejected: "bk-badge-rejected" };
  const labels = { pending: "Pending / लंबित", approved: "Approved / स्वीकृत", rejected: "Rejected / अस्वीकृत" };
  return <span className={map[status] || "bk-badge-pending"}>{labels[status] || status}</span>;
};

// ═══════════════════════════════════════════════════════════════════════════
// Muneem / Sipahi Dashboard
// ═══════════════════════════════════════════════════════════════════════════
function FieldAgentDashboard({ user, selectedIllaka }) {
  const navigate = useNavigate();
  const [month] = useState(getActiveMonth);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!selectedIllaka?.id) return;
    setLoading(true);
    axios
      .get(`${API}/collections/monthly-summary?illaka_id=${selectedIllaka.id}&month=${month}`, {
        withCredentials: true,
      })
      .then((r) => setSummary(r.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [selectedIllaka, month]);

  const quickActions = [
    {
      label: "Vasuli",
      labelHi: "वसूली",
      icon: IndianRupee,
      color: "bg-green-600 hover:bg-green-700",
      path: "/collections",
      testId: "quick-vasuli",
    },
    {
      label: "New KYC",
      labelHi: "नया KYC",
      icon: UserPlus,
      color: "bg-primary hover:bg-primary/90",
      path: "/kyc/new",
      testId: "quick-new-kyc",
    },
    {
      label: "Bid",
      labelHi: "बिड",
      icon: Gavel,
      color: "bg-amber-600 hover:bg-amber-700",
      path: "/accounts?tab=bid",
      testId: "quick-bid",
    },
    {
      label: "Expenses",
      labelHi: "खर्चा",
      icon: Receipt,
      color: "bg-rose-600 hover:bg-rose-700",
      path: "/accounts?tab=expense",
      testId: "quick-expenses",
    },
  ];

  const total = summary?.total || {};
  const misals = summary?.misals || [];

  return (
    <div className="p-4 sm:p-6 max-w-2xl mx-auto space-y-6">
      {/* Greeting */}
      <div>
        <h1 className="text-2xl font-bold font-['Outfit'] text-foreground">
          Namaste, {user?.name?.split(" ")[0]}
        </h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" })}
          {selectedIllaka && <span> · {selectedIllaka.name}</span>}
        </p>
      </div>

      {/* ── Quick Action Buttons ── */}
      <div className="grid grid-cols-4 gap-3" data-testid="quick-actions">
        {quickActions.map((a) => (
          <button
            key={a.label}
            onClick={() => navigate(a.path)}
            className={`flex flex-col items-center justify-center gap-2 rounded-2xl py-4 px-2 text-white font-semibold transition-all active:scale-95 shadow-sm ${a.color}`}
            data-testid={a.testId}
          >
            <a.icon size={26} strokeWidth={2} />
            <span className="text-[11px] leading-none text-center">{a.label}</span>
            <span className="text-[10px] leading-none text-white/75">{a.labelHi}</span>
          </button>
        ))}
      </div>

      {/* ── Collection Summary ── */}
      <div className="space-y-3" data-testid="collection-summary-section">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold font-['Outfit'] text-foreground">
              {fmtMonth(month)} — किस्त सारांश
            </h2>
            <p className="text-xs text-muted-foreground">Monthly Collection Summary</p>
          </div>
          <button
            onClick={() => navigate("/collections")}
            className="text-xs text-primary font-semibold flex items-center gap-0.5 hover:underline"
          >
            Vasuli <ChevronRight size={13} />
          </button>
        </div>

        {/* Illaka Total Card */}
        {!loading && summary && (
          <div
            className="bk-card p-4 bg-primary/5 border-primary/20"
            data-testid="illaka-total-card"
          >
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  {selectedIllaka?.name} — कुल / Total
                </p>
                <p className="text-xs text-muted-foreground">{total.clients_paid ?? 0}/{total.clients || 0} clients paid</p>
              </div>
              <span className="text-xs font-semibold text-primary bg-primary/10 px-2 py-1 rounded-full">
                {total.utaar > 0 ? Math.round((total.vayda / total.utaar) * 100) : 0}% collected
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-red-50 border border-red-100 p-3 text-center">
                <p className="text-[10px] font-bold uppercase tracking-wider text-red-500 mb-1">
                  उतार / Utaar
                </p>
                <p className="text-xl font-black tabular-nums text-red-700 leading-none" data-testid="illaka-utaar">
                  {fmt(total.utaar)}
                </p>
                <p className="text-[10px] text-red-400 mt-1">Due this month</p>
              </div>
              <div className="rounded-xl bg-green-50 border border-green-100 p-3 text-center">
                <p className="text-[10px] font-bold uppercase tracking-wider text-green-600 mb-1">
                  वायदा / Vayda
                </p>
                <p className="text-xl font-black tabular-nums text-green-700 leading-none" data-testid="illaka-vayda">
                  {fmt(total.vayda)}
                </p>
                <p className="text-[10px] text-green-500 mt-1">Collected</p>
              </div>
            </div>
            {/* Progress bar */}
            <div className="mt-3 h-2 bg-muted rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-700"
                style={{ width: `${total.utaar > 0 ? Math.round((total.vayda / total.utaar) * 100) : 0}%` }}
              />
            </div>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="bk-card p-4 animate-pulse space-y-3">
            <div className="h-4 bg-muted rounded w-1/2" />
            <div className="grid grid-cols-2 gap-3">
              <div className="h-20 bg-muted rounded-xl" />
              <div className="h-20 bg-muted rounded-xl" />
            </div>
          </div>
        )}

        {/* Misal-wise breakdown */}
        {!loading && misals.length > 0 && (
          <div className="space-y-2" data-testid="misal-breakdown">
            {misals.map((m) => {
              const pct = m.utaar > 0 ? Math.round((m.vayda / m.utaar) * 100) : 0;
              return (
                <div key={m.misal_id} className="bk-card p-3" data-testid={`misal-card-${m.misal_id}`}>
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-sm text-foreground truncate">{m.misal_name}</p>
                      <p className="text-[11px] text-muted-foreground">{m.clients_paid ?? 0}/{m.clients} clients paid</p>
                    </div>
                    <span
                      className={`text-[11px] font-bold px-2 py-0.5 rounded-full flex-shrink-0 ${
                        pct >= 100
                          ? "bg-green-100 text-green-700"
                          : pct >= 50
                          ? "bg-amber-100 text-amber-700"
                          : "bg-red-100 text-red-600"
                      }`}
                    >
                      {pct}%
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-center">
                    <div>
                      <p className="text-[10px] font-bold text-red-500 uppercase tracking-wide">उतार</p>
                      <p className="text-sm font-bold tabular-nums text-red-700">{fmt(m.utaar)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-bold text-green-600 uppercase tracking-wide">वायदा</p>
                      <p className="text-sm font-bold tabular-nums text-green-700">{fmt(m.vayda)}</p>
                    </div>
                  </div>
                  <div className="mt-2 h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500 rounded-full transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!loading && !selectedIllaka && (
          <div className="bk-card p-6 text-center text-muted-foreground text-sm">
            Select an Illaka to see collection summary
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Admin / Maalik Dashboard (unchanged)
// ═══════════════════════════════════════════════════════════════════════════
function AdminDashboard({ user, selectedIllaka }) {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const p = new URLSearchParams({ limit: "5" });
        if (selectedIllaka) p.append("illaka_id", selectedIllaka.id);
        const [s, k] = await Promise.all([
          axios.get(`${API}/dashboard/stats${selectedIllaka ? `?illaka_id=${selectedIllaka.id}` : ""}`, { withCredentials: true }),
          axios.get(`${API}/kycs?${p}`, { withCredentials: true }),
        ]);
        setStats(s.data);
        setRecent(k.data.kycs || []);
      } catch {}
      finally { setLoading(false); }
    };
    fetchAll();
  }, [selectedIllaka]);

  const roleGreeting = { admin: "Administrator", maalik: "Maalik (Owner)" }[user?.role] || "";

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground font-['Outfit']">
            Namaste, {user?.name?.split(" ")[0]} !
          </h1>
          <p className="text-muted-foreground mt-1">
            {roleGreeting} — {new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1,2,3,4].map(i => <div key={i} className="bk-card h-24 animate-pulse bg-muted" />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="stats-grid">
          <StatCard icon={FileText}    label="Total KYCs"    labelHi="कुल KYC"         value={stats?.total}        color="bg-primary"      testId="stat-total" />
          <StatCard icon={Clock}       label="Pending"       labelHi="लंबित"            value={stats?.pending}      color="bg-yellow-500"   testId="stat-pending" />
          <StatCard icon={CheckCircle} label="Approved"      labelHi="स्वीकृत"          value={stats?.approved}     color="bg-green-600"    testId="stat-approved" />
          <StatCard icon={Calendar}    label="Today"         labelHi="आज"               value={stats?.today}        color="bg-accent"       testId="stat-today" />
        </div>
      )}

      {!loading && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard icon={XCircle}    label="Rejected"      labelHi="अस्वीकृत"  value={stats?.rejected}     color="bg-destructive"  testId="stat-rejected" />
          <StatCard icon={Users}      label="Sipahi Count"  labelHi="सिपाही"    value={stats?.sipahi_count} color="bg-indigo-600"   testId="stat-officers" />
          <StatCard icon={TrendingUp} label="Active Loans"  labelHi="सक्रिय कर्ज" value={stats?.active_loans} color="bg-emerald-600" testId="stat-active-loans" />
          <StatCard icon={TrendingUp} label="Total Loans"   labelHi="कुल कर्ज"  value={stats?.total_loans}  color="bg-amber-600"    testId="stat-total-loans" />
        </div>
      )}

      <div className="bk-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-foreground font-['Outfit']">Recent KYCs</h2>
            <p className="text-xs text-muted-foreground">हाल के KYC</p>
          </div>
          <button onClick={() => navigate("/clients")} className="text-primary text-sm font-semibold hover:underline" data-testid="view-all-btn">
            View All →
          </button>
        </div>
        {recent.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground" data-testid="no-kycs-msg">
            <FileText size={40} className="mx-auto mb-3 opacity-30" />
            <p className="font-medium">No KYCs yet / अभी तक कोई KYC नहीं</p>
            <button onClick={() => navigate("/kyc/new")} className="mt-4 text-primary font-semibold text-sm hover:underline">Start first KYC →</button>
          </div>
        ) : (
          <div className="space-y-3" data-testid="recent-kycs-list">
            {recent.map((kyc) => (
              <div key={kyc.id} onClick={() => navigate(`/clients/${kyc.id}`)}
                className="flex items-center justify-between p-4 rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-colors"
                data-testid={`kyc-row-${kyc.id}`}>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-primary font-bold text-sm">{kyc.primary_borrower?.name?.charAt(0)?.toUpperCase() || "?"}</span>
                  </div>
                  <div>
                    <p className="font-semibold text-foreground text-sm">{kyc.primary_borrower?.name || "—"}</p>
                    <p className="text-xs text-muted-foreground">{kyc.kyc_number} · {kyc.primary_borrower?.phone || "—"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusBadge status={kyc.status} />
                  <span className="text-xs text-muted-foreground hidden sm:block">
                    {kyc.created_at ? new Date(kyc.created_at).toLocaleDateString("en-IN") : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Root export — routes to correct dashboard by role
// ═══════════════════════════════════════════════════════════════════════════
export default function Dashboard() {
  const { user } = useAuth();
  const { selectedIllaka } = useIllaka();

  if (user?.role === "muneem" || user?.role === "sipahi") {
    return <FieldAgentDashboard user={user} selectedIllaka={selectedIllaka} />;
  }
  return <AdminDashboard user={user} selectedIllaka={selectedIllaka} />;
}
