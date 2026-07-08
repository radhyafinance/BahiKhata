import { useState, useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, CheckCircle, ChevronRight, ChevronLeft,
  MapPin, User, Users, Shield, Camera,
  ToggleLeft, ToggleRight, Lock
} from "lucide-react";
import { API, STEPS, emptyPerson } from "./kyc/utils";
import { PersonSection } from "./kyc/PersonSection";
import { LivePhotoGPS } from "./kyc/LivePhotoGPS";
import { ReviewSection } from "./kyc/ReviewSection";
import { useIllaka } from "./IllakaContext";
import { useAuth } from "./AuthContext";

const STEP_ICONS = [MapPin, User, Users, Shield, Camera, CheckCircle];

export default function KYCForm() {
  const navigate = useNavigate();
  const { id } = useParams();
  const { user } = useAuth();
  const { selectedIllaka: contextIllaka } = useIllaka();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [successData, setSuccessData] = useState(null); // { customerId, loanId, clientName, kycId }
  const [illakas, setIllakas] = useState([]);
  const [misals, setMisals] = useState([]);
  const [selectedIllaka, setSelectedIllaka] = useState(null);
  const [selectedMisal, setSelectedMisal] = useState(null);
  const [includeCoBorrower, setIncludeCoBorrower] = useState(false);
  const [includeGuarantor, setIncludeGuarantor] = useState(false);
  // true only when the user explicitly changes the illaka via the dropdown
  const illakaChangedByUser = useRef(false);

  const [formData, setFormData] = useState({
    primaryBorrower: { ...emptyPerson },
    coBorrower: { ...emptyPerson },
    guarantor: { ...emptyPerson },
    livePhotoPath: null,
    gpsLocation: null,
    notes: "",
    disbursementAmount: "",
  });

  useEffect(() => {
    axios.get(`${API}/illakas`, { withCredentials: true }).then(r => {
      setIllakas(r.data);
      // Pre-populate from global context in create mode (only specific illaka, not "All")
      if (!id && contextIllaka) {
        setSelectedIllaka(contextIllaka);
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedIllaka) { setMisals([]); setSelectedMisal(null); return; }
    axios.get(`${API}/misals?illaka_id=${selectedIllaka.id}`, { withCredentials: true })
      .then(r => {
        setMisals(r.data);
        // Only reset misal when the user explicitly changed the illaka;
        // on initial edit-mode load, selectedMisal is already set directly.
        if (illakaChangedByUser.current) {
          setSelectedMisal(null);
          illakaChangedByUser.current = false;
        }
      }).catch(() => {});
  }, [selectedIllaka]);

  useEffect(() => {
    if (!id) return;
    axios.get(`${API}/kycs/${id}`, { withCredentials: true }).then(r => {
      const k = r.data;
      setFormData({
        primaryBorrower: k.primary_borrower || { ...emptyPerson },
        coBorrower: k.co_borrower || { ...emptyPerson },
        guarantor: k.guarantor || { ...emptyPerson },
        livePhotoPath: k.live_photo_path || null,
        gpsLocation: k.gps_location || null,
        notes: k.notes || "",
        disbursementAmount: "",
      });
      if (k.co_borrower) setIncludeCoBorrower(true);
      if (k.guarantor) setIncludeGuarantor(true);
      if (k.illaka_id) setSelectedIllaka({ id: k.illaka_id, name: k.illaka_name });
      if (k.misal_id) setSelectedMisal({ id: k.misal_id, name: k.misal_name });
    }).catch(() => toast.error("Failed to load KYC"));
  }, [id]);

  const updatePerson = (key) => (field, value) => setFormData(p => ({ ...p, [key]: { ...p[key], [field]: value } }));
  const updatePersonBatch = (key) => (updates) => setFormData(p => ({ ...p, [key]: { ...p[key], ...updates } }));

  const validateStep = () => {
    if (step === 1) {
      if (!selectedIllaka) { toast.error("Please select an Illaka / इलाका चुनें"); return false; }
      if (!selectedMisal) { toast.error("Please select a Misal / मिसाल चुनें"); return false; }
      return true;
    }
    if (step === 2) {
      const p = formData.primaryBorrower;
      if (!p.phone) { toast.error("Primary borrower phone required"); return false; }
      if (!p.name) { toast.error("Primary borrower name required"); return false; }
      if (!p.dob) { toast.error("Date of birth required"); return false; }
      if (!p.relative_name) { toast.error("Husband's / Father's name required / पति/पिता का नाम अनिवार्य है"); return false; }
      if (!p.address) { toast.error("Address required"); return false; }
      if (!p.aadhaar_number) { toast.error("Aadhaar number required"); return false; }
      if (!p.aadhaar_front_path) { toast.error("Aadhaar front photo required"); return false; }
      if (!p.aadhaar_back_path) { toast.error("Aadhaar back photo required"); return false; }
      return true;
    }
    // Co-borrower and guarantor phone are optional — no phone validation needed
    if (step === 5) {
      if (!formData.livePhotoPath) { toast.error("Live photo is required / लाइव फोटो अनिवार्य है"); return false; }
      return true;
    }
    if (step === 6) {
      if (!id) {
        const amt = parseFloat(formData.disbursementAmount);
        if (!formData.disbursementAmount || isNaN(amt) || amt <= 0) {
          toast.error("Enter disbursement amount / वितरण राशि दर्ज करें");
          return false;
        }
      }
      return true;
    }
    return true;
  };

  const nextStep = () => { if (!validateStep()) return; setStep(s => s + 1); };

  const handleSubmit = async () => {
    if (!validateStep()) return;
    setSubmitting(true);
    try {
      const payload = {
        illaka_id: selectedIllaka.id, illaka_name: selectedIllaka.name,
        misal_id: selectedMisal.id, misal_name: selectedMisal.name,
        primary_borrower: formData.primaryBorrower,
        co_borrower: includeCoBorrower && formData.coBorrower.name ? formData.coBorrower : null,
        guarantor: includeGuarantor && formData.guarantor.name ? formData.guarantor : null,
        live_photo_path: formData.livePhotoPath,
        gps_location: formData.gpsLocation,
        notes: formData.notes,
        disbursement_amount: id ? null : (parseFloat(formData.disbursementAmount) || null),
      };
      const res = id
        ? await axios.put(`${API}/kycs/${id}`, payload, { withCredentials: true })
        : await axios.post(`${API}/kycs`, payload, { withCredentials: true });
      if (id) {
        toast.success("KYC updated successfully!");
        navigate(`/clients/${res.data.id}`);
      } else {
        setSuccessData({
          customerId: res.data.customer_id,
          loanId: res.data.loan_id,
          clientName: formData.primaryBorrower.name,
          kycId: res.data.id,
        });
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to submit KYC");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto">

      {/* ── Success Screen ── */}
      {successData && (
        <div className="flex flex-col items-center justify-center py-16 gap-6 text-center" data-testid="kyc-success-screen">
          <div className="w-20 h-20 rounded-full bg-green-100 flex items-center justify-center">
            <CheckCircle size={44} className="text-green-600" />
          </div>
          <div>
            <h2 className="text-2xl font-bold font-['Outfit'] text-green-700">Client Saved!</h2>
            <p className="text-muted-foreground mt-1 text-sm">ग्राहक सफलतापूर्वक दर्ज हुआ</p>
          </div>
          <div className="w-full max-w-sm bk-card space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Customer ID</span>
              <span className="font-bold text-primary text-lg" data-testid="kyc-success-customer-id">{successData.customerId}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-muted-foreground">Client Name</span>
              <span className="font-semibold" data-testid="kyc-success-client-name">{successData.clientName}</span>
            </div>
            {successData.loanId ? (
              <div className="mt-3 pt-3 border-t border-border flex items-center gap-2 text-green-700 justify-center text-sm font-semibold" data-testid="kyc-success-loan-badge">
                <CheckCircle size={16} />
                Loan Disbursed / कर्ज जारी हुआ
              </div>
            ) : (
              <div className="mt-3 pt-3 border-t border-border text-muted-foreground text-sm text-center">
                No disbursement amount provided
              </div>
            )}
          </div>
          <button
            type="button"
            className="bk-btn-primary px-8 py-3 text-base"
            onClick={() => navigate(`/clients/${successData.kycId}`)}
            data-testid="kyc-success-view-client-btn"
          >
            View Client Profile
          </button>
        </div>
      )}

      {/* ── Main Form (hidden once submitted) ── */}
      {!successData && (<>
        <div className="mb-5">
          <h1 className="text-2xl font-bold font-['Outfit']">{id ? "Edit KYC" : "New KYC / नया KYC"}</h1>
          <p className="text-muted-foreground text-sm mt-1">Step {step} of {STEPS.length}</p>
        </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-1 mb-7 overflow-x-auto pb-1" data-testid="step-indicator">
        {STEPS.map((s, i) => {
          const Icon = STEP_ICONS[i];
          return (
            <div key={s.id} className="flex items-center flex-shrink-0">
              <button
                type="button"
                onClick={() => s.id < step && setStep(s.id)}
                className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-semibold transition-all ${
                  step === s.id ? "bg-primary text-white" : s.id < step ? "bg-primary/20 text-primary cursor-pointer" : "bg-muted text-muted-foreground"
                }`}
                data-testid={`step-btn-${s.id}`}
              >
                <Icon size={13} />
                <span className="hidden sm:inline">{s.title}</span>
                <span className="sm:hidden">{s.id}</span>
              </button>
              {i < STEPS.length - 1 && <ChevronRight size={13} className="text-muted-foreground mx-0.5" />}
            </div>
          );
        })}
      </div>

      <div className="bk-card mb-5">
        {/* Step 1: Illaka & Misal */}
        {step === 1 && (
          <div className="space-y-5">
            <div className="flex items-center gap-2 pb-2 border-b border-border">
              <h3 className="text-lg font-bold font-['Outfit']">Select Illaka & Misal</h3>
              <span className="text-sm text-muted-foreground">इलाका और मिसाल चुनें</span>
            </div>
            <div>
              <label className="bk-label"><span className="bk-label-en">Illaka (Area) <span className="text-destructive">*</span></span><span className="bk-label-hi">इलाका</span></label>
              {illakas.length === 0 ? (
                <div className="p-4 rounded-lg bg-yellow-50 border border-yellow-200 text-yellow-800 text-sm">
                  No Illakas assigned to you yet. Contact your Maalik or Admin.
                </div>
              ) : !id ? (
                /* Create mode — Illaka locked to the globally selected one */
                <div className="bk-input flex items-center gap-2 bg-muted/50 cursor-not-allowed select-none" data-testid="illaka-locked">
                  <Lock size={13} className="text-muted-foreground flex-shrink-0" />
                  <span className="font-medium">{selectedIllaka?.name || "—"}</span>
                </div>
              ) : (
                /* Edit mode — allow changing */
                <select value={selectedIllaka?.id || ""} onChange={e => { illakaChangedByUser.current = true; const ill = illakas.find(i => i.id === e.target.value); setSelectedIllaka(ill || null); }} className="bk-input" data-testid="illaka-select">
                  <option value="">— Select Illaka —</option>
                  {illakas.map(ill => <option key={ill.id} value={ill.id}>{ill.name}</option>)}
                </select>
              )}
            </div>
            <div>
              <label className="bk-label"><span className="bk-label-en">Misal (Village) <span className="text-destructive">*</span></span><span className="bk-label-hi">मिसाल (गांव)</span></label>
              {!selectedIllaka ? (
                <p className="text-sm text-muted-foreground italic">Select an Illaka first</p>
              ) : misals.length === 0 ? (
                <div className="p-4 rounded-lg bg-yellow-50 border border-yellow-200 text-yellow-800 text-sm">
                  No Misals in this Illaka. Ask Admin or Maalik to add Misals.
                </div>
              ) : (
                <select value={selectedMisal?.id || ""} onChange={e => { const m = misals.find(m => m.id === e.target.value); setSelectedMisal(m || null); }} className="bk-input" data-testid="misal-select">
                  <option value="">— Select Misal —</option>
                  {misals.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
              )}
            </div>
          </div>
        )}

        {/* Step 2: Primary Borrower */}
        {step === 2 && (
          <PersonSection
            title="Primary Borrower" titleHi="प्राथमिक उधारकर्ता"
            data={formData.primaryBorrower}
            onChange={updatePerson("primaryBorrower")}
            onBatchChange={updatePersonBatch("primaryBorrower")}
            isMandatory={true}
            userRole={user?.role}
            selectedIllakaId={selectedIllaka?.id}
          />
        )}

        {/* Step 3: Co-borrower (optional) */}
        {step === 3 && (
          <div className="space-y-5">
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <div>
                <h3 className="text-lg font-bold font-['Outfit']">Co-borrower</h3>
                <p className="text-xs text-muted-foreground">सह-उधारकर्ता — Optional / वैकल्पिक</p>
              </div>
              <button type="button" onClick={() => setIncludeCoBorrower(p => !p)} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${includeCoBorrower ? "bg-primary text-white" : "bg-muted text-foreground border border-border"}`} data-testid="toggle-coborrower">
                {includeCoBorrower ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                {includeCoBorrower ? "Included" : "Include?"}
              </button>
            </div>
            {includeCoBorrower ? (
              <PersonSection
                title="Co-borrower" titleHi="सह-उधारकर्ता"
                data={formData.coBorrower}
                onChange={updatePerson("coBorrower")}
                onBatchChange={updatePersonBatch("coBorrower")}
                isMandatory={false}
                userRole={user?.role}
                selectedIllakaId={selectedIllaka?.id}
              />
            ) : (
              <div className="py-8 text-center text-muted-foreground space-y-3">
                <Users size={36} className="mx-auto opacity-30" />
                <p>Co-borrower not included.</p>
                <p className="text-xs">Toggle above to add a co-borrower / ऊपर टॉगल करें</p>
              </div>
            )}
          </div>
        )}

        {/* Step 4: Guarantor (optional) */}
        {step === 4 && (
          <div className="space-y-5">
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <div>
                <h3 className="text-lg font-bold font-['Outfit']">Guarantor</h3>
                <p className="text-xs text-muted-foreground">गारंटर — Optional / वैकल्पिक</p>
              </div>
              <button type="button" onClick={() => setIncludeGuarantor(p => !p)} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all ${includeGuarantor ? "bg-primary text-white" : "bg-muted text-foreground border border-border"}`} data-testid="toggle-guarantor">
                {includeGuarantor ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                {includeGuarantor ? "Included" : "Include?"}
              </button>
            </div>
            {includeGuarantor ? (
              <PersonSection
                title="Guarantor" titleHi="गारंटर"
                data={formData.guarantor}
                onChange={updatePerson("guarantor")}
                onBatchChange={updatePersonBatch("guarantor")}
                isMandatory={false}
                userRole={user?.role}
                selectedIllakaId={selectedIllaka?.id}
              />
            ) : (
              <div className="py-8 text-center text-muted-foreground space-y-3">
                <Shield size={36} className="mx-auto opacity-30" />
                <p>Guarantor not included.</p>
                <p className="text-xs">Toggle above to add a guarantor / ऊपर टॉगल करें</p>
              </div>
            )}
          </div>
        )}

        {/* Step 5: Live Photo + GPS */}
        {step === 5 && (
          <LivePhotoGPS
            livePhotoPath={formData.livePhotoPath}
            gpsLocation={formData.gpsLocation}
            onPhotoChange={v => setFormData(p => ({ ...p, livePhotoPath: v }))}
            onGPSChange={v => setFormData(p => ({ ...p, gpsLocation: v }))}
          />
        )}

        {/* Step 6: Review */}
        {step === 6 && (
          <ReviewSection
            formData={formData}
            illaka={selectedIllaka}
            misal={selectedMisal}
            includeCoBorrower={includeCoBorrower}
            includeGuarantor={includeGuarantor}
            isEdit={!!id}
            disbursementAmount={formData.disbursementAmount}
            setDisbursementAmount={v => setFormData(p => ({ ...p, disbursementAmount: v }))}
          />
        )}
      </div>

      {/* Notes on last step */}
      {step === 6 && (
        <div className="bk-card mb-5">
          <label className="bk-label"><span className="bk-label-en">Notes (Optional)</span><span className="bk-label-hi">टिप्पणियाँ</span></label>
          <textarea value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} className="bk-input h-auto py-3 resize-none w-full" rows={2} data-testid="notes-input" />
        </div>
      )}

      {/* Nav Buttons */}
      <div className="flex gap-3">
        {step > 1 && (
          <button type="button" onClick={() => setStep(s => s - 1)} className="bk-btn-secondary flex items-center justify-center gap-2 flex-1" data-testid="prev-step-btn">
            <ChevronLeft size={18} /> Back
          </button>
        )}
        {step < STEPS.length ? (
          <button type="button" onClick={nextStep} className="bk-btn-primary flex items-center justify-center gap-2 flex-1" data-testid="next-step-btn">
            Next <ChevronRight size={18} />
          </button>
        ) : (
          <button type="button" onClick={handleSubmit} disabled={submitting} className="bk-btn-primary flex items-center justify-center gap-2 flex-1" data-testid="submit-kyc-btn">
            {submitting ? <><Loader2 size={18} className="animate-spin" />Submitting...</> : <><CheckCircle size={18} />Submit KYC / जमा करें</>}
          </button>
        )}
      </div>
    </>)}
    </div>
  );
}
