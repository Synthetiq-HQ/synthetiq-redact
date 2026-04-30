import { useState, useEffect } from 'react';
import { listDocuments } from '../api';
import StatusBadge from './StatusBadge';

export default function DocumentList({ setScreen, setDocId, setDocData, setProgress }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDocs = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDocuments();
      setDocs(Array.isArray(data) ? data : data.documents ?? []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
  }, []);

  const handleNew = () => {
    setDocId(null);
    setDocData(null);
    setProgress({ status: '', message: '', percent: 0 });
    setScreen('scan');
  };

  const handleView = (doc) => {
    setDocId(doc.id);
    setDocData(doc);
    setScreen('final');
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="council-card">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">All Documents</h2>
          <div className="flex gap-2">
            <button
              onClick={fetchDocs}
              disabled={loading}
              className="tap-target rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-200 active:bg-slate-300 disabled:opacity-50"
            >
              {loading ? '⏳' : '🔄'} Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-3 rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {docs.length === 0 && !loading && (
          <div className="rounded-lg bg-slate-50 py-8 text-center text-sm text-slate-400 ring-1 ring-slate-200">
            <div className="mb-2 text-2xl">📭</div>
            No documents yet.
          </div>
        )}

        {/* Mobile: cards */}
        <div className="flex flex-col gap-3 sm:hidden">
          {docs.map((doc) => (
            <div
              key={doc.id}
              className="rounded-xl bg-slate-50 p-3 ring-1 ring-slate-200"
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-mono text-slate-400">#{doc.id}</span>
                <StatusBadge status={doc.status} />
              </div>
              <p className="mb-1 text-sm font-semibold text-slate-800 truncate">
                {doc.filename ?? 'Untitled'}
              </p>
              <div className="mb-2 flex flex-wrap gap-1 text-xs text-slate-500">
                {doc.category && (
                  <span className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200 capitalize">
                    {doc.category.replace('_', ' ')}
                  </span>
                )}
                {doc.department && (
                  <span className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200">
                    {doc.department}
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  Urgency: {((doc.urgency_score ?? 0) * 100).toFixed(0)}%
                </span>
                <button
                  onClick={() => handleView(doc)}
                  className="tap-target rounded-lg bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                >
                  View
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Desktop: table */}
        <div className="hidden overflow-x-auto rounded-xl ring-1 ring-slate-200 sm:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-100 text-left text-xs font-bold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2">ID</th>
                <th className="px-4 py-2">Filename</th>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Department</th>
                <th className="px-4 py-2">Urgency</th>
                <th className="px-4 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {docs.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-mono text-slate-400">{doc.id}</td>
                  <td className="px-4 py-2 font-medium text-slate-700 truncate max-w-[160px]">
                    {doc.filename ?? 'Untitled'}
                  </td>
                  <td className="px-4 py-2 capitalize text-slate-600">
                    {(doc.category ?? '—').replace('_', ' ')}
                  </td>
                  <td className="px-4 py-2">
                    <StatusBadge status={doc.status} />
                  </td>
                  <td className="px-4 py-2 text-slate-600">{doc.department ?? '—'}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`text-xs font-bold ${
                        (doc.urgency_score ?? 0) >= 0.7
                          ? 'text-red-600'
                          : (doc.urgency_score ?? 0) >= 0.4
                          ? 'text-amber-600'
                          : 'text-emerald-600'
                      }`}
                    >
                      {((doc.urgency_score ?? 0) * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    <button
                      onClick={() => handleView(doc)}
                      className="tap-target rounded-lg bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100"
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* New document button */}
        <button
          onClick={handleNew}
          className="tap-target mt-4 w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white hover:bg-emerald-500 active:bg-emerald-700"
        >
          ➕ Process New Document
        </button>
      </div>
    </div>
  );
}
