const CATEGORY_LABELS = {
  housing_repairs: { label: 'Housing & Repairs', icon: '🏠', color: 'bg-teal-100 text-teal-800 border-teal-200' },
  council_tax: { label: 'Council Tax', icon: '💷', color: 'bg-blue-100 text-blue-800 border-blue-200' },
  parking: { label: 'Parking', icon: '🚗', color: 'bg-indigo-100 text-indigo-800 border-indigo-200' },
  complaint: { label: 'Complaint', icon: '📢', color: 'bg-rose-100 text-rose-800 border-rose-200' },
  waste: { label: 'Waste & Environment', icon: '♻️', color: 'bg-green-100 text-green-800 border-green-200' },
  adult_social_care: { label: 'Adult Social Care', icon: '🧑‍🤝‍🧑', color: 'bg-violet-100 text-violet-800 border-violet-200' },
  children_safeguarding: { label: "Children's Safeguarding", icon: '🛡️', color: 'bg-red-100 text-red-800 border-red-200' },
  foi_legal: { label: 'FOI / Legal', icon: '⚖️', color: 'bg-slate-100 text-slate-800 border-slate-200' },
  translation: { label: 'Translation', icon: '🌐', color: 'bg-cyan-100 text-cyan-800 border-cyan-200' },
  unknown: { label: 'Unknown', icon: '❓', color: 'bg-gray-100 text-gray-700 border-gray-200' },
};

const SENTIMENT_STYLE = {
  positive:   { label: 'Positive',   color: 'bg-emerald-100 text-emerald-800' },
  neutral:    { label: 'Neutral',    color: 'bg-slate-100 text-slate-700' },
  negative:   { label: 'Negative',   color: 'bg-amber-100 text-amber-800' },
  angry:      { label: 'Angry',      color: 'bg-red-100 text-red-800' },
  distressed: { label: 'Distressed', color: 'bg-red-200 text-red-900' },
};

export default function RoutingUrgency({ setScreen, docData }) {
  const category = docData?.category ?? 'unknown';
  const department = docData?.department ?? 'General Enquiries';
  const urgency = docData?.urgency_score ?? 0;
  const sentiment = docData?.sentiment ?? 'neutral';
  const confidence = docData?.confidence_score ?? 0;
  const riskFlags = docData?.risk_flags ?? [];
  const needsReview = docData?.flag_needs_review;

  const pct = Math.round(urgency * 100);
  const urgencyBar = pct < 40 ? 'bg-emerald-500' : pct < 70 ? 'bg-amber-500' : 'bg-red-500';
  const urgencyLabel = pct < 40 ? '🟢 Low Priority' : pct < 70 ? '🟡 Standard Priority' : '🔴 High Priority';

  const cat = CATEGORY_LABELS[category] ?? CATEGORY_LABELS.unknown;
  const sent = SENTIMENT_STYLE[sentiment] ?? SENTIMENT_STYLE.neutral;

  return (
    <div className="flex flex-col gap-4 py-4">
      {/* Category hero */}
      <div className={`rounded-2xl border-2 p-5 text-center ${cat.color}`}>
        <div className="text-4xl mb-1">{cat.icon}</div>
        <div className="text-lg font-bold">{cat.label}</div>
        <div className="text-xs mt-1 opacity-70 uppercase tracking-wide">Document Category</div>
      </div>

      {/* Department */}
      <div className="rounded-2xl bg-blue-50 border border-blue-100 px-5 py-4">
        <div className="text-xs font-bold uppercase tracking-wide text-blue-400 mb-1">📬 Route To</div>
        <div className="text-base font-bold text-blue-800">{department}</div>
        <div className="text-xs text-blue-500 mt-0.5">AI confidence: {Math.round(confidence * 100)}%</div>
      </div>

      {/* Urgency bar */}
      <div className="rounded-2xl bg-slate-50 border border-slate-200 px-5 py-4">
        <div className="flex justify-between items-center mb-2">
          <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Urgency</span>
          <span className="text-sm font-bold text-slate-700">{urgencyLabel}</span>
        </div>
        <div className="h-3 w-full rounded-full bg-slate-200 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${urgencyBar}`} style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* Risk flags */}
      {riskFlags.length > 0 && (
        <div className="rounded-2xl bg-red-50 border border-red-200 px-5 py-4">
          <div className="text-xs font-bold uppercase tracking-wide text-red-500 mb-2">⚠️ Risk Flags</div>
          <div className="flex flex-wrap gap-2">
            {riskFlags.map((f, i) => (
              <span key={i} className="rounded-full bg-red-100 border border-red-200 px-3 py-1 text-xs font-semibold text-red-700 capitalize">
                {f.replace(/_/g, ' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Sentiment + review warning */}
      <div className="flex gap-3">
        <div className="flex-1 rounded-xl bg-slate-50 border border-slate-200 p-3 text-center">
          <div className="text-xs text-slate-400 mb-1">Sentiment</div>
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${sent.color}`}>{sent.label}</span>
        </div>
        {needsReview && (
          <div className="flex-1 rounded-xl bg-amber-50 border border-amber-200 p-3 text-center">
            <div className="text-xs text-amber-600 font-bold">⚠️ Needs Review</div>
            <div className="text-xs text-amber-500 mt-0.5">Low confidence</div>
          </div>
        )}
      </div>

      <button onClick={() => setScreen('final')}
        className="w-full py-4 rounded-2xl bg-blue-600 text-white font-bold text-base shadow-lg hover:bg-blue-500 active:bg-blue-700">
        Final Review →
      </button>
    </div>
  );
}
