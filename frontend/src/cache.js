const CACHE_PREFIX = 'synthetiq_redact_v31';
const MAX_DOC_CACHE = 25;
const DEFAULT_DOWNLOAD_PATH = 'C:\\Users\\INTERPOL\\Downloads';

const DEFAULT_PROCESSING_SETTINGS = {
  allowOcrFallback: false,
};

const DEFAULT_USER_PROFILE = {
  displayName: 'Local Reviewer',
  employeeId: 'SR-LOCAL-001',
  email: 'local_user',
  role: 'Redaction reviewer',
  department: 'Local workspace',
};

const DEFAULT_WORKSPACE_PREFERENCES = {
  showProcessingPath: true,
  showConfidenceBadges: true,
  confirmApproveAll: true,
  rememberEditorZoom: true,
  syncPaneZoom: true,
  showLibraryAfterExport: false,
  preferDownloadsFolder: true,
  keepOriginalCopy: true,
};

function readJson(key, fallback = null) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify({
      savedAt: new Date().toISOString(),
      value,
    }));
  } catch {
    // Ignore cache quota or locked-storage failures; live API data still works.
  }
}

export function readCachedDocuments() {
  return readJson(`${CACHE_PREFIX}:documents`);
}

export function writeCachedDocuments(data) {
  writeJson(`${CACHE_PREFIX}:documents`, data);
}

export function readCachedDocument(docId) {
  return readJson(`${CACHE_PREFIX}:document:${docId}`);
}

export function writeCachedDocument(docId, data) {
  writeJson(`${CACHE_PREFIX}:document:${docId}`, data);
  const indexKey = `${CACHE_PREFIX}:document-index`;
  const index = readJson(indexKey, { value: [] })?.value || [];
  const next = [String(docId), ...index.filter((id) => id !== String(docId))].slice(0, MAX_DOC_CACHE);
  writeJson(indexKey, next);
}

export function readDownloadDestinations() {
  const saved = readJson(`${CACHE_PREFIX}:download-destinations`, { value: [] })?.value;
  return Array.isArray(saved) ? saved : [];
}

export function writeDownloadDestinations(paths) {
  const unique = Array.from(new Set((Array.isArray(paths) ? paths : []).map((path) => String(path || '').trim()).filter(Boolean)));
  writeJson(`${CACHE_PREFIX}:download-destinations`, unique.slice(0, 8));
}

export function readLastDownloadDestination() {
  return readJson(`${CACHE_PREFIX}:last-download-destination`, { value: DEFAULT_DOWNLOAD_PATH })?.value || DEFAULT_DOWNLOAD_PATH;
}

export function writeLastDownloadDestination(path) {
  writeJson(`${CACHE_PREFIX}:last-download-destination`, path || '');
}

export function readProcessingSettings() {
  const saved = readJson(`${CACHE_PREFIX}:processing-settings`, { value: DEFAULT_PROCESSING_SETTINGS })?.value || {};
  return {
    ...DEFAULT_PROCESSING_SETTINGS,
    ...saved,
    allowOcrFallback: Boolean(saved.allowOcrFallback),
  };
}

export function writeProcessingSettings(settings) {
  writeJson(`${CACHE_PREFIX}:processing-settings`, {
    ...DEFAULT_PROCESSING_SETTINGS,
    ...settings,
    allowOcrFallback: Boolean(settings?.allowOcrFallback),
  });
}

export function readUserProfile() {
  const saved = readJson(`${CACHE_PREFIX}:user-profile`, { value: DEFAULT_USER_PROFILE })?.value || {};
  return {
    ...DEFAULT_USER_PROFILE,
    ...saved,
  };
}

export function writeUserProfile(profile) {
  writeJson(`${CACHE_PREFIX}:user-profile`, {
    ...DEFAULT_USER_PROFILE,
    ...profile,
    displayName: String(profile?.displayName || '').trim() || DEFAULT_USER_PROFILE.displayName,
    employeeId: String(profile?.employeeId || '').trim() || DEFAULT_USER_PROFILE.employeeId,
    email: String(profile?.email || '').trim() || DEFAULT_USER_PROFILE.email,
    role: String(profile?.role || '').trim() || DEFAULT_USER_PROFILE.role,
    department: String(profile?.department || '').trim() || DEFAULT_USER_PROFILE.department,
  });
}

export function readWorkspacePreferences() {
  const saved = readJson(`${CACHE_PREFIX}:workspace-preferences`, { value: DEFAULT_WORKSPACE_PREFERENCES })?.value || {};
  return {
    ...DEFAULT_WORKSPACE_PREFERENCES,
    ...saved,
  };
}

export function writeWorkspacePreferences(preferences) {
  writeJson(`${CACHE_PREFIX}:workspace-preferences`, {
    ...DEFAULT_WORKSPACE_PREFERENCES,
    ...Object.fromEntries(
      Object.entries(preferences || {}).map(([key, value]) => [key, Boolean(value)])
    ),
  });
}

export function getDefaultDownloadPath() {
  return DEFAULT_DOWNLOAD_PATH;
}
