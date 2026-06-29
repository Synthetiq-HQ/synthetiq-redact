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
import Library from './components/Library';
import Preferences from './components/Preferences';
import ProvenanceLookup from './components/ProvenanceLookup';
import { BrandHomeButton, BrandSplash, BrandWordmark } from './components/Branding';
import {
  MULTI_USER_AUTH_ENABLED,
  clearAuthSession,
  getHealth,
  getMe,
  getStoredUser,
  loginUser,
  logoutUser,
  registerUser,
} from './api';

const APP_VERSION = 'v3.1';

// Minimal inline icons for the navigation rail (no icon dependency).
const ICONS = {
  new: 'M12 5v14M5 12h14',
  inbox: 'M3 13h4l2 3h6l2-3h4M5 5h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
  library: 'M4 5h16v14H4zM8 5v14M4 10h16',
  queue: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  batch: 'M12 2 2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  find: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 21l-4.3-4.3',
};

function RailIcon({ path }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className="h-5 w-5">
      <path d={path} />
    </svg>
  );
}

function RailButton({ active, label, onClick, path, accent }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      className={`flex w-full flex-col items-center gap-1 py-3 text-[10px] font-semibold transition-colors ${
        active
          ? 'bg-slate-800 text-white'
          : accent
            ? 'text-emerald-300 hover:bg-slate-800 hover:text-emerald-200'
            : 'text-slate-400 hover:bg-slate-800 hover:text-white'
      }`}
    >
      <RailIcon path={path} />
      <span className="leading-none">{label}</span>
    </button>
  );
}

function SystemStatus() {
  const [state, setState] = useState({ online: null, version: '', degraded: false });

  useEffect(() => {
    let active = true;
    let timer = null;
    const poll = async () => {
      try {
        const h = await getHealth();
        if (active) setState({ online: true, version: h?.version || '', degraded: h?.status === 'degraded' });
      } catch {
        if (active) setState({ online: false, version: '', degraded: false });
      } finally {
        if (active) {
          timer = window.setTimeout(poll, state.online ? 15000 : 2000);
        }
      }
    };
    poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [state.online]);

  const color = state.online == null
    ? 'bg-slate-500'
    : !state.online
      ? 'bg-red-500'
      : state.degraded
        ? 'bg-amber-400'
        : 'bg-emerald-400';
  const label = state.online == null
    ? 'Connecting…'
    : !state.online
      ? 'Backend offline'
      : state.degraded
        ? 'Degraded'
        : 'Online';

  return (
    <div className="flex flex-col items-center gap-1 py-3" title={`Backend ${label}${state.version ? ` · API ${state.version}` : ''}`}>
      <span className={`h-2.5 w-2.5 rounded-full ${color} ${state.online ? 'shadow-[0_0_6px] shadow-current' : ''}`} />
      <span className="text-[9px] font-semibold leading-none text-slate-400">{label}</span>
    </div>
  );
}

const SCREEN_TITLES = {
  scan: 'New document',
  list: 'Document inbox',
  library: 'Library',
  'review-queue': 'Review queue',
  batch: 'Batch processing',
  progress: 'Processing',
  ocr: 'Extracted text',
  redaction: 'Redactions',
  translation: 'Translation',
  routing: 'Routing',
  final: 'Final review',
  provenance: 'Find ID',
  preferences: 'Account',
};

const LAST_WORKSPACE_KEY = 'synthetiq_redact_v31:last-workspace';

function readLastWorkspace() {
  try {
    const raw = localStorage.getItem(LAST_WORKSPACE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function writeLastWorkspace(data) {
  try {
    localStorage.setItem(LAST_WORKSPACE_KEY, JSON.stringify(data));
  } catch {
    // If storage is unavailable, the live app still works normally.
  }
}

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
    <div className="brand-theme min-h-[100dvh] bg-slate-50">
      <div className="mx-auto flex min-h-[100dvh] w-full max-w-md flex-col justify-center px-5">
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-5">
            <BrandWordmark className="h-9 max-w-[280px]" />
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
  const [workspaceSeed] = useState(() => readLastWorkspace());
  const [screen, setScreen] = useState(() => (
    workspaceSeed.screen === 'review' && !workspaceSeed.docId ? 'list' : workspaceSeed.screen || 'list'
  ));
  const [docId, setDocId] = useState(() => workspaceSeed.docId || null);
  const [docData, setDocData] = useState(null);
  const [progress, setProgress] = useState({ status: '', message: '', percent: 0 });
  const [homePulseKey, setHomePulseKey] = useState(0);

  useEffect(() => {
    const stableScreens = new Set(['scan', 'list', 'library', 'review', 'batch']);
    writeLastWorkspace({
      screen: stableScreens.has(screen) ? screen : 'list',
      docId,
      savedAt: new Date().toISOString(),
    });
  }, [screen, docId]);

  const goHome = () => {
    setHomePulseKey((key) => key + 1);
    setScreen('list');
  };

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
      case 'library':
        return <Library {...commonProps} />;
      case 'review':
        return <ReviewStudio docId={docId} setScreen={setScreen} />;
      case 'review-queue':
        return <ReviewQueue setScreen={setScreen} setDocId={setDocId} />;
      case 'batch':
        return <BatchDashboard {...commonProps} />;
      case 'preferences':
        return <Preferences setScreen={setScreen} />;
      case 'provenance':
        return <ProvenanceLookup {...commonProps} />;
      default:
        return <DocumentList {...commonProps} />;
    }
  };

  const isEditor = screen === 'review';
  const userInitial = (user?.email || 'L').trim().charAt(0).toUpperCase();
  const userRole = MULTI_USER_AUTH_ENABLED ? user?.role : 'local';

  return (
    <div className="brand-theme flex h-[100dvh] w-full select-none overflow-hidden bg-slate-100 text-slate-900">
      {/* Navigation rail */}
      <nav className="flex w-[72px] shrink-0 flex-col border-r border-slate-800 bg-slate-900">
        <BrandHomeButton
          onClick={goHome}
          active={screen === 'list'}
          pulseKey={homePulseKey}
        />
        <button
          type="button"
          onClick={() => setScreen('list')}
          title="Synthetiq Redact — home"
          className="hidden"
        >
          <span className="text-sm font-black tracking-tight text-white">SR</span>
          <span className="text-[8px] font-bold uppercase tracking-widest text-emerald-400">{APP_VERSION}</span>
        </button>

        <div className="flex flex-1 flex-col">
          <RailButton label="New" path={ICONS.new} accent
            active={screen === 'scan'} onClick={() => { setScreen('scan'); setDocData(null); }} />
          <RailButton label="Inbox" path={ICONS.inbox}
            active={screen === 'list'} onClick={() => setScreen('list')} />
          <RailButton label="Library" path={ICONS.library}
            active={screen === 'library'} onClick={() => setScreen('library')} />
          <RailButton label="Batch" path={ICONS.batch}
            active={screen === 'batch'} onClick={() => setScreen('batch')} />
        </div>

        <div className="border-t border-slate-800">
          <RailButton label="Find ID" path={ICONS.find}
            active={screen === 'provenance'} onClick={() => setScreen('provenance')} />
          <SystemStatus />
          <button
            type="button"
            onClick={() => setScreen('preferences')}
            className={`flex w-full flex-col items-center gap-1 border-t border-slate-800 py-3 hover:bg-slate-800 ${screen === 'preferences' ? 'bg-slate-800' : ''}`}
            title={`${user?.email || 'local user'} · ${userRole}`}>
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-700 text-xs font-bold text-white">
              {userInitial}
            </span>
            <span className="text-[9px] font-semibold text-slate-400">Account</span>
          </button>
          <div className="flex flex-col items-center gap-1 py-2">
            {MULTI_USER_AUTH_ENABLED && (
              <button type="button" onClick={onLogout}
                className="text-[9px] font-semibold text-slate-400 hover:text-white">
                Sign out
              </button>
            )}
          </div>
        </div>
      </nav>

      {/* Workspace */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {isEditor ? (
          <div className="min-h-0 flex-1">
            {renderScreen()}
          </div>
        ) : (
          <>
            <header className="relative flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-4">
              <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 text-lg font-black tracking-tight text-slate-950">
                Synthetiq Redact
              </div>
              <button
                type="button"
                onClick={() => { setScreen('scan'); setDocData(null); }}
                className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-emerald-500"
              >
                + New document
              </button>
            </header>
            <main className="min-h-0 flex-1 overflow-auto bg-slate-100">
              <div className={(screen === 'list' || screen === 'batch' || screen === 'library') ? 'h-full p-3' : 'mx-auto max-w-5xl p-4'}>
                {renderScreen()}
              </div>
            </main>
          </>
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  // Wait for the local backend before showing the app, so a cold start shows a
  // branded loading screen instead of erroring. Capped so it never hangs.
  const [backendReady, setBackendReady] = useState(false);
  const [backendSlow, setBackendSlow] = useState(false);
  const [user, setUser] = useState(
    MULTI_USER_AUTH_ENABLED
      ? getStoredUser()
      : { id: 1, email: 'local_user', role: 'admin' }
  );

  useEffect(() => {
    let active = true;
    const start = Date.now();
    const slowTimer = window.setTimeout(() => active && setBackendSlow(true), 8000);
    const poll = async () => {
      if (!active) return;
      try {
        await getHealth();
        if (active) setBackendReady(true);
      } catch {
        if (!active) return;
        // Grace cap: after 25s let the user in anyway (the app then retries on its own).
        if (Date.now() - start > 25000) setBackendReady(true);
        else window.setTimeout(poll, 1000);
      }
    };
    poll();
    return () => { active = false; window.clearTimeout(slowTimer); };
  }, []);

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

  if (!backendReady) {
    return (
      <BrandSplash
        message={backendSlow
          ? 'Starting the local engine… first launch can take a little longer.'
          : 'Starting Synthetiq Redact…'}
      />
    );
  }

  if (!authChecked) {
    return <BrandSplash message="Opening Synthetiq Redact..." />;
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
