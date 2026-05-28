import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Camera, Loader2, X, RefreshCw } from "lucide-react";
import { API, compressImage } from "./utils";

export function LivePhotoGPS({ livePhotoPath, gpsLocation, onPhotoChange, onGPSChange }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [cameraActive, setCameraActive] = useState(false);
  const [photoUploading, setPhotoUploading] = useState(false);
  const galleryRef = useRef();

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
    if (!navigator.mediaDevices?.getUserMedia) {
      toast.info("In-browser camera not available. Using device camera instead.");
      galleryRef.current?.click();
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } }
      });
      setStream(s);
      setCameraActive(true);
    } catch (err1) {
      if (err1.name === "NotAllowedError" || err1.name === "PermissionDeniedError") {
        toast.error("Camera permission denied. Please allow camera access in your browser settings, then try again.");
        return;
      }
      if (err1.name === "NotFoundError" || err1.name === "DevicesNotFoundError") {
        toast.error("No camera found on this device. Please use the gallery option below.");
        return;
      }
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: true });
        setStream(s);
        setCameraActive(true);
      } catch (err2) {
        if (err2.name === "NotAllowedError" || err2.name === "PermissionDeniedError") {
          toast.error("Camera permission denied. Please allow camera access in your browser settings, then try again.");
        } else {
          toast.info("Opening device camera...");
          galleryRef.current?.click();
        }
      }
    }
  };

  const stopCamera = () => {
    stream?.getTracks().forEach(t => t.stop());
    setStream(null);
    setCameraActive(false);
  };

  const captureGpsBackground = () => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      pos => { onGPSChange({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: Math.round(pos.coords.accuracy), timestamp: new Date().toISOString() }); },
      () => {},
      { enableHighAccuracy: true, timeout: 15000 }
    );
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
    captureGpsBackground();
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
    captureGpsBackground();
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

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">Live Photo</h3>
        <span className="text-sm text-muted-foreground">लाइव फोटो</span>
      </div>

      <div className="space-y-3">
        <div>
          <p className="text-sm font-semibold">Client Photo <span className="text-destructive">*</span></p>
          <p className="text-xs text-muted-foreground">Take a clear photo of the client's face</p>
        </div>

        {cameraActive ? (
          <div className="flex flex-col items-center gap-3">
            {/* Round viewfinder — guides field agent to frame the face */}
            <div className="relative w-56 h-56 rounded-full overflow-hidden border-4 border-primary mx-auto shadow-lg">
              <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" data-testid="camera-preview" />
              {/* Face guide oval */}
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <div className="w-36 h-44 rounded-full border-2 border-white/50 border-dashed" />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Position client's face in the circle</p>
            <div className="flex gap-3">
              <button type="button" onClick={capturePhoto} className="bk-btn-primary flex items-center justify-center gap-2 px-6" data-testid="capture-photo-btn">
                <Camera size={18} /> Capture
              </button>
              <button type="button" onClick={stopCamera} className="bk-btn-secondary w-11 flex items-center justify-center" data-testid="cancel-camera-btn">
                <X size={18} />
              </button>
            </div>
          </div>
        ) : livePhotoPath ? (
          <div className="flex items-center gap-4">
            <img src={`${API}/files/${livePhotoPath}`} alt="Client Photo" className="w-20 h-20 object-cover rounded-full border-4 border-primary shadow-md shrink-0" data-testid="live-photo-preview" />
            <button type="button" onClick={() => { onPhotoChange(null); onGPSChange(null); }} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground" data-testid="retake-photo-btn">
              <RefreshCw size={13} /> Retake
            </button>
          </div>
        ) : (
          <div className="border-2 border-dashed border-border rounded-xl py-6 px-4 flex flex-col items-center gap-3">
            {photoUploading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 size={22} className="animate-spin text-primary" />
                <span className="text-sm">Uploading photo...</span>
              </div>
            ) : (
              <>
                <Camera size={32} className="text-muted-foreground opacity-30" />
                <div className="flex flex-col items-center gap-2 w-full max-w-[200px]">
                  <button type="button" onClick={startCamera} className="bk-btn-primary w-full flex items-center justify-center gap-2 text-sm h-10" data-testid="start-camera-btn">
                    <Camera size={15} /> Open Camera
                  </button>
                  <button type="button" onClick={() => galleryRef.current?.click()} className="bk-btn-secondary w-full flex items-center justify-center gap-2 text-sm h-9" data-testid="gallery-upload-btn">
                    Upload from Gallery
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        <canvas ref={canvasRef} className="hidden" />
        <input ref={galleryRef} type="file" accept="image/*" capture="environment" onChange={handleGalleryPhoto} className="hidden" />
      </div>
    </div>
  );
}

