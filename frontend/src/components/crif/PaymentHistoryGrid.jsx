import React from "react";
import { MONTHS, parsePaymentHistory, dpdCellStyle } from "./parsePaymentHistory";

export default function PaymentHistoryGrid({ raw }) {
  const grid = parsePaymentHistory(raw);
  const years = Object.keys(grid).sort((a, b) => Number(b) - Number(a)); // newest first
  if (years.length === 0) {
    return <p className="text-xs text-muted-foreground italic">No payment history reported.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-[10px] sm:text-xs" data-testid="crif-payment-history-grid">
        <thead>
          <tr>
            <th className="px-1.5 py-1 text-left text-muted-foreground font-semibold w-12"></th>
            {MONTHS.map((m) => (
              <th key={m} className="px-1.5 py-1 text-muted-foreground font-medium w-10 text-center">{m}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((y) => (
            <tr key={y} className="border-t border-border/40">
              <td className="px-1.5 py-1 font-bold text-foreground bg-muted/40 text-center w-12">{y}</td>
              {MONTHS.map((_, mi) => {
                const dpd = grid[y][mi];
                return (
                  <td key={mi} className={`px-1 py-1 text-center tabular-nums border border-white/60 ${dpdCellStyle(dpd)}`}>
                    {dpd === undefined ? "—" : dpd}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap gap-3 mt-2 text-[10px] text-muted-foreground">
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-emerald-50 border border-emerald-200" /> 0 days (on-time)</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-yellow-100" /> 1–29 days</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-orange-200" /> 30–59</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-orange-400" /> 60–89</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-red-500" /> 90+</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-gray-100 border border-gray-200" /> XXX (not reported)</span>
      </div>
    </div>
  );
}
