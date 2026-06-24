import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import api, {
  approveAllRedactions,
  createManualRedaction,
  createTextRedaction,
  downloadExport,
  getDocumentHistory,
  getDocumentPage,
  getImageBlobUrl,
  getPageImageBlobUrl,
  modifyRedaction,
  rejectRedaction as rejectRedactionApi,
  undoLastAction,
  verifyExport,
} from '../api';

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
  if (confidence >= 0.9) return 'High';
  if (confidence >= 0.7) return 'Medium';
  return 'Low';
}

function overlayStyle(redaction, isSelected) {
  const rejected = redaction.status === 'rejected';
  const approved = redaction.status === 'approved';
  const manual = redaction.method === 'manual' || redaction.method === 'text_selection';
  return {
    backgroundColor: rejected
      ? 'rgba(220, 38, 38, 0.12)'
      : approved
        ? 'rgba(0, 0, 0, 0.76)'
        : manual
          ? 'rgba(15, 23, 42, 0.42)'
          : 'rgba(180, 83, 9, 0.30)',
    border: isSelected
      ? '2px solid #2563eb'
      : rejected
        ? '2px dashed #dc2626'
        : manual
          ? '2px solid #0f172a'
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
  for (const redaction of redactions) {
    if (redaction.status === 'rejected') continue;
    const value = String(redaction.original_value || '').trim();
    if (value.length < 2) continue;
    const needle = value.toLowerCase();
    let index = lower.indexOf(needle);
    while (index >= 0) {
      ranges.push({ start: index, end: index + value.length, redaction });
      index = lower.indexOf(needle, index + value.length);
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

function renderHighlightedText(text, ranges, onRedactionClick) {
  if (!text) return <span className="text-slate-400">No OCR text available.</span>;
  if (!ranges.length) return text;

  const parts = [];
  let cursor = 0;
  ranges.forEach((range, index) => {
    if (range.start > cursor) {
      parts.push(text.slice(cursor, range.start));
    }
    parts.push(
      <button
        key={`${range.start}-${range.end}-${index}`}
        type="button"
        onClick={() => onRedactionClick(range.redaction)}
        className="rounded-sm bg-amber-200 px-0.5 text-left text-slate-950 outline outline-1 outline-amber-400"
      >
        {text.slice(range.start, range.end)}
      </button>
    );
    cursor = range.end;
  });
  if (cursor < text.length) parts.push(text.slice(cursor));
  return parts;
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
  beginDraw,
  continueDraw,
  finishDraw,
  draftRect,
  pendingChange,
  startEdit,
  disabledOverlay,
}) {
  const pendingEditId = pendingChange?.mode === 'edit' ? pendingChange.redactionId : null;

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

      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="relative min-h-0 flex-1 overscroll-contain overflow-auto rounded-md border border-slate-300 bg-slate-300 p-3"
      >
        {imageUrl ? (
          <div
            ref={stageRef}
            onMouseDown={drawEnabled ? beginDraw : undefined}
            onMouseMove={drawEnabled ? continueDraw : undefined}
            onMouseUp={drawEnabled ? finishDraw : undefined}
            onMouseLeave={drawEnabled ? finishDraw : undefined}
            className={`relative inline-block select-none bg-white shadow-sm ring-1 ring-slate-400 ${
              drawEnabled ? 'cursor-crosshair' : 'cursor-default'
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
              className="block h-full w-full"
            />

            {showOverlays && redactions
              .filter((redaction) => redaction.status !== 'rejected')
              .map((redaction) => {
                const rect = pendingEditId === redaction.id ? pendingChange.rect : bboxToRect(redaction);
                if (!rect) return null;
                const selected = selectedRedaction?.id === redaction.id;
                return (
                  <button
                    type="button"
                    key={redaction.id}
                    onMouseDown={(event) => {
                      if (!drawEnabled || redaction.status === 'rejected') return;
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
                    {drawEnabled && selected && redaction.status !== 'rejected' && (
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
          <div className="rounded-md border border-slate-300 bg-white p-8 text-sm text-slate-600">
            Preview image is not available.
          </div>
        )}
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
  const [imageRevision, setImageRevision] = useState(0);
  const [viewMode, setViewMode] = useState('both');
  const [zoom, setZoom] = useState(0.75);
  const [drawMode, setDrawMode] = useState(false);
  const [manualType, setManualType] = useState('manual');
  const [draftRect, setDraftRect] = useState(null);
  const [drawStart, setDrawStart] = useState(null);
  const [pendingChange, setPendingChange] = useState(null);
  const [editSession, setEditSession] = useState(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const currentPage = useMemo(
    () => pages.find((page) => Number(page.page_number) === Number(currentPageNumber)) || pages[0] || null,
    [pages, currentPageNumber]
  );

  const pageRedactions = useMemo(
    () => redactions.filter((redaction) => Number(redaction.page_number || 1) === Number(currentPageNumber)),
    [redactions, currentPageNumber]
  );

  const ocrText = currentPage?.ocr?.extracted_text || documentData?.ocr?.extracted_text || '';
  const activeRedactions = useMemo(
    () => pageRedactions.filter((redaction) => redaction.status !== 'rejected'),
    [pageRedactions]
  );

  const reviewStats = useMemo(() => {
    return pageRedactions.reduce(
      (acc, redaction) => {
        if (redaction.status === 'approved') acc.approved += 1;
        else if (redaction.status === 'rejected') acc.rejected += 1;
        else acc.pending += 1;
        return acc;
      },
      { approved: 0, rejected: 0, pending: 0 }
    );
  }, [pageRedactions]);

  const highlightRanges = useMemo(
    () => buildHighlightRanges(ocrText, activeRedactions),
    [ocrText, activeRedactions]
  );

  const selectedRect = (
    pendingChange?.mode === 'edit' && pendingChange.redactionId === selectedRedaction?.id
      ? pendingChange.rect
      : bboxToRect(selectedRedaction)
  );
  const selectedCanBeRemoved = Boolean(
    selectedRedaction && selectedRedaction.status !== 'rejected'
  );

  const loadDocument = useCallback(async () => {
    setError('');
    try {
      const res = await api.get(`/document/${docId}`);
      setDocumentData(res.data);
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
    } catch (err) {
      setError(err.response?.data?.detail || 'Document could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadDocument();
  }, [loadDocument]);

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
    setDrawStart(null);
    setPendingChange(null);
    setEditSession(null);
    setImageSizes({});
  }, [currentPageNumber]);

  const refreshCurrentPage = useCallback(async () => {
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
  }, [currentPageNumber, docId, loadDocument, loadHistory]);

  useEffect(() => {
    let active = true;
    const objectUrls = [];
    const modes = viewMode === 'both' ? ['original', 'redacted'] : [viewMode];
    setImageUrls({});

    async function loadImages() {
      const next = {};
      await Promise.all(modes.map(async (mode) => {
        try {
          const url = currentPage?.page_number
            ? await getPageImageBlobUrl(docId, currentPage.page_number, mode)
            : await getImageBlobUrl(docId, mode);
          objectUrls.push(url);
          next[mode] = url;
        } catch {
          next[mode] = null;
        }
      }));
      if (active) setImageUrls(next);
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

  const updateRedaction = (redactionId, updates) => {
    setRedactions((prev) => {
      const next = prev.map((redaction) => (
        redaction.id === redactionId ? { ...redaction, ...updates } : redaction
      ));
      const selected = next.find((redaction) => redaction.id === redactionId);
      if (selected) setSelectedRedaction(selected);
      return next;
    });
    refreshRenderedImages();
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
      refreshRenderedImages();
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Redaction could not be removed.');
    }
  };

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (!selectedRedaction || selectedRedaction.status === 'rejected' || saving) return;
      if (event.key !== 'Delete' && event.key !== 'Backspace') return;
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
      event.preventDefault();
      handleReject(selectedRedaction.id);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedRedaction, saving]);

  const handleApproveAll = async () => {
    try {
      await approveAllRedactions(docId);
      setRedactions((prev) => prev.map((redaction) => (
        redaction.status === 'pending' ? { ...redaction, status: 'approved' } : redaction
      )));
      refreshRenderedImages();
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Redactions could not be approved.');
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
      refreshRenderedImages();
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

    setPendingChange({ mode: 'create', rect: clampRectToImage(finalRect) });
  };

  const startEdit = (event, redaction, handle) => {
    if (!drawMode || saving || redaction.status === 'rejected') return;
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
    if (!drawMode || !pendingChange) return;
    setSaving(true);
    setError('');
    try {
      if (pendingChange.mode === 'create') {
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
      refreshRenderedImages();
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
      refreshRenderedImages();
      await refreshCurrentPage();
    } catch (err) {
      setError(err.response?.data?.detail || 'Selected text could not be redacted.');
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadPdf = async () => {
    setDownloading(true);
    setError('');
    try {
      const verification = await verifyExport(docId);
      if (!verification?.passed) {
        const failed = (verification?.checks || []).filter((check) => !check.passed);
        setError(`Burned PDF verification failed: ${failed.map((check) => check.name).join(', ') || 'unknown check'}.`);
        return;
      }
      await downloadExport(docId, 'pdf');
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'object') {
        setError(detail.message || 'PDF export verification failed.');
      } else {
        setError(detail || 'PDF export is not available.');
      }
    } finally {
      setDownloading(false);
    }
  };

  const handleUndo = async () => {
    setSaving(true);
    setError('');
    try {
      await undoLastAction(docId);
      setPendingChange(null);
      setSelectedRedaction(null);
      refreshRenderedImages();
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

  const goToNextIssuePage = () => {
    if (!pages.length) return;
    const ordered = [...pages].sort((a, b) => Number(a.page_number) - Number(b.page_number));
    const currentIndex = ordered.findIndex((page) => Number(page.page_number) === Number(currentPageNumber));
    const rotated = [...ordered.slice(currentIndex + 1), ...ordered.slice(0, currentIndex + 1)];
    const target = rotated.find((page) => (
      (page.warning_count || page.vision_warnings?.length || 0) > 0 ||
      (page.redaction_count || 0) > 0 ||
      (page.ocr_confidence || 1) < 0.7
    ));
    if (target) setCurrentPageNumber(target.page_number);
  };

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
      beginDraw={beginDraw}
      continueDraw={continueDraw}
      finishDraw={finishDraw}
      draftRect={draftRect}
      pendingChange={pendingChange}
      startEdit={startEdit}
      disabledOverlay={false}
    />
  );

  const redactedCanvas = (
    <DocumentCanvas
      title="Redacted"
      imageUrl={imageUrls.redacted}
      imageSize={imageSizes.redacted}
      setImageSize={(size) => setImageSize('redacted', size)}
      zoom={zoom}
      redactions={[]}
      selectedRedaction={selectedRedaction}
      setSelectedRedaction={setSelectedRedaction}
      showOverlays={false}
      drawEnabled={false}
      stageRef={null}
      scrollRef={redactedScrollRef}
      onScroll={() => syncPaneScroll('redacted')}
      draftRect={null}
      pendingChange={null}
      startEdit={() => {}}
      disabledOverlay={drawMode && viewMode === 'both'}
    />
  );

  if (loading) {
    return (
      <div className="flex h-[calc(100dvh-4rem)] items-center justify-center bg-slate-100">
        <div className="h-10 w-10 rounded-full border-2 border-slate-300 border-t-slate-900 animate-spin" />
      </div>
    );
  }

  if (error && !documentData) {
    return (
      <div className="flex h-[calc(100dvh-4rem)] items-center justify-center bg-slate-100 px-6">
        <div className="max-w-md rounded-md border border-red-200 bg-white p-5 text-sm text-red-700 shadow-sm">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col bg-slate-100 text-slate-900">
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
            <div className="text-xs text-slate-500">
              Page {currentPageNumber} of {pages.length || 1} · {activeRedactions.length} active on page · {documentData?.status || 'unknown'}
            </div>
          </div>
        </div>

        <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
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

          <select
            value={manualType}
            onChange={(event) => setManualType(event.target.value)}
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-xs font-semibold text-slate-700"
            aria-label="Redaction type"
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
            disabled={!drawMode || !pendingChange || saving}
            className="h-9 rounded-md bg-blue-700 px-3 text-xs font-bold text-white hover:bg-blue-600 disabled:bg-slate-200 disabled:text-slate-400"
          >
            Apply
          </button>

          <button
            type="button"
            onClick={handleUndo}
            disabled={!history.length || saving}
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-bold text-slate-700 hover:bg-slate-50 disabled:bg-slate-100 disabled:text-slate-300"
          >
            Undo
          </button>

          <button
            type="button"
            onClick={goToNextWarning}
            className="h-9 rounded-md border border-amber-200 bg-white px-3 text-xs font-bold text-amber-800 hover:bg-amber-50"
          >
            Next warning
          </button>

          <button
            type="button"
            onClick={goToNextIssuePage}
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-xs font-bold text-slate-700 hover:bg-slate-50"
          >
            Next issue
          </button>

          <button
            type="button"
            onClick={() => selectedRedaction && handleReject(selectedRedaction.id)}
            disabled={!selectedCanBeRemoved || saving}
            className="h-9 rounded-md border border-red-200 bg-white px-3 text-xs font-bold text-red-700 hover:bg-red-50 disabled:border-slate-200 disabled:text-slate-300 disabled:hover:bg-white"
          >
            Remove selected
          </button>

          <div className="flex items-center rounded-md border border-slate-300 bg-white">
            <button
              type="button"
              onClick={() => setZoom((value) => Math.max(0.35, value - 0.1))}
              className="h-9 px-3 text-sm font-bold text-slate-700 hover:bg-slate-50"
              aria-label="Zoom out"
            >
              -
            </button>
            <div className="w-14 text-center text-xs font-semibold text-slate-600">
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

          <button
            type="button"
            onClick={handleApproveAll}
            className="h-9 rounded-md bg-emerald-700 px-3 text-xs font-bold text-white hover:bg-emerald-600"
          >
            Approve all
          </button>
          <button
            type="button"
            onClick={handleDownloadPdf}
            disabled={downloading}
            className="h-9 rounded-md bg-slate-950 px-3 text-xs font-bold text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {downloading ? 'Verifying' : 'Verify and download burned PDF'}
          </button>
        </div>
      </div>

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

        <main className="flex min-w-0 flex-1 flex-col overflow-hidden bg-slate-200 p-4">
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
        </main>

        <aside className="flex w-[420px] shrink-0 flex-col border-l border-slate-200 bg-white">
          <div className="border-b border-slate-200 p-4">
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-md bg-emerald-50 px-2 py-2">
                <div className="text-lg font-bold text-emerald-700">{reviewStats.approved}</div>
                <div className="text-[11px] text-emerald-700">Approved</div>
              </div>
              <div className="rounded-md bg-amber-50 px-2 py-2">
                <div className="text-lg font-bold text-amber-700">{reviewStats.pending}</div>
                <div className="text-[11px] text-amber-700">Pending</div>
              </div>
              <div className="rounded-md bg-red-50 px-2 py-2">
                <div className="text-lg font-bold text-red-700">{reviewStats.rejected}</div>
                <div className="text-[11px] text-red-700">Removed</div>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            <div className="border-b border-slate-200 p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wide text-slate-400">
                  OCR text · page {currentPageNumber}
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
                onMouseUp={captureTextSelection}
                onKeyUp={captureTextSelection}
                tabIndex={0}
                className="h-64 overflow-auto rounded-md border border-slate-300 bg-white p-3 font-mono text-xs leading-5 text-slate-800 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 whitespace-pre-wrap"
              >
                {renderHighlightedText(ocrText, highlightRanges, setSelectedRedaction)}
              </div>
              <div className="mt-2 min-h-[34px] rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">
                {selection?.text ? (
                  <span className="font-mono">{selection.text.trim().slice(0, 140)}</span>
                ) : (
                  <span>Select OCR text to create a matching redaction box.</span>
                )}
              </div>
            </div>

            <div className="border-b border-slate-200 p-4">
              <div className="mb-2 flex items-center justify-between">
                <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Vision warnings</div>
                <span className="text-[11px] font-semibold text-slate-400">
                  {currentPage?.vision_status || 'not run'}
                </span>
              </div>
              <div className="max-h-36 space-y-2 overflow-auto">
                {(currentPage?.vision_warnings || []).length ? (
                  currentPage.vision_warnings.map((warning, index) => (
                    <div key={`${warning}-${index}`} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                      {warning}
                    </div>
                  ))
                ) : (
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
                    No vision warnings for this page.
                  </div>
                )}
              </div>
            </div>

            <div className="border-b border-slate-200 p-4">
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">Redactions</div>
              <div className="max-h-56 space-y-1 overflow-auto pr-1">
                {pageRedactions.length ? pageRedactions.map((redaction) => (
                  <div
                    key={redaction.id}
                    className={`rounded-md border p-2 text-xs ${
                      selectedRedaction?.id === redaction.id
                        ? 'border-blue-300 bg-blue-50'
                        : redaction.status === 'rejected'
                          ? 'border-slate-100 bg-slate-50 opacity-70'
                          : 'border-transparent hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedRedaction(redaction)}
                        className="min-w-0 flex-1 text-left"
                      >
                        <span className="block truncate font-semibold text-slate-800">
                          {redaction.type?.replace(/_/g, ' ') || 'redaction'}
                        </span>
                      </button>
                      <span className="text-[11px] text-slate-500">{redaction.status || 'pending'}</span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={() => setSelectedRedaction(redaction)}
                        className="min-w-0 flex-1 truncate text-left text-[11px] text-slate-500"
                      >
                        {redaction.method || 'detected'} · {Math.round((redaction.confidence || 0) * 100)}%
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
                )) : (
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

                  {selectedRect && (
                    <div>
                      <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Box</div>
                      <div className="mt-1 grid grid-cols-4 gap-2 text-xs text-slate-700">
                        <div className="rounded-md bg-slate-50 px-2 py-2">X {Math.round(selectedRect.x)}</div>
                        <div className="rounded-md bg-slate-50 px-2 py-2">Y {Math.round(selectedRect.y)}</div>
                        <div className="rounded-md bg-slate-50 px-2 py-2">W {Math.round(selectedRect.width)}</div>
                        <div className="rounded-md bg-slate-50 px-2 py-2">H {Math.round(selectedRect.height)}</div>
                      </div>
                    </div>
                  )}

                  <div>
                    <div className="text-xs font-bold uppercase tracking-wide text-slate-400">Value</div>
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
