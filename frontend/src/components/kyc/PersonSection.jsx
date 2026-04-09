import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { Loader2, Sparkles, Lock, LockOpen } from "lucide-react";
import { API } from "./utils";
import { DocUpload } from "./DocUpload";

export function PersonSection({ title, titleHi, data, onChange, onBatchChange, isMandatory, userRole, selectedIllakaId }) {
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrDone, setOcrDone] = useState(false);
  const [backOcrLoading, setBackOcrLoading] = useState(false);
  const [backOcrDone, setBackOcrDone] = useState(false);
  const [frontAadhaarNum, setFrontAadhaarNum] = useState("");
  const [wrongSideWarning, setWrongSideWarning] = useState(false);
  const [aadhaarMismatch, setAadhaarMismatch] = useState(false);
  const [transField, setTransField] = useState("");
  const [frontOcrFailed, setFrontOcrFailed] = useState(false);
  const [backOcrFailed, setBackOcrFailed] = useState(false);
  const [frontOverride, setFrontOverride] = useState(false);
  const [backOverride, setBackOverride] = useState(false);
  const [duplicateError, setDuplicateError] = useState(null); // { illaka_name, kyc_id, client_name }

  const navigate = useNavigate();

  // Muneem & Sipahi: OCR-filled fields are locked until override
  const isRestricted = userRole === "muneem" || userRole === "sipahi";
  const frontLocked = isRestricted && ocrDone && !frontOcrFailed && !frontOverride;
  const backLocked = isRestricted && backOcrDone && !backOcrFailed && !backOverride;

  // Sequential reveal flags
  const showFrontFields = !!data.aadhaar_front_path || frontOcrFailed;
  const showBackSection = !!data.aadhaar_front_path;
  const showBackFields = !!data.aadhaar_back_path || backOcrFailed;

  const normalizeAadhaar = (s) => (s ? s.replace(/\D/g, "") : "");

  const autoTransliterate = async (text, hindiField) => {
    if (!text || !text.trim()) return;
    setTransField(hindiField);
    try {
      const res = await axios.post(`${API}/transliterate`, { text: text.trim() }, { withCredentials: true });
      if (res.data.hindi) onChange(hindiField, res.data.hindi);
    } catch {}
    finally { setTransField(""); }
  };

  const handleAadhaarFront = async (path) => {
    onChange("aadhaar_front_path", path);
    setOcrDone(false);
    setFrontOcrFailed(false);
    setFrontOverride(false);
    setWrongSideWarning(false);
    setDuplicateError(null);
    if (!path) return;
    setOcrLoading(true);
    try {
      const res = await axios.post(`${API}/ocr/aadhaar`, { path }, { withCredentials: true });
      const d = res.data;
      if (!d.name && d.address) {
        setWrongSideWarning(true);
        onChange("aadhaar_front_path", null);
        toast.error("This appears to be the BACK of the Aadhaar card. Please upload the FRONT side. / यह आधार का पिछला भाग है।");
        setOcrLoading(false);
        return;
      }
      const updates = {};
      if (d.name) updates.name = d.name;
      if (d.dob) updates.dob = d.dob;
      if (d.aadhaar_number) {
        updates.aadhaar_number = d.aadhaar_number;
        setFrontAadhaarNum(normalizeAadhaar(d.aadhaar_number));

        // ── Duplicate check ──
        try {
          const chk = await axios.get(
            `${API}/kycs/check-aadhaar?aadhaar_number=${encodeURIComponent(d.aadhaar_number)}`,
            { withCredentials: true }
          );
          if (chk.data.exists) {
            if (chk.data.illaka_id === selectedIllakaId) {
              // Same illaka → redirect to client page
              toast.info(`Client already registered as ${chk.data.customer_id} — redirecting...`);
              navigate(`/clients/${chk.data.kyc_id}`);
              return;
            } else {
              // Different illaka → show error, block form
              onChange("aadhaar_front_path", null);
              setDuplicateError(chk.data);
              setOcrLoading(false);
              return;
            }
          }
        } catch {}
      }
      if (d.gender) updates.gender = d.gender;
      if (Object.keys(updates).length > 0) {
        onBatchChange(updates);
        setOcrDone(true);
        toast.success("Aadhaar front details auto-filled! / आधार (सामने) भरा गया");
        if (updates.name) autoTransliterate(updates.name, "name_hindi");
      } else {
        setFrontOcrFailed(true);
        toast.info("OCR could not read fields — please enter manually / OCR नाकाम — खुद भरें");
      }
    } catch {
      setFrontOcrFailed(true);
      toast.info("OCR failed — fill details manually / OCR नाकाम — खुद भरें");
    } finally {
      setOcrLoading(false);
    }
  };

  const handleAadhaarBack = async (path) => {
    onChange("aadhaar_back_path", path);
    setBackOcrDone(false);
    setBackOcrFailed(false);
    setBackOverride(false);
    setAadhaarMismatch(false);
    if (!path) return;
    setBackOcrLoading(true);
    try {
      const res = await axios.post(`${API}/ocr/aadhaar-back`, { path }, { withCredentials: true });
      const d = res.data;
      const updates = {};
      if (d.address) updates.address = d.address;
      if (d.relative_name) updates.relative_name = d.relative_name;
      if (d.aadhaar_number && frontAadhaarNum) {
        const backNum = normalizeAadhaar(d.aadhaar_number);
        if (backNum && backNum !== frontAadhaarNum) {
          setAadhaarMismatch(true);
          toast.error("Aadhaar numbers don't match on front & back! / आधार नंबर मेल नहीं खाते।");
        }
      }
      if (Object.keys(updates).length > 0) {
        onBatchChange(updates);
        setBackOcrDone(true);
        toast.success("Address & Guardian name auto-filled! / पता और अभिभावक का नाम भरा गया");
        if (updates.relative_name) autoTransliterate(updates.relative_name, "relative_name_hindi");
      } else {
        setBackOcrFailed(true);
        toast.info("Back OCR failed — fill address manually / पीछे से OCR नाकाम — पता खुद भरें");
      }
    } catch {
      setBackOcrFailed(true);
      toast.info("Back OCR failed — fill address manually");
    } finally {
      setBackOcrLoading(false);
    }
  };

  const slug = title.toLowerCase().replace(/\s+/g, "-");

  // Suffix field state (dropdown + optional urf text)
  const [suffixSelect, setSuffixSelect] = useState(() => {
    if (!data.suffix) return "";
    if (data.suffix.startsWith("Urf ")) return "urf";
    return data.suffix;
  });
  const [urfText, setUrfText] = useState(() => {
    if (data.suffix?.startsWith("Urf ")) return data.suffix.substring(4);
    return "";
  });

  const handleSuffixSelect = (val) => {
    setSuffixSelect(val);
    if (val === "urf") {
      onChange("suffix", urfText ? `Urf ${urfText}` : "");
    } else {
      onChange("suffix", val);
    }
  };

  const handleUrfText = (text) => {
    setUrfText(text);
    onChange("suffix", text ? `Urf ${text}` : "");
  };

  // Reusable locked input wrapper
  const lockedCls = "bg-green-50/80 border-green-300 cursor-not-allowed pr-8";
  const lockedBackCls = "bg-blue-50/60 border-blue-300 cursor-not-allowed pr-8";

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">{title}</h3>
        <span className="text-sm text-muted-foreground">{titleHi}</span>
        {(ocrLoading || backOcrLoading) && (
          <span className="flex items-center gap-1 text-primary text-xs ml-2 animate-pulse">
            <Loader2 size={12} className="animate-spin" />
            {backOcrLoading ? "Reading back..." : "Reading Aadhaar..."}
          </span>
        )}
      </div>

      {/* ── STEP 1: Phone + Suffix ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Phone Number <span className="text-destructive">*</span></span>
            <span className="bk-label-hi">फ़ोन नंबर</span>
          </label>
          <input
            type="tel" value={data.phone}
            onChange={e => onChange("phone", e.target.value)}
            className="bk-input" placeholder="9876543210" maxLength={10}
            data-testid={`phone-${slug}`}
          />
        </div>

        {/* Suffix / उपनाम — caste, occupation, or urf */}
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Suffix — Caste / Occ. / Urf <span className="font-normal text-muted-foreground">(optional)</span></span>
            <span className="bk-label-hi">उपनाम — जाति / पेशा / उर्फ़</span>
          </label>
          <div className="flex gap-2">
            <select
              value={suffixSelect}
              onChange={e => handleSuffixSelect(e.target.value)}
              className="bk-input flex-1"
              data-testid={`suffix-select-${slug}`}
            >
              <option value="">None / कोई नहीं</option>
              <optgroup label="— Occupation / पेशा —">
                <option value="Dhobi">Dhobi / धोबी</option>
                <option value="Darji">Darji / दर्जी</option>
                <option value="Kumhar">Kumhar / कुम्हार</option>
                <option value="Lohar">Lohar / लोहार</option>
                <option value="Teli">Teli / तेली</option>
                <option value="Nai">Nai / नाई</option>
                <option value="Kori">Kori / कोरी</option>
                <option value="Mallah">Mallah / मल्लाह</option>
                <option value="Kewat">Kewat / केवट</option>
                <option value="Kahar">Kahar / कहार</option>
              </optgroup>
              <optgroup label="— Caste / जाति —">
                <option value="Yadav">Yadav / यादव</option>
                <option value="Maurya">Maurya / मौर्य</option>
                <option value="Prajapati">Prajapati / प्रजापति</option>
                <option value="Kushwaha">Kushwaha / कुशवाहा</option>
                <option value="Pasi">Pasi / पासी</option>
                <option value="Bind">Bind / बिंद</option>
                <option value="Rajput">Rajput / राजपूत</option>
                <option value="Thakur">Thakur / ठाकुर</option>
                <option value="Sharma">Sharma / शर्मा</option>
                <option value="Gupta">Gupta / गुप्त</option>
                <option value="Dubey">Dubey / दुबे</option>
                <option value="Mishra">Mishra / मिश्रा</option>
                <option value="Chamar">Chamar / चमार</option>
              </optgroup>
              <optgroup label="— Nickname / उर्फ़ —">
                <option value="urf">Urf... / उर्फ़... (Custom)</option>
              </optgroup>
            </select>
            {suffixSelect === "urf" && (
              <input
                type="text"
                value={urfText}
                onChange={e => handleUrfText(e.target.value)}
                className="bk-input flex-1"
                placeholder="Nickname / उपनाम"
                data-testid={`suffix-urf-input-${slug}`}
              />
            )}
          </div>
          {data.suffix && (
            <p className="text-xs text-muted-foreground mt-1">
              Preview: <span className="font-semibold text-foreground">{data.name || "…"} {data.suffix}</span>
            </p>
          )}
        </div>
      </div>

      {/* ── STEP 2: Aadhaar Front ── */}
      <div className="pt-1 border-t border-dashed border-border/60">
        <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">
          Step 2 · Aadhaar Front / आधार — सामने वाला भाग
        </p>
        <DocUpload
          label="Aadhaar Card (Front)" labelHi="आधार कार्ड (सामने) — OCR: Name, DOB, Gender"
          value={data.aadhaar_front_path} onChange={handleAadhaarFront}
          required={isMandatory} testId={`aadhaar-front-${slug}`}
        />

        {wrongSideWarning && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2 mt-2" data-testid="wrong-side-warning">
            <span className="font-bold shrink-0">!</span>
            <div>
              <p className="font-semibold">Wrong side uploaded / गलत तरफ अपलोड की</p>
              <p className="text-xs mt-0.5">Please upload the FRONT side (with photo, name & date of birth).</p>
              <button type="button" onClick={() => setWrongSideWarning(false)} className="mt-1 text-xs underline">Try again / फिर से</button>
            </div>
          </div>
        )}

        {/* Duplicate Aadhaar — different illaka */}
        {duplicateError && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-800 text-sm flex items-start gap-2 mt-2" data-testid="duplicate-aadhaar-error">
            <span className="font-bold shrink-0 text-red-600">!</span>
            <div>
              <p className="font-semibold">Client already exists in another Illaka</p>
              <p className="text-xs mt-0.5">
                <span className="font-semibold">{duplicateError.client_name}</span> ({duplicateError.customer_id}) is registered under{" "}
                <span className="font-semibold text-red-700">Illaka: {duplicateError.illaka_name}</span>.
                Contact your Admin / Maalik to transfer or view this client.
              </p>
              <p className="text-xs mt-1 text-red-600">यह ग्राहक दूसरे इलाके में पहले से दर्ज है — {duplicateError.illaka_name}</p>
              <button
                type="button"
                onClick={() => { setDuplicateError(null); setWrongSideWarning(false); }}
                className="mt-1.5 text-xs underline text-red-700"
              >
                Upload a different Aadhaar / दूसरा आधार अपलोड करें
              </button>
            </div>
          </div>
        )}
        {ocrLoading && (
          <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20 text-primary text-sm animate-pulse mt-2">
            <Loader2 size={16} className="animate-spin flex-shrink-0" />
            Extracting details from Aadhaar front... / आधार से विवरण निकाला जा रहा है...
          </div>
        )}
        {ocrDone && !ocrLoading && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 border border-green-200 text-green-700 text-sm mt-2">
            <Sparkles size={15} className="flex-shrink-0" />
            <span>Name, DOB &amp; Gender auto-filled</span>
            {frontLocked && <span className="ml-auto flex items-center gap-1 text-xs font-semibold"><Lock size={11} /> Verified</span>}
          </div>
        )}
        {frontOcrFailed && !ocrLoading && (
          <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-sm mt-2">
            <span className="font-bold">!</span> OCR could not read — please fill fields manually below
          </div>
        )}
      </div>

      {/* Front OCR fields — revealed after front upload */}
      {showFrontFields && (
        <div className={`space-y-4 transition-opacity duration-200 ${ocrLoading ? "opacity-40 pointer-events-none" : ""}`}>
          {/* Lock notice + override for restricted roles */}
          {frontLocked && (
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-green-50 border border-green-200 text-xs" data-testid={`front-locked-notice-${slug}`}>
              <span className="flex items-center gap-1.5 text-green-700 font-semibold">
                <Lock size={12} /> Fields locked from Aadhaar scan — verified
              </span>
              <button
                type="button"
                onClick={() => setFrontOverride(true)}
                className="flex items-center gap-1 text-amber-700 underline hover:text-amber-900 ml-2"
                data-testid={`front-override-btn-${slug}`}
              >
                <LockOpen size={11} /> OCR issue? Override
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Name */}
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Full Name <span className="text-destructive">*</span></span>
                <span className="bk-label-hi">पूरा नाम</span>
              </label>
              <div className="relative">
                <input
                  type="text" value={data.name}
                  onChange={frontLocked ? undefined : e => onChange("name", e.target.value)}
                  onBlur={frontLocked ? undefined : e => { if (e.target.value && !data.name_hindi) autoTransliterate(e.target.value, "name_hindi"); }}
                  readOnly={frontLocked}
                  className={`bk-input ${frontLocked ? lockedCls : ocrDone && data.name ? "border-green-400 bg-green-50/60" : ""}`}
                  placeholder="Auto-filled from Aadhaar"
                  data-testid={`name-${slug}`}
                />
                {frontLocked && <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-green-600" />}
              </div>
            </div>

            {/* Name Hindi — locked with front fields for restricted roles */}
            <div>
              <label className="bk-label">
                <span className="bk-label-en">
                  Name in Hindi{" "}
                  {transField === "name_hindi" && <span className="text-xs text-primary animate-pulse ml-1">(transliterating...)</span>}
                </span>
                <span className="bk-label-hi">हिंदी नाम</span>
              </label>
              <div className="relative">
                <input
                  type="text" value={data.name_hindi || ""}
                  onChange={frontLocked ? undefined : e => onChange("name_hindi", e.target.value)}
                  readOnly={frontLocked}
                  className={`bk-input ${frontLocked ? lockedCls : "border-amber-300 bg-amber-50/40 focus:border-amber-500"}`}
                  placeholder="Auto-filled · हिंदी में नाम"
                  data-testid={`name-hindi-${slug}`}
                />
                {frontLocked && <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-green-600" />}
              </div>
            </div>

            {/* DOB */}
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Date of Birth <span className="text-destructive">*</span></span>
                <span className="bk-label-hi">जन्म तिथि</span>
              </label>
              <div className="relative">
                <input
                  type="text" value={data.dob}
                  onChange={frontLocked ? undefined : e => onChange("dob", e.target.value)}
                  readOnly={frontLocked}
                  className={`bk-input ${frontLocked ? lockedCls : ocrDone && data.dob ? "border-green-400 bg-green-50/60" : ""}`}
                  placeholder="DD/MM/YYYY"
                  data-testid={`dob-${slug}`}
                />
                {frontLocked && <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-green-600" />}
              </div>
            </div>

            {/* Aadhaar Number */}
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Aadhaar Number <span className="text-destructive">*</span></span>
                <span className="bk-label-hi">आधार संख्या</span>
              </label>
              <div className="relative">
                <input
                  type="text" value={data.aadhaar_number}
                  onChange={frontLocked ? undefined : e => onChange("aadhaar_number", e.target.value)}
                  readOnly={frontLocked}
                  className={`bk-input ${frontLocked ? lockedCls : ocrDone && data.aadhaar_number ? "border-green-400 bg-green-50/60" : ""}`}
                  placeholder="XXXX XXXX XXXX"
                  data-testid={`aadhaar-num-${slug}`}
                />
                {frontLocked && <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-green-600" />}
              </div>
            </div>

            {/* Gender */}
            <div>
              <label className="bk-label">
                <span className="bk-label-en">Gender <span className="text-destructive">*</span></span>
                <span className="bk-label-hi">लिंग</span>
              </label>
              <div className="relative">
                {frontLocked ? (
                  <>
                    <input
                      type="text" value={data.gender}
                      readOnly
                      className={`bk-input ${lockedCls}`}
                      data-testid={`gender-${slug}`}
                    />
                    <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-green-600" />
                  </>
                ) : (
                  <select
                    value={data.gender}
                    onChange={e => onChange("gender", e.target.value)}
                    className={`bk-input ${ocrDone && data.gender ? "border-green-400 bg-green-50/60" : ""}`}
                    data-testid={`gender-${slug}`}
                  >
                    <option value="">Select / चुनें</option>
                    <option value="Male">Male / पुरुष</option>
                    <option value="Female">Female / महिला</option>
                    <option value="Other">Other / अन्य</option>
                  </select>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── STEP 3: Aadhaar Back — revealed after front is uploaded ── */}
      {showBackSection && (
        <div className="pt-1 border-t border-dashed border-border/60">
          <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mb-3">
            Step 3 · Aadhaar Back / आधार — पीछे वाला भाग
          </p>
          <DocUpload
            label="Aadhaar Card (Back)" labelHi="आधार कार्ड (पीछे) — OCR: पता और अभिभावक नाम"
            value={data.aadhaar_back_path} onChange={handleAadhaarBack}
            required={isMandatory} testId={`aadhaar-back-${slug}`}
          />

          {aadhaarMismatch && (
            <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2 mt-2" data-testid="aadhaar-mismatch-warning">
              <span className="font-bold shrink-0">!</span>
              <div>
                <p className="font-semibold">Aadhaar number mismatch / आधार नंबर मेल नहीं खाते</p>
                <p className="text-xs mt-0.5">The Aadhaar numbers on front & back don't match. Please verify both cards belong to the same person.</p>
                <button type="button" onClick={() => { onChange("aadhaar_back_path", null); setAadhaarMismatch(false); }} className="mt-1 text-xs underline">Retake back photo</button>
              </div>
            </div>
          )}
          {backOcrLoading && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm animate-pulse mt-2">
              <Loader2 size={16} className="animate-spin flex-shrink-0" />
              Reading address &amp; guardian name from Aadhaar back...
            </div>
          )}
          {backOcrDone && !backOcrLoading && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm mt-2">
              <Sparkles size={15} className="flex-shrink-0" />
              <span>Address &amp; Guardian name auto-filled — please verify below</span>
              {backLocked && <span className="ml-auto flex items-center gap-1 text-xs font-semibold"><Lock size={11} /> Locked</span>}
            </div>
          )}
          {backOcrFailed && !backOcrLoading && (
            <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-700 text-sm mt-2">
              <span className="font-bold">!</span> Back OCR failed — please fill address and guardian name below
            </div>
          )}
        </div>
      )}

      {/* Back OCR fields — revealed after back upload */}
      {showBackSection && showBackFields && (
        <div className={`space-y-4 transition-opacity duration-200 ${backOcrLoading ? "opacity-40 pointer-events-none" : ""}`}>
          {/* Lock notice + override for restricted roles */}
          {backLocked && (
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-blue-50 border border-blue-200 text-xs" data-testid={`back-locked-notice-${slug}`}>
              <span className="flex items-center gap-1.5 text-blue-700 font-semibold">
                <Lock size={12} /> Fields locked from Aadhaar back scan
              </span>
              <button
                type="button"
                onClick={() => setBackOverride(true)}
                className="flex items-center gap-1 text-amber-700 underline hover:text-amber-900 ml-2"
                data-testid={`back-override-btn-${slug}`}
              >
                <LockOpen size={11} /> OCR issue? Override
              </button>
            </div>
          )}

          {/* Address */}
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Address <span className="text-destructive">*</span></span>
              <span className="bk-label-hi">पता</span>
            </label>
            <div className="relative">
              <textarea
                value={data.address}
                onChange={backLocked ? undefined : e => onChange("address", e.target.value)}
                readOnly={backLocked}
                className={`bk-input h-auto py-3 resize-none ${backLocked ? "bg-blue-50/60 border-blue-300 cursor-not-allowed" : backOcrDone && data.address ? "border-blue-400 bg-blue-50/60" : ""}`}
                rows={3}
                placeholder="Auto-filled from Aadhaar back"
                data-testid={`address-${slug}`}
              />
              {backLocked && <Lock size={13} className="absolute right-2.5 top-3 text-blue-600" />}
            </div>
          </div>

          {/* Relative Name */}
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Husband's / Father's Name <span className="text-destructive">*</span></span>
              <span className="bk-label-hi">पति / पिता का नाम</span>
            </label>
            <div className="relative">
              <input
                type="text" value={data.relative_name}
                onChange={backLocked ? undefined : e => onChange("relative_name", e.target.value)}
                onBlur={backLocked ? undefined : e => { if (e.target.value && !data.relative_name_hindi) autoTransliterate(e.target.value, "relative_name_hindi"); }}
                readOnly={backLocked}
                className={`bk-input ${backLocked ? lockedBackCls : backOcrDone && data.relative_name ? "border-blue-400 bg-blue-50/60" : ""}`}
                placeholder="Auto-filled from Aadhaar back"
                data-testid={`relative-name-${slug}`}
              />
              {backLocked && <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-blue-600" />}
            </div>
          </div>

          {/* Relative Name Hindi — locked with back fields for restricted roles */}
          <div>
            <label className="bk-label">
              <span className="bk-label-en">
                Husband's / Father's Name in Hindi{" "}
                {transField === "relative_name_hindi" && <span className="text-xs text-primary animate-pulse ml-1">(transliterating...)</span>}
              </span>
              <span className="bk-label-hi">पति / पिता का हिंदी नाम</span>
            </label>
            <div className="relative">
              <input
                type="text" value={data.relative_name_hindi || ""}
                onChange={backLocked ? undefined : e => onChange("relative_name_hindi", e.target.value)}
                readOnly={backLocked}
                className={`bk-input ${backLocked ? lockedBackCls : "border-amber-300 bg-amber-50/40 focus:border-amber-500"}`}
                placeholder="Auto-filled · हिंदी में पति/पिता का नाम"
                data-testid={`relative-name-hindi-${slug}`}
              />
              {backLocked && <Lock size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-blue-600" />}
            </div>
          </div>
        </div>
      )}

      {/* Additional Doc — shown after back section is revealed */}
      {showBackSection && (
        <div className="pt-3 border-t border-dashed border-border">
          <p className="text-sm font-semibold text-muted-foreground mb-3">
            Additional Document <span className="font-normal">(Optional / वैकल्पिक)</span>
          </p>
          <div>
            <label className="bk-label">
              <span className="bk-label-en">Document Type</span>
              <span className="bk-label-hi">दस्तावेज़ प्रकार</span>
            </label>
            <select
              value={data.document_type}
              onChange={e => { onChange("document_type", e.target.value); onChange("document_back_path", null); }}
              className="bk-input"
              data-testid={`doc-type-${slug}`}
            >
              <option value="voter_id">Voter ID / मतदाता पहचान पत्र</option>
              <option value="pan">PAN Card / पैन कार्ड</option>
              <option value="ration_card">Ration Card / राशन कार्ड</option>
            </select>
          </div>
          <div className="mt-3">
            <DocUpload
              label={`${data.document_type === "pan" ? "PAN" : data.document_type === "ration_card" ? "Ration Card" : "Voter ID"} (Front)`}
              labelHi="सामने की तस्वीर"
              value={data.document_front_path} onChange={v => onChange("document_front_path", v)}
              testId={`doc-front-${slug}`}
            />
          </div>
          {data.document_type !== "pan" && (
            <div className="mt-3">
              <DocUpload
                label={`${data.document_type === "ration_card" ? "Ration Card" : "Voter ID"} (Back)`}
                labelHi="पीछे की तस्वीर"
                value={data.document_back_path} onChange={v => onChange("document_back_path", v)}
                testId={`doc-back-${slug}`}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
