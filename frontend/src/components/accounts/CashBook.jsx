import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import {
  BookOpen, ArrowUpCircle, ArrowDownCircle, IndianRupee,
  Zap, Trash2, Edit3,
} from "lucide-react";
import { API, fmt } from "./utils";

export function CashBook({ month, illakaId, maalikId, refresh, user, onDelete, onEdit }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const canAct = user?.role === "admin" || user?.role === "maalik";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ month });
      if (illakaId) params.set("illaka_id", illakaId);
      else if (maalikId) params.set("maalik_id", maalikId);
      const res = await fetch(`${API}/api/accounts/cashbook?${params}`, { credentials: "include" });
      setData(await res.json());
    } catch { toast.error("Failed to load cashbook"); }
    finally { setLoading(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- API/toast/setState are stable module-level constants
  }, [month, illakaId, maalikId, refresh]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex items-center justify-center py-20"><div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const drSections = data?.dr_sections || [];
  const crEntries = data?.cr_entries || [];
  // Payments grouped as {regular…, expense_group}; fall back to the flat list
  // if an older backend is still serving cr_entries only.
  const crSections = data?.cr_sections || crEntries.map((e) => ({ type: "regular", ...e }));
  const openingBal = data?.opening_balance || 0;
  const closingBal = data?.closing_balance || 0;
  // A cash book reads "To Balance b/d" first and "By Balance c/d" last, so both
  // sides foot to the same figure.
  const drFooting = Math.round(((data?.total_receipts || 0) + openingBal) * 100) / 100;

  return (
    <div>
      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
        {[
          { label: "Opening Cash", value: data?.opening_balance, icon: BookOpen, color: "text-slate-600" },
          { label: "Total Receipts", value: data?.total_receipts, icon: ArrowUpCircle, color: "text-green-600" },
          { label: "Total Payments", value: data?.total_payments, icon: ArrowDownCircle, color: "text-red-600" },
          { label: "Closing Cash", value: data?.closing_balance, icon: IndianRupee, color: "text-primary" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-card border border-border rounded-xl p-4">
            <div className={`flex items-center gap-2 ${color} mb-1`}>
              <Icon size={15} />
              <span className="text-xs font-semibold">{label}</span>
            </div>
            <p className={`text-xl font-bold ${color}`}>{fmt(value)}</p>
          </div>
        ))}
      </div>

      {/* Two-column cashbook */}
      {drSections.length === 0 && crEntries.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <BookOpen size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-medium">No cash transactions this month</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border border-border rounded-xl overflow-hidden">
          {/* LEFT: Dr / Receipts */}
          <div className="border-b lg:border-b-0 lg:border-r border-border">
            <div className="bg-green-50 dark:bg-green-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <ArrowUpCircle size={15} className="text-green-600" />
                <span className="font-bold text-sm text-green-800 dark:text-green-300">Dr — Receipts</span>
              </div>
              <span className="font-bold text-green-700 dark:text-green-400">{fmt(data?.total_receipts)}</span>
            </div>

            <div className="divide-y divide-border">
              {/* Opening balance carried forward — always the first receipt line */}
              {openingBal !== 0 && (
                <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 dark:bg-slate-900/30">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold truncate">To Opening Cash b/d</p>
                    <p className="text-xs text-muted-foreground">Carried forward</p>
                  </div>
                  <span className="text-sm font-bold text-slate-700 dark:text-slate-300 ml-2">{fmt(openingBal)}</span>
                </div>
              )}
              {drSections.map((section, idx) => {
                if (section.type === "emi_group") {
                  return (
                    <div key={idx} className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <Zap size={13} className="text-amber-500" />
                          <span className="text-sm font-bold">EMI Collections</span>
                        </div>
                        <span className="text-sm font-bold text-green-700">{fmt(section.total)}</span>
                      </div>
                      {section.misals?.map((misal, mi) => (
                        <div key={mi} className="ml-4 mb-2">
                          <div className="flex items-center justify-between py-1">
                            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                              {misal.misal_name}
                            </span>
                            <span className="text-xs font-bold text-green-600">{fmt(misal.total)}</span>
                          </div>
                          {misal.entries?.map((e, ei) => (
                            <div key={ei} className="flex items-center justify-between py-0.5 ml-2">
                              <span className="text-xs text-muted-foreground truncate max-w-[160px]">
                                {e.client_name || e.narration}
                              </span>
                              <div className="flex items-center gap-1">
                                <span className="text-xs font-medium">{fmt(e.amount)}</span>
                                {canAct && (
                                  <button onClick={() => onDelete(e.entry_id)}
                                    className="p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                                    title="Delete EMI entry" data-testid={`delete-emi-${e.entry_id}`}>
                                    <Trash2 size={11} />
                                  </button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  );
                }
                return (
                  <div key={idx} className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{section.narration}</p>
                      <p className="text-xs text-muted-foreground">{section.date}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-2">
                      <span className="text-sm font-bold text-green-700">{fmt(section.amount)}</span>
                      {canAct && (
                        <div className="flex gap-0.5">
                          {section.entry_type === "expense_voucher" && (
                            <button onClick={() => onEdit(section.entry_id)}
                              className="p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded transition-colors"
                              title="Edit entry" data-testid={`edit-entry-${section.entry_id}`}>
                              <Edit3 size={12} />
                            </button>
                          )}
                          <button onClick={() => onDelete(section.entry_id)}
                            className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                            title="Delete entry" data-testid={`delete-entry-${section.entry_id}`}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {drSections.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">No receipts</div>
              )}
            </div>

            <div className="px-4 py-3 bg-green-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL</span>
              <span className="font-bold text-green-700">{fmt(drFooting)}</span>
            </div>
          </div>

          {/* RIGHT: Cr / Payments */}
          <div>
            <div className="bg-red-50 dark:bg-red-950/30 px-4 py-3 flex items-center justify-between border-b border-border">
              <div className="flex items-center gap-2">
                <ArrowDownCircle size={15} className="text-red-600" />
                <span className="font-bold text-sm text-red-800 dark:text-red-300">Cr — Payments</span>
              </div>
              <span className="font-bold text-red-700 dark:text-red-400">{fmt(data?.total_payments)}</span>
            </div>

            <div className="divide-y divide-border">
              {crSections.map((section, idx) => {
                if (section.type === "expense_group") {
                  return (
                    <div key={`exp-${idx}`} className="p-3">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-bold">Expenses</span>
                        <span className="text-sm font-bold text-red-700">{fmt(section.total)}</span>
                      </div>
                      {section.heads?.map((h, hi) => (
                        <div key={hi} className="ml-4 mb-2">
                          <div className="flex items-center justify-between py-1">
                            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide truncate max-w-[180px]">
                              {h.head_name}
                            </span>
                            <span className="text-xs font-bold text-red-600">{fmt(h.total)}</span>
                          </div>
                          {h.entries?.map((e, ei) => (
                            <div key={ei} className="flex items-center justify-between py-0.5 ml-2">
                              <span className="text-xs text-muted-foreground truncate max-w-[160px]">
                                {e.narration || e.date}
                              </span>
                              <div className="flex items-center gap-1">
                                <span className="text-xs font-medium">{fmt(e.amount)}</span>
                                {canAct && (
                                  <div className="flex gap-0.5">
                                    {e.entry_type === "expense_voucher" && (
                                      <button onClick={() => onEdit(e.entry_id)}
                                        className="p-0.5 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded transition-colors"
                                        title="Edit entry" data-testid={`edit-entry-${e.entry_id}`}>
                                        <Edit3 size={11} />
                                      </button>
                                    )}
                                    <button onClick={() => onDelete(e.entry_id)}
                                      className="p-0.5 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                                      title="Delete entry" data-testid={`delete-entry-${e.entry_id}`}>
                                      <Trash2 size={11} />
                                    </button>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  );
                }
                const e = section;
                return (
                  <div key={e.entry_id || `${e.date}-${e.narration}-${e.amount}`} className="flex items-center justify-between px-4 py-2.5">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{e.narration}</p>
                      <p className="text-xs text-muted-foreground">{e.date} · {e.contra_account}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-2">
                      <span className="text-sm font-bold text-red-700">{fmt(e.amount)}</span>
                      {canAct && (
                        <div className="flex gap-0.5">
                          {e.entry_type === "expense_voucher" && (
                            <button onClick={() => onEdit(e.entry_id)}
                              className="p-1 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded transition-colors"
                              title="Edit entry" data-testid={`edit-entry-${e.entry_id}`}>
                              <Edit3 size={12} />
                            </button>
                          )}
                          <button onClick={() => onDelete(e.entry_id)}
                            className="p-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded transition-colors"
                            title="Delete entry" data-testid={`delete-entry-${e.entry_id}`}>
                            <Trash2 size={12} />
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {crSections.length === 0 && (
                <div className="px-4 py-8 text-center text-sm text-muted-foreground">No payments</div>
              )}

              {/* Closing cash closes the payments side, so both columns foot equal */}
              <div className="flex items-center justify-between px-4 py-2.5 bg-primary/5">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold truncate">By Closing Cash c/d</p>
                  <p className="text-xs text-muted-foreground">Cash in hand at month end</p>
                </div>
                <span className={`text-sm font-bold ml-2 ${closingBal >= 0 ? "text-primary" : "text-destructive"}`}>
                  {fmt(closingBal)}
                </span>
              </div>
            </div>

            <div className="px-4 py-3 bg-red-50/50 border-t border-border flex justify-between">
              <span className="text-xs font-bold text-muted-foreground">TOTAL</span>
              <span className="font-bold text-red-700">{fmt(Math.round(((data?.total_payments || 0) + closingBal) * 100) / 100)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Closing balance bar */}
      {(drSections.length > 0 || crEntries.length > 0) && (
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
