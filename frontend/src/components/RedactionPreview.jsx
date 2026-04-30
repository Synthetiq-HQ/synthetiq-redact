import { useState, useRef, useEffect, useCallback } from 'react';
import { getImageUrl } from '../api';

export default function RedactionPreview({ setScreen, docId, docData }) {
  const redactions = docData?.redactions ?? [];
  const originalUrl = docId ? getImageUrl(docId, 'original') : null;
  const redactedUrl = docId ? getImageUrl(docId, 'redacted') : null;

  // Shared zoom/pan state
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [showRedactions, setShowRedactions] = useState(true);
  const [showLabels, setShowLabels] = useState(true);

  const leftRef = useRef(null);
  const rightRef = useRef(null);
  const containerRef = useRef(null);

  const handleWheel = useCallback((e) => {
    // Only zoom if Ctrl/Cmd is held OR if hovering directly over an image viewer
    const isOverViewer = leftRef.current?.contains(e.target) || rightRef.current?.contains(e.target);
    if (!isOverViewer && !e.ctrlKey && !e.metaKey) {
      return; // let normal scroll pass through
    }
    e.preventDefault();
    e.stopPropagation();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setScale((s) => Math.min(Math.max(s * delta, 0.2), 8));
  }, []);

  // Attach non-passive wheel listeners so preventDefault works
  useEffect(() => {
    const containers = [leftRef.current, rightRef.current].filter(Boolean);
    const opts = { passive: false };
    containers.forEach((el) => el.addEventListener('wheel', handleWheel, opts));
    return () => containers.forEach((el) => el.removeEventListener('wheel', handleWheel, opts));
  }, [handleWheel]);

  const startDrag = useCallback((e) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  }, [pan]);

  const doDrag = useCallback((e) => {
    if (!isDragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }, [isDragging, dragStart]);

  const endDrag = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener('mousemove', doDrag);
      window.addEventListener('mouseup', endDrag);
      return () => {
        window.removeEventListener('mousemove', doDrag);
        window.removeEventListener('mouseup', endDrag);
      };
    }
  }, [isDragging, doDrag, endDrag]);

  const resetView = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const fitToWidth = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
  };

  const zoomIn = () => setScale((s) => Math.min(s * 1.25, 8));
  const zoomOut = () => setScale((s) => Math.max(s / 1.25, 0.2));

  const transformStyle = {
    transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})`,
    transformOrigin: '0 0',
    transition: isDragging ? 'none' : 'transform 0.15s ease-out',
  };

  const handleContinue = () => {
    const needsTranslation = docData?.language_detected && docData.language_detected !== 'en';
    if (needsTranslation && docData?.translated) {
      setScreen('translation');
    } else {
      setScreen('routing');
    }
  };

  // Determine bbox format and compute CSS for overlays
  const renderOverlays = () => {
    return redactions.map((r, i) => {
      const bbox = r.bbox;
      if (!bbox) return null;

      let x, y, w, h;
      if (Array.isArray(bbox) && bbox.length === 4 && typeof bbox[0] === 'number') {
        // [x, y, w, h] format
        x = bbox[0];
        y = bbox[1];
        w = bbox[2];
        h = bbox[3];
      } else if (bbox.x != null && bbox.y != null && bbox.w != null) {
        x = bbox.x;
        y = bbox.y;
        w = bbox.w;
        h = bbox.h;
      } else if (bbox.x1 != null && bbox.y1 != null && bbox.x2 != null) {
        x = bbox.x1;
        y = bbox.y1;
        w = bbox.x2 - bbox.x1;
        h = bbox.y2 - bbox.y1;
      } else {
        return null;
      }

      const isRelative = Math.max(x + w, y + h) <= 1.01;
      const unit = isRelative ? '%' : 'px';
      const left = isRelative ? x * 100 : x;
      const top = isRelative ? y * 100 : y;
      const width = isRelative ? w * 100 : w;
      const height = isRelative ? h * 100 : h;

      return (
        <div
          key={i}
          className="absolute border-2 border-red-500/80 bg-red-500/10 pointer-events-none"
          style={{
            left: `${left}${unit}`,
            top: `${top}${unit}`,
            width: `${width}${unit}`,
            height: `${height}${unit}`,
          }}
          title={`${r.redaction_type} (${((r.confidence || 0) * 100).toFixed(0)}%)`}
        >
          {showLabels && (
            <span className="absolute -top-5 left-0 whitespace-nowrap rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
              {r.redaction_type}
            </span>
          )}
        </div>
      );
    });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Toolbar */}
      <div className="council-card">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-slate-800">Redaction Comparison</h2>
            <p className="text-xs text-slate-500">Scroll to zoom · Drag to pan · Both panels sync</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Zoom controls */}
            <div className="flex items-center rounded-lg bg-slate-100 ring-1 ring-slate-200">
              <button onClick={zoomOut} className="tap-target px-3 py-1.5 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-l-lg">−</button>
              <span className="px-2 text-xs font-mono font-semibold text-slate-700 min-w-[3.5rem] text-center">{Math.round(scale * 100)}%</span>
              <button onClick={zoomIn} className="tap-target px-3 py-1.5 text-sm font-bold text-slate-600 hover:bg-slate-200 rounded-r-lg">+</button>
            </div>

            <button onClick={resetView} className="tap-target rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 ring-1 ring-slate-200">
              Reset
            </button>

            <button onClick={fitToWidth} className="tap-target rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-200 ring-1 ring-slate-200">
              Fit
            </button>

            <label className="flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showRedactions}
                onChange={(e) => setShowRedactions(e.target.checked)}
                className="h-3.5 w-3.5 accent-red-500"
              />
              Boxes
            </label>

            <label className="flex items-center gap-1.5 rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600 ring-1 ring-slate-200 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showLabels}
                onChange={(e) => setShowLabels(e.target.checked)}
                className="h-3.5 w-3.5 accent-red-500"
              />
              Labels
            </label>
          </div>
        </div>
      </div>

      {/* Side-by-side viewers */}
      <div ref={containerRef} className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* Original */}
        <div className="council-card flex flex-col">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
            Original Document
          </h3>
          <div
            ref={leftRef}
            className="relative flex-1 overflow-hidden rounded-lg bg-slate-900 ring-1 ring-slate-800 cursor-grab active:cursor-grabbing"
            style={{ minHeight: '50vh', touchAction: 'none' }}
            onMouseDown={startDrag}
          >
            {originalUrl ? (
              <div style={transformStyle} className="absolute top-0 left-0 origin-top-left">
                <img
                  src={originalUrl}
                  alt="Original document"
                  className="block max-w-none"
                  draggable={false}
                />
                {showRedactions && (
                  <div className="absolute inset-0">
                    {renderOverlays()}
                  </div>
                )}
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">
                No original image available
              </div>
            )}
          </div>
        </div>

        {/* Redacted */}
        <div className="council-card flex flex-col">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
            Redacted Result
          </h3>
          <div
            ref={rightRef}
            className="relative flex-1 overflow-hidden rounded-lg bg-slate-900 ring-1 ring-slate-800 cursor-grab active:cursor-grabbing"
            style={{ minHeight: '50vh', touchAction: 'none' }}
            onMouseDown={startDrag}
          >
            {redactedUrl ? (
              <div style={transformStyle} className="absolute top-0 left-0 origin-top-left">
                <img
                  src={redactedUrl}
                  alt="Redacted document"
                  className="block max-w-none"
                  draggable={false}
                />
              </div>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-slate-500">
                No redacted image available
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Redaction list */}
      {redactions.length > 0 && (
        <div className="council-card">
          <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
            Detected Redactions ({redactions.length})
          </h3>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {redactions.map((r, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-200"
              >
                <div className="flex flex-col">
                  <span className="text-xs font-semibold capitalize text-slate-700">
                    {r.redaction_type}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    {r.original_value
                      ? `Value: ${'*'.repeat(Math.min(r.original_value.length, 12))}`
                      : 'Value hidden'}
                  </span>
                </div>
                <span
                  className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                    (r.confidence || 0) >= 0.8
                      ? 'bg-emerald-100 text-emerald-700'
                      : (r.confidence || 0) >= 0.6
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-red-100 text-red-700'
                  }`}
                >
                  {((r.confidence || 0) * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <button
        onClick={handleContinue}
        className="tap-target w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-500 active:bg-blue-700"
      >
        Continue →
      </button>
    </div>
  );
}
