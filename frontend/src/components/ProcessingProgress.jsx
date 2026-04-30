import { useEffect, useRef } from 'react';
import { subscribeProgress, getDocument } from '../api';

const STEPS = [
  { key: 'uploaded',       label: 'Upload',     icon: '📤' },
  { key: 'preprocessing',  label: 'Clean',      icon: '🖼️' },
  { key: 'ocr',            label: 'Read Text',  icon: '🔍' },
  { key: 'redaction',      label: 'Redact',     icon: '🛡️' },
  { key: 'translation',    label: 'Translate',  icon: '🌐' },
  { key: 'classification', label: 'Classify',   icon: '🗂️' },
  { key: 'routing',        label: 'Route',      icon: '📬' },
  { key: 'complete',       label: 'Done',       icon: '✅' },
];

const STEP_INDEX = Object.fromEntries(STEPS.map((s, i) => [s.key, i]));

export default function ProcessingProgress({ setScreen, docId, setDocData, progress, setProgress }) {
  const unsubRef = useRef(null);

  useEffect(() => {
    if (!docId) return;
    setProgress({ status: 'uploaded', message: 'Connecting...', percent: 5 });

    unsubRef.current = subscribeProgress(docId, async data => {
      setProgress(data);
      if (data.status === 'complete' || data.status === 'needs_review') {
        setTimeout(async () => {
          try { setDocData(await getDocument(docId)); } catch {}
          setScreen('ocr');
        }, 800);
      }
    });
    return () => unsubRef.current?.();
  }, [docId]);

  const currentIdx = STEP_INDEX[progress.status] ?? 0;
  const pct = progress.percent ?? Math.round((currentIdx / (STEPS.length - 1)) * 100);
  const isError = progress.status === 'error';
  const isDone = progress.status === 'complete' || progress.status === 'needs_review';

  return (
    <div className="flex flex-col gap-6 py-4">
      {/* Title */}
      <div className="text-center">
        <div className="text-4xl mb-2">{isError ? '❌' : isDone ? '✅' : '⚙️'}</div>
        <h2 className="text-xl font-bold text-slate-800">
          {isError ? 'Processing Failed' : isDone ? 'Done!' : 'Processing Document'}
        </h2>
        <p className="text-sm text-slate-500 mt-1">
          {progress.message || 'Please wait...'}
        </p>
      </div>

      {/* Big progress bar */}
      <div>
        <div className="flex justify-between text-xs text-slate-500 mb-2">
          <span>{STEPS[currentIdx]?.icon} {STEPS[currentIdx]?.label}</span>
          <span className="font-bold text-slate-700">{pct}%</span>
        </div>
        <div className="h-3 w-full rounded-full bg-slate-100 overflow-hidden shadow-inner">
          <div
            className={`h-full rounded-full transition-all duration-500 ${
              isError ? 'bg-red-500' : isDone ? 'bg-emerald-500' : 'bg-blue-500'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Step pills */}
      <div className="flex gap-1.5 flex-wrap">
        {STEPS.map((step, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;
          return (
            <div key={step.key}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium transition-all ${
                done  ? 'bg-emerald-100 text-emerald-700' :
                active ? 'bg-blue-100 text-blue-700 ring-2 ring-blue-300' :
                         'bg-slate-100 text-slate-400'
              }`}>
              <span>{step.icon}</span>
              <span className="hidden sm:inline">{step.label}</span>
            </div>
          );
        })}
      </div>

      {/* Error message */}
      {isError && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Processing failed. Check the server logs for details.
          <button onClick={() => setScreen('scan')}
            className="block mt-3 w-full rounded-xl bg-red-600 text-white py-2.5 font-semibold text-sm">
            Try Again
          </button>
        </div>
      )}

      {!isError && !isDone && (
        <button onClick={() => { unsubRef.current?.(); setScreen('scan'); }}
          className="w-full py-3 rounded-xl bg-slate-200 text-slate-600 font-semibold text-sm hover:bg-slate-300">
          Cancel
        </button>
      )}
    </div>
  );
}
