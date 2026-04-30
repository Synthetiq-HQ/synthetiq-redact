import { useEffect } from 'react';

export default function TranslationResult({ setScreen, docData }) {
  const translation = docData?.translation ?? {};
  const originalLang = docData?.language_detected ?? 'en';
  const translatedText = translation.translated_text ?? '';
  const translationConf = translation.confidence ?? 0;

  // Auto-skip if no translation needed
  useEffect(() => {
    const needsTranslation = originalLang && originalLang !== 'en' && docData?.translated;
    if (!needsTranslation) {
      const t = setTimeout(() => setScreen('routing'), 600);
      return () => clearTimeout(t);
    }
  }, [originalLang, docData?.translated, setScreen]);

  const isTranslated = originalLang && originalLang !== 'en' && docData?.translated;

  if (!isTranslated) {
    return (
      <div className="flex flex-col gap-4">
        <div className="council-card text-center">
          <div className="mb-2 text-3xl">🌐</div>
          <h2 className="mb-1 text-lg font-bold text-slate-800">No Translation Needed</h2>
          <p className="text-sm text-slate-500">Document is already in English. Skipping...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="council-card">
        <h2 className="mb-1 text-lg font-bold text-slate-800">Translation Result</h2>
        <p className="mb-4 text-sm text-slate-500">
          Document was translated from <strong>{originalLang.toUpperCase()}</strong> to English.
        </p>

        {/* Translation confidence */}
        <div className="mb-4 flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2 ring-1 ring-slate-200">
          <span className="text-xs text-slate-500">Translation Confidence</span>
          <span
            className={`text-sm font-bold ${
              translationConf >= 0.8 ? 'text-emerald-600' : translationConf >= 0.6 ? 'text-amber-600' : 'text-red-600'
            }`}
          >
            {(translationConf * 100).toFixed(1)}%
          </span>
        </div>

        {/* Translated text */}
        <div className="mb-4">
          <h3 className="mb-1.5 text-xs font-bold uppercase tracking-wide text-slate-400">
            Translated Text
          </h3>
          <div className="max-h-[40vh] overflow-y-auto rounded-lg bg-white p-3 text-sm leading-relaxed ring-1 ring-slate-200">
            {translatedText ? (
              <span className="text-slate-700">{translatedText}</span>
            ) : (
              <span className="italic text-slate-400">No translated text available.</span>
            )}
          </div>
        </div>

        <button
          onClick={() => setScreen('routing')}
          className="tap-target w-full rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-500 active:bg-blue-700"
        >
          Continue to Routing →
        </button>
      </div>
    </div>
  );
}
