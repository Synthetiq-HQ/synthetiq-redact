import { useState, useEffect, useRef, useCallback } from 'react';
import { listBatches, getBatchStatus, createBatch } from '../api';
import { readProcessingSettings } from '../cache';
import StatusBadge from './StatusBadge';

const ACCEPTED = ['.png', '.jpg', '.jpeg', '.pdf', '.docx', '.gif', '.bmp', '.tiff', '.tif'];

function accepted(file) {
  const n = file.name.toLowerCase();
  return ACCEPTED.some((ext) => n.endsWith(ext));
}

function formatTime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString();
}

function ProgressBar({ percent, status }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
      <div
        className={`h-full rounded-full transition-all ${status === 'complete' ? 'bg-emerald-500' : status === 'failed' ? 'bg-red-500' : 'bg-blue-500'}`}
        style={{ width: `${Math.round(percent || 0)}%` }}
      />
    </div>
  );
}

export default function BatchDashboard({ setScreen, setDocId, setDocData }) {
  const [view, setView] = useState('list'); // 'list' | 'detail'
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [activeBatch, setActiveBatch] = useState(null);
  const filesRef = useRef(null);
  const folderRef = useRef(null);

  const loadBatches = useCallback(async () => {
    try {
      const data = await listBatches();
      setBatches(data.batches || []);
      setError('');
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load batches.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBatches();
    const id = window.setInterval(loadBatches, 8000);
    return () => window.clearInterval(id);
  }, [loadBatches]);

  const openBatch = useCallback(async (batchId) => {
    setView('detail');
    setActiveBatch({ id: batchId, loading: true });
    try {
      const data = await getBatchStatus(batchId);
      setActiveBatch(data);
    } catch {
      setActiveBatch({ id: batchId, error: 'Could not load this batch.' });
    }
  }, []);

  // Poll the open batch while it is still processing.
  useEffect(() => {
    if (view !== 'detail' || !activeBatch?.id) return undefined;
    if (!['queued', 'processing'].includes(activeBatch.status)) return undefined;
    const id = window.setInterval(async () => {
      try { setActiveBatch(await getBatchStatus(activeBatch.id)); } catch { /* ignore */ }
    }, 4000);
    return () => window.clearInterval(id);
  }, [view, activeBatch?.id, activeBatch?.status]);

  const addFiles = (fileList) => {
    const next = Array.from(fileList).filter(accepted);
    setSelectedFiles((prev) => {
      const seen = new Set(prev.map((f) => f.name + f.size));
      return [...prev, ...next.filter((f) => !seen.has(f.name + f.size))];
    });
  };

  const handleUpload = async () => {
    if (!selectedFiles.length) return;
    setUploading(true);
    setError('');
    try {
      await createBatch(selectedFiles, false, readProcessingSettings());
      setSelectedFiles([]);
      if (filesRef.current) filesRef.current.value = '';
      if (folderRef.current) folderRef.current.value = '';
      await loadBatches();
    } catch (err) {
      setError(err.response?.data?.detail || 'Batch upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const openDoc = (doc) => {
    setDocId(doc.id);
    setDocData?.(doc);
    setScreen('review');
  };

  // ---- Detail view -----------------------------------------------------
  if (view === 'detail') {
    const b = activeBatch || {};
    const docs = b.documents || [];
    return (
      <div className="flex h-full min-h-0 flex-col rounded-md border border-slate-200 bg-white">
        <div className="flex items-center gap-3 border-b border-slate-200 px-3 py-2">
          <button
            type="button"
            onClick={() => { setView('list'); setActiveBatch(null); loadBatches(); }}
            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            ← Batches
          </button>
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-slate-900">{b.name || 'Batch'}</div>
            <div className="text-xs text-slate-500">
              {b.processed_docs ?? 0}/{b.total_docs ?? 0} processed
              {b.failed_docs ? ` · ${b.failed_docs} failed` : ''} · {formatTime(b.created_at)}
            </div>
          </div>
          {b.status && <div className="ml-auto"><StatusBadge status={b.status} /></div>}
        </div>
        {['queued', 'processing'].includes(b.status) && (
          <div className="px-3 py-2"><ProgressBar percent={b.progress_percent} status={b.status} /></div>
        )}
        <div className="min-h-0 flex-1 overflow-auto">
          {b.loading ? (
            <div className="p-6 text-center text-sm text-slate-400">Loading batch…</div>
          ) : docs.length === 0 ? (
            <div className="p-6 text-center text-sm text-slate-400">No documents in this batch.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-[11px] font-bold uppercase tracking-wide text-slate-500">
                <tr><th className="px-3 py-2">ID</th><th className="px-3 py-2">Filename</th><th className="px-3 py-2">Status</th><th className="px-3 py-2" /></tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id} onClick={() => openDoc(d)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-3 py-2 font-mono text-xs text-slate-400">{d.id}</td>
                    <td className="max-w-[280px] truncate px-3 py-2 font-medium text-slate-800">
                      {d.filename || 'Untitled'}
                      {d.flag_needs_review && <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-800">review</span>}
                    </td>
                    <td className="px-3 py-2"><StatusBadge status={d.status} /></td>
                    <td className="px-3 py-2 text-right">
                      <button type="button" onClick={(e) => { e.stopPropagation(); openDoc(d); }}
                        className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100">Open</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    );
  }

  // ---- List view -------------------------------------------------------
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* Upload */}
      <div className="rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-500">New batch</div>
        <div className="flex flex-wrap items-center gap-2">
          <input ref={filesRef} type="file" multiple accept={ACCEPTED.join(',')} className="hidden"
            onChange={(e) => addFiles(e.target.files)} id="batch-files" />
          <input ref={folderRef} type="file" multiple webkitdirectory="" directory="" className="hidden"
            onChange={(e) => addFiles(e.target.files)} id="batch-folder" />
          <button type="button" onClick={() => filesRef.current?.click()}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">Select files</button>
          <button type="button" onClick={() => folderRef.current?.click()}
            className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50">Select folder</button>
          <span className="text-xs text-slate-500">{selectedFiles.length ? `${selectedFiles.length} file(s) ready` : 'PNG, JPG, TIFF, PDF, DOCX'}</span>
          <div className="ml-auto flex items-center gap-2">
            {selectedFiles.length > 0 && (
              <button type="button" onClick={() => setSelectedFiles([])}
                className="rounded-md px-2 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100">Clear</button>
            )}
            <button type="button" onClick={handleUpload} disabled={uploading || !selectedFiles.length}
              className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 disabled:opacity-50">
              {uploading ? 'Uploading…' : 'Start batch'}
            </button>
          </div>
        </div>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {/* Batches list */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
          <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Batches</span>
          <button type="button" onClick={loadBatches} className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50">Refresh</button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          {loading ? (
            <div className="p-6 text-center text-sm text-slate-400">Loading…</div>
          ) : batches.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-400">No batches yet. Select files or a folder above to start one.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-50 text-left text-[11px] font-bold uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-2">Batch</th><th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2 w-40">Progress</th><th className="px-3 py-2">Created</th><th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {batches.map((b) => (
                  <tr key={b.id} onClick={() => openBatch(b.id)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                    <td className="max-w-[240px] truncate px-3 py-2 font-medium text-slate-800">{b.name || b.id}</td>
                    <td className="px-3 py-2"><StatusBadge status={b.status} /></td>
                    <td className="px-3 py-2">
                      <ProgressBar percent={b.progress_percent} status={b.status} />
                      <div className="mt-1 text-[10px] text-slate-400">{b.processed_docs}/{b.total_docs}{b.failed_docs ? ` · ${b.failed_docs} failed` : ''}</div>
                    </td>
                    <td className="px-3 py-2 text-xs text-slate-500">{formatTime(b.created_at)}</td>
                    <td className="px-3 py-2 text-right">
                      <button type="button" onClick={(e) => { e.stopPropagation(); openBatch(b.id); }}
                        className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100">Open</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
