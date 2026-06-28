export default function StatusBadge({ status }) {
  const statusMap = {
    processing: { class: 'status-badge--processing', label: 'Processing' },
    complete: { class: 'status-badge--complete', label: 'Complete' },
    needs_review: { class: 'status-badge--needs_review', label: 'Needs Review' },
    in_review: { class: 'status-badge--needs_review', label: 'In Review' },
    review_approved: { class: 'status-badge--complete', label: 'Approved' },
    exported: { class: 'status-badge--complete', label: 'Exported' },
    error: { class: 'status-badge--error', label: 'Error' },
    failed: { class: 'status-badge--error', label: 'Failed' },
    uploaded: { class: 'status-badge--uploaded', label: 'Uploaded' },
    preprocessing: { class: 'status-badge--preprocessing', label: 'Preprocessing' },
    ocr: { class: 'status-badge--ocr', label: 'OCR' },
    redaction: { class: 'status-badge--redaction', label: 'Redaction' },
    translation: { class: 'status-badge--translation', label: 'Language' },
    classification: { class: 'status-badge--classification', label: 'Classifying' },
    routing: { class: 'status-badge--routing', label: 'Routing' },
  };

  const mapped = statusMap[status] || { class: 'status-badge--uploaded', label: status || 'Unknown' };

  return <span className={`status-badge ${mapped.class}`}>{mapped.label}</span>;
}
