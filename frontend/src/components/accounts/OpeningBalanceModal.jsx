import { useState, useEffect } from "react";
import { toast } from "sonner";
import { Landmark, Trash2, Copy, Plus, Users, RefreshCw } from "lucide-react";
import { API, fmt } from "./utils";

export function OpeningBalanceModal({ illakaId, onClose, onSaved }) {
  const [heads, setHeads] = useState([]);
  const [existing, setExisting] = useState(null);
  const [loadingHeads, setLoadingHeads] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [copying, setCopying] = useState(false);
  const [latestClosing, setLatestClosing] = useState(null);
  // Aasami Khata (Loans Portfolio) is derived from live client balances rather
  // than typed in — keep the computed figure so it can be shown and re-applied.
  const [aasami, setAasami] = useState(null);
  // Ad-hoc named parties → become real account heads on save.
  const [parties, setParties] = useState([]);
  const [date, setDate] = useState(() => {
    const now = new Date();
    const fy = now.getMonth() < 3 ? now.getFullYear() - 1 : now.getFullYear();
    return `${fy}-04-01`;
  });
  const [amounts, setAmounts] = useState({});

  const typeLabel = { asset: "Assets", liability: "Liabilities", equity: "Capital & Equity" };
  const typeHint = { asset: "Debit balance", liability: "Credit balance", equity: "Credit balance" };

  useEffect(() => {
    async function load() {
      setLoadingHeads(true);
      try {
        const res = await fetch(`${API}/api/accounts/heads`, { credentials: "include" });
        const data = await res.json();
        const filtered = (data.heads || data || []).filter(
          h => ["asset", "liability", "equity"].includes(h.group_type)
            && h.is_active !== false
            && h.system_key !== "opening_capital"
        );
        setHeads(filtered);

        const params = new URLSearchParams();
        if (illakaId) params.set("illaka_id", illakaId);
        const eRes = await fetch(`${API}/api/accounts/opening-balance?${params}`, { credentials: "include" });
        const eData = await eRes.json();
        const prefill = {};
        if (eData.entry) {
          setExisting(eData.entry);
          for (const line of eData.entry.lines || []) {
            if (line.account_head_id) {
              prefill[line.account_head_id] = line.debit > 0 ? line.debit : line.credit > 0 ? line.credit : 0;
            }
          }
          if (eData.entry.date) setDate(eData.entry.date);
        }

        // Aasami Khata — total outstanding across live client loans. Fill it in
        // automatically; a saved entry's own figure still wins so an edited
        // opening balance isn't silently overwritten.
        try {
          const aRes = await fetch(`${API}/api/accounts/aasami-balance?${params}`, { credentials: "include" });
          const aData = await aRes.json();
          if (aData.account_head_id) {
            setAasami(aData);
            if (prefill[aData.account_head_id] === undefined && aData.total > 0) {
              prefill[aData.account_head_id] = aData.total;
            }
          }
        } catch { /* non-critical — the field stays manual */ }

        setAmounts(prefill);

        // Check if a year-end closing exists for this illaka
        if (illakaId) {
          try {
            const hRes = await fetch(`${API}/api/loans/year-end-closing/history?illaka_id=${illakaId}`, { credentials: "include" });
            const hData = await hRes.json();
            if (hData.closings?.length > 0) {
              setLatestClosing(hData.closings[0].closing_date);
            }
          } catch { /* silent — not critical */ }
        }
      } catch { toast.error("Failed to load account heads"); }
      finally { setLoadingHeads(false); }
    }
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- API/fetch/toast/setState are stable; only illakaId triggers reload
  }, [illakaId]);

  const partyDr = parties
    .filter(p => p.kind === "debtor")
    .reduce((s, p) => s + (parseFloat(p.amount) || 0), 0);
  const partyCr = parties
    .filter(p => p.kind === "creditor")
    .reduce((s, p) => s + (parseFloat(p.amount) || 0), 0);
  const totalDr = heads
    .filter(h => h.group_type === "asset")
    .reduce((s, h) => s + (parseFloat(amounts[h.id] || amounts[h._id] || 0) || 0), 0) + partyDr;
  const totalCr = heads
    .filter(h => ["liability", "equity"].includes(h.group_type))
    .reduce((s, h) => s + (parseFloat(amounts[h.id] || amounts[h._id] || 0) || 0), 0) + partyCr;
  const capitalPlug = Math.round((totalDr - totalCr) * 100) / 100;

  const addParty = (kind) => setParties(p => [...p, { key: `${kind}-${Date.now()}-${p.length}`, kind, name: "", amount: "" }]);
  const updateParty = (key, patch) => setParties(p => p.map(x => (x.key === key ? { ...x, ...patch } : x)));
  const removeParty = (key) => setParties(p => p.filter(x => x.key !== key));

  async function handleSave() {
    if (!illakaId) { toast.error("Please select an Illaka before entering opening balance"); return; }
    setSaving(true);
    try {
      const lines = heads
        .filter(h => parseFloat(amounts[h.id || h._id] || 0) > 0)
        .map(h => {
          const hid = h.id || h._id;
          const amt = parseFloat(amounts[hid] || 0);
          return h.group_type === "asset"
            ? { account_head_id: hid, debit: amt, credit: 0 }
            : { account_head_id: hid, debit: 0, credit: amt };
        });

      // Named parties — the backend creates/reuses a real account head per name.
      const namedParties = parties.filter(p => p.name.trim() && parseFloat(p.amount) > 0);
      if (namedParties.length !== parties.filter(p => p.name.trim() || p.amount).length) {
        toast.error("Every party needs both a name and an amount");
        setSaving(false);
        return;
      }
      for (const p of namedParties) {
        const amt = parseFloat(p.amount);
        lines.push(p.kind === "debtor"
          ? { new_head_name: p.name.trim(), new_head_kind: "debtor", debit: amt, credit: 0 }
          : { new_head_name: p.name.trim(), new_head_kind: "creditor", debit: 0, credit: amt });
      }

      if (lines.length === 0) { toast.error("Enter at least one non-zero amount"); setSaving(false); return; }
      const res = await fetch(`${API}/api/accounts/opening-balance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ illaka_id: illakaId, date, lines }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Failed to save"); return; }
      toast.success("Opening balance saved");
      onSaved();
      onClose();
    } catch { toast.error("Failed to save opening balance"); }
    finally { setSaving(false); }
  }

  async function handleDelete() {
    if (!illakaId) return;
    setDeleting(true);
    try {
      const res = await fetch(`${API}/api/accounts/opening-balance?illaka_id=${illakaId}`, {
        method: "DELETE", credentials: "include",
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Failed to delete"); return; }
      toast.success("Opening balance deleted");
      setExisting(null);
      setAmounts({});
      onSaved();
    } catch { toast.error("Failed to delete"); }
    finally { setDeleting(false); }
  }

  async function handleCopyFromClosing() {
    if (!illakaId || !latestClosing) return;
    setCopying(true);
    try {
      const res = await fetch(
        `${API}/api/accounts/closing-balances?illaka_id=${illakaId}&closing_date=${latestClosing}`,
        { credentials: "include" }
      );
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || "Failed to copy closing balances"); return; }

      // Pre-fill amounts by account_head_id
      const newAmounts = {};
      for (const item of data.items || []) {
        if (item.balance > 0) {
          newAmounts[item.account_head_id] = item.balance;
        }
      }
      setAmounts(newAmounts);

      // Set date to the day after the closing (April 1 of next FY)
      const closingDateObj = new Date(latestClosing + "T00:00:00");
      closingDateObj.setDate(closingDateObj.getDate() + 1);
      setDate(closingDateObj.toISOString().split("T")[0]);

      toast.success(`Copied balances from ${latestClosing} closing`);
    } catch { toast.error("Failed to copy closing balances"); }
    finally { setCopying(false); }
  }

  const typeOrder = ["asset", "liability", "equity"];
  const grouped = heads.reduce((acc, h) => {
    const t = h.group_type;
    if (!acc[t]) acc[t] = [];
    acc[t].push(h);
    return acc;
  }, {});

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-background rounded-2xl w-full max-w-xl max-h-[90vh] flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <Landmark className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="font-bold text-base">Opening Balance</h2>
              <p className="text-xs text-muted-foreground">Set the starting balances for your books</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xl leading-none">&times;</button>
        </div>

        {loadingHeads ? (
          <div className="flex items-center justify-center py-16">
            <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            <div className="overflow-y-auto flex-1 px-5 py-4 space-y-5">
              <div>
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wide block mb-1.5">
                  As of Date
                </label>
                <input
                  type="date"
                  value={date}
                  onChange={e => setDate(e.target.value)}
                  className="w-full border border-border rounded-lg px-3 py-2 text-sm bg-background"
                  data-testid="ob-date-input"
                />
              </div>

              {/* Copy from Year-End Closing — only shown after a closing exists */}
              {latestClosing && (
                <div className="flex items-center justify-between rounded-xl border border-primary/30 bg-primary/5 px-4 py-3">
                  <div>
                    <p className="text-xs font-bold text-primary">Year-End Closing found</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{latestClosing}</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleCopyFromClosing}
                    disabled={copying}
                    className="flex items-center gap-2 text-xs font-semibold px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
                    data-testid="ob-copy-closing-btn"
                  >
                    <Copy size={13} />
                    {copying ? "Copying…" : "Copy as Opening"}
                  </button>
                </div>
              )}

              {typeOrder.filter(t => grouped[t]?.length).map(t => (
                <div key={t}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{typeLabel[t]}</span>
                    <span className="text-xs text-muted-foreground">({typeHint[t]})</span>
                  </div>
                  <div className="space-y-2">
                    {grouped[t].map(h => {
                      const hid = h.id || h._id;
                      const isAasami = aasami && hid === aasami.account_head_id;
                      return (
                        <div key={hid} className="flex items-center gap-3">
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium truncate">
                              {h.name}
                              {isAasami && (
                                <span className="ml-2 text-[10px] font-bold text-primary bg-primary/10 px-1.5 py-0.5 rounded-full align-middle">
                                  AASAMI KHATA
                                </span>
                              )}
                            </p>
                            {isAasami ? (
                              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                                Auto-filled from {aasami.loan_count} live client balances
                                <button
                                  type="button"
                                  onClick={() => setAmounts(a => ({ ...a, [hid]: aasami.total }))}
                                  className="inline-flex items-center gap-0.5 text-primary hover:underline font-semibold"
                                  title="Recalculate from client balances"
                                  data-testid="ob-aasami-refresh"
                                >
                                  <RefreshCw size={10} /> refresh
                                </button>
                              </p>
                            ) : (
                              <p className="text-xs text-muted-foreground">{h.group_name}</p>
                            )}
                          </div>
                          <div className="relative w-36 shrink-0">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">₹</span>
                            <input
                              type="number"
                              min="0"
                              placeholder="0"
                              value={amounts[hid] || ""}
                              onChange={e => setAmounts(a => ({ ...a, [hid]: e.target.value }))}
                              className="w-full pl-7 pr-3 py-2 border border-border rounded-lg text-sm bg-background text-right"
                              data-testid={`ob-amount-${hid}`}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}

              {/* ── Named sundry debtors / creditors ───────────────────────── */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Users size={13} className="text-muted-foreground" />
                  <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
                    Sundry Debtors &amp; Creditors
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mb-2">
                  Named parties. Each becomes an account head you can post to later.
                </p>

                {parties.length > 0 && (
                  <div className="space-y-2 mb-2">
                    {parties.map(p => (
                      <div key={p.key} className="flex items-center gap-2">
                        <select
                          value={p.kind}
                          onChange={e => updateParty(p.key, { kind: e.target.value })}
                          className="border border-border rounded-lg px-2 py-2 text-xs bg-background shrink-0"
                          data-testid={`ob-party-kind-${p.key}`}
                        >
                          <option value="debtor">Debtor (Dr)</option>
                          <option value="creditor">Creditor (Cr)</option>
                        </select>
                        <input
                          type="text"
                          placeholder="Party name"
                          value={p.name}
                          onChange={e => updateParty(p.key, { name: e.target.value })}
                          className="flex-1 min-w-0 border border-border rounded-lg px-3 py-2 text-sm bg-background"
                          data-testid={`ob-party-name-${p.key}`}
                        />
                        <div className="relative w-28 shrink-0">
                          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground text-sm">₹</span>
                          <input
                            type="number"
                            min="0"
                            placeholder="0"
                            value={p.amount}
                            onChange={e => updateParty(p.key, { amount: e.target.value })}
                            className="w-full pl-6 pr-2 py-2 border border-border rounded-lg text-sm bg-background text-right"
                            data-testid={`ob-party-amount-${p.key}`}
                          />
                        </div>
                        <button
                          type="button"
                          onClick={() => removeParty(p.key)}
                          className="p-2 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-lg transition-colors shrink-0"
                          title="Remove party"
                          data-testid={`ob-party-remove-${p.key}`}
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => addParty("debtor")}
                    className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
                    data-testid="ob-add-debtor"
                  >
                    <Plus size={13} /> Add Debtor
                  </button>
                  <button
                    type="button"
                    onClick={() => addParty("creditor")}
                    className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-lg border border-border hover:bg-muted transition-colors"
                    data-testid="ob-add-creditor"
                  >
                    <Plus size={13} /> Add Creditor
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-dashed border-primary/40 bg-primary/5 p-4 space-y-2">
                <p className="text-xs font-bold text-primary uppercase tracking-wide">Auto-calculated</p>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Total Assets (Dr)</span>
                  <span className="font-bold font-mono">{fmt(totalDr)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Total Liabilities &amp; Equity (Cr)</span>
                  <span className="font-bold font-mono">{fmt(totalCr)}</span>
                </div>
                <div className="border-t border-primary/20 pt-2 flex justify-between text-sm">
                  <span className="font-semibold">Opening Capital (plug)</span>
                  <span className={`font-bold font-mono ${capitalPlug < 0 ? "text-red-600" : "text-green-700"}`}>
                    {fmt(Math.abs(capitalPlug))}
                    {capitalPlug < 0 && <span className="text-xs ml-1">(Dr — unusual)</span>}
                  </span>
                </div>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-border flex items-center gap-3">
              {existing && (
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex items-center gap-2 text-sm text-red-600 hover:text-red-700 border border-red-200 rounded-lg px-3 py-2 hover:bg-red-50 transition-colors disabled:opacity-50"
                  data-testid="ob-delete-btn"
                >
                  <Trash2 className="w-4 h-4" />
                  {deleting ? "Deleting…" : "Delete"}
                </button>
              )}
              <div className="flex-1" />
              <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted transition-colors">
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !illakaId}
                className="px-5 py-2 text-sm rounded-lg bg-primary text-primary-foreground font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50"
                data-testid="ob-save-btn"
              >
                {saving ? "Saving…" : existing ? "Update" : "Save Opening Balance"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
