import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';
const TOKEN_KEY = 'synthetiq_redact_token';
const USER_KEY = 'synthetiq_redact_user';
export const MULTI_USER_AUTH_ENABLED = import.meta.env.VITE_ENABLE_MULTI_USER_AUTH === '1';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

function getStoredToken() {
  const token = sessionStorage.getItem(TOKEN_KEY);
  const legacyToken = localStorage.getItem('token');
  if (!token && legacyToken) {
    sessionStorage.setItem(TOKEN_KEY, legacyToken);
    localStorage.removeItem('token');
    return legacyToken;
  }
  return token;
}

function storeAuthSession(data) {
  sessionStorage.setItem(TOKEN_KEY, data.token);
  sessionStorage.setItem(USER_KEY, JSON.stringify(data.user));
  localStorage.removeItem('token');
  return data;
}

export function clearAuthSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  localStorage.removeItem('token');
}

export function getStoredUser() {
  try {
    const raw = sessionStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (MULTI_USER_AUTH_ENABLED) {
        clearAuthSession();
        window.dispatchEvent(new Event('synthetiq:auth-expired'));
      }
    }
    return Promise.reject(error);
  }
);

// --- Named API helpers used by components ---

export async function uploadDocument(file, translateEnabled, selectedCategory) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('translate', translateEnabled ? 'true' : 'false');
  if (selectedCategory) {
    formData.append('category', selectedCategory);
  }
  const res = await api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export function subscribeProgress(docId, onData) {
  let cancelled = false;
  const terminalStatuses = new Set(['complete', 'needs_review', 'review_approved', 'exported', 'failed', 'error']);
  const statusPercent = {
    uploaded: 5,
    preprocessing: 15,
    ocr: 30,
    redaction: 50,
    translation: 60,
    classification: 75,
    routing: 85,
    complete: 100,
    needs_review: 100,
    review_approved: 100,
    exported: 100,
    failed: 100,
    error: 100,
  };
  const statusMessage = {
    uploaded: 'Document uploaded...',
    preprocessing: 'Preprocessing document...',
    ocr: 'Extracting text with OCR...',
    redaction: 'Detecting and redacting sensitive data...',
    translation: 'Checking document language...',
    classification: 'Classifying document...',
    routing: 'Computing urgency and routing...',
    complete: 'Processing complete.',
    needs_review: 'Processing complete; human review required.',
    review_approved: 'Review complete.',
    exported: 'Export complete.',
    failed: 'Processing failed.',
    error: 'Processing failed.',
  };

  const poll = async () => {
    if (cancelled) return;
    try {
      const data = await getDocument(docId);
      const status = data.status || 'uploaded';
      const payload = {
        status,
        message: data.needs_review_reason || statusMessage[status] || 'Processing...',
        percent: statusPercent[status] ?? 0,
      };
      onData(payload);
      if (!terminalStatuses.has(status)) {
        window.setTimeout(poll, 800);
      }
    } catch (error) {
      const status = error.response?.status === 404 ? 'error' : 'failed';
      const data = {
        status,
        message: error.response?.data?.detail || 'Unable to read processing status.',
        percent: 100,
      };
      onData(data);
    }
  };

  poll();
  return () => {
    cancelled = true;
  };
}

export async function getDocument(docId) {
  const res = await api.get(`/document/${docId}`);
  return res.data;
}

export async function getDocumentPages(docId) {
  const res = await api.get(`/document/${docId}/pages`);
  return res.data;
}

export async function getDocumentPage(docId, pageNumber = 1) {
  const res = await api.get(`/document/${docId}/pages/${pageNumber}`);
  return res.data;
}

export function getImageUrl(docId, type = 'original') {
  return `${API_BASE}/api/document/${docId}/image?type=${type}`;
}

export async function getImageBlobUrl(docId, type = 'original') {
  const res = await api.get(`/document/${docId}/image`, {
    params: { type },
    responseType: 'blob',
  });
  return URL.createObjectURL(res.data);
}

export async function getPageImageBlobUrl(docId, pageNumber = 1, type = 'original') {
  const res = await api.get(`/document/${docId}/pages/${pageNumber}/image`, {
    params: { type },
    responseType: 'blob',
  });
  return URL.createObjectURL(res.data);
}

export async function approveDocument(docId) {
  const res = await api.post(`/document/${docId}/approve`);
  return res.data;
}

export async function flagForReview(docId) {
  const res = await api.post(`/document/${docId}/review`);
  return res.data;
}

export function getExportUrl(docId, type = 'docx') {
  return `${API_BASE}/api/document/${docId}/export?type=${type}`;
}

export async function downloadExport(docId, type = 'text') {
  const res = await api.get(`/document/${docId}/export`, {
    params: { type },
    responseType: 'blob',
  });
  const contentDisposition = res.headers['content-disposition'] || '';
  const match = contentDisposition.match(/filename="?([^"]+)"?/i);
  const filename = match?.[1] || `document_${docId}_${type}.dat`;
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function listDocuments() {
  const res = await api.get('/documents');
  return res.data;
}

export async function registerUser(email, password, role = 'processor') {
  const formData = new FormData();
  formData.append('email', email);
  formData.append('password', password);
  formData.append('role', role);
  const res = await api.post('/auth/register', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return storeAuthSession(res.data);
}

export async function loginUser(email, password) {
  const formData = new FormData();
  formData.append('email', email);
  formData.append('password', password);
  const res = await api.post('/auth/login', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return storeAuthSession(res.data);
}

export async function getMe() {
  const res = await api.get('/auth/me');
  return res.data;
}

export async function logoutUser() {
  try {
    await api.post('/auth/logout');
  } finally {
    clearAuthSession();
  }
}

export async function getReviewQueue(priority = 'all') {
  const res = await api.get('/review-queue', { params: { priority } });
  return res.data;
}

export async function approveRedaction(redactionId) {
  const res = await api.post(`/redactions/${redactionId}/approve`);
  return res.data;
}

export async function rejectRedaction(redactionId, reason = '') {
  const formData = new FormData();
  formData.append('reason', reason);
  const res = await api.post(`/redactions/${redactionId}/reject`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function modifyRedaction(redactionId, updates) {
  const formData = new FormData();
  if (updates.new_bbox) formData.append('new_bbox', JSON.stringify(updates.new_bbox));
  if (updates.new_type) formData.append('new_type', updates.new_type);
  if (updates.reason) formData.append('reason', updates.reason);
  const res = await api.post(`/redactions/${redactionId}/modify`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function createManualRedaction(docId, bbox, redactionType = 'manual', reason = '', pageNumber = 1) {
  const formData = new FormData();
  formData.append('bbox', JSON.stringify(bbox));
  formData.append('redaction_type', redactionType);
  formData.append('reason', reason);
  const res = await api.post(`/document/${docId}/pages/${pageNumber}/redactions`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function createTextRedaction(docId, {
  selectedText,
  selectionStart,
  selectionEnd,
  redactionType = 'manual',
  reason = '',
  pageNumber = 1,
}) {
  const formData = new FormData();
  formData.append('selected_text', selectedText);
  if (Number.isFinite(selectionStart)) formData.append('selection_start', String(selectionStart));
  if (Number.isFinite(selectionEnd)) formData.append('selection_end', String(selectionEnd));
  formData.append('redaction_type', redactionType);
  formData.append('reason', reason);
  const res = await api.post(`/document/${docId}/pages/${pageNumber}/redactions/from-text`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getDocumentHistory(docId) {
  const res = await api.get(`/document/${docId}/history`);
  return res.data;
}

export async function undoLastAction(docId) {
  const res = await api.post(`/document/${docId}/undo-last`);
  return res.data;
}

export async function verifyExport(docId) {
  const res = await api.post(`/document/${docId}/verify-export`);
  return res.data;
}

export async function approveAllRedactions(docId) {
  const res = await api.post(`/document/${docId}/approve-all`);
  return res.data;
}

export async function assignReview(docId) {
  const res = await api.post(`/document/${docId}/assign-review`);
  return res.data;
}

export async function createBatch(files, translateEnabled = false) {
  const formData = new FormData();
  files.forEach((f) => formData.append('files', f));
  formData.append('translate', translateEnabled ? 'true' : 'false');
  const res = await api.post('/batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getBatchStatus(jobId) {
  const res = await api.get(`/batch/${jobId}`);
  return res.data;
}

export async function getAnalyticsDashboard(days = 30) {
  const res = await api.get('/analytics/dashboard', { params: { days } });
  return res.data;
}

export default api;
