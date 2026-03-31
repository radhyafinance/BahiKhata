import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { TrendingUp, TrendingDown, BarChart3 } from "lucide-react";
import { API, fmt } from "./utils";

export function PLSummary({ month, illakaId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      const res = await fetch(`${API}/api/accounts/summary?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load summary"); }
    finally { setLoading(false); }
  }, [month, illakaId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const income = data?.income || [];
  const expenses = data?.expenses || [];

  return (
    <div className="space-y-5">
      <div className={`rounded-2xl p-5 border-2 ${(data?.net_profit || 0) >= 0 ? "border-green-200 bg-green-50" : "border-red-200 bg-red-50"}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-muted-foreground">Net Profit / Loss</p>
            <p className={`text-3xl font-bold mt-1 ${(data?.net_profit || 0) >= 0 ? "text-green-700" : "text-red-700"}`}>
              {fmt(data?.net_profit)}
            </p>
          </div>
          <BarChart3 size={40} className={`opacity-20 ${(data?.net_profit || 0) >= 0 ? "text-green-600" : "text-red-600"}`} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Total Income</p>
            <p className="text-lg font-bold text-green-700">{fmt(data?.total_income)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Total Expense</p>
            <p className="text-lg font-bold text-red-700">{fmt(data?.total_expense)}</p>
          </div>
        </div>
      </div>
      <div className="grid lg:grid-cols-2 gap-5">
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-green-50 border-b border-border">
            <TrendingUp size={16} className="text-green-600" />
            <h3 className="font-bold text-green-800 text-sm">Income</h3>
            <span className="ml-auto font-bold text-green-700">{fmt(data?.total_income)}</span>
          </div>
          {income.length === 0 ? <p className="text-center text-sm text-muted-foreground py-8">No income entries</p> : (
            <table className="w-full text-sm">
              <tbody>
                {income.map((h, i) => (
                  <tr key={i} className="border-b border-border hover:bg-muted/30">
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{h.account_head_name}</div>
                      <div className="text-xs text-muted-foreground">{h.group_name}</div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-green-700">
                      {fmt(h.total_credit - h.total_debit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-red-50 border-b border-border">
            <TrendingDown size={16} className="text-red-600" />
            <h3 className="font-bold text-red-800 text-sm">Expenses</h3>
            <span className="ml-auto font-bold text-red-700">{fmt(data?.total_expense)}</span>
          </div>
          {expenses.length === 0 ? <p className="text-center text-sm text-muted-foreground py-8">No expense entries</p> : (
            <table className="w-full text-sm">
              <tbody>
                {expenses.map((h, i) => (
                  <tr key={i} className="border-b border-border hover:bg-muted/30">
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{h.account_head_name}</div>
                      <div className="text-xs text-muted-foreground">{h.group_name}</div>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold text-red-700">
                      {fmt(h.total_debit - h.total_credit)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
