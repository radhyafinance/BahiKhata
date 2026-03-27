import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Camera, MapPin, Loader2, CheckCircle, ChevronRight, ChevronLeft,
  X, RefreshCw, User, Users, Shield, ImageIcon, Sparkles, ToggleLeft, ToggleRight
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STEPS = [
  { id: 1, title: "Illaka & Misal", titleHi: "इलाका और मिसाल", icon: MapPin },
  { id: 2, title: "Primary Borrower", titleHi: "प्राथमिक उधारकर्ता", icon: User },
  { id: 3, title: "Co-borrower", titleHi: "सह-उधारकर्ता", icon: Users },
  { id: 4, title: "Guarantor", titleHi: "गारंटर", icon: Shield },
  { id: 5, title: "Live Photo & GPS", titleHi: "लाइव फोटो और GPS", icon: Camera },
  { id: 6, title: "Review & Submit", titleHi: "समीक्षा और जमा करें", icon: CheckCircle },
];

const emptyPerson = {
  phone: "", name: "", dob: "", address: "", relative_name: "", gender: "",
  aadhaar_number: "", aadhaar_front_path: null, aadhaar_back_path: null,
  document_type: "voter_id", document_front_path: null, document_back_path: null,
};

// ─── Image Compression ────────────────────────────────────────────────────────
async function compressImage(file, maxWidth = 1200, quality = 0.72) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      let w = img.naturalWidth, h = img.naturalHeight;
      if (w > maxWidth) { h = Math.round((h * maxWidth) / w); w = maxWidth; }
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      canvas.toBlob(
        (blob) => resolve(blob ? new File([blob], "img.jpg", { type: "image/jpeg" }) : file),
        "image/jpeg", quality
      );
    };
    img.onerror = () => resolve(file);
    img.src = url;
  });
}

// ─── Document Upload ──────────────────────────────────────────────────────────
function DocUpload({ label, labelHi, value, onChange, required, testId }) {
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const galleryRef = useRef();
  const cameraRef = useRef();

  const handleFile = async (e) => {
    const raw = e.target.files[0];
    if (!raw) return;
    e.target.value = "";
    const file = await compressImage(raw);
    setPreview(URL.createObjectURL(file));
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/upload`, fd, { withCredentials: true });
      onChange(res.data.path);
    } catch {
      toast.error(`Failed to upload ${label}`);
      setPreview(null);
    } finally {
      setUploading(false);
    }
  };

  const imgSrc = preview || (value ? `${API}/files/${value}` : null);

  return (
    <div>
      <label className="bk-label">
        <span className="bk-label-en">{label}{required && <span className="text-destructive ml-0.5">*</span>}</span>
        {labelHi && <span className="bk-label-hi">{labelHi}</span>}
      </label>
      {imgSrc && (
        <div className="relative border border-border rounded-xl overflow-hidden mb-2 bg-muted/10">
          <img src={imgSrc} alt={label} className="w-full max-h-44 object-contain p-2" />
          {uploading && <div className="absolute inset-0 bg-white/80 flex items-center justify-center"><Loader2 className="animate-spin text-primary" size={28} /></div>}
          <button type="button" onClick={() => { setPreview(null); onChange(null); }} className="absolute top-2 right-2 bg-destructive text-white rounded-full w-7 h-7 flex items-center justify-center shadow"><X size={14} /></button>
        </div>
      )}
      {!imgSrc && (
        <div className="border-2 border-dashed border-border rounded-xl bg-muted/10 p-3 text-center mb-2" data-testid={testId}>
          {uploading ? (
            <div className="flex items-center justify-center gap-2 py-2 text-muted-foreground">
              <Loader2 className="animate-spin text-primary" size={22} />
              <span className="text-sm">Uploading & compressing...</span>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">No photo selected</p>
          )}
        </div>
      )}
      {!uploading && (
        <div className="flex gap-2">
          <button type="button" onClick={() => galleryRef.current?.click()} className="flex-1 flex items-center justify-center gap-2 h-11 border border-border rounded-lg text-sm font-medium bg-white hover:bg-muted/50 transition-all" data-testid={`${testId}-gallery`}>
            <ImageIcon size={15} className="text-muted-foreground" /> Gallery
          </button>
          <button type="button" onClick={() => cameraRef.current?.click()} className="flex-1 flex items-center justify-center gap-2 h-11 border border-primary/40 rounded-lg text-sm font-medium text-primary bg-primary/5 hover:bg-primary/10 transition-all" data-testid={`${testId}-camera`}>
            <Camera size={15} /> Camera / कैमरा
          </button>
        </div>
      )}
      <input ref={galleryRef} type="file" accept="image/*" onChange={handleFile} className="hidden" />
      <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={handleFile} className="hidden" />
    </div>
  );
}

// ─── Person Section ───────────────────────────────────────────────────────────
function PersonSection({ title, titleHi, data, onChange, onBatchChange, isMandatory }) {
  const [ocrLoading, setOcrLoading] = useState(false);
  const [ocrDone, setOcrDone] = useState(false);
  const [backOcrLoading, setBackOcrLoading] = useState(false);
  const [backOcrDone, setBackOcrDone] = useState(false);

  const handleAadhaarFront = async (path) => {
    onChange("aadhaar_front_path", path);
    setOcrDone(false);
    if (!path) return;
    setOcrLoading(true);
    try {
      const res = await axios.post(`${API}/ocr/aadhaar`, { path }, { withCredentials: true });
      const d = res.data;
      const updates = {};
      if (d.name) updates.name = d.name;
      if (d.dob) updates.dob = d.dob;
      if (d.aadhaar_number) updates.aadhaar_number = d.aadhaar_number;
      if (d.gender) updates.gender = d.gender;
      // address from front is a fallback; back takes priority
      if (d.address && !data.address) updates.address = d.address;
      if (Object.keys(updates).length > 0) {
        onBatchChange(updates);
        setOcrDone(true);
        toast.success("Aadhaar front details auto-filled! / आधार (सामने) भरा गया");
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
    setBackOcrDone(false);
    if (!path) return;
    setBackOcrLoading(true);
    try {
      const res = await axios.post(`${API}/ocr/aadhaar-back`, { path }, { withCredentials: true });
      const d = res.data;
      const updates = {};
      if (d.address) updates.address = d.address;
      if (d.relative_name) updates.relative_name = d.relative_name;
      if (Object.keys(updates).length > 0) {
        onBatchChange(updates);
        setBackOcrDone(true);
        toast.success("Address & Guardian name auto-filled! / पता और अभिभावक का नाम भरा गया");
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

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">{title}</h3>
        <span className="text-sm text-muted-foreground">{titleHi}</span>
        {(ocrLoading || backOcrLoading) && <span className="flex items-center gap-1 text-primary text-xs ml-2 animate-pulse"><Loader2 size={12} className="animate-spin" />{backOcrLoading ? "Reading back..." : "Reading Aadhaar..."}</span>}
      </div>

      <div>
        <label className="bk-label"><span className="bk-label-en">Phone Number<span className="text-destructive">*</span></span><span className="bk-label-hi">फ़ोन नंबर</span></label>
        <input type="tel" value={data.phone} onChange={e => onChange("phone", e.target.value)} className="bk-input" placeholder="9876543210" maxLength={10} data-testid={`phone-${title.toLowerCase().replace(/\s+/g, "-")}`} />
      </div>

      <DocUpload
        label="Aadhaar Card (Front)" labelHi="आधार कार्ड (सामने) — OCR: Name, DOB, Gender"
        value={data.aadhaar_front_path} onChange={handleAadhaarFront}
        required={isMandatory} testId={`aadhaar-front-${title.toLowerCase().replace(/\s+/g, "-")}`}
      />

      {ocrLoading && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20 text-primary text-sm animate-pulse">
          <Loader2 size={16} className="animate-spin flex-shrink-0" />
          Extracting details from Aadhaar front... / आधार से विवरण निकाला जा रहा है...
        </div>
      )}
      {ocrDone && !ocrLoading && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-green-50 border border-green-200 text-green-700 text-sm">
          <Sparkles size={15} className="flex-shrink-0" />
          Name, DOB & Gender auto-filled from front — upload back for Address &amp; Guardian name
        </div>
      )}

      <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 transition-opacity duration-200 ${ocrLoading ? "opacity-40 pointer-events-none" : ""}`}>
        <div>
          <label className="bk-label"><span className="bk-label-en">Full Name<span className="text-destructive">*</span></span><span className="bk-label-hi">पूरा नाम</span></label>
          <input type="text" value={data.name} onChange={e => onChange("name", e.target.value)} className={`bk-input ${hi("name")}`} placeholder="Auto-filled from Aadhaar" data-testid={`name-${title.toLowerCase().replace(/\s+/g, "-")}`} />
        </div>
        <div>
          <label className="bk-label"><span className="bk-label-en">Date of Birth<span className="text-destructive">*</span></span><span className="bk-label-hi">जन्म तिथि</span></label>
          <input type="text" value={data.dob} onChange={e => onChange("dob", e.target.value)} className={`bk-input ${hi("dob")}`} placeholder="DD/MM/YYYY" data-testid={`dob-${title.toLowerCase().replace(/\s+/g, "-")}`} />
        </div>
      </div>

      <div className={`grid grid-cols-1 sm:grid-cols-2 gap-4 transition-opacity duration-200 ${ocrLoading ? "opacity-40 pointer-events-none" : ""}`}>
        <div>
          <label className="bk-label"><span className="bk-label-en">Aadhaar Number<span className="text-destructive">*</span></span><span className="bk-label-hi">आधार संख्या</span></label>
          <input type="text" value={data.aadhaar_number} onChange={e => onChange("aadhaar_number", e.target.value)} className={`bk-input ${hi("aadhaar_number")}`} placeholder="XXXX XXXX XXXX" data-testid={`aadhaar-num-${title.toLowerCase().replace(/\s+/g, "-")}`} />
        </div>
        <div>
          <label className="bk-label"><span className="bk-label-en">Gender<span className="text-destructive">*</span></span><span className="bk-label-hi">लिंग</span></label>
          <select value={data.gender} onChange={e => onChange("gender", e.target.value)} className={`bk-input ${hi("gender")}`} data-testid={`gender-${title.toLowerCase().replace(/\s+/g, "-")}`}>
            <option value="">Select / चुनें</option>
            <option value="Male">Male / पुरुष</option>
            <option value="Female">Female / महिला</option>
            <option value="Other">Other / अन्य</option>
          </select>
        </div>
      </div>

      {/* Aadhaar Back — OCR for Address + Relative Name */}
      <DocUpload
        label="Aadhaar Card (Back)" labelHi="आधार कार्ड (पीछे) — OCR: पता और अभिभावक नाम"
        value={data.aadhaar_back_path} onChange={handleAadhaarBack}
        required={isMandatory} testId={`aadhaar-back-${title.toLowerCase().replace(/\s+/g, "-")}`}
      />

      {backOcrLoading && (
        <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm animate-pulse">
          <Loader2 size={16} className="animate-spin flex-shrink-0" />
          Reading address & guardian name from Aadhaar back... / पीछे से पता निकाला जा रहा है...
        </div>
      )}
      {backOcrDone && !backOcrLoading && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 border border-blue-200 text-blue-700 text-sm">
          <Sparkles size={15} className="flex-shrink-0" />
          Address &amp; Guardian name auto-filled from Aadhaar back — please verify below
        </div>
      )}

      <div className={`transition-opacity duration-200 ${(ocrLoading || backOcrLoading) ? "opacity-40 pointer-events-none" : ""}`}>
        <label className="bk-label"><span className="bk-label-en">Husband's / Father's Name<span className="text-destructive">*</span></span><span className="bk-label-hi">पति / पिता का नाम</span></label>
        <input type="text" value={data.relative_name} onChange={e => onChange("relative_name", e.target.value)} className={`bk-input ${hi("relative_name")}`} placeholder="Auto-filled from Aadhaar back" data-testid={`relative-name-${title.toLowerCase().replace(/\s+/g, "-")}`} />
      </div>

      <div className={`transition-opacity duration-200 ${(ocrLoading || backOcrLoading) ? "opacity-40 pointer-events-none" : ""}`}>
        <label className="bk-label"><span className="bk-label-en">Address<span className="text-destructive">*</span></span><span className="bk-label-hi">पता</span></label>
        <textarea value={data.address} onChange={e => onChange("address", e.target.value)} className={`bk-input h-auto py-3 resize-none ${hi("address")}`} rows={3} placeholder="Auto-filled from Aadhaar back" data-testid={`address-${title.toLowerCase().replace(/\s+/g, "-")}`} />
      </div>

      {/* Additional Doc — OPTIONAL */}
      <div className="pt-3 border-t border-dashed border-border">
        <p className="text-sm font-semibold text-muted-foreground mb-3">Additional Document <span className="font-normal">(Optional / वैकल्पिक)</span></p>
        <div>
          <label className="bk-label"><span className="bk-label-en">Document Type</span><span className="bk-label-hi">दस्तावेज़ प्रकार</span></label>
          <select value={data.document_type} onChange={e => { onChange("document_type", e.target.value); onChange("document_back_path", null); }} className="bk-input" data-testid={`doc-type-${title.toLowerCase().replace(/\s+/g, "-")}`}>
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
            testId={`doc-front-${title.toLowerCase().replace(/\s+/g, "-")}`}
          />
        </div>
        {data.document_type !== "pan" && (
          <div className="mt-3">
            <DocUpload
              label={`${data.document_type === "ration_card" ? "Ration Card" : "Voter ID"} (Back)`}
              labelHi="पीछे की तस्वीर"
              value={data.document_back_path} onChange={v => onChange("document_back_path", v)}
              testId={`doc-back-${title.toLowerCase().replace(/\s+/g, "-")}`}
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Live Photo + GPS ──────────────────────────────────────────────────────────
function LivePhotoGPS({ livePhotoPath, gpsLocation, onPhotoChange, onGPSChange }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [photoUploading, setPhotoUploading] = useState(false);
  const [gpsLoading, setGpsLoading] = useState(false);
  const galleryRef = useRef();

  // Set srcObject after render when camera goes active
  useEffect(() => {
    if (stream && videoRef.current && cameraActive) {
      videoRef.current.srcObject = stream;
      videoRef.current.play().catch(() => {});
    }
  }, [stream, cameraActive]);

  useEffect(() => {
    return () => { if (stream) stream.getTracks().forEach(t => t.stop()); };
  }, [stream]);

  const startCamera = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      setStream(s);
      setCameraActive(true);
    } catch (err) {
      console.error("Camera error:", err);
      toast.error("Camera not available. Use gallery upload instead.");
    }
  };

  const stopCamera = () => {
    stream?.getTracks().forEach(t => t.stop());
    setStream(null);
    setCameraActive(false);
  };

  const capturePhoto = async () => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!video || !canvas) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    stopCamera();
    setPhotoUploading(true);
    canvas.toBlob(async (blob) => {
      try {
        const compressed = await compressImage(new File([blob], "live.jpg", { type: "image/jpeg" }), 900, 0.8);
        const fd = new FormData();
        fd.append("file", compressed);
        const res = await axios.post(`${API}/upload`, fd, { withCredentials: true });
        onPhotoChange(res.data.path);
        toast.success("Live photo saved!");
      } catch { toast.error("Photo upload failed"); }
      finally { setPhotoUploading(false); }
    }, "image/jpeg", 0.85);
  };

  const handleGalleryPhoto = async (e) => {
    const raw = e.target.files[0];
    if (!raw) return;
    e.target.value = "";
    setPhotoUploading(true);
    try {
      const file = await compressImage(raw, 900, 0.8);
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/upload`, fd, { withCredentials: true });
      onPhotoChange(res.data.path);
      toast.success("Photo saved!");
    } catch { toast.error("Upload failed"); }
    finally { setPhotoUploading(false); }
  };

  const captureGPS = () => {
    if (!navigator.geolocation) { toast.error("GPS not supported"); return; }
    setGpsLoading(true);
    navigator.geolocation.getCurrentPosition(
      pos => {
        onGPSChange({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: Math.round(pos.coords.accuracy), timestamp: new Date().toISOString() });
        toast.success("GPS location captured!");
        setGpsLoading(false);
      },
      err => { toast.error(`GPS error: ${err.message || "Try again"}`); setGpsLoading(false); },
      { enableHighAccuracy: true, timeout: 30000 }
    );
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">Live Photo & GPS</h3>
        <span className="text-sm text-muted-foreground">लाइव फोटो और GPS</span>
      </div>

      {/* Live Photo */}
      <div className="space-y-3">
        <div>
          <p className="text-sm font-semibold">Live Client Photo<span className="text-destructive">*</span></p>
          <p className="text-xs text-muted-foreground">लाइव क्लाइंट फोटो</p>
        </div>

        {cameraActive ? (
          <div className="space-y-3">
            <video ref={videoRef} autoPlay playsInline muted className="w-full max-w-sm mx-auto rounded-xl border-4 border-primary block" data-testid="camera-preview" />
            <div className="flex gap-3 max-w-sm mx-auto">
              <button type="button" onClick={capturePhoto} className="flex-1 bk-btn-primary flex items-center justify-center gap-2" data-testid="capture-photo-btn">
                <Camera size={18} /> Capture
              </button>
              <button type="button" onClick={stopCamera} className="bk-btn-secondary px-4 w-14 flex items-center justify-center" data-testid="cancel-camera-btn">
                <X size={18} />
              </button>
            </div>
          </div>
        ) : livePhotoPath ? (
          <div className="flex flex-col items-center gap-3">
            <img src={`${API}/files/${livePhotoPath}`} alt="Live Photo" className="w-32 h-32 object-cover rounded-full border-4 border-primary shadow-md" data-testid="live-photo-preview" />
            <button type="button" onClick={() => { onPhotoChange(null); }} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" data-testid="retake-photo-btn">
              <RefreshCw size={13} /> Retake / फिर से
            </button>
          </div>
        ) : (
          <div className="border-2 border-dashed border-border rounded-xl py-8 px-4 flex flex-col items-center gap-4">
            {photoUploading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 size={24} className="animate-spin text-primary" />
                <span className="text-sm">Uploading...</span>
              </div>
            ) : (
              <>
                <Camera size={36} className="text-muted-foreground opacity-30" />
                <div className="flex gap-3">
                  <button type="button" onClick={startCamera} className="bk-btn-primary max-w-[180px] flex items-center justify-center gap-2 text-sm h-11" data-testid="start-camera-btn">
                    <Camera size={16} /> Open Camera
                  </button>
                  <button type="button" onClick={() => galleryRef.current?.click()} className="bk-btn-secondary max-w-[160px] flex items-center justify-center gap-2 text-sm h-11" data-testid="gallery-photo-btn">
                    <ImageIcon size={16} /> Gallery
                  </button>
                </div>
                <p className="text-xs text-muted-foreground text-center">Camera खोलें या गैलरी से चुनें</p>
              </>
            )}
          </div>
        )}
        <canvas ref={canvasRef} className="hidden" />
        <input ref={galleryRef} type="file" accept="image/*" onChange={handleGalleryPhoto} className="hidden" />
      </div>

      {/* GPS — Mandatory */}
      <div className="space-y-3">
        <div>
          <p className="text-sm font-semibold">GPS Location<span className="text-destructive">*</span> <span className="text-xs font-normal text-muted-foreground">(Mandatory / अनिवार्य)</span></p>
          <p className="text-xs text-muted-foreground">GPS स्थान — KYC करने की जगह रिकॉर्ड होगी</p>
        </div>

        {gpsLocation ? (
          <div className="p-4 rounded-xl bg-green-50 border border-green-200 space-y-2" data-testid="gps-captured">
            <div className="flex items-center gap-2 text-green-700">
              <MapPin size={17} />
              <span className="font-semibold text-sm">Location Captured / स्थान रिकॉर्ड किया गया</span>
            </div>
            <p className="text-sm">Lat: {gpsLocation.latitude?.toFixed(6)}, Lng: {gpsLocation.longitude?.toFixed(6)}</p>
            <p className="text-xs text-muted-foreground">Accuracy: ±{gpsLocation.accuracy}m</p>
            <a href={`https://www.google.com/maps?q=${gpsLocation.latitude},${gpsLocation.longitude}`} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">View on map →</a>
            <button type="button" onClick={() => onGPSChange(null)} className="block text-xs text-muted-foreground hover:text-foreground mt-1" data-testid="clear-gps-btn">Clear & recapture</button>
          </div>
        ) : (
          <button type="button" onClick={captureGPS} disabled={gpsLoading} className="bk-btn-secondary max-w-xs flex items-center justify-center gap-2" data-testid="capture-gps-btn">
            {gpsLoading ? <><Loader2 size={18} className="animate-spin" /> Getting location...</> : <><MapPin size={18} /> Capture GPS Location</>}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Review ───────────────────────────────────────────────────────────────────
function ReviewSection({ formData, illaka, misal, includeCoBorrower, includeGuarantor }) {
  const PersonSummary = ({ title, data }) => {
    if (!data) return null;
    return (
      <div className="rounded-xl border border-border p-4 space-y-2">
        <h4 className="font-semibold text-foreground text-sm">{title}</h4>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div><span className="text-muted-foreground">Name:</span> <span className="font-medium">{data.name || "—"}</span></div>
          <div><span className="text-muted-foreground">Phone:</span> <span className="font-medium">{data.phone || "—"}</span></div>
          <div><span className="text-muted-foreground">DOB:</span> <span className="font-medium">{data.dob || "—"}</span></div>
          <div><span className="text-muted-foreground">Aadhaar:</span> <span className="font-medium">{data.aadhaar_number || "—"}</span></div>
          <div><span className="text-muted-foreground">Husband/Father:</span> <span className="font-medium">{data.relative_name || "—"}</span></div>
          <div className="col-span-2"><span className="text-muted-foreground">Address:</span> <span className="font-medium">{data.address || "—"}</span></div>
        </div>
      </div>
    );
  };
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">Review & Submit</h3>
        <span className="text-sm text-muted-foreground">समीक्षा करें</span>
      </div>
      <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 text-primary text-sm">
        <strong>Illaka:</strong> {illaka?.name || "—"} &nbsp;|&nbsp; <strong>Misal:</strong> {misal?.name || "—"}
      </div>
      <PersonSummary title="Primary Borrower / प्राथमिक उधारकर्ता" data={formData.primaryBorrower} />
      {includeCoBorrower && <PersonSummary title="Co-borrower / सह-उधारकर्ता" data={formData.coBorrower} />}
      {includeGuarantor && <PersonSummary title="Guarantor / गारंटर" data={formData.guarantor} />}
      <div className="flex gap-4 text-sm">
        <span className={formData.livePhotoPath ? "text-green-700" : "text-muted-foreground"}>
          {formData.livePhotoPath ? "✓" : "✗"} Live Photo
        </span>
        <span className={formData.gpsLocation ? "text-green-700" : "text-destructive font-semibold"}>
          {formData.gpsLocation ? "✓" : "✗"} GPS Location {!formData.gpsLocation && "(Required!)"}
        </span>
      </div>
    </div>
  );
}

// ─── KYC Form ─────────────────────────────────────────────────────────────────
export default function KYCForm() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [illakas, setIllakas] = useState([]);
  const [misals, setMisals] = useState([]);
  const [selectedIllaka, setSelectedIllaka] = useState(null);
  const [selectedMisal, setSelectedMisal] = useState(null);
  const [includeCoBorrower, setIncludeCoBorrower] = useState(false);
  const [includeGuarantor, setIncludeGuarantor] = useState(false);

  const [formData, setFormData] = useState({
    primaryBorrower: { ...emptyPerson },
    coBorrower: { ...emptyPerson },
    guarantor: { ...emptyPerson },
    livePhotoPath: null,
    gpsLocation: null,
    notes: "",
  });

  useEffect(() => {
    axios.get(`${API}/illakas`, { withCredentials: true }).then(r => setIllakas(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedIllaka) { setMisals([]); setSelectedMisal(null); return; }
    axios.get(`${API}/misals?illaka_id=${selectedIllaka.id}`, { withCredentials: true })
      .then(r => { setMisals(r.data); setSelectedMisal(null); }).catch(() => {});
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
    if (step === 3 && includeCoBorrower) {
      if (!formData.coBorrower.phone) { toast.error("Co-borrower phone required"); return false; }
    }
    if (step === 4 && includeGuarantor) {
      if (!formData.guarantor.phone) { toast.error("Guarantor phone required"); return false; }
    }
    if (step === 5) {
      if (!formData.livePhotoPath) { toast.error("Live photo is required / लाइव फोटो अनिवार्य है"); return false; }
      if (!formData.gpsLocation) { toast.error("GPS location is required / GPS स्थान अनिवार्य है"); return false; }
      return true;
    }
    return true;
  };

  const nextStep = () => {
    if (!validateStep()) return;
    setStep(s => s + 1);
  };

  const handleSubmit = async () => {
    if (!validateStep()) return;
    if (!formData.gpsLocation) { toast.error("GPS location is required"); return; }
    setSubmitting(true);
    try {
      const payload = {
        illaka_id: selectedIllaka.id,
        illaka_name: selectedIllaka.name,
        misal_id: selectedMisal.id,
        misal_name: selectedMisal.name,
        primary_borrower: formData.primaryBorrower,
        co_borrower: includeCoBorrower && formData.coBorrower.phone ? formData.coBorrower : null,
        guarantor: includeGuarantor && formData.guarantor.phone ? formData.guarantor : null,
        live_photo_path: formData.livePhotoPath,
        gps_location: formData.gpsLocation,
        notes: formData.notes,
      };
      const res = id
        ? await axios.put(`${API}/kycs/${id}`, payload, { withCredentials: true })
        : await axios.post(`${API}/kycs`, payload, { withCredentials: true });
      toast.success("KYC submitted successfully!");
      navigate(`/clients/${res.data.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to submit KYC");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold font-['Outfit']">{id ? "Edit KYC" : "New KYC / नया KYC"}</h1>
        <p className="text-muted-foreground text-sm mt-1">Step {step} of {STEPS.length}</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-1 mb-7 overflow-x-auto pb-1" data-testid="step-indicator">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-shrink-0">
            <button
              type="button"
              onClick={() => s.id < step && setStep(s.id)}
              className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs font-semibold transition-all ${
                step === s.id ? "bg-primary text-white" : s.id < step ? "bg-primary/20 text-primary cursor-pointer" : "bg-muted text-muted-foreground"
              }`}
              data-testid={`step-btn-${s.id}`}
            >
              <s.icon size={13} />
              <span className="hidden sm:inline">{s.title}</span>
              <span className="sm:hidden">{s.id}</span>
            </button>
            {i < STEPS.length - 1 && <ChevronRight size={13} className="text-muted-foreground mx-0.5" />}
          </div>
        ))}
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
              ) : (
                <select value={selectedIllaka?.id || ""} onChange={e => { const ill = illakas.find(i => i.id === e.target.value); setSelectedIllaka(ill || null); }} className="bk-input" data-testid="illaka-select">
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
    </div>
  );
}
