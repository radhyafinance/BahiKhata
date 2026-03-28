import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "./AuthContext";
import { Search, UserPlus } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const StatusBadge = ({ status }) => {
  const map = {
    pending: "bk-badge-pending",
    approved: "bk-badge-approved",
    rejected: "bk-badge-rejected",
  };
  const labels = {
    pending: "Pending",
    approved: "Approved",
    rejected: "Rejected",
  };
  return <span className={map[status] || "bk-badge-pending"}>{labels[status] || status}</span>;
};

export default function ClientList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [kycs, setKycs] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(0);
  const limit = 20;

  const fetchKycs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        skip: (page * limit).toString(),
      });
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);
      const res = await axios.get(`${API}/kycs?${params}`, { withCredentials: true });
      setKycs(res.data.kycs || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(fetchKycs, 300);
    return () => clearTimeout(t);
  }, [search, statusFilter, page]);

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground font-['Outfit']">Clients / ग्राहक</h1>
          <p className="text-muted-foreground text-sm">{total} total KYC records</p>
        </div>
        {(user?.role === "muneem" || user?.role === "sipahi") && (
          <button
            onClick={() => navigate("/kyc/new")}
            className="flex items-center gap-2 bg-primary text-primary-foreground px-5 py-3 rounded-lg font-semibold hover:bg-primary/90 active:scale-[0.98] transition-all shadow-sm text-sm"
            data-testid="new-kyc-btn"
          >
            <UserPlus size={16} /> New KYC
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search by name, phone or KYC number..."
            className="bk-input pl-11"
            data-testid="search-input"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(0); }}
          className="bk-input sm:w-52"
          data-testid="status-filter"
        >
          <option value="">All Status / सभी स्थिति</option>
          <option value="pending">Pending / लंबित</option>
          <option value="approved">Approved / स्वीकृत</option>
          <option value="rejected">Rejected / अस्वीकृत</option>
        </select>
      </div>

      {/* Table */}
      <div className="bk-card overflow-hidden p-0">
        {/* Table Header */}
        <div className="hidden sm:grid grid-cols-[1fr_1fr_1fr_auto_auto] gap-4 px-5 py-3 bg-muted/50 border-b border-border text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <span>Client Name / नाम</span>
          <span>Phone / फ़ोन</span>
          <span>Customer ID</span>
          <span>Status</span>
          <span>Date</span>
        </div>

        {loading ? (
          <div className="p-12 flex items-center justify-center">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : kycs.length === 0 ? (
          <div className="p-12 text-center text-muted-foreground" data-testid="no-results">
            <p className="font-medium">No KYCs found</p>
            <p className="text-sm">कोई KYC नहीं मिला</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {kycs.map((kyc) => (
              <div
                key={kyc.id}
                onClick={() => navigate(`/clients/${kyc.id}`)}
                className="flex sm:grid sm:grid-cols-[1fr_1fr_1fr_auto_auto] gap-4 items-center px-5 py-4 hover:bg-muted/30 cursor-pointer transition-colors"
                data-testid={`client-row-${kyc.id}`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0">
                    <span className="text-primary font-bold text-sm">
                      {kyc.primary_borrower?.name?.charAt(0)?.toUpperCase() || "?"}
                    </span>
                  </div>
                  <div>
                    <p className="font-semibold text-foreground text-sm">
                      {kyc.primary_borrower?.name || "—"}
                    </p>
                    <p className="text-xs text-muted-foreground sm:hidden">
                      {kyc.primary_borrower?.phone} · {kyc.customer_id || kyc.kyc_number}
                    </p>
                  </div>
                </div>
                <span className="text-sm text-foreground hidden sm:block">
                  {kyc.primary_borrower?.phone || "—"}
                </span>
                <span className="text-sm text-muted-foreground hidden sm:block font-mono">
                  {kyc.customer_id || kyc.kyc_number}
                </span>
                <StatusBadge status={kyc.status} />
                <span className="text-xs text-muted-foreground hidden sm:block">
                  {kyc.created_at ? new Date(kyc.created_at).toLocaleDateString("en-IN") : "—"}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Pagination */}
        {total > limit && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-border">
            <p className="text-sm text-muted-foreground">
              Showing {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total}
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 rounded border border-border text-sm hover:bg-muted disabled:opacity-40"
                data-testid="prev-page-btn"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={(page + 1) * limit >= total}
                className="px-3 py-1.5 rounded border border-border text-sm hover:bg-muted disabled:opacity-40"
                data-testid="next-page-btn"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
