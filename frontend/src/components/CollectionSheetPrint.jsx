import { useEffect, useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const ROWS_PER_PAGE = 10;

// ── helpers ───────────────────────────────────────────────────────────────
const fmtK    = (n) => n ? new Intl.NumberFormat("en-IN").format(Math.round(n)) : "";
const fmtDate = (s) => { if (!s) return ""; const d=new Date(s); return isNaN(d)?"":`${d.toLocaleString("hi-IN",{month:"short"})} ${d.getFullYear()}`; };

const HI_MONTH = ["अप्र","मई","जून","जुला","अग","सित","अक्टू","नव","दिस","जन","फर","मार"];

function getFyMonths(fyStart) {
  return Array.from({length:12},(_,i)=>{const m=((3+i)%12)+1;const y=m>=4?fyStart:fyStart+1;return`${y}-${String(m).padStart(2,"0")}`;});
}
function getFyLabel(s){ return `${String(s).slice(-2)}-${String(s+1).slice(-2)}`; }
function getCurrentFyStart(){ const d=new Date(); return d.getMonth()+1>=4?d.getFullYear():d.getFullYear()-1; }

// ── Pure black-and-white CSS ─────────────────────────────────────────────
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

* { box-sizing:border-box; }
body { font-family:'Noto Sans','Noto Sans Devanagari',sans-serif; font-size:7.5pt; color:#000; }

/* ── page chrome ── */
.page-header { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom:5px; border-bottom:1.5pt solid #000; padding-bottom:4px; }
.page-header .left-info { font-size:8pt; font-weight:700; color:#000; }
.page-header .sub { font-size:7pt; color:#333; margin-top:1px; }
.page-header .right { text-align:right; font-size:7pt; color:#333; }
.page-footer { display:flex; justify-content:space-between; margin-top:4px; font-size:6.5pt; color:#555; border-top:.5pt solid #888; padding-top:3px; }

/* ── index page ── */
.index-title { font-size:14pt; font-weight:900; text-align:center; margin-bottom:4px; }
.index-subtitle { font-size:8pt; text-align:center; color:#444; margin-bottom:16px; }
table.index-tbl { width:60%; margin:0 auto; border-collapse:collapse; font-size:9pt; }
table.index-tbl th { border:1pt solid #000; padding:5px 8px; font-weight:700; background:#e8e8e8; color:#000; text-align:center; }
table.index-tbl td { border:.7pt solid #333; padding:5px 8px; }
table.index-tbl tr:nth-child(even) td { background:#f5f5f5; }

/* ── main table ── */
table.main { width:100%; table-layout:fixed; border-collapse:collapse; font-size:7pt; }
col.sn    { width:1.5%; }
col.emi   { width:4.5%; }
col.names { width:15%;  }
col.prev  { width:5%;   }
col.new   { width:5%;   }
col.mo    { width:4.84%; }
col.bal   { width:4.5%; }
col.sign  { width:4.5%; }

/* ── header row ── */
thead tr { background:#fff; color:#000; }
th { padding:3px 2px; text-align:center; font-weight:700; border:.7pt solid #000; line-height:1.3; white-space:nowrap; overflow:hidden; }
th.left { text-align:left; padding-left:4px; }
th.mo-h { font-size:6pt; }
th.blank-h { background:#e8e8e8; }

/* ── data cells ── */
td { padding:3px 2px; border:.4pt solid #999; vertical-align:middle; }
td.c  { text-align:center; }
td.r  { text-align:right; padding-right:3px; }
td.lp { padding-left:4px; }

/* ── all rows: no colour ── */
tr.data-row td { background:#fff; }
tr.row-empty   { height:21pt; }
tr.row-empty td { background:#fff; }

/* ── month cells: B&W only ── */
td.mo-na      { background:#f0f0f0; }
td.mo-paid    { background:#fff; }
td.mo-overdue { background:#fff; }
td.mo-netoff  { background:#fff; }
td.mo-note    { background:#fff; }
td.mo-pending { background:#fff; }
td.mo-gyal    { background:#e8e8e8; }

/* text styles in month cells */
.tick  { font-weight:900; font-size:8pt; }
.kamt  { font-weight:700; font-size:6.5pt; display:block; }
.bang  { font-weight:900; font-size:9pt; }
.arrow { font-weight:900; font-size:8pt; }
.dot   { color:#bbb; font-size:10pt; }

/* strikethrough for prev EMI amounts */
.stk { text-decoration:line-through; color:#666; font-size:6pt; display:block; }

/* ── totals row ── */
tr.total-row td { background:#e8e8e8!important; font-weight:700; border-top:1.5pt solid #000; }

/* ── blank columns: diagonal hatching ── */
td.blank { background: repeating-linear-gradient(45deg,#fff,#fff 4pt,#e8e8e8 4pt,#e8e8e8 5pt)!important; }

/* ── gyal separator ── */
tr.gyal-sep td { border-top:1pt dashed #888; padding:2px 4px; font-size:6pt; color:#555; background:#f5f5f5!important; }
`;

export default function CollectionSheetPrint() {
  const [searchParams]    = useSearchParams();
  const illakaId          = searchParams.get("illaka_id");
  const fyStart           = Number(searchParams.get("fy_start")) || getCurrentFyStart();
  const duplex            = searchParams.get("duplex") === "true";
  const blankRowsBeforeGyal = Math.max(0, Math.min(20, Number(searchParams.get("blank_rows")) || 0));

  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);

  const fyMonths = useMemo(() => getFyMonths(fyStart), [fyStart]);

  useEffect(() => {
    const el = document.createElement("style");
    el.textContent = CSS;
    document.head.appendChild(el);
    return () => document.head.removeChild(el);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams({ month: fyMonths[0] });
    if (illakaId) params.append("illaka_id", illakaId);
    axios.get(`${API}/collections/sheet?${params}`, { withCredentials: true })
      .then(r => setData(r.data))
      .catch(() => setError("डेटा लोड नहीं हुआ। कृपया पुनः लॉगिन करें।"))
      .finally(() => setLoading(false));
  }, []);           // eslint-disable-line

  // ── Build pages: gyal rows at the bottom of every misal ─────────────────
  const { pages, indexData } = useMemo(() => {
    if (!data) return { pages: [], indexData: [] };
    const out  = [];
    const idx  = [];    // for index page
    let globalPage = 2; // page 1 = index

    for (const il of data.illakas) {
      for (const ms of il.misals) {
        // Sort: regular rows first, then blank spacers, then gyal at bottom
        const regular = ms.rows.filter(r => !r.is_gyal);
        const gyal    = ms.rows.filter(r =>  r.is_gyal);

        // Insert null spacer rows between regular and gyal (only if gyal exists)
        const spacers = gyal.length > 0
          ? Array.from({ length: blankRowsBeforeGyal }, () => ({ __blank: true }))
          : [];

        const allRows = [...regular, ...spacers, ...gyal];

        const np = Math.max(1, Math.ceil(allRows.length / ROWS_PER_PAGE));
        const startGlobal = globalPage;

        for (let p = 0; p < np; p++) {
          const sliceRows = allRows.slice(p * ROWS_PER_PAGE, (p + 1) * ROWS_PER_PAGE);
          out.push({
            illakaName:  il.illaka_name,
            misalName:   ms.misal_name,
            misalId:     ms.misal_id,
            pageNum:     p + 1,
            totalPages:  np,
            rows:        sliceRows,
            startIdx:    p * ROWS_PER_PAGE + 1,
            allRows,
            gyalStart:   regular.length + spacers.length + 1,   // serial # where gyal starts
            globalPage:  globalPage++,
          });
        }

        idx.push({
          misalName:  ms.misal_name,
          clients:    regular.length + gyal.length,   // don't count blank spacers
          fromPage:   startGlobal,
          toPage:     globalPage - 1,
        });
      }
    }
    return { pages: out, indexData: idx };
  }, [data, blankRowsBeforeGyal]);

  // Misal totals
  function misalTotals(allRows) {
    const byMonth = {};
    let total = 0;
    for (const row of allRows) {
      if (row?.__blank) continue;   // skip blank spacers
      for (const yd of row.emi_year_data || []) {
        if (yd.status === "paid") {
          byMonth[yd.month] = (byMonth[yd.month] || 0) + (yd.paid_amount || 0);
          total += (yd.paid_amount || 0);
        }
      }
    }
    return { byMonth, total };
  }

  if (loading) return <div style={{padding:40,fontFamily:"sans-serif"}}>वित्तीय वर्ष {getFyLabel(fyStart)} का डेटा लोड हो रहा है…</div>;
  if (error)   return <div style={{padding:40,fontFamily:"sans-serif",color:"red"}}>{error}</div>;

  const printDate = new Date().toLocaleDateString("hi-IN", {day:"numeric",month:"long",year:"numeric"});
  const illakaName = pages[0]?.illakaName || "";
  const totalClients = indexData.reduce((a,m) => a + m.clients, 0);

  return (
    <div>
      {/* ── Screen toolbar ── */}
      <div className="no-print" style={{position:"fixed",top:0,left:0,right:0,zIndex:999,background:"#0f172a",color:"#fff",padding:"8px 18px",display:"flex",alignItems:"center",gap:14,fontFamily:"sans-serif"}}>
        <div>
          <b style={{fontSize:14}}>वसूली पत्र — वि.व. {getFyLabel(fyStart)}</b>
          <span style={{fontSize:12,color:"#94a3b8",marginLeft:10}}>{pages.length + 1} पृष्ठ · {totalClients} ग्राहक</span>
        </div>
        {duplex && (
          <span style={{fontSize:11,background:"#7c3aed",padding:"3px 12px",borderRadius:20,flexShrink:0}}>
            Duplex → Two-sided ON · Flip on Long Edge
          </span>
        )}
        <div style={{marginLeft:"auto",display:"flex",gap:10}}>
          <button onClick={()=>window.print()} style={{background:"#15803d",color:"#fff",border:"none",padding:"7px 20px",borderRadius:8,fontWeight:700,cursor:"pointer",fontSize:14}}>मुद्रण / PDF</button>
          <button onClick={()=>window.close()} style={{background:"#475569",color:"#fff",border:"none",padding:"7px 14px",borderRadius:8,cursor:"pointer",fontSize:14}}>बंद करें</button>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          PAGE 1 — INDEX
      ══════════════════════════════════════════════════════════════════ */}
      <div className="print-page">
        <div style={{height:"100%",display:"flex",flexDirection:"column",justifyContent:"center"}}>
          <div className="index-title">वसूली पत्र — अनुक्रमणिका</div>
          <div className="index-subtitle">
            इलाका: {illakaName} &nbsp;|&nbsp; वित्तीय वर्ष: {getFyLabel(fyStart)} &nbsp;|&nbsp;
            (अप्रैल {fyStart} — मार्च {fyStart+1}) &nbsp;|&nbsp;
            कुल ग्राहक: {totalClients} &nbsp;|&nbsp; मुद्रण दिनांक: {printDate}
          </div>

          <table className="index-tbl">
            <thead>
              <tr>
                <th>क्र.सं.</th>
                <th>मिसाल का नाम</th>
                <th>ग्राहकों की संख्या</th>
                <th>पृष्ठ संख्या</th>
              </tr>
            </thead>
            <tbody>
              {indexData.map((m, i) => (
                <tr key={m.misalName}>
                  <td style={{textAlign:"center"}}>{i + 1}</td>
                  <td style={{fontWeight:700}}>{m.misalName}</td>
                  <td style={{textAlign:"center"}}>{m.clients}</td>
                  <td style={{textAlign:"center"}}>
                    {m.fromPage === m.toPage ? m.fromPage : `${m.fromPage} – ${m.toPage}`}
                  </td>
                </tr>
              ))}
              {/* Grand total row */}
              <tr style={{fontWeight:700,borderTop:"1.5pt solid #000"}}>
                <td colSpan={2} style={{textAlign:"right"}}>कुल योग:</td>
                <td style={{textAlign:"center"}}>{totalClients}</td>
                <td style={{textAlign:"center"}}>2 – {pages.length + 1}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Index footer */}
        <div className="page-footer">
          <span>इलाका: {illakaName}</span>
          <span>वसूली पत्र — वि.व. {getFyLabel(fyStart)}</span>
          <span>पृष्ठ १ / {pages.length + 1}</span>
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════════════
          CONTENT PAGES
      ══════════════════════════════════════════════════════════════════ */}
      {pages.map((page) => {
        const isLast = page.pageNum === page.totalPages;
        const tots   = isLast ? misalTotals(page.allRows) : null;
        const padded = [...page.rows];
        while (padded.length < ROWS_PER_PAGE) padded.push(null);

        return (
          <div key={`${page.misalId}-${page.pageNum}`} className="print-page">

            {/* ── Compact page header (no big title) ── */}
            <div className="page-header">
              <div>
                <div className="left-info">
                  इलाका: {page.illakaName} &nbsp;|&nbsp; मिसाल: {page.misalName}
                </div>
                <div className="sub">
                  वित्तीय वर्ष: {getFyLabel(fyStart)}
                  (अप्रैल {fyStart} — मार्च {fyStart+1})
                  &nbsp;|&nbsp;
                  ग्राहक {page.startIdx}–{page.startIdx + page.rows.length - 1} / {page.allRows.length}
                </div>
              </div>
              <div className="right">
                <div>मुद्रण दिनांक: {printDate}</div>
                <div>पृष्ठ {page.globalPage} / {pages.length + 1}</div>
              </div>
            </div>

            {/* ── Table ── */}
            <table className="main">
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
                  <th>क्र.</th>
                  <th>किस्त ₹</th>
                  <th className="left">ग्राहक</th>
                  <th className="mo-h">पिछली<br/>बाक़ी</th>
                  <th className="mo-h">किस्त<br/>हाल</th>
                  {HI_MONTH.map((a,i) => <th key={fyMonths[i]} className="mo-h">{a}</th>)}
                  <th className="blank-h">शेष ₹</th>
                  <th className="blank-h">हस्ताक्षर</th>
                </tr>
              </thead>
              <tbody>
                {padded.map((row, ri) => {
                  const sn = page.startIdx + ri;

                  // Empty padding row (end-of-page filler) or __blank spacer
                  if (!row || row.__blank) {
                    return (
                      <tr key={`e-${ri}`} className="row-empty">
                        <td className="c" style={{color:"#aaa",fontSize:"6pt"}}>{row?.__blank ? "" : sn}</td>
                        <td/><td/><td/><td/>
                        {fyMonths.map(m => <td key={m} className="mo-na"/>)}
                        <td className="blank"/><td className="blank"/>
                      </tr>
                    );
                  }

                  const isGyal = !!row.is_gyal;

                  // Gyal separator line before first gyal row (skip blank spacers)
                  const prevRow = ri > 0 ? padded[ri-1] : null;
                  const showGyalSep = isGyal && (ri === 0 || (!prevRow?.is_gyal && !prevRow?.__blank));

                  // Prev balance
                  const loanYm   = row.loan_date ? row.loan_date.substring(0,7) : null;
                  const isOld    = loanYm && loanYm < fyMonths[0];
                  const showPrev = row.is_netoff_combined ? row.prev_opening_balance > 0 : isOld;
                  const prevAmt  = row.is_netoff_combined ? row.prev_opening_balance : row.opening_balance;
                  const prevDate = row.is_netoff_combined ? row.prev_loan_date : row.loan_date;

                  // New loan
                  const isNew   = loanYm && loanYm >= fyMonths[0];
                  const showNew = row.is_netoff_combined ? row.new_loan_in_fy===true : isNew;
                  const extras  = row.extra_kisht_entries || [];

                  const moCls = isGyal ? "mo-gyal" : "mo-paid";   // gyal months slightly shaded

                  return (
                    <>
                      {showGyalSep && (
                        <tr key={`gyal-sep-${ri}`} className="gyal-sep">
                          <td colSpan={5 + 12 + 2}>
                            — घ्याल (Gyal) ग्राहक —
                          </td>
                        </tr>
                      )}
                      <tr key={row.loan_db_id} className="data-row">
                        {/* क्र. */}
                        <td className="c" style={{fontWeight:600,fontSize:"6.5pt"}}>{sn}</td>

                        {/* किस्त */}
                        <td className="r">
                          {(row.older_emi_chain||[]).map((a,i)=>(
                            <span key={i} className="stk">{fmtK(a)}</span>
                          ))}
                          {row.is_netoff_combined && row.prev_emi_amount > 0 && (
                            <span className="stk">{fmtK(row.prev_emi_amount)}</span>
                          )}
                          <span style={{fontWeight:700,fontSize:"7.5pt",display:"block"}}>{fmtK(row.emi_amount)}</span>
                        </td>

                        {/* ग्राहक */}
                        <td className="lp">
                          <div style={{fontWeight:700,fontSize:"7.5pt",lineHeight:1.3}}>
                            {row.client_name_hindi || row.client_name}
                          </div>
                          {row.client_name_hindi && (
                            <div style={{fontSize:"6pt",color:"#444",lineHeight:1.2}}>{row.client_name}</div>
                          )}
                          {(row.relative_name_hindi||row.relative_name) && (
                            <div style={{fontSize:"6pt",color:"#444",lineHeight:1.2}}>
                              {row.relative_name_hindi||row.relative_name}
                            </div>
                          )}
                        </td>

                        {/* पिछली बाक़ी */}
                        <td className="r" style={{fontSize:"6.5pt"}}>
                          {showPrev && prevAmt > 0 && (
                            <>
                              <span style={{fontWeight:600,display:"block"}}>{fmtK(prevAmt)}</span>
                              <span style={{color:"#555",fontSize:"5.5pt"}}>{fmtDate(prevDate)}</span>
                            </>
                          )}
                        </td>

                        {/* किस्त हाल */}
                        <td className="r" style={{fontSize:"6.5pt"}}>
                          {showNew && (
                            <>
                              {extras.map((e,i)=>(
                                <div key={i} style={{marginBottom:"1pt"}}>
                                  <span style={{fontWeight:600,display:"block"}}>{fmtK(e.amount)}</span>
                                  <span style={{fontSize:"5.5pt"}}>↩ {fmtDate(e.loan_date)}</span>
                                </div>
                              ))}
                              <span style={{fontWeight:600,display:"block"}}>{fmtK(row.total_repayable)}</span>
                              <span style={{fontSize:"5.5pt"}}>{row.is_netoff_combined?"↩ ":""}{fmtDate(row.loan_date)}</span>
                            </>
                          )}
                        </td>

                        {/* १२ माह */}
                        {(row.emi_year_data||fyMonths.map(()=>({status:"na",paid_amount:0}))).map((yd,mi)=>{
                          const ym = fyMonths[mi];
                          if (isGyal) return <td key={ym} className="mo-gyal c"><span className="dot">·</span></td>;
                          if (yd.status==="na")      return <td key={ym} className="mo-na"/>;
                          if (yd.status==="paid")    return (
                            <td key={ym} className="mo-paid c">
                              <span className="tick">✓</span>
                              <span className="kamt">{fmtK(yd.paid_amount)}</span>
                              {yd.note && <span style={{fontSize:"5pt",display:"block"}}>*</span>}
                            </td>
                          );
                          if (yd.status==="netoff"||yd.status==="chain_start")
                            return <td key={ym} className="mo-netoff c"><span className="arrow">↩</span></td>;
                          if (yd.note)
                            return <td key={ym} className="mo-note c" style={{fontSize:"5.5pt"}}>{yd.note.substring(0,10)}{yd.note.length>10?"…":""}</td>;
                          if (yd.status==="overdue") return <td key={ym} className="mo-overdue c"><span className="bang">!</span></td>;
                          return <td key={ym} className="mo-pending c"><span className="dot">·</span></td>;
                        })}

                        {/* शेष (blank) */}
                        <td className="blank"/>
                        {/* हस्ताक्षर (blank) */}
                        <td className="blank"/>
                      </tr>
                    </>
                  );
                })}

                {/* मिसाल कुल — last page only */}
                {isLast && tots && (
                  <tr className="total-row">
                    <td colSpan={5} className="r" style={{paddingRight:5,fontSize:"7pt"}}>
                      मिसाल कुल ({page.allRows.filter(r => !r?.__blank).length} ग्राहक):
                    </td>
                    {fyMonths.map(m => (
                      <td key={m} className="c" style={{fontWeight:700,fontSize:"6.5pt"}}>
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
              <span>इलाका: {page.illakaName}</span>
              <span>मिसाल: {page.misalName} — वि.व. {getFyLabel(fyStart)}</span>
              <span>पृष्ठ {page.globalPage} / {pages.length + 1}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
