import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "./AuthContext";
import {
  UserPlus, FileText, Clock, CheckCircle, XCircle, Users, TrendingUp, Calendar
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const StatusBadge = ({ status }) => {
  const map = {
    pending: "bk-badge-pending",
    approved: "bk-badge-approved",
    rejected: "bk-badge-rejected",
  };
  const labels = {
    pending: "Pending / लंबित",
    approved: "Approved / स्वीकृत",
    rejected: "Rejected / अस्वीकृत",
  };
  return (
    <span className={map[status] || "bk-badge-pending"} data-testid={`status-${status}`}>
      {labels[status] || status}
    </span>
  );
};

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

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchAll = async () => {
      try {
        const [s, k] = await Promise.all([
          axios.get(`${API}/dashboard/stats`, { withCredentials: true }),
          axios.get(`${API}/kycs?limit=5`, { withCredentials: true }),
        ]);
        setStats(s.data);
        setRecent(k.data.kycs || []);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchAll();
  }, []);

  const roleGreeting = {
    admin: "Administrator",
    maalik: "Maalik (Owner)",
    muneem: "Muneem (Senior Agent)",
    sipahi: "Sipahi (Field Agent)",
  }[user?.role] || "";

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground font-['Outfit']">
            Namaste, {user?.name?.split(" ")[0]} !
          </h1>
          <p className="text-muted-foreground mt-1">
            {roleGreeting} — {new Date().toLocaleDateString("en-IN", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
          </p>
        </div>
        {(user?.role === "muneem" || user?.role === "sipahi") && (
          <button
            onClick={() => navigate("/kyc/new")}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-6 py-3 rounded-lg font-semibold hover:bg-primary/90 active:scale-[0.98] transition-all shadow-sm"
            data-testid="new-kyc-btn"
          >
            <UserPlus size={18} />
            <span>New KYC / नया KYC</span>
          </button>
        )}
      </div>

      {/* Stats */}
      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="bk-card h-24 animate-pulse bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid="stats-grid">
          <StatCard
            icon={FileText}
            label="Total KYCs"
            labelHi="कुल KYC"
            value={stats?.total}
            color="bg-primary"
            testId="stat-total"
          />
          <StatCard
            icon={Clock}
            label="Pending"
            labelHi="लंबित"
            value={stats?.pending}
            color="bg-yellow-500"
            testId="stat-pending"
          />
          <StatCard
            icon={CheckCircle}
            label="Approved"
            labelHi="स्वीकृत"
            value={stats?.approved}
            color="bg-green-600"
            testId="stat-approved"
          />
          <StatCard
            icon={Calendar}
            label="Today"
            labelHi="आज"
            value={stats?.today}
            color="bg-accent"
            testId="stat-today"
          />
        </div>
      )}

      {/* Secondary Stats */}
      {!loading && user?.role !== "sipahi" && (
        <div className="grid grid-cols-2 gap-4">
          <StatCard
            icon={XCircle}
            label="Rejected"
            labelHi="अस्वीकृत"
            value={stats?.rejected}
            color="bg-destructive"
            testId="stat-rejected"
          />
          <StatCard
            icon={Users}
            label="Sipahi Count"
            labelHi="सिपाही"
            value={stats?.sipahi_count}
            color="bg-indigo-600"
            testId="stat-officers"
          />
        </div>
      )}

      {/* Recent KYCs */}
      <div className="bk-card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-lg font-bold text-foreground font-['Outfit']">Recent KYCs</h2>
            <p className="text-xs text-muted-foreground">हाल के KYC</p>
          </div>
          <button
            onClick={() => navigate("/clients")}
            className="text-primary text-sm font-semibold hover:underline"
            data-testid="view-all-btn"
          >
            View All →
          </button>
        </div>

        {recent.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground" data-testid="no-kycs-msg">
            <FileText size={40} className="mx-auto mb-3 opacity-30" />
            <p className="font-medium">No KYCs yet</p>
            <p className="text-sm text-xs mt-1">अभी तक कोई KYC नहीं</p>
            <button
              onClick={() => navigate("/kyc/new")}
              className="mt-4 text-primary font-semibold text-sm hover:underline"
            >
              Start first KYC →
            </button>
          </div>
        ) : (
          <div className="space-y-3" data-testid="recent-kycs-list">
            {recent.map((kyc) => (
              <div
                key={kyc.id}
                onClick={() => navigate(`/clients/${kyc.id}`)}
                className="flex items-center justify-between p-4 rounded-lg border border-border hover:bg-muted/30 cursor-pointer transition-colors"
                data-testid={`kyc-row-${kyc.id}`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-primary font-bold text-sm">
                      {kyc.primary_borrower?.name?.charAt(0)?.toUpperCase() || "?"}
                    </span>
                  </div>
                  <div>
                    <p className="font-semibold text-foreground text-sm">
                      {kyc.primary_borrower?.name || "—"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {kyc.kyc_number} · {kyc.primary_borrower?.phone || "—"}
                    </p>
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
