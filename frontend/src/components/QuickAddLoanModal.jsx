import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { X, ChevronDown, ChevronUp, Zap, CheckCircle2, Search, UserCheck, UserPlus, XCircle } from "lucide-react";
import { useIllaka } from "./IllakaContext";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SUFFIXES = [
  "Dhobi","Darji","Kumhar","Lohar","Teli","Nai","Kori","Mallah","Kewat","Kahar",
  "Yadav","Maurya","Prajapati","Kushwaha","Pasi","Bind","Rajput","Thakur","Sharma",
  "Gupta","Dubey","Mishra","Chamar",
];

function calcEmi(principal) {
  const p = Number(principal);
  if (!p || p <= 0) return { emi: 0, interest: 0, total: 0 };
  const emi = Math.round(p * 120 / 103 / 12 / 10) * 10;
  const total = emi * 12;
  return { emi, interest: total - p, total };
}

function fmt(n) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n);
}

const todayMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export default function QuickAddLoanModal({ open, onClose, onSuccess }) {
  const { eligibleIllakas } = useIllaka();
  const [mode, setMode] = useState("new"); // "new" | "existing"

  // Existing customer search state
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState(null); // { kyc_id, customer_id, name, illaka_name, misal_name }
  const searchTimer = useRef(null);

  // New customer fields
  const [illakaId, setIllakaId] = useState("");
  const [illakaName, setIllakaName] = useState("");
  const [misalId, setMisalId] = useState("");
  const [misalName, setMisalName] = useState("");
  const [misals, setMisals] = useState([]);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [suffix, setSuffix] = useState("");
  const [urfText, setUrfText] = useState("");
  const [showCo, setShowCo] = useState(false);
  const [coName, setCoName] = useState("");
  const [coPhone, setCoPhone] = useState("");
  const [showGuar, setShowGuar] = useState(false);
  const [guarName, setGuarName] = useState("");
  const [guarPhone, setGuarPhone] = useState("");

  // Shared fields
  const [principal, setPrincipal] = useState("");
  const [loanMonth, setLoanMonth] = useState(todayMonth());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(null);

  useEffect(() => {
    if (!illakaId) { setMisals([]); setMisalId(""); setMisalName(""); return; }
    axios.get(`${API}/misals?illaka_id=${illakaId}`, { withCredentials: true })
      .then(r => setMisals(r.data || []))
      .catch(() => {});
  }, [illakaId]);

  // Debounced search for existing customers
  useEffect(() => {
    if (mode !== "existing") return;
    if (!searchQuery.trim() || searchQuery.length < 2) { setSearchResults([]); return; }
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await axios.get(`${API}/kycs?search=${encodeURIComponent(searchQuery)}&limit=8`, { withCredentials: true });
        setSearchResults(res.data.kycs || []);
      } catch { setSearchResults([]); }
      finally { setSearchLoading(false); }
    }, 350);
    return () => clearTimeout(searchTimer.current);
  }, [searchQuery, mode]);

  const { emi, interest, total } = calcEmi(principal);
  const computedSuffix = suffix === "Urf" ? (urfText.trim() ? `Urf ${urfText.trim()}` : "") : suffix;

  const reset = () => {
    setMode("new");
    setSearchQuery(""); setSearchResults([]); setSelectedCustomer(null);
    setIllakaId(""); setIllakaName(""); setMisalId(""); setMisalName(""); setMisals([]);
    setName(""); setPhone(""); setSuffix(""); setUrfText("");
    setShowCo(false); setCoName(""); setCoPhone("");
    setShowGuar(false); setGuarName(""); setGuarPhone("");
    setPrincipal(""); setError(""); setSuccess(null);
    setLoanMonth(todayMonth());
  };

  const handleClose = () => { reset(); onClose(); };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (mode === "existing") {
      if (!selectedCustomer) { setError("Please search and select an existing customer"); return; }
    } else {
      if (!illakaId || !misalId) { setError("Please select Illaka and Misal"); return; }
      if (!name.trim()) { setError("Borrower name is required"); return; }
    }
    if (!principal || Number(principal) <= 0) { setError("Principal amount must be greater than 0"); return; }

    setSubmitting(true);
    try {
      const payload = mode === "existing"
        ? {
            // Existing customer — only needs principal + month + kyc ref
            // illaka/misal/name fetched from KYC on backend
            illaka_id: selectedCustomer.illaka_id,
            illaka_name: selectedCustomer.illaka_name,
            misal_id: selectedCustomer.misal_id,
            misal_name: selectedCustomer.misal_name,
            name: selectedCustomer.name,
            existing_kyc_id: selectedCustomer.kyc_id,
            principal_amount: Number(principal),
            loan_month: loanMonth,
          }
        : {
            illaka_id: illakaId, illaka_name: illakaName,
            misal_id: misalId, misal_name: misalName,
            name: name.trim(),
            phone: phone.trim() || null,
            suffix: computedSuffix || null,
            co_borrower_name: showCo && coName.trim() ? coName.trim() : null,
            co_borrower_phone: showCo && coPhone.trim() ? coPhone.trim() : null,
            guarantor_name: showGuar && guarName.trim() ? guarName.trim() : null,
            guarantor_phone: showGuar && guarPhone.trim() ? guarPhone.trim() : null,
            principal_amount: Number(principal),
            loan_month: loanMonth,
          };

      const res = await axios.post(`${API}/kycs/quick-loan`, payload, { withCredentials: true });
      setSuccess(res.data);
      toast.success(`Loan created: ${res.data.loan_number}`);
      onSuccess && onSuccess(res.data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const errMsg = typeof detail === "string"
        ? detail
        : Array.isArray(detail)
        ? "Validation error: please check all required fields."
        : "Failed to create loan. Please try again.";
      setError(errMsg);
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" data-testid="quick-add-loan-modal">
      <div className="bg-card border border-border rounded-2xl w-full max-w-lg max-h-[92vh] overflow-y-auto shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border sticky top-0 bg-card z-10">
          <div className="flex items-center gap-2">
            <Zap size={20} className="text-primary" />
            <div>
              <h2 className="text-base font-bold text-foreground">Quick Add Loan</h2>
              <p className="text-xs text-muted-foreground">No Aadhaar or photo needed</p>
            </div>
          </div>
          <button onClick={handleClose} className="p-1.5 rounded-lg hover:bg-muted transition-colors" data-testid="quick-add-loan-close">
            <X size={18} />
          </button>
        </div>

        {/* Success state */}
        {success ? (
          <div className="p-6 text-center space-y-4">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto">
              <CheckCircle2 size={32} className="text-green-600" />
            </div>
            <h3 className="text-xl font-bold text-foreground">Loan Created!</h3>
            <div className="bg-muted rounded-xl p-4 text-left space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Customer ID</span>
                <span className="font-bold font-mono text-primary">{success.customer_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Loan Number</span>
                <span className="font-bold font-mono">{success.loan_number}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">EMI / किस्त</span>
                <span className="font-semibold text-green-700">{fmt(success.emi_amount)} × 12</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Interest / ब्याज</span>
                <span className="font-semibold text-orange-600">{fmt(success.interest_amount)}</span>
              </div>
              <div className="flex justify-between border-t border-border pt-2 mt-2">
                <span className="text-muted-foreground font-medium">Total Repayable</span>
                <span className="font-bold text-foreground">{fmt(success.total_repayable)}</span>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => { reset(); }}
                className="flex-1 px-4 py-2.5 rounded-xl border border-border hover:bg-muted text-sm font-medium transition-colors"
                data-testid="quick-add-another-btn"
              >
                Add Another
              </button>
              <button
                onClick={handleClose}
                className="flex-1 px-4 py-2.5 rounded-xl bg-primary text-white text-sm font-semibold hover:bg-primary/90 transition-colors"
                data-testid="quick-add-done-btn"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="p-6 space-y-4">

            {/* Mode Toggle */}
            <div className="flex rounded-xl border border-border overflow-hidden">
              <button
                type="button"
                onClick={() => { setMode("new"); setSelectedCustomer(null); setSearchQuery(""); setSearchResults([]); }}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-semibold transition-colors ${mode === "new" ? "bg-primary text-white" : "bg-muted/40 text-muted-foreground hover:bg-muted"}`}
                data-testid="quick-mode-new"
              >
                <UserPlus size={15} /> New Client
              </button>
              <button
                type="button"
                onClick={() => { setMode("existing"); }}
                className={`flex-1 flex items-center justify-center gap-2 py-2.5 text-sm font-semibold transition-colors ${mode === "existing" ? "bg-primary text-white" : "bg-muted/40 text-muted-foreground hover:bg-muted"}`}
                data-testid="quick-mode-existing"
              >
                <UserCheck size={15} /> Existing Client
              </button>
            </div>

            {/* ── EXISTING CLIENT: Search ── */}
            {mode === "existing" && (
              <div className="space-y-2">
                <label className="bk-label">Search Customer / ग्राहक खोजें *</label>
                {selectedCustomer ? (
                  <div className="flex items-center gap-3 p-3 rounded-xl bg-primary/5 border border-primary/30" data-testid="quick-selected-customer">
                    <UserCheck size={18} className="text-primary flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm truncate">{selectedCustomer.name}</p>
                      <p className="text-xs text-muted-foreground">{selectedCustomer.customer_id} · {selectedCustomer.illaka_name} › {selectedCustomer.misal_name}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => { setSelectedCustomer(null); setSearchQuery(""); }}
                      className="shrink-0 text-muted-foreground hover:text-destructive transition-colors"
                      data-testid="quick-clear-customer"
                    >
                      <XCircle size={18} />
                    </button>
                  </div>
                ) : (
                  <div className="relative">
                    <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      className="bk-input pl-9"
                      placeholder="Name or Customer ID (e.g. DE0001)"
                      autoFocus
                      data-testid="quick-customer-search"
                    />
                    {searchLoading && (
                      <div className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    )}
                    {searchResults.length > 0 && (
                      <div className="absolute z-20 top-full mt-1 w-full bg-card border border-border rounded-xl shadow-lg overflow-hidden max-h-52 overflow-y-auto" data-testid="quick-search-results">
                        {searchResults.map(k => (
                          <button
                            key={k.id}
                            type="button"
                            className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted transition-colors border-b border-border/50 last:border-0"
                            onClick={() => {
                              setSelectedCustomer({
                                kyc_id: k.id,
                                customer_id: k.customer_id,
                                name: k.primary_borrower?.name || "",
                                illaka_id: k.illaka_id,
                                illaka_name: k.illaka_name,
                                misal_id: k.misal_id,
                                misal_name: k.misal_name,
                              });
                              setSearchResults([]);
                              setSearchQuery("");
                            }}
                            data-testid={`quick-search-result-${k.customer_id}`}
                          >
                            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                              <span className="text-xs font-bold text-primary">{(k.primary_borrower?.name || "?")[0]}</span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-semibold truncate">{k.primary_borrower?.name}</p>
                              <p className="text-xs text-muted-foreground">{k.customer_id} · {k.illaka_name}</p>
                            </div>
                          </button>
                        ))}
                      </div>
                    )}
                    {!searchLoading && searchQuery.length >= 2 && searchResults.length === 0 && (
                      <p className="absolute z-20 top-full mt-1 w-full bg-card border border-border rounded-xl shadow px-4 py-3 text-sm text-muted-foreground">
                        No customers found
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── NEW CLIENT: Illaka + Misal + Name ── */}
            {mode === "new" && (<>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="bk-label">Illaka *</label>
                  <select
                    value={illakaId}
                    onChange={e => {
                      const ill = eligibleIllakas.find(i => i.id === e.target.value);
                      setIllakaId(e.target.value);
                      setIllakaName(ill?.name || "");
                      setMisalId(""); setMisalName("");
                    }}
                    className="bk-input"
                    data-testid="quick-illaka-select"
                    required
                  >
                    <option value="">— Select —</option>
                    {eligibleIllakas.map(ill => <option key={ill.id} value={ill.id}>{ill.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="bk-label">Misal *</label>
                  <select
                    value={misalId}
                    onChange={e => {
                      const m = misals.find(x => x.id === e.target.value);
                      setMisalId(e.target.value);
                      setMisalName(m?.name || "");
                    }}
                    className="bk-input"
                    data-testid="quick-misal-select"
                    disabled={!illakaId || misals.length === 0}
                    required
                  >
                    <option value="">— Select —</option>
                    {misals.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className="bk-label">Borrower Name / नाम *</label>
                  <input
                    type="text"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    className="bk-input"
                    placeholder="Full name"
                    data-testid="quick-name-input"
                    required
                  />
                </div>
                <div>
                  <label className="bk-label">Suffix</label>
                  <select
                    value={suffix}
                    onChange={e => setSuffix(e.target.value)}
                    className="bk-input"
                    data-testid="quick-suffix-select"
                  >
                    <option value="">None</option>
                    {SUFFIXES.map(s => <option key={s} value={s}>{s}</option>)}
                    <option value="Urf">Urf...</option>
                  </select>
                </div>
              </div>
              {suffix === "Urf" && (
                <input
                  type="text"
                  value={urfText}
                  onChange={e => setUrfText(e.target.value)}
                  className="bk-input"
                  placeholder="Nickname / उर्फ़ नाम"
                  data-testid="quick-urf-input"
                />
              )}

              <div>
                <label className="bk-label">
                  Phone / फ़ोन <span className="text-muted-foreground font-normal">(optional)</span>
                </label>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  className="bk-input"
                  placeholder="10-digit mobile"
                  maxLength={10}
                  data-testid="quick-phone-input"
                />
              </div>

              <div className="border border-border rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setShowCo(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium bg-muted/40 hover:bg-muted/70 transition-colors"
                  data-testid="quick-coborrower-toggle"
                >
                  <span>Co-borrower / सह-ऋणी <span className="text-muted-foreground font-normal">(optional)</span></span>
                  {showCo ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {showCo && (
                  <div className="p-4 grid grid-cols-2 gap-3">
                    <div>
                      <label className="bk-label">Name</label>
                      <input type="text" value={coName} onChange={e => setCoName(e.target.value)} className="bk-input" placeholder="Name" data-testid="quick-co-name-input" />
                    </div>
                    <div>
                      <label className="bk-label">Phone</label>
                      <input type="tel" value={coPhone} onChange={e => setCoPhone(e.target.value)} className="bk-input" placeholder="Phone" maxLength={10} data-testid="quick-co-phone-input" />
                    </div>
                  </div>
                )}
              </div>

              <div className="border border-border rounded-xl overflow-hidden">
                <button
                  type="button"
                  onClick={() => setShowGuar(v => !v)}
                  className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium bg-muted/40 hover:bg-muted/70 transition-colors"
                  data-testid="quick-guarantor-toggle"
                >
                  <span>Guarantor / ज़मानतदार <span className="text-muted-foreground font-normal">(optional)</span></span>
                  {showGuar ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {showGuar && (
                  <div className="p-4 grid grid-cols-2 gap-3">
                    <div>
                      <label className="bk-label">Name</label>
                      <input type="text" value={guarName} onChange={e => setGuarName(e.target.value)} className="bk-input" placeholder="Name" data-testid="quick-guar-name-input" />
                    </div>
                    <div>
                      <label className="bk-label">Phone</label>
                      <input type="tel" value={guarPhone} onChange={e => setGuarPhone(e.target.value)} className="bk-input" placeholder="Phone" maxLength={10} data-testid="quick-guar-phone-input" />
                    </div>
                  </div>
                )}
              </div>
            </>)}

            {/* Principal + Loan Month */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="bk-label">Principal Amount *</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm font-semibold">₹</span>
                  <input
                    type="number"
                    value={principal}
                    onChange={e => setPrincipal(e.target.value)}
                    className="bk-input pl-7"
                    placeholder="0"
                    min={1}
                    required
                    data-testid="quick-principal-input"
                  />
                </div>
              </div>
              <div>
                <label className="bk-label">Loan Month *</label>
                <input
                  type="month"
                  value={loanMonth}
                  onChange={e => setLoanMonth(e.target.value)}
                  className="bk-input"
                  required
                  data-testid="quick-loan-month-input"
                />
              </div>
            </div>

            {/* Live EMI preview */}
            {emi > 0 && (
              <div className="bg-primary/5 border border-primary/20 rounded-xl p-4 grid grid-cols-3 gap-2 text-center">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">EMI / किस्त</p>
                  <p className="font-bold text-primary text-lg">{fmt(emi)}</p>
                  <p className="text-xs text-muted-foreground">× 12 months</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Interest / ब्याज</p>
                  <p className="font-semibold text-orange-600 text-base">{fmt(interest)}</p>
                  <p className="text-xs text-muted-foreground">@ 17% flat</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Total Repayable</p>
                  <p className="font-semibold text-foreground text-base">{fmt(total)}</p>
                  <p className="text-xs text-muted-foreground">P + I</p>
                </div>
              </div>
            )}

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 rounded-lg px-3 py-2.5" data-testid="quick-add-error">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary/90 active:scale-[0.99] transition-all disabled:opacity-50 flex items-center justify-center gap-2 text-sm"
              data-testid="quick-add-submit-btn"
            >
              {submitting
                ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                : <Zap size={15} />}
              {submitting ? "Creating Loan..." : "Create Loan / कर्ज बनाएं"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
