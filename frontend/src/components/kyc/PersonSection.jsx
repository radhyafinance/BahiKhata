import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Sparkles } from "lucide-react";
import { API } from "./utils";
import { DocUpload } from "./DocUpload";

export function PersonSection({ title, titleHi, data, onChange, onBatchChange, isMandatory }) {
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrDone, setOcrDone] = useState(false);
  const [backOcrLoading, setBackOcrLoading] = useState(false);
  const [backOcrDone, setBackOcrDone] = useState(false);
  const [frontAadhaarNum, setFrontAadhaarNum] = useState("");
  const [wrongSideWarning, setWrongSideWarning] = useState(false);
  const [aadhaarMismatch, setAadhaarMismatch] = useState(false);
  const [transField, setTransField] = useState("");

  const normalizeAadhaar = (s) => s ? s.replace(/\D/g, "") : "";

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
    setOcrDone(false); setWrongSideWarning(false);
    if (!path) return;
    setOcrLoading(true);
    try {
      const res = await axios.post(`${API}/ocr/aadhaar`, { path }, { withCredentials: true });
      const d = res.data;
      if (!d.name && d.address) {
        setWrongSideWarning(true);
        onChange("aadhaar_front_path", null);
        toast.error("This appears to be the BACK of the Aadhaar card. Please upload the FRONT side. / यह आधार का पिछला भाग है, कृपया सामने का भाग अपलोड करें।");
        setOcrLoading(false);
        return;
      }
      const updates = {};
      if (d.name) updates.name = d.name;
      if (d.dob) updates.dob = d.dob;
      if (d.aadhaar_number) { updates.aadhaar_number = d.aadhaar_number; setFrontAadhaarNum(normalizeAadhaar(d.aadhaar_number)); }
      if (d.gender) updates.gender = d.gender;
      if (d.address && !data.address) updates.address = d.address;
      if (Object.keys(updates).length > 0) {
        onBatchChange(updates);
        setOcrDone(true);
        toast.success("Aadhaar front details auto-filled! / आधार (सामने) भरा गया");
        if (updates.name) autoTransliterate(updates.name, "name_hindi");
      } else {
        toast.info("OCR could not read all fields — please fill manually");
      }
    } catch {
      toast.info("OCR failed — fill details manually");
    } finally {
      setOcrLoading(false);
    }
  };

  const handleAadhaarBack = async (path) => {
    onChange("aadhaar_back_path", path);
    setBackOcrDone(false); setAadhaarMismatch(false);
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
          toast.error("Aadhaar numbers don't match on front & back! Please verify both cards belong to the same person. / आधार नंबर मेल नहीं खाते।");
        }
      }
      if (Object.keys(updates).length > 0) {
        onBatchChange(updates);
        setBackOcrDone(true);
        toast.success("Address & Guardian name auto-filled! / पता और अभिभावक का नाम भरा गया");
        if (updates.relative_name) autoTransliterate(updates.relative_name, "relative_name_hindi");
      } else {
        toast.info("Back OCR could not read address — please fill manually");
      }
    } catch {
      toast.info("Back OCR failed — fill address manually");
    } finally {
      setBackOcrLoading(false);
    }
  };

  const hi = (f) => ocrDone && data[f] ? "border-green-400 bg-green-50/60" : backOcrDone && data[f] ? "border-blue-400 bg-blue-50/60" : "";
  const slug = title.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="space-y-5">
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

      <div>
        <label className="bk-label"><span className="bk-label-en">Phone Number<span className="text-destructive">*</span></span><span className="bk-label-hi">फ़ोन नंबर</span></label>
        <input type="tel" value={data.phone} onChange={e => onChange("phone", e.target.value)} className="bk-input" placeholder="9876543210" maxLength={10} data-testid={`phone-${slug}`} />
      </div>

      <DocUpload
        label="Aadhaar Card (Front)" labelHi="आधार कार्ड (सामने) — OCR: Name, DOB, Gender"
        value={data.aadhaar_front_path} onChange={handleAadhaarFront}
        required={isMandatory} testId={`aadhaar-front-${slug}`}
      />

      {wrongSideWarning && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2" data-testid="wrong-side-warning">
          <span className="font-bold shrink-0">!</span>
          <div>
            <p className="font-semibold">Wrong side uploaded / गलत तरफ अपलोड की</p>
            <p className="text-xs mt-0.5">You uploaded the BACK of the Aadhaar card in the front slot. Please upload the correct side (the side with the photo, name and date of birth).</p>
            <button type="button" onClick={() => setWrongSideWarning(false)} className="mt-1 text-xs underline">Try again / फिर से</button>
          </div>
        </div>
      )}

      {ocrLoading && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20 text-primary text-sm animate-pulse">
          <Loader2 size={16} className="animate-spin flex-shrink-0" />
          Extracting details from Aadhaar front... / आधार से विवरण निकाला जा रहा है...
        </div>
      )}
      {ocrDone && !ocrLoading && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 border border-green-200 text-green-700 text-sm">
          <Sparkles size={15} className="flex-shrink-0" />
          Name, DOB &amp; Gender auto-filled from front — upload back for Address &amp; Guardian name
        </div>
      )}

      <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 transition-opacity duration-200 ${ocrLoading ? "opacity-40 pointer-events-none" : ""}`}>
        <div>
          <label className="bk-label"><span className="bk-label-en">Full Name<span className="text-destructive">*</span></span><span className="bk-label-hi">पूरा नाम</span></label>
          <input
            type="text" value={data.name}
            onChange={e => onChange("name", e.target.value)}
            onBlur={e => { if (e.target.value && !data.name_hindi) autoTransliterate(e.target.value, "name_hindi"); }}
            className={`bk-input ${hi("name")}`} placeholder="Auto-filled from Aadhaar"
            data-testid={`name-${slug}`}
          />
        </div>
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Name in Hindi {transField === "name_hindi" && <span className="text-xs text-primary animate-pulse ml-1">(transliterating...)</span>}</span>
            <span className="bk-label-hi">हिंदी नाम</span>
          </label>
          <input
            type="text" value={data.name_hindi || ""}
            onChange={e => onChange("name_hindi", e.target.value)}
            className="bk-input border-amber-300 bg-amber-50/40 focus:border-amber-500"
            placeholder="Auto-filled · हिंदी में नाम"
            data-testid={`name-hindi-${slug}`}
          />
        </div>
        <div>
          <label className="bk-label"><span className="bk-label-en">Date of Birth<span className="text-destructive">*</span></span><span className="bk-label-hi">जन्म तिथि</span></label>
          <input type="text" value={data.dob} onChange={e => onChange("dob", e.target.value)} className={`bk-input ${hi("dob")}`} placeholder="DD/MM/YYYY" data-testid={`dob-${slug}`} />
        </div>
      </div>

      <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 transition-opacity duration-200 ${ocrLoading ? "opacity-40 pointer-events-none" : ""}`}>
        <div>
          <label className="bk-label"><span className="bk-label-en">Aadhaar Number<span className="text-destructive">*</span></span><span className="bk-label-hi">आधार संख्या</span></label>
          <input type="text" value={data.aadhaar_number} onChange={e => onChange("aadhaar_number", e.target.value)} className={`bk-input ${hi("aadhaar_number")}`} placeholder="XXXX XXXX XXXX" data-testid={`aadhaar-num-${slug}`} />
        </div>
        <div>
          <label className="bk-label"><span className="bk-label-en">Gender<span className="text-destructive">*</span></span><span className="bk-label-hi">लिंग</span></label>
          <select value={data.gender} onChange={e => onChange("gender", e.target.value)} className={`bk-input ${hi("gender")}`} data-testid={`gender-${slug}`}>
            <option value="">Select / चुनें</option>
            <option value="Male">Male / पुरुष</option>
            <option value="Female">Female / महिला</option>
            <option value="Other">Other / अन्य</option>
          </select>
        </div>
      </div>

      <DocUpload
        label="Aadhaar Card (Back)" labelHi="आधार कार्ड (पीछे) — OCR: पता और अभिभावक नाम"
        value={data.aadhaar_back_path} onChange={handleAadhaarBack}
        required={isMandatory} testId={`aadhaar-back-${slug}`}
      />

      {aadhaarMismatch && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2" data-testid="aadhaar-mismatch-warning">
          <span className="font-bold shrink-0">!</span>
          <div>
            <p className="font-semibold">Aadhaar number mismatch / आधार नंबर मेल नहीं खाते</p>
            <p className="text-xs mt-0.5">The Aadhaar numbers on the front and back cards don't match. Please verify both cards belong to the same person.</p>
            <button type="button" onClick={() => { onChange("aadhaar_back_path", null); setAadhaarMismatch(false); }} className="mt-1 text-xs underline">Retake back photo</button>
          </div>
        </div>
      )}

      {backOcrLoading && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm animate-pulse">
          <Loader2 size={16} className="animate-spin flex-shrink-0" />
          Reading address &amp; guardian name from Aadhaar back... / पीछे से पता निकाला जा रहा है...
        </div>
      )}
      {backOcrDone && !backOcrLoading && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm">
          <Sparkles size={15} className="flex-shrink-0" />
          Address &amp; Guardian name auto-filled from Aadhaar back — please verify below
        </div>
      )}

      <div className={`transition-opacity duration-200 ${(ocrLoading || backOcrLoading) ? "opacity-40 pointer-events-none" : ""}`}>
        <label className="bk-label"><span className="bk-label-en">Address<span className="text-destructive">*</span></span><span className="bk-label-hi">पता</span></label>
        <textarea value={data.address} onChange={e => onChange("address", e.target.value)} className={`bk-input h-auto py-3 resize-none ${hi("address")}`} rows={3} placeholder="Auto-filled from Aadhaar back" data-testid={`address-${slug}`} />
      </div>

      <div className={`transition-opacity duration-200 ${(ocrLoading || backOcrLoading) ? "opacity-40 pointer-events-none" : ""}`}>
        <label className="bk-label"><span className="bk-label-en">Husband's / Father's Name<span className="text-destructive">*</span></span><span className="bk-label-hi">पति / पिता का नाम</span></label>
        <input
          type="text" value={data.relative_name}
          onChange={e => onChange("relative_name", e.target.value)}
          onBlur={e => { if (e.target.value && !data.relative_name_hindi) autoTransliterate(e.target.value, "relative_name_hindi"); }}
          className={`bk-input ${hi("relative_name")}`} placeholder="Auto-filled from Aadhaar back"
          data-testid={`relative-name-${slug}`}
        />
      </div>

      <div className={`transition-opacity duration-200 ${(ocrLoading || backOcrLoading) ? "opacity-40 pointer-events-none" : ""}`}>
        <label className="bk-label">
          <span className="bk-label-en">Husband's / Father's Name in Hindi {transField === "relative_name_hindi" && <span className="text-xs text-primary animate-pulse ml-1">(transliterating...)</span>}</span>
          <span className="bk-label-hi">पति / पिता का हिंदी नाम</span>
        </label>
        <input
          type="text" value={data.relative_name_hindi || ""}
          onChange={e => onChange("relative_name_hindi", e.target.value)}
          className="bk-input border-amber-300 bg-amber-50/40 focus:border-amber-500"
          placeholder="Auto-filled · हिंदी में पति/पिता का नाम"
          data-testid={`relative-name-hindi-${slug}`}
        />
      </div>

      {/* Additional Doc — OPTIONAL */}
      <div className="pt-3 border-t border-dashed border-border">
        <p className="text-sm font-semibold text-muted-foreground mb-3">Additional Document <span className="font-normal">(Optional / वैकल्पिक)</span></p>
        <div>
          <label className="bk-label"><span className="bk-label-en">Document Type</span><span className="bk-label-hi">दस्तावेज़ प्रकार</span></label>
          <select value={data.document_type} onChange={e => { onChange("document_type", e.target.value); onChange("document_back_path", null); }} className="bk-input" data-testid={`doc-type-${slug}`}>
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
    </div>
  );
}
