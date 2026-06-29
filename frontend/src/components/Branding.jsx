const BRAND_ICON = '/brand/synthetiq-redact-icon-transparent.png';
const BRAND_WORDMARK = '/brand/synthetiq-redact-wordmark.png';

export function BrandSplash({ message }) {
  return (
    <div className="brand-splash" aria-label="Launching Synthetiq Redact">
      <div className="brand-splash__stage brand-splash__stage--single">
        <div className="brand-splash__copy brand-splash__copy--single">
          <img
            className="brand-splash__wordmark brand-splash__wordmark--single"
            src={BRAND_WORDMARK}
            alt="Synthetiq Redact"
          />
          <div className="brand-splash__loader" aria-hidden="true">
            <span />
          </div>
          {message && (
            <p className="mt-4 text-sm font-medium text-slate-300">{message}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function BrandHomeButton({ onClick, active, pulseKey }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Synthetiq Redact home"
      className={`brand-home-button ${active ? 'brand-home-button--active' : ''}`}
    >
      <span key={pulseKey} className="brand-home-button__mark">
        <img src={BRAND_ICON} alt="" />
      </span>
    </button>
  );
}

export function BrandWordmark({ className = '' }) {
  return (
    <img
      src={BRAND_WORDMARK}
      alt="Synthetiq Redact"
      className={`block h-7 w-auto max-w-[220px] object-contain ${className}`}
      draggable="false"
    />
  );
}
