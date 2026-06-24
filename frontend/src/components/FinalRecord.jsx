import { useState } from 'react';
import { approveDocument, flagForReview, downloadExport } from '../api';
import StatusBadge from './StatusBadge';

export default function FinalRecord({ setScreen, docId, docData, setDocData }) {
  const [actionState, setActionState] = useState('idle'); // idle | approving | flagging | success
  const [actionMessage, setActionMessage] = useState('');
  const [exportError, setExportError] = useState('');

  const handleDownload = async (type) => {
    setExportError('');
    try {
      await downloadExport(docId, type);
    } catch (err) {
      setExportError(err.response?.data?.detail || 'Export is not available yet.');
    }
  };

  const handleApprove = async () => {
    setActionState('approving');
    try {
      await approveDocument(docId);
      setActionState('success');
      setActionMessage('Document approved and stored successfully.');
      setDocData((prev) => (prev ? { ...prev, status: 'review_approved' } : prev));
      setTimeout(() => setScreen('list'), 1500);
    } catch (err) {
      setActionState('idle');
      setActionMessage(`Approval failed: ${err.message}`);
    }
  };

  const handleFlag = async () => {
    setActionState('flagging');
    try {
      await flagForReview(docId);
      setActionState('success');
      setActionMessage('Document flagged for human review.');
      setDocData((prev) => (prev ? { ...prev, status: 'needs_review' } : prev));
      setTimeout(() => setScreen('list'), 1500);
    } catch (err) {
      setActionState('idle');
      setActionMessage(`Flag failed: ${err.message}`);
    }
  };

  return (
    <div className="flex flex-col gap-4 py-4">
      <div className="text-center">
        <h2 className="text-xl font-bold text-slate-800">Final review</h2>
        <p className="text-sm text-slate-500 mt-1">Document #{docId} · {docData?.filename}</p>
      </div>

      {/* Summary grid */}
      <div className="rounded-2xl bg-slate-50 border border-slate-200 p-4 grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">Category</div>
          <div className="text-sm font-semibold text-slate-700 capitalize">{(docData?.category ?? 'unknown').replace(/_/g,' ')}</div>
        </div>
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">Department</div>
          <div className="text-sm font-semibold text-slate-700">{docData?.department ?? '—'}</div>
        </div>
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">Urgency</div>
          <div className="text-sm font-semibold text-slate-700">{Math.round((docData?.urgency_score ?? 0) * 100)}%</div>
        </div>
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">AI Confidence</div>
          <div className="text-sm font-semibold text-slate-700">{Math.round((docData?.confidence_score ?? 0) * 100)}%</div>
        </div>
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">Language</div>
          <div className="text-sm font-semibold text-slate-700 uppercase">{docData?.language_detected ?? 'en'}{docData?.translated ? ' → EN' : ''}</div>
        </div>
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">Handwriting</div>
          <div className="text-sm font-semibold text-slate-700">
            {docData?.handwriting_backend ?? 'easyocr_baseline'} · {Math.round((docData?.handwriting_confidence ?? 0) * 100)}%
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-400 font-bold uppercase tracking-wide mb-0.5">Status</div>
          <StatusBadge status={docData?.status ?? 'complete'} />
        </div>
      </div>

      {actionState === 'success' ? (
        <div className="rounded-2xl bg-emerald-50 border border-emerald-200 px-5 py-5 text-center">
          <div className="text-3xl mb-2">✅</div>
          <div className="font-bold text-emerald-800">{actionMessage}</div>
          <button onClick={() => { setScreen('scan'); setDocData(null); }}
            className="mt-4 w-full py-3 rounded-xl bg-emerald-600 text-white font-bold hover:bg-emerald-500">
            Process Another Document
          </button>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <button type="button" onClick={() => handleDownload('docx')}
            className="w-full rounded-lg bg-slate-900 px-4 py-4 text-base font-bold text-white shadow-sm hover:bg-slate-800">
            Download redacted document
          </button>
          <button type="button" onClick={() => handleDownload('pdf')}
            className="w-full rounded-lg bg-slate-800 px-4 py-4 text-base font-bold text-white shadow-sm hover:bg-slate-700">
            Download burned PDF
          </button>
          <button onClick={handleApprove} disabled={actionState !== 'idle'}
            className="w-full py-4 rounded-2xl bg-emerald-600 text-white font-bold text-base flex items-center justify-center gap-2 shadow-lg hover:bg-emerald-500 disabled:opacity-60">
            {actionState === 'approving'
              ? <><span className="h-5 w-5 rounded-full border-2 border-white border-t-transparent animate-spin" />Approving...</>
              : <>Approve release</>}
          </button>
          <button onClick={handleFlag} disabled={actionState !== 'idle'}
            className="w-full py-4 rounded-2xl bg-amber-500 text-white font-bold text-base flex items-center justify-center gap-2 shadow hover:bg-amber-400 disabled:opacity-60">
            {actionState === 'flagging'
              ? <><span className="h-5 w-5 rounded-full border-2 border-white border-t-transparent animate-spin" />Flagging...</>
              : <>Send to human review</>}
          </button>
          <button type="button" onClick={() => handleDownload('text')}
            className="w-full py-3 rounded-xl bg-slate-800 text-white font-semibold text-sm flex items-center justify-center gap-2 hover:bg-slate-700">
            Download redacted text
          </button>
          <div className="grid grid-cols-2 gap-2">
            <button type="button" onClick={() => handleDownload('clean')}
              className="py-3 rounded-xl bg-slate-100 text-slate-700 font-semibold text-sm flex items-center justify-center gap-2 hover:bg-slate-200">
              OCR text
            </button>
            <button type="button" onClick={() => handleDownload('json')}
              className="py-3 rounded-xl bg-slate-100 text-slate-700 font-semibold text-sm flex items-center justify-center gap-2 hover:bg-slate-200">
              Metadata JSON
            </button>
          </div>
          {exportError && (
            <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {exportError}
            </div>
          )}
          {docData?.handwriting_review_reason && (
            <div className="rounded-xl bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800">
              {docData.handwriting_review_reason}
            </div>
          )}
          <div className="flex gap-2">
            <button onClick={() => setScreen('scan')}
              className="flex-1 py-3 rounded-xl bg-slate-200 text-slate-700 font-semibold text-sm hover:bg-slate-300">
              New document
            </button>
            <button onClick={() => setScreen('list')}
              className="flex-1 py-3 rounded-xl bg-slate-200 text-slate-700 font-semibold text-sm hover:bg-slate-300">
              All documents
            </button>
          </div>
        </div>
      )}

      {actionState === 'idle' && actionMessage && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">{actionMessage}</div>
      )}
    </div>
  );
}
