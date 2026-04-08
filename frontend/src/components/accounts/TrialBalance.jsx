import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { API, fmt, MONTHS } from "./utils";

export function TrialBalance({ month, illakaId, maalikId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [y, m] = month.split("-").map(Number);
  const label = `${MONTHS[m - 1]} ${y}`;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      else if (maalikId) params.set("maalik_id", maalikId);
      const res = await fetch(`${API}/api/accounts/trial-balance?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load Trial Balance"); }
    finally { setLoading(false); }
  }, [month, illakaId, maalikId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const rows = data?.rows || [];
  const typeLabel = { asset: "Assets", liability: "Liabilities", equity: "Equity / Capital", income: "Income", expense: "Expenses" };
  const typeColor = { asset: "text-blue-700", liability: "text-orange-700", equity: "text-purple-700", income: "text-green-700", expense: "text-red-700" };
  const typeBg = { asset: "bg-blue-50/60", liability: "bg-orange-50/60", equity: "bg-purple-50/60", income: "bg-green-50/60", expense: "bg-red-50/60" };

  const grouped = rows.reduce((acc, r) => {
    const t = r.group_type || "other";
    if (!acc[t]) acc[t] = [];
    acc[t].push(r);
    return acc;
  }, {});
  const typeOrder = ["asset", "liability", "equity", "income", "expense"];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Trial Balance</h2>
          <p className="text-sm text-muted-foreground">Cumulative as of {label}</p>
        </div>
        {data && (
          <span className={`text-xs font-bold px-3 py-1 rounded-full ${data.is_balanced ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
            {data.is_balanced ? "✓ Balanced" : "⚠ Out of Balance"}
          </span>
        )}
      </div>

      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className="grid grid-cols-12 text-xs font-bold text-muted-foreground uppercase tracking-wide px-4 py-2.5 bg-muted/50 border-b border-border">
          <div className="col-span-5">Account Head</div>
          <div className="col-span-3 text-center">Group</div>
          <div className="col-span-2 text-right">Debit</div>
          <div className="col-span-2 text-right">Credit</div>
        </div>

        {rows.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground py-10">No entries found</p>
        ) : (
          typeOrder.filter(t => grouped[t]?.length).map(t => (
            <div key={t}>
              <div className={`px-4 py-2 ${typeBg[t]} border-b border-border`}>
                <span className={`text-xs font-bold uppercase tracking-wide ${typeColor[t]}`}>{typeLabel[t]}</span>
              </div>
              {grouped[t].map((row, i) => (
                <div key={i} className="grid grid-cols-12 px-4 py-2.5 border-b border-border hover:bg-muted/20 text-sm">
                  <div className="col-span-5 font-medium truncate">{row.account_head_name}</div>
                  <div className="col-span-3 text-center text-xs text-muted-foreground truncate">{row.group_name}</div>
                  <div className="col-span-2 text-right text-blue-700 font-mono">
                    {row.total_debit > 0 ? fmt(row.total_debit) : "—"}
                  </div>
                  <div className="col-span-2 text-right text-red-700 font-mono">
                    {row.total_credit > 0 ? fmt(row.total_credit) : "—"}
                  </div>
                </div>
              ))}
            </div>
          ))
        )}

        {rows.length > 0 && (
          <div className="grid grid-cols-12 px-4 py-3 bg-muted/70 border-t-2 border-border font-bold text-sm">
            <div className="col-span-8">TOTAL</div>
            <div className="col-span-2 text-right text-blue-800">{fmt(data?.total_debit)}</div>
            <div className="col-span-2 text-right text-red-800">{fmt(data?.total_credit)}</div>
          </div>
        )}
      </div>
    </div>
  );
}
