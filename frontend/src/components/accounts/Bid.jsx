import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import {
  BookOpen, TrendingUp, TrendingDown, ArrowUpCircle,
  ArrowDownCircle, IndianRupee, BarChart3, Zap,
} from "lucide-react";
import { API, fmt } from "./utils";

export function Bid({ month, illakaId, maalikId, refresh }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      else if (maalikId) params.set("maalik_id", maalikId);
      const res = await fetch(`${API}/api/accounts/bid?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load Bid"); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- API/toast/setState are stable module-level constants
  }, [month, illakaId, maalikId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const drTotals = data?.dr_totals || [];
  const crTotals = data?.cr_totals || [];
  const isEmpty = drTotals.length === 0 && crTotals.length === 0;
  const openingBal = data?.opening_balance || 0;
  const closingBal = data?.closing_balance || 0;
  // Both columns foot to the same figure once b/d and c/d are included.
  const drFooting = Math.round(((data?.total_dr || 0) + openingBal) * 100) / 100;
  const crFooting = Math.round(((data?.total_cr || 0) + closingBal) * 100) / 100;

  return (
    <div>
      {/* Header summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {[
          { label: "Opening Cash", value: data?.opening_balance, color: "text-slate-600", icon: BookOpen },
          { label: "Total Receipts", value: data?.total_dr, color: "text-green-600", icon: ArrowUpCircle },
          { label: "Total Payments", value: data?.total_cr, color: "text-red-600", icon: ArrowDownCircle },
          { label: "Closing Cash", value: data?.closing_balance, color: (data?.closing_balance || 0) >= 0 ? "text-primary" : "text-destructive", icon: IndianRupee },
        ].map(({ label, value, color, icon: Icon }) => (
          <div key={label} className="bg-card border border-border rounded-xl p-4">
            <div className={`flex items-center gap-2 ${color} mb-1`}>
              <Icon size={15} />
              <span className="text-xs font-semibold">{label}</span>
            </div>
            <p className={`text-xl font-bold ${color}`}>{fmt(value)}</p>
          </div>
        ))}
      </div>

      {isEmpty ? (
        <div className="text-center py-16 text-muted-foreground">
          <BarChart3 size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">No transactions this month</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-border rounded-xl overflow-hidden">
          {/* LEFT: Dr totals */}
          <div className="border-b lg:border-b-0 lg:border-r border-border">
            <div className="bg-green-50 dark:bg-green-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <TrendingUp size={15} className="text-green-600" />
                <span className="font-bold text-sm text-green-800">Dr — Receipts (Total)</span>
              </div>
              <span className="font-bold text-green-700">{fmt(data?.total_dr)}</span>
            </div>
            <div className="divide-y divide-border">
              {/* Opening balance leads the receipts side, as a cash book reads */}
              {openingBal !== 0 && (
                <div className="flex items-center justify-between px-4 py-3 bg-slate-50 dark:bg-slate-900/30">
                  <div>
                    <p className="text-sm font-semibold">To Opening Cash b/d</p>
                    <p className="text-xs text-muted-foreground">Carried forward</p>
                  </div>
                  <span className="font-bold text-slate-700 dark:text-slate-300">{fmt(openingBal)}</span>
                </div>
              )}
              {drTotals.map((item, i) => (
                <div key={item.type === "emi_total" ? "emi_total" : (item.label || i)} className="p-4">
                  {item.type === "emi_total" ? (
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <Zap size={13} className="text-amber-500" />
                          <span className="font-bold text-sm">EMI Collections</span>
                        </div>
                        <span className="font-bold text-green-700">{fmt(item.total)}</span>
                      </div>
                      {item.misal_breakdown?.map((mb, mi) => (
                        <div key={mi} className="flex items-center justify-between ml-5 py-0.5">
                          <span className="text-xs text-muted-foreground">{mb.misal_name}</span>
                          <span className="text-xs font-semibold text-green-600">{fmt(mb.total)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{item.label}</span>
                      <span className="font-bold text-green-700">{fmt(item.total)}</span>
                    </div>
                  )}
                </div>
              ))}
              {drTotals.length === 0 && <div className="px-4 py-8 text-center text-sm text-muted-foreground">No receipts</div>}
            </div>
            <div className="px-4 py-3 bg-green-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL</span>
              <span className="font-bold text-green-700">{fmt(drFooting)}</span>
            </div>
          </div>

          {/* RIGHT: Cr totals */}
          <div>
            <div className="bg-red-50 dark:bg-red-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <TrendingDown size={15} className="text-red-600" />
                <span className="font-bold text-sm text-red-800">Cr — Payments (Total)</span>
              </div>
              <span className="font-bold text-red-700">{fmt(data?.total_cr)}</span>
            </div>
            <div className="divide-y divide-border">
              {crTotals.map((item) => (
                item.type === "expense_group" ? (
                  <div key="expense_group" className="p-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-bold text-sm">Expenses</span>
                      <span className="font-bold text-red-700">{fmt(item.total)}</span>
                    </div>
                    {item.breakdown?.map((b, bi) => (
                      <div key={bi} className="flex items-center justify-between ml-5 py-0.5">
                        <span className="text-xs text-muted-foreground truncate max-w-[200px]">{b.account_head_name}</span>
                        <span className="text-xs font-semibold text-red-600">{fmt(b.total)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div key={item.account_head_name} className="flex items-center justify-between px-4 py-3">
                    <div>
                      <p className="text-sm font-medium">{item.account_head_name}</p>
                      <p className="text-xs text-muted-foreground">{item.group_name}</p>
                    </div>
                    <span className="font-bold text-red-700">{fmt(item.total)}</span>
                  </div>
                )
              ))}
              {crTotals.length === 0 && <div className="px-4 py-8 text-center text-sm text-muted-foreground">No payments</div>}

              {/* Closing cash closes the payments side */}
              <div className="flex items-center justify-between px-4 py-3 bg-primary/5">
                <div>
                  <p className="text-sm font-semibold">By Closing Cash c/d</p>
                  <p className="text-xs text-muted-foreground">Cash in hand at month end</p>
                </div>
                <span className={`font-bold ${closingBal >= 0 ? "text-primary" : "text-destructive"}`}>{fmt(closingBal)}</span>
              </div>
            </div>
            <div className="px-4 py-3 bg-red-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL</span>
              <span className="font-bold text-red-700">{fmt(crFooting)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Closing balance */}
      {!isEmpty && (
        <div className={`mt-3 flex items-center justify-between px-5 py-3 rounded-xl border-2 ${(data?.closing_balance || 0) >= 0 ? "border-primary/30 bg-primary/5" : "border-destructive/30 bg-destructive/5"}`}>
          <span className="font-bold text-sm">Closing Cash</span>
          <span className={`text-xl font-bold ${(data?.closing_balance || 0) >= 0 ? "text-primary" : "text-destructive"}`}>
            {fmt(data?.closing_balance)}
          </span>
        </div>
      )}
    </div>
  );
}
