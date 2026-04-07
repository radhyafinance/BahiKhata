import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ROWS_PER_PAGE = 10;
const FY_ABBR = ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar"];

function getFyMonths(fyStart) {
  const months = [];
  for (let i = 0; i < 12; i++) {
    const mo = ((3 + i) % 12) + 1;
    const yr = mo >= 4 ? fyStart : fyStart + 1;
    months.push(`${yr}-${String(mo).padStart(2, "0")}`);
  }
  return months;
}

function getFyLabel(s) {
  return `${String(s).slice(-2)}-${String(s + 1).slice(-2)}`;
}

function fmtIN(n) {
  if (!n) return "";
  return Number(n).toLocaleString("en-IN");
}

// ── Inject print + screen CSS once ──────────────────────────────────────────
const PRINT_CSS = `
@media print {
  @page { size: legal landscape; margin: 0.3in 0.38in; }
  html, body { margin: 0; padding: 0; font-size: 7.5pt; }
  .no-print { display: none !important; }
  .print-page { page-break-after: always; }
  .print-page:last-child { page-break-after: auto; }
}
@media screen {
  body { background: #cbd5e1; padding: 56px 20px 20px; }
  .print-page {
    background: white;
    width: 13.6in;
    margin: 0 auto 20px;
    padding: 0.3in 0.38in;
    box-shadow: 0 2px 12px rgba(0,0,0,0.15);
  }
}
* { box-sizing: border-box; }
body { font-family: 'Noto Sans', 'Noto Sans Devanagari', Arial, sans-serif; }

/* ── Page header ── */
.ph { display:flex; justify-content:space-between; align-items:flex-end; border-bottom:2pt solid #1e293b; padding-bottom:5px; margin-bottom:7px; }
.ph-title { font-size:13pt; font-weight:900; color:#1e293b; line-height:1.2; }
.ph-sub { font-size:7.5pt; color:#475569; margin-top:2px; }
.ph-right { text-align:right; font-size:7.5pt; color:#64748b; }
.ph-badge { display:inline-block; background:#7c3aed; color:white; font-size:6.5pt; padding:1px 7px; border-radius:10px; margin-top:2px; }

/* ── Table ── */
table { width:100%; border-collapse:collapse; font-size:7pt; }
thead tr { background:#1e293b; color:white; }
th { padding:3.5px 2px; text-align:center; font-weight:700; border:0.4pt solid #334155; white-space:nowrap; line-height:1.3; }
th.left { text-align:left; padding-left:5px; }
td { padding:3.5px 2px; border:0.4pt solid #e2e8f0; vertical-align:middle; line-height:1.3; }
td.c { text-align:center; }
td.r { text-align:right; padding-right:3px; }
tr:nth-child(even) td { background:#f8fafc; }
.paid  { color:#16a34a; font-weight:600; }
.overdue { color:#dc2626; }
.na    { color:#cbd5e1; }
.blank { background:#f1f5f9 !important; }
.total-row td { background:#dcfce7 !important; font-weight:700; border-top:1.5pt solid #16a34a; }
.empty-row { height:21pt; }

/* ── Page footer ── */
.pf { display:flex; justify-content:space-between; margin-top:5px; font-size:6.5pt; color:#94a3b8; border-top:0.5pt solid #e2e8f0; padding-top:3px; }
`;

export default function CollectionSheetPrint() {
  const [searchParams] = useSearchParams();
  const illakaId = searchParams.get("illaka_id");
  const fyStart   = Number(searchParams.get("fy_start")) || new Date().getFullYear() - (new Date().getMonth() < 3 ? 1 : 0);
  const duplex    = searchParams.get("duplex") === "true";

  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fyMonths    = useMemo(() => getFyMonths(fyStart), [fyStart]);
  const activeMonth = fyMonths[0]; // Apr of the selected FY

  // Inject CSS
  useEffect(() => {
    const el = document.createElement("style");
    el.textContent = PRINT_CSS;
    document.head.appendChild(el);
    return () => document.head.removeChild(el);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ month: activeMonth });
    if (illakaId) params.append("illaka_id", illakaId);
    axios
      .get(`${API}/collections/sheet?${params}`, { withCredentials: true })
      .then((r) => setData(r.data))
      .catch(() => setError("Failed to load collection data. Please check login and try again."))
      .finally(() => setLoading(false));
  }, [activeMonth, illakaId]);

  // Build pages: [{illakaName, misalName, misalId, pageNum, totalPagesInMisal, rows, startIndex, allMisalRows}]
  const pages = useMemo(() => {
    if (!data) return [];
    const result = [];
    for (const illaka of data.illakas) {
      for (const misal of illaka.misals) {
        const allRows  = misal.rows;
        const numPages = Math.max(1, Math.ceil(allRows.length / ROWS_PER_PAGE));
        for (let pg = 0; pg < numPages; pg++) {
          result.push({
            illakaName:         illaka.illaka_name,
            misalName:          misal.misal_name,
            misalId:            misal.misal_id,
            pageNum:            pg + 1,
            totalPagesInMisal:  numPages,
            rows:               allRows.slice(pg * ROWS_PER_PAGE, (pg + 1) * ROWS_PER_PAGE),
            startIndex:         pg * ROWS_PER_PAGE + 1,
            allMisalRows:       allRows,
          });
        }
      }
    }
    return result;
  }, [data]);

  const totalClients = pages.reduce((a, p) => a + p.rows.length, 0);

  // ── helpers ────────────────────────────────────────────────────────────────
  function getMisalTotals(allRows) {
    const monthTotals = {};
    let totalVayda = 0;
    for (const row of allRows) {
      for (const yd of row.emi_year_data || []) {
        if (yd.status === "paid") {
          monthTotals[yd.month] = (monthTotals[yd.month] || 0) + (yd.paid_amount || 0);
          totalVayda += yd.paid_amount || 0;
        }
      }
    }
    return { monthTotals, totalVayda };
  }

  // ── render guards ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div style={{ padding: 40, fontFamily: "sans-serif", color: "#475569" }}>
        <p style={{ fontSize: 16, fontWeight: 700 }}>Loading collection data for FY {getFyLabel(fyStart)}…</p>
        <p style={{ fontSize: 13, marginTop: 8 }}>Please wait while we fetch the full year's data.</p>
      </div>
    );
  }
  if (error) {
    return (
      <div style={{ padding: 40, fontFamily: "sans-serif", color: "#dc2626" }}>
        <p style={{ fontSize: 16, fontWeight: 700 }}>Error</p>
        <p>{error}</p>
      </div>
    );
  }

  const printDate = new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

  return (
    <div>
      {/* ── Screen-only top bar ── */}
      <div
        className="no-print"
        style={{
          position: "fixed", top: 0, left: 0, right: 0, zIndex: 999,
          background: "#1e293b", color: "white",
          padding: "9px 20px", display: "flex", alignItems: "center", gap: 16,
          fontFamily: "sans-serif",
        }}
      >
        <div>
          <strong style={{ fontSize: 14 }}>
            Vasuli FY {getFyLabel(fyStart)} — Print Preview
          </strong>
          <span style={{ fontSize: 12, color: "#94a3b8", marginLeft: 12 }}>
            {pages.length} pages · {totalClients} clients
          </span>
        </div>

        {duplex && (
          <span style={{
            fontSize: 11, background: "#7c3aed", padding: "3px 12px",
            borderRadius: 20, flexShrink: 0,
          }}>
            Duplex: In print dialog → Two-sided: On → Flip on Long Edge
          </span>
        )}

        <div style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
          <button
            onClick={() => window.print()}
            style={{
              background: "#16a34a", color: "white", border: "none",
              padding: "8px 22px", borderRadius: 8, fontWeight: 700,
              cursor: "pointer", fontSize: 14,
            }}
          >
            Print / PDF
          </button>
          <button
            onClick={() => window.close()}
            style={{
              background: "#475569", color: "white", border: "none",
              padding: "8px 14px", borderRadius: 8, cursor: "pointer", fontSize: 14,
            }}
          >
            Close
          </button>
        </div>
      </div>

      {/* ── Pages ── */}
      {pages.map((page) => {
        const isLastPage = page.pageNum === page.totalPagesInMisal;
        const totals     = isLastPage ? getMisalTotals(page.allMisalRows) : null;

        // Pad to exactly ROWS_PER_PAGE with nulls for empty rows
        const paddedRows = [...page.rows];
        while (paddedRows.length < ROWS_PER_PAGE) paddedRows.push(null);

        return (
          <div key={`${page.misalId}-p${page.pageNum}`} className="print-page">
            {/* Page Header */}
            <div className="ph">
              <div>
                <div className="ph-title">
                  बही खाता — वसूली पत्र &nbsp;/&nbsp; Collection Sheet &nbsp;·&nbsp; FY {getFyLabel(fyStart)}
                </div>
                <div className="ph-sub">
                  इलाका: <strong>{page.illakaName}</strong>
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  मिसाल: <strong>{page.misalName}</strong>
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  Page {page.pageNum} of {page.totalPagesInMisal}
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  Clients {page.startIndex}–{page.startIndex + page.rows.length - 1} of {page.allMisalRows.length}
                  {duplex && <span className="ph-badge">Duplex · Long Edge</span>}
                </div>
              </div>
              <div className="ph-right">
                <div><strong>Printed:</strong> {printDate}</div>
                <div>Apr {fyStart} → Mar {fyStart + 1}</div>
              </div>
            </div>

            {/* Table */}
            <table>
              <thead>
                <tr>
                  <th style={{ width: 22 }}>#</th>
                  <th className="left" style={{ width: "20%" }}>ग्राहक / Client</th>
                  <th style={{ width: 54 }}>Loan No.</th>
                  <th style={{ width: 40 }}>EMI ₹</th>
                  {FY_ABBR.map((abbr, i) => (
                    <th key={fyMonths[i]} style={{ width: 36, fontSize: "6pt" }}>{abbr}</th>
                  ))}
                  <th style={{ width: 52 }}>Paid ₹</th>
                  <th className="blank" style={{ width: 52 }}>Bal. ₹</th>
                  <th className="blank" style={{ width: 38 }}>Sign</th>
                </tr>
              </thead>
              <tbody>
                {paddedRows.map((row, ri) => {
                  const sn = page.startIndex + ri;

                  if (!row) {
                    return (
                      <tr key={`empty-${ri}`} className="empty-row">
                        <td className="c na">{sn}</td>
                        <td /><td /><td />
                        {fyMonths.map((ym) => <td key={ym} />)}
                        <td /><td className="blank" /><td className="blank" />
                      </tr>
                    );
                  }

                  const yearData = row.emi_year_data || fyMonths.map(() => ({ status: "na", paid_amount: 0 }));

                  return (
                    <tr key={row.loan_db_id}>
                      <td className="c">{sn}</td>
                      <td style={{ paddingLeft: 5 }}>
                        <div style={{ fontWeight: 600 }}>{row.client_name_hindi || row.client_name}</div>
                        {row.client_name_hindi && (
                          <div style={{ fontSize: "6pt", color: "#64748b" }}>{row.client_name}</div>
                        )}
                      </td>
                      <td className="c" style={{ fontSize: "6pt" }}>{row.loan_number}</td>
                      <td className="r">{fmtIN(row.emi_amount)}</td>

                      {yearData.map((yd, mi) => {
                        let cls = "";
                        let val = "";
                        if (yd.status === "paid") {
                          cls = "paid c";
                          val = fmtIN(yd.paid_amount);
                        } else if (yd.status === "overdue" || yd.status === "pending") {
                          cls = "overdue c";
                          val = "";
                        } else {
                          cls = "na c";
                          val = "—";
                        }
                        return (
                          <td key={fyMonths[mi]} className={cls}>{val}</td>
                        );
                      })}

                      <td className="r paid" style={{ fontWeight: 700 }}>
                        {fmtIN(row.total_paid)}
                      </td>
                      <td className="blank" />
                      <td className="blank" />
                    </tr>
                  );
                })}

                {/* Misal totals row — only on last page of the misal */}
                {isLastPage && totals && (
                  <tr className="total-row">
                    <td colSpan={4} style={{ textAlign: "right", paddingRight: 6 }}>
                      मिसाल कुल / Misal Total ({page.allMisalRows.length} clients):
                    </td>
                    {fyMonths.map((ym) => (
                      <td key={ym} className="c paid">
                        {totals.monthTotals[ym] ? fmtIN(totals.monthTotals[ym]) : ""}
                      </td>
                    ))}
                    <td className="r paid">{fmtIN(totals.totalVayda)}</td>
                    <td className="blank" />
                    <td className="blank" />
                  </tr>
                )}
              </tbody>
            </table>

            {/* Page Footer */}
            <div className="pf">
              <span>बही खाता &nbsp;|&nbsp; {page.illakaName}</span>
              <span>{page.misalName} &nbsp;|&nbsp; FY {getFyLabel(fyStart)}</span>
              <span>Page {page.pageNum}/{page.totalPagesInMisal} &nbsp;|&nbsp; {printDate}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
