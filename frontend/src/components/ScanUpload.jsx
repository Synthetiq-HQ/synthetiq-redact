import { useState, useRef, useCallback } from 'react';
import { uploadDocument } from '../api';

const ACCEPTED_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.pdf', '.gif', '.bmp', '.tiff', '.tif'];
const ACCEPTED_INPUT = 'image/png,image/jpeg,image/gif,image/bmp,image/tiff,application/pdf,.png,.jpg,.jpeg,.pdf,.gif,.bmp,.tiff,.tif';

export default function ScanUpload({ setScreen, setDocId, setDocData, setProgress }) {
  const [previewUrl, setPreviewUrl] = useState(null);
  const [file, setFile] = useState(null);
  const [error, setError] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [cameraActive, setCameraActive] = useState(false);
  const [translateEnabled, setTranslateEnabled] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('');
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const fileInputRef = useRef(null);

  const resetSelectedFile = useCallback(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(null);
    setPreviewUrl(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, [previewUrl]);

  const selectFile = useCallback((nextFile) => {
    if (!nextFile) return;
    const lowerName = nextFile.name.toLowerCase();
    const allowed = ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!allowed) {
      setError('Upload a PNG, JPG, TIFF, GIF, BMP, or PDF file.');
      return;
    }

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setError(null);
    setFile(nextFile);
    if (nextFile.type.startsWith('image/')) {
      setPreviewUrl(URL.createObjectURL(nextFile));
    } else {
      setPreviewUrl(null);
    }
  }, [previewUrl]);

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
      selectFile(f);
      stopCamera();
    }, 'image/jpeg', 0.92);
  }, [selectFile, stopCamera]);

  const handleFileSelect = useCallback(e => {
    const f = e.target.files?.[0];
    if (!f) return;
    selectFile(f);
  }, [selectFile]);

  const handleDragOver = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.currentTarget.contains(event.relatedTarget)) return;
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    selectFile(dropped);
  }, [selectFile]);

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
  }, [file, translateEnabled, selectedCategory, setDocId, setScreen, setProgress]);

  return (
    <div className="flex flex-col gap-6 py-4">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-slate-900">New document</h2>
        <p className="mt-1 text-sm text-slate-500">Upload a scanned image or PDF for local redaction review.</p>
      </div>

      {/* Camera view */}
      {cameraActive && (
        <div className="relative overflow-hidden rounded-2xl bg-black shadow-xl">
          <video ref={videoRef} autoPlay playsInline muted className="w-full max-h-[55vh] object-cover" />
          <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/70 to-transparent p-4 flex justify-center gap-4">
            <button onClick={capturePhoto}
              className="h-16 w-16 rounded-full bg-white shadow-lg flex items-center justify-center text-sm font-bold text-slate-900 ring-4 ring-emerald-400 active:scale-95 transition-transform">
              Capture
            </button>
            <button onClick={stopCamera}
              className="h-12 w-12 rounded-full bg-red-500 flex items-center justify-center text-white text-lg shadow-lg active:scale-95 transition-transform self-end">
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Preview / selected file */}
      {file && !cameraActive && (
        <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          {previewUrl ? (
            <img src={previewUrl} alt="Selected document preview" className="w-full max-h-[50vh] object-contain bg-slate-100" />
          ) : (
            <div className="flex min-h-48 flex-col items-center justify-center gap-2 bg-slate-50 p-6 text-center">
              <div className="rounded border border-slate-300 bg-white px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                PDF
              </div>
              <div className="max-w-full truncate text-sm font-semibold text-slate-800">{file.name}</div>
              <div className="text-xs text-slate-500">PDF processing renders up to 50 pages and sends issues to human review.</div>
            </div>
          )}
          <button onClick={resetSelectedFile}
            className="absolute right-3 top-3 rounded-md bg-white px-3 py-1 text-xs font-semibold text-slate-700 shadow ring-1 ring-slate-200 hover:bg-slate-50">
            Remove
          </button>
        </div>
      )}

      {/* Upload controls */}
      {!cameraActive && !file && (
        <div className="space-y-3">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`flex min-h-64 w-full flex-col items-center justify-center rounded-lg border-2 border-dashed bg-white px-6 py-10 text-center transition-colors ${
              isDragging ? 'border-emerald-500 bg-emerald-50' : 'border-slate-300 hover:border-slate-400 hover:bg-slate-50'
            }`}
          >
            <span className="text-base font-semibold text-slate-900">Drop a file here or click to choose</span>
            <span className="mt-2 text-sm text-slate-500">PNG, JPG, TIFF, GIF, BMP, or PDF</span>
            <span className="mt-4 rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white">Choose file</span>
          </button>
          <input ref={fileInputRef} type="file" accept={ACCEPTED_INPUT} onChange={handleFileSelect} className="sr-only" />

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label className="sm:hidden flex items-center justify-center rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 shadow-sm">
              Take photo
              <input type="file" accept="image/*" capture="environment" onChange={handleFileSelect} className="sr-only" />
            </label>
            <button onClick={startCamera}
              className="hidden rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 sm:block">
              Use camera
            </button>
          </div>
        </div>
      )}

      {/* Process button */}
      {file && !cameraActive && (
        <button onClick={handleUpload} disabled={isUploading}
          className="flex w-full items-center justify-center gap-3 rounded-lg bg-emerald-700 py-4 text-base font-bold text-white shadow-sm transition-colors hover:bg-emerald-600 active:bg-emerald-800 disabled:opacity-60">
          {isUploading
            ? <><span className="h-5 w-5 rounded-full border-2 border-white border-t-transparent animate-spin" />Processing...</>
            : <>Process document</>}
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
            <span className="text-sm text-slate-700 font-medium">Non-English translation <span className="text-slate-400 font-normal">(off by default)</span></span>
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
        Synthetic demo data only · local processing workspace
      </div>

      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
}
