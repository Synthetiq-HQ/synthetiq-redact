import { useMemo } from 'react';

function highlightConfidence(text, words) {
  if (!words || !Array.isArray(words) || words.length === 0) {
    return <span className="text-slate-700">{text}</span>;
  }

  // Sort words by position in text
  const sortedWords = [...words]
    .filter((w) => w && w.text)
    .sort((a, b) => (a.start || 0) - (b.start || 0));

  const elements = [];
  let lastIndex = 0;

  sortedWords.forEach((word, i) => {
    const start = word.start ?? text.indexOf(word.text, lastIndex);
    const end = word.end ?? start + word.text.length;
    if (start === -1) return;

    // Text before this word
    if (start > lastIndex) {
      elements.push(
        <span key={`gap-${i}`} className="text-slate-700">
          {text.slice(lastIndex, start)}
        </span>
      );
    }

    const conf = word.confidence ?? 0;
    const colorClass =
      conf >= 0.8 ? 'confidence-high' : conf >= 0.6 ? 'confidence-medium' : 'confidence-low';

    elements.push(
      <span key={`word-${i}`} className={colorClass} title={`Confidence: ${(conf * 100).toFixed(1)}%`}>
        {text.slice(start, end)}
      </span>
    );

    lastIndex = end;
  });

  if (lastIndex < text.length) {
    elements.push(
      <span key="tail" className="text-slate-700">
        {text.slice(lastIndex)}
      </span>
    );
  }

  return <>{elements}</>;
}

function renderRedactedText(text) {
  if (!text) return null;
  const parts = text.split(/(\[REDACTED-[A-Z_]+\])/g);
  return parts.map((part, i) => {
    if (part.startsWith('[REDACTED-')) {
      return (
        <mark
          key={i}
          className="rounded bg-red-100 px-1 py-0.5 text-red-700 font-semibold"
          title="Sensitive data redacted"
        >
          {part}
        </mark>
      );
    }
    return <span key={i} className="text-slate-700">{part}</span>;
  });
}

export default function OCRResult({ setScreen, docData }) {
  const ocr = docData?.ocr ?? {};
  const extractedText = ocr.extracted_text ?? '';
  const redactedText = ocr.redacted_text ?? '';
  const words = ocr.words ?? [];
  const avgConfidence = ocr.ocr_confidence ?? 0;

  const confidenceColor = useMemo(() => {
    if (avgConfidence >= 0.8) return 'text-emerald-600';
    if (avgConfidence >= 0.6) return 'text-amber-600';
    return 'text-red-600';
  }, [avgConfidence]);

  const confidenceBg = useMemo(() => {
    if (avgConfidence >= 0.8) return 'bg-emerald-50';
    if (avgConfidence >= 0.6) return 'bg-amber-50';
    return 'bg-red-50';
  }, [avgConfidence]);

  return (
    <div className="flex flex-col gap-4">
      <div className="council-card">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">OCR Result</h2>
          <div className={`flex items-center gap-2 rounded-lg px-3 py-1.5 ${confidenceBg}`}>
            <span className="text-xs text-slate-500">Avg Confidence</span>
            <span className={`text-sm font-bold ${confidenceColor}`}>
              {(avgConfidence * 100).toFixed(1)}%
            </span>
          </div>
        </div>

        {/* Extracted text */}
        <div className="mb-4">
          <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
            Extracted Text
          </h3>
          <div className="max-h-[40vh] overflow-y-auto rounded-lg bg-slate-50 p-3 text-sm leading-relaxed ring-1 ring-slate-200">
            {extractedText ? (
              highlightConfidence(extractedText, words)
            ) : (
              <span className="italic text-slate-400">No text extracted.</span>
            )}
          </div>
          <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" /> ≥80%
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-400" /> ≥60%
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-full bg-red-400" /> &lt;60%
            </span>
          </div>
        </div>

        {/* Redacted text */}
        <div className="mb-4">
          <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
            Redacted Text Preview
          </h3>
          <div className="max-h-[30vh] overflow-y-auto rounded-lg bg-white p-3 text-sm leading-relaxed ring-1 ring-slate-200">
            {redactedText ? (
              renderRedactedText(redactedText)
            ) : (
              <span className="italic text-slate-400">No redactions applied.</span>
            )}
          </div>
        </div>

        {/* Continue */}
        <button
          onClick={() => setScreen('redaction')}
          className="tap-target w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-500 active:bg-blue-700"
        >
          Continue to Redaction →
        </button>
      </div>
    </div>
  );
}
