import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { API, fmt, MONTHS } from "./utils";

export function BalanceSheet({ month, illakaId, maalikId, refresh }) {
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
      const res = await fetch(`${API}/api/accounts/balance-sheet?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load Balance Sheet"); }
    finally { setLoading(false); }
  }, [month, illakaId, maalikId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const assets = data?.assets || [];
  const liabilities = data?.liabilities || [];
  const equityItems = data?.equity_items || [];
  const netProfit = data?.net_profit || 0;
  const openingCapital = data?.opening_capital || 0;

  function SideSection({ title, color, items, footer }) {
    return (
      <div className="bg-card border border-border rounded-xl overflow-hidden">
        <div className={`px-4 py-3 ${color} border-b border-border`}>
          <span className="font-bold text-sm">{title}</span>
        </div>
        <table className="w-full text-sm">
          <tbody>
            {items.map((item, i) => (
              <tr key={i} className="border-b border-border hover:bg-muted/20">
                <td className="px-4 py-2.5">
                  <div className="font-medium">{item.account_head_name}</div>
                  <div className="text-xs text-muted-foreground">{item.group_name}</div>
                </td>
                <td className={`px-4 py-2.5 text-right font-bold font-mono ${item.amount < 0 ? "text-red-600" : ""}`}>
                  {fmt(Math.abs(item.amount))}
                  {item.amount < 0 && <span className="text-xs ml-1">(Dr)</span>}
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={2} className="px-4 py-6 text-center text-muted-foreground text-xs">Nil</td></tr>}
          </tbody>
        </table>
        {footer}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Balance Sheet</h2>
          <p className="text-sm text-muted-foreground">As of {label}</p>
        </div>
        {data && (
          <span className={`text-xs font-bold px-3 py-1 rounded-full ${data.is_balanced ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
            {data.is_balanced ? "✓ Balanced" : "✓ Balanced (with capital plug)"}
          </span>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        {/* LEFT: Capital & Liabilities */}
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 bg-purple-50 border-b border-border">
              <span className="font-bold text-sm text-purple-800">Capital & Reserves</span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {equityItems.map((e, i) => (
                  <tr key={i} className="border-b border-border hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-medium">{e.account_head_name}</td>
                    <td className="px-4 py-2.5 text-right font-bold font-mono">{fmt(e.amount)}</td>
                  </tr>
                ))}
                {openingCapital !== 0 && (
                  <tr className="border-b border-border hover:bg-muted/20">
                    <td className="px-4 py-2.5 font-medium">
                      Opening / Owner's Capital
                      <div className="text-xs text-muted-foreground">Balancing figure</div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold font-mono">{fmt(Math.abs(openingCapital))}</td>
                  </tr>
                )}
                <tr className="border-b border-border bg-green-50/40">
                  <td className="px-4 py-2.5 font-medium">
                    {netProfit >= 0 ? "Net Profit (Current Period)" : "Net Loss (Current Period)"}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-bold font-mono ${netProfit < 0 ? "text-red-600" : "text-green-700"}`}>
                    {fmt(Math.abs(netProfit))}
                  </td>
                </tr>
              </tbody>
            </table>
            <div className="px-4 py-2.5 bg-purple-50/50 border-t border-border flex justify-between font-bold text-sm">
              <span>Total Capital</span>
              <span className="font-mono">{fmt((data?.total_equity || 0) + openingCapital + netProfit)}</span>
            </div>
          </div>

          <SideSection
            title="Liabilities"
            color="bg-orange-50"
            items={liabilities}
            footer={
              <div className="px-4 py-2.5 bg-orange-50/50 border-t border-border flex justify-between font-bold text-sm">
                <span>Total Liabilities</span>
                <span className="font-mono">{fmt(data?.total_liabilities)}</span>
              </div>
            }
          />

          <div className="px-5 py-3 bg-muted rounded-xl flex justify-between font-bold">
            <span>Total Capital &amp; Liabilities</span>
            <span className="text-lg font-mono">{fmt(data?.total_capital_side)}</span>
          </div>
        </div>

        {/* RIGHT: Assets */}
        <div className="space-y-4">
          <SideSection
            title="Assets"
            color="bg-blue-50"
            items={assets}
            footer={null}
          />
          <div className="px-5 py-3 bg-muted rounded-xl flex justify-between font-bold">
            <span>Total Assets</span>
            <span className="text-lg font-mono">{fmt(data?.total_assets)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
