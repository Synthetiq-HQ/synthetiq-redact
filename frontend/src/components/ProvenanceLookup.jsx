import { useEffect, useRef, useState } from 'react';
import { decodeProvenance, getProvenanceInstance } from '../api';

function Row({ label, value, mono }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex gap-3 border-b border-slate-100 py-1.5 text-sm last:border-b-0">
      <span className="w-40 shrink-0 text-xs font-bold uppercase tracking-wide text-slate-400">{label}</span>
      <span className={`min-w-0 break-words text-slate-800 ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  );
}

function StatusBanner({ status, message }) {
  const map = {
    found: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    foreign: 'border-amber-200 bg-amber-50 text-amber-900',
    not_in_library: 'border-amber-200 bg-amber-50 text-amber-900',
    invalid: 'border-red-200 bg-red-50 text-red-700',
    unreadable: 'border-slate-200 bg-slate-50 text-slate-600',
  };
  const title = {
    found: 'Provenance found',
    foreign: 'Produced by another server',
    not_in_library: 'Valid ID, not in this library',
    invalid: 'Not a valid Synthetiq Redact ID',
    unreadable: 'No watermark could be read',
  };
  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${map[status] || map.unreadable}`}>
      <div className="font-bold">{title[status] || 'Result'}</div>
      {message && <div className="mt-0.5 text-xs leading-5">{message}</div>}
    </div>
  );
}

export default function ProvenanceLookup({ setScreen, setDocId, setDocData }) {
  const [instance, setInstance] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    getProvenanceInstance().then(setInstance).catch(() => setInstance(null));
  }, []);

  const handleFile = async (file) => {
    if (!file) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      setResult(await decodeProvenance(file));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not read that file.');
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  const record = result?.record;
  const doc = result?.document;

  const openInEditor = () => {
    if (!doc?.openable) return;
    setDocId(doc.id);
    setDocData?.({ id: doc.id, filename: doc.filename, status: doc.status });
    setScreen('review');
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-4 py-3">
        <div>
          <h1 className="text-lg font-bold text-slate-950">Find ID</h1>
          <p className="mt-1 text-xs text-slate-500">
            Drop a redacted PDF or image to read its Synthetiq Redact provenance watermark.
          </p>
        </div>
        {instance?.short_id && (
          <span className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-bold text-slate-500"
            title={`This server's provenance id: ${instance.instance_id || ''}`}>
            Server {instance.short_id}
          </span>
        )}
      </div>

      {/* Dropzone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-6 py-10 text-center transition-colors ${
          dragging ? 'border-emerald-500 bg-emerald-50' : 'border-slate-300 bg-white hover:bg-slate-50'
        }`}
      >
        <input ref={inputRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.bmp,.tiff,.tif,.gif" className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])} />
        <div className="text-sm font-semibold text-slate-700">
          {busy ? 'Reading watermark…' : 'Drop a redacted PDF or image here, or click to choose'}
        </div>
        <div className="mt-1 text-xs text-slate-400">Reads the burned-in mark; works on screenshots and scans too.</div>
      </div>

      {error && <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

      {result && (
        <div className="space-y-3">
          <StatusBanner status={result.status} message={result.message} />

          {result.status === 'found' && record && (
            <div className="rounded-md border border-slate-200 bg-white p-4">
              <Row label="Document" value={doc?.filename || `#${record.document_id}`} />
              <Row label="Export ID" value={record.export_id} mono />
              <Row label="Exported" value={record.created_at ? new Date(record.created_at).toLocaleString() : null} />
              <Row label="Engine path" value={record.engine_used} />
              <Row label="Pages" value={record.page_count} />
              <Row label="User / employee" value={record.user_id != null ? `#${record.user_id}` : 'Not recorded'} />
              <Row label="Original hash" value={record.original_hash} mono />
              <Row label="Redacted hash" value={record.redacted_hash} mono />
              <Row label="Output ID" value={record.redacted_output_id} mono />

              <div className="mt-3 flex gap-2">
                <button type="button" onClick={openInEditor} disabled={!doc?.openable}
                  className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-40">
                  Open in Editor
                </button>
                <button type="button" onClick={() => setScreen('library')}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-50">
                  Open Library
                </button>
                {doc && !doc.accessible && (
                  <span className="self-center text-xs text-slate-400">Document is in another council workspace.</span>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
