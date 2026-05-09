import React, { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  ShieldCheck, AlertTriangle, RefreshCw, ExternalLink,
  CheckCircle, XCircle, Clock, TrendingUp, CreditCard,
  Building2, AlertCircle, Info, Download
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

// ── Helpers ───────────────────────────────────────────────────────────────────
function ScoreBadge({ value }) {
  const num = parseInt(value);
  if (!value || isNaN(num)) return <span className="text-sm text-muted-foreground">N/A</span>;
  const color =
    num >= 700 ? "text-green-600 bg-green-50 border-green-200" :
    num >= 500 ? "text-yellow-600 bg-yellow-50 border-yellow-200" :
                 "text-red-600 bg-red-50 border-red-200";
  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full border text-lg font-bold tabular-nums ${color}`}>
      {num}
    </span>
  );
}

function StatusChip({ status }) {
  const lower = (status || "").toLowerCase();
  if (lower === "success") return (
    <span className="flex items-center gap-1 text-green-600 text-xs font-semibold">
      <CheckCircle size={12} /> SUCCESS
    </span>
  );
  if (lower.includes("no response") || lower.includes("not found")) return (
    <span className="flex items-center gap-1 text-muted-foreground text-xs">
      <Info size={12} /> {status}
    </span>
  );
  return (
    <span className="flex items-center gap-1 text-yellow-600 text-xs font-semibold">
      <AlertCircle size={12} /> {status}
    </span>
  );
}

function SummaryCard({ label, value, sub }) {
  return (
    <div className="bg-muted/40 rounded-xl p-4 flex flex-col gap-1">
      <p className="text-xs text-muted-foreground font-medium uppercase tracking-wide">{label}</p>
      <p className="text-xl font-bold tabular-nums text-foreground">{value || "—"}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  );
}

// ── Per-Loan Card with Payment History matrix ─────────────────────────────────
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * Parse CRIF COMBINED-PAYMENT-HISTORY string → { year: { monthIdx: dpd } }
 * Format: "Jan:2025,000|Dec:2024,000|Nov:2024,XXX|..."
 * IOI/CNS variant: "Apr:2026,011/XXX|..."  (DPD/asset-classification — keep DPD only)
 */
function parsePaymentHistory(raw) {
  if (!raw || typeof raw !== "string") return {};
  const grid = {};
  raw.split("|").forEach((entry) => {
    const trimmed = entry.trim();
    if (!trimmed) return;
    const [monYear, dpdRaw] = trimmed.split(",");
    if (!monYear) return;
    const [mon, year] = monYear.split(":");
    const mi = MONTHS.indexOf((mon || "").slice(0, 3));
    if (mi === -1 || !year) return;
    // CNS variant: "DPD/CLASSIFICATION" — take DPD part only
    let dpd = (dpdRaw ?? "").trim();
    if (dpd.includes("/")) dpd = dpd.split("/")[0].trim();
    if (!grid[year]) grid[year] = {};
    grid[year][mi] = dpd;
  });
  return grid;
}

/** Map DPD value → cell style (matches CRIF report colour scheme) */
function dpdCellStyle(dpd) {
  if (dpd === undefined || dpd === null || dpd === "" || dpd === "-") {
    return "bg-muted/30 text-muted-foreground";
  }
  const upper = String(dpd).toUpperCase();
  if (upper === "XXX") return "bg-gray-100 text-gray-400";
  const n = parseInt(dpd, 10);
  if (Number.isNaN(n)) return "bg-muted/30 text-muted-foreground";
  if (n === 0)   return "bg-emerald-50 text-emerald-700";
  if (n <= 29)   return "bg-yellow-100 text-yellow-800 font-semibold";
  if (n <= 59)   return "bg-orange-200 text-orange-900 font-semibold";
  if (n <= 89)   return "bg-orange-400 text-white font-bold";
  return "bg-red-500 text-white font-bold";
}

function PaymentHistoryGrid({ raw }) {
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

function DetailField({ label, value, valueClass = "" }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-medium">{label}</span>
      <span className={`text-sm tabular-nums text-foreground ${valueClass}`}>{value || "—"}</span>
    </div>
  );
}

function LoanAccountCard({ acct, index }) {
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

// ── Main Component ────────────────────────────────────────────────────────────
export default function CrifCheck({ kycId, hasDob }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(false);
  const [htmlOpen, setHtmlOpen] = useState(false);

  const fetchResult = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/crif/result/${kycId}`, { withCredentials: true });
      if (res.data.has_result) setResult(res.data);
    } catch {
      // no prior result - that's fine
    } finally {
      setLoading(false);
    }
  }, [kycId]);

  useEffect(() => { fetchResult(); }, [fetchResult]);

  const runCheck = async () => {
    if (!hasDob) {
      toast.error("Date of Birth is required for CRIF check. Please edit KYC to add DOB.");
      return;
    }
    setChecking(true);
    try {
      const res = await axios.post(`${API}/crif/check/${kycId}`, {}, { withCredentials: true });
      setResult(res.data);
      toast.success("CRIF check completed");
    } catch (e) {
      const msg = e.response?.data?.detail || "CRIF check failed";
      toast.error(msg);
    } finally {
      setChecking(false);
    }
  };

  const openHtmlReport = () => {
    window.open(`${API}/crif/report-html/${kycId}`, "_blank");
  };

  const downloadPdf = () => {
    // Set a meaningful filename for the browser's "Save as PDF" dialog,
    // restore the original title afterwards.
    const customerId = result?.customer_id || "client";
    const checkedDate = result?.checked_at
      ? new Date(result.checked_at).toISOString().slice(0, 10)
      : new Date().toISOString().slice(0, 10);
    const originalTitle = document.title;
    document.title = `CRIF_${customerId}_${checkedDate}`;
    window.print();
    // Browsers handle the dialog asynchronously — restore after a tick
    setTimeout(() => { document.title = originalTitle; }, 1000);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40">
        <div className="w-8 h-8 border-3 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const r = result?.result;
  const summary = r?.account_summary || {};
  const primarySummary = r?.primary_summary || {};
  const scores = r?.scores || [];
  const mfiAccounts = r?.mfi_accounts || [];
  const cnsAccounts = r?.cns_accounts || [];
  const ioiAccounts = r?.ioi_accounts || [];
  const prodAccounts = r?.prod_accounts || [];
  const inquiryHistory = r?.inquiry_history || [];
  const verifications = r?.verifications || {};
  const serviceStatuses = r?.service_statuses || {};
  const errors = r?.errors || [];

  // ── Derive PROD-format summary from prod_accounts when ACCOUNTS-SUMMARY is empty ──
  const toNum = (v) => parseInt(String(v || "0").replace(/[^\d.-]/g, "")) || 0;
  const prodDerivedSummary = prodAccounts.length > 0 ? prodAccounts.reduce(
    (acc, a) => {
      const isActive = (a.status || "").toUpperCase() === "ACTIVE";
      acc.total += 1;
      if (isActive) acc.active += 1;
      acc.disbursed += toNum(a.disbursed);
      acc.balance   += toNum(a.current_balance);
      acc.overdue   += toNum(a.overdue);
      acc.write_off += toNum(a.write_off);
      return acc;
    },
    { total: 0, active: 0, disbursed: 0, balance: 0, overdue: 0, write_off: 0 }
  ) : null;

  return (
    <div className="space-y-5" data-testid="crif-tab">

      {/* Header Bar */}
      <div className="bk-card flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
            <ShieldCheck size={20} className="text-blue-600" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-foreground text-sm">CRIF High Mark</h3>
              {result?.env && (
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                  result.env === "PROD" || result.current_env === "PROD"
                    ? "bg-green-100 text-green-700 border border-green-300"
                    : "bg-amber-100 text-amber-700 border border-amber-300"
                }`}>
                  {result.env || result.current_env}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {result
                ? `Last checked: ${new Date(result.checked_at).toLocaleString("en-IN")} by ${result.checked_by_name || "—"}`
                : "No credit check performed yet"}
            </p>
          </div>
        </div>
        <div className="flex gap-2 crif-no-print">
          {result?.result?.html_report && (
            <button
              onClick={openHtmlReport}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/70 border border-border transition-colors"
              data-testid="crif-full-report-btn"
            >
              <ExternalLink size={13} /> Full Report
            </button>
          )}
          {result && r?.status === "success" && (
            <button
              onClick={downloadPdf}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold bg-muted hover:bg-muted/70 border border-border transition-colors"
              data-testid="crif-download-pdf-btn"
              title="Print / Save as PDF"
            >
              <Download size={13} /> Download PDF
            </button>
          )}
          <button
            onClick={runCheck}
            disabled={checking || !hasDob}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="crif-run-check-btn"
            title={!hasDob ? "Add Date of Birth to KYC first" : ""}
          >
            {checking ? (
              <><RefreshCw size={14} className="animate-spin" /> Checking...</>
            ) : (
              <><ShieldCheck size={14} /> {result ? "Re-check" : "Run CRIF Check"}</>
            )}
          </button>
        </div>
      </div>

      {/* No DOB warning */}
      {!hasDob && (
        <div className="bk-card flex items-start gap-3 border-l-4 border-amber-400 bg-amber-50">
          <AlertTriangle size={18} className="text-amber-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-amber-800">Date of Birth Required</p>
            <p className="text-xs text-amber-700 mt-0.5">CRIF requires DOB for credit check. Please edit KYC and add the applicant's Date of Birth.</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {r?.status === "error" && errors.length > 0 && (
        <div className="bk-card border-l-4 border-red-400 bg-red-50 space-y-2">
          <p className="text-sm font-semibold text-red-800 flex items-center gap-2"><XCircle size={14} /> CRIF returned errors</p>
          {errors.map((e, i) => (
            <div key={i} className="text-xs text-red-700">
              <span className="font-mono font-bold">{e.code}</span> — {e.description}
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {r?.status === "success" && (
        <>
          {/* Report ID */}
          <div className="bk-card flex items-center justify-between text-sm">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Clock size={14} />
              <span>Report ID: <span className="font-mono font-semibold text-foreground">{r.report_id || "—"}</span></span>
            </div>
            <span className="text-xs text-muted-foreground">{r.date_of_issue}</span>
          </div>

          {/* Score Section */}
          {scores.length > 0 && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <TrendingUp size={15} /> Credit Score
              </h4>
              <div className="flex flex-wrap gap-4">
                {scores.map((s, i) => (
                  <div key={i} className="flex flex-col gap-1">
                    <p className="text-xs text-muted-foreground uppercase tracking-wide">{s.name}</p>
                    <ScoreBadge value={s.value} />
                    {s.description && <p className="text-xs text-muted-foreground max-w-xs">{s.description}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Service Status */}
          {Object.keys(serviceStatuses).length > 0 && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground">Service Status</h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {Object.entries(serviceStatuses).map(([svc, status]) => (
                  <div key={svc} className="flex flex-col gap-0.5">
                    <p className="text-xs font-mono text-muted-foreground">{svc}</p>
                    <StatusChip status={status} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Account Summary (UAT/CONSUMER format) — hidden when PROD-derived summary is shown */}
          {!prodDerivedSummary && Object.keys(summary).length > 0 && (
            <div className="bk-card space-y-4">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <CreditCard size={15} /> Account Summary
              </h4>

              {/* MFI Section */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">MFI (Microfinance)</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <SummaryCard label="Total Accounts" value={summary.mfi_total_accounts} />
                  <SummaryCard label="Active Accounts" value={summary.mfi_active_accounts} />
                  <SummaryCard
                    label="Disbursed Amount"
                    value={summary.mfi_disbursed_amount ? `₹${parseInt(summary.mfi_disbursed_amount).toLocaleString("en-IN")}` : "₹0"}
                  />
                  <SummaryCard
                    label="Current Balance"
                    value={summary.mfi_current_balance ? `₹${parseInt(summary.mfi_current_balance).toLocaleString("en-IN")}` : "₹0"}
                    sub={summary.mfi_overdue_amount && parseInt(summary.mfi_overdue_amount) > 0
                      ? `Overdue: ₹${parseInt(summary.mfi_overdue_amount).toLocaleString("en-IN")}`
                      : null}
                  />
                </div>
              </div>

              {/* Consumer (Bank) Section */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Consumer (Banks & NBFCs)</p>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <SummaryCard label="Total Accounts" value={summary.cns_total_accounts} />
                  <SummaryCard label="Active Accounts" value={summary.cns_active_accounts} />
                  <SummaryCard
                    label="Disbursed Amount"
                    value={summary.cns_disbursed_amount ? `₹${parseInt(summary.cns_disbursed_amount).toLocaleString("en-IN")}` : "₹0"}
                  />
                  <SummaryCard
                    label="Current Balance"
                    value={summary.cns_current_balance ? `₹${parseInt(summary.cns_current_balance).toLocaleString("en-IN")}` : "₹0"}
                    sub={summary.cns_overdue_amount && parseInt(summary.cns_overdue_amount) > 0
                      ? `Overdue: ₹${parseInt(summary.cns_overdue_amount).toLocaleString("en-IN")}`
                      : null}
                  />
                </div>
              </div>

              {/* Derived attributes */}
              <div className="flex flex-wrap gap-4 pt-1 border-t border-border text-sm">
                <span className="text-muted-foreground">Inquiries (last 6m): <strong>{summary.inquiries_last_6m || "0"}</strong></span>
                <span className="text-muted-foreground">Credit history: <strong>{summary.credit_history_years || "0"}y {summary.credit_history_months || "0"}m</strong></span>
                <span className="text-muted-foreground">New accounts (6m): <strong>{summary.new_accounts_6m || "0"}</strong></span>
              </div>
            </div>
          )}

          {/* MFI Accounts Detail */}
          {mfiAccounts.length > 0 && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Building2 size={15} /> MFI Loan History ({mfiAccounts.length})
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-xs uppercase">
                      <th className="text-left py-2 pr-3">Lender</th>
                      <th className="text-left py-2 pr-3">Type</th>
                      <th className="text-right py-2 pr-3">Disbursed</th>
                      <th className="text-right py-2 pr-3">Balance</th>
                      <th className="text-left py-2 pr-3">Status</th>
                      <th className="text-left py-2">Opened</th>
                    </tr>
                  </thead>
                  <tbody>
                    {mfiAccounts.map((acct, i) => (
                      <tr key={i} className="border-b border-border/50 hover:bg-muted/30">
                        <td className="py-2 pr-3 font-medium">{acct.lender || "XXXX"}</td>
                        <td className="py-2 pr-3 text-muted-foreground">{acct.loan_type || "—"}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {acct.disbursed ? `₹${parseInt(acct.disbursed).toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {acct.current_balance ? `₹${parseInt(acct.current_balance).toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td className="py-2 pr-3">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                            (acct.status || "").toLowerCase() === "active"
                              ? "bg-green-100 text-green-700"
                              : "bg-muted text-muted-foreground"
                          }`}>
                            {acct.status || "—"}
                          </span>
                        </td>
                        <td className="py-2 text-muted-foreground text-xs">{acct.date_opened || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* CNS Accounts */}
          {cnsAccounts.length > 0 && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <CreditCard size={15} /> Bank/NBFC Loan History ({cnsAccounts.length})
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-xs uppercase">
                      <th className="text-left py-2 pr-3">Lender</th>
                      <th className="text-left py-2 pr-3">Type</th>
                      <th className="text-right py-2 pr-3">Disbursed</th>
                      <th className="text-right py-2 pr-3">Balance</th>
                      <th className="text-left py-2 pr-3">Status</th>
                      <th className="text-left py-2">Opened</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cnsAccounts.map((acct, i) => (
                      <tr key={i} className="border-b border-border/50 hover:bg-muted/30">
                        <td className="py-2 pr-3 font-medium">{acct.lender || "XXXX"}</td>
                        <td className="py-2 pr-3 text-muted-foreground">{acct.loan_type || "—"}</td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {acct.disbursed ? `₹${parseInt(acct.disbursed).toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums">
                          {acct.current_balance ? `₹${parseInt(acct.current_balance).toLocaleString("en-IN")}` : "—"}
                        </td>
                        <td className="py-2 pr-3">
                          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                            (acct.status || "").toLowerCase().includes("active")
                              ? "bg-green-100 text-green-700"
                              : "bg-muted text-muted-foreground"
                          }`}>
                            {acct.status || "—"}
                          </span>
                        </td>
                        <td className="py-2 text-muted-foreground text-xs">{acct.date_opened || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Identity Verifications */}
          {Object.keys(verifications).length > 0 && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground">Identity Verifications</h4>
              <div className="flex flex-wrap gap-3">
                {Object.entries(verifications).map(([type, data]) => (
                  <div key={type} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border">
                    <span className="font-mono text-xs font-bold">{type}</span>
                    <StatusChip status={data.status} />
                    {data.description && (
                      <span className="text-xs text-muted-foreground hidden sm:block">— {data.description}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Primary Account Summary (UAT IOI format) — hidden when PROD-derived summary is shown */}
          {!prodDerivedSummary && Object.keys(primarySummary).length > 0 && (
            <div className="bk-card space-y-4">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <CreditCard size={15} /> Account Summary
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <SummaryCard label="Total Accounts" value={primarySummary.total_accounts} />
                <SummaryCard label="Active Accounts" value={primarySummary.active_accounts} />
                <SummaryCard label="Overdue Accounts" value={primarySummary.overdue_accounts} />
                <SummaryCard
                  label="Current Balance"
                  value={primarySummary.current_balance ? `₹${primarySummary.current_balance}` : "₹0"}
                />
                <SummaryCard
                  label="Total Disbursed"
                  value={primarySummary.disbursed_amount ? `₹${primarySummary.disbursed_amount}` : "₹0"}
                />
                <SummaryCard
                  label="Total Sanctioned"
                  value={primarySummary.sanctioned_amount ? `₹${primarySummary.sanctioned_amount}` : "₹0"}
                />
              </div>
            </div>
          )}

          {/* PROD-format Account Summary (derived from prod_accounts) */}
          {prodDerivedSummary && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <CreditCard size={15} /> Account Summary
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                <SummaryCard label="Total Accounts" value={prodDerivedSummary.total} />
                <SummaryCard label="Active" value={prodDerivedSummary.active} />
                <SummaryCard
                  label="Total Disbursed"
                  value={`₹${prodDerivedSummary.disbursed.toLocaleString("en-IN")}`}
                />
                <SummaryCard
                  label="Current Balance"
                  value={`₹${prodDerivedSummary.balance.toLocaleString("en-IN")}`}
                />
                <SummaryCard
                  label="Overdue"
                  value={`₹${prodDerivedSummary.overdue.toLocaleString("en-IN")}`}
                  sub={prodDerivedSummary.overdue > 0 ? "⚠ Active overdue" : null}
                />
                <SummaryCard
                  label="Write-Off"
                  value={`₹${prodDerivedSummary.write_off.toLocaleString("en-IN")}`}
                />
              </div>
              {summary.inquiries_last_6m && (
                <div className="flex flex-wrap gap-4 pt-2 border-t border-border text-sm">
                  <span className="text-muted-foreground">Inquiries (last 6m): <strong>{summary.inquiries_last_6m}</strong></span>
                  <span className="text-muted-foreground">Credit history: <strong>{summary.credit_history_years || "0"}y {summary.credit_history_months || "0"}m</strong></span>
                  <span className="text-muted-foreground">New accounts (6m): <strong>{summary.new_accounts_6m || "0"}</strong></span>
                </div>
              )}
            </div>
          )}

          {/* PROD Per-Loan Cards (INDV-RESPONSE / LOAN-DETAIL) */}
          {prodAccounts.length > 0 && (
            <div className="space-y-3" data-testid="crif-prod-accounts-list">
              <div className="flex items-center gap-2 px-1">
                <Building2 size={15} className="text-foreground" />
                <h4 className="text-sm font-semibold text-foreground">
                  Loan History ({prodAccounts.length} accounts)
                </h4>
              </div>
              {prodAccounts.map((acct, i) => (
                <LoanAccountCard key={i} acct={acct} index={i} />
              ))}
            </div>
          )}

          {/* IOI / CNS Loan History (RESPONSES/RESPONSE/LOAN-DETAILS format) */}
          {ioiAccounts.length > 0 && (
            <div className="space-y-3" data-testid="crif-ioi-accounts-list">
              <div className="flex items-center gap-2 px-1">
                <Building2 size={15} className="text-foreground" />
                <h4 className="text-sm font-semibold text-foreground">
                  {prodAccounts.length > 0 ? "Bank/NBFC Loan History" : "Loan History"} ({ioiAccounts.length} accounts)
                </h4>
              </div>
              {ioiAccounts.map((acct, i) => (
                <LoanAccountCard key={i} acct={acct} index={`ioi-${i}`} />
              ))}
            </div>
          )}

          {/* Inquiry History */}
          {inquiryHistory.length > 0 && (
            <div className="bk-card space-y-3">
              <h4 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Clock size={15} /> Inquiry History ({inquiryHistory.length})
              </h4>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-muted-foreground text-xs uppercase">
                      <th className="text-left py-2 pr-3">Institution</th>
                      <th className="text-left py-2 pr-3">Date</th>
                      <th className="text-left py-2 pr-3">Purpose</th>
                      <th className="text-right py-2">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {inquiryHistory.slice(0, 10).map((h, i) => (
                      <tr key={i} className="border-b border-border/50 hover:bg-muted/30">
                        <td className="py-2 pr-3 font-medium text-xs">{h.member || "—"}</td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">{h.date || "—"}</td>
                        <td className="py-2 pr-3 text-xs text-muted-foreground">{h.purpose || "—"}</td>
                        <td className="py-2 text-right text-xs tabular-nums">{h.amount ? `₹${h.amount}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {inquiryHistory.length > 10 && (
                  <p className="text-xs text-muted-foreground mt-2">Showing latest 10 of {inquiryHistory.length} inquiries</p>
                )}
              </div>
            </div>
          )}
          {!scores.length && !mfiAccounts.length && !cnsAccounts.length && !ioiAccounts.length && !prodAccounts.length && !primarySummary.total_accounts && (
            <div className="bk-card text-center py-8 text-muted-foreground">
              <ShieldCheck size={32} className="mx-auto mb-2 opacity-40" />
              <p className="font-semibold">No credit history found</p>
              <p className="text-xs mt-1">This applicant has no record in CRIF High Mark database</p>
            </div>
          )}
        </>
      )}

      {/* No result yet */}
      {!result && !loading && (
        <div className="bk-card text-center py-12 text-muted-foreground">
          <ShieldCheck size={40} className="mx-auto mb-3 opacity-30" />
          <p className="font-semibold text-base">No CRIF check performed</p>
          <p className="text-sm mt-1">Click "Run CRIF Check" to fetch the applicant's credit history</p>
          {!hasDob && (
            <p className="text-xs mt-2 text-amber-600 flex items-center justify-center gap-1">
              <AlertTriangle size={12} /> Add Date of Birth to KYC before running check
            </p>
          )}
        </div>
      )}
    </div>
  );
}
