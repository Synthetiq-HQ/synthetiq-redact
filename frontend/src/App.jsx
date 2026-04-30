import { useState } from 'react';

import ScanUpload from './components/ScanUpload';
import ProcessingProgress from './components/ProcessingProgress';
import OCRResult from './components/OCRResult';
import RedactionPreview from './components/RedactionPreview';
import TranslationResult from './components/TranslationResult';
import RoutingUrgency from './components/RoutingUrgency';
import FinalRecord from './components/FinalRecord';
import DocumentList from './components/DocumentList';

export default function App() {
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
        <div className="screen-container flex items-center justify-between py-3">
          <div className="flex items-center gap-2">
            <div className="text-xl">🏛️</div>
            <div>
              <h1 className="text-sm font-bold leading-tight tracking-wide sm:text-base">
                HILLINGDON COUNCIL
              </h1>
              <p className="text-[10px] uppercase tracking-widest text-slate-400 sm:text-xs">
                AI Document Processor
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setScreen('list')}
              className="rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              📋
            </button>
            <button
              onClick={() => { setScreen('scan'); setDocData(null); }}
              className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white hover:bg-emerald-500"
            >
              ➕ New
            </button>
          </div>
        </div>
        {/* Step breadcrumb shown during result review */}
        {currentStep >= 0 && (
          <div className="screen-container pb-2">
            <div className="flex gap-1">
              {[['ocr','🔍 Text'],['redaction','🛡️ Redact'],['routing','📬 Route'],['final','✅ Review']].map(([key, label], i) => (
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
      <main className="screen-container">
        {renderScreen()}
      </main>
    </div>
  );
}
