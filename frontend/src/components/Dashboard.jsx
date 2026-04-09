import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import {
  UserPlus, FileText, Clock, CheckCircle, XCircle, Users,
  TrendingUp, Calendar, BookOpen, Receipt, Gavel, ClipboardList,
  IndianRupee, ChevronRight, ArrowUpRight, Landmark, Wallet, BarChart2
} from "lucide-react";
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend
} from "recharts";

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
// Admin / Maalik Dashboard — Rich Overview
// ═══════════════════════════════════════════════════════════════════════════

const fmtCr = (n) => {
  const v = Number(n || 0);
  if (v >= 10000000) return `₹${(v / 10000000).toFixed(2)} Cr`;
  if (v >= 100000) return `₹${(v / 100000).toFixed(2)} L`;
  return `₹${v.toLocaleString("en-IN")}`;
};

const fmtINR = (n) =>
  Number(n || 0).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

function recBadge(pct) {
  if (pct === null || pct === undefined) return "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-muted text-muted-foreground";
  if (pct >= 80) return "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-green-100 text-green-800 border border-green-200 dark:bg-green-900/40 dark:text-green-400 dark:border-green-800";
  if (pct >= 50) return "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-yellow-100 text-yellow-800 border border-yellow-200 dark:bg-yellow-900/40 dark:text-yellow-400 dark:border-yellow-800";
  return "inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-red-100 text-red-800 border border-red-200 dark:bg-red-900/40 dark:text-red-400 dark:border-red-800";
}

function MetricCard({ icon: Icon, en, hi, value, sub, color, testId, trend }) {
  return (
    <div className="bk-card relative overflow-hidden flex flex-col justify-between hover:shadow-md hover:border-primary/40 transition-all duration-200" data-testid={testId}>
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0 ${color}`}>
          <Icon size={18} className="text-white" strokeWidth={1.5} />
        </div>
        {trend !== undefined && trend !== null && (
          <span className={`text-xs font-semibold ${trend >= 0 ? "text-green-600" : "text-red-500"}`}>
            {trend >= 0 ? "+" : ""}{trend}%
          </span>
        )}
      </div>
      <div>
        <p className="text-2xl lg:text-3xl font-bold text-foreground font-['Outfit'] tracking-tight leading-none">{value}</p>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
        <p className="text-sm font-medium text-foreground mt-2">{en}</p>
        <p className="text-xs text-muted-foreground/80">{hi}</p>
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card border border-border rounded-xl shadow-lg p-3 text-xs space-y-1 min-w-[160px]">
      <p className="font-semibold text-foreground mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex justify-between gap-4">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-medium tabular-nums">
            {p.dataKey === "recovery_pct" ? `${p.value}%` : fmtCr(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
};

function AdminDashboard({ user, selectedIllaka, selectedMaalik }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams();
      if (selectedIllaka) p.append("illaka_id", selectedIllaka.id);
      else if (selectedMaalik) p.append("maalik_id", selectedMaalik.id);
      const res = await axios.get(`${API}/dashboard/overview?${p}`, { withCredentials: true });
      setData(res.data);
    } catch {}
    finally { setLoading(false); }
  }, [selectedIllaka, selectedMaalik]);

  useEffect(() => { fetchOverview(); }, [fetchOverview]);

  const monthLabel = data
    ? new Date(data.current_month + "-01").toLocaleString("en-IN", { month: "long", year: "numeric" })
    : "";

  const fyLabel = data ? `FY ${data.fy_start_year}-${String(data.fy_start_year + 1).slice(2)}` : "";

  const scopeLabel = selectedIllaka
    ? selectedIllaka.name
    : selectedMaalik
    ? `${selectedMaalik.name}`
    : "All Illakas";

  const Skeleton = () => (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
      {[1,2,3,4,5].map(i => <div key={i} className="bk-card h-32 animate-pulse bg-muted" />)}
    </div>
  );

  return (
    <div className="p-4 md:p-6 max-w-[1600px] mx-auto flex flex-col gap-6">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2" data-testid="dashboard-header-greeting">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground font-['Outfit'] tracking-tight">
            Namaste, {user?.name?.split(" ")[0]} !
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
            <span className="mx-1.5 opacity-40">·</span>
            <span className="font-medium text-foreground/70">{scopeLabel}</span>
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => navigate("/collections")} className="bk-btn-sm flex items-center gap-1.5 bg-green-600 text-white hover:bg-green-700 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors">
            <IndianRupee size={13} /> Vasuli
          </button>
          <button onClick={() => navigate("/kyc/new")} className="bk-btn-sm flex items-center gap-1.5 bg-primary text-white hover:bg-primary/90 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors">
            <UserPlus size={13} /> New KYC
          </button>
        </div>
      </div>

      {/* ── Top Metric Cards ── */}
      {loading ? <Skeleton /> : (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          <MetricCard
            icon={Landmark} en="Total Bakaya" hi="कुल बकाया"
            value={fmtCr(data?.bakaya)}
            sub="Outstanding principal + interest"
            color="bg-primary"
            testId="card-bakaya-total"
          />
          <MetricCard
            icon={Users} en="Active Clients" hi="सक्रिय ग्राहक"
            value={(data?.active_clients || 0).toLocaleString("en-IN")}
            sub="Excludes Gyal (bad debt)"
            color="bg-indigo-600"
            testId="card-active-clients"
          />
          <MetricCard
            icon={BarChart2} en={`Utaar — ${monthLabel}`} hi="उतार"
            value={fmtCr(data?.utaar)}
            sub={`${data?.utaar_count || 0} EMIs scheduled`}
            color="bg-amber-600"
            testId="card-utaar-month"
          />
          <MetricCard
            icon={TrendingUp} en={`Vayda — ${monthLabel}`} hi="वायदा"
            value={fmtCr(data?.vayda)}
            sub={data?.recovery_pct !== null ? `${data?.recovery_pct}% recovery` : `${data?.vayda_count || 0} EMIs collected`}
            color="bg-green-600"
            testId="card-vayda-month"
            trend={data?.recovery_pct}
          />
          <MetricCard
            icon={Wallet} en={`देन — ${monthLabel}`} hi="देन"
            value={fmtCr(data?.den)}
            sub={`${data?.den_count || 0} loan(s) disbursed`}
            color="bg-rose-600"
            testId="card-den-month"
          />
        </div>
      )}

      {/* ── Bottom row: Illaka Table + Year Graph ── */}
      {!loading && data && (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">

          {/* ── Illaka Breakdown Table (2 cols) ── */}
          <div className="lg:col-span-2" data-testid="table-illaka-breakdown">
            <div className="bk-card p-0 overflow-hidden">
              <div className="px-4 py-3 border-b border-border bg-muted/30">
                <h2 className="text-sm font-bold text-foreground font-['Outfit']">Illaka Breakdown</h2>
                <p className="text-xs text-muted-foreground">इलाकावार — {monthLabel}</p>
              </div>
              {data.illakas.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-sm">No data for current scope</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-muted/50 text-muted-foreground text-left">
                        <th className="px-3 py-2 font-medium">Illaka</th>
                        <th className="px-3 py-2 font-medium text-right">Bakaya</th>
                        <th className="px-3 py-2 font-medium text-right">Active</th>
                        <th className="px-3 py-2 font-medium text-right">Utaar</th>
                        <th className="px-3 py-2 font-medium text-right">Vayda</th>
                        <th className="px-3 py-2 font-medium text-center">Rec%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.illakas.map((il) => (
                        <tr key={il.illaka_id} className="border-t border-border hover:bg-muted/30 transition-colors" data-testid={`illaka-row-${il.illaka_id}`}>
                          <td className="px-3 py-2.5 font-semibold text-foreground max-w-[100px] truncate">{il.name}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-foreground">{fmtCr(il.bakaya)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{il.active_clients}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-amber-700 dark:text-amber-400">{fmtCr(il.utaar)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-green-700 dark:text-green-400">{fmtCr(il.vayda)}</td>
                          <td className="px-3 py-2.5 text-center">
                            <span className={recBadge(il.recovery_pct)}>
                              {il.recovery_pct !== null ? `${il.recovery_pct}%` : "—"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    {/* Totals row */}
                    <tfoot>
                      <tr className="border-t-2 border-border bg-muted/40 font-bold">
                        <td className="px-3 py-2.5 text-foreground">Total</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{fmtCr(data.bakaya)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{data.active_clients}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-amber-700 dark:text-amber-400">{fmtCr(data.utaar)}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-green-700 dark:text-green-400">{fmtCr(data.vayda)}</td>
                        <td className="px-3 py-2.5 text-center">
                          <span className={recBadge(data.recovery_pct)}>
                            {data.recovery_pct !== null ? `${data.recovery_pct}%` : "—"}
                          </span>
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* ── Year Recovery Graph (3 cols) ── */}
          <div className="lg:col-span-3" data-testid="chart-year-recovery">
            <div className="bk-card h-full flex flex-col">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className="text-sm font-bold text-foreground font-['Outfit']">Year Recovery</h2>
                  <p className="text-xs text-muted-foreground">वार्षिक वसूली — {fyLabel}</p>
                </div>
                <div className="flex gap-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1"><span className="w-3 h-2 bg-amber-400/60 rounded inline-block" /> Utaar</span>
                  <span className="flex items-center gap-1"><span className="w-3 h-2 bg-green-500 rounded inline-block" /> Vayda</span>
                  <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-primary inline-block" /> Rec%</span>
                </div>
              </div>
              <div className="flex-1 min-h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={data.year_graph} margin={{ top: 4, right: 20, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="month" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                    <YAxis yAxisId="amount" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} tickFormatter={v => v >= 100000 ? `${(v/100000).toFixed(0)}L` : v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} width={40} />
                    <YAxis yAxisId="pct" orientation="right" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} unit="%" width={35} domain={[0, 120]} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar yAxisId="amount" dataKey="utaar" name="Utaar" fill="hsl(43 96% 56% / 0.5)" radius={[3,3,0,0]} maxBarSize={28} />
                    <Bar yAxisId="amount" dataKey="vayda" name="Vayda" fill="hsl(142 71% 45%)" radius={[3,3,0,0]} maxBarSize={28} />
                    <Line yAxisId="pct" type="monotone" dataKey="recovery_pct" name="Rec %" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 3, fill: "hsl(var(--primary))" }} activeDot={{ r: 5 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

        </div>
      )}

    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// Root export — routes to correct dashboard by role
// ═══════════════════════════════════════════════════════════════════════════
export default function Dashboard() {
  const { user } = useAuth();
  const { selectedIllaka, selectedMaalik } = useIllaka();

  if (user?.role === "muneem" || user?.role === "sipahi") {
    return <FieldAgentDashboard user={user} selectedIllaka={selectedIllaka} />;
  }
  return <AdminDashboard user={user} selectedIllaka={selectedIllaka} selectedMaalik={selectedMaalik} />;
}
