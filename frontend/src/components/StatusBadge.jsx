export default function StatusBadge({ status }) {
  const statusMap = {
    processing: { class: 'status-badge--processing', label: 'Processing' },
    complete: { class: 'status-badge--complete', label: 'Complete' },
    needs_review: { class: 'status-badge--needs_review', label: 'Needs Review' },
    error: { class: 'status-badge--error', label: 'Error' },
    uploaded: { class: 'status-badge--uploaded', label: 'Uploaded' },
    preprocessing: { class: 'status-badge--preprocessing', label: 'Preprocessing' },
    ocr: { class: 'status-badge--ocr', label: 'OCR' },
    redaction: { class: 'status-badge--redaction', label: 'Redaction' },
    translation: { class: 'status-badge--translation', label: 'Translation' },
    classification: { class: 'status-badge--classification', label: 'Classifying' },
    routing: { class: 'status-badge--routing', label: 'Routing' },
  };

  const mapped = statusMap[status] || { class: 'status-badge--uploaded', label: status || 'Unknown' };

  return <span className={`status-badge ${mapped.class}`}>{mapped.label}</span>;
}
