import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { useAuth } from "./AuthContext";
import {
  ArrowLeft, Edit, CheckCircle, XCircle, Clock, MapPin, Camera,
  Phone, User, Shield, Users, FileText
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const StatusBadge = ({ status }) => {
  const map = {
    pending: "bk-badge-pending",
    approved: "bk-badge-approved",
    rejected: "bk-badge-rejected",
  };
  const labels = { pending: "Pending / लंबित", approved: "Approved / स्वीकृत", rejected: "Rejected / अस्वीकृत" };
  return <span className={map[status] || "bk-badge-pending"}>{labels[status] || status}</span>;
};

const SecureImage = ({ path, alt, className }) => {
  if (!path) return (
    <div className={`bg-muted flex items-center justify-center rounded-lg ${className || "w-full h-32"}`}>
      <FileText size={24} className="text-muted-foreground opacity-40" />
    </div>
  );
  return (
    <img
      src={`${API}/files/${path}`}
      alt={alt}
      className={`object-contain rounded-lg border border-border ${className || "w-full h-32"}`}
      onError={(e) => { e.target.style.display = "none"; }}
    />
  );
};

const PersonCard = ({ title, titleHi, data, icon: Icon }) => {
  if (!data || (!data.name && !data.phone)) return null;
  const docLabel = { voter_id: "Voter ID", pan: "PAN Card", ration_card: "Ration Card" };
  return (
    <div className="bk-card space-y-5">
      <div className="flex items-center gap-2 pb-3 border-b border-border">
        <div className="w-9 h-9 bg-primary/10 rounded-xl flex items-center justify-center">
          <Icon size={18} className="text-primary" />
        </div>
        <div>
          <h3 className="font-bold text-foreground font-['Outfit']">{title}</h3>
          <p className="text-xs text-muted-foreground">{titleHi}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-3">
          <InfoRow label="Full Name / नाम" value={data.name} />
          <InfoRow label="Phone / फ़ोन" value={data.phone} />
          <InfoRow label="Date of Birth / जन्म तिथि" value={data.dob} />
          <InfoRow label="Gender / लिंग" value={data.gender} />
          <InfoRow label="Husband's / Father's Name / पति-पिता" value={data.relative_name} />
          <InfoRow label="Aadhaar Number / आधार" value={data.aadhaar_number} />
          <InfoRow label="Address / पता" value={data.address} multiLine />
        </div>

        <div className="space-y-4">
          {data.aadhaar_front_path && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">Aadhaar Front</p>
              <SecureImage path={data.aadhaar_front_path} alt="Aadhaar Front" className="w-full h-36 object-contain" />
            </div>
          )}
          {data.aadhaar_back_path && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">Aadhaar Back</p>
              <SecureImage path={data.aadhaar_back_path} alt="Aadhaar Back" className="w-full h-36 object-contain" />
            </div>
          )}
          {data.document_type && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">
                {docLabel[data.document_type] || data.document_type} (Front)
              </p>
              <SecureImage path={data.document_front_path} alt="Doc Front" className="w-full h-36 object-contain" />
            </div>
          )}
          {data.document_back_path && (
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-2">
                {docLabel[data.document_type]} (Back)
              </p>
              <SecureImage path={data.document_back_path} alt="Doc Back" className="w-full h-36 object-contain" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const InfoRow = ({ label, value, multiLine }) => (
  <div>
    <p className="text-xs text-muted-foreground">{label}</p>
    <p className={`text-sm font-medium text-foreground ${multiLine ? "whitespace-pre-wrap" : "truncate"}`}>
      {value || "—"}
    </p>
  </div>
);

export default function ClientDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [kyc, setKyc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusLoading, setStatusLoading] = useState(false);
  const [notes, setNotes] = useState("");

  useEffect(() => {
    axios
      .get(`${API}/kycs/${id}`, { withCredentials: true })
      .then((r) => { setKyc(r.data); setNotes(r.data.notes || ""); })
      .catch(() => toast.error("Failed to load KYC"))
      .finally(() => setLoading(false));
  }, [id]);

  const updateStatus = async (status) => {
    setStatusLoading(true);
    try {
      const res = await axios.patch(
        `${API}/kycs/${id}/status`,
        { status, notes },
        { withCredentials: true }
      );
      setKyc(res.data);
      toast.success(`KYC ${status} successfully`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to update status");
    } finally {
      setStatusLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!kyc) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        <p>KYC not found</p>
        <button onClick={() => navigate("/clients")} className="mt-4 text-primary hover:underline">
          Back to Clients
        </button>
      </div>
    );
  }

  const canUpdateStatus = user?.role === "admin" || user?.role === "maalik" || user?.role === "muneem";

  return (
    <div className="p-4 sm:p-6 max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/clients")}
            className="p-2 rounded-lg hover:bg-muted transition-colors"
            data-testid="back-btn"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-foreground font-['Outfit']">
              {kyc.primary_borrower?.name || "KYC Detail"}
            </h1>
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-sm text-muted-foreground">{kyc.kyc_number}</span>
              <StatusBadge status={kyc.status} />
            </div>
          </div>
        </div>

        {(user?.role === "sipahi" || user?.role === "muneem") && (
          <button
            onClick={() => navigate(`/kyc/${id}/edit`)}
            className="flex items-center gap-2 bg-muted text-foreground px-4 py-2.5 rounded-lg text-sm font-semibold hover:bg-muted/80 border border-border transition-colors"
            data-testid="edit-kyc-btn"
          >
            <Edit size={16} /> Edit
          </button>
        )}
      </div>

      <div className="bk-card">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <InfoRow label="Field Agent / एजेंट" value={`${kyc.field_officer_name || "—"} (${kyc.field_officer_role || "—"})`} />
          <InfoRow label="Illaka / इलाका" value={kyc.illaka_name} />
          <InfoRow label="Misal / मिसाल" value={kyc.misal_name} />
          <InfoRow label="Created / बनाया" value={kyc.created_at ? new Date(kyc.created_at).toLocaleDateString("en-IN") : "—"} />
        </div>
        {kyc.loan_id && (
          <div className="mt-4 pt-4 border-t border-border">
            <button
              onClick={() => navigate(`/loans/${kyc.loan_id}`)}
              className="flex items-center gap-2 text-primary text-sm font-semibold hover:underline"
              data-testid="view-loan-btn"
            >
              View Loan / कर्ज देखें → ₹{kyc.disbursement_amount?.toLocaleString("en-IN") || ""}
            </button>
          </div>
        )}
      </div>

      {/* Person Cards */}
      <PersonCard
        title="Primary Borrower"
        titleHi="प्राथमिक उधारकर्ता"
        data={kyc.primary_borrower}
        icon={User}
      />
      <PersonCard
        title="Co-borrower"
        titleHi="सह-उधारकर्ता"
        data={kyc.co_borrower}
        icon={Users}
      />
      <PersonCard
        title="Guarantor"
        titleHi="गारंटर"
        data={kyc.guarantor}
        icon={Shield}
      />

      {/* Live Photo + GPS */}
      {(kyc.live_photo_path || kyc.gps_location) && (
        <div className="bk-card grid grid-cols-1 sm:grid-cols-2 gap-6">
          {kyc.live_photo_path && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <Camera size={16} className="text-primary" />
                <p className="font-semibold text-sm text-foreground">Live Photo</p>
              </div>
              <img
                src={`${API}/files/${kyc.live_photo_path}`}
                alt="Live Photo"
                className="w-32 h-32 rounded-full object-cover border-4 border-primary shadow-md mx-auto"
                data-testid="detail-live-photo"
              />
            </div>
          )}
          {kyc.gps_location && (user?.role === "admin" || user?.role === "maalik") && (
            <div>
              <div className="flex items-center gap-2 mb-3">
                <MapPin size={16} className="text-primary" />
                <p className="font-semibold text-sm text-foreground">GPS Location <span className="text-xs text-muted-foreground font-normal">(Admin/Maalik only)</span></p>
              </div>
              <div className="p-4 bg-green-50 rounded-xl border border-green-200 space-y-2" data-testid="detail-gps">
                <p className="text-sm text-foreground">Lat: {kyc.gps_location.latitude?.toFixed(6)}</p>
                <p className="text-sm text-foreground">Lng: {kyc.gps_location.longitude?.toFixed(6)}</p>
                {kyc.gps_location.accuracy && <p className="text-xs text-muted-foreground">±{kyc.gps_location.accuracy}m accuracy</p>}
                <a href={`https://www.google.com/maps?q=${kyc.gps_location.latitude},${kyc.gps_location.longitude}`} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline" data-testid="view-on-map-link">View on Google Maps →</a>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Notes */}
      {kyc.notes && (
        <div className="bk-card">
          <p className="text-xs font-semibold text-muted-foreground mb-2">Notes / टिप्पणियाँ</p>
          <p className="text-sm text-foreground">{kyc.notes}</p>
        </div>
      )}
    </div>
  );
}
