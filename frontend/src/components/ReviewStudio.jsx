import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import api from '../api';

export default function ReviewStudio({ docId, setScreen }) {
  const [document, setDocument] = useState(null);
  const [redactions, setRedactions] = useState([]);
  const [selectedRedaction, setSelectedRedaction] = useState(null);
  const [loading, setLoading] = useState(true);
  const [zoom, setZoom] = useState(1);
  const [showConfidence, setShowConfidence] = useState(true);
  const [reviewStats, setReviewStats] = useState({ approved: 0, rejected: 0, pending: 0 });

  useEffect(() => {
    loadDocument();
  }, [docId]);

  const loadDocument = async () => {
    try {
      const res = await api.get(`/document/${docId}`);
      setDocument(res.data);
      setRedactions(res.data.redactions || []);
      updateStats(res.data.redactions || []);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load document:', err);
      setLoading(false);
    }
  };

  const updateStats = (reds) => {
    const approved = reds.filter(r => r.status === 'approved').length;
    const rejected = reds.filter(r => r.status === 'rejected').length;
    const pending = reds.filter(r => r.status === 'pending').length;
    setReviewStats({ approved, rejected, pending });
  };

  const handleApprove = async (redactionId) => {
    try {
      await api.post(`/redactions/${redactionId}/approve`);
      setRedactions(prev => prev.map(r => 
        r.id === redactionId ? { ...r, status: 'approved' } : r
      ));
      updateStats(redactions.map(r => r.id === redactionId ? { ...r, status: 'approved' } : r));
    } catch (err) {
      console.error('Failed to approve:', err);
    }
  };

  const handleReject = async (redactionId) => {
    try {
      await api.post(`/redactions/${redactionId}/reject`, { reason: '' });
      setRedactions(prev => prev.map(r => 
        r.id === redactionId ? { ...r, status: 'rejected' } : r
      ));
      updateStats(redactions.map(r => r.id === redactionId ? { ...r, status: 'rejected' } : r));
    } catch (err) {
      console.error('Failed to reject:', err);
    }
  };

  const handleApproveAll = async () => {
    try {
      await api.post(`/document/${docId}/approve-all`);
      setRedactions(prev => prev.map(r => ({ ...r, status: 'approved' })));
      updateStats(redactions.map(r => ({ ...r, status: 'approved' })));
    } catch (err) {
      console.error('Failed to approve all:', err);
    }
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.9) return 'bg-emerald-500';
    if (confidence >= 0.7) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getConfidenceText = (confidence) => {
    if (confidence >= 0.9) return '🟢 High';
    if (confidence >= 0.7) return '🟡 Medium';
    return '🔴 Low';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="flex items-center justify-center h-screen text-red-500">
        Document not found
      </div>
    );
  }

  return (
    <div className="h-[calc(100dvh-4rem)] flex flex-col">
      {/* Toolbar */}
      <div className="bg-white border-b border-slate-200 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h2 className="font-bold text-slate-800">Review Studio</h2>
          <span className="text-sm text-slate-500">#{docId}</span>
          <span className="text-sm text-slate-500">{document.filename}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowConfidence(!showConfidence)}
            className={`px-3 py-1 rounded text-xs font-medium ${showConfidence ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'}`}
          >
            Confidence Heatmap
          </button>
          <button
            onClick={() => setZoom(z => Math.max(0.5, z - 0.1))}
            className="px-3 py-1 rounded bg-slate-100 text-xs font-medium"
          >
            🔍-
          </button>
          <span className="text-xs text-slate-500">{Math.round(zoom * 100)}%</span>
          <button
            onClick={() => setZoom(z => Math.min(2, z + 0.1))}
            className="px-3 py-1 rounded bg-slate-100 text-xs font-medium"
          >
            🔍+
          </button>
          <button
            onClick={handleApproveAll}
            className="px-3 py-1 rounded bg-emerald-600 text-white text-xs font-bold"
          >
            ✓ Approve All
          </button>
        </div>
      </div>

      {/* Stats bar */}
      <div className="bg-slate-50 border-b border-slate-200 px-4 py-2 flex items-center gap-6 text-xs">
        <span className="text-emerald-700 font-medium">✓ Approved: {reviewStats.approved}</span>
        <span className="text-red-700 font-medium">✗ Rejected: {reviewStats.rejected}</span>
        <span className="text-slate-600 font-medium">○ Pending: {reviewStats.pending}</span>
        <span className="text-slate-400">|</span>
        <span className="text-slate-600">Total: {redactions.length}</span>
      </div>

      {/* Main content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Document viewer */}
        <div className="flex-1 bg-slate-100 overflow-auto p-4">
          <div className="relative inline-block" style={{ transform: `scale(${zoom})`, transformOrigin: 'top left' }}>
            <img
              src={api.defaults.baseURL + `/document/${docId}/image?type=original`}
              alt="Original document"
              className="max-w-none shadow-lg"
            />
            {/* Redaction overlays */}
            {showConfidence && redactions.map(red => {
              if (!red.bbox || !red.bbox.bbox) return null;
              const bbox = red.bbox.bbox;
              const xs = bbox.map(p => p[0]);
              const ys = bbox.map(p => p[1]);
              const x = Math.min(...xs);
              const y = Math.min(...ys);
              const w = Math.max(...xs) - x;
              const h = Math.max(...ys) - y;
              
              const isSelected = selectedRedaction?.id === red.id;
              const colorClass = getConfidenceColor(red.confidence);
              
              return (
                <div
                  key={red.id}
                  onClick={() => setSelectedRedaction(red)}
                  className={`absolute cursor-pointer transition-all ${isSelected ? 'ring-2 ring-blue-500 z-10' : ''}`}
                  style={{
                    left: x,
                    top: y,
                    width: w,
                    height: h,
                    backgroundColor: red.status === 'approved' ? 'rgba(0,0,0,0.8)' : 
                                     red.status === 'rejected' ? 'rgba(255,0,0,0.3)' : 
                                     `rgba(${red.confidence >= 0.9 ? '0,200,0' : red.confidence >= 0.7 ? '255,200,0' : '255,0,0'}, 0.4)`,
                    border: `2px solid ${red.status === 'approved' ? '#10b981' : red.status === 'rejected' ? '#ef4444' : '#f59e0b'}`,
                  }}
                >
                  <span className="absolute -top-5 left-0 bg-black text-white text-[10px] px-1 rounded whitespace-nowrap">
                    {red.type} {getConfidenceText(red.confidence)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right: Redaction inspector */}
        <div className="w-96 bg-white border-l border-slate-200 flex flex-col">
          <div className="p-4 border-b border-slate-200">
            <h3 className="font-bold text-slate-800">Redaction Inspector</h3>
            <p className="text-xs text-slate-500 mt-1">Click a redaction on the image to inspect</p>
          </div>

          <div className="flex-1 overflow-auto p-4 space-y-3">
            {selectedRedaction ? (
              <div className="space-y-4">
                <div className="bg-slate-50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase font-medium">Type</div>
                  <div className="text-sm font-semibold text-slate-800">{selectedRedaction.type}</div>
                </div>
                
                <div className="bg-slate-50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase font-medium">Original Value</div>
                  <div className="text-sm font-mono text-slate-800 mt-1 bg-white p-2 rounded border">
                    {selectedRedaction.original_value || '[Not captured]'}
                  </div>
                </div>

                <div className="bg-slate-50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase font-medium">Masked Value</div>
                  <div className="text-sm font-mono text-slate-800 mt-1 bg-white p-2 rounded border">
                    {selectedRedaction.masked_value || '[REDACTED]'}
                  </div>
                </div>

                <div className="bg-slate-50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase font-medium">Confidence</div>
                  <div className="flex items-center gap-2 mt-1">
                    <div className={`w-3 h-3 rounded-full ${getConfidenceColor(selectedRedaction.confidence)}`}></div>
                    <span className="text-sm font-medium">{(selectedRedaction.confidence * 100).toFixed(1)}%</span>
                  </div>
                  <div className="mt-2 h-2 bg-slate-200 rounded-full overflow-hidden">
                    <div 
                      className={`h-full ${getConfidenceColor(selectedRedaction.confidence)}`}
                      style={{ width: `${selectedRedaction.confidence * 100}%` }}
                    ></div>
                  </div>
                </div>

                <div className="bg-slate-50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase font-medium">Detection Method</div>
                  <div className="text-sm text-slate-800">{selectedRedaction.method}</div>
                </div>

                <div className="bg-slate-50 rounded-lg p-3">
                  <div className="text-xs text-slate-500 uppercase font-medium">Status</div>
                  <div className="text-sm font-medium">
                    {selectedRedaction.status === 'approved' && <span className="text-emerald-600">✓ Approved</span>}
                    {selectedRedaction.status === 'rejected' && <span className="text-red-600">✗ Rejected</span>}
                    {selectedRedaction.status === 'pending' && <span className="text-yellow-600">○ Pending Review</span>}
                  </div>
                </div>

                {/* Action buttons */}
                {selectedRedaction.status === 'pending' && (
                  <div className="flex gap-2 pt-2">
                    <button
                      onClick={() => handleApprove(selectedRedaction.id)}
                      className="flex-1 bg-emerald-600 text-white py-2 rounded-lg font-bold text-sm hover:bg-emerald-500 transition-colors"
                    >
                      ✓ Approve
                    </button>
                    <button
                      onClick={() => handleReject(selectedRedaction.id)}
                      className="flex-1 bg-red-600 text-white py-2 rounded-lg font-bold text-sm hover:bg-red-500 transition-colors"
                    >
                      ✗ Reject
                    </button>
                  </div>
                )}

                {selectedRedaction.status !== 'pending' && (
                  <button
                    onClick={() => setSelectedRedaction(prev => ({ ...prev, status: 'pending' }))}
                    className="w-full bg-slate-200 text-slate-700 py-2 rounded-lg font-bold text-sm hover:bg-slate-300 transition-colors"
                  >
                    ↺ Reset to Pending
                  </button>
                )}
              </div>
            ) : (
              <div className="text-center text-slate-400 py-8">
                <div className="text-4xl mb-2">🖱️</div>
                <p className="text-sm">Click a redaction box on the document to inspect and approve/reject</p>
              </div>
            )}
          </div>

          {/* Redaction list */}
          <div className="border-t border-slate-200 p-4 max-h-48 overflow-auto">
            <h4 className="text-xs font-bold text-slate-500 uppercase mb-2">All Redactions</h4>
            <div className="space-y-1">
              {redactions.map(red => (
                <div
                  key={red.id}
                  onClick={() => setSelectedRedaction(red)}
                  className={`flex items-center gap-2 p-2 rounded cursor-pointer text-xs ${
                    selectedRedaction?.id === red.id ? 'bg-blue-50 border border-blue-200' : 'hover:bg-slate-50'
                  }`}
                >
                  <div className={`w-2 h-2 rounded-full ${
                    red.status === 'approved' ? 'bg-emerald-500' : 
                    red.status === 'rejected' ? 'bg-red-500' : 'bg-yellow-500'
                  }`}></div>
                  <span className="font-medium">{red.type}</span>
                  <span className="text-slate-400">{(red.confidence * 100).toFixed(0)}%</span>
                  <span className="ml-auto">
                    {red.status === 'approved' && '✓'}
                    {red.status === 'rejected' && '✗'}
                    {red.status === 'pending' && '○'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
