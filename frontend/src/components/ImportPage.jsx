import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import { useIllaka } from "./IllakaContext";
import {
  Upload, Download, CheckCircle, XCircle, AlertTriangle,
  FileSpreadsheet, FormInput, Loader2, ChevronRight, RotateCcw
} from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;

const fmtINR = (n) =>
  Number(n || 0).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

// ─── Opening Balance Form ────────────────────────────────────────────────────
function OpeningBalanceForm() {
  const { filteredIllakas } = useIllaka();
  const [misals, setMisals] = useState([]);
  const [form, setForm] = useState({
    illaka_id: "", misal_id: "", client_name: "", client_phone: "",
    co_borrower_name: "", guarantor_name: "", loan_date: "", opening_balance: "", emi_amount: "",
  });
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    if (!form.illaka_id) { setMisals([]); setForm(f => ({ ...f, misal_id: "" })); return; }
    axios.get(`${API}/api/misals?illaka_id=${form.illaka_id}`, { withCredentials: true })
      .then(r => setMisals(r.data || []))
      .catch(() => setMisals([]));
  }, [form.illaka_id]);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const previewEMIs = () => {
    const ob = parseFloat(form.opening_balance);
    const emi = parseFloat(form.emi_amount);
    if (ob > 0 && emi > 0) return Math.ceil(ob / emi);
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.illaka_id || !form.misal_id || !form.client_name || !form.loan_date || !form.opening_balance || !form.emi_amount) {
      toast.error("Please fill all required fields");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post(`${API}/api/import/opening-balance`, {
        ...form,
        opening_balance: parseFloat(form.opening_balance),
        emi_amount: parseFloat(form.emi_amount),
      }, { withCredentials: true });
      setSuccess(res.data);
      toast.success(`Imported: ${form.client_name} — Loan #${res.data.loan_number}`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setSuccess(null);
    setForm({ illaka_id: "", misal_id: "", client_name: "", client_phone: "", co_borrower_name: "", guarantor_name: "", loan_date: "", opening_balance: "", emi_amount: "" });
  };

  if (success) {
    return (
      <div className="max-w-lg mx-auto py-10 text-center space-y-4" data-testid="ob-success">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
          <CheckCircle className="text-green-600" size={32} />
        </div>
        <h2 className="text-xl font-bold text-foreground">Entry Created!</h2>
        <p className="text-sm text-muted-foreground">
          <span className="font-semibold text-foreground">{form.client_name}</span> — Loan <span className="font-mono font-semibold">{success.loan_number}</span>
        </p>
        <p className="text-sm text-muted-foreground">{success.emi_count} EMIs scheduled starting from this month.</p>
        <div className="flex justify-center gap-3 pt-2">
          <button onClick={reset} className="flex items-center gap-2 bg-primary text-white px-5 py-2 rounded-lg font-semibold text-sm hover:bg-primary/90 transition-colors">
            <RotateCcw size={15} /> Add Another
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-2xl mx-auto space-y-6" data-testid="ob-form">
      <div className="bk-card space-y-5">
        <div>
          <h2 className="font-semibold text-foreground text-base">Location</h2>
          <p className="text-xs text-muted-foreground">इलाका / मिसाल</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="bk-label">Illaka <span className="text-destructive">*</span></label>
            <select value={form.illaka_id} onChange={e => set("illaka_id", e.target.value)} className="bk-input" required data-testid="ob-illaka">
              <option value="">Select Illaka</option>
              {filteredIllakas.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}
            </select>
          </div>
          <div>
            <label className="bk-label">Misal <span className="text-destructive">*</span></label>
            <select value={form.misal_id} onChange={e => set("misal_id", e.target.value)} className="bk-input" required disabled={!form.illaka_id} data-testid="ob-misal">
              <option value="">Select Misal</option>
              {misals.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </div>
        </div>
      </div>

      <div className="bk-card space-y-5">
        <div>
          <h2 className="font-semibold text-foreground text-base">Borrower Details</h2>
          <p className="text-xs text-muted-foreground">उधारकर्ता की जानकारी</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="bk-label">Client Name <span className="text-destructive">*</span></label>
            <input value={form.client_name} onChange={e => set("client_name", e.target.value)} className="bk-input" placeholder="Primary borrower's name" required data-testid="ob-client-name" />
          </div>
          <div>
            <label className="bk-label">Client Phone</label>
            <input value={form.client_phone} onChange={e => set("client_phone", e.target.value)} className="bk-input" placeholder="10-digit mobile (optional)" maxLength={10} data-testid="ob-client-phone" />
          </div>
          <div>
            <label className="bk-label">Co-borrower Name</label>
            <input value={form.co_borrower_name} onChange={e => set("co_borrower_name", e.target.value)} className="bk-input" placeholder="Optional" data-testid="ob-coborrower" />
          </div>
          <div>
            <label className="bk-label">Guarantor Name</label>
            <input value={form.guarantor_name} onChange={e => set("guarantor_name", e.target.value)} className="bk-input" placeholder="Optional" data-testid="ob-guarantor" />
          </div>
        </div>
      </div>

      <div className="bk-card space-y-5">
        <div>
          <h2 className="font-semibold text-foreground text-base">Loan Details</h2>
          <p className="text-xs text-muted-foreground">कर्ज की जानकारी</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="bk-label">Original Loan Date <span className="text-destructive">*</span></label>
            <input type="date" value={form.loan_date} onChange={e => set("loan_date", e.target.value)} className="bk-input" required data-testid="ob-loan-date" />
          </div>
          <div>
            <label className="bk-label">Opening Balance (₹) <span className="text-destructive">*</span></label>
            <input type="number" min="1" value={form.opening_balance} onChange={e => set("opening_balance", e.target.value)} className="bk-input" placeholder="Outstanding amount" required data-testid="ob-opening-balance" />
          </div>
          <div>
            <label className="bk-label">EMI Amount (₹) <span className="text-destructive">*</span></label>
            <input type="number" min="1" value={form.emi_amount} onChange={e => set("emi_amount", e.target.value)} className="bk-input" placeholder="Monthly instalment" required data-testid="ob-emi-amount" />
          </div>
        </div>

        {previewEMIs() && (
          <div className="bg-muted/40 border border-border rounded-lg px-4 py-3 flex items-center gap-3" data-testid="ob-emi-preview">
            <ChevronRight size={15} className="text-primary" />
            <p className="text-sm text-foreground">
              <span className="font-semibold">{previewEMIs()} monthly EMIs</span> of{" "}
              <span className="font-semibold">{fmtINR(form.emi_amount)}</span> — starting from this month.
              {previewEMIs() > 1 && (
                <span className="text-muted-foreground"> (Last EMI: {fmtINR(parseFloat(form.opening_balance) - parseFloat(form.emi_amount) * (previewEMIs() - 1))})</span>
              )}
            </p>
          </div>
        )}
      </div>

      <button type="submit" disabled={loading} className="w-full flex items-center justify-center gap-2 bg-primary text-white py-3 rounded-lg font-semibold hover:bg-primary/90 transition-colors disabled:opacity-50" data-testid="ob-submit-btn">
        {loading ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle size={18} />}
        Create Opening Balance Entry
      </button>
    </form>
  );
}

// ─── Excel Import ────────────────────────────────────────────────────────────
function ExcelImport() {
  const fileRef = useRef();
  const [preview, setPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const res = await axios.get(`${API}/api/import/template`, {
        withCredentials: true, responseType: "blob"
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a"); a.href = url;
      a.download = "bahi_khata_import_template.xlsx"; a.click();
      window.URL.revokeObjectURL(url);
    } catch { toast.error("Failed to download template"); }
  };

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setPreview(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/api/import/excel/preview`, fd, {
        withCredentials: true,
        headers: { "Content-Type": "multipart/form-data" },
      });
      setPreview(res.data);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to parse file");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleConfirm = async () => {
    if (!preview?.valid_rows?.length) return;
    setConfirming(true);
    try {
      const res = await axios.post(`${API}/api/import/excel/confirm`,
        { rows: preview.valid_rows },
        { withCredentials: true }
      );
      setResult(res.data);
      toast.success(`Imported ${res.data.imported_count} client(s) successfully`);
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    } finally {
      setConfirming(false);
    }
  };

  const reset = () => { setPreview(null); setResult(null); };

  if (result) {
    return (
      <div className="max-w-xl mx-auto py-8 space-y-4 text-center" data-testid="excel-result">
        <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
          <CheckCircle className="text-green-600" size={32} />
        </div>
        <h2 className="text-xl font-bold text-foreground">Import Complete</h2>
        <div className="flex justify-center gap-6">
          <div className="text-center">
            <p className="text-3xl font-bold text-green-600">{result.imported_count}</p>
            <p className="text-xs text-muted-foreground mt-1">Imported</p>
          </div>
          {result.failed_count > 0 && (
            <div className="text-center">
              <p className="text-3xl font-bold text-destructive">{result.failed_count}</p>
              <p className="text-xs text-muted-foreground mt-1">Failed</p>
            </div>
          )}
        </div>
        {result.failed?.length > 0 && (
          <div className="text-left mt-4 space-y-1">
            {result.failed.map((f) => (
              <div key={f.client_name} className="flex items-center gap-2 text-xs text-destructive bg-destructive/10 rounded px-3 py-1.5">
                <XCircle size={13} /> {f.client_name}: {f.error}
              </div>
            ))}
          </div>
        )}
        <button onClick={reset} className="flex items-center gap-2 bg-primary text-white px-5 py-2 rounded-lg font-semibold text-sm hover:bg-primary/90 transition-colors mx-auto">
          <RotateCcw size={15} /> Import Another File
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6" data-testid="excel-import">
      {/* Step 1 — Download template */}
      <div className="bk-card">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Step 1</p>
            <h3 className="font-bold text-foreground">Download Template</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Fill in the Excel template with your client data. Required and optional fields are colour-coded.
            </p>
          </div>
          <button onClick={downloadTemplate} className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg font-semibold text-sm hover:bg-primary/90 transition-colors flex-shrink-0 ml-4" data-testid="download-template-btn">
            <Download size={15} /> Download
          </button>
        </div>
      </div>

      {/* Step 2 — Upload */}
      <div className="bk-card">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Step 2</p>
        <h3 className="font-bold text-foreground mb-1">Upload Filled File</h3>
        <p className="text-sm text-muted-foreground mb-4">Upload your filled Excel file (.xlsx). We'll validate every row before importing.</p>
        <div
          onClick={() => fileRef.current?.click()}
          className="border-2 border-dashed border-border rounded-xl py-10 text-center cursor-pointer hover:border-primary/50 hover:bg-muted/20 transition-all"
          data-testid="excel-upload-zone"
        >
          {uploading ? (
            <Loader2 size={28} className="animate-spin text-primary mx-auto mb-2" />
          ) : (
            <Upload size={28} className="text-muted-foreground mx-auto mb-2" />
          )}
          <p className="text-sm font-medium text-foreground">{uploading ? "Parsing file…" : "Click to select .xlsx file"}</p>
          <p className="text-xs text-muted-foreground mt-1">.xlsx only</p>
        </div>
        <input ref={fileRef} type="file" accept=".xlsx" onChange={handleFile} className="hidden" data-testid="excel-file-input" />
      </div>

      {/* Step 3 — Preview */}
      {preview && (
        <div className="bk-card space-y-4" data-testid="excel-preview">
          <div>
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">Step 3</p>
            <h3 className="font-bold text-foreground mb-0.5">Review & Confirm</h3>
            <div className="flex gap-4 mt-2">
              <span className="flex items-center gap-1.5 text-sm text-green-700 dark:text-green-400 font-semibold">
                <CheckCircle size={14} /> {preview.valid_count} ready
              </span>
              {preview.error_count > 0 && (
                <span className="flex items-center gap-1.5 text-sm text-destructive font-semibold">
                  <XCircle size={14} /> {preview.error_count} errors
                </span>
              )}
            </div>
          </div>

          {/* Valid rows table */}
          {preview.valid_rows.length > 0 && (
            <div className="overflow-x-auto border border-border rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-muted/50">
                  <tr>
                    {["Row", "Client", "Illaka / Misal", "Loan Date", "Balance", "EMI", "# EMIs"].map(h => (
                      <th key={h} className="px-3 py-2 text-left font-semibold text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.valid_rows.map((r) => (
                    <tr key={r.row} className="border-t border-border hover:bg-muted/20" data-testid={`preview-row-${r.row}`}>
                      <td className="px-3 py-2 text-muted-foreground">{r.row}</td>
                      <td className="px-3 py-2 font-medium text-foreground">
                        {r.client_name}
                        {r.client_phone && <span className="block text-muted-foreground text-[10px]">{r.client_phone}</span>}
                      </td>
                      <td className="px-3 py-2">{r.illaka_name} / {r.misal_name}</td>
                      <td className="px-3 py-2">{r.loan_date}</td>
                      <td className="px-3 py-2 font-semibold tabular-nums">{fmtINR(r.opening_balance)}</td>
                      <td className="px-3 py-2 tabular-nums">{fmtINR(r.emi_amount)}</td>
                      <td className="px-3 py-2 tabular-nums">{r.emi_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Error rows */}
          {preview.error_rows.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold text-destructive uppercase tracking-wide flex items-center gap-1.5">
                <AlertTriangle size={13} /> Rows with errors (fix in Excel and re-upload)
              </p>
              {preview.error_rows.map((r) => (
                <div key={r.row} className="border border-destructive/30 bg-destructive/5 rounded-lg px-3 py-2.5" data-testid={`error-row-${r.row}`}>
                  <p className="text-xs font-semibold text-foreground">Row {r.row}: {r.data.client_name || "(blank)"}</p>
                  <ul className="mt-1 space-y-0.5">
                    {r.errors.map((e, j) => <li key={j} className="text-xs text-destructive">• {e}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <button onClick={handleConfirm} disabled={confirming || preview.valid_count === 0}
              className="flex items-center gap-2 bg-green-600 text-white px-5 py-2.5 rounded-lg font-semibold text-sm hover:bg-green-700 transition-colors disabled:opacity-50"
              data-testid="excel-confirm-btn"
            >
              {confirming ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle size={15} />}
              Import {preview.valid_count} Client{preview.valid_count !== 1 ? "s" : ""}
            </button>
            <button onClick={() => { setPreview(null); fileRef.current?.click(); }}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-sm font-semibold hover:bg-muted/30 transition-colors"
            >
              <RotateCcw size={15} /> Re-upload
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────────
export default function ImportPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("ob");

  if (!["admin", "maalik"].includes(user?.role)) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Access restricted to Admin and Maalik
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground font-['Outfit']">Data Import</h1>
        <p className="text-sm text-muted-foreground mt-0.5">डेटा आयात — migrate your existing client & loan data</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-muted/40 p-1 rounded-xl border border-border w-fit" data-testid="import-tabs">
        <button
          onClick={() => setTab("ob")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${tab === "ob" ? "bg-card shadow-sm text-foreground border border-border" : "text-muted-foreground hover:text-foreground"}`}
          data-testid="tab-ob"
        >
          <FormInput size={15} /> Opening Balance Entry
        </button>
        <button
          onClick={() => setTab("excel")}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${tab === "excel" ? "bg-card shadow-sm text-foreground border border-border" : "text-muted-foreground hover:text-foreground"}`}
          data-testid="tab-excel"
        >
          <FileSpreadsheet size={15} /> Excel Import
        </button>
      </div>

      {tab === "ob" ? <OpeningBalanceForm /> : <ExcelImport />}
    </div>
  );
}
