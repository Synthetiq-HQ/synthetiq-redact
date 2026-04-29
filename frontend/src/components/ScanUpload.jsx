import { useState, useRef, useCallback } from 'react';
import { uploadDocument } from '../api';

export default function ScanUpload({ setScreen, setDocId, setDocData, setProgress }) {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [translateEnabled, setTranslateEnabled] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('');
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const startCamera = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraActive(true);
      setTimeout(() => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      }, 100);
    } catch {
      setError('Camera unavailable — use file upload instead.');
    }
  }, []);

  const stopCamera = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraActive(false);
  }, []);

  const capturePhoto = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) {
      setError('Camera not ready — wait a moment.');
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      if (!blob) return;
      const f = new File([blob], `capture_${Date.now()}.jpg`, { type: 'image/jpeg' });
      setFile(f);
      setPreviewUrl(URL.createObjectURL(f));
      stopCamera();
    }, 'image/jpeg', 0.92);
  }, [stopCamera]);

  const handleFileSelect = useCallback(e => {
    const f = e.target.files?.[0];
    if (!f) return;
    setError(null);
    setFile(f);
    setPreviewUrl(URL.createObjectURL(f));
  }, []);

  const handleUpload = useCallback(async () => {
    if (!file) return;
    setIsUploading(true);
    setError(null);
    setProgress({ status: 'uploaded', message: 'Uploading...', percent: 5 });
    try {
      const result = await uploadDocument(file, translateEnabled, selectedCategory);
      if (result?.document_id) {
        setDocId(result.document_id);
        setScreen('progress');
      } else {
        throw new Error('Invalid server response');
      }
    } catch (err) {
      setError(err.message || 'Upload failed.');
      setIsUploading(false);
    }
  }, [file, setDocId, setScreen, setProgress]);

  return (
    <div className="flex flex-col gap-6 py-4">
      {/* Header */}
      <div className="text-center">
        <div className="text-4xl mb-2">📄</div>
        <h2 className="text-xl font-bold text-slate-800">Scan Document</h2>
        <p className="text-sm text-slate-500 mt-1">Upload or photograph a council document to process</p>
      </div>

      {/* Camera view */}
      {cameraActive && (
        <div className="relative overflow-hidden rounded-2xl bg-black shadow-xl">
          <video ref={videoRef} autoPlay playsInline muted className="w-full max-h-[55vh] object-cover" />
          <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent p-4 flex justify-center gap-4">
            <button onClick={capturePhoto}
              className="h-16 w-16 rounded-full bg-white shadow-lg flex items-center justify-center text-2xl ring-4 ring-emerald-400 active:scale-95 transition-transform">
              📷
            </button>
            <button onClick={stopCamera}
              className="h-12 w-12 rounded-full bg-red-500 flex items-center justify-center text-white text-lg shadow-lg active:scale-95 transition-transform self-end">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Preview */}
      {previewUrl && !cameraActive && (
        <div className="relative rounded-2xl overflow-hidden shadow-lg border border-slate-200">
          <img src={previewUrl} alt="Preview" className="w-full max-h-[50vh] object-contain bg-slate-100" />
          <button onClick={() => { setFile(null); setPreviewUrl(null); setError(null); }}
            className="absolute top-3 right-3 bg-red-500 text-white text-xs px-3 py-1 rounded-full shadow hover:bg-red-600">
            Remove
          </button>
        </div>
      )}

      {/* Upload controls */}
      {!cameraActive && !previewUrl && (
        <div className="grid grid-cols-2 gap-3">
          {/* Mobile: native capture */}
          <label className="sm:hidden flex flex-col items-center justify-center gap-2 rounded-2xl bg-slate-800 text-white p-5 text-sm font-semibold cursor-pointer active:bg-slate-700 shadow-md">
            <span className="text-3xl">📷</span>
            Take Photo
            <input type="file" accept="image/*" capture="environment" onChange={handleFileSelect} className="sr-only" />
          </label>
          {/* Desktop: getUserMedia */}
          <button onClick={startCamera}
            className="hidden sm:flex flex-col items-center justify-center gap-2 rounded-2xl bg-slate-800 text-white p-5 text-sm font-semibold active:bg-slate-700 shadow-md">
            <span className="text-3xl">📷</span>
            Use Camera
          </button>
          <label className="flex flex-col items-center justify-center gap-2 rounded-2xl bg-white text-slate-700 p-5 text-sm font-semibold cursor-pointer ring-2 ring-slate-200 hover:ring-emerald-400 shadow-md transition-all">
            <span className="text-3xl">📁</span>
            Upload File
            <input type="file" accept="image/*,.pdf" onChange={handleFileSelect} className="sr-only" />
          </label>
        </div>
      )}

      {/* Process button */}
      {previewUrl && !cameraActive && (
        <button onClick={handleUpload} disabled={isUploading}
          className="w-full py-4 rounded-2xl bg-emerald-600 text-white font-bold text-base flex items-center justify-center gap-3 shadow-lg hover:bg-emerald-500 active:bg-emerald-700 disabled:opacity-60 transition-colors">
          {isUploading
            ? <><span className="h-5 w-5 rounded-full border-2 border-white border-t-transparent animate-spin" />Processing...</>
            : <><span className="text-xl">⚡</span>Process Document</>}
        </button>
      )}

      {/* Category selector + translation toggle */}
      {!cameraActive && (
        <div className="flex flex-col gap-2">
          <div className="rounded-xl bg-white border border-slate-200 px-4 py-2.5">
            <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-1">Document Category</div>
            <select
              value={selectedCategory}
              onChange={e => setSelectedCategory(e.target.value)}
              className="w-full text-sm text-slate-700 bg-transparent outline-none"
            >
              <option value="">Auto-detect</option>
              <option value="housing_repairs">Housing Repairs</option>
              <option value="council_tax">Council Tax</option>
              <option value="parking">Parking</option>
              <option value="complaint">Complaint</option>
              <option value="waste">Waste / Environment</option>
              <option value="adult_social_care">Adult Social Care</option>
              <option value="children_safeguarding">Children Safeguarding</option>
              <option value="foi_legal">FOI / Legal</option>
            </select>
          </div>
          <label className="flex items-center gap-3 rounded-xl bg-white border border-slate-200 px-4 py-3 cursor-pointer select-none">
            <div className={`relative w-10 h-5 rounded-full transition-colors ${translateEnabled ? 'bg-emerald-500' : 'bg-slate-300'}`}>
              <div className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${translateEnabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </div>
            <input type="checkbox" className="sr-only" checked={translateEnabled} onChange={e => setTranslateEnabled(e.target.checked)} />
            <span className="text-sm text-slate-700 font-medium">Translate to English <span className="text-slate-400 font-normal">(if non-English detected)</span></span>
          </label>
        </div>
      )}

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Demo badge */}
      <div className="text-center text-xs text-slate-400 border-t border-slate-100 pt-3">
        🔒 Synthetic demo data only · Hillingdon Council × Brunel University
      </div>

      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
}
