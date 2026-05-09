import React from "react";
import { AlertCircle } from "lucide-react";
import PaymentHistoryGrid from "./PaymentHistoryGrid";

function DetailField({ label, value, valueClass = "" }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">{label}</span>
      <span className={`text-sm tabular-nums text-foreground ${valueClass}`}>{value || "—"}</span>
    </div>
  );
}

export default function LoanAccountCard({ acct, index }) {
  const isActive = (acct.status || "").toUpperCase() === "ACTIVE";
  const overdueNum = parseInt(String(acct.overdue || "0").replace(/[^\d]/g, "")) || 0;
  const dpdNum = parseInt(acct.dpd || "0") || 0;
  // CNS/IOI accounts use ownership+security+interest_rate; PROD/MFI uses fldg+worst_delinq+kendra
  const isCns = !!(acct.ownership || acct.security_status || acct.interest_rate);

  return (
    <div className="bk-card overflow-hidden" data-testid={`crif-loan-card-${index}`}>
      {/* Header bar — lender + status */}
      <div className="flex items-center justify-between gap-3 pb-3 mb-3 border-b border-border">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`shrink-0 px-2.5 py-1 rounded-md text-xs font-bold tracking-wide ${
            isActive
              ? "bg-emerald-100 text-emerald-700 border border-emerald-200"
              : "bg-muted text-muted-foreground border border-border"
          }`}>
            {acct.status || "—"}
          </span>
          <div className="min-w-0">
            <p className="font-semibold text-sm text-foreground truncate">{acct.lender || "—"}</p>
            <p className="text-xs text-muted-foreground truncate">
              {acct.loan_type || "—"}
              {acct.frequency && ` • ${acct.frequency}`}
              {acct.loan_cycle && ` • Cycle ${acct.loan_cycle}`}
              {acct.ownership && ` • ${acct.ownership}`}
            </p>
          </div>
        </div>
        {(overdueNum > 0 || dpdNum > 0) && (
          <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 text-red-700 text-xs font-semibold border border-red-200">
            <AlertCircle size={11} /> Delinquent
          </span>
        )}
      </div>

      {/* Detail grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-x-5 gap-y-3 mb-4">
        <DetailField label="Account #" value={acct.acct_number} />
        <DetailField label="Disbursed Date" value={acct.date_disbursed} />
        <DetailField label="Disbursed Amount" value={acct.disbursed ? `₹${acct.disbursed}` : "—"} />
        <DetailField label="Info As On" value={acct.info_as_on} />

        <DetailField label="Closed Date" value={acct.date_closed} />
        <DetailField
          label="Current Balance"
          value={acct.current_balance ? `₹${acct.current_balance}` : "₹0"}
          valueClass={parseInt((acct.current_balance || "").replace(/,/g, "")) > 0 ? "font-semibold" : ""}
        />
        <DetailField label="Write-Off" value={acct.write_off ? `₹${acct.write_off}` : "₹0"} />
        <DetailField label="Last Payment Date" value={acct.last_payment} />

        <DetailField label="Instalment" value={acct.installment ? `₹${acct.installment}` : "—"} />
        <DetailField
          label="Amount Overdue"
          value={acct.overdue ? `₹${acct.overdue}` : "₹0"}
          valueClass={overdueNum > 0 ? "text-red-600 font-bold" : ""}
        />
        <DetailField
          label="DPD"
          value={acct.dpd || "0"}
          valueClass={dpdNum > 0 ? "text-red-600 font-bold" : ""}
        />
        <DetailField label="Tenure (months)" value={acct.term_months} />

        {isCns ? (
          <>
            <DetailField label="Security" value={acct.security_status} />
            <DetailField label="Interest Rate" value={acct.interest_rate ? `${acct.interest_rate}%` : "—"} />
            <DetailField label="Ownership" value={acct.ownership} />
            <DetailField label="Account in Dispute" value={acct.dispute || "No"} />
          </>
        ) : (
          <>
            <DetailField label="FLDG" value={acct.fldg} />
            <DetailField label="Account in Dispute" value={acct.dispute || "No"} />
            <DetailField label="Worst Delinquency" value={acct.worst_delinq || "0"} />
            <DetailField label="Branch / Kendra" value={[acct.branch, acct.kendra].filter(Boolean).join(" / ") || "—"} />
          </>
        )}
      </div>

      {/* Payment History matrix */}
      <div className="pt-3 border-t border-border">
        <p className="text-xs font-semibold text-foreground mb-2 uppercase tracking-wide">Payment History (DPD)</p>
        <PaymentHistoryGrid raw={acct.payment_history} />
      </div>
    </div>
  );
}
