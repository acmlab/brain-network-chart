export const Spinner = ({ size = 'h-8 w-8', color = 'text-indigo-500' }) => (
  <svg className={`animate-spin ${size} ${color}`} fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

export const StatusBadge = ({ status }) => {
  const map = {
    pending: { bg: 'bg-amber-50', text: 'text-amber-700', dot: 'bg-amber-400', pulse: true },
    processing: { bg: 'bg-indigo-50', text: 'text-indigo-700', dot: 'bg-indigo-400', pulse: true },
    completed: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500', pulse: false },
    error: { bg: 'bg-red-50', text: 'text-red-700', dot: 'bg-red-400', pulse: false },
    cancelled: { bg: 'bg-slate-100', text: 'text-slate-500', dot: 'bg-slate-400', pulse: false },
  };
  const s = map[status] || map.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${s.pulse ? 'animate-pulse' : ''}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
};

export const ErrorBanner = ({ error, onDismiss }) => {
  if (!error) return null;
  return (
    <div className="mb-4 flex items-start gap-2.5 p-3.5 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm">
      <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
      </svg>
      <span className="flex-1">{error}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="opacity-50 hover:opacity-100 transition-opacity">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
};

export const getHeatColor = (t) => {
  let clamped = Math.max(0, Math.min(1, t));
  if (clamped < 0.5) {
    const s = clamped * 2;
    return `rgb(${Math.round(59 + 196 * s)},${Math.round(130 + 125 * s)},${Math.round(246 + 9 * s)})`;
  }
  const s = (clamped - 0.5) * 2;
  return `rgb(${Math.round(255 - 16 * s)},${Math.round(255 - 187 * s)},${Math.round(255 - 187 * s)})`;
};
