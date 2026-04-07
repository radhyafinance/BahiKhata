import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ROWS_PER_PAGE = 10;

// ── helpers (mirrors CollectionSheet.jsx) ─────────────────────────────────
const fmtK    = (n) => n ? new Intl.NumberFormat("en-IN").format(Math.round(n)) : "";
const fmtIN   = (n) => n ? new Intl.NumberFormat("en-IN").format(Math.round(n)) : "";
const fmtDate = (s) => { if (!s) return ""; const d=new Date(s); return isNaN(d)?"":`${d.toLocaleString("en-IN",{month:"short"})} ${d.getFullYear()}`; };

const FY_ABBR = ["Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec","Jan","Feb","Mar"];

function getFyMonths(fyStart) {
  return Array.from({length:12},(_,i)=>{const m=((3+i)%12)+1;const y=m>=4?fyStart:fyStart+1;return`${y}-${String(m).padStart(2,"0")}`;});
}
function getFyLabel(s){ return `${String(s).slice(-2)}-${String(s+1).slice(-2)}`; }
function getCurrentFyStart(){ const d=new Date(); return d.getMonth()+1>=4?d.getFullYear():d.getFullYear()-1; }

// ── Inject print/screen CSS ───────────────────────────────────────────────
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;600;700;900&family=Noto+Sans+Devanagari:wght@400;600;700;900&display=swap');

@media print {
  @page { size: legal landscape; margin: 0.28in 0.34in; }
  html, body { margin:0; padding:0; }
  .no-print { display:none!important; }
  .print-page { page-break-after:always; }
  .print-page:last-child { page-break-after:auto; }
}
@media screen {
  body { background:#94a3b8; padding:56px 16px 20px; }
  .print-page {
    background:#fff; width:13.6in;
    margin:0 auto 20px; padding:0.28in 0.34in;
    box-shadow:0 4px 24px rgba(0,0,0,.22);
  }
}

*  { box-sizing:border-box; }
body { font-family:'Noto Sans','Noto Sans Devanagari',sans-serif; font-size:7.5pt; color:#1e293b; }

/* ── page chrome ── */
.page-header { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:6px; }
.page-header h1 { font-size:12pt; font-weight:900; line-height:1.2; color:#1e293b; margin:0; }
.page-header .sub { font-size:7pt; color:#64748b; margin-top:2px; }
.page-header .right { text-align:right; font-size:7pt; color:#64748b; }
.duplex-badge { display:inline-block; background:#7c3aed; color:#fff; font-size:6pt; padding:1px 6px; border-radius:10px; vertical-align:middle; margin-left:6px; }
.page-footer { display:flex; justify-content:space-between; margin-top:5px; font-size:6.5pt; color:#94a3b8; border-top:.4pt solid #e2e8f0; padding-top:3px; }

/* ── main table ── */
table  { width:100%; table-layout:fixed; border-collapse:collapse; font-size:7pt; }
col.sn    { width:1.5%; }
col.emi   { width:4.5%; }
col.names { width:15%;  }
col.prev  { width:5%;   }
col.new   { width:5%;   }
col.mo    { width:4.84%; }   /* 12 × 4.84 = 58.08 */
col.bal   { width:4.5%; }
col.sign  { width:4.5%; }

/* ── header row (dark, like screen's sticky header) ── */
thead tr { background:#1e293b; color:#fff; }
th { padding:3px 2px; text-align:center; font-weight:700; border:.4pt solid #334155; line-height:1.3; white-space:nowrap; overflow:hidden; }
th.left { text-align:left; padding-left:4px; }
th.mo-h { font-size:6pt; letter-spacing:-.2px; }

/* ── misal section header ── */
.misal-hdr td { background:#0f172a; color:#e2e8f0; font-weight:700; font-size:7.5pt; padding:3px 6px; border:.4pt solid #1e293b; letter-spacing:.3px; }

/* ── data cells ── */
td { padding:3px 2px; border:.4pt solid #e2e8f0; vertical-align:middle; }
td.c  { text-align:center; }
td.r  { text-align:right; padding-right:3px; }
td.lp { padding-left:4px; }

/* ── row status backgrounds (mirrors screen) ── */
tr.row-paid    td { background:#f0fdf4; }  /* green-50 */
tr.row-netoff  td { background:#eff6ff; }  /* blue-50  */
tr.row-overdue td { background:#fff1f2; }  /* red-50   */
tr.row-gyal    td { background:#f4f4f5; }  /* gray-100 */
tr.row-empty   td { background:#fafafa; }
tr.row-empty   { height:21pt; }

/* ── month cell states (mirrors screen) ── */
td.mo-na      { background:#f8fafc; }
td.mo-paid    { background:#dcfce7; } /* green-100 */
td.mo-overdue { background:#fee2e2; } /* red-100   */
td.mo-netoff  { background:#dbeafe; } /* blue-100  */
td.mo-note    { background:#fef3c7; } /* amber-100 */
td.mo-pending { background:#fff;    }

.tick  { color:#16a34a; font-weight:900; font-size:8pt; }
.kamt  { color:#15803d; font-weight:700; font-size:6.5pt; display:block; }
.bang  { color:#ef4444; font-weight:900; font-size:9pt; }
.arrow { color:#3b82f6; font-weight:900; font-size:8pt; }
.dot   { color:#cbd5e1; font-size:10pt; }

/* strikethrough for prev EMI amounts */
.stk { text-decoration:line-through; color:#94a3b8; font-size:6pt; display:block; }

/* ── totals row ── */
tr.total-row td { background:#dcfce7!important; font-weight:700; border-top:1.5pt solid #16a34a; }

/* ── blank columns styling (hatched look) ── */
td.blank { background:repeating-linear-gradient(45deg,#f8fafc,#f8fafc 4pt,#f1f5f9 4pt,#f1f5f9 8pt)!important; }
th.blank-h { background:#334155; }
`;

// ── Print page component ──────────────────────────────────────────────────
export default function CollectionSheetPrint() {
  const [searchParams]    = useSearchParams();
  const illakaId          = searchParams.get("illaka_id");
  const fyStart           = Number(searchParams.get("fy_start")) || getCurrentFyStart();
  const duplex            = searchParams.get("duplex") === "true";

  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fyMonths = useMemo(() => getFyMonths(fyStart), [fyStart]);

  // Inject CSS
  useEffect(() => {
    const el = document.createElement("style");
    el.textContent = CSS;
    document.head.appendChild(el);
    return () => document.head.removeChild(el);
  }, []);

  // Fetch full-year data (use Apr of the FY as the month param)
  useEffect(() => {
    const params = new URLSearchParams({ month: fyMonths[0] });
    if (illakaId) params.append("illaka_id", illakaId);
    axios.get(`${API}/collections/sheet?${params}`, { withCredentials: true })
      .then(r => setData(r.data))
      .catch(() => setError("Failed to load data. Please close this tab, check your login and try again."))
      .finally(() => setLoading(false));
  }, []);                         // eslint-disable-line

  // ── Paginate: flat list of {illakaName, misalName, misalId, rows, startIdx, pageNum, totalPages, allRows}
  const pages = useMemo(() => {
    if (!data) return [];
    const out = [];
    for (const il of data.illakas) {
      for (const ms of il.misals) {
        const all = ms.rows;
        const np  = Math.max(1, Math.ceil(all.length / ROWS_PER_PAGE));
        for (let p = 0; p < np; p++) {
          out.push({
            illakaName: il.illaka_name,
            misalName:  ms.misal_name,
            misalId:    ms.misal_id,
            pageNum:    p + 1,
            totalPages: np,
            rows:       all.slice(p * ROWS_PER_PAGE, (p + 1) * ROWS_PER_PAGE),
            startIdx:   p * ROWS_PER_PAGE + 1,
            allRows:    all,
          });
        }
      }
    }
    return out;
  }, [data]);

  // Misal totals (collected per month + total)
  function misalTotals(allRows) {
    const byMonth = {};
    let total = 0;
    for (const row of allRows) {
      for (const yd of row.emi_year_data || []) {
        if (yd.status === "paid") {
          byMonth[yd.month] = (byMonth[yd.month] || 0) + (yd.paid_amount || 0);
          total += (yd.paid_amount || 0);
        }
      }
    }
    return { byMonth, total };
  }

  if (loading) return <div style={{padding:40,fontFamily:"sans-serif",color:"#475569"}}><b>Loading FY {getFyLabel(fyStart)} collection sheet…</b></div>;
  if (error)   return <div style={{padding:40,fontFamily:"sans-serif",color:"#dc2626"}}><b>Error:</b> {error}</div>;

  const printDate = new Date().toLocaleDateString("en-IN", {day:"numeric",month:"short",year:"numeric"});
  const totalClients = pages.reduce((a,p)=>a+p.rows.length, 0);

  return (
    <div>
      {/* ── Screen toolbar ── */}
      <div className="no-print" style={{position:"fixed",top:0,left:0,right:0,zIndex:999,background:"#0f172a",color:"#fff",padding:"8px 18px",display:"flex",alignItems:"center",gap:14,fontFamily:"sans-serif"}}>
        <div>
          <b style={{fontSize:14}}>Vasuli FY {getFyLabel(fyStart)}</b>
          <span style={{fontSize:12,color:"#94a3b8",marginLeft:10}}>{pages.length} pages · {totalClients} clients</span>
        </div>
        {duplex && (
          <span style={{fontSize:11,background:"#7c3aed",padding:"3px 12px",borderRadius:20,flexShrink:0}}>
            Duplex → In print dialog: Two-sided ON · Flip on Long Edge
          </span>
        )}
        <div style={{marginLeft:"auto",display:"flex",gap:10}}>
          <button onClick={()=>window.print()} style={{background:"#16a34a",color:"#fff",border:"none",padding:"7px 20px",borderRadius:8,fontWeight:700,cursor:"pointer",fontSize:14}}>Print / PDF</button>
          <button onClick={()=>window.close()} style={{background:"#475569",color:"#fff",border:"none",padding:"7px 14px",borderRadius:8,cursor:"pointer",fontSize:14}}>Close</button>
        </div>
      </div>

      {/* ── Pages ── */}
      {pages.map((page) => {
        const isLast = page.pageNum === page.totalPages;
        const tots   = isLast ? misalTotals(page.allRows) : null;
        // pad to exactly ROWS_PER_PAGE
        const padded = [...page.rows];
        while (padded.length < ROWS_PER_PAGE) padded.push(null);

        return (
          <div key={`${page.misalId}-${page.pageNum}`} className="print-page">

            {/* Page header */}
            <div className="page-header">
              <div>
                <h1>
                  बही खाता — वसूली पत्र &nbsp;/&nbsp; Collection Sheet
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  FY {getFyLabel(fyStart)}
                  {duplex && <span className="duplex-badge">Duplex · Long Edge</span>}
                </h1>
                <div className="sub">
                  इलाका: <b>{page.illakaName}</b>
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  मिसाल: <b>{page.misalName}</b>
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  Page {page.pageNum}/{page.totalPages}
                  &nbsp;&nbsp;|&nbsp;&nbsp;
                  Clients {page.startIdx}–{page.startIdx + page.rows.length - 1} of {page.allRows.length}
                </div>
              </div>
              <div className="right">
                <div><b>Printed:</b> {printDate}</div>
                <div>Apr {fyStart} → Mar {fyStart+1}</div>
              </div>
            </div>

            {/* Main table */}
            <table>
              <colgroup>
                <col className="sn"/>
                <col className="emi"/>
                <col className="names"/>
                <col className="prev"/>
                <col className="new"/>
                {fyMonths.map(m => <col key={m} className="mo"/>)}
                <col className="bal"/>
                <col className="sign"/>
              </colgroup>
              <thead>
                <tr>
                  <th>#</th>
                  <th>EMI ₹</th>
                  <th className="left">ग्राहक / Client</th>
                  <th className="mo-h">पिछली<br/>बाक़ी</th>
                  <th className="mo-h">किस्त<br/>हाल</th>
                  {FY_ABBR.map((a,i) => <th key={fyMonths[i]} className="mo-h">{a}</th>)}
                  <th className="blank-h">Bal. ₹</th>
                  <th className="blank-h">Sign</th>
                </tr>
              </thead>
              <tbody>
                {/* Misal name sub-header on page 1 of misal, or always for clarity */}
                <tr className="misal-hdr">
                  <td colSpan={5 + 12 + 2}>
                    मिसाल: {page.misalName} &nbsp;·&nbsp; {page.allRows.length} clients &nbsp;·&nbsp; Page {page.pageNum}/{page.totalPages}
                  </td>
                </tr>

                {padded.map((row, ri) => {
                  const sn = page.startIdx + ri;

                  // Empty padding row
                  if (!row) {
                    return (
                      <tr key={`e-${ri}`} className="row-empty">
                        <td className="c" style={{color:"#cbd5e1",fontSize:"6pt"}}>{sn}</td>
                        <td/><td/><td/><td/>
                        {fyMonths.map(m => <td key={m} className="mo-na"/>)}
                        <td className="blank"/><td className="blank"/>
                      </tr>
                    );
                  }

                  // Row class based on status
                  const rowCls =
                    row.is_gyal              ? "row-gyal"    :
                    row.emi_status==="netoff" ? "row-netoff"  :
                    row.emi_status==="paid"   ? "row-paid"    :
                    row.emi_status==="overdue"? "row-overdue" : "";

                  // Prev balance (old loan or net-off combined)
                  const loanYm     = row.loan_date ? row.loan_date.substring(0,7) : null;
                  const isOldLoan  = loanYm && loanYm < fyMonths[0];
                  const showPrev   = row.is_netoff_combined ? row.prev_opening_balance > 0 : isOldLoan;
                  const prevAmt    = row.is_netoff_combined ? row.prev_opening_balance : row.opening_balance;
                  const prevDate   = row.is_netoff_combined ? row.prev_loan_date : row.loan_date;

                  // New loan (disbursed in this FY)
                  const isNewLoan  = loanYm && loanYm >= fyMonths[0];
                  const showNew    = row.is_netoff_combined ? row.new_loan_in_fy===true : isNewLoan;
                  const extras     = row.extra_kisht_entries || [];

                  return (
                    <tr key={row.loan_db_id} className={rowCls}>
                      {/* Serial # */}
                      <td className="c" style={{fontWeight:600,fontSize:"6.5pt"}}>{sn}</td>

                      {/* EMI amount */}
                      <td className="r">
                        {(row.older_emi_chain||[]).map((a,i)=>(
                          <span key={i} className="stk">{fmtIN(a)}</span>
                        ))}
                        {row.is_netoff_combined && row.prev_emi_amount > 0 && (
                          <span className="stk">{fmtIN(row.prev_emi_amount)}</span>
                        )}
                        <span style={{fontWeight:700,fontSize:"7.5pt",display:"block"}}>{fmtIN(row.emi_amount)}</span>
                      </td>

                      {/* Names */}
                      <td className="lp">
                        <div style={{fontWeight:700,fontSize:"7.5pt",lineHeight:1.3}}>
                          {row.client_name_hindi || row.client_name}
                        </div>
                        {row.client_name_hindi && (
                          <div style={{fontSize:"6pt",color:"#64748b",lineHeight:1.2}}>{row.client_name}</div>
                        )}
                        {(row.relative_name_hindi||row.relative_name) && (
                          <div style={{fontSize:"6pt",color:"#64748b",lineHeight:1.2}}>
                            {row.relative_name_hindi||row.relative_name}
                          </div>
                        )}
                        {(row.guarantor_name_hindi||row.guarantor_name) && (
                          <div style={{fontSize:"6pt",color:"#2563eb",lineHeight:1.2}}>
                            {row.guarantor_name_hindi||row.guarantor_name}
                          </div>
                        )}
                      </td>

                      {/* Previous balance */}
                      <td className="r" style={{fontSize:"6.5pt"}}>
                        {showPrev && prevAmt > 0 && (
                          <>
                            <span style={{fontWeight:600,display:"block"}}>{fmtIN(prevAmt)}</span>
                            <span style={{color:"#64748b",fontSize:"5.5pt"}}>{fmtDate(prevDate)}</span>
                          </>
                        )}
                      </td>

                      {/* New loan */}
                      <td className="r" style={{fontSize:"6.5pt"}}>
                        {showNew && (
                          <>
                            {extras.map((e,i)=>(
                              <div key={i} style={{marginBottom:"1pt"}}>
                                <span style={{fontWeight:600,display:"block"}}>{fmtIN(e.amount)}</span>
                                <span style={{color:"#2563eb",fontSize:"5.5pt"}}>↩ {fmtDate(e.loan_date)}</span>
                              </div>
                            ))}
                            <span style={{fontWeight:600,display:"block"}}>{fmtIN(row.total_repayable)}</span>
                            <span style={{color: row.is_netoff_combined?"#2563eb":"#64748b",fontSize:"5.5pt"}}>
                              {row.is_netoff_combined?"↩ ":""}{fmtDate(row.loan_date)}
                            </span>
                          </>
                        )}
                      </td>

                      {/* 12-month cells */}
                      {(row.emi_year_data||fyMonths.map(()=>({status:"na",paid_amount:0}))).map((yd, mi) => {
                        const ym = fyMonths[mi];
                        if (yd.status==="na") {
                          return <td key={ym} className="mo-na"/>;
                        }
                        if (yd.status==="paid") {
                          return (
                            <td key={ym} className="mo-paid c">
                              <span className="tick">✓</span>
                              <span className="kamt">{fmtK(yd.paid_amount)}</span>
                              {yd.note && <span style={{display:"block",width:"6pt",height:"6pt",borderRadius:"50%",background:"#f59e0b",margin:"0 auto"}}/>}
                            </td>
                          );
                        }
                        if (yd.status==="netoff"||yd.status==="chain_start") {
                          return <td key={ym} className="mo-netoff c"><span className="arrow">↩</span></td>;
                        }
                        if (yd.note) {
                          return (
                            <td key={ym} className="mo-note c" style={{fontSize:"5.5pt",color:"#92400e"}}>
                              {yd.note.substring(0,12)}{yd.note.length>12?"…":""}
                            </td>
                          );
                        }
                        if (yd.status==="overdue") {
                          return <td key={ym} className="mo-overdue c"><span className="bang">!</span></td>;
                        }
                        // pending
                        return <td key={ym} className="mo-pending c"><span className="dot">·</span></td>;
                      })}

                      {/* Bal (blank) */}
                      <td className="blank"/>
                      {/* Sign (blank) */}
                      <td className="blank"/>
                    </tr>
                  );
                })}

                {/* Misal totals — last page only */}
                {isLast && tots && (
                  <tr className="total-row">
                    <td colSpan={5} className="r" style={{paddingRight:5,fontSize:"7pt"}}>
                      मिसाल कुल / Total ({page.allRows.length}):
                    </td>
                    {fyMonths.map(m => (
                      <td key={m} className="c" style={{color:"#15803d",fontWeight:700,fontSize:"6.5pt"}}>
                        {tots.byMonth[m] ? fmtK(tots.byMonth[m]) : ""}
                      </td>
                    ))}
                    <td className="blank"/><td className="blank"/>
                  </tr>
                )}
              </tbody>
            </table>

            {/* Page footer */}
            <div className="page-footer">
              <span>बही खाता &nbsp;·&nbsp; {page.illakaName}</span>
              <span>{page.misalName} &nbsp;·&nbsp; FY {getFyLabel(fyStart)}</span>
              <span>Page {page.pageNum}/{page.totalPages} &nbsp;·&nbsp; {printDate}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
