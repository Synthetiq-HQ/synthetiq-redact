import { useState, useEffect } from 'react';
import api from '../api';

export default function BatchDashboard({ setScreen, setDocId }) {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState([]);

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadJobs = async () => {
    try {
      // In a real implementation, this would call GET /api/batch/list
      // For now, we mock the data structure
      setJobs([
        {
          id: 'batch-001',
          name: 'Housing Applications Q1',
          status: 'complete',
          total_docs: 60,
          processed_docs: 60,
          failed_docs: 0,
          progress_percent: 100,
          created_at: '2026-04-28T10:00:00Z',
          completed_at: '2026-04-28T10:15:00Z',
        },
        {
          id: 'batch-002',
          name: 'Parking Appeals April',
          status: 'processing',
          total_docs: 20,
          processed_docs: 9,
          failed_docs: 0,
          progress_percent: 45,
          created_at: '2026-04-30T09:00:00Z',
        },
      ]);
      setLoading(false);
    } catch (err) {
      console.error('Failed to load batches:', err);
      setLoading(false);
    }
  };

  const handleFileSelect = (e) => {
    setSelectedFiles(Array.from(e.target.files));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    
    setUploading(true);
    const formData = new FormData();
    selectedFiles.forEach(file => formData.append('files', file));
    formData.append('name', 'Batch Upload ' + new Date().toLocaleString());
    
    try {
      await api.post('/batch', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setSelectedFiles([]);
      loadJobs();
    } catch (err) {
      console.error('Upload failed:', err);
      alert('Upload failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setUploading(false);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'complete': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
      case 'processing': return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'queued': return 'bg-slate-100 text-slate-600 border-slate-200';
      case 'failed': return 'bg-red-100 text-red-700 border-red-200';
      default: return 'bg-slate-100 text-slate-600';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'complete': return '✅';
      case 'processing': return '⏳';
      case 'queued': return '⏸️';
      case 'failed': return '❌';
      default: return '○';
    }
  };

  return (
    <div className="min-h-[calc(100dvh-4rem)] bg-slate-50 p-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Batch Processing</h1>
            <p className="text-sm text-slate-500">Upload and process multiple documents at once</p>
          </div>
        </div>

        {/* Upload section */}
        <div className="bg-white rounded-lg border border-slate-200 p-6 mb-6">
          <h2 className="font-bold text-slate-800 mb-4">Upload New Batch</h2>
          
          <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-emerald-500 transition-colors">
            <input
              type="file"
              multiple
              accept=".png,.jpg,.jpeg,.pdf"
              onChange={handleFileSelect}
              className="hidden"
              id="batch-upload"
            />
            <label htmlFor="batch-upload" className="cursor-pointer">
              <div className="text-4xl mb-2">📁</div>
              <p className="text-sm font-medium text-slate-700">
                {selectedFiles.length > 0 
                  ? `${selectedFiles.length} files selected` 
                  : 'Drop files here or click to select'}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                Supports: PNG, JPG, JPEG, PDF
              </p>
            </label>
          </div>
          
          {selectedFiles.length > 0 && (
            <div className="mt-4 flex items-center justify-between">
              <div className="text-sm text-slate-600">
                {selectedFiles.map(f => f.name).join(', ')}
              </div>
              <button
                onClick={handleUpload}
                disabled={uploading}
                className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-bold hover:bg-emerald-500 disabled:opacity-50"
              >
                {uploading ? 'Uploading...' : '🚀 Start Processing'}
              </button>
            </div>
          )}
        </div>

        {/* Jobs list */}
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-slate-200">
            <h2 className="font-bold text-slate-800">Processing Jobs</h2>
          </div>
          
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600"></div>
            </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <div className="text-4xl mb-2">📭</div>
              <p>No batch jobs yet</p>
            </div>
          ) : (
            <div className="divide-y divide-slate-200">
              {jobs.map(job => (
                <div key={job.id} className="px-6 py-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <span className="text-lg">{getStatusIcon(job.status)}</span>
                      <div>
                        <h3 className="font-semibold text-slate-800">{job.name}</h3>
                        <p className="text-xs text-slate-500">ID: {job.id}</p>
                      </div>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs font-bold border ${getStatusColor(job.status)}`}>
                      {job.status.toUpperCase()}
                    </span>
                  </div>
                  
                  {/* Progress bar */}
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs text-slate-500 mb-1">
                      <span>{job.processed_docs} / {job.total_docs} processed</span>
                      <span>{job.progress_percent}%</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div 
                        className={`h-full rounded-full transition-all ${
                          job.status === 'complete' ? 'bg-emerald-500' : 'bg-blue-500'
                        }`}
                        style={{ width: `${job.progress_percent}%` }}
                      ></div>
                    </div>
                  </div>
                  
                  {/* Stats */}
                  <div className="flex items-center gap-4 mt-3 text-xs text-slate-500">
                    <span>✅ {job.processed_docs} done</span>
                    {job.failed_docs > 0 && <span>❌ {job.failed_docs} failed</span>}
                    <span>📅 {new Date(job.created_at).toLocaleDateString()}</span>
                    {job.completed_at && (
                      <span>🏁 {new Date(job.completed_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
