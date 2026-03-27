import { useState, useRef, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Camera, MapPin, Upload, Loader2, CheckCircle, ChevronRight, ChevronLeft,
  X, RefreshCw, User, Users, Shield
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STEPS = [
  { id: 1, title: "Primary Borrower", titleHi: "प्राथमिक उधारकर्ता", icon: User },
  { id: 2, title: "Co-borrower", titleHi: "सह-उधारकर्ता", icon: Users },
  { id: 3, title: "Guarantor", titleHi: "गारंटर", icon: Shield },
  { id: 4, title: "Live Photo & GPS", titleHi: "लाइव फोटो और GPS", icon: Camera },
  { id: 5, title: "Review & Submit", titleHi: "समीक्षा और जमा करें", icon: CheckCircle },
];

const emptyPerson = {
  phone: "",
  name: "",
  dob: "",
  address: "",
  gender: "",
  aadhaar_number: "",
  aadhaar_front_path: null,
  aadhaar_back_path: null,
  document_type: "voter_id",
  document_front_path: null,
  document_back_path: null,
};

// ─── Document Upload Field ─────────────────────────────────────────────────
function DocUpload({ label, labelHi, value, onChange, accept = "image/*", testId }) {
  const [uploading, setUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const inputRef = useRef();

  const handleChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/upload`, fd, { withCredentials: true });
      onChange(res.data.path);
      toast.success(`${label} uploaded`);
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
        <span className="bk-label-en">{label}</span>
        {labelHi && <span className="bk-label-hi">{labelHi}</span>}
      </label>
      <div
        className="border-2 border-dashed border-border rounded-xl overflow-hidden cursor-pointer hover:border-primary transition-colors bg-muted/20"
        onClick={() => inputRef.current?.click()}
        data-testid={testId || `upload-${label.toLowerCase().replace(/\s+/g, "-")}`}
      >
        {imgSrc ? (
          <div className="relative">
            <img src={imgSrc} alt={label} className="w-full max-h-44 object-contain p-2" />
            {uploading && (
              <div className="absolute inset-0 bg-white/80 flex items-center justify-center">
                <Loader2 className="animate-spin text-primary" size={28} />
              </div>
            )}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setPreview(null); onChange(null); }}
              className="absolute top-2 right-2 bg-destructive text-white rounded-full w-7 h-7 flex items-center justify-center hover:bg-destructive/90"
            >
              <X size={14} />
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-muted-foreground gap-2">
            {uploading ? (
              <Loader2 className="animate-spin text-primary" size={28} />
            ) : (
              <>
                <Upload size={28} className="opacity-50" />
                <span className="text-sm font-medium">Click to upload</span>
                <span className="text-xs opacity-70">JPG, PNG supported</span>
              </>
            )}
          </div>
        )}
      </div>
      <input ref={inputRef} type="file" accept={accept} onChange={handleChange} className="hidden" />
    </div>
  );
}

// ─── Person KYC Section ───────────────────────────────────────────────────────
function PersonSection({ title, titleHi, data, onChange }) {
  const [ocrLoading, setOcrLoading] = useState(false);

  const handleAadhaarFront = async (path) => {
    onChange("aadhaar_front_path", path);
    if (!path) return;
    setOcrLoading(true);
    try {
      const res = await axios.post(`${API}/ocr/aadhaar`, { path }, { withCredentials: true });
      if (res.data.name) onChange("name", res.data.name);
      if (res.data.dob) onChange("dob", res.data.dob);
      if (res.data.address) onChange("address", res.data.address);
      if (res.data.aadhaar_number) onChange("aadhaar_number", res.data.aadhaar_number);
      if (res.data.gender) onChange("gender", res.data.gender);
      toast.success("Aadhaar data extracted automatically / आधार डेटा स्वतः निकाला गया");
    } catch {
      toast.info("Please fill details manually / कृपया विवरण मैन्युअल भरें");
    } finally {
      setOcrLoading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold text-foreground font-['Outfit']">{title}</h3>
        <span className="text-sm text-muted-foreground">{titleHi}</span>
        {ocrLoading && (
          <span className="flex items-center gap-1 text-primary text-xs ml-2">
            <Loader2 size={13} className="animate-spin" /> Extracting Aadhaar data...
          </span>
        )}
      </div>

      {/* Phone */}
      <div>
        <label className="bk-label">
          <span className="bk-label-en">Phone Number *</span>
          <span className="bk-label-hi">फ़ोन नंबर</span>
        </label>
        <input
          type="tel"
          value={data.phone}
          onChange={(e) => onChange("phone", e.target.value)}
          className="bk-input"
          placeholder="9876543210"
          maxLength={10}
          data-testid={`phone-${title.toLowerCase().replace(/\s+/g, "-")}`}
        />
      </div>

      {/* Aadhaar Front */}
      <DocUpload
        label="Aadhaar Card (Front)"
        labelHi="आधार कार्ड (सामने) — OCR will auto-fill details"
        value={data.aadhaar_front_path}
        onChange={handleAadhaarFront}
        testId={`aadhaar-front-${title.toLowerCase().replace(/\s+/g, "-")}`}
      />

      {/* OCR Fields */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Full Name</span>
            <span className="bk-label-hi">पूरा नाम</span>
          </label>
          <input
            type="text"
            value={data.name}
            onChange={(e) => onChange("name", e.target.value)}
            className="bk-input"
            placeholder="Auto-filled from Aadhaar"
            data-testid={`name-${title.toLowerCase().replace(/\s+/g, "-")}`}
          />
        </div>
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Date of Birth</span>
            <span className="bk-label-hi">जन्म तिथि</span>
          </label>
          <input
            type="text"
            value={data.dob}
            onChange={(e) => onChange("dob", e.target.value)}
            className="bk-input"
            placeholder="DD/MM/YYYY"
            data-testid={`dob-${title.toLowerCase().replace(/\s+/g, "-")}`}
          />
        </div>
      </div>

      <div>
        <label className="bk-label">
          <span className="bk-label-en">Address</span>
          <span className="bk-label-hi">पता</span>
        </label>
        <textarea
          value={data.address}
          onChange={(e) => onChange("address", e.target.value)}
          className="bk-input h-auto py-3 resize-none"
          rows={3}
          placeholder="Auto-filled from Aadhaar"
          data-testid={`address-${title.toLowerCase().replace(/\s+/g, "-")}`}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Aadhaar Number</span>
            <span className="bk-label-hi">आधार संख्या</span>
          </label>
          <input
            type="text"
            value={data.aadhaar_number}
            onChange={(e) => onChange("aadhaar_number", e.target.value)}
            className="bk-input"
            placeholder="XXXX XXXX XXXX"
            data-testid={`aadhaar-num-${title.toLowerCase().replace(/\s+/g, "-")}`}
          />
        </div>
        <div>
          <label className="bk-label">
            <span className="bk-label-en">Gender</span>
            <span className="bk-label-hi">लिंग</span>
          </label>
          <select
            value={data.gender}
            onChange={(e) => onChange("gender", e.target.value)}
            className="bk-input"
            data-testid={`gender-${title.toLowerCase().replace(/\s+/g, "-")}`}
          >
            <option value="">Select / चुनें</option>
            <option value="Male">Male / पुरुष</option>
            <option value="Female">Female / महिला</option>
            <option value="Other">Other / अन्य</option>
          </select>
        </div>
      </div>

      {/* Aadhaar Back */}
      <DocUpload
        label="Aadhaar Card (Back)"
        labelHi="आधार कार्ड (पीछे)"
        value={data.aadhaar_back_path}
        onChange={(v) => onChange("aadhaar_back_path", v)}
        testId={`aadhaar-back-${title.toLowerCase().replace(/\s+/g, "-")}`}
      />

      {/* Additional Document */}
      <div>
        <label className="bk-label">
          <span className="bk-label-en">Additional Document Type</span>
          <span className="bk-label-hi">अतिरिक्त दस्तावेज़ प्रकार</span>
        </label>
        <select
          value={data.document_type}
          onChange={(e) => { onChange("document_type", e.target.value); onChange("document_back_path", null); }}
          className="bk-input"
          data-testid={`doc-type-${title.toLowerCase().replace(/\s+/g, "-")}`}
        >
          <option value="voter_id">Voter ID / मतदाता पहचान पत्र</option>
          <option value="pan">PAN Card / पैन कार्ड</option>
          <option value="ration_card">Ration Card / राशन कार्ड</option>
        </select>
      </div>

      <DocUpload
        label={`${data.document_type === "pan" ? "PAN Card" : data.document_type === "ration_card" ? "Ration Card" : "Voter ID"} (Front)`}
        labelHi="सामने की तस्वीर"
        value={data.document_front_path}
        onChange={(v) => onChange("document_front_path", v)}
        testId={`doc-front-${title.toLowerCase().replace(/\s+/g, "-")}`}
      />

      {data.document_type !== "pan" && (
        <DocUpload
          label={`${data.document_type === "ration_card" ? "Ration Card" : "Voter ID"} (Back)`}
          labelHi="पीछे की तस्वीर"
          value={data.document_back_path}
          onChange={(v) => onChange("document_back_path", v)}
          testId={`doc-back-${title.toLowerCase().replace(/\s+/g, "-")}`}
        />
      )}
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

  useEffect(() => {
    return () => {
      if (stream) stream.getTracks().forEach((t) => t.stop());
    };
  }, [stream]);

  const startCamera = async () => {
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
      videoRef.current.srcObject = s;
      setStream(s);
      setCameraActive(true);
    } catch {
      toast.error("Camera access denied. Please allow camera permission.");
    }
  };

  const capturePhoto = () => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);

    canvas.toBlob(async (blob) => {
      stream?.getTracks().forEach((t) => t.stop());
      setStream(null);
      setCameraActive(false);
      setPhotoUploading(true);
      try {
        const fd = new FormData();
        fd.append("file", blob, "live_photo.jpg");
        const res = await axios.post(`${API}/upload`, fd, { withCredentials: true });
        onPhotoChange(res.data.path);
        toast.success("Live photo captured!");
      } catch {
        toast.error("Failed to upload photo");
      } finally {
        setPhotoUploading(false);
      }
    }, "image/jpeg", 0.85);
  };

  const captureGPS = () => {
    if (!navigator.geolocation) {
      toast.error("Geolocation not supported");
      return;
    }
    setGpsLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const loc = {
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: Math.round(pos.coords.accuracy),
          timestamp: new Date().toISOString(),
        };
        onGPSChange(loc);
        toast.success("GPS location captured!");
        setGpsLoading(false);
      },
      () => {
        toast.error("GPS failed. Try again.");
        setGpsLoading(false);
      },
      { enableHighAccuracy: true, timeout: 30000 }
    );
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold text-foreground font-['Outfit']">Live Photo & GPS</h3>
        <span className="text-sm text-muted-foreground">लाइव फोटो और GPS</span>
      </div>

      {/* Live Photo */}
      <div className="space-y-4">
        <div>
          <p className="bk-label-en text-sm font-semibold">Live Client Photo *</p>
          <p className="bk-label-hi text-xs text-muted-foreground">लाइव क्लाइंट फोटो (वेबकैम द्वारा)</p>
        </div>

        {cameraActive ? (
          <div className="space-y-3">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              className="w-full max-w-sm mx-auto rounded-xl border-2 border-primary"
              data-testid="camera-preview"
            />
            <div className="flex gap-3 max-w-sm mx-auto">
              <button
                type="button"
                onClick={capturePhoto}
                className="flex-1 bk-btn-primary flex items-center justify-center gap-2"
                data-testid="capture-photo-btn"
              >
                <Camera size={18} /> Capture / कैप्चर
              </button>
              <button
                type="button"
                onClick={() => { stream?.getTracks().forEach((t) => t.stop()); setStream(null); setCameraActive(false); }}
                className="bk-btn-secondary px-4 max-w-[80px]"
                data-testid="cancel-camera-btn"
              >
                <X size={18} />
              </button>
            </div>
          </div>
        ) : livePhotoPath ? (
          <div className="flex flex-col items-center gap-3">
            <img
              src={`${API}/files/${livePhotoPath}`}
              alt="Live photo"
              className="w-32 h-32 object-cover rounded-full border-4 border-primary shadow-md"
              data-testid="live-photo-preview"
            />
            <button
              type="button"
              onClick={() => { onPhotoChange(null); startCamera(); }}
              className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              data-testid="retake-photo-btn"
            >
              <RefreshCw size={14} /> Retake Photo
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center py-8 gap-4 border-2 border-dashed border-border rounded-xl">
            {photoUploading ? (
              <Loader2 size={32} className="animate-spin text-primary" />
            ) : (
              <>
                <Camera size={40} className="text-muted-foreground opacity-40" />
                <button
                  type="button"
                  onClick={startCamera}
                  className="bk-btn-primary max-w-xs flex items-center justify-center gap-2"
                  data-testid="start-camera-btn"
                >
                  <Camera size={18} /> Open Camera / कैमरा खोलें
                </button>
              </>
            )}
          </div>
        )}
        <canvas ref={canvasRef} className="hidden" />
      </div>

      {/* GPS */}
      <div className="space-y-4">
        <div>
          <p className="bk-label-en text-sm font-semibold">GPS Location</p>
          <p className="bk-label-hi text-xs text-muted-foreground">GPS स्थान</p>
        </div>

        {gpsLocation ? (
          <div className="p-4 rounded-xl bg-green-50 border border-green-200 space-y-2" data-testid="gps-captured">
            <div className="flex items-center gap-2 text-green-700">
              <MapPin size={18} />
              <span className="font-semibold text-sm">Location Captured</span>
            </div>
            <p className="text-sm text-foreground">
              Lat: {gpsLocation.latitude?.toFixed(6)}, Lng: {gpsLocation.longitude?.toFixed(6)}
            </p>
            <p className="text-xs text-muted-foreground">Accuracy: ±{gpsLocation.accuracy}m</p>
            <button
              type="button"
              onClick={() => onGPSChange(null)}
              className="text-xs text-muted-foreground hover:text-foreground"
              data-testid="clear-gps-btn"
            >
              Clear & recapture
            </button>
          </div>
        ) : (
          <button
            type="button"
            onClick={captureGPS}
            disabled={gpsLoading}
            className="bk-btn-secondary flex items-center justify-center gap-2 max-w-xs"
            data-testid="capture-gps-btn"
          >
            {gpsLoading ? (
              <><Loader2 size={18} className="animate-spin" /> Getting location...</>
            ) : (
              <><MapPin size={18} /> Capture GPS Location / GPS लोकेशन</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Review Step ──────────────────────────────────────────────────────────────
function ReviewSection({ formData }) {
  const PersonSummary = ({ title, data }) => {
    if (!data) return null;
    return (
      <div className="rounded-xl border border-border p-4 space-y-2">
        <h4 className="font-semibold text-foreground">{title}</h4>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div><span className="text-muted-foreground">Name:</span> <span className="font-medium">{data.name || "—"}</span></div>
          <div><span className="text-muted-foreground">Phone:</span> <span className="font-medium">{data.phone || "—"}</span></div>
          <div><span className="text-muted-foreground">DOB:</span> <span className="font-medium">{data.dob || "—"}</span></div>
          <div><span className="text-muted-foreground">Aadhaar:</span> <span className="font-medium">{data.aadhaar_number || "—"}</span></div>
          <div className="col-span-2"><span className="text-muted-foreground">Document:</span> <span className="font-medium capitalize">{data.document_type?.replace("_", " ") || "—"}</span></div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold text-foreground font-['Outfit']">Review & Submit</h3>
        <span className="text-sm text-muted-foreground">समीक्षा करें</span>
      </div>
      <div className="p-4 rounded-xl bg-primary/5 border border-primary/20 text-sm text-primary">
        Please review all details before submitting. / जमा करने से पहले सभी विवरण जांचें।
      </div>
      <PersonSummary title="Primary Borrower / प्राथमिक उधारकर्ता" data={formData.primaryBorrower} />
      <PersonSummary title="Co-borrower / सह-उधारकर्ता" data={formData.coBorrower} />
      <PersonSummary title="Guarantor / गारंटर" data={formData.guarantor} />
      <div className="flex gap-3 text-sm">
        <div className="flex items-center gap-1">
          <Camera size={14} className={formData.livePhotoPath ? "text-green-600" : "text-muted-foreground"} />
          <span className={formData.livePhotoPath ? "text-green-700" : "text-muted-foreground"}>
            Live Photo {formData.livePhotoPath ? "Captured" : "Not Captured"}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <MapPin size={14} className={formData.gpsLocation ? "text-green-600" : "text-muted-foreground"} />
          <span className={formData.gpsLocation ? "text-green-700" : "text-muted-foreground"}>
            GPS {formData.gpsLocation ? "Captured" : "Not Captured"}
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Main KYC Form ─────────────────────────────────────────────────────────────
export default function KYCForm() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);

  const [formData, setFormData] = useState({
    primaryBorrower: { ...emptyPerson },
    coBorrower: { ...emptyPerson },
    guarantor: { ...emptyPerson },
    livePhotoPath: null,
    gpsLocation: null,
    notes: "",
    branch: "",
  });

  // Load existing KYC if editing
  useEffect(() => {
    if (!id) return;
    axios.get(`${API}/kycs/${id}`, { withCredentials: true }).then((r) => {
      const k = r.data;
      setFormData({
        primaryBorrower: k.primary_borrower || { ...emptyPerson },
        coBorrower: k.co_borrower || { ...emptyPerson },
        guarantor: k.guarantor || { ...emptyPerson },
        livePhotoPath: k.live_photo_path || null,
        gpsLocation: k.gps_location || null,
        notes: k.notes || "",
        branch: k.branch || "",
      });
    }).catch(() => toast.error("Failed to load KYC"));
  }, [id]);

  const updatePerson = (key) => (field, value) => {
    setFormData((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: value },
    }));
  };

  const handleSubmit = async () => {
    if (!formData.primaryBorrower.phone) {
      toast.error("Primary borrower phone number is required");
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        primary_borrower: formData.primaryBorrower,
        co_borrower: formData.coBorrower.phone ? formData.coBorrower : null,
        guarantor: formData.guarantor.phone ? formData.guarantor : null,
        live_photo_path: formData.livePhotoPath,
        gps_location: formData.gpsLocation,
        notes: formData.notes,
        branch: formData.branch,
      };
      let res;
      if (id) {
        res = await axios.put(`${API}/kycs/${id}`, payload, { withCredentials: true });
      } else {
        res = await axios.post(`${API}/kycs`, payload, { withCredentials: true });
      }
      toast.success(`KYC ${id ? "updated" : "submitted"} successfully!`);
      navigate(`/clients/${res.data.id}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to submit KYC");
    } finally {
      setSubmitting(false);
    }
  };

  const StepIcon = STEPS[step - 1]?.icon;

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground font-['Outfit']">
          {id ? "Edit KYC" : "New KYC"} / {id ? "KYC संपादित करें" : "नया KYC"}
        </h1>
        <p className="text-muted-foreground text-sm mt-1">Step {step} of {STEPS.length}</p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-1 sm:gap-2 mb-8 overflow-x-auto pb-2" data-testid="step-indicator">
        {STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center flex-shrink-0">
            <button
              type="button"
              onClick={() => s.id < step && setStep(s.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition-all ${
                step === s.id
                  ? "bg-primary text-white"
                  : s.id < step
                  ? "bg-primary/20 text-primary cursor-pointer"
                  : "bg-muted text-muted-foreground cursor-not-allowed"
              }`}
              data-testid={`step-btn-${s.id}`}
            >
              <s.icon size={14} />
              <span className="hidden sm:inline">{s.title}</span>
              <span className="sm:hidden">{s.id}</span>
            </button>
            {i < STEPS.length - 1 && (
              <ChevronRight size={14} className="text-muted-foreground mx-0.5 flex-shrink-0" />
            )}
          </div>
        ))}
      </div>

      {/* Form Content */}
      <div className="bk-card mb-6">
        {step === 1 && (
          <PersonSection
            title="Primary Borrower"
            titleHi="प्राथमिक उधारकर्ता"
            data={formData.primaryBorrower}
            onChange={updatePerson("primaryBorrower")}
          />
        )}
        {step === 2 && (
          <PersonSection
            title="Co-borrower"
            titleHi="सह-उधारकर्ता"
            data={formData.coBorrower}
            onChange={updatePerson("coBorrower")}
          />
        )}
        {step === 3 && (
          <PersonSection
            title="Guarantor"
            titleHi="गारंटर"
            data={formData.guarantor}
            onChange={updatePerson("guarantor")}
          />
        )}
        {step === 4 && (
          <LivePhotoGPS
            livePhotoPath={formData.livePhotoPath}
            gpsLocation={formData.gpsLocation}
            onPhotoChange={(v) => setFormData((p) => ({ ...p, livePhotoPath: v }))}
            onGPSChange={(v) => setFormData((p) => ({ ...p, gpsLocation: v }))}
          />
        )}
        {step === 5 && <ReviewSection formData={formData} />}
      </div>

      {/* Notes (Step 5 only) */}
      {step === 5 && (
        <div className="bk-card mb-6">
          <label className="bk-label">
            <span className="bk-label-en">Notes (Optional)</span>
            <span className="bk-label-hi">टिप्पणियाँ (वैकल्पिक)</span>
          </label>
          <textarea
            value={formData.notes}
            onChange={(e) => setFormData((p) => ({ ...p, notes: e.target.value }))}
            className="bk-input h-auto py-3 resize-none w-full"
            rows={3}
            placeholder="Any additional notes..."
            data-testid="notes-input"
          />
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3">
        {step > 1 && (
          <button
            type="button"
            onClick={() => setStep((s) => s - 1)}
            className="bk-btn-secondary flex items-center justify-center gap-2 flex-1"
            data-testid="prev-step-btn"
          >
            <ChevronLeft size={18} /> Back / वापस
          </button>
        )}
        {step < STEPS.length ? (
          <button
            type="button"
            onClick={() => setStep((s) => s + 1)}
            className="bk-btn-primary flex items-center justify-center gap-2 flex-1"
            data-testid="next-step-btn"
          >
            Next / आगे <ChevronRight size={18} />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting}
            className="bk-btn-primary flex items-center justify-center gap-2 flex-1"
            data-testid="submit-kyc-btn"
          >
            {submitting ? (
              <><Loader2 size={18} className="animate-spin" /> Submitting...</>
            ) : (
              <><CheckCircle size={18} /> Submit KYC / जमा करें</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}
