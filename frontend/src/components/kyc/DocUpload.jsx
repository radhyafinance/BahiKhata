import { useState, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Camera, Loader2, X, ImageIcon } from "lucide-react";
import { API, compressImage } from "./utils";

export function DocUpload({ label, labelHi, value, onChange, required, testId }) {
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
