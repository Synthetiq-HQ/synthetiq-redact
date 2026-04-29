import { useState } from 'react';
import { getImageUrl } from '../api';

export default function RedactionPreview({ setScreen, docId, docData }) {
  const [mode, setMode] = useState('preview'); // 'preview' | 'final'
  const redactions = docData?.redactions ?? [];

  const originalUrl = docId ? getImageUrl(docId, 'original') : null;
  const redactedUrl = docId ? getImageUrl(docId, 'redacted') : null;

  const handleContinue = () => {
    const needsTranslation = docData?.language_detected && docData.language_detected !== 'en';
    if (needsTranslation && docData?.translated) {
      setScreen('translation');
    } else {
      setScreen('routing');
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="council-card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">Redaction Preview</h2>
          <div className="flex rounded-lg bg-slate-100 p-0.5">
            <button
              onClick={() => setMode('preview')}
              className={`tap-target rounded-md px-3 py-1.5 text-xs font-semibold ${
                mode === 'preview'
                  ? 'bg-white text-slate-800 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Preview
            </button>
            <button
              onClick={() => setMode('final')}
              className={`tap-target rounded-md px-3 py-1.5 text-xs font-semibold ${
                mode === 'final'
                  ? 'bg-white text-slate-800 shadow-sm'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              Final
            </button>
          </div>
        </div>

        {/* Images */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:gap-4">
          {/* Original with overlay */}
          <div className="flex-1">
            <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
              Original with Markers
            </h3>
            <div className="relative overflow-hidden rounded-lg bg-slate-100 ring-1 ring-slate-200">
              {originalUrl ? (
                <>
                  <img
                    src={originalUrl}
                    alt="Original document"
                    className="w-full object-contain"
                    style={{ maxHeight: '40vh' }}
                  />
                  {mode === 'preview' &&
                    redactions.map((r, i) => {
                      const bbox = r.bbox || {};
                      const hasBbox =
                        bbox.x1 != null && bbox.y1 != null && bbox.x2 != null && bbox.y2 != null;
                      if (!hasBbox) return null;
                      // Assume bbox is in image coords; we can't map to CSS % without image size
                      // Display as overlay if bbox contains relative coords
                      const isRelative =
                        Math.max(bbox.x1, bbox.x2, bbox.y1, bbox.y2) <= 1;
                      const left = isRelative ? `${bbox.x1 * 100}%` : `${bbox.x1}px`;
                      const top = isRelative ? `${bbox.y1 * 100}%` : `${bbox.y1}px`;
                      const width = isRelative
                        ? `${(bbox.x2 - bbox.x1) * 100}%`
                        : `${bbox.x2 - bbox.x1}px`;
                      const height = isRelative
                        ? `${(bbox.y2 - bbox.y1) * 100}%`
                        : `${bbox.y2 - bbox.y1}px`;
                      return (
                        <div
                          key={i}
                          className="redaction-overlay pointer-events-none"
                          style={{ left, top, width, height }}
                          title={`${r.redaction_type} (conf: ${((r.confidence || 0) * 100).toFixed(0)}%)`}
                        />
                      );
                    })}
                </>
              ) : (
                <div className="flex h-32 items-center justify-center text-sm text-slate-400">
                  No original image available
                </div>
              )}
            </div>
          </div>

          {/* Redacted */}
          <div className="flex-1">
            <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
              Redacted Result
            </h3>
            <div className="overflow-hidden rounded-lg bg-slate-100 ring-1 ring-slate-200">
              {redactedUrl ? (
                <img
                  src={redactedUrl}
                  alt="Redacted document"
                  className="w-full object-contain"
                  style={{ maxHeight: '40vh' }}
                />
              ) : (
                <div className="flex h-32 items-center justify-center text-sm text-slate-400">
                  No redacted image available
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Redaction list */}
        {redactions.length > 0 && (
          <div className="mb-4">
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
              Detected Redactions ({redactions.length})
            </h3>
            <div className="flex flex-col gap-2">
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
    </div>
  );
}
