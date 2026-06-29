import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api, {
  approveAllRedactions,
  createManualRedaction,
  createTextRedaction,
  getDocumentHistory,
  getDocumentPage,
  getImageBlobUrl,
  getPageImageBlobUrl,
  modifyRedaction,
  rejectRedaction as rejectRedactionApi,
  subscribeProgress,
  undoLastAction,
  verifyExport,
} from '../api';
import { readCachedDocument, writeCachedDocument } from '../cache';
import ExportMenu from './ExportMenu';

const VIEW_MODES = [
  { id: 'original', label: 'Original' },
  { id: 'redacted', label: 'Redacted' },
  { id: 'both', label: 'Both' },
];

const MANUAL_TYPES = [
  'manual',
  'person_name',
  'address',
  'phone',
  'email',
  'dob',
  'child_age',
  'council_ref',
  'signature',
  'medical_details',
  'notes',
];

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function bboxToRect(redaction) {
  const points = redaction?.bbox?.bbox;
  if (!Array.isArray(points) || points.length !== 4) return null;
  const xs = points.map((point) => Number(point[0]));
  const ys = points.map((point) => Number(point[1]));
  if (xs.some(Number.isNaN) || ys.some(Number.isNaN)) return null;
  const x = Math.min(...xs);
  const y = Math.min(...ys);
  return {
    x,
    y,
    width: Math.max(...xs) - x,
    height: Math.max(...ys) - y,
  };
}

function rectToBbox(rect) {
  const x1 = rect.x;
  const y1 = rect.y;
  const x2 = rect.x + rect.width;
  const y2 = rect.y + rect.height;
  return {
    bbox: [
      [x1, y1],
      [x2, y1],
      [x2, y2],
      [x1, y2],
    ],
  };
}

function rectsEqual(first, second) {
  if (!first || !second) return false;
  return ['x', 'y', 'width', 'height'].every((key) => (
    Math.abs(Number(first[key]) - Number(second[key])) < 0.5
  ));
}

function confidenceLabel(confidence) {
  if (confidence >= 0.8) return 'High';
  if (confidence >= 0.55) return 'Medium';
  return 'Low';
}

function normaliseEngineStatus(status, engineUsed = '') {
  if (status?.label) return status;
  if (engineUsed.includes('synthetiq_redact_v3_glm_geometry')) {
    return {
      mode: 'main',
      label: 'Synthetiq Redact v3',
      detail: 'GLM OCR text with value-level geometry mapping',
      engine_used: engineUsed,
    };
  }
  if (engineUsed.includes('fallback')) {
    return {
      mode: 'fallback',
      label: 'Fallback',
      detail: 'OCR word-box fallback used',
      engine_used: engineUsed,
    };
  }
  if (engineUsed.includes('synthetiq_redact_v3_unavailable') || engineUsed.includes('synthetiq_redact_v3_config_off')) {
    return {
      mode: 'blocked',
      label: 'v3 unavailable',
      detail: 'Synthetiq Redact v3 could not run and fallback is off',
      engine_used: engineUsed,
    };
  }
  return {
    mode: 'pending',
    label: 'Selecting engine',
    detail: 'Processing path will appear once redaction starts',
    engine_used: engineUsed,
  };
}

function engineBadgeClass(mode) {
  // Gold = the best/main engine (Synthetiq Redact v3). Red is reserved for genuine
  // problems (blocked) so the UI never looks like an error when nothing is wrong.
  if (mode === 'main') return 'border-amber-300 bg-amber-50 text-amber-800';
  if (mode === 'fallback') return 'border-orange-300 bg-orange-50 text-orange-800';
  if (mode === 'blocked') return 'border-red-300 bg-red-50 text-red-900';
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function noticeClass(message = '') {
  const text = String(message).toLowerCase();
  if (text.includes('saved')) return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  if (text.includes('cached')) return 'border-amber-200 bg-amber-50 text-amber-800';
  if (text.includes('backend') || text.includes('loading') || text.includes('starting')) {
    return 'border-blue-200 bg-blue-50 text-blue-700';
  }
  return 'border-slate-200 bg-white text-slate-700';
}

// Short preview of the actual redacted text for the list/legend.
function redactionValuePreview(redaction, max = 30) {
  const value = String(redaction?.original_value || '').trim();
  if (!value || value === '[image model candidate]') return '';
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

// A detected (non-manual) box below this confidence is treated as "needs review":
// shown amber/dashed so a reviewer knows to check it before approving.
function isReviewNeeded(redaction) {
  if (!redaction) return false;
  if (redaction.status === 'approved' || redaction.status === 'rejected') return false;
  if (redaction.method === 'manual' || redaction.method === 'text_selection') return false;
  return typeof redaction.confidence === 'number' && redaction.confidence < 0.6;
}

function overlayStyle(redaction, isSelected) {
  const rejected = redaction.status === 'rejected';
  const approved = redaction.status === 'approved';
  const manual = redaction.method === 'manual' || redaction.method === 'text_selection';
  const review = isReviewNeeded(redaction);
  return {
    backgroundColor: rejected
      ? 'rgba(220, 38, 38, 0.12)'
      : approved
        ? 'rgba(0, 0, 0, 0.76)'
        : manual
          ? 'rgba(15, 23, 42, 0.42)'
          : review
            ? 'rgba(217, 119, 6, 0.32)'
            : 'rgba(180, 83, 9, 0.30)',
    border: isSelected
      ? '2px solid #2563eb'
      : rejected
        ? '2px dashed #dc2626'
        : manual
          ? '2px solid #0f172a'
          : review
            ? '2px dashed #d97706'
            : '2px solid #b45309',
  };
}

function getSelectionOffsets(container) {
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;

  const before = range.cloneRange();
  before.selectNodeContents(container);
  before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  const text = range.toString();
  const end = start + text.length;
  if (!text.trim()) return null;
  return { start, end, text };
}

function buildHighlightRanges(text, redactions) {
  const ranges = [];
  const lower = text.toLowerCase();
  const normalisedChars = [];
  const normalisedToSource = [];
  Array.from(text).forEach((char, index) => {
    if (/[a-z0-9]/i.test(char)) {
      normalisedChars.push(char.toLowerCase());
      normalisedToSource.push(index);
    }
  });
  const normalisedText = normalisedChars.join('');

  for (const redaction of redactions) {
    if (redaction.status === 'rejected') continue;
    const value = String(redaction.original_value || '').trim();
    if (value.length < 2) continue;
    const needle = value.toLowerCase();
    let matched = false;
    let index = lower.indexOf(needle);
    while (index >= 0) {
      ranges.push({ start: index, end: index + value.length, redaction });
      matched = true;
      index = lower.indexOf(needle, index + value.length);
    }
    if (matched) continue;

    const normalisedNeedle = value.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (normalisedNeedle.length < 2) continue;
    let normalisedIndex = normalisedText.indexOf(normalisedNeedle);
    while (normalisedIndex >= 0) {
      const sourceStart = normalisedToSource[normalisedIndex];
      const sourceEnd = normalisedToSource[normalisedIndex + normalisedNeedle.length - 1] + 1;
      if (Number.isFinite(sourceStart) && Number.isFinite(sourceEnd) && sourceEnd > sourceStart) {
        ranges.push({ start: sourceStart, end: sourceEnd, redaction });
      }
      normalisedIndex = normalisedText.indexOf(normalisedNeedle, normalisedIndex + normalisedNeedle.length);
    }
  }

  return ranges
    .sort((a, b) => a.start - b.start || b.end - a.end)
    .reduce((acc, range) => {
      const last = acc[acc.length - 1];
      if (!last || range.start >= last.end) {
        acc.push(range);
      }
      return acc;
    }, []);
}

function renderPlainSelectableText(text, startOffset, selection, onSelectText) {
  return text.split(/(\s+)/).map((part, index, parts) => {
    const offset = parts.slice(0, index).join('').length + startOffset;
    if (!part || /^\s+$/.test(part)) return part;
    const tokenStart = offset;
    const tokenEnd = offset + part.length;
    const selected = selection?.start === tokenStart && selection?.end === tokenEnd;
    return (
      <button
        key={`${tokenStart}-${tokenEnd}-${part}`}
        type="button"
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => onSelectText({ start: tokenStart, end: tokenEnd, text: part })}
        onDoubleClick={(event) => {
          event.preventDefault();
          onSelectText({ start: tokenStart, end: tokenEnd, text: part });
        }}
        className={`rounded-sm px-0.5 text-left ${
          selected
            ? 'bg-blue-100 text-blue-950 outline outline-1 outline-blue-400'
            : 'hover:bg-blue-50 hover:text-blue-950'
        }`}
      >
        {part}
      </button>
    );
  });
}

function renderHighlightedText(text, ranges, onRedactionClick, onSelectText, selection) {
  if (!text) return <span className="text-slate-400">No OCR text available.</span>;
  if (!ranges.length) return renderPlainSelectableText(text, 0, selection, onSelectText);

  const parts = [];
  let cursor = 0;
  ranges.forEach((range, index) => {
    if (range.start > cursor) {
      parts.push(...renderPlainSelectableText(text.slice(cursor, range.start), cursor, selection, onSelectText));
    }
    parts.push(
      <button
        key={`${range.start}-${range.end}-${index}`}
        type="button"
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => onRedactionClick(range.redaction)}
        className="rounded-sm bg-amber-200 px-0.5 text-left text-slate-950 outline outline-1 outline-amber-400"
      >
        {text.slice(range.start, range.end)}
      </button>
    );
    cursor = range.end;
  });
  if (cursor < text.length) {
    parts.push(...renderPlainSelectableText(text.slice(cursor), cursor, selection, onSelectText));
  }
  return parts;
}

function PagePreviewSkeleton({ title, message, failed = false }) {
  return (
    <div className="flex min-h-full items-start justify-center">
      <div
        className="relative w-full max-w-[760px] overflow-hidden rounded-sm bg-white p-8 shadow-sm ring-1 ring-slate-300"
        style={{ minHeight: 'min(980px, calc(100vh - 190px))' }}
      >
        <div className="mb-6 flex items-center gap-2 text-sm font-bold text-slate-800">
          <span className={`h-2.5 w-2.5 rounded-full ${failed ? 'bg-amber-500' : 'bg-blue-600 animate-pulse'}`} />
          {title}
        </div>
        <div className="space-y-4">
          <div className="h-5 w-3/5 rounded bg-slate-200 processing-shimmer" />
          <div className="h-4 w-2/5 rounded bg-slate-200 processing-shimmer" />
          <div className="h-4 w-1/2 rounded bg-slate-200 processing-shimmer" />
          <div className="space-y-3 pt-5">
            <div className="h-4 w-4/5 rounded bg-slate-200 processing-shimmer" />
            <div className="h-4 w-2/3 rounded bg-slate-200 processing-shimmer" />
            <div className="h-4 w-3/4 rounded bg-slate-200 processing-shimmer" />
          </div>
          <div className="space-y-3 pt-6">
            <div className="h-4 w-full rounded bg-slate-200 processing-shimmer" />
            <div className="h-4 w-11/12 rounded bg-slate-200 processing-shimmer" />
            <div className="h-4 w-10/12 rounded bg-slate-200 processing-shimmer" />
            <div className="h-4 w-2/3 rounded bg-slate-200 processing-shimmer" />
          </div>
        </div>
        <div className="absolute inset-x-0 bottom-0 border-t border-slate-100 bg-white/90 px-8 py-4 text-xs text-slate-500">
          {message}
        </div>
      </div>
    </div>
  );
}

function DocumentCanvas({
  title,
  imageUrl,
  imageSize,
  setImageSize,
  zoom,
  redactions,
  selectedRedaction,
  setSelectedRedaction,
  showOverlays,
  drawEnabled,
  stageRef,
  scrollRef,
  onScroll,
  onWheelZoom,
  beginDraw,
  continueDraw,
  finishDraw,
  draftRect,
  pendingCreates = [],
  pendingChange,
  startEdit,
  clearSelection,
  disabledOverlay,
  liveRedactionPreview = false,
  previewLoading = false,
  processingActive = false,
  processingMessage = '',
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const panSessionRef = useRef(null);
  const pendingEditId = pendingChange?.mode === 'edit' ? pendingChange.redactionId : null;
  const previewRedactions = redactions
    .filter((redaction) => redaction.status !== 'rejected')
    .map((redaction) => {
      const rect = pendingEditId === redaction.id ? pendingChange.rect : bboxToRect(redaction);
      return rect ? { redaction, rect } : null;
    })
    .filter(Boolean);

  useEffect(() => {
    setImageFailed(false);
  }, [imageUrl]);

  useEffect(() => {
    if (!isPanning) return undefined;

    const handleMouseMove = (event) => {
      const session = panSessionRef.current;
      if (!session?.scrollElement) return;
      event.preventDefault();
      const dx = event.clientX - session.startX;
      const dy = event.clientY - session.startY;
      session.scrollElement.scrollLeft = session.scrollLeft - dx;
      session.scrollElement.scrollTop = session.scrollTop - dy;
      onScroll?.();
    };

    const stopPanning = () => {
      panSessionRef.current = null;
      setIsPanning(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', stopPanning);
    window.addEventListener('blur', stopPanning);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', stopPanning);
      window.removeEventListener('blur', stopPanning);
    };
  }, [isPanning, onScroll]);

  const startPan = (event) => {
    if (event.button !== 1 || !scrollRef?.current) return;
    event.preventDefault();
    event.stopPropagation();
    panSessionRef.current = {
      scrollElement: scrollRef.current,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: scrollRef.current.scrollLeft,
      scrollTop: scrollRef.current.scrollTop,
    };
    setIsPanning(true);
  };

  const handleStageMouseDown = (event) => {
    if (event.button !== 0) return;
    if (drawEnabled) {
      beginDraw?.(event);
    } else {
      clearSelection?.();
    }
  };

  const previewUnavailable = !imageUrl || imageFailed;
  const previewMessage = processingMessage
    || (previewLoading
      ? 'Loading the page image from the local backend.'
      : 'Preview is not ready yet. The editor will refresh it when the backend responds.');

  return (
    <section className="flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="mb-2 flex h-8 items-center justify-between text-xs font-bold uppercase tracking-wide text-slate-500">
        <span>{title}</span>
        {imageSize?.width ? (
          <span className="font-semibold normal-case tracking-normal text-slate-400">
            {imageSize.width} x {imageSize.height}
          </span>
        ) : null}
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          onWheel={(event) => onWheelZoom?.(event, scrollRef?.current)}
          onMouseDown={startPan}
          onAuxClick={(event) => {
            if (event.button === 1) event.preventDefault();
          }}
          className={`h-full overscroll-contain overflow-auto rounded-md border border-slate-300 bg-slate-300 p-3 ${
            isPanning ? 'cursor-grabbing select-none' : 'cursor-grab'
          }`}
        >
          {!previewUnavailable ? (
            <div
              ref={stageRef}
              onMouseDown={handleStageMouseDown}
              onMouseMove={continueDraw}
              onMouseUp={finishDraw}
              onMouseLeave={finishDraw}
              className={`relative inline-block select-none bg-white shadow-sm ring-1 ring-slate-400 ${
                drawEnabled ? 'cursor-crosshair' : isPanning ? 'cursor-grabbing' : 'cursor-grab'
              }`}
              style={{
                width: imageSize?.width ? imageSize.width * zoom : undefined,
                height: imageSize?.height ? imageSize.height * zoom : undefined,
              }}
            >
            <img
              src={imageUrl}
              alt={`${title} document`}
              draggable={false}
              onLoad={(event) => {
                setImageSize({
                  width: event.currentTarget.naturalWidth,
                  height: event.currentTarget.naturalHeight,
                });
              }}
              onError={() => setImageFailed(true)}
              className="block h-full w-full"
            />

            {processingActive && (
              <div className="pointer-events-none absolute inset-x-0 top-0 z-30 h-1 overflow-hidden bg-blue-100/70">
                <div className="processing-scanline h-full w-1/3 rounded-full bg-blue-600/80" />
              </div>
            )}

            {liveRedactionPreview && previewRedactions.map(({ redaction, rect }) => (
              <div
                key={`live-${redaction.id}`}
                className="pointer-events-none absolute bg-black"
                style={{
                  left: rect.x * zoom,
                  top: rect.y * zoom,
                  width: Math.max(1, rect.width * zoom),
                  height: Math.max(1, rect.height * zoom),
                  zIndex: 4,
                }}
              />
            ))}

            {liveRedactionPreview && draftRect && (
              <div
                className="pointer-events-none absolute bg-black"
                style={{
                  left: draftRect.x * zoom,
                  top: draftRect.y * zoom,
                  width: Math.max(1, draftRect.width * zoom),
                  height: Math.max(1, draftRect.height * zoom),
                  zIndex: 4,
                }}
              />
            )}

            {liveRedactionPreview && pendingCreates.map((rect, index) => (
              <div
                key={`pending-live-${index}`}
                className="pointer-events-none absolute bg-black"
                style={{
                  left: rect.x * zoom,
                  top: rect.y * zoom,
                  width: Math.max(1, rect.width * zoom),
                  height: Math.max(1, rect.height * zoom),
                  zIndex: 4,
                }}
              />
            ))}

            {liveRedactionPreview && pendingChange?.mode === 'create' && (
              <div
                className="pointer-events-none absolute bg-black"
                style={{
                  left: pendingChange.rect.x * zoom,
                  top: pendingChange.rect.y * zoom,
                  width: Math.max(1, pendingChange.rect.width * zoom),
                  height: Math.max(1, pendingChange.rect.height * zoom),
                  zIndex: 4,
                }}
              />
            )}

            {showOverlays && previewRedactions.map(({ redaction, rect }) => {
                const selected = selectedRedaction?.id === redaction.id;
                return (
                  <button
                    type="button"
                    key={redaction.id}
                    onMouseDown={(event) => {
                      if (redaction.status === 'rejected') return;
                      event.stopPropagation();
                      event.preventDefault();
                      startEdit(event, redaction, 'move');
                    }}
                    onClick={(event) => {
                      event.stopPropagation();
                      setSelectedRedaction(redaction);
                    }}
                    className="absolute text-left"
                    style={{
                      left: rect.x * zoom,
                      top: rect.y * zoom,
                      width: Math.max(1, rect.width * zoom),
                      height: Math.max(1, rect.height * zoom),
                      ...overlayStyle(redaction, selected),
                      zIndex: selected ? 15 : 5,
                      boxShadow: selected ? '0 0 0 3px rgba(37, 99, 235, 0.22)' : 'none',
                    }}
                    aria-label={`Select ${redaction.type || 'redaction'}`}
                  >
                    {selected && redaction.status !== 'rejected' && (
                      <>
                        {['nw', 'ne', 'sw', 'se'].map((handle) => (
                          <span
                            key={handle}
                            onMouseDown={(event) => {
                              event.stopPropagation();
                              event.preventDefault();
                              startEdit(event, redaction, handle);
                            }}
                            className={`absolute h-3 w-3 rounded-sm border border-white bg-blue-700 shadow-sm ${
                              handle.includes('n') ? '-top-1.5' : '-bottom-1.5'
                            } ${handle.includes('w') ? '-left-1.5' : '-right-1.5'}`}
                          />
                        ))}
                      </>
                    )}
                  </button>
                );
              })}

            {showOverlays && pendingCreates.map((rect, index) => (
              <div
                key={`pending-create-${index}`}
                className="pointer-events-none absolute border-2 border-blue-700 bg-blue-500/20"
                style={{
                  left: rect.x * zoom,
                  top: rect.y * zoom,
                  width: rect.width * zoom,
                  height: rect.height * zoom,
                  zIndex: 6,
                }}
              />
            ))}

            {(draftRect || (drawEnabled && pendingChange?.mode === 'create' ? pendingChange.rect : null)) && drawEnabled && (
              <div
                className="absolute border-2 border-blue-700 bg-blue-500/20"
                style={{
                  left: (draftRect || pendingChange.rect).x * zoom,
                  top: (draftRect || pendingChange.rect).y * zoom,
                  width: (draftRect || pendingChange.rect).width * zoom,
                  height: (draftRect || pendingChange.rect).height * zoom,
                }}
              />
            )}
            </div>
          ) : (
            <PagePreviewSkeleton
              title={processingActive || previewLoading ? 'Preparing page preview' : 'Waiting for page preview'}
              message={previewMessage}
              failed={imageFailed && !previewLoading && !processingActive}
            />
          )}
        </div>
        {disabledOverlay && (
          <div className="absolute inset-3 z-20 flex items-center justify-center rounded-sm bg-slate-200/70 ring-1 ring-slate-400/30 backdrop-blur-[1px]">
            <div className="rounded-md border border-slate-300 bg-white/90 px-3 py-2 text-xs font-semibold text-slate-600 shadow-sm">
              Draw and adjust boxes on the original page
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

export default function ReviewStudio({ docId, setScreen }) {
  const originalStageRef = useRef(null);
  const originalScrollRef = useRef(null);
  const redactedScrollRef = useRef(null);
  const scrollSyncRef = useRef(false);
  const textRef = useRef(null);
  const cacheHydratedRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const documentDataRef = useRef(null);

  const [documentData, setDocumentData] = useState(null);
  const [pages, setPages] = useState([]);
  const [currentPageNumber, setCurrentPageNumber] = useState(1);
  const [history, setHistory] = useState([]);
  const [redactions, setRedactions] = useState([]);
  const [selectedRedaction, setSelectedRedaction] = useState(null);
  const [selection, setSelection] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [imageUrls, setImageUrls] = useState({});
  const [imageSizes, setImageSizes] = useState({});
  const [imagesLoading, setImagesLoading] = useState(false);
  const [imageRevision, setImageRevision] = useState(0);
  const [viewMode, setViewMode] = useState('both');
  const [zoom, setZoom] = useState(0.75);
  const [drawMode, setDrawMode] = useState(false);
  const [manualType, setManualType] = useState('manual');
  const [draftRect, setDraftRect] = useState(null);
  const [pendingCreates, setPendingCreates] = useState([]);
  const [drawStart, setDrawStart] = useState(null);
  const [pendingChange, setPendingChange] = useState(null);
  const [editSession, setEditSession] = useState(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [notice, setNotice] = useState('');
  const [reconnectTick, setReconnectTick] = useState(0);
  const [processingProgress, setProcessingProgress] = useState(null);

  useEffect(() => {
    documentDataRef.current = documentData;
  }, [documentData]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectTimerRef.current) return;
    reconnectTimerRef.current = window.setTimeout(() => {
      reconnectTimerRef.current = null;
      setReconnectTick((value) => value + 1);
    }, 1500);
  }, []);

  useEffect(() => () => {
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, [docId]);

  const clearReviewSelection = useCallback(() => {
    setSelectedRedaction(null);
    setSelection(null);
    setPendingChange(null);
    setPendingCreates([]);
    setDraftRect(null);
    setDrawStart(null);
    setEditSession(null);
    setDrawMode(false);
    window.getSelection()?.removeAllRanges();
  }, []);

  const currentPage = useMemo(
    () => pages.find((page) => Number(page.page_number) === Number(currentPageNumber)) || pages[0] || null,
    [pages, currentPageNumber]
  );

  const pageRedactions = useMemo(
    () => redactions.filter((redaction) => Number(redaction.page_number || 1) === Number(currentPageNumber)),
    [redactions, currentPageNumber]
  );

  // Prefer the clean transcription (GLM-OCR when enabled) over the raw OCR text,
  // which is garbled on handwriting.
  const ocrText = currentPage?.ocr?.clean_text
    || currentPage?.ocr?.extracted_text
    || documentData?.ocr?.clean_text
    || documentData?.ocr?.extracted_text
    || '';
  const activeRedactions = useMemo(
    () => pageRedactions.filter((redaction) => redaction.status !== 'rejected'),
    [pageRedactions]
  );

  const hasAnyWarnings = useMemo(
    () => pages.some((page) => (page.warning_count || page.vision_warnings?.length || 0) > 0),
    [pages]
  );

  const highlightRanges = useMemo(
    () => buildHighlightRanges(ocrText, activeRedactions),
    [ocrText, activeRedactions]
  );

  const selectedCanBeRemoved = Boolean(
    selectedRedaction && selectedRedaction.status !== 'rejected'
  );
  const activeProcessing = processingProgress && !['complete', 'needs_review', 'in_review', 'review_approved', 'exported'].includes(processingProgress.status);
  const processingFailed = ['failed', 'error'].includes(processingProgress?.status || documentData?.status || '');
  const engineStatus = useMemo(
    () => normaliseEngineStatus(
      processingProgress?.engine_status || documentData?.engine_status,
      processingProgress?.engine_used || documentData?.engine_used || ''
    ),
    [documentData?.engine_status, documentData?.engine_used, processingProgress?.engine_status, processingProgress?.engine_used]
  );
  const progressPercent = processingFailed ? 100 : (processingProgress?.percent ?? 5);

  const loadDocument = useCallback(async () => {
    setError('');
    const cached = readCachedDocument(docId)?.value;
    if (cached && cacheHydratedRef.current !== docId) {
      cacheHydratedRef.current = docId;
      setDocumentData(cached);
      const cachedPages = cached.pages?.length
        ? cached.pages
        : [{
          page_number: 1,
          ocr: cached.ocr,
          redactions: cached.redactions || [],
          warning_count: 0,
          redaction_count: (cached.redactions || []).filter((redaction) => redaction.status !== 'rejected').length,
        }];
      setPages(cachedPages);
      setRedactions(cached.redactions || []);
      setLoading(false);
    }
    try {
      const res = await api.get(`/document/${docId}`);
      setDocumentData(res.data);
      writeCachedDocument(docId, res.data);
      const nextPages = res.data.pages?.length
        ? res.data.pages
        : [{
          page_number: 1,
          ocr: res.data.ocr,
          redactions: res.data.redactions || [],
          warning_count: 0,
          redaction_count: (res.data.redactions || []).filter((redaction) => redaction.status !== 'rejected').length,
        }];
      setPages(nextPages);
      setCurrentPageNumber((pageNumber) => (
        nextPages.some((page) => Number(page.page_number) === Number(pageNumber))
          ? pageNumber
          : nextPages[0]?.page_number || 1
      ));
      setRedactions(res.data.redactions || []);
      setNotice((current) => (
        current.includes('cached document') || current.includes('local backend') ? '' : current
      ));
    } catch (err) {
      const hasUsableCache = Boolean(cached || documentDataRef.current);
      if (!err.response && hasUsableCache) {
        setError('');
        setNotice('Showing cached document while the local backend starts. Live data will refresh automatically.');
        scheduleReconnect();
        return;
      }
      if (!err.response) {
        setError('');
        setNotice('Starting local backend. The document will open automatically when it is ready.');
        scheduleReconnect();
        return;
      }
      setError(err.response?.data?.detail || 'Document could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [docId, scheduleReconnect]);

  useEffect(() => {
    loadDocument();
  }, [loadDocument, reconnectTick]);

  useEffect(() => {
    const terminal = new Set(['complete', 'needs_review', 'in_review', 'review_approved', 'exported', 'failed', 'error']);
    const status = documentData?.status;
    if (!docId || !status || terminal.has(status)) {
      setProcessingProgress(null);
      return undefined;
    }
    const unsubscribe = subscribeProgress(docId, async (data) => {
      setProcessingProgress(data);
      if (terminal.has(data.status)) {
        await loadDocument();
        refreshRenderedImages();
      }
    });
    return unsubscribe;
  }, [docId, documentData?.status, loadDocument]);

  const loadHistory = useCallback(async () => {
    try {
      const result = await getDocumentHistory(docId);
      setHistory(result.entries || []);
    } catch {
      setHistory([]);
    }
  }, [docId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    setSelectedRedaction(null);
    setSelection(null);
    setDraftRect(null);
    setPendingCreates([]);
    setDrawStart(null);
    setPendingChange(null);
    setEditSession(null);
    setImageSizes({});
  }, [currentPageNumber]);

  const capturePaneScroll = () => ({
    original: {
      left: originalScrollRef.current?.scrollLeft || 0,
      top: originalScrollRef.current?.scrollTop || 0,
    },
    redacted: {
      left: redactedScrollRef.current?.scrollLeft || 0,
      top: redactedScrollRef.current?.scrollTop || 0,
    },
  });

  const restorePaneScroll = (snapshot) => {
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        if (originalScrollRef.current) {
          originalScrollRef.current.scrollLeft = snapshot.original.left;
          originalScrollRef.current.scrollTop = snapshot.original.top;
        }
        if (redactedScrollRef.current) {
          redactedScrollRef.current.scrollLeft = snapshot.redacted.left;
          redactedScrollRef.current.scrollTop = snapshot.redacted.top;
        }
      });
    });
  };

  const refreshCurrentPage = useCallback(async ({ preserveScroll = true } = {}) => {
    const scrollSnapshot = preserveScroll ? capturePaneScroll() : null;
    try {
      const page = await getDocumentPage(docId, currentPageNumber);
      setPages((prev) => prev.map((item) => (
        Number(item.page_number) === Number(currentPageNumber) ? page : item
      )));
      setRedactions((prev) => {
        const otherPages = prev.filter((redaction) => Number(redaction.page_number || 1) !== Number(currentPageNumber));
        return [...otherPages, ...(page.redactions || [])].sort((a, b) => a.id - b.id);
      });
      setSelectedRedaction((selected) => {
        if (!selected) return selected;
        return (page.redactions || []).find((redaction) => redaction.id === selected.id) || selected;
      });
    } catch {
      await loadDocument();
    }
    await loadHistory();
    if (scrollSnapshot) restorePaneScroll(scrollSnapshot);
  }, [currentPageNumber, docId, loadDocument, loadHistory]);

  useEffect(() => {
    let active = true;
    const objectUrls = [];
    // The redacted pane is a live preview: original image + client-side black
    // boxes. Keep the original image mounted so edits never require a PNG reload.
    const modes = ['original'];
    setImageUrls({});
    setImageSizes({});
    setImagesLoading(true);

    async function loadImages() {
      const next = {};
      try {
        await Promise.all(modes.map(async (mode) => {
          try {
            let url;
            try {
              url = currentPage?.page_number
                ? await getPageImageBlobUrl(docId, currentPage.page_number, mode)
                : await getImageBlobUrl(docId, mode);
            } catch (pageError) {
              url = await getImageBlobUrl(docId, mode);
            }
            objectUrls.push(url);
            next[mode] = url;
          } catch {
            next[mode] = null;
          }
        }));
        if (active) setImageUrls(next);
      } finally {
        if (active) setImagesLoading(false);
      }
    }

    loadImages();
    return () => {
      active = false;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [docId, currentPage?.page_number, viewMode, imageRevision]);

  const setImageSize = (mode, size) => {
    setImageSizes((prev) => ({ ...prev, [mode]: size }));
  };

  const refreshRenderedImages = () => {
    setImageRevision((value) => value + 1);
  };

  const syncPaneScroll = useCallback((sourceMode) => {
    if (viewMode !== 'both' || scrollSyncRef.current) return;
    const source = sourceMode === 'original' ? originalScrollRef.current : redactedScrollRef.current;
    const target = sourceMode === 'original' ? redactedScrollRef.current : originalScrollRef.current;
    if (!source || !target) return;
    scrollSyncRef.current = true;
    const leftRange = Math.max(1, source.scrollWidth - source.clientWidth);
    const topRange = Math.max(1, source.scrollHeight - source.clientHeight);
    const targetLeftRange = Math.max(1, target.scrollWidth - target.clientWidth);
    const targetTopRange = Math.max(1, target.scrollHeight - target.clientHeight);
    target.scrollLeft = (source.scrollLeft / leftRange) * targetLeftRange;
    target.scrollTop = (source.scrollTop / topRange) * targetTopRange;
    window.requestAnimationFrame(() => {
      scrollSyncRef.current = false;
    });
  }, [viewMode]);

  const handleCanvasWheelZoom = useCallback((event, sourceMode, scrollElement) => {
    if (!event.ctrlKey) return;
    event.preventDefault();

    const delta = event.deltaY < 0 ? 0.08 : -0.08;
    const rect = scrollElement?.getBoundingClientRect();
    const pointerX = rect ? event.clientX - rect.left : 0;
    const pointerY = rect ? event.clientY - rect.top : 0;
    const contentX = scrollElement ? scrollElement.scrollLeft + pointerX : 0;
    const contentY = scrollElement ? scrollElement.scrollTop + pointerY : 0;

    setZoom((currentZoom) => {
      const nextZoom = clamp(Number((currentZoom + delta).toFixed(2)), 0.35, 2.5);
      if (nextZoom === currentZoom) return currentZoom;

      if (scrollElement) {
        window.requestAnimationFrame(() => {
          const ratio = nextZoom / currentZoom;
          scrollElement.scrollLeft = Math.max(0, contentX * ratio - pointerX);
          scrollElement.scrollTop = Math.max(0, contentY * ratio - pointerY);
          window.requestAnimationFrame(() => syncPaneScroll(sourceMode));
        });
      }

      return nextZoom;
    });
  }, [syncPaneScroll]);

  const updateRedaction = (redactionId, updates) => {
    setRedactions((prev) => {
      const next = prev.map((redaction) => (
        redaction.id === redactionId ? { ...redaction, ...updates } : redaction
      ));
      const selected = next.find((redaction) => redaction.id === redactionId);
      if (selected) setSelectedRedaction(selected);
      return next;
    });
  };

  const clearPendingForRedaction = (redactionId) => {
    setPendingChange((change) => (
      change?.redactionId === redactionId ? null : change
    ));
  };

  const handleApprove = async (redactionId) => {
    try {
      await api.post(`/redactions/${redactionId}/approve`);
      updateRedaction(redactionId, { status: 'approved' });
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Redaction could not be approved.');
    }
  };

  const handleReject = async (redactionId) => {
    try {
      await rejectRedactionApi(redactionId, 'Removed in review editor');
      setRedactions((prev) => prev.map((redaction) => (
        redaction.id === redactionId ? { ...redaction, status: 'rejected' } : redaction
      )));
      if (selectedRedaction?.id === redactionId) setSelectedRedaction(null);
      clearPendingForRedaction(redactionId);
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Redaction could not be removed.');
    }
  };

  useEffect(() => {
    const handleKeyDown = (event) => {
      const target = event.target;
      const tagName = target?.tagName?.toLowerCase();
      if (
        tagName === 'input' ||
        tagName === 'textarea' ||
        tagName === 'select' ||
        target?.isContentEditable
      ) {
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        clearReviewSelection();
        return;
      }
      if (!selectedRedaction || selectedRedaction.status === 'rejected' || saving) return;
      if (event.key !== 'Delete' && event.key !== 'Backspace') return;
      event.preventDefault();
      handleReject(selectedRedaction.id);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedRedaction, saving, clearReviewSelection]);

  const handleApproveAll = async () => {
    setSaving(true);
    setError('');
    setNotice('');
    clearReviewSelection();
    try {
      await approveAllRedactions(docId);
      setRedactions((prev) => prev.map((redaction) => (
        redaction.status !== 'rejected' ? { ...redaction, status: 'approved' } : redaction
      )));
      await refreshCurrentPage();
      clearReviewSelection();
    } catch (err) {
      setError(err.response?.data?.detail || 'Redactions could not be approved.');
    } finally {
      setSaving(false);
    }
  };

  const pointFromEvent = (event) => {
    const size = imageSizes.original;
    if (!originalStageRef.current || !size?.width || !size?.height) return null;
    const bounds = originalStageRef.current.getBoundingClientRect();
    const x = clamp((event.clientX - bounds.left) / zoom, 0, size.width);
    const y = clamp((event.clientY - bounds.top) / zoom, 0, size.height);
    return { x, y };
  };

  const clampRectToImage = (rect) => {
    const size = imageSizes.original;
    if (!size?.width || !size?.height) return rect;
    const width = Math.max(8, Math.min(rect.width, size.width));
    const height = Math.max(8, Math.min(rect.height, size.height));
    return {
      x: clamp(rect.x, 0, Math.max(0, size.width - width)),
      y: clamp(rect.y, 0, Math.max(0, size.height - height)),
      width,
      height,
    };
  };

  const resizeRect = (startRect, handle, currentPoint, startPoint) => {
    const dx = currentPoint.x - startPoint.x;
    const dy = currentPoint.y - startPoint.y;
    let x1 = startRect.x;
    let y1 = startRect.y;
    let x2 = startRect.x + startRect.width;
    let y2 = startRect.y + startRect.height;

    if (handle.includes('w')) x1 += dx;
    if (handle.includes('e')) x2 += dx;
    if (handle.includes('n')) y1 += dy;
    if (handle.includes('s')) y2 += dy;

    if (x2 - x1 < 8) {
      if (handle.includes('w')) x1 = x2 - 8;
      else x2 = x1 + 8;
    }
    if (y2 - y1 < 8) {
      if (handle.includes('n')) y1 = y2 - 8;
      else y2 = y1 + 8;
    }

    return clampRectToImage({
      x: Math.min(x1, x2),
      y: Math.min(y1, y2),
      width: Math.abs(x2 - x1),
      height: Math.abs(y2 - y1),
    });
  };

  const editChangeFromEvent = (session, event) => {
    const point = pointFromEvent(event);
    if (!point || !session) return null;
    if (session.handle === 'move') {
      const dx = point.x - session.startPoint.x;
      const dy = point.y - session.startPoint.y;
      return {
        mode: 'edit',
        redactionId: session.redaction.id,
        rect: clampRectToImage({
          ...session.startRect,
          x: session.startRect.x + dx,
          y: session.startRect.y + dy,
        }),
      };
    }
    return {
      mode: 'edit',
      redactionId: session.redaction.id,
      rect: resizeRect(session.startRect, session.handle, point, session.startPoint),
    };
  };

  const saveExistingBoxChange = async (change, originalRedaction) => {
    const target = originalRedaction || redactions.find((redaction) => redaction.id === change.redactionId);
    if (!target) return;

    const updated = {
      ...target,
      bbox: rectToBbox(change.rect),
      status: 'modified',
    };

    setPendingChange(null);
    setRedactions((prev) => prev.map((redaction) => (
      redaction.id === target.id ? updated : redaction
    )));
    setSelectedRedaction(updated);
    setSaving(true);
    setError('');

    try {
      await modifyRedaction(target.id, {
        new_bbox: rectToBbox(change.rect),
        new_type: target.type || target.redaction_type || manualType,
        reason: 'Adjusted in review editor',
      });
      await refreshCurrentPage();
    } catch (err) {
      setRedactions((prev) => prev.map((redaction) => (
        redaction.id === target.id ? target : redaction
      )));
      setSelectedRedaction(target);
      setError(err.response?.data?.detail || 'Redaction change could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const beginDraw = (event) => {
    if (!drawMode || saving || !imageUrls.original || editSession) return;
    const point = pointFromEvent(event);
    if (!point) return;
    event.preventDefault();
    setSelectedRedaction(null);
    setPendingChange(null);
    setDrawStart(point);
    setDraftRect({ x: point.x, y: point.y, width: 0, height: 0 });
  };

  const continueDraw = (event) => {
    if (editSession) {
      const nextChange = editChangeFromEvent(editSession, event);
      if (nextChange) setPendingChange(nextChange);
      return;
    }

    if (!drawStart || !draftRect) return;
    const point = pointFromEvent(event);
    if (!point) return;
    const x = Math.min(drawStart.x, point.x);
    const y = Math.min(drawStart.y, point.y);
    setDraftRect({
      x,
      y,
      width: Math.abs(point.x - drawStart.x),
      height: Math.abs(point.y - drawStart.y),
    });
  };

  const finishDraw = (event) => {
    if (editSession) {
      const finalChange = event ? editChangeFromEvent(editSession, event) : pendingChange;
      const originalRedaction = editSession.redaction;
      const originalRect = editSession.startRect;
      setEditSession(null);
      if (finalChange && !rectsEqual(finalChange.rect, originalRect)) {
        setPendingChange(finalChange);
        saveExistingBoxChange(finalChange, originalRedaction);
      } else {
        setPendingChange(null);
      }
      return;
    }

    if (!drawStart || !draftRect) return;
    const finalRect = draftRect;
    setDrawStart(null);
    setDraftRect(null);

    if (finalRect.width < 8 || finalRect.height < 8) return;

    setPendingCreates((prev) => [...prev, clampRectToImage(finalRect)]);
  };

  const startEdit = (event, redaction, handle) => {
    if (saving || redaction.status === 'rejected') return;
    const point = pointFromEvent(event);
    const rect = bboxToRect(redaction);
    if (!point || !rect) return;
    setSelectedRedaction(redaction);
    setDraftRect(null);
    setDrawStart(null);
    setPendingChange({
      mode: 'edit',
      redactionId: redaction.id,
      rect,
    });
    setEditSession({
      redaction,
      handle,
      startPoint: point,
      startRect: rect,
    });
  };

  const applyBoxChange = async () => {
    if (!drawMode || (!pendingChange && pendingCreates.length === 0)) return;
    setSaving(true);
    setError('');
    try {
      if (pendingCreates.length > 0) {
        const createdRedactions = [];
        for (const rect of pendingCreates) {
          const created = await createManualRedaction(
            docId,
            rectToBbox(rect),
            manualType,
            'Drawn in review editor',
            currentPageNumber
          );
          createdRedactions.push(created);
        }
        setRedactions((prev) => [...prev, ...createdRedactions]);
        if (createdRedactions[0]) setSelectedRedaction(createdRedactions[0]);
      } else if (pendingChange?.mode === 'create') {
        const created = await createManualRedaction(
          docId,
          rectToBbox(pendingChange.rect),
          manualType,
          'Drawn in review editor',
          currentPageNumber
        );
        setRedactions((prev) => [...prev, created]);
        setSelectedRedaction(created);
      } else {
        const target = redactions.find((redaction) => redaction.id === pendingChange.redactionId);
        if (!target) throw new Error('Redaction no longer exists.');
        await modifyRedaction(target.id, {
          new_bbox: rectToBbox(pendingChange.rect),
          new_type: target.type || target.redaction_type || manualType,
          reason: 'Adjusted in review editor',
        });
        const updated = {
          ...target,
          bbox: rectToBbox(pendingChange.rect),
          status: 'modified',
        };
        setRedactions((prev) => prev.map((redaction) => (
          redaction.id === target.id ? updated : redaction
        )));
        setSelectedRedaction(updated);
      }
      setPendingChange(null);
      setPendingCreates([]);
      // Box tool is one-shot: turn it off after applying so it doesn't stay armed.
      setDrawMode(false);
      setDraftRect(null);
      setDrawStart(null);
      setEditSession(null);
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Redaction change could not be saved.');
    } finally {
      setSaving(false);
    }
  };

  const captureTextSelection = () => {
    if (!textRef.current) return;
    const offsets = getSelectionOffsets(textRef.current);
    if (offsets) setSelection(offsets);
  };

  const handleRedactSelection = async () => {
    if (!selection?.text?.trim()) {
      setError('Select text in the OCR panel first.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const result = await createTextRedaction(docId, {
        selectedText: selection.text,
        selectionStart: selection.start,
        selectionEnd: selection.end,
        redactionType: manualType,
        reason: 'Selected from OCR text panel',
        pageNumber: currentPageNumber,
      });
      const created = result.redactions || [];
      setRedactions((prev) => [...prev, ...created]);
      if (created[0]) setSelectedRedaction(created[0]);
      setSelection(null);
      window.getSelection()?.removeAllRanges();
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Selected text could not be redacted.');
    } finally {
      setSaving(false);
    }
  };

  const verifyBeforeDownload = async () => {
    setDownloading(true);
    setError('');
    try {
      const verification = await verifyExport(docId);
      if (!verification?.passed) {
        const failed = (verification?.checks || []).filter((check) => !check.passed);
        throw new Error(`Burned PDF verification failed: ${failed.map((check) => check.name).join(', ') || 'unknown check'}.`);
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'object') {
        setError(detail.message || 'PDF export verification failed.');
      } else {
        setError(detail || err.message || 'PDF export is not available.');
      }
      throw err;
    } finally {
      setDownloading(false);
    }
  };

  const handleUndo = async () => {
    setSaving(true);
    setError('');
    setNotice('');
    try {
      await undoLastAction(docId);
      clearReviewSelection();
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Nothing to undo.');
    } finally {
      setSaving(false);
    }
  };

  const toggleDrawMode = () => {
    if (!drawMode && viewMode === 'redacted') setViewMode('original');
    setDraftRect(null);
    setPendingCreates([]);
    setDrawStart(null);
    setEditSession(null);
    setDrawMode((active) => !active);
  };

  const goToNextWarning = () => {
    if (!pages.length) return;
    const ordered = [...pages].sort((a, b) => Number(a.page_number) - Number(b.page_number));
    const currentIndex = ordered.findIndex((page) => Number(page.page_number) === Number(currentPageNumber));
    const rotated = [...ordered.slice(currentIndex + 1), ...ordered.slice(0, currentIndex + 1)];
    const target = rotated.find((page) => (page.warning_count || page.vision_warnings?.length || 0) > 0);
    if (target) setCurrentPageNumber(target.page_number);
  };

  const previewLoadingMessage = imagesLoading
    ? 'Loading the page image from the local backend.'
    : (processingProgress?.message || 'Preview is not ready yet. The editor will refresh it when the backend responds.');

  const originalCanvas = (
    <DocumentCanvas
      title="Original"
      imageUrl={imageUrls.original}
      imageSize={imageSizes.original}
      setImageSize={(size) => setImageSize('original', size)}
      zoom={zoom}
      redactions={pageRedactions}
      selectedRedaction={selectedRedaction}
      setSelectedRedaction={setSelectedRedaction}
      showOverlays
      drawEnabled={drawMode}
      stageRef={originalStageRef}
      scrollRef={originalScrollRef}
      onScroll={() => syncPaneScroll('original')}
      onWheelZoom={(event, scrollElement) => handleCanvasWheelZoom(event, 'original', scrollElement)}
      beginDraw={beginDraw}
      continueDraw={continueDraw}
      finishDraw={finishDraw}
      draftRect={draftRect}
      pendingCreates={pendingCreates}
      pendingChange={pendingChange}
      startEdit={startEdit}
      clearSelection={clearReviewSelection}
      disabledOverlay={false}
      previewLoading={imagesLoading}
      processingActive={Boolean(activeProcessing)}
      processingMessage={previewLoadingMessage}
    />
  );

  const redactedCanvas = (
    <DocumentCanvas
      title="Redacted"
      imageUrl={imageUrls.original}
      imageSize={imageSizes.original}
      setImageSize={(size) => setImageSize('original', size)}
      zoom={zoom}
      redactions={pageRedactions}
      selectedRedaction={selectedRedaction}
      setSelectedRedaction={setSelectedRedaction}
      showOverlays={false}
      liveRedactionPreview
      drawEnabled={false}
      stageRef={null}
      scrollRef={redactedScrollRef}
      onScroll={() => syncPaneScroll('redacted')}
      onWheelZoom={(event, scrollElement) => handleCanvasWheelZoom(event, 'redacted', scrollElement)}
      draftRect={draftRect}
      pendingCreates={pendingCreates}
      pendingChange={pendingChange}
      startEdit={() => {}}
      clearSelection={clearReviewSelection}
      disabledOverlay={drawMode && viewMode === 'both'}
      previewLoading={imagesLoading}
      processingActive={Boolean(activeProcessing)}
      processingMessage={previewLoadingMessage}
    />
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-100">
        <div className="h-10 w-10 rounded-full border-2 border-slate-300 border-t-slate-900 animate-spin" />
      </div>
    );
  }

  if (!documentData && notice) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-100 px-6">
        <div className="flex max-w-md flex-col items-center gap-4 rounded-md border border-blue-200 bg-white p-6 text-center text-sm text-blue-800 shadow-sm">
          <div className="h-10 w-10 rounded-full border-2 border-blue-100 border-t-blue-700 animate-spin" />
          <div>{notice}</div>
        </div>
      </div>
    );
  }

  if (error && !documentData) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-100 px-6">
        <div className="max-w-md rounded-md border border-red-200 bg-white p-5 text-sm text-red-700 shadow-sm">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-slate-100 text-slate-900">
      <div className="flex min-h-[64px] items-center justify-between border-b border-slate-200 bg-white px-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={() => setScreen('list')}
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Back
          </button>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-950">
              {documentData?.filename || 'Document'}
            </div>
            <div className="mt-1">
              <span
                className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-bold ${engineBadgeClass(engineStatus.mode)}`}
                title={engineStatus.detail}
              >
                {engineStatus.label}
              </span>
            </div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2 text-xs text-slate-500">
              Page {currentPageNumber} of {pages.length || 1} · {activeRedactions.length} active on page · {documentData?.status || 'unknown'}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
          {/* View */}
          <div className="flex rounded-md border border-slate-300 bg-slate-50 p-0.5">
            {VIEW_MODES.map((mode) => (
              <button
                key={mode.id}
                type="button"
                onClick={() => {
                  setViewMode(mode.id);
                  if (mode.id === 'redacted') setDrawMode(false);
                }}
                className={`rounded px-3 py-1.5 text-xs font-semibold ${
                  viewMode === mode.id ? 'bg-white text-slate-950 shadow-sm' : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {mode.label}
              </button>
            ))}
          </div>

          <div className="flex items-center rounded-md border border-slate-300 bg-white">
            <button
              type="button"
              onClick={() => setZoom((value) => Math.max(0.35, value - 0.1))}
              className="h-9 px-3 text-sm font-bold text-slate-700 hover:bg-slate-50"
              aria-label="Zoom out"
            >
              -
            </button>
            <div className="w-12 text-center text-xs font-semibold text-slate-600">
              {Math.round(zoom * 100)}%
            </div>
            <button
              type="button"
              onClick={() => setZoom((value) => Math.min(2.5, value + 0.1))}
              className="h-9 px-3 text-sm font-bold text-slate-700 hover:bg-slate-50"
              aria-label="Zoom in"
            >
              +
            </button>
          </div>

          <div className="h-6 w-px bg-slate-200" aria-hidden="true" />

          {/* Edit */}
          <div className="flex items-center gap-1.5">
            <select
              value={manualType}
              onChange={(event) => setManualType(event.target.value)}
              className="h-9 rounded-md border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-700"
              aria-label="Redaction type for new boxes"
              title="Type for new boxes you draw"
            >
              {MANUAL_TYPES.map((type) => (
                <option key={type} value={type}>{type.replace(/_/g, ' ')}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={toggleDrawMode}
              className={`h-9 rounded-md px-3 text-xs font-bold ${
                drawMode ? 'bg-slate-950 text-white' : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              Box tool
            </button>
            <button
              type="button"
              onClick={applyBoxChange}
              disabled={!drawMode || (!pendingChange && pendingCreates.length === 0) || saving}
              className="h-9 rounded-md bg-blue-700 px-3 text-xs font-bold text-white hover:bg-blue-600 disabled:bg-slate-200 disabled:text-slate-400"
            >
              {pendingCreates.length > 1 ? `Apply ${pendingCreates.length}` : 'Apply'}
            </button>
            <button
              type="button"
              onClick={() => selectedRedaction && handleReject(selectedRedaction.id)}
              disabled={!selectedCanBeRemoved || saving}
              className="h-9 rounded-md border border-red-200 bg-white px-3 text-xs font-bold text-red-700 hover:bg-red-50 disabled:border-slate-200 disabled:text-slate-300 disabled:hover:bg-white"
            >
              Remove selected
            </button>
            <button
              type="button"
              onClick={handleUndo}
              disabled={!history.length || saving}
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:bg-slate-100 disabled:text-slate-300"
            >
              Undo
            </button>
          </div>

          <div className="h-6 w-px bg-slate-200" aria-hidden="true" />

          {/* Navigate */}
          {hasAnyWarnings && (
          <div className="flex items-center gap-1.5">
            {hasAnyWarnings && (
              <button
                type="button"
                onClick={goToNextWarning}
                className="h-9 rounded-md border border-amber-200 bg-white px-3 text-xs font-bold text-amber-800 hover:bg-amber-50"
              >
                Next warning
              </button>
            )}
          </div>
          )}

          {hasAnyWarnings && <div className="h-6 w-px bg-slate-200" aria-hidden="true" />}

          {/* Decide */}
          <button
            type="button"
            onClick={handleApproveAll}
            disabled={saving}
            className="h-9 rounded-md border border-emerald-300 bg-white px-3 text-xs font-bold text-emerald-700 hover:bg-emerald-50"
          >
            Approve all
          </button>
          <ExportMenu
            docId={docId}
            type="pdf"
            label={downloading ? 'Verifying...' : 'Download redacted PDF'}
            disabled={downloading}
            onBeforeExport={verifyBeforeDownload}
            onExported={(result) => setNotice(`Saved to ${result.path}`)}
            buttonClassName="h-9 rounded-md bg-slate-950 px-4 text-xs font-bold text-white shadow-sm hover:bg-slate-800 disabled:opacity-60"
          />
        </div>
      </div>

      {(activeProcessing || processingFailed) && (
        <div className={`border-b px-4 py-3 ${
          processingFailed ? 'border-red-200 bg-red-50' : 'border-blue-200 bg-blue-50'
        }`}>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-3 text-xs">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className={`font-bold ${processingFailed ? 'text-red-700' : 'text-blue-900'}`}>
                {processingFailed ? 'Processing failed' : 'Processing document'}
              </span>
              <span className={`rounded-full border px-2 py-0.5 text-[11px] font-bold ${engineBadgeClass(engineStatus.mode)}`}>
                {engineStatus.label}
              </span>
              <span className={processingFailed ? 'text-red-700' : 'text-blue-800'}>
                {engineStatus.detail}
              </span>
            </div>
            <span className={processingFailed ? 'text-red-700' : 'text-blue-800'}>
              {progressPercent}%
            </span>
          </div>
          <div className={`h-2 overflow-hidden rounded-full ${processingFailed ? 'bg-red-100' : 'bg-blue-100'}`}>
            <div
              className={`h-full rounded-full transition-all duration-500 ${processingFailed ? 'bg-red-500' : 'bg-blue-600 progress-striped'}`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className={`mt-2 text-xs ${processingFailed ? 'text-red-700' : 'text-blue-800'}`}>
            {processingProgress?.message || documentData?.needs_review_reason || 'Preparing the review workspace...'}
          </div>
          {processingFailed && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setScreen('preferences')}
                className="rounded-md bg-red-700 px-3 py-2 text-xs font-bold text-white hover:bg-red-800"
              >
                Open engine settings
              </button>
              <button
                type="button"
                onClick={() => setScreen('scan')}
                className="rounded-md border border-red-300 bg-white px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-50"
              >
                Upload again
              </button>
            </div>
          )}
        </div>
      )}

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside className="flex w-44 shrink-0 flex-col border-r border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-3 py-3">
            <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Pages</div>
            <div className="mt-1 text-xs text-slate-500">{pages.length || 1} total</div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto p-2">
            {(pages.length ? pages : [{ page_number: 1 }]).map((page) => {
              const active = Number(page.page_number) === Number(currentPageNumber);
              const warningCount = page.warning_count || page.vision_warnings?.length || 0;
              return (
                <button
                  key={page.page_number}
                  type="button"
                  onClick={() => setCurrentPageNumber(page.page_number)}
                  className={`mb-2 w-full rounded-md border p-2 text-left text-xs transition-colors ${
                    active
                      ? 'border-blue-300 bg-blue-50 text-blue-950'
                      : warningCount
                        ? 'border-amber-200 bg-amber-50 text-slate-800 hover:bg-amber-100'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-bold">Page {page.page_number}</span>
                    {warningCount > 0 && (
                      <span className="rounded bg-amber-200 px-1.5 py-0.5 font-bold text-amber-900">
                        {warningCount}
                      </span>
                    )}
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-slate-500">
                    <span>{page.redaction_count || 0} boxes</span>
                    <span>{Math.round((page.ocr_confidence || 0) * 100)}% OCR</span>
                  </div>
                  <div className="mt-1 truncate text-[11px] text-slate-400">
                    Vision: {page.vision_status || 'not run'}
                  </div>
                </button>
              );
            })}
          </div>

        </aside>

        <main className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-slate-200 p-4">
          {notice && (
            <div className={`mb-3 rounded-md border px-4 py-3 text-sm ${noticeClass(notice)}`}>
              {notice}
            </div>
          )}
          {error && (
            <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
          {saving && (
            <div className="mb-3 rounded-md border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
              Saving redaction.
            </div>
          )}

          <div className={viewMode === 'both' ? 'grid min-h-0 flex-1 grid-cols-2 gap-4 overflow-hidden' : 'min-h-0 flex-1 overflow-hidden'}>
            {viewMode === 'both' ? (
              <>
                {originalCanvas}
                {redactedCanvas}
              </>
            ) : viewMode === 'redacted' ? (
              redactedCanvas
            ) : (
              originalCanvas
            )}
          </div>

          <div className="pointer-events-none absolute bottom-5 right-5 z-10 rounded-md border border-slate-300 bg-white/90 px-3 py-2 text-[11px] shadow-sm backdrop-blur-sm">
            <div className="mb-1 font-bold uppercase tracking-wide text-slate-400">Legend</div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="h-3 w-4 rounded-sm border-2 border-orange-700 bg-orange-700/30" />
                <span className="text-slate-600">Proposed redaction</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-4 rounded-sm border-2 border-dashed border-amber-500 bg-amber-500/30" />
                <span className="text-slate-600">Needs review</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-4 rounded-sm border-2 border-slate-900 bg-slate-900/40" />
                <span className="text-slate-600">Manual / from text</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-4 rounded-sm bg-black" />
                <span className="text-slate-600">Will be redacted</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-3 w-4 rounded-sm border-2 border-blue-600" />
                <span className="text-slate-600">Selected</span>
              </div>
            </div>
          </div>
        </main>

        <aside className="flex w-[420px] shrink-0 flex-col border-l border-slate-200 bg-white">
          <div className="min-h-0 flex-1 overflow-auto">
            <div className="border-b border-slate-200 p-4">
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Processing path</div>
              <div className={`rounded-md border p-3 text-sm ${engineBadgeClass(engineStatus.mode)}`}>
                <div className="font-bold">{engineStatus.label}</div>
                <div className="mt-1 text-xs opacity-90">{engineStatus.detail}</div>
                {(engineStatus.engine_used || engineStatus.handwriting_backend) && (
                  <div className="mt-2 rounded bg-white/70 p-2 font-mono text-[11px] text-slate-700">
                    {engineStatus.engine_used || 'engine pending'}
                    {engineStatus.handwriting_backend ? ` / ${engineStatus.handwriting_backend}` : ''}
                  </div>
                )}
              </div>
            </div>

            <div className="border-b border-slate-200 p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wide text-slate-400">
                  Transcription · page {currentPageNumber}
                </div>
                <button
                  type="button"
                  onClick={handleRedactSelection}
                  disabled={!selection?.text || saving}
                  className="rounded-md bg-slate-950 px-3 py-1.5 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-40"
                >
                  Redact selection
                </button>
              </div>
              <div
                ref={textRef}
                tabIndex={0}
                className="h-64 select-none overflow-auto rounded-md border border-slate-300 bg-white p-3 font-mono text-xs leading-5 text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 whitespace-pre-wrap"
              >
                {renderHighlightedText(
                  ocrText,
                  highlightRanges,
                  setSelectedRedaction,
                  setSelection,
                  selection
                )}
              </div>
              <div className="mt-2 min-h-[34px] rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
                {selection?.text ? (
                  <span className="font-mono">{selection.text.trim().slice(0, 140)}</span>
                ) : (
                  <span>Select OCR text to create a matching redaction box.</span>
                )}
              </div>
            </div>

            {(currentPage?.vision_warnings || []).length > 0 && (
              <div className="border-b border-slate-200 p-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Vision warnings</div>
                  <span className="text-[11px] font-semibold text-slate-400">
                    {currentPage?.vision_status || 'not run'}
                  </span>
                </div>
                <div className="max-h-36 space-y-2 overflow-auto">
                  {currentPage.vision_warnings.map((warning, index) => (
                    <div key={`${warning}-${index}`} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                      {warning}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="border-b border-slate-200 p-4">
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Redactions</div>
              <div className="max-h-56 space-y-1 overflow-auto pr-1">
                {pageRedactions.length ? [...pageRedactions]
                  .sort((a, b) => (isReviewNeeded(b) ? 1 : 0) - (isReviewNeeded(a) ? 1 : 0) || (a.id || 0) - (b.id || 0))
                  .map((redaction) => {
                  const review = isReviewNeeded(redaction);
                  return (
                  <div
                    key={redaction.id}
                    className={`rounded-md border p-2 text-xs ${
                      selectedRedaction?.id === redaction.id
                        ? 'border-blue-300 bg-blue-50'
                        : redaction.status === 'rejected'
                          ? 'border-slate-100 bg-slate-50 opacity-70'
                          : review
                            ? 'border-amber-200 bg-amber-50/60 hover:bg-amber-50'
                            : 'border-transparent hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedRedaction(redaction)}
                        className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                      >
                        <span className={`h-2 w-2 shrink-0 rounded-full ${review ? 'bg-amber-500' : 'bg-orange-700'}`} />
                        <span className="block truncate font-semibold text-slate-800">
                          {redaction.type?.replace(/_/g, ' ') || 'redaction'}
                        </span>
                      </button>
                      {review ? (
                        <span className="shrink-0 rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-bold text-amber-900">REVIEW</span>
                      ) : (
                        <span className="text-[11px] text-slate-500">{redaction.status || 'pending'}</span>
                      )}
                    </div>
                    {redactionValuePreview(redaction) && (
                      <button
                        type="button"
                        onClick={() => setSelectedRedaction(redaction)}
                        className="mt-1 block w-full truncate text-left font-mono text-[11px] text-slate-700"
                        title={redaction.original_value || ''}
                      >
                        {redactionValuePreview(redaction)}
                      </button>
                    )}
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedRedaction(redaction)}
                        className="min-w-0 flex-1 truncate text-left text-[11px] text-slate-500"
                      >
                        {confidenceLabel(redaction.confidence || 0)} · {Math.round((redaction.confidence || 0) * 100)}%
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReject(redaction.id)}
                        disabled={redaction.status === 'rejected' || saving}
                        className="rounded border border-red-200 px-2 py-1 text-[11px] font-bold text-red-700 hover:bg-red-50 disabled:border-slate-200 disabled:text-slate-300"
                      >
                        Remove
                      </button>
                    </div>
                  </div>
                  );
                }) : (
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
                    No redactions yet.
                  </div>
                )}
              </div>
            </div>

            <div className="p-4">
              <div className="mb-4 rounded-md border border-slate-200 bg-slate-50 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <div className="text-xs font-bold uppercase tracking-wide text-slate-400">History</div>
                  <button
                    type="button"
                    onClick={handleUndo}
                    disabled={!history.length || saving}
                    className="rounded border border-slate-300 bg-white px-2 py-1 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:text-slate-300"
                  >
                    Undo last
                  </button>
                </div>
                <div className="max-h-24 space-y-1 overflow-auto text-xs text-slate-600">
                  {history.length ? history.slice(0, 5).map((entry) => (
                    <div key={entry.id} className="flex items-center justify-between gap-2">
                      <span className="truncate">
                        Page {entry.page_number || 1}: {entry.action_type || entry.decision}
                      </span>
                      <span className="shrink-0 text-[11px] text-slate-400">
                        #{entry.redaction_id}
                      </span>
                    </div>
                  )) : (
                    <div className="text-slate-400">No edit history yet.</div>
                  )}
                </div>
              </div>

              {selectedRedaction ? (
                <div className="space-y-4">
                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Selected redaction</div>
                    <div className="mt-1 text-sm font-semibold text-slate-950">
                      {selectedRedaction.type?.replace(/_/g, ' ') || 'redaction'}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {selectedRedaction.method || 'detected'} · {selectedRedaction.status || 'pending'}
                    </div>
                  </div>

                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Confidence</div>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-2 flex-1 rounded-full bg-slate-200">
                        <div
                          className="h-2 rounded-full bg-slate-950"
                          style={{ width: `${Math.round((selectedRedaction.confidence || 0) * 100)}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold text-slate-700">
                        {confidenceLabel(selectedRedaction.confidence || 0)}
                      </span>
                    </div>
                  </div>

                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Redacted text</div>
                    <div className="mt-1 max-h-28 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-700">
                      {selectedRedaction.original_value || selectedRedaction.masked_value || '[redacted]'}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => handleApprove(selectedRedaction.id)}
                      className="rounded-md bg-emerald-700 px-3 py-2 text-sm font-bold text-white hover:bg-emerald-600"
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      onClick={() => handleReject(selectedRedaction.id)}
                      className="rounded-md bg-red-700 px-3 py-2 text-sm font-bold text-white hover:bg-red-600"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ) : (
                <div className="rounded-md border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  Select a redaction or draw a new box.
                </div>
              )}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
