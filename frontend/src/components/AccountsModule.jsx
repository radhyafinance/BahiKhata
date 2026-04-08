import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import { toast } from "sonner";
import {
  BookOpen, TrendingUp, Plus, Settings, RefreshCw,
  Edit3, Scale, Table, Landmark, BarChart3, FileText,
} from "lucide-react";
import FullJournalEntryModal from "./FullJournalEntryModal";
import ExpenseSheet from "./ExpenseSheet";
import { MonthNav } from "./accounts/MonthNav";
import { SimpleEntryModal } from "./accounts/SimpleEntryModal";
import { ManageHeadsModal } from "./accounts/ManageHeadsModal";
import { CashBook } from "./accounts/CashBook";
import { Bid } from "./accounts/Bid";
import { PLSummary } from "./accounts/PLSummary";
import { OpeningBalanceModal } from "./accounts/OpeningBalanceModal";
import { TrialBalance } from "./accounts/TrialBalance";
import { BalanceSheet } from "./accounts/BalanceSheet";
import { API } from "./accounts/utils";

export default function AccountsModule() {
  const { user } = useAuth();
  const { selectedIllaka, filteredIllakas, selectedMaalik } = useIllaka();
  const [searchParams] = useSearchParams();
  const illakaId = selectedIllaka?.id && selectedIllaka.id !== "all" ? selectedIllaka.id : null;
  const maalikId = !illakaId && selectedMaalik ? selectedMaalik.id : null;

  const today = new Date();
  const [month, setMonth] = useState(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`);
  const [activeTab, setActiveTab] = useState(() => {
    const t = searchParams.get("tab");
    return ["cashbook","bid","summary","trial","balancesheet","expense"].includes(t) ? t : "cashbook";
  });
  const [heads, setHeads] = useState([]);
  const [groups, setGroups] = useState([]);
  const [showSimpleEntry, setShowSimpleEntry] = useState(false);
  const [showJournalEntry, setShowJournalEntry] = useState(false);
  const [showHeadsModal, setShowHeadsModal] = useState(false);
  const [showOpeningBalance, setShowOpeningBalance] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [editEntry, setEditEntry] = useState(null);

  const isAdmin = user?.role === "admin";
  const canFullEntry = isAdmin || user?.role === "maalik";

  const loadHeads = useCallback(async () => {
    try {
      const [hRes, gRes] = await Promise.all([
        fetch(`${API}/api/accounts/heads`, { credentials: "include" }),
        fetch(`${API}/api/accounts/groups`, { credentials: "include" }),
      ]);
      setHeads(await hRes.json());
      setGroups(await gRes.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => { loadHeads(); }, [loadHeads]);

  const handleSaved = () => { setRefreshKey(k => k + 1); };

  const handleDeleteEntry = useCallback(async (entryId) => {
    if (!window.confirm("Delete this journal entry? This cannot be undone.")) return;
    try {
      const res = await fetch(`${API}/api/accounts/entries/${entryId}`, {
        method: "DELETE", credentials: "include",
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      toast.success("Entry deleted");
      setRefreshKey(k => k + 1);
    } catch (err) { toast.error(err.message); }
  }, []);

  const handleEditEntry = useCallback(async (entryId) => {
    try {
      const res = await fetch(`${API}/api/accounts/entries/${entryId}`, { credentials: "include" });
      if (!res.ok) throw new Error("Failed to load entry");
      const entry = await res.json();
      const nonCashLine = entry.lines?.find(l => l.group_type === "expense" || l.group_type === "income");
      if (!nonCashLine) { toast.error("Cannot edit this entry type. Delete and recreate using Journal Entry."); return; }
      setEditEntry({
        id: entryId,
        date: entry.date,
        narration: entry.narration,
        amount: nonCashLine.debit > 0 ? nonCashLine.debit : nonCashLine.credit,
        account_head_id: nonCashLine.account_head_id,
        illaka_id: entry.illaka_id,
      });
    } catch (err) { toast.error("Could not load entry for editing"); }
  }, []);

  const tabs = [
    { key: "cashbook", label: "Cash Book", icon: BookOpen },
    { key: "bid", label: "Bid", icon: BarChart3 },
    { key: "summary", label: "P&L Summary", icon: TrendingUp },
    { key: "trial", label: "Trial Balance", icon: Scale },
    { key: "balancesheet", label: "Balance Sheet", icon: Table },
    { key: "expense", label: "Expense Sheet", icon: FileText },
  ];

  const eligibleList = (filteredIllakas || []).filter(i => i.id !== "all");

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">Accounts / खाता</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {selectedIllaka ? selectedIllaka.name : "All Illakas"} · Cash Book & P&L
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <MonthNav month={month} onChange={setMonth} />
          {isAdmin && (
            <button onClick={() => setShowHeadsModal(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="manage-heads-btn">
              <Settings size={15} />
              <span className="hidden sm:inline">Heads</span>
            </button>
          )}
          {canFullEntry && (
            <button onClick={() => setShowOpeningBalance(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="opening-balance-btn">
              <Landmark size={15} />
              <span className="hidden sm:inline">Opening Balance</span>
            </button>
          )}
          {canFullEntry && (
            <button onClick={() => setShowJournalEntry(true)}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-border text-sm font-semibold hover:bg-muted transition-colors"
              data-testid="journal-entry-btn">
              <Edit3 size={15} />
              <span className="hidden sm:inline">Journal Entry</span>
            </button>
          )}
          <button onClick={() => setShowSimpleEntry(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors shadow-sm"
            data-testid="add-entry-btn">
            <Plus size={15} />
            Add Entry
          </button>
        </div>
      </div>

      {/* Illaka warning */}
      {!illakaId && activeTab !== "expense" && (
        <div className="mb-4 p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-sm flex items-center gap-2">
          <RefreshCw size={14} />
          Showing data across all accessible Illakas. Select a specific Illaka for filtered view.
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-muted rounded-xl p-1 mb-5 w-fit overflow-x-auto">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setActiveTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all whitespace-nowrap ${
              activeTab === key ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
            }`}
            data-testid={`tab-${key}`}>
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "cashbook" && <CashBook month={month} illakaId={illakaId} maalikId={maalikId} refresh={refreshKey} user={user} onDelete={handleDeleteEntry} onEdit={handleEditEntry} />}
      {activeTab === "bid" && <Bid month={month} illakaId={illakaId} maalikId={maalikId} refresh={refreshKey} />}
      {activeTab === "summary" && <PLSummary month={month} illakaId={illakaId} maalikId={maalikId} refresh={refreshKey} />}
      {activeTab === "trial" && <TrialBalance month={month} illakaId={illakaId} maalikId={maalikId} refresh={refreshKey} />}
      {activeTab === "balancesheet" && <BalanceSheet month={month} illakaId={illakaId} maalikId={maalikId} refresh={refreshKey} />}
      {activeTab === "expense" && (
        <ExpenseSheet
          illakaId={illakaId}
          illakaName={selectedIllaka?.name}
          month={month}
          eligibleIllakas={eligibleList}
        />
      )}

      {/* Modals */}
      <SimpleEntryModal
        open={showSimpleEntry || !!editEntry}
        onClose={() => { setShowSimpleEntry(false); setEditEntry(null); }}
        onSave={handleSaved}
        heads={heads}
        illakaId={illakaId}
        eligibleIllakas={eligibleList}
        editEntry={editEntry}
      />
      <FullJournalEntryModal
        open={showJournalEntry}
        onClose={() => setShowJournalEntry(false)}
        onSave={handleSaved}
        heads={heads}
        illakaId={illakaId}
        eligibleIllakas={eligibleList}
      />
      <ManageHeadsModal
        open={showHeadsModal}
        onClose={() => setShowHeadsModal(false)}
        heads={heads}
        groups={groups}
        onRefresh={loadHeads}
      />
      {showOpeningBalance && (
        <OpeningBalanceModal
          illakaId={illakaId}
          onClose={() => setShowOpeningBalance(false)}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
