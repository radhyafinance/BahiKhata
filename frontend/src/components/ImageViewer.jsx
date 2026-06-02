import { useState, useEffect, useRef, useCallback } from "react";
import { X, ZoomIn, ZoomOut, RotateCcw, RotateCw, ChevronLeft, ChevronRight, Maximize2 } from "lucide-react";

/**
 * Full-screen image viewer modal.
 * Props:
 *   images       — array of { src: string, label: string }
 *   initialIndex — index of image to open first
 *   onClose      — callback to close the modal
 */
export default function ImageViewer({ images, initialIndex = 0, onClose }) {
  const [index, setIndex] = useState(initialIndex);
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const lastPinchDist = useRef(null);

  const current = images[index] || images[0];
  const count = images.length;

  const resetTransform = useCallback(() => { setZoom(1); setRotation(0); }, []);
  const goTo = useCallback((i) => { setIndex(i); setZoom(1); setRotation(0); }, []);
  const prev = useCallback(() => goTo((index - 1 + count) % count), [index, count, goTo]);
  const next = useCallback(() => goTo((index + 1) % count), [index, count, goTo]);
  const rotateLeft  = () => setRotation(r => r - 90);
  const rotateRight = () => setRotation(r => r + 90);
  const zoomIn  = useCallback(() => setZoom(z => Math.min(5, +(z + 0.25).toFixed(2))), []);
  const zoomOut = useCallback(() => setZoom(z => Math.max(0.25, +(z - 0.25).toFixed(2))), []);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape")      { onClose(); }
      else if (e.key === "ArrowLeft")  { prev(); }
      else if (e.key === "ArrowRight") { next(); }
      else if (e.key === "+" || e.key === "=") { zoomIn(); }
      else if (e.key === "-")          { zoomOut(); }
      else if (e.key === "r" || e.key === "R") { rotateRight(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prev, next, zoomIn, zoomOut, onClose]);

  // Scroll-to-zoom
  const onWheel = (e) => {
    e.preventDefault();
    if (e.deltaY < 0) zoomIn();
    else zoomOut();
  };

  // Pinch-to-zoom (touch)
  const pinchDist = (touches) => {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };
  const onTouchStart = (e) => {
    if (e.touches.length === 2) lastPinchDist.current = pinchDist(e.touches);
  };
  const onTouchMove = (e) => {
    if (e.touches.length === 2 && lastPinchDist.current !== null) {
      const d = pinchDist(e.touches);
      const delta = d - lastPinchDist.current;
      lastPinchDist.current = d;
      setZoom(z => Math.max(0.25, Math.min(5, +(z + delta * 0.008).toFixed(2))));
    }
  };
  const onTouchEnd = () => { lastPinchDist.current = null; };

  return (
    <div
      className="fixed inset-0 z-[100] bg-black flex flex-col"
      data-testid="image-viewer-modal"
      // Prevent body scroll while open
      style={{ touchAction: "none" }}
    >
      {/* ── Header ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 bg-black/80 shrink-0">
        <div className="min-w-0">
          <p className="text-white font-semibold text-sm truncate">{current?.label}</p>
          <p className="text-white/50 text-xs">{index + 1} / {count}</p>
        </div>
        <button
          onClick={onClose}
          className="text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors shrink-0 ml-3"
          data-testid="viewer-close-btn"
        >
          <X size={22} />
        </button>
      </div>

      {/* ── Image area ──────────────────────────────────────── */}
      <div
        className="flex-1 flex items-center justify-center overflow-hidden relative cursor-zoom-in"
        onWheel={onWheel}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        data-testid="viewer-image-area"
      >
        {count > 1 && (
          <button
            onClick={prev}
            className="absolute left-2 z-10 text-white/70 hover:text-white bg-black/50 hover:bg-black/70 rounded-full p-2.5 transition-colors"
            data-testid="viewer-prev-btn"
          >
            <ChevronLeft size={26} />
          </button>
        )}

        <img
          key={current?.src}
          src={current?.src}
          alt={current?.label}
          draggable={false}
          className="max-w-full max-h-full object-contain select-none"
          style={{
            transform: `rotate(${rotation}deg) scale(${zoom})`,
            transition: "transform 0.15s ease",
          }}
          data-testid="viewer-image"
        />

        {count > 1 && (
          <button
            onClick={next}
            className="absolute right-2 z-10 text-white/70 hover:text-white bg-black/50 hover:bg-black/70 rounded-full p-2.5 transition-colors"
            data-testid="viewer-next-btn"
          >
            <ChevronRight size={26} />
          </button>
        )}
      </div>

      {/* ── Thumbnail strip (if multiple images) ────────────── */}
      {count > 1 && (
        <div className="flex items-center gap-2 px-4 py-2 bg-black/70 overflow-x-auto shrink-0">
          {images.map((img, i) => (
            <button
              key={img.src}
              onClick={() => goTo(i)}
              className={`shrink-0 w-12 h-12 rounded-lg overflow-hidden border-2 transition-colors ${
                i === index ? "border-white" : "border-white/20 opacity-50 hover:opacity-80"
              }`}
              data-testid={`viewer-thumb-${i}`}
            >
              <img src={img.src} alt={img.label} className="w-full h-full object-cover" draggable={false} />
            </button>
          ))}
        </div>
      )}

      {/* ── Controls bar ────────────────────────────────────── */}
      <div className="flex items-center justify-center gap-1 px-4 py-3 bg-black/80 shrink-0">
        <ControlBtn onClick={rotateLeft}  title="Rotate Left (R)" testId="viewer-rotate-left">
          <RotateCcw size={19} />
        </ControlBtn>
        <ControlBtn onClick={zoomOut} title="Zoom Out (−)" testId="viewer-zoom-out">
          <ZoomOut size={19} />
        </ControlBtn>
        <button
          onClick={resetTransform}
          className="text-white/60 hover:text-white px-3 py-1.5 rounded-full hover:bg-white/10 transition-colors text-sm tabular-nums min-w-[56px] text-center"
          title="Reset (click to reset)"
          data-testid="viewer-zoom-level"
        >
          {Math.round(zoom * 100)}%
        </button>
        <ControlBtn onClick={zoomIn}  title="Zoom In (+)" testId="viewer-zoom-in">
          <ZoomIn size={19} />
        </ControlBtn>
        <ControlBtn onClick={rotateRight} title="Rotate Right" testId="viewer-rotate-right">
          <RotateCw size={19} />
        </ControlBtn>
        {count > 1 && (
          <>
            <div className="w-px h-5 bg-white/20 mx-1" />
            <ControlBtn onClick={prev} title="Previous" testId="viewer-ctrl-prev">
              <ChevronLeft size={19} />
            </ControlBtn>
            <ControlBtn onClick={next} title="Next" testId="viewer-ctrl-next">
              <ChevronRight size={19} />
            </ControlBtn>
          </>
        )}
      </div>
    </div>
  );
}

function ControlBtn({ onClick, title, testId, children }) {
  return (
    <button
      onClick={onClick}
      title={title}
      data-testid={testId}
      className="text-white/70 hover:text-white p-2.5 rounded-full hover:bg-white/10 transition-colors"
    >
      {children}
    </button>
  );
}
