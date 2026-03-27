import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Search } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LoanForm() {
  const navigate = useNavigate();
  const { id } = useParams();
  const isEdit = !!id;

  const [submitting, setSubmitting] = useState(false);
  const [clientSearch, setClientSearch] = useState("");
  const [clients, setClients] = useState([]);
  const [selectedClient, setSelectedClient] = useState(null);
  const [searchLoading, setSearchLoading] = useState(false);

  const [form, setForm] = useState({
    kyc_id: "",
    client_name: "",
    client_phone: "",
    illaka_id: "",
    illaka_name: "",
    misal_id: "",
    misal_name: "",
    principal_amount: "",
    interest_rate: "",
    loan_date: new Date().toISOString().split("T")[0],
    due_date: "",
    notes: "",
  });

  // Load existing loan for edit
  useEffect(() => {
    if (!isEdit) return;
    axios.get(`${API}/loans/${id}`, { withCredentials: true }).then(r => {
      const l = r.data;
      setForm({
        kyc_id: l.kyc_id,
        client_name: l.client_name,
        client_phone: l.client_phone || "",
        illaka_id: l.illaka_id,
        illaka_name: l.illaka_name,
        misal_id: l.misal_id,
        misal_name: l.misal_name,
        principal_amount: l.principal_amount,
        interest_rate: l.interest_rate,
        loan_date: l.loan_date,
        due_date: l.due_date || "",
        notes: l.notes || "",
      });
      setSelectedClient({ id: l.kyc_id, name: l.client_name });
    }).catch(() => toast.error("Failed to load loan"));
  }, [id, isEdit]);

  // Search clients (KYCs)
  useEffect(() => {
    if (!clientSearch || clientSearch.length < 2) { setClients([]); return; }
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await axios.get(`${API}/kycs?search=${clientSearch}&limit=10`, { withCredentials: true });
        setClients(res.data.kycs || []);
      } catch { setClients([]); }
      finally { setSearchLoading(false); }
    }, 400);
    return () => clearTimeout(t);
  }, [clientSearch]);

  const selectClient = (kyc) => {
    setSelectedClient(kyc);
    setClientSearch("");
    setClients([]);
    setForm(f => ({
      ...f,
      kyc_id: kyc.id,
      client_name: kyc.primary_borrower?.name || "",
      client_phone: kyc.primary_borrower?.phone || "",
      illaka_id: kyc.illaka_id || "",
      illaka_name: kyc.illaka_name || "",
      misal_id: kyc.misal_id || "",
      misal_name: kyc.misal_name || "",
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.kyc_id) { toast.error("Please select a client / ग्राहक चुनें"); return; }
    if (!form.principal_amount || isNaN(form.principal_amount) || Number(form.principal_amount) <= 0) {
      toast.error("Enter a valid principal amount"); return;
    }
    if (!form.interest_rate || isNaN(form.interest_rate)) {
      toast.error("Enter a valid interest rate"); return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...form,
        principal_amount: Number(form.principal_amount),
        interest_rate: Number(form.interest_rate),
      };
      if (isEdit) {
        await axios.put(`${API}/loans/${id}`, payload, { withCredentials: true });
        toast.success("Loan updated");
        navigate(`/loans/${id}`);
      } else {
        const res = await axios.post(`${API}/loans`, payload, { withCredentials: true });
        toast.success("Loan created! / कर्ज दर्ज किया गया");
        navigate(`/loans/${res.data.id}`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to save loan");
    } finally {
      setSubmitting(false);
    }
  };

  const f = (field, val) => setForm(p => ({ ...p, [field]: val }));

  return (
    <div className="p-4 sm:p-6 max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold font-['Outfit']">{isEdit ? "Edit Loan" : "New Loan / नया कर्ज"}</h1>
        <p className="text-muted-foreground text-sm mt-1">
          {isEdit ? "Update loan details" : "Record a new loan for a KYC-verified client"}
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Client Selection */}
        <div className="bk-card space-y-4">
          <h3 className="font-semibold text-foreground border-b border-border pb-2">Client / ग्राहक</h3>

          {selectedClient ? (
            <div className="flex items-center justify-between p-3 bg-primary/5 border border-primary/20 rounded-lg">
              <div>
                <p className="font-semibold text-foreground text-sm">{form.client_name}</p>
                <p className="text-xs text-muted-foreground">{form.client_phone} · {form.illaka_name} / {form.misal_name}</p>
              </div>
              {!isEdit && (
                <button type="button" onClick={() => { setSelectedClient(null); setForm(p => ({ ...p, kyc_id: "", client_name: "", client_phone: "", illaka_id: "", illaka_name: "", misal_id: "", misal_name: "" })); }} className="text-xs text-destructive hover:underline">Change</button>
              )}
            </div>
          ) : (
            <div className="relative">
              <label className="bk-label"><span className="bk-label-en">Search Client *</span><span className="bk-label-hi">ग्राहक खोजें (KYC नाम / फ़ोन)</span></label>
              <div className="relative">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  value={clientSearch}
                  onChange={e => setClientSearch(e.target.value)}
                  className="bk-input pl-9"
                  placeholder="Type name or phone to search KYC..."
                  data-testid="client-search-input"
                />
                {searchLoading && <Loader2 size={15} className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-primary" />}
              </div>
              {clients.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-card border border-border rounded-lg shadow-lg max-h-48 overflow-y-auto" data-testid="client-dropdown">
                  {clients.map(kyc => (
                    <button
                      key={kyc.id}
                      type="button"
                      onClick={() => selectClient(kyc)}
                      className="w-full flex items-start gap-3 px-4 py-3 hover:bg-muted/50 text-left"
                      data-testid={`client-option-${kyc.id}`}
                    >
                      <div>
                        <p className="text-sm font-semibold">{kyc.primary_borrower?.name || "—"}</p>
                        <p className="text-xs text-muted-foreground">{kyc.primary_borrower?.phone} · {kyc.illaka_name} / {kyc.misal_name}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Loan Details */}
        <div className="bk-card space-y-4">
          <h3 className="font-semibold text-foreground border-b border-border pb-2">Loan Details / कर्ज विवरण</h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="bk-label"><span className="bk-label-en">Principal Amount (₹) *</span><span className="bk-label-hi">मूलधन राशि</span></label>
              <input
                type="number"
                value={form.principal_amount}
                onChange={e => f("principal_amount", e.target.value)}
                className="bk-input"
                placeholder="e.g. 50000"
                min="1"
                required
                data-testid="principal-input"
              />
            </div>
            <div>
              <label className="bk-label"><span className="bk-label-en">Interest Rate (% / month) *</span><span className="bk-label-hi">मासिक ब्याज दर</span></label>
              <input
                type="number"
                value={form.interest_rate}
                onChange={e => f("interest_rate", e.target.value)}
                className="bk-input"
                placeholder="e.g. 2.5"
                step="0.01"
                min="0"
                required
                data-testid="interest-rate-input"
              />
            </div>
            <div>
              <label className="bk-label"><span className="bk-label-en">Loan Date *</span><span className="bk-label-hi">कर्ज तारीख</span></label>
              <input
                type="date"
                value={form.loan_date}
                onChange={e => f("loan_date", e.target.value)}
                className="bk-input"
                required
                data-testid="loan-date-input"
              />
            </div>
            <div>
              <label className="bk-label"><span className="bk-label-en">Due Date</span><span className="bk-label-hi">देय तारीख (वैकल्पिक)</span></label>
              <input
                type="date"
                value={form.due_date}
                onChange={e => f("due_date", e.target.value)}
                className="bk-input"
                data-testid="due-date-input"
              />
            </div>
          </div>

          <div>
            <label className="bk-label"><span className="bk-label-en">Notes (Optional)</span><span className="bk-label-hi">टिप्पणियाँ</span></label>
            <textarea
              value={form.notes}
              onChange={e => f("notes", e.target.value)}
              className="bk-input h-auto py-3 resize-none"
              rows={2}
              data-testid="loan-notes-input"
            />
          </div>
        </div>

        <div className="flex gap-3">
          <button type="button" onClick={() => navigate(-1)} className="bk-btn-secondary flex-1">Cancel</button>
          <button type="submit" disabled={submitting} className="bk-btn-primary flex-1 flex items-center justify-center gap-2" data-testid="submit-loan-btn">
            {submitting ? <><Loader2 size={18} className="animate-spin" />Saving...</> : isEdit ? "Update Loan" : "Create Loan / कर्ज दर्ज करें"}
          </button>
        </div>
      </form>
    </div>
  );
}
