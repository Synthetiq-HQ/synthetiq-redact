import { useState, useEffect, useMemo, useRef } from 'react';
import { listDocuments } from '../api';
import { readCachedDocuments, writeCachedDocuments } from '../cache';
import StatusBadge from './StatusBadge';

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'needs_review', label: 'Needs review' },
  { id: 'processed', label: 'Processed' },
  { id: 'approved', label: 'Approved' },
  { id: 'failed', label: 'Failed' },
];

function matchesFilter(doc, filter) {
  switch (filter) {
    case 'needs_review':
      return doc.flag_needs_review || ['needs_review', 'in_review'].includes(doc.status);
    case 'processed':
      return ['complete', 'needs_review', 'in_review', 'review_approved', 'exported'].includes(doc.status);
    case 'approved':
      return ['review_approved', 'exported'].includes(doc.status);
    case 'failed':
      return ['failed', 'error'].includes(doc.status);
    default:
      return true;
  }
}

function EnginePill({ engineStatus }) {
  if (!engineStatus) return <span className="text-xs text-slate-300">—</span>;
  const cls = engineStatus.mode === 'main'
    ? 'border-amber-200 bg-amber-50 text-amber-800'
    : engineStatus.mode === 'fallback'
      ? 'border-amber-200 bg-amber-50 text-amber-800'
      : engineStatus.mode === 'blocked'
        ? 'border-red-200 bg-red-50 text-red-800'
      : 'border-slate-200 bg-slate-50 text-slate-500';
  return (
    <span title={engineStatus.detail || ''} className={`inline-block rounded border px-1.5 py-0.5 text-[10px] font-bold ${cls}`}>
      {engineStatus.label}
    </span>
  );
}

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const diffMin = Math.round((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffMin < 1440) return `${Math.round(diffMin / 60)}h ago`;
  return d.toLocaleDateString();
}

export default function DocumentList({ setScreen, setDocId, setDocData, setProgress }) {
  const cachedDocs = readCachedDocuments();
  const [docs, setDocs] = useState(() => cachedDocs?.value?.documents || []);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(() => (
    cachedDocs?.value?.documents?.length ? 'Showing cached inbox while the local backend connects.' : null
  ));
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const retryTimer = useRef(null);
  const retryCount = useRef(0);

  const fetchDocs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments();
      const documents = Array.isArray(data) ? data : data.documents ?? [];
      setDocs(documents);
      writeCachedDocuments({ ...(Array.isArray(data) ? { documents } : data), documents });
      retryCount.current = 0;
      setNotice(null);
    } catch (err) {
      const isNetwork = !err.response;
      if (isNetwork && retryCount.current < 40) {
        retryCount.current += 1;
        setNotice(docs.length
          ? 'Showing cached inbox while the local backend connects.'
          : 'Starting local backend... documents will appear automatically when it is ready.');
        setError(null);
        retryTimer.current = window.setTimeout(fetchDocs, 1500);
      } else {
        setNotice(null);
        setError(err.response?.data?.detail || err.message || 'Could not load documents.');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
    return () => {
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
    };
  }, []);

  const counts = useMemo(() => {
    const c = {};
    for (const f of FILTERS) c[f.id] = docs.filter((d) => matchesFilter(d, f.id)).length;
    return c;
  }, [docs]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return docs
      .filter((d) => matchesFilter(d, filter))
      .filter((d) => !q || String(d.filename || '').toLowerCase().includes(q) || String(d.id).includes(q));
  }, [docs, filter, search]);

  const handleView = (doc) => {
    setDocId(doc.id);
    setDocData(doc);
    if (['complete', 'needs_review', 'in_review', 'review_approved', 'exported'].includes(doc.status)) {
      setScreen('review');
    } else {
      setScreen('final');
    }
  };

  const handleNew = () => {
    setDocId(null);
    setDocData(null);
    setProgress?.({ status: '', message: '', percent: 0 });
    setScreen('scan');
  };

  return (
    <div className="flex h-full min-h-0 flex-col rounded-md border border-slate-200 bg-white">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-3 py-2">
        <div className="flex items-center gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              className={`rounded px-2.5 py-1.5 text-xs font-semibold ${
                filter === f.id ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {f.label}
              <span className={`ml-1.5 rounded px-1 text-[10px] ${filter === f.id ? 'bg-white/20' : 'bg-slate-200 text-slate-600'}`}>
                {counts[f.id] ?? 0}
              </span>
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search id or filename…"
            className="h-8 w-56 rounded-md border border-slate-300 px-2 text-xs outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          />
          <button
            type="button"
            onClick={fetchDocs}
            disabled={loading}
            className="h-8 rounded-md border border-slate-300 px-3 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {notice && (
        <div className="m-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">{notice}</div>
      )}
      {error && (
        <div className="m-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>
      )}

      {/* Table */}
      <div className="min-h-0 flex-1 overflow-auto">
        {visible.length === 0 && !loading ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center text-sm text-slate-400">
            <p>No documents{filter !== 'all' ? ' in this view' : ' yet'}.</p>
            <button type="button" onClick={handleNew}
              className="rounded-md bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500">
              + New document
            </button>
          </div>
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead className="sticky top-0 z-10 bg-slate-50 text-left text-[11px] font-bold uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">Filename</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Engine path</th>
                <th className="px-3 py-2 text-center">Redactions</th>
                <th className="px-3 py-2">Updated</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((doc) => (
                <tr
                  key={doc.id}
                  onClick={() => handleView(doc)}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-3 py-2 font-mono text-xs text-slate-400">{doc.id}</td>
                  <td className="max-w-[260px] truncate px-3 py-2 font-medium text-slate-800">
                    {doc.filename ?? 'Untitled'}
                    {doc.flag_needs_review && (
                      <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">review</span>
                    )}
                  </td>
                  <td className="px-3 py-2"><StatusBadge status={doc.status} /></td>
                  <td className="px-3 py-2"><EnginePill engineStatus={doc.engine_status} /></td>
                  <td className="px-3 py-2 text-center font-semibold text-slate-700">{doc.redaction_count ?? 0}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">{formatTime(doc.updated_at || doc.created_at)}</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleView(doc); }}
                      className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                    >
                      Open
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-slate-200 px-3 py-2 text-xs text-slate-500">
        <span>{visible.length} shown · {docs.length} total</span>
        <span className="text-slate-400">Synthetiq Redact · local document inbox</span>
      </div>
    </div>
  );
}
