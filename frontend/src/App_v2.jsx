import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';

import ScanUpload from './components/ScanUpload';
import ProcessingProgress from './components/ProcessingProgress';
import OCRResult from './components/OCRResult';
import RedactionPreview from './components/RedactionPreview';
import TranslationResult from './components/TranslationResult';
import RoutingUrgency from './components/RoutingUrgency';
import FinalRecord from './components/FinalRecord';
import DocumentList from './components/DocumentList';
import ReviewStudio from './components/ReviewStudio';
import ReviewQueue from './components/ReviewQueue';
import BatchDashboard from './components/BatchDashboard';
import {
  MULTI_USER_AUTH_ENABLED,
  clearAuthSession,
  getMe,
  getStoredUser,
  loginUser,
  logoutUser,
  registerUser,
} from './api';

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('processor');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const data = mode === 'setup'
        ? await registerUser(email, password, role)
        : await loginUser(email, password);
      onAuthenticated(data.user);
    } catch (err) {
      setError(err.response?.data?.detail || 'Sign in failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-slate-50">
      <div className="mx-auto flex min-h-[100dvh] w-full max-w-md flex-col justify-center px-5">
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-5">
            <h1 className="text-lg font-bold text-slate-900">Synthetiq Redact</h1>
            <p className="mt-1 text-sm text-slate-500">
              Council redaction review workspace
            </p>
          </div>

          <div className="mb-4 grid grid-cols-2 rounded-lg bg-slate-100 p-1 text-sm font-semibold">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={`rounded-md px-3 py-2 ${mode === 'login' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'}`}
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => setMode('setup')}
              className={`rounded-md px-3 py-2 ${mode === 'setup' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'}`}
            >
              First setup
            </button>
          </div>

          <form onSubmit={submit} className="space-y-3">
            <label className="block">
              <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Email</span>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                required
              />
            </label>
            <label className="block">
              <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                required
                minLength={8}
              />
            </label>
            {mode === 'setup' && (
              <label className="block">
                <span className="text-xs font-bold uppercase tracking-wide text-slate-500">Role</span>
                <select
                  value={role}
                  onChange={(event) => setRole(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                >
                  <option value="processor">Processor</option>
                  <option value="reviewer">Reviewer</option>
                  <option value="auditor">Auditor</option>
                  <option value="dpo">DPO</option>
                  <option value="admin">Admin</option>
                </select>
                <p className="mt-1 text-xs text-slate-500">The first account is created as admin.</p>
              </label>
            )}
            {error && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-lg bg-emerald-600 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-500 disabled:opacity-60"
            >
              {busy ? 'Please wait...' : mode === 'setup' ? 'Create first admin' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function AppContent({ user, onLogout }) {
  const [screen, setScreen] = useState('scan');
  const [docId, setDocId] = useState(null);
  const [docData, setDocData] = useState(null);
  const [progress, setProgress] = useState({ status: '', message: '', percent: 0 });

  const commonProps = {
    setScreen,
    docId,
    setDocId,
    docData,
    setDocData,
    progress,
    setProgress,
  };

  const renderScreen = () => {
    switch (screen) {
      case 'scan':
        return <ScanUpload {...commonProps} />;
      case 'progress':
        return <ProcessingProgress {...commonProps} />;
      case 'ocr':
        return <OCRResult {...commonProps} />;
      case 'redaction':
        return <RedactionPreview {...commonProps} />;
      case 'translation':
        return <TranslationResult {...commonProps} />;
      case 'routing':
        return <RoutingUrgency {...commonProps} />;
      case 'final':
        return <FinalRecord {...commonProps} />;
      case 'list':
        return <DocumentList {...commonProps} />;
      case 'review':
        return <ReviewStudio docId={docId} setScreen={setScreen} />;
      case 'review-queue':
        return <ReviewQueue setScreen={setScreen} setDocId={setDocId} />;
      case 'batch':
        return <BatchDashboard {...commonProps} />;
      default:
        return <ScanUpload {...commonProps} />;
    }
  };

  // Step breadcrumb for result screens
  const RESULT_SCREENS = ['ocr', 'redaction', 'routing', 'final'];
  const currentStep = RESULT_SCREENS.indexOf(screen);

  return (
    <div className="min-h-[100dvh] bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-slate-900 text-white shadow-md">
        <div className="screen-container flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-sm font-semibold leading-tight tracking-wide sm:text-base">
              Synthetiq Redact
            </h1>
            <p className="text-[10px] uppercase tracking-widest text-slate-400 sm:text-xs">
              Council redaction review
            </p>
          </div>
          <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
            <button
              onClick={() => setScreen('review-queue')}
              className="whitespace-nowrap rounded-md bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              Review queue
            </button>
            <button
              onClick={() => setScreen('batch')}
              className="whitespace-nowrap rounded-md bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              Batch
            </button>
            <button
              onClick={() => setScreen('list')}
              className="whitespace-nowrap rounded-md bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              Documents
            </button>
            <button
              onClick={() => { setScreen('scan'); setDocData(null); }}
              className="whitespace-nowrap rounded-md bg-emerald-700 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-600"
            >
              New
            </button>
            <div className="hidden items-center gap-2 border-l border-slate-700 pl-3 text-xs text-slate-300 sm:flex">
              <span>{user?.email}</span>
              <span className="rounded bg-slate-800 px-2 py-1 uppercase text-slate-400">
                {MULTI_USER_AUTH_ENABLED ? user?.role : 'local'}
              </span>
              {MULTI_USER_AUTH_ENABLED && (
                <button
                  onClick={onLogout}
                  className="rounded-lg bg-slate-800 px-3 py-2 font-medium text-slate-200 hover:bg-slate-700"
                >
                  Sign out
                </button>
              )}
            </div>
          </div>
        </div>
        {/* Step breadcrumb shown during result review */}
        {currentStep >= 0 && (
          <div className="screen-container pb-2">
            <div className="flex gap-1">
              {[['ocr','Text'],['redaction','Redactions'],['routing','Routing'],['final','Final review']].map(([key, label], i) => (
                <button key={key}
                  onClick={() => docData && setScreen(key)}
                  className={`flex-1 text-center py-1 rounded text-[10px] font-bold transition-colors ${
                    screen === key ? 'bg-emerald-500 text-white' :
                    i < currentStep ? 'bg-slate-700 text-slate-300' :
                    'bg-slate-800 text-slate-500'
                  }`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </header>

      {/* Main content */}
      <main className={screen === 'review' ? 'w-full' : 'screen-container'}>
        {renderScreen()}
      </main>
    </div>
  );
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState(
    MULTI_USER_AUTH_ENABLED
      ? getStoredUser()
      : { id: 1, email: 'local_user', role: 'admin' }
  );

  useEffect(() => {
    if (!MULTI_USER_AUTH_ENABLED) {
      clearAuthSession();
      setUser({ id: 1, email: 'local_user', role: 'admin' });
      setAuthChecked(true);
      return undefined;
    }

    let mounted = true;
    async function loadUser() {
      try {
        const current = await getMe();
        if (mounted) setUser(current);
      } catch {
        clearAuthSession();
        if (mounted) setUser(null);
      } finally {
        if (mounted) setAuthChecked(true);
      }
    }
    loadUser();

    const handleExpired = () => {
      setUser(null);
      setAuthChecked(true);
    };
    window.addEventListener('synthetiq:auth-expired', handleExpired);
    return () => {
      mounted = false;
      window.removeEventListener('synthetiq:auth-expired', handleExpired);
    };
  }, []);

  const handleLogout = async () => {
    await logoutUser();
    setUser(null);
  };

  if (!authChecked) {
    return (
      <div className="flex min-h-[100dvh] items-center justify-center bg-slate-50 text-sm text-slate-500">
        Loading...
      </div>
    );
  }

  if (!user) {
    return <AuthScreen onAuthenticated={setUser} />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="*" element={<AppContent user={user} onLogout={handleLogout} />} />
      </Routes>
    </BrowserRouter>
  );
}
