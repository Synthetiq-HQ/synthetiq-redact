import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../api';

export default function ReviewQueue({ setScreen, setDocId }) {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [stats, setStats] = useState({ urgent: 0, high: 0, normal: 0 });
  const navigate = useNavigate();

  useEffect(() => {
    loadQueue();
    const interval = setInterval(loadQueue, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [filter]);

  const loadQueue = async () => {
    try {
      const res = await api.get(`/review-queue?priority=${filter}&limit=50`);
      setDocuments(res.data.documents || []);
      setStats({
        urgent: res.data.documents?.filter(d => d.urgency_score >= 0.8).length || 0,
        high: res.data.documents?.filter(d => d.urgency_score >= 0.5 && d.urgency_score < 0.8).length || 0,
        normal: res.data.documents?.filter(d => d.urgency_score < 0.5).length || 0,
      });
      setLoading(false);
    } catch (err) {
      console.error('Failed to load review queue:', err);
      setLoading(false);
    }
  };

  const handleAssign = async (docId) => {
    try {
      await api.post(`/document/${docId}/assign-review`);
      setDocId(docId);
      setScreen('review');
    } catch (err) {
      console.error('Failed to assign review:', err);
    }
  };

  const getUrgencyBadge = (score) => {
    if (score >= 0.8) return { text: 'URGENT', class: 'bg-red-600 text-white' };
    if (score >= 0.5) return { text: 'HIGH', class: 'bg-orange-500 text-white' };
    return { text: 'NORMAL', class: 'bg-slate-400 text-white' };
  };

  const getRiskFlags = (flags) => {
    if (!flags || flags.length === 0) return null;
    return flags.map(flag => {
      const colors = {
        safeguarding: 'bg-red-100 text-red-700 border-red-200',
        distress: 'bg-orange-100 text-orange-700 border-orange-200',
        financial_hardship: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        angry: 'bg-purple-100 text-purple-700 border-purple-200',
        unsafe_housing: 'bg-blue-100 text-blue-700 border-blue-200',
      };
      return (
        <span key={flag} className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${colors[flag] || 'bg-slate-100 text-slate-700 border-slate-200'}`}>
          {flag.replace('_', ' ').toUpperCase()}
        </span>
      );
    });
  };

  return (
    <div className="min-h-[calc(100dvh-4rem)] bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-4 py-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold text-slate-800">Review Queue</h1>
            <p className="text-sm text-slate-500">Documents flagged for human review</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${filter === 'all' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600'}`}
            >
              All ({documents.length})
            </button>
            <button
              onClick={() => setFilter('urgent')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${filter === 'urgent' ? 'bg-red-600 text-white' : 'bg-red-50 text-red-600'}`}
            >
              ⚠️ Urgent ({stats.urgent})
            </button>
            <button
              onClick={() => setFilter('high')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${filter === 'high' ? 'bg-orange-500 text-white' : 'bg-orange-50 text-orange-600'}`}
            >
              High ({stats.high})
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="grid grid-cols-4 gap-3">
          <div className="bg-red-50 rounded-lg p-3 border border-red-100">
            <div className="text-2xl font-bold text-red-700">{stats.urgent}</div>
            <div className="text-xs text-red-600">Urgent (≥80%)</div>
          </div>
          <div className="bg-orange-50 rounded-lg p-3 border border-orange-100">
            <div className="text-2xl font-bold text-orange-700">{stats.high}</div>
            <div className="text-xs text-orange-600">High (≥50%)</div>
          </div>
          <div className="bg-slate-50 rounded-lg p-3 border border-slate-200">
            <div className="text-2xl font-bold text-slate-700">{stats.normal}</div>
            <div className="text-xs text-slate-600">Normal (&lt;50%)</div>
          </div>
          <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-100">
            <div className="text-2xl font-bold text-emerald-700">{documents.length}</div>
            <div className="text-xs text-emerald-600">Total Pending</div>
          </div>
        </div>
      </div>

      {/* Document list */}
      <div className="p-4">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600"></div>
          </div>
        ) : documents.length === 0 ? (
          <div className="text-center py-12">
            <div className="text-4xl mb-2">🎉</div>
            <h3 className="text-lg font-bold text-slate-700">Queue is empty!</h3>
            <p className="text-sm text-slate-500">No documents need review at the moment.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {documents.map(doc => {
              const urgency = getUrgencyBadge(doc.urgency_score);
              return (
                <div
                  key={doc.id}
                  className="bg-white rounded-lg border border-slate-200 p-4 hover:shadow-md transition-shadow"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${urgency.class}`}>
                          {urgency.text}
                        </span>
                        <span className="text-xs text-slate-400">
                          #{doc.id}
                        </span>
                        <span className="text-xs text-slate-400">
                          {doc.category?.replace('_', ' ')}
                        </span>
                      </div>
                      <h3 className="font-semibold text-slate-800">{doc.filename}</h3>
                      <div className="flex items-center gap-3 mt-2 text-xs text-slate-500">
                        <span>📅 {new Date(doc.created_at).toLocaleDateString()}</span>
                        <span>🛡️ {doc.redaction_count} redactions</span>
                        <span>😊 {doc.sentiment || 'neutral'}</span>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-2">
                        {getRiskFlags(doc.risk_flags)}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2 ml-4">
                      <button
                        onClick={() => handleAssign(doc.id)}
                        className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-500 transition-colors"
                      >
                        Review →
                      </button>
                      {doc.reviewer_id && (
                        <span className="text-[10px] text-slate-400 text-center">
                          Assigned
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
