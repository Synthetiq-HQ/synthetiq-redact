const API_BASE = '/api';

/**
 * Upload a document file to the backend.
 * @param {File} file
 * @returns {Promise<{document_id: number}>}
 */
export async function uploadDocument(file, translateEnabled = false, selectedCategory = '') {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('translate', translateEnabled ? '1' : '0');
  formData.append('selected_category', selectedCategory || '');
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

/**
 * Subscribe to SSE progress updates for a document.
 * @param {number|string} docId
 * @param {(data: {status: string, message: string, percent: number}) => void} onUpdate
 * @returns {() => void} Unsubscribe function
 */
export function subscribeProgress(docId, onUpdate) {
  const source = new EventSource(`${API_BASE}/progress/${docId}`);
  source.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      onUpdate(data);
    } catch (err) {
      console.warn('Failed to parse SSE message', e.data);
    }
  };
  source.onerror = (err) => {
    console.warn('SSE error', err);
  };
  return () => {
    source.close();
  };
}

/**
 * Get full document result.
 * @param {number|string} docId
 */
export async function getDocument(docId) {
  const res = await fetch(`${API_BASE}/document/${docId}`);
  if (!res.ok) throw new Error(`Failed to get document: ${res.status}`);
  return res.json();
}

/**
 * Get image URL for a document.
 * @param {number|string} docId
 * @param {'original'|'redacted'} type
 */
export function getImageUrl(docId, type) {
  return `${API_BASE}/document/${docId}/image?type=${type}`;
}

/**
 * Get the text export download URL for a document.
 * @param {number|string} docId
 */
export function getExportUrl(docId, type = 'text') {
  return `${API_BASE}/document/${docId}/export?type=${type}`;
}

/**
 * Approve a document.
 * @param {number|string} docId
 */
export async function approveDocument(docId) {
  const res = await fetch(`${API_BASE}/document/${docId}/approve`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Approve failed: ${res.status}`);
  return res.json();
}

/**
 * Flag a document for human review.
 * @param {number|string} docId
 */
export async function flagForReview(docId) {
  const res = await fetch(`${API_BASE}/document/${docId}/review`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Flag failed: ${res.status}`);
  return res.json();
}

/**
 * List all documents.
 */
export async function listDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error(`Failed to list documents: ${res.status}`);
  return res.json();
}

/**
 * Get department mappings.
 */
export async function getDepartments() {
  const res = await fetch(`${API_BASE}/departments`);
  if (!res.ok) throw new Error(`Failed to get departments: ${res.status}`);
  return res.json();
}
