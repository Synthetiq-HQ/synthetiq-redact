import { useState } from 'react';
import {
  getDefaultDownloadPath,
  readDownloadDestinations,
  readLastDownloadDestination,
  readProcessingSettings,
  readUserProfile,
  readWorkspacePreferences,
  writeDownloadDestinations,
  writeLastDownloadDestination,
  writeProcessingSettings,
  writeUserProfile,
  writeWorkspacePreferences,
} from '../cache';

function Section({ title, description, children }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="text-xs font-bold uppercase tracking-wide text-slate-400">{title}</div>
        {description && <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-bold text-slate-500">{label}</span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
      />
    </label>
  );
}

function ToggleRow({ title, description, checked, onChange, tone = 'emerald' }) {
  const active = tone === 'amber' ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 rounded-md border border-slate-200 bg-white px-3 py-3 hover:bg-slate-50">
      <span>
        <span className="block text-sm font-bold text-slate-900">{title}</span>
        {description && <span className="mt-1 block text-xs leading-5 text-slate-500">{description}</span>}
      </span>
      <span className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? active : 'bg-slate-300'}`}>
        <span className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-6' : 'translate-x-1'}`} />
      </span>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} className="sr-only" />
    </label>
  );
}

function StatusCard({ label, value, tone = 'slate' }) {
  const tones = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    amber: 'border-amber-200 bg-amber-50 text-amber-900',
    slate: 'border-slate-200 bg-slate-50 text-slate-700',
  };

  return (
    <div className={`rounded-md border px-3 py-2 ${tones[tone] || tones.slate}`}>
      <div className="text-[10px] font-bold uppercase tracking-wide opacity-70">{label}</div>
      <div className="mt-1 text-xs font-bold">{value}</div>
    </div>
  );
}

export default function Preferences({ setScreen }) {
  const downloadsPath = getDefaultDownloadPath();
  const [settings, setSettings] = useState(() => readProcessingSettings());
  const [profile, setProfile] = useState(() => readUserProfile());
  const [workspacePrefs, setWorkspacePrefs] = useState(() => readWorkspacePreferences());
  const [paths, setPaths] = useState(() => readDownloadDestinations());
  const [lastPath, setLastPath] = useState(() => readLastDownloadDestination());
  const [newPath, setNewPath] = useState('');
  const [dragIndex, setDragIndex] = useState(null);
  const [notice, setNotice] = useState('');

  const showNotice = (message) => {
    setNotice(message);
    window.clearTimeout(showNotice.timer);
    showNotice.timer = window.setTimeout(() => setNotice(''), 1800);
  };

  const updateProfile = (field, value) => {
    const next = { ...profile, [field]: value };
    setProfile(next);
    writeUserProfile(next);
    showNotice('Account saved');
  };

  const updateProcessing = (field, value) => {
    const next = { ...settings, [field]: value };
    setSettings(next);
    writeProcessingSettings(next);
    showNotice('Processing preference saved');
  };

  const updateWorkspacePreference = (field, value) => {
    const next = { ...workspacePrefs, [field]: value };
    setWorkspacePrefs(next);
    writeWorkspacePreferences(next);
    showNotice('Workspace preference saved');
  };

  const savePaths = (nextPaths) => {
    setPaths(nextPaths);
    writeDownloadDestinations(nextPaths);
    showNotice('Saved paths updated');
  };

  const setPreferredPath = (path) => {
    setLastPath(path);
    writeLastDownloadDestination(path);
    showNotice('Default save folder updated');
  };

  const addPath = () => {
    const value = newPath.trim();
    if (!value) return;
    const next = [value, ...paths.filter((path) => path !== value)].slice(0, 8);
    savePaths(next);
    setPreferredPath(value);
    setNewPath('');
  };

  const removePath = (path) => {
    const next = paths.filter((item) => item !== path);
    savePaths(next);
    if (lastPath === path) {
      setPreferredPath(downloadsPath);
    }
  };

  const movePath = (index, direction) => {
    const target = index + direction;
    if (target < 0 || target >= paths.length) return;
    const next = [...paths];
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    savePaths(next);
  };

  const reorderPath = (targetIndex) => {
    if (dragIndex === null || dragIndex === targetIndex) return;
    const next = [...paths];
    const [item] = next.splice(dragIndex, 1);
    next.splice(targetIndex, 0, item);
    savePaths(next);
    setDragIndex(null);
  };

  return (
    <div className="h-full overflow-auto bg-slate-100 p-4">
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-200 bg-white px-4 py-3">
          <div>
            <h1 className="text-lg font-bold text-slate-950">Account & Preferences</h1>
            <p className="mt-1 text-xs text-slate-500">
              Local account identity, saved export folders, review behaviour, and redaction safety controls.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {notice && (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
                {notice}
              </span>
            )}
            <button
              type="button"
              onClick={() => setScreen?.('list')}
              className="rounded-md border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-50"
            >
              Back to inbox
            </button>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="space-y-4">
            <Section
              title="Profile"
              description="This is the local review profile. The employee ID will become the audit identity when multi-user accounts are switched on."
            >
              <div className="grid gap-4 md:grid-cols-[auto_1fr]">
                <div className="flex flex-col items-center gap-2 rounded-md border border-slate-200 bg-slate-50 p-4">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-900 text-xl font-black text-white">
                    {(profile.displayName || profile.email || 'L').trim().charAt(0).toUpperCase()}
                  </div>
                  <div className="text-center">
                    <div className="text-sm font-bold text-slate-900">{profile.displayName}</div>
                    <div className="text-xs font-semibold text-emerald-700">{profile.employeeId}</div>
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <Field label="Display name" value={profile.displayName} onChange={(value) => updateProfile('displayName', value)} />
                  <Field label="Employee ID" value={profile.employeeId} onChange={(value) => updateProfile('employeeId', value)} />
                  <Field label="Email or local account" value={profile.email} onChange={(value) => updateProfile('email', value)} />
                  <Field label="Role" value={profile.role} onChange={(value) => updateProfile('role', value)} />
                  <Field label="Department" value={profile.department} onChange={(value) => updateProfile('department', value)} />
                </div>
              </div>
            </Section>

            <Section
              title="Saved export folders"
              description="Use this to edit the same folder shortcuts shown in the Download redacted PDF menu."
            >
              <div className="space-y-3">
                <button
                  type="button"
                  onClick={() => setPreferredPath(downloadsPath)}
                  className={`w-full rounded-md border px-3 py-3 text-left transition ${
                    lastPath === downloadsPath
                      ? 'border-emerald-300 bg-emerald-50 text-emerald-900'
                      : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-white'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-bold">Downloads folder</span>
                    {lastPath === downloadsPath && <span className="rounded-full bg-emerald-600 px-2 py-1 text-[10px] font-bold text-white">DEFAULT</span>}
                  </div>
                  <div className="mt-1 break-all font-mono text-xs">{downloadsPath}</div>
                </button>

                {paths.length > 0 ? (
                  <div className="space-y-2">
                    {paths.map((path, index) => (
                      <div
                        key={path}
                        draggable
                        onDragStart={() => setDragIndex(index)}
                        onDragOver={(event) => event.preventDefault()}
                        onDrop={() => reorderPath(index)}
                        className={`rounded-md border px-3 py-2 ${
                          lastPath === path ? 'border-emerald-300 bg-emerald-50' : 'border-slate-200 bg-white'
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <button
                            type="button"
                            onClick={() => setPreferredPath(path)}
                            className="min-w-0 flex-1 text-left"
                          >
                            <span className="block text-xs font-bold text-slate-900">Saved folder {index + 1}</span>
                            <span className="block break-all font-mono text-xs text-slate-500">{path}</span>
                          </button>
                          <div className="flex items-center gap-1">
                            <button type="button" onClick={() => movePath(index, -1)} className="rounded border border-slate-200 px-2 py-1 text-xs font-bold text-slate-600 hover:bg-slate-50">
                              Up
                            </button>
                            <button type="button" onClick={() => movePath(index, 1)} className="rounded border border-slate-200 px-2 py-1 text-xs font-bold text-slate-600 hover:bg-slate-50">
                              Down
                            </button>
                            <button type="button" onClick={() => removePath(path)} className="rounded border border-red-200 px-2 py-1 text-xs font-bold text-red-600 hover:bg-red-50">
                              Remove
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-xs text-slate-500">
                    No extra folders saved yet.
                  </div>
                )}

                <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                  <label className="mb-1 block text-xs font-bold text-slate-500">Add new path</label>
                  <div className="flex gap-2">
                    <input
                      value={newPath}
                      onChange={(event) => setNewPath(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') addPath();
                      }}
                      placeholder={downloadsPath}
                      className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-900 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                    />
                    <button type="button" onClick={addPath} className="rounded-md bg-slate-900 px-3 py-2 text-xs font-bold text-white hover:bg-slate-800">
                      Save path
                    </button>
                  </div>
                </div>
              </div>
            </Section>
          </div>

          <div className="space-y-4">
            <Section
              title="Redaction engine"
              description="The main path stays locked to Synthetiq Redact v3 unless you explicitly allow the weaker fallback."
            >
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-2">
                  <StatusCard label="Main path" value="Synthetiq Redact v3" tone="emerald" />
                  <StatusCard label="Fallback" value={settings.allowOcrFallback ? 'Allowed' : 'Blocked'} tone={settings.allowOcrFallback ? 'amber' : 'emerald'} />
                </div>
                <ToggleRow
                  title="Allow fallback OCR engine"
                  description="Off by default. Turn this on only when you deliberately want the older OCR geometry path to run."
                  checked={settings.allowOcrFallback}
                  onChange={(value) => updateProcessing('allowOcrFallback', value)}
                  tone="amber"
                />
              </div>
            </Section>

            <Section
              title="Editor preferences"
              description="These local preferences keep the review workspace predictable without changing the redaction engine."
            >
              <div className="space-y-2">
                <ToggleRow
                  title="Show processing path"
                  description="Display whether a page used Synthetiq Redact v3 or a fallback."
                  checked={workspacePrefs.showProcessingPath}
                  onChange={(value) => updateWorkspacePreference('showProcessingPath', value)}
                />
                <ToggleRow
                  title="Show confidence badges"
                  description="Keep confidence and review labels visible beside proposed redactions."
                  checked={workspacePrefs.showConfidenceBadges}
                  onChange={(value) => updateWorkspacePreference('showConfidenceBadges', value)}
                />
                <ToggleRow
                  title="Confirm approve all"
                  description="Ask before approving every redaction on a document."
                  checked={workspacePrefs.confirmApproveAll}
                  onChange={(value) => updateWorkspacePreference('confirmApproveAll', value)}
                />
                <ToggleRow
                  title="Remember editor zoom"
                  description="Reopen documents at the last zoom level used on this PC."
                  checked={workspacePrefs.rememberEditorZoom}
                  onChange={(value) => updateWorkspacePreference('rememberEditorZoom', value)}
                />
                <ToggleRow
                  title="Sync original and redacted zoom"
                  description="Keep both document panes moving together while reviewing."
                  checked={workspacePrefs.syncPaneZoom}
                  onChange={(value) => updateWorkspacePreference('syncPaneZoom', value)}
                />
              </div>
            </Section>

            <Section
              title="Storage and security"
              description="Local-first defaults for keeping originals, redacted copies, and exports clear."
            >
              <div className="space-y-2">
                <ToggleRow
                  title="Prefer Downloads folder"
                  description="Use Downloads as the first save option unless another saved folder is selected."
                  checked={workspacePrefs.preferDownloadsFolder}
                  onChange={(value) => updateWorkspacePreference('preferDownloadsFolder', value)}
                />
                <ToggleRow
                  title="Keep original copy in local library"
                  description="Retain the unredacted source next to the redacted output for audit review."
                  checked={workspacePrefs.keepOriginalCopy}
                  onChange={(value) => updateWorkspacePreference('keepOriginalCopy', value)}
                />
                <ToggleRow
                  title="Open library after export"
                  description="After saving, move to the read-only library view for the document."
                  checked={workspacePrefs.showLibraryAfterExport}
                  onChange={(value) => updateWorkspacePreference('showLibraryAfterExport', value)}
                />
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <StatusCard label="PDF export" value="Burned image output" tone="emerald" />
                <StatusCard label="Recent cache" value="Stored locally" />
                <StatusCard label="Saved paths" value={`${paths.length + 1} total`} />
              </div>
            </Section>
          </div>
        </div>
      </div>
    </div>
  );
}
