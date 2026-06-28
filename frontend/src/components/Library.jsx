import { useEffect, useMemo, useRef, useState } from 'react';
import { downloadOriginalFile, getImageUrl, listDocuments } from '../api';
import { readCachedDocuments, writeCachedDocuments } from '../cache';
import ExportMenu from './ExportMenu';
import StatusBadge from './StatusBadge';

const LIBRARY_STATUSES = new Set([
  'complete',
  'needs_review',
  'in_review',
  'review_approved',
  'exported',
]);

function formatTime(iso) {
  if (!iso) return 'unknown';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'unknown';
  return date.toLocaleString([], {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function engineLabel(doc) {
  return doc?.engine_status?.label || (doc?.engine_used ? 'Custom engine' : 'Not recorded');
}

function PreviewPane({ doc, type, label, revision, refreshing }) {
  const [failed, setFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    setFailed(false);
    setLoaded(false);
  }, [doc?.id, type, revision]);

  const imageSrc = doc?.id ? getImageUrl(doc.id, type, revision) : '';

  return (
    <div className="min-h-0 rounded-md border border-slate-200 bg-slate-100 p-2">
      <div className="mb-2 flex items-center justify-between text-[11px] font-bold uppercase tracking-wide text-slate-400">
        <span>{label}</span>
        <span>{type}</span>
      </div>
      <div className="flex aspect-[3/4] items-center justify-center overflow-hidden rounded border border-slate-200 bg-white">
        {doc?.id ? (
          <div className="relative h-full w-full">
            {!failed && (
              <img
                src={imageSrc}
                alt={`${label} preview`}
                className={`h-full w-full object-contain transition-opacity duration-200 ${loaded ? 'opacity-100' : 'opacity-0'}`}
                onLoad={() => {
                  setLoaded(true);
                  setFailed(false);
                }}
                onError={() => {
                  setLoaded(false);
                  setFailed(true);
                }}
              />
            )}
            {(!loaded || failed || refreshing) && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-white/90 px-6 text-center text-xs text-slate-500">
                <div className="h-8 w-8 rounded-full border-2 border-slate-200 border-t-emerald-600 animate-spin" />
                <div className="max-w-56">
                  {failed
                    ? 'Retrying preview as soon as the local backend responds.'
                    : refreshing
                      ? 'Refreshing preview...'
                      : 'Loading preview...'}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 px-4 text-center text-xs text-slate-400">
            <div className="h-8 w-8 rounded-full border-2 border-slate-200 border-t-emerald-600 animate-spin" />
            <div>
              Preview will appear when the local backend is online.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Library({ setScreen, setDocId, setDocData }) {
  const cachedDocs = readCachedDocuments();
  const [docs, setDocs] = useState(() => cachedDocs?.value?.documents || []);
  const [activeId, setActiveId] = useState(() => cachedDocs?.value?.documents?.[0]?.id || null);
  const [search, setSearch] = useState('');
  const [notice, setNotice] = useState(() => (
    cachedDocs?.value?.documents?.length ? 'Showing cached library while the local backend connects.' : ''
  ));
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [imageRevision, setImageRevision] = useState(() => Date.now());
  const retryTimer = useRef(null);
  const retryCount = useRef(0);

  const fetchDocs = async () => {
    let keepLoading = false;
    setLoading(true);
    setError('');
    try {
      const data = await listDocuments();
      const documents = Array.isArray(data) ? data : data.documents ?? [];
      setDocs(documents);
      writeCachedDocuments({ ...(Array.isArray(data) ? { documents } : data), documents });
      retryCount.current = 0;
      setNotice('');
      setImageRevision(Date.now());
    } catch (err) {
      const isNetwork = !err.response;
      if (isNetwork && retryCount.current < 40) {
        retryCount.current += 1;
        keepLoading = true;
        setNotice(docs.length
          ? 'Showing cached library while the local backend connects.'
          : 'Starting local backend... library items will appear automatically.');
        retryTimer.current = window.setTimeout(fetchDocs, 1500);
      } else {
        setError(err.response?.data?.detail || err.message || 'Could not load the library.');
      }
    } finally {
      if (!keepLoading) setLoading(false);
    }
  };

  useEffect(() => {
    fetchDocs();
    return () => {
      if (retryTimer.current) window.clearTimeout(retryTimer.current);
    };
  }, []);

  const libraryDocs = useMemo(() => {
    const query = search.trim().toLowerCase();
    return docs
      .filter((doc) => LIBRARY_STATUSES.has(doc.status))
      .filter((doc) => (
        !query ||
        String(doc.filename || '').toLowerCase().includes(query) ||
        String(doc.id).includes(query)
      ));
  }, [docs, search]);

  useEffect(() => {
    if (!libraryDocs.length) {
      setActiveId(null);
      return;
    }
    if (!libraryDocs.some((doc) => doc.id === activeId)) {
      setActiveId(libraryDocs[0].id);
    }
  }, [libraryDocs, activeId]);

  const activeDoc = libraryDocs.find((doc) => doc.id === activeId) || libraryDocs[0] || null;

  const openInEditor = (doc) => {
    if (!doc) return;
    setDocId(doc.id);
    setDocData(doc);
    setScreen('review');
  };

  const saveOriginalNow = async (doc) => {
    if (!doc) return;
    setError('');
    try {
      await downloadOriginalFile(doc.id);
    } catch (err) {
      setError(err.response?.data?.detail || 'Original file could not be downloaded.');
    }
  };

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(360px,480px)_1fr] gap-3">
      <section className="flex min-h-0 flex-col rounded-md border border-slate-200 bg-white">
        <div className="border-b border-slate-200 p-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-bold text-slate-950">Library</h2>
              <p className="mt-0.5 text-xs text-slate-500">Processed documents, saved exports, and originals.</p>
            </div>
            <button
              type="button"
              onClick={fetchDocs}
              disabled={loading}
              className="h-8 rounded-md border border-slate-300 px-3 text-xs font-bold text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              <span className="inline-flex items-center gap-2">
                {loading && <span className="h-3.5 w-3.5 rounded-full border-2 border-slate-300 border-t-emerald-600 animate-spin" />}
                <span>Refresh</span>
              </span>
            </button>
          </div>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search library..."
            className="mt-3 h-9 w-full rounded-md border border-slate-300 px-3 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
          />
        </div>

        {(notice || loading) && (
          <div className="mx-3 mt-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
            <span className="inline-flex items-center gap-2">
              {loading && <span className="h-4 w-4 rounded-full border-2 border-blue-200 border-t-blue-700 animate-spin" />}
              <span>{notice || 'Refreshing library and previews...'}</span>
            </span>
          </div>
        )}
        {error && (
          <div className="mx-3 mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto p-2">
          {libraryDocs.length ? libraryDocs.map((doc) => {
            const active = doc.id === activeDoc?.id;
            return (
              <button
                key={doc.id}
                type="button"
                onClick={() => setActiveId(doc.id)}
                className={`mb-2 w-full rounded-md border p-3 text-left transition-colors ${
                  active ? 'border-emerald-300 bg-emerald-50' : 'border-slate-200 bg-white hover:bg-slate-50'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-bold text-slate-900">{doc.filename || 'Untitled'}</div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <StatusBadge status={doc.status} />
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-500">
                        {doc.redaction_count ?? 0} redactions
                      </span>
                    </div>
                  </div>
                  <span className="shrink-0 font-mono text-xs text-slate-400">#{doc.id}</span>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500">
                  <span className="truncate">Engine: {engineLabel(doc)}</span>
                  <span className="text-right">{formatTime(doc.updated_at || doc.created_at)}</span>
                </div>
              </button>
            );
          }) : (
            <div className="flex h-full items-center justify-center px-8 text-center text-sm text-slate-400">
              No processed documents in the library yet.
            </div>
          )}
        </div>
      </section>

      <section className="flex min-h-0 flex-col rounded-md border border-slate-200 bg-white">
        {activeDoc ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 p-4">
              <div className="min-w-0">
                <div className="truncate text-base font-bold text-slate-950">{activeDoc.filename || 'Untitled'}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <StatusBadge status={activeDoc.status} />
                  <span>Document #{activeDoc.id}</span>
                  <span>{engineLabel(activeDoc)}</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => openInEditor(activeDoc)}
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-bold text-slate-700 hover:bg-slate-50"
                >
                  Send to editor
                </button>
                <button
                  type="button"
                  onClick={() => saveOriginalNow(activeDoc)}
                  className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-bold text-slate-700 hover:bg-slate-50"
                >
                  Browser download original
                </button>
                <ExportMenu
                  docId={activeDoc.id}
                  type="original"
                  label="Save original"
                  buttonClassName="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-bold text-slate-700 hover:bg-slate-50"
                  onExported={(result) => setNotice(`Saved original to ${result.path}`)}
                />
                <ExportMenu
                  docId={activeDoc.id}
                  type="pdf"
                  label="Save redacted PDF"
                  buttonClassName="h-9 rounded-md bg-slate-950 px-3 text-xs font-bold text-white hover:bg-slate-800"
                  onExported={(result) => setNotice(`Saved redacted PDF to ${result.path}`)}
                />
              </div>
            </div>

            <div className="grid min-h-0 flex-1 grid-cols-2 gap-3 overflow-auto bg-slate-100 p-4">
              <PreviewPane doc={activeDoc} type="original" label="Original" revision={imageRevision} refreshing={loading} />
              <PreviewPane doc={activeDoc} type="redacted" label="Redacted" revision={imageRevision} refreshing={loading} />
            </div>

            <div className="grid grid-cols-4 gap-3 border-t border-slate-200 p-4 text-xs">
              <div>
                <div className="font-bold uppercase tracking-wide text-slate-400">Status</div>
                <div className="mt-1 text-slate-700">{activeDoc.status || 'unknown'}</div>
              </div>
              <div>
                <div className="font-bold uppercase tracking-wide text-slate-400">Updated</div>
                <div className="mt-1 text-slate-700">{formatTime(activeDoc.updated_at || activeDoc.created_at)}</div>
              </div>
              <div>
                <div className="font-bold uppercase tracking-wide text-slate-400">Redactions</div>
                <div className="mt-1 text-slate-700">{activeDoc.redaction_count ?? 0}</div>
              </div>
              <div>
                <div className="font-bold uppercase tracking-wide text-slate-400">Path</div>
                <div className="mt-1 truncate text-slate-700">Downloads by default, custom folders supported</div>
              </div>
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">
            Select a library document to preview it.
          </div>
        )}
      </section>
    </div>
  );
}
