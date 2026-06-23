import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import { Search, Plus, TrendingUp, Zap } from "lucide-react";
import QuickAddLoanModal from "./QuickAddLoanModal";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STATUS_BADGE = {
  active: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-600",
  overdue: "bg-red-100 text-red-700",
};

const STATUS_LABELS = {
  active: "Active / सक्रिय",
  closed: "Closed / बंद",
  overdue: "Overdue / बकाया",
};

function fmt(amount) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(amount);
}

export default function LoanList() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { selectedIllaka, selectedMaalik } = useIllaka();
  const [loans, setLoans] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [misalFilter, setMisalFilter] = useState("");
  const [misals, setMisals] = useState([]);
  const [page, setPage] = useState(0);
  const limit = 20;

  // Fetch misals when illaka changes
  useEffect(() => {
    setMisalFilter("");
    setMisals([]);
    if (!selectedIllaka?.id) return;
    axios.get(`${API}/misals?illaka_id=${selectedIllaka.id}`, { withCredentials: true })
      .then(r => setMisals(r.data || []))
      .catch(() => {});
  }, [selectedIllaka]);

  const fetchLoans = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: limit.toString(), skip: (page * limit).toString() });
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);
      if (misalFilter) params.append("misal_id", misalFilter);
      if (selectedIllaka) params.append("illaka_id", selectedIllaka.id);
      else if (selectedMaalik) params.append("maalik_id", selectedMaalik.id);
      const res = await axios.get(`${API}/loans?${params}`, { withCredentials: true });
      setLoans(res.data.loans || []);
      setTotal(res.data.total || 0);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const t = setTimeout(fetchLoans, 300);
    return () => clearTimeout(t);
  }, [search, statusFilter, misalFilter, page, selectedIllaka, selectedMaalik]);

  const canCreate = user?.role === "muneem" || user?.role === "sipahi";
  const canQuickAdd = user?.role === "admin" || user?.role === "maalik";
  const [showQuickAdd, setShowQuickAdd] = useState(false);

  return (
    <>
    <div className="p-4 sm:p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground font-['Outfit']">Loans / कर्ज</h1>
          <p className="text-muted-foreground text-sm">{total} total loan records</p>
        </div>
        {canCreate && (
          <button
            onClick={() => navigate("/loans/new")}
            className="flex items-center gap-2 bg-primary text-white px-5 py-3 rounded-lg font-semibold hover:bg-primary/90 active:scale-[0.98] transition-all text-sm"
            data-testid="new-loan-btn"
          >
            <Plus size={16} /> New Loan / नया कर्ज
          </button>
        )}
        {canQuickAdd && (
          <button
            onClick={() => setShowQuickAdd(true)}
            className="flex items-center gap-2 bg-primary text-white px-5 py-3 rounded-lg font-semibold hover:bg-primary/90 active:scale-[0.98] transition-all text-sm"
            data-testid="quick-add-loan-btn"
          >
            <Zap size={16} /> Quick Add Loan
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
            onChange={e => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search by client name or phone..."
            className="bk-input pl-11"
            data-testid="loan-search-input"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => { setStatusFilter(e.target.value); setPage(0); }}
          className="bk-input sm:w-44"
          data-testid="loan-status-filter"
        >
          <option value="">All Status / सभी</option>
          <option value="active">Active / सक्रिय</option>
          <option value="overdue">Overdue / बकाया</option>
          <option value="closed">Closed / बंद</option>
        </select>
        {misals.length > 0 && (
          <select
            value={misalFilter}
            onChange={e => { setMisalFilter(e.target.value); setPage(0); }}
            className="bk-input sm:w-44"
            data-testid="loan-misal-filter"
          >
            <option value="">All Misals / सभी मिसाल</option>
            {misals.map(m => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        )}
      </div>

      {/* Table */}
      <div className="bk-card overflow-hidden p-0">
        <div className="hidden sm:grid grid-cols-[1fr_1fr_1fr_1fr_auto_auto] gap-4 px-5 py-3 bg-muted/50 border-b border-border text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          <span>Client / ग्राहक</span>
          <span>Principal / मूलधन</span>
          <span>Interest / ब्याज</span>
          <span>Paid / चुकाया</span>
          <span>Status</span>
          <span>Date</span>
        </div>

        {loading ? (
          <div className="p-12 flex items-center justify-center">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : loans.length === 0 ? (
          <div className="p-12 text-center text-muted-foreground" data-testid="no-loans">
            <TrendingUp size={40} className="mx-auto mb-3 opacity-30" />
            <p className="font-medium">No loans found</p>
            <p className="text-sm">कोई कर्ज नहीं मिला</p>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {loans.map(loan => {
              const outstanding = loan.principal_amount - (loan.total_paid || 0);
              return (
                <div
                  key={loan.id}
                  onClick={() => navigate(`/loans/${loan.id}`)}
                  className="flex sm:grid sm:grid-cols-[1fr_1fr_1fr_1fr_auto_auto] gap-4 items-center px-5 py-4 hover:bg-muted/30 cursor-pointer transition-colors"
                  data-testid={`loan-row-${loan.id}`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 bg-primary/10 rounded-full flex items-center justify-center flex-shrink-0">
                      <span className="text-primary font-bold text-sm">{loan.client_name?.charAt(0)?.toUpperCase() || "?"}</span>
                    </div>
                    <div>
                      <p className="font-semibold text-foreground text-sm">
                        {(user?.role === "muneem" || user?.role === "sipahi")
                          ? (loan.client_name_hindi || loan.client_name)
                          : loan.client_name}
                      </p>
                      {(user?.role === "muneem" || user?.role === "sipahi") && loan.client_name_hindi && (
                        <p className="text-xs text-muted-foreground">{loan.client_name}</p>
                      )}
                      <p className="text-xs text-muted-foreground font-mono">{loan.loan_number || loan.id?.slice(-6)}</p>
                    </div>
                  </div>
                  <div className="hidden sm:block">
                    <p className="text-sm font-semibold text-foreground">{fmt(loan.principal_amount)}</p>
                    <p className="text-xs text-muted-foreground">{loan.interest_rate}% / month</p>
                  </div>
                  <div className="hidden sm:block">
                    <p className="text-sm text-foreground">{fmt(outstanding)}</p>
                    <p className="text-xs text-muted-foreground">outstanding</p>
                  </div>
                  <div className="hidden sm:block">
                    <p className="text-sm text-green-700 font-medium">{fmt(loan.total_paid || 0)}</p>
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full font-semibold whitespace-nowrap ${STATUS_BADGE[loan.status] || ""}`}>
                    {STATUS_LABELS[loan.status] || loan.status}
                  </span>
                  <span className="text-xs text-muted-foreground hidden sm:block whitespace-nowrap">
                    {loan.loan_date ? new Date(loan.loan_date).toLocaleDateString("en-IN") : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {total > limit && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-border">
            <p className="text-sm text-muted-foreground">
              Showing {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total}
            </p>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} className="px-3 py-1.5 rounded border border-border text-sm hover:bg-muted disabled:opacity-40" data-testid="prev-page">Previous</button>
              <button onClick={() => setPage(p => p + 1)} disabled={(page + 1) * limit >= total} className="px-3 py-1.5 rounded border border-border text-sm hover:bg-muted disabled:opacity-40" data-testid="next-page">Next</button>
            </div>
          </div>
        )}
      </div>
    </div>
    <QuickAddLoanModal
      open={showQuickAdd}
      onClose={() => setShowQuickAdd(false)}
      onSuccess={() => { fetchLoans(); }}
    />
  </>
  );
}
