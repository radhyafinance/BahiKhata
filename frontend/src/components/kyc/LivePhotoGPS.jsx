import { useState, useRef, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Camera, MapPin, Loader2, X, RefreshCw } from "lucide-react";
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
    try {
      const s = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } }
      });
      setStream(s);
      setCameraActive(true);
    } catch {
      try {
        const s = await navigator.mediaDevices.getUserMedia({ video: true });
        setStream(s);
        setCameraActive(true);
      } catch {
        toast.error("Camera not available. Use gallery upload instead.");
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
      pos => {
        onGPSChange({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: Math.round(pos.coords.accuracy), timestamp: new Date().toISOString() });
      },
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
        toast.success("Live photo saved! GPS location will be captured.");
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
    <div className="space-y-8">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <h3 className="text-lg font-bold font-['Outfit']">Live Photo</h3>
        <span className="text-sm text-muted-foreground">लाइव फोटो — GPS auto-captured</span>
      </div>

      <div className="space-y-3">
        <div>
          <p className="text-sm font-semibold">Live Client Photo<span className="text-destructive">*</span></p>
          <p className="text-xs text-muted-foreground">Back camera — GPS location captured automatically</p>
        </div>

        {cameraActive ? (
          <div className="space-y-3">
            <video ref={videoRef} autoPlay playsInline muted className="w-full max-w-sm mx-auto rounded-xl border-4 border-primary block" data-testid="camera-preview" />
            <div className="flex gap-3 max-w-sm mx-auto">
              <button type="button" onClick={capturePhoto} className="flex-1 bk-btn-primary flex items-center justify-center gap-2" data-testid="capture-photo-btn">
                <Camera size={18} /> Capture Photo
              </button>
              <button type="button" onClick={stopCamera} className="bk-btn-secondary px-4 w-14 flex items-center justify-center" data-testid="cancel-camera-btn">
                <X size={18} />
              </button>
            </div>
          </div>
        ) : livePhotoPath ? (
          <div className="flex flex-col items-center gap-3">
            <img src={`${API}/files/${livePhotoPath}`} alt="Live Photo" className="w-32 h-32 object-cover rounded-full border-4 border-primary shadow-md" data-testid="live-photo-preview" />
            {gpsLocation ? (
              <div className="flex items-center gap-2 text-green-700 text-sm">
                <MapPin size={14} /> GPS Captured
              </div>
            ) : (
              <div className="flex items-center gap-2 text-amber-600 text-xs">
                <MapPin size={13} /> GPS capturing...
              </div>
            )}
            <button type="button" onClick={() => { onPhotoChange(null); onGPSChange(null); }} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground" data-testid="retake-photo-btn">
              <RefreshCw size={13} /> Retake / फिर से
            </button>
          </div>
        ) : (
          <div className="border-2 border-dashed border-border rounded-xl py-8 px-4 flex flex-col items-center gap-4">
            {photoUploading ? (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 size={24} className="animate-spin text-primary" />
                <span className="text-sm">Uploading & capturing GPS...</span>
              </div>
            ) : (
              <>
                <Camera size={36} className="text-muted-foreground opacity-30" />
                <div className="flex gap-3">
                  <button type="button" onClick={startCamera} className="bk-btn-primary max-w-[200px] flex items-center justify-center gap-2 text-sm h-11" data-testid="start-camera-btn">
                    <Camera size={16} /> Open Camera (Back)
                  </button>
                </div>
                <p className="text-xs text-muted-foreground text-center">GPS location will be captured automatically when you take the photo</p>
              </>
            )}
          </div>
        )}
        <canvas ref={canvasRef} className="hidden" />
        <input ref={galleryRef} type="file" accept="image/*" onChange={handleGalleryPhoto} className="hidden" />
      </div>
    </div>
  );
}
