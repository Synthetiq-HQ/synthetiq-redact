import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
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
      localStorage.removeItem('token');
      window.location.href = '/login';
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
  const source = new EventSource(`${API_BASE}/api/progress/${docId}`);
  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onData(data);
    } catch {
      onData({ status: '', message: event.data, percent: 0 });
    }
  };
  source.onerror = () => {
    source.close();
  };
  return () => source.close();
}

export async function getDocument(docId) {
  const res = await api.get(`/document/${docId}`);
  return res.data;
}

export function getImageUrl(docId, type = 'original') {
  return `${API_BASE}/api/document/${docId}/image?type=${type}`;
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

export async function listDocuments() {
  const res = await api.get('/documents');
  return res.data;
}

export async function registerUser(email, password, role = 'processor') {
  const res = await api.post('/auth/register', { email, password, role });
  return res.data;
}

export async function loginUser(email, password) {
  const res = await api.post('/auth/login', { email, password });
  return res.data;
}

export async function getMe() {
  const res = await api.get('/auth/me');
  return res.data;
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
  const res = await api.post(`/redactions/${redactionId}/reject`, { reason });
  return res.data;
}

export async function modifyRedaction(redactionId, updates) {
  const res = await api.post(`/redactions/${redactionId}/modify`, updates);
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
