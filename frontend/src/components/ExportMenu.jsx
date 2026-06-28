import { useMemo, useState } from 'react';
import { exportToFolder } from '../api';
import {
  readDownloadDestinations,
  readLastDownloadDestination,
  writeDownloadDestinations,
  writeLastDownloadDestination,
} from '../cache';

export default function ExportMenu({
  docId,
  type = 'pdf',
  label = 'Download redacted PDF',
  disabled = false,
  onBeforeExport,
  buttonClassName = '',
  onExported,
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [customPath, setCustomPath] = useState(readLastDownloadDestination());
  const [savedPaths, setSavedPaths] = useState(readDownloadDestinations());
  const [draggingPath, setDraggingPath] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const normalisedSavedPaths = useMemo(() => {
    return Array.from(new Set(savedPaths.map((path) => String(path || '').trim()).filter(Boolean)));
  }, [savedPaths]);

  const menuTitle = type === 'original'
    ? 'Save original file'
    : type === 'pdf'
      ? 'Save redacted PDF'
      : 'Save export';

  const runExport = async (path = '') => {
    if (!docId || busy) return;
    setBusy(true);
    setError('');
    setMessage('');
    try {
      if (onBeforeExport) await onBeforeExport();
      const result = await exportToFolder(docId, type, path);
      if (path) {
        const next = Array.from(new Set([path, ...normalisedSavedPaths]));
        persistPaths(next);
        writeLastDownloadDestination(path);
      }
      setMessage(`Saved to ${result.path}`);
      onExported?.(result);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'object' ? detail.message || 'Export failed.' : detail || 'Export failed.');
    } finally {
      setBusy(false);
    }
  };

  const persistPaths = (paths) => {
    const next = Array.from(new Set(paths.map((path) => String(path || '').trim()).filter(Boolean)));
    setSavedPaths(next);
    writeDownloadDestinations(next);
  };

  const addCustomPath = () => {
    const trimmed = customPath.trim();
    if (!trimmed) return;
    const next = Array.from(new Set([trimmed, ...normalisedSavedPaths]));
    persistPaths(next);
    writeLastDownloadDestination(trimmed);
    setMessage(`Saved path: ${trimmed}`);
    setError('');
  };

  const movePath = (path, offset) => {
    const index = normalisedSavedPaths.indexOf(path);
    const target = index + offset;
    if (index < 0 || target < 0 || target >= normalisedSavedPaths.length) return;
    const next = [...normalisedSavedPaths];
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    persistPaths(next);
  };

  const removePath = (path) => {
    persistPaths(normalisedSavedPaths.filter((savedPath) => savedPath !== path));
    if (customPath.trim() === path) setCustomPath('');
  };

  const dropPath = (targetPath) => {
    if (!draggingPath || draggingPath === targetPath) return;
    const next = normalisedSavedPaths.filter((path) => path !== draggingPath);
    const targetIndex = next.indexOf(targetPath);
    next.splice(targetIndex < 0 ? next.length : targetIndex, 0, draggingPath);
    persistPaths(next);
    setDraggingPath('');
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        disabled={disabled || busy}
        className={buttonClassName}
      >
        {busy ? 'Saving...' : label}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-50 w-[380px] rounded-md border border-slate-200 bg-white p-3 text-left text-xs shadow-xl">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="font-bold uppercase tracking-wide text-slate-400">{menuTitle}</div>
            {busy && <div className="font-semibold text-blue-700">Saving...</div>}
          </div>

          <button
            type="button"
            onClick={() => runExport('')}
            disabled={busy}
            className="group flex w-full items-center justify-between gap-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-3 text-left shadow-sm transition-colors hover:bg-emerald-100 disabled:opacity-50"
          >
            <span>
              <span className="block text-sm font-bold text-emerald-950">Downloads folder</span>
              <span className="mt-0.5 block text-[11px] font-medium text-emerald-700">Default save location on this PC</span>
            </span>
            <span className="rounded-md bg-emerald-700 px-2.5 py-1.5 text-[11px] font-bold text-white group-hover:bg-emerald-800">
              Save here
            </span>
          </button>

          <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-2">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-bold uppercase tracking-wide text-slate-500">Saved paths</div>
              <div className="text-[10px] font-semibold text-slate-400">Drag or move</div>
            </div>
            {normalisedSavedPaths.length ? (
              <div className="space-y-1.5">
                {normalisedSavedPaths.map((path, index) => (
                  <div
                    key={path}
                    draggable
                    onDragStart={() => setDraggingPath(path)}
                    onDragEnd={() => setDraggingPath('')}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => dropPath(path)}
                    className={`rounded-md border bg-white p-2 shadow-sm ${
                      draggingPath === path ? 'border-blue-300 opacity-60' : 'border-slate-200'
                    }`}
                  >
                    <div className="flex items-start gap-2">
                      <button
                        type="button"
                        onClick={() => runExport(path)}
                        disabled={busy}
                        className="min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 py-2 text-left font-semibold text-slate-700 hover:border-blue-300 hover:bg-blue-50 disabled:opacity-50"
                        title={path}
                      >
                        <span className="block truncate">{path}</span>
                        <span className="mt-0.5 block text-[10px] font-bold uppercase tracking-wide text-blue-600">Save to this path</span>
                      </button>
                      <div className="flex shrink-0 flex-col gap-1">
                        <button
                          type="button"
                          onClick={() => movePath(path, -1)}
                          disabled={index === 0}
                          className="rounded border border-slate-200 px-1.5 py-0.5 font-bold text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                        >
                          Up
                        </button>
                        <button
                          type="button"
                          onClick={() => movePath(path, 1)}
                          disabled={index === normalisedSavedPaths.length - 1}
                          className="rounded border border-slate-200 px-1.5 py-0.5 font-bold text-slate-500 hover:bg-slate-100 disabled:opacity-30"
                        >
                          Down
                        </button>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removePath(path)}
                      className="mt-1 text-[10px] font-bold uppercase tracking-wide text-red-500 hover:text-red-700"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-slate-300 bg-white px-3 py-4 text-center text-slate-500">
                No saved paths yet.
              </div>
            )}
          </div>

          <div className="mt-3 rounded-md border border-slate-200 bg-white p-3">
            <label className="block text-[11px] font-bold uppercase tracking-wide text-slate-500">
              Add new path
            </label>
            <div className="mt-2 flex gap-2">
              <input
                value={customPath}
                onChange={(event) => setCustomPath(event.target.value)}
                placeholder="C:\\Users\\INTERPOL\\Downloads"
                className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-xs outline-none focus:border-emerald-500"
              />
              <button
                type="button"
                onClick={addCustomPath}
                disabled={!customPath.trim()}
                className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-1.5 font-bold text-emerald-800 hover:bg-emerald-100 disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400"
              >
                Save path
              </button>
            </div>
            <button
              type="button"
              onClick={() => runExport(customPath.trim())}
              disabled={!customPath.trim() || busy}
              className="mt-2 w-full rounded-md bg-slate-950 px-3 py-2.5 font-bold text-white shadow-sm hover:bg-slate-800 disabled:bg-slate-300"
            >
              Save to typed path
            </button>
          </div>
          {message && <div className="mt-2 rounded bg-emerald-50 px-2 py-1.5 text-emerald-700">{message}</div>}
          {error && <div className="mt-2 rounded bg-red-50 px-2 py-1.5 text-red-700">{error}</div>}
        </div>
      )}
    </div>
  );
}
