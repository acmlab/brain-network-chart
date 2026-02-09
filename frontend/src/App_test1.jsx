import { useState, useEffect, useMemo } from 'react';
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';

/* ═══════════════════════════════════════════════════════════════════════════
   CONSTANTS
   ═══════════════════════════════════════════════════════════════════════════ */

const ANALYSIS_METHODS = {
  cfc_wavelet: {
    name: 'CFC Wavelet Analysis',
    description: 'Cross-Frequency Coupling using Harmonic Wavelets',
    config: {
      window: 50,
      step: 3,
      padding: false,
      ratio: 0.1,
      wavelets_num: 10,
      beta: 1.0,
      gamma: 0.1,
      max_iter: 100,
      min_err: 0.000001,
      node_select: 10,
    },
  },
  hub_detection: {
    name: 'Hub Detection',
    description: 'Detect hub nodes in brain networks using Grassmann manifold optimization',
    config: {
      window: 50,
      step: 3,
      padding: false,
      ratio: 0.1,
      k: 2,
      hub_num: 10,
      use_group: false,
    },
  },
};

/* ═══════════════════════════════════════════════════════════════════════════
   TOAST NOTIFICATION SYSTEM
   ═══════════════════════════════════════════════════════════════════════════ */

let _toastId = 0;
let _setToasts = null;

export const showToast = (message, type = 'error') => {
  if (!_setToasts) return;
  const id = ++_toastId;
  _setToasts(prev => [...prev, { id, message, type }]);
  setTimeout(() => _setToasts?.(prev => prev.filter(t => t.id !== id)), 4500);
};

const ToastContainer = () => {
  const [toasts, setToasts] = useState([]);
  useEffect(() => {
    _setToasts = setToasts;
    return () => { _setToasts = null; };
  }, []);

  const styleMap = {
    error:   'bg-red-50 border-red-200 text-red-700',
    success: 'bg-emerald-50 border-emerald-200 text-emerald-700',
    warning: 'bg-amber-50 border-amber-200 text-amber-700',
  };

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 w-full max-w-sm pointer-events-none">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-2.5 p-3.5 rounded-xl border shadow-lg text-sm animate-slide-up ${styleMap[t.type] || styleMap.error}`}
        >
          <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            {t.type === 'success'
              ? <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              : <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            }
          </svg>
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => setToasts(prev => prev.filter(x => x.id !== t.id))}
            className="opacity-50 hover:opacity-100 transition-opacity"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ))}
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   SHARED UI PRIMITIVES
   ═══════════════════════════════════════════════════════════════════════════ */

const Spinner = ({ size = 'h-8 w-8', color = 'text-indigo-500' }) => (
  <svg className={`animate-spin ${size} ${color}`} fill="none" viewBox="0 0 24 24">
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
  </svg>
);

const StatusBadge = ({ status }) => {
  const map = {
    pending:    { bg: 'bg-amber-50',   text: 'text-amber-700',   dot: 'bg-amber-400',   pulse: true },
    processing: { bg: 'bg-indigo-50',  text: 'text-indigo-700',  dot: 'bg-indigo-400',  pulse: true },
    completed:  { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500', pulse: false },
    error:      { bg: 'bg-red-50',     text: 'text-red-700',     dot: 'bg-red-400',     pulse: false },
    cancelled:  { bg: 'bg-slate-100',  text: 'text-slate-500',   dot: 'bg-slate-400',   pulse: false },
  };
  const s = map[status] || map.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${s.bg} ${s.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot} ${s.pulse ? 'animate-pulse' : ''}`} />
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
};

const ErrorBanner = ({ error, onDismiss }) => {
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

/** Diverging color scale: Blue → White → Red */
const getHeatColor = (t) => {
  t = Math.max(0, Math.min(1, t));
  if (t < 0.5) {
    const s = t * 2;
    return `rgb(${Math.round(59 + 196 * s)},${Math.round(130 + 125 * s)},${Math.round(246 + 9 * s)})`;
  }
  const s = (t - 0.5) * 2;
  return `rgb(${Math.round(255 - 16 * s)},${Math.round(255 - 187 * s)},${Math.round(255 - 187 * s)})`;
};

/* ═══════════════════════════════════════════════════════════════════════════
   FLOATING LLM CHAT
   ═══════════════════════════════════════════════════════════════════════════ */

const FloatingLLMChat = ({ isOpen, onToggle, messages, input, onInputChange, onSend }) => {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
  };

  return (
    <>
      <button
        onClick={onToggle}
        className={`fixed bottom-6 right-6 w-14 h-14 rounded-2xl shadow-panel flex items-center justify-center transition-all duration-200 z-50 ${
          isOpen ? 'bg-slate-600 hover:bg-slate-700 text-white' : 'bg-slate-850 text-white hover:shadow-glow'
        }`}
        title={isOpen ? 'Close Chat' : 'Open AI Assistant'}
      >
        {isOpen ? (
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        )}
      </button>

      {isOpen && (
        <div className="fixed bottom-24 right-6 w-[380px] h-[520px] bg-white rounded-2xl shadow-panel border border-slate-200/80 flex flex-col z-50 animate-slide-up overflow-hidden">
          <div className="flex-shrink-0 bg-slate-850 text-white px-4 py-3 flex items-center justify-between">
            <h3 className="font-semibold text-sm flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-white/15 flex items-center justify-center">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
              </span>
              AI Assistant
            </h3>
            <button onClick={onToggle} className="text-slate-300 hover:text-white p-1.5 rounded-lg hover:bg-white/10 transition-colors">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-auto p-4 space-y-3 bg-slate-50/50">
            {messages.length === 0 ? (
              <div className="text-center text-slate-400 py-12">
                <div className="w-12 h-12 rounded-xl bg-slate-200/60 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <p className="text-sm">Start a conversation…</p>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm ${
                    msg.role === 'user'
                      ? 'bg-slate-850 text-white rounded-br-md'
                      : 'bg-white text-slate-700 border border-slate-200/80 rounded-bl-md shadow-sm'
                  }`}>
                    <p className="whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="flex-shrink-0 p-4 border-t border-slate-200 bg-white">
            <textarea
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              placeholder="Type a message… (Enter to send)"
              className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 resize-none transition-shadow outline-none"
            />
            <div className="mt-2 flex justify-end">
              <button
                onClick={onSend}
                disabled={!input.trim()}
                className="px-4 py-2 text-sm font-medium bg-slate-850 text-white rounded-xl hover:bg-slate-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
                Send
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   HOME PAGE
   ═══════════════════════════════════════════════════════════════════════════ */

const HomePage = ({ onNavigate }) => {
  const features = [
    {
      id: 'cfc',
      title: 'CFC Wavelet Analysis',
      description: 'Cross-Frequency Coupling using Harmonic Wavelets for brain signal analysis',
      icon: (
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
      color: 'from-blue-500 to-cyan-500',
      stats: ['Time-Frequency Analysis', 'Wavelet Decomposition', 'Coupling Metrics'],
    },
    {
      id: 'hub',
      title: 'Hub Detection',
      description: 'Detect hub nodes in brain networks using Grassmann manifold optimization',
      icon: (
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
      color: 'from-purple-500 to-pink-500',
      stats: ['Network Topology', 'Hub Identification', 'Manifold Optimization'],
    },
    {
      id: 'chart',
      title: 'BrainChart',
      description: 'Lifespan normative growth curves for brain phenotypes and measurements',
      icon: (
        <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      color: 'from-emerald-500 to-teal-500',
      stats: ['Growth Curves', 'Centile Analysis', 'Age Normalization'],
    },
  ];

  return (
    <div className="flex-1 min-h-0 overflow-auto bg-slate-50">
      <div className="max-w-5xl mx-auto px-4 md:px-6 py-8 md:py-10">
        <div className="mb-10 animate-fade-in">
          <h1 className="text-2xl md:text-3xl font-bold text-slate-800 tracking-tight mb-2">
            Brain Network Analysis Suite
          </h1>
          <p className="text-slate-500 max-w-2xl">
            Advanced tools for brain signal analysis, network topology detection, and normative growth curve modeling.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
          {features.map((feature, idx) => (
            <button
              key={feature.id}
              type="button"
              onClick={() => onNavigate(feature.id)}
              className="group text-left bg-white rounded-2xl border border-slate-200 overflow-hidden transition-all duration-200 hover:shadow-lg hover:border-indigo-300 hover:-translate-y-0.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:ring-offset-2 animate-slide-up"
              style={{ animationDelay: `${idx * 80}ms` }}
            >
              <div className={`bg-gradient-to-br ${feature.color} p-5 text-white`}>
                <div className="flex justify-center mb-2 opacity-95">{feature.icon}</div>
                <h2 className="text-lg font-semibold text-center tracking-tight">{feature.title}</h2>
              </div>
              <div className="p-4">
                <p className="text-slate-500 text-sm leading-relaxed mb-3">{feature.description}</p>
                <ul className="space-y-1.5 mb-4">
                  {feature.stats.map((stat, i) => (
                    <li key={i} className="flex items-center text-xs text-slate-500">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mr-2" />
                      {stat}
                    </li>
                  ))}
                </ul>
                <span className={`inline-flex items-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-semibold bg-gradient-to-r ${feature.color} text-white`}>
                  Open
                  <svg className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </span>
              </div>
            </button>
          ))}
        </div>

        <p className="text-center text-slate-400 text-xs">Powered by advanced ML and signal processing</p>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   LOADING PAGE
   ═══════════════════════════════════════════════════════════════════════════ */

const LoadingPage = () => (
  <div className="fixed inset-0 bg-slate-850 flex items-center justify-center z-50">
    <div className="text-center">
      <div className="relative w-24 h-24 mx-auto mb-8 flex items-center justify-center">
        <div className="absolute inset-0 border-2 border-white/15 border-t-white rounded-full animate-spin" />
        <div className="w-16 h-16 rounded-xl bg-white/10 flex items-center justify-center">
          <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
      </div>
      <h2 className="text-2xl font-semibold text-white mb-2 tracking-tight">Loading Brain Tools</h2>
      <p className="text-white/60 text-sm">Initializing analysis modules…</p>
    </div>
  </div>
);

/* ═══════════════════════════════════════════════════════════════════════════
   ROI IMAGE PANEL
   ═══════════════════════════════════════════════════════════════════════════ */

const RoiImagePanel = ({ roiName }) => {
  const [roiId, setRoiId] = useState(null);

  useEffect(() => {
    if (!roiName) return;
    const cleanName = roiName.replace(/^Hub:\s*/, '');
    fetch(`/api/roi-id?name=${encodeURIComponent(cleanName)}`)
      .then(res => res.json())
      .then(data => setRoiId(data.roi_id))
      .catch(() => setRoiId(null));
  }, [roiName]);

  if (!roiName) {
    return (
      <div className="h-full flex flex-col items-center justify-center border border-dashed border-slate-300 rounded-xl bg-slate-50">
        <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-2">
          <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
        <p className="text-xs text-slate-500">Click a node to view ROI</p>
      </div>
    );
  }

  if (!roiId) {
    return (
      <div className="h-full flex items-center justify-center border border-red-200 rounded-xl bg-red-50">
        <p className="text-xs text-red-500">ROI image not found</p>
      </div>
    );
  }

  return (
    <div className="h-full border border-slate-200 rounded-xl overflow-hidden bg-white">
      <div className="px-3 py-2 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-indigo-400" />
        <span className="text-xs font-semibold text-slate-600 truncate">{roiName}</span>
      </div>
      <div className="p-2">
        <img src={`/api/roi_figs/mask${roiId}_roi.png`} alt={roiName} className="w-full h-auto object-contain" />
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   INLINE LLM CHAT PANEL
   ═══════════════════════════════════════════════════════════════════════════ */

const LlmChatPanel = ({ messages, input, onInputChange, onSend }) => {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); }
  };

  return (
    <div className="h-full flex flex-col bg-white rounded-xl border border-slate-200 overflow-hidden">
      <div className="flex-shrink-0 px-3.5 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
        <span className="w-6 h-6 rounded-lg bg-indigo-100 flex items-center justify-center">
          <svg className="w-3.5 h-3.5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
        </span>
        <h3 className="text-xs font-semibold text-slate-700">LLM Assistant</h3>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-2.5 bg-slate-50/30">
        {messages.length === 0 ? (
          <div className="text-center text-slate-400 mt-6">
            <p className="text-xs">No messages yet</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] px-2.5 py-1.5 rounded-xl text-xs leading-relaxed ${
                msg.role === 'user'
                  ? 'bg-indigo-600 text-white rounded-br-sm'
                  : 'bg-white text-slate-700 border border-slate-200 rounded-bl-sm shadow-sm'
              }`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="flex-shrink-0 p-2.5 border-t border-slate-100 bg-white">
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          placeholder="Ask about results…"
          className="w-full border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 resize-none outline-none"
        />
        <div className="mt-1.5 flex justify-end">
          <button
            onClick={onSend}
            disabled={!input.trim()}
            className="px-2.5 py-1 text-xs font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
            Send
          </button>
        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   BRAINCHART VIEW
   ═══════════════════════════════════════════════════════════════════════════ */

const BrainChartView = () => {
  const [phenotypes, setPhenotypes] = useState([]);
  const [phenotype, setPhenotype] = useState('');
  const [curveData, setCurveData] = useState(null);
  const [loadingCurve, setLoadingCurve] = useState(false);
  const [curveError, setCurveError] = useState(null);
  const [file, setFile] = useState(null);
  const [csvPreview, setCsvPreview] = useState(null);
  const [ageCol, setAgeCol] = useState('');
  const [valCol, setValCol] = useState('');
  const [overlay, setOverlay] = useState(null);
  const [overlayLoading, setOverlayLoading] = useState(false);
  const [error, setError] = useState(null);
  const [autoScale, setAutoScale] = useState(true);
  const [yMin, setYMin] = useState(0);
  const [yMax, setYMax] = useState(1);
  const [xMin, setXMin] = useState(-1);
  const [xMax, setXMax] = useState(80);
  const [yAxisDecimals, setYAxisDecimals] = useState(3);

  const xAxisDomain = useMemo(() => {
    const min = typeof xMin === 'number' && !isNaN(xMin) ? xMin : -1;
    const max = typeof xMax === 'number' && !isNaN(xMax) ? xMax : 80;
    return [min, max];
  }, [xMin, xMax]);

  useEffect(() => {
    fetch('/chart_api/phenotypes')
      .then((res) => { if (!res.ok) throw new Error('Failed to load phenotypes'); return res.json(); })
      .then((data) => {
        setPhenotypes(data.phenotypes);
        if (data.phenotypes.length > 0) setPhenotype(data.phenotypes[0]);
      })
      .catch((err) => { console.error(err); setError('Failed to load phenotypes: ' + err.message); });
  }, []);

  useEffect(() => {
    if (!phenotype) return;
    let alive = true;
    setLoadingCurve(true); setCurveError(null); setCurveData(null);
    fetch(`/chart_api/curve/${encodeURIComponent(phenotype)}`)
      .then((res) => { if (!res.ok) throw new Error('Failed to load curve'); return res.json(); })
      .then((data) => { if (!alive) return; setCurveData(data); setLoadingCurve(false); })
      .catch((err) => { if (!alive) return; console.error(err); setCurveError(err.message); setLoadingCurve(false); });
    return () => { alive = false; };
  }, [phenotype]);

  const chartData = useMemo(() => {
    if (!curveData) return [];
    const { X, centiles } = curveData;
    return X.map((x, i) => ({
      age: x, p5: centiles[i][0], p25: centiles[i][1],
      p50: centiles[i][2], p75: centiles[i][3], p95: centiles[i][4],
    }));
  }, [curveData]);

  const yAxisDomain = useMemo(() => {
    if (!autoScale) return [yMin, yMax];
    if (chartData.length === 0) return [0, 1];
    let min = Infinity, max = -Infinity;
    chartData.forEach(d => {
      [d.p5, d.p25, d.p50, d.p75, d.p95].forEach(val => {
        if (val < min) min = val;
        if (val > max) max = val;
      });
    });
    if (overlay) overlay.values.forEach(val => { if (val < min) min = val; if (val > max) max = val; });
    const margin = (max - min) * 0.1;
    return [min - margin, max + margin];
  }, [chartData, overlay, autoScale, yMin, yMax]);

  const handleFileChange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f); setOverlay(null); setError(null); setCsvPreview(null);
    const formData = new FormData();
    formData.append('file', f);
    try {
      const res = await fetch('/chart_api/parse-csv', { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to parse CSV');
      setCsvPreview(data);
      setAgeCol(data.columns[0] || '');
      setValCol(data.columns[1] || data.columns[0] || '');
    } catch (err) { console.error('Parse error:', err); setError('Failed to parse CSV: ' + err.message); }
  };

  const handleOverlay = async () => {
    if (!file || !ageCol || !valCol || !phenotype) { setError('Please select file and columns first'); return; }
    setOverlayLoading(true); setError(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const url = `/chart_api/overlay?age_col=${encodeURIComponent(ageCol)}&val_col=${encodeURIComponent(valCol)}&phenotype=${encodeURIComponent(phenotype)}`;
      const res = await fetch(url, { method: 'POST', body: formData });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Overlay failed');
      setOverlay(data);
    } catch (err) { console.error('Overlay error:', err); setError('Overlay failed: ' + err.message); }
    finally { setOverlayLoading(false); }
  };

  const agePresets = [
    { label: 'Full Range',          min: -1, max: 80, cls: 'text-slate-600 bg-slate-100 hover:bg-slate-200' },
    { label: 'Childhood (0–25)',    min: 0,  max: 25, cls: 'text-blue-700 bg-blue-50 hover:bg-blue-100' },
    { label: 'Adolescence (13–30)', min: 13, max: 30, cls: 'text-violet-700 bg-violet-50 hover:bg-violet-100' },
    { label: 'Aging (40–80)',       min: 40, max: 80, cls: 'text-amber-700 bg-amber-50 hover:bg-amber-100' },
  ];

  return (
    <div className="h-full overflow-auto p-5">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <div className="grid grid-cols-12 gap-5">
        {/* Left — Controls */}
        <div className="col-span-3 space-y-3">
          {/* Phenotype */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
              <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-700">Normative Curves</h3>
            </div>
            <div className="p-4">
              <label className="block text-xs font-medium text-slate-500 mb-1.5">Phenotype</label>
              <select value={phenotype} onChange={(e) => setPhenotype(e.target.value)}
                className="w-full border border-slate-200 px-3 py-2 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400/40 focus:border-indigo-400 bg-white">
                {phenotypes.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              {curveData && (
                <div className="mt-3 flex items-center gap-2 px-2.5 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg">
                  <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-xs text-emerald-700">Loaded: {curveData.keys.join(', ')}</span>
                </div>
              )}
            </div>
          </div>

          {/* Settings */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
              <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-700">Chart Settings</h3>
            </div>
            <div className="p-4 space-y-4">
              {/* Y Axis */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Y Axis</label>
                <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                  <input type="checkbox" checked={autoScale} onChange={(e) => setAutoScale(e.target.checked)}
                    className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-400" />
                  Auto-scale
                </label>
                {!autoScale && (
                  <div className="grid grid-cols-2 gap-2 mt-2 pl-6">
                    <div>
                      <label className="block text-xs text-slate-500 mb-0.5">Min</label>
                      <input type="number" step="0.1" value={yMin} onChange={(e) => setYMin(parseFloat(e.target.value))}
                        className="w-full px-2 py-1 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none" />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-0.5">Max</label>
                      <input type="number" step="0.1" value={yMax} onChange={(e) => setYMax(parseFloat(e.target.value))}
                        className="w-full px-2 py-1 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none" />
                    </div>
                  </div>
                )}
                <div className="mt-2 pl-6">
                  <label className="block text-xs text-slate-500 mb-0.5">Decimal places</label>
                  <select value={yAxisDecimals} onChange={(e) => setYAxisDecimals(parseInt(e.target.value))}
                    className="w-full px-2 py-1 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none bg-white">
                    {[0,1,2,3,4].map(n => <option key={n} value={n}>{n}</option>)}
                  </select>
                </div>
              </div>

              {/* X Axis */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">X Axis (Age)</label>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs text-slate-500 mb-0.5">Min (yr)</label>
                    <input type="number" step="1" value={xMin}
                      onChange={(e) => { const n = parseFloat(e.target.value); if (!isNaN(n)) setXMin(n); }}
                      className="w-full px-2 py-1 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none" />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-0.5">Max (yr)</label>
                    <input type="number" step="1" value={xMax}
                      onChange={(e) => { const n = parseFloat(e.target.value); if (!isNaN(n)) setXMax(n); }}
                      className="w-full px-2 py-1 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none" />
                  </div>
                </div>
              </div>

              {/* Age Presets */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Quick Ranges</label>
                <div className="flex flex-wrap gap-1.5">
                  {agePresets.map(p => (
                    <button key={p.label} type="button"
                      onClick={() => { setXMin(p.min); setXMax(p.max); setAutoScale(true); }}
                      className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors ${p.cls}`}>
                      {p.label}
                    </button>
                  ))}
                  {overlay && overlay.age.length > 0 && (
                    <button type="button"
                      onClick={() => {
                        const ages = overlay.age;
                        const minA = Math.min(...ages), maxA = Math.max(...ages);
                        const pad = Math.max(5, (maxA - minA) * 0.2);
                        setXMin(Math.floor(minA - pad)); setXMax(Math.ceil(maxA + pad)); setAutoScale(true);
                      }}
                      className="px-2.5 py-1 text-xs font-medium rounded-lg text-emerald-700 bg-emerald-50 hover:bg-emerald-100 transition-colors">
                      Focus on Data
                    </button>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Center — Chart */}
        <div className="col-span-6 bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-slate-100 bg-slate-50">
            <h2 className="text-sm font-semibold text-slate-700">Lifespan Normative Growth Curve</h2>
            <p className="text-xs text-slate-500 mt-0.5">{phenotype || '—'}</p>
          </div>
          <div className="p-4">
            {loadingCurve ? (
              <div className="h-96 flex items-center justify-center"><Spinner size="h-10 w-10" /></div>
            ) : curveError ? (
              <div className="h-96 flex items-center justify-center">
                <p className="text-sm text-red-500">Error: {curveError}</p>
              </div>
            ) : chartData.length === 0 ? (
              <div className="h-96 flex items-center justify-center">
                <p className="text-sm text-slate-400">No data available</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={400}>
                <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis dataKey="age"
                    label={{ value: 'Age (yr)', position: 'insideBottom', offset: -5, style: { fontSize: 12, fill: '#64748b' } }}
                    domain={xAxisDomain} type="number" tick={{ fontSize: 11, fill: '#64748b' }} />
                  <YAxis
                    label={{ value: phenotype, angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#64748b' } }}
                    domain={yAxisDomain} width={85} tick={{ fontSize: 11, fill: '#64748b' }}
                    tickFormatter={(value) => value.toFixed(yAxisDecimals)} />
                  <Tooltip contentStyle={{ borderRadius: '0.75rem', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)', fontSize: 12 }} />
                  <Legend iconType="dash" iconSize={18} wrapperStyle={{ fontSize: 12 }} />
                  <Line dataKey="p5"  stroke="#475569" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="5th" />
                  <Line dataKey="p25" stroke="#64748b" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="25th" />
                  <Line dataKey="p50" stroke="#0f172a" strokeWidth={2.5} dot={false} name="50th (Median)" />
                  <Line dataKey="p75" stroke="#64748b" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="75th" />
                  <Line dataKey="p95" stroke="#475569" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="95th" />
                  {overlay && (
                    <Scatter
                      data={overlay.age.map((a, i) => ({ age: a, value: overlay.values[i] }))}
                      dataKey="value" fill="#ef4444" name="Your data" />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        {/* Right — Upload */}
        <div className="col-span-3">
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden h-full">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
              <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-700">Overlay Your Data</h3>
            </div>
            <div className="p-4 space-y-4">
              {/* Drop zone */}
              <div>
                <label className="block text-xs font-medium text-slate-500 mb-2">Upload CSV / TSV</label>
                <label className="block border border-dashed border-slate-300 rounded-xl p-4 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/40 transition-colors">
                  <svg className="w-7 h-7 text-slate-400 mx-auto mb-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-xs text-slate-600 font-medium">{file ? file.name : 'Click to select file'}</p>
                  <p className="text-xs text-slate-400 mt-0.5">CSV, TSV supported</p>
                  <input type="file" accept=".csv,.tsv,.txt" onChange={handleFileChange} className="sr-only" />
                </label>
              </div>

              {csvPreview && (
                <>
                  <div className="flex items-center gap-2 px-2.5 py-1.5 bg-indigo-50 border border-indigo-200 rounded-lg">
                    <svg className="w-3.5 h-3.5 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    <span className="text-xs text-indigo-700">{csvPreview.rows} rows, {csvPreview.columns.length} columns</span>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">Age column (months)</label>
                      <select value={ageCol} onChange={(e) => setAgeCol(e.target.value)}
                        className="w-full border border-slate-200 px-2.5 py-1.5 rounded-lg text-sm focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none bg-white">
                        {csvPreview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-500 mb-1">Value column</label>
                      <select value={valCol} onChange={(e) => setValCol(e.target.value)}
                        className="w-full border border-slate-200 px-2.5 py-1.5 rounded-lg text-sm focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none bg-white">
                        {csvPreview.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                      </select>
                    </div>
                  </div>

                  {/* Preview table */}
                  <div>
                    <p className="text-xs font-medium text-slate-500 mb-1.5">Preview</p>
                    <div className="overflow-auto max-h-28 border border-slate-200 rounded-lg text-xs">
                      <table className="min-w-full">
                        <thead className="bg-slate-50 sticky top-0">
                          <tr>
                            {csvPreview.columns.map((col) => (
                              <th key={col} className="px-2.5 py-1.5 text-left font-semibold text-slate-600 border-b border-slate-200">{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {csvPreview.preview.map((row, i) => (
                            <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                              {csvPreview.columns.map((col) => (
                                <td key={col} className="px-2.5 py-1.5 text-slate-600">{row[col]}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <button onClick={handleOverlay} disabled={overlayLoading || !ageCol || !valCol}
                    className="w-full bg-indigo-600 text-white px-4 py-2.5 rounded-xl hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-sm font-semibold flex items-center justify-center gap-2">
                    {overlayLoading && <Spinner size="h-4 w-4" color="text-white" />}
                    {overlayLoading ? 'Computing…' : 'Overlay on Curve'}
                  </button>

                  {overlay && (
                    <div className="flex items-center gap-2 px-2.5 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg">
                      <svg className="w-3.5 h-3.5 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="text-xs text-emerald-700">Overlaid {overlay.age.length} data points</span>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   NETWORK ANALYSIS VIEW
   ═══════════════════════════════════════════════════════════════════════════ */

const NetworkAnalysisView = ({ mode }) => {
  const initialMethod = mode === 'hub' ? 'hub_detection' : 'cfc_wavelet';

  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskDetail, setTaskDetail] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState(0);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedMethod, setSelectedMethod] = useState(initialMethod);
  const [config, setConfig] = useState(ANALYSIS_METHODS[initialMethod].config);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [selectedNodeLabel, setSelectedNodeLabel] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [nodeColorMap, setNodeColorMap] = useState({});
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: 'Hi! I can help interpret the current network results.' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [hoveredNodeId, setHoveredNodeId] = useState(null);

  const [isProcessing, setIsProcessing] = useState(false);

  // const loadTasks = async () => {
  //   try {
  //     const res = await fetch('/api/tasks');
  //     const data = await res.json();
  //     setTasks(data.tasks || []);
  //   } catch (err) { console.error('Failed to load tasks:', err); }
  // };
  const loadTasks = async () => {
    try {
      const response = await fetch('http://localhost:8011/api/tasks');
      
      // 检查响应状态
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      // 检查响应是否有内容
      const text = await response.text();
      if (!text) {
        console.warn('Empty response from /api/tasks');
        setTasks([]);
        return;
      }
      
      // 解析 JSON
      const data = JSON.parse(text);
      setTasks(data);
    } catch (error) {
      console.error('Failed to load tasks:', error);
      // 设置默认空数组,避免应用崩溃
      setTasks([]);
    }
  };

  const loadTaskDetail = async (taskId) => {
    try {
      const res = await fetch(`/api/task/${taskId}`);
      const data = await res.json();
      setTaskDetail(data);
      setError(null);
      if (data.status === 'pending' || data.status === 'processing') setTimeout(() => loadTaskDetail(taskId), 2000);
    } catch (err) { console.error('Failed to load task detail:', err); setError('Failed to load task detail: ' + err.message); }
  };

  useEffect(() => { loadTasks(); const iv = setInterval(loadTasks, 5000); return () => clearInterval(iv); }, []);

  useEffect(() => {
    if (selectedTask) { setSelectedWindow(0); loadTaskDetail(selectedTask); }
    else setTaskDetail(null);
  }, [selectedTask]);

  useEffect(() => { setSelectedNodeLabel(null); setSelectedNodeId(null); }, [selectedWindow, selectedTask]);

  const handleSendChat = async () => {
    const content = chatInput.trim();
    if (!content) return;
    const nextMessages = [...chatMessages, { role: 'user', content }];
    setChatMessages(nextMessages);
    setChatInput('');
    try {
      const res = await fetch('http://localhost:8011/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: nextMessages, task_id: selectedTask, window_idx: selectedWindow }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'LLM request failed');
      if (data.action === 'set_node_color') {
        const { node_ids, color } = data.payload || {};
        if (Array.isArray(node_ids) && color) {
          setNodeColorMap(prev => { const next = { ...prev }; node_ids.forEach(id => { next[id] = color; }); return next; });
        }
      }
      const reply = data.response || data.message || (data.action === 'set_node_color' ? 'Color updated' : '');
      setChatMessages(prev => [...prev, { role: 'assistant', content: reply || '(No response)' }]);
    } catch (err) { setChatMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]); }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        setUploadedFiles([...uploadedFiles, { id: data.file_id, name: file.name }]);
        setSelectedFile(data.file_id);
        showToast('File uploaded successfully', 'success');
      } else showToast('Upload failed: ' + data.detail);
    } catch (err) { showToast('Upload error: ' + err.message); }
    finally { setUploading(false); }
  };

  const handleCancelTask = async (taskId) => {
    if (!confirm('Cancel this task?')) return;
    try {
      const res = await fetch(`/api/task/${taskId}/cancel`, { method: 'POST' });
      if (res.ok) { loadTasks(); if (selectedTask === taskId) loadTaskDetail(taskId); }
      else { const data = await res.json(); showToast('Cancel failed: ' + data.detail); }
    } catch (err) { showToast('Cancel error: ' + err.message); }
  };

  const handleDeleteTask = async (taskId) => {
    if (!confirm('Delete this task?')) return;
    try {
      const res = await fetch(`/api/task/${taskId}`, { method: 'DELETE' });
      if (res.ok) { if (selectedTask === taskId) { setSelectedTask(null); setTaskDetail(null); } loadTasks(); }
      else { const data = await res.json(); showToast('Delete failed: ' + data.detail); }
    } catch (err) { showToast('Delete error: ' + err.message); }
  };

  const handleRunAnalysis = async () => {
    if (!selectedFile) { showToast('Please select a file first', 'warning'); return; }
    setRunning(true);
    try {
      const res = await fetch('/api/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: selectedFile, method: selectedMethod, config }),
      });
      const data = await res.json();
      if (res.ok) { setSelectedTask(data.task_id); loadTasks(); }
      else showToast('Analysis failed: ' + data.detail);
    } catch (err) { showToast('Analysis error: ' + err.message); }
    finally { setRunning(false); }
  };

  const handleMethodChange = (method) => { setSelectedMethod(method); setConfig(ANALYSIS_METHODS[method].config); };

  const getCurrentWindow = (progress) => {
    if (!taskDetail?.result?.num_windows) return 0;
    if (progress < 0.6) return Math.max(0, Math.floor(((progress - 0.2) / 0.4) * taskDetail.result.num_windows));
    if (progress < 0.8) return Math.max(0, Math.floor(((progress - 0.6) / 0.2) * taskDetail.result.num_windows));
    return taskDetail.result.num_windows;
  };

  /* ── CFC Heatmap ── */
  const renderCFCHeatmap = (cfc, index) => {
    if (!cfc || !Array.isArray(cfc) || cfc.length === 0)
      return <div className="text-sm text-slate-500">No CFC data available</div>;

    const size = cfc.length;
    const cellSize = Math.min(340 / size, 20);
    let min = Infinity, max = -Infinity, validCount = 0;
    cfc.forEach(row => {
      if (Array.isArray(row)) row.forEach(val => {
        const n = Number(val);
        if (!isNaN(n) && isFinite(n)) { validCount++; if (n < min) min = n; if (n > max) max = n; }
      });
    });
    if (validCount === 0 || !isFinite(min) || !isFinite(max))
      return <div className="text-sm text-slate-500">Invalid CFC data (found {validCount} valid numbers)</div>;

    return (
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-600">CFC Matrix — Window {index + 1}</span>
          <span className="text-xs text-slate-400">{size}×{cfc[0]?.length || 0}</span>
        </div>
        <div className="flex justify-center">
          <div className="border border-slate-200 rounded-lg overflow-hidden shadow-sm">
            {cfc.map((row, i) => (
              <div key={i} className="flex">
                {Array.isArray(row) && row.map((val, j) => {
                  const numVal = Number(val);
                  const isValid = !isNaN(numVal) && isFinite(numVal);
                  const normalized = isValid && max > min ? (numVal - min) / (max - min) : 0;
                  return (
                    <div key={j}
                      style={{ width: cellSize, height: cellSize, backgroundColor: isValid ? getHeatColor(normalized) : '#cbd5e1' }}
                      title={`[${i},${j}]: ${isValid ? numVal.toFixed(4) : 'Invalid'}`}
                    />
                  );
                })}
              </div>
            ))}
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <span>Range: [{min.toFixed(4)}, {max.toFixed(4)}]</span>
          <div className="flex items-center gap-1.5">
            <span>Low</span>
            <div className="w-20 h-2.5 rounded-full border border-slate-200" style={{ background: 'linear-gradient(to right, #3b82f6, #ffffff, #ef4444)' }} />
            <span>High</span>
          </div>
        </div>
      </div>
    );
  };

  /* ── Network Graph ── */
  const renderNetwork = (graph, roiNames) => {
    if (!graph || !graph.nodes || !Array.isArray(graph.nodes)) {
      return (
        <div className="h-full flex items-center justify-center border border-dashed border-slate-300 rounded-xl bg-slate-50">
          <p className="text-sm text-slate-400">No graph data available</p>
        </div>
      );
    }
    const width = 450, height = 450, centerX = width / 2, centerY = height / 2, radius = 180;
    const hubNodes = graph.hub_nodes || [];
    const positions = graph.nodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / graph.nodes.length;
      return { id: node, x: centerX + radius * Math.cos(angle), y: centerY + radius * Math.sin(angle), isHub: hubNodes.includes(node) };
    });

    const getRoiLabel = (nodeId, isHub) => {
      const idx = Number(nodeId);
      const hasName = Array.isArray(roiNames) && Number.isInteger(idx) && roiNames[idx];
      if (hasName) return isHub ? `Hub: ${roiNames[idx]}` : roiNames[idx];
      return isHub ? `Hub Node ${nodeId}` : `Node ${nodeId}`;
    };

    return (
      <svg width={width} height={height} className="rounded-xl border border-slate-200 bg-slate-50">
        {graph.edges && Array.isArray(graph.edges) && graph.edges.map((edge, i) => {
          if (!Array.isArray(edge) || edge.length < 2) return null;
          const source = positions.find(p => p.id === edge[0]);
          const target = positions.find(p => p.id === edge[1]);
          if (!source || !target) return null;
          const isConnected = hoveredNodeId && (edge[0] === hoveredNodeId || edge[1] === hoveredNodeId);
          return (
            <line key={i} x1={source.x} y1={source.y} x2={target.x} y2={target.y}
              stroke={isConnected ? '#f59e0b' : '#cbd5e1'}
              strokeWidth={isConnected ? 2 : 0.8}
              opacity={isConnected ? 0.9 : (hoveredNodeId ? 0.12 : 0.3)}
              pointerEvents="none" />
          );
        })}
        {positions.map(pos => {
          const isSelected = selectedNodeId === pos.id;
          const isHovered = hoveredNodeId === pos.id;
          const fillColor = nodeColorMap[pos.id] ?? (pos.isHub ? '#ef4444' : '#6366f1');
          const baseR = pos.isHub ? 9 : 6;
          const r = isHovered ? baseR + 3 : baseR;
          return (
            <circle key={pos.id} cx={pos.x} cy={pos.y} r={r}
              fill={fillColor}
              stroke={isSelected ? '#f59e0b' : (pos.isHub ? '#dc2626' : '#4f46e5')}
              strokeWidth={isSelected ? 3 : (pos.isHub ? 2 : 1.2)}
              onMouseEnter={() => setHoveredNodeId(pos.id)}
              onMouseLeave={() => setHoveredNodeId(null)}
              onClick={() => { setSelectedNodeLabel(getRoiLabel(pos.id, pos.isHub)); setSelectedNodeId(pos.id); }}
              className="cursor-pointer transition-all duration-150" />
          );
        })}
        {positions.map(pos => {
          if (hoveredNodeId !== pos.id) return null;
          return (
            <text key={`label-${pos.id}`} x={pos.x + 13} y={pos.y - 13}
              className="text-xs fill-slate-700 font-semibold" pointerEvents="none"
              style={{ textShadow: '0 0 4px white' }}>
              {getRoiLabel(pos.id, pos.isHub)}
            </text>
          );
        })}
      </svg>
    );
  };

  /* ── Config Inputs ── */
  const renderConfigInputs = () => {
    const method = ANALYSIS_METHODS[selectedMethod];
    return (
      <div className="space-y-3 text-sm">
        {Object.keys(method.config).map(key => (
          <div key={key}>
            <label className="block text-xs font-medium text-slate-500 mb-1 capitalize">{key.replace(/_/g, ' ')}</label>
            {typeof method.config[key] === 'boolean' ? (
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={config[key]}
                  onChange={(e) => setConfig({ ...config, [key]: e.target.checked })}
                  className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-400" />
                <span className="text-xs text-slate-600">{config[key] ? 'Enabled' : 'Disabled'}</span>
              </label>
            ) : (
              <input type="number"
                step={key.includes('ratio') || key.includes('min_err') || key.includes('beta') || key.includes('gamma') ? '0.01' : '1'}
                value={config[key]}
                onChange={(e) => {
                  const value = key.includes('ratio') || key.includes('min_err') || key.includes('beta') || key.includes('gamma')
                    ? parseFloat(e.target.value) : parseInt(e.target.value);
                  setConfig({ ...config, [key]: value || method.config[key] });
                }}
                className="w-full px-2.5 py-1 text-sm border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none" />
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="h-full overflow-auto p-5">
      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <div className="grid grid-cols-12 gap-5 h-full">
        {/* Left — Controls */}
        <div className="col-span-3 space-y-3 overflow-y-auto">
          {/* Upload */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
              <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-700">Upload Data</h3>
            </div>
            <div className="p-4">
              <label className="block border border-dashed border-slate-300 rounded-xl p-3 text-center cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/40 transition-colors">
                <svg className="w-6 h-6 text-slate-400 mx-auto mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-xs text-slate-500">Drop .csv / .tsv here</p>
                <input type="file" accept=".pkl,.pickle,csv,tsv" onChange={handleFileUpload} disabled={uploading} className="sr-only" />
              </label>
              {uploading && (
                <div className="flex items-center gap-2 mt-3 text-sm text-indigo-600">
                  <Spinner size="h-4 w-4" color="text-indigo-600" />
                  <span>Uploading…</span>
                </div>
              )}
              {uploadedFiles.length > 0 && (
                <div className="mt-3">
                  <label className="block text-xs font-medium text-slate-500 mb-1">Uploaded Files</label>
                  <select value={selectedFile || ''} onChange={(e) => setSelectedFile(e.target.value)}
                    className="w-full px-2.5 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-400/30 focus:border-indigo-400 outline-none bg-white">
                    <option value="">Select a file…</option>
                    {uploadedFiles.map(file => <option key={file.id} value={file.id}>{file.name}</option>)}
                  </select>
                </div>
              )}
            </div>
          </div>

          {/* Method + Config */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
              <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-700">Configuration</h3>
            </div>
            <div className="p-4">
              {/* Method Tabs */}
              <div className="flex gap-1 mb-3 p-0.5 bg-slate-100 rounded-lg">
                {Object.entries(ANALYSIS_METHODS).map(([key]) => (
                  <button key={key} type="button" onClick={() => handleMethodChange(key)}
                    className={`flex-1 px-2 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                      selectedMethod === key ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-500 hover:text-slate-700'
                    }`}>
                    {key === 'cfc_wavelet' ? 'CFC Wavelet' : 'Hub Detection'}
                  </button>
                ))}
              </div>
              <div className="max-h-72 overflow-y-auto">{renderConfigInputs()}</div>
              <button onClick={handleRunAnalysis} disabled={!selectedFile || running}
                className={`w-full mt-4 py-2.5 px-4 rounded-xl font-semibold text-sm flex items-center justify-center gap-2 transition-all ${
                  !selectedFile || running
                    ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                    : 'bg-gradient-to-r from-emerald-500 to-emerald-600 text-white hover:from-emerald-600 hover:to-emerald-700 shadow-sm'
                }`}>
                {running ? <><Spinner size="h-4 w-4" color="text-white" /> Running…</> : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Run Analysis
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Tasks */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-2.5 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
              <svg className="w-4 h-4 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-700">Tasks</h3>
            </div>
            <div className="p-3 space-y-2 max-h-72 overflow-y-auto">
              {tasks.length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-4">No tasks yet</p>
              ) : tasks.map(task => (
                <div key={task.task_id}
                  className={`border rounded-lg overflow-hidden transition-all ${
                    selectedTask === task.task_id
                      ? 'border-indigo-400 bg-indigo-50 shadow-sm'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}>
                  <button onClick={() => setSelectedTask(task.task_id)} className="w-full text-left px-3 py-2.5">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-xs text-slate-700 truncate flex-1 mr-2">{task.filename || task.task_id}</span>
                      <StatusBadge status={task.status} />
                    </div>
                    <div className="flex items-center gap-2 mt-1.5">
                      {task.method && <span className="text-xs bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded-md font-medium">{task.method}</span>}
                      <span className="text-xs text-slate-400">({(task.progress * 100).toFixed(0)}%)</span>
                    </div>
                  </button>
                  <div className="px-3 pb-2.5 flex gap-1.5">
                    {(task.status === 'pending' || task.status === 'processing') && (
                      <button onClick={(e) => { e.stopPropagation(); handleCancelTask(task.task_id); }}
                        className="flex-1 px-2 py-1 text-xs font-semibold bg-amber-100 text-amber-700 rounded-lg hover:bg-amber-200 transition-colors">
                        Cancel
                      </button>
                    )}
                    {(task.status === 'completed' || task.status === 'error' || task.status === 'cancelled') && (
                      <button onClick={(e) => { e.stopPropagation(); handleDeleteTask(task.task_id); }}
                        className="flex-1 px-2 py-1 text-xs font-semibold bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors">
                        Delete
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Center — Visualization */}
        <div className="col-span-6 space-y-3">
          {!taskDetail ? (
            <div className="h-full flex items-center justify-center bg-white border border-dashed border-slate-300 rounded-xl">
              <div className="text-center text-slate-400">
                <div className="w-16 h-16 rounded-xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-8 h-8 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <p className="text-sm font-medium">Select a task to view results</p>
              </div>
            </div>
          ) : (taskDetail.status === 'pending' || taskDetail.status === 'processing') ? (
            <div className="h-full flex items-center justify-center bg-white border border-slate-200 rounded-xl">
              <div className="text-center py-12 px-6 w-full max-w-md mx-auto">
                <div className="flex justify-center"><Spinner size="h-12 w-12" /></div>
                <div className="text-base font-semibold text-slate-700 mt-5 mb-5">Processing Analysis…</div>
                <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
                  <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-3 rounded-full transition-all duration-300"
                    style={{ width: `${taskDetail.progress * 100}%` }} />
                </div>
                <div className="flex justify-between mt-1.5 text-xs text-slate-500">
                  <span>Progress</span>
                  <span className="font-semibold">{(taskDetail.progress * 100).toFixed(1)}%</span>
                </div>
                {taskDetail.result?.num_windows && (
                  <div className="text-xs text-slate-400 mt-3">Window {getCurrentWindow(taskDetail.progress)} / {taskDetail.result.num_windows}</div>
                )}
              </div>
            </div>
          ) : taskDetail.status === 'cancelled' ? (
            <div className="h-full flex items-center justify-center bg-white border border-slate-200 rounded-xl">
              <div className="text-center">
                <div className="w-16 h-16 rounded-xl bg-amber-50 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-8 h-8 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div className="text-sm font-semibold text-amber-700">Task Cancelled</div>
                <div className="text-xs text-slate-400 mt-1">This task was cancelled by the user</div>
              </div>
            </div>
          ) : taskDetail.status === 'error' ? (
            <div className="h-full flex items-center justify-center bg-white border border-slate-200 rounded-xl">
              <div className="text-center max-w-sm mx-auto px-6">
                <div className="w-16 h-16 rounded-xl bg-red-50 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div className="text-sm font-semibold text-red-700">Analysis Error</div>
                <div className="text-xs text-slate-500 mt-1">{taskDetail.error}</div>
              </div>
            </div>
          ) : taskDetail.result ? (
            <div className="space-y-3">
              {/* Info Banner */}
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="grid grid-cols-4 gap-3">
                  {[
                    { label: 'Method',  value: taskDetail.method || 'N/A' },
                    { label: 'Label',   value: taskDetail.result.labels?.[0] || 'N/A' },
                    { label: 'Windows', value: taskDetail.result.num_windows || 0 },
                    { label: 'Nodes',   value: taskDetail.result.graphs?.[0]?.num_nodes || 0 },
                  ].map(item => (
                    <div key={item.label} className="bg-slate-50 rounded-lg p-2.5">
                      <div className="text-xs text-slate-500">{item.label}</div>
                      <div className="text-sm font-semibold text-indigo-700 mt-0.5">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Window Slider */}
              {taskDetail.result.num_windows > 0 && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-semibold text-slate-600">Time Window</label>
                    <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                      {selectedWindow + 1} / {taskDetail.result.num_windows}
                    </span>
                  </div>
                  <input type="range" min="0" max={taskDetail.result.num_windows - 1} value={selectedWindow}
                    onChange={(e) => setSelectedWindow(parseInt(e.target.value))}
                    className="w-full h-2 bg-slate-200 rounded-full appearance-none cursor-pointer accent-indigo-600" />
                </div>
              )}

              {/* Network Graph */}
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                    </svg>
                    <h3 className="text-sm font-semibold text-slate-700">Network Graph</h3>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span><strong className="text-slate-700">{taskDetail.result.graphs?.[selectedWindow]?.num_nodes || 0}</strong> nodes</span>
                    <span><strong className="text-slate-700">{taskDetail.result.graphs?.[selectedWindow]?.num_edges || 0}</strong> edges</span>
                  </div>
                </div>
                <div className="flex justify-center">
                  {taskDetail.result.graphs?.[selectedWindow]
                    ? renderNetwork(taskDetail.result.graphs[selectedWindow], taskDetail.result.roi_names)
                    : <div className="text-sm text-slate-500">No graph data for this window</div>
                  }
                </div>
                {taskDetail.result.graphs?.[selectedWindow] && (
                  <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                    {selectedNodeLabel ? (
                      <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-indigo-500" />
                        Selected: {selectedNodeLabel}
                      </span>
                    ) : <span className="text-xs text-slate-400">Hover or click a node</span>}
                    {taskDetail.result.graphs[selectedWindow]?.hub_nodes?.length > 0 && (
                      <span className="text-xs text-red-600 font-semibold">
                        Hubs: {taskDetail.result.graphs[selectedWindow].hub_nodes.map((nodeId) => {
                          const idx = Number(nodeId);
                          const rn = taskDetail.result.roi_names;
                          return (Array.isArray(rn) && Number.isInteger(idx) && rn[idx]) ? rn[idx] : `${nodeId}`;
                        }).join(', ')}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Results */}
              <div className="bg-white border border-slate-200 rounded-xl p-4">
                {taskDetail.method === 'hub_detection' ? (
                  <>
                    <div className="flex items-center gap-2 mb-3">
                      <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      <h3 className="text-sm font-semibold text-slate-700">Hub Detection Results</h3>
                    </div>
                    {taskDetail.result.hub_results && (
                      <div className="bg-slate-50 rounded-lg border border-slate-200 p-4">
                        <div className="grid grid-cols-3 gap-3 mb-4">
                          {[
                            { label: 'Method',        value: taskDetail.result.hub_results.method },
                            { label: 'Embedding (k)', value: taskDetail.result.method_specific?.hub_detection?.k || 2 },
                            { label: 'Hub Count',     value: taskDetail.result.method_specific?.hub_detection?.hub_num || 1 },
                          ].map(item => (
                            <div key={item.label} className="bg-white rounded-lg p-2.5 shadow-sm">
                              <div className="text-xs text-slate-500">{item.label}</div>
                              <div className="text-sm font-semibold text-slate-700">{item.value}</div>
                            </div>
                          ))}
                        </div>
                        {taskDetail.result.hub_results.method === 'group' ? (
                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="text-xs font-semibold text-red-700 mb-1">Group Common Hubs</div>
                            <div className="font-mono text-xs text-red-900">{taskDetail.result.hub_results.hub_nodes.join(', ')}</div>
                          </div>
                        ) : (
                          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
                            <div className="text-xs font-semibold text-indigo-700 mb-1">Individual Hub — Window {selectedWindow + 1}</div>
                            <div className="font-mono text-xs text-indigo-900">
                              {taskDetail.result.hub_results.results?.[selectedWindow]?.hub_nodes.join(', ') || 'N/A'}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2 mb-3">
                      <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                      </svg>
                      <h3 className="text-sm font-semibold text-slate-700">CFC Matrix</h3>
                    </div>
                    {taskDetail.result.cfcs?.[selectedWindow]
                      ? renderCFCHeatmap(taskDetail.result.cfcs[selectedWindow], selectedWindow)
                      : <div className="text-sm text-slate-500 text-center py-8">No CFC data for this window</div>
                    }
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center bg-white border border-slate-200 rounded-xl">
              <p className="text-sm text-slate-400">No results available</p>
            </div>
          )}
        </div>

        {/* Right — ROI + Chat */}
        <div className="col-span-3 space-y-3">
          <div className="h-[44%]">
            <RoiImagePanel roiName={selectedNodeLabel} />
          </div>
          <div className="h-[54%]">
            <LlmChatPanel messages={chatMessages} input={chatInput} onInputChange={setChatInput} onSend={handleSendChat} />
          </div>
        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN APP
   ═══════════════════════════════════════════════════════════════════════════ */

export default function UnifiedBrainApp() {
  const [activeView, setActiveView] = useState('home');
  const [isLoading, setIsLoading] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: 'assistant', content: 'Hi! I can help interpret your analysis results.' }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [selectedTask, setSelectedTask] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState(0);

  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => { setTimeout(() => setIsLoading(false), 1500); }, []);

  const handleSendChat = async () => {
    const content = chatInput.trim();
    if (!content || isProcessing) return;

    const nextMessages = [...chatMessages, { role: 'user', content }];
    setChatMessages(nextMessages);
    setChatInput('');      
    setIsProcessing(true); 

    try {
      console.log("Connecting to backend: /api/planner/chat ...");

      const res = await fetch('http://localhost:8011/api/planner/chat', {
        method: 'POST', 
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          query: content,
          context: { 
            current_view: activeView, 
            task_id: selectedTask     
          }
        }),
      });

      if (!res.ok) {
        const errorText = await res.text().catch(() => 'Unknown Server Error');
        throw new Error(`Server responded with ${res.status}: ${errorText}`);
      }

      const data = await res.json();
      
      const reply = data.response || data.message || JSON.stringify(data);

      setChatMessages(prev => [...prev, { role: 'agent', content: reply }]);

    } catch (err) { 
      console.error(err);
      setChatMessages(prev => [...prev, { 
        role: 'agent', 
        content: `⚠️ Error: Connection Error: ${err.message}. Could not connect to Planner Agent. Please check if Port 8011 is running.` 
      }]); 
    } finally {
      setIsProcessing(false);
    }
  };

  const getViewTitle = () => {
    switch (activeView) {
      case 'cfc':   return { title: 'CFC Wavelet Analysis',  subtitle: 'Cross-Frequency Coupling using Harmonic Wavelets' };
      case 'hub':   return { title: 'Hub Detection Analysis', subtitle: 'Detect hub nodes using Grassmann manifold optimization' };
      case 'chart': return { title: 'BrainChart Analysis',    subtitle: 'Lifespan normative growth curves for brain phenotypes' };
      default:      return { title: '', subtitle: '' };
    }
  };

  if (isLoading) return <LoadingPage />;

  const { title, subtitle } = getViewTitle();
  const navItems = [
    { id: 'home',  label: 'Home',       icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    { id: 'cfc',   label: 'CFC',        icon: 'M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z' },
    { id: 'hub',   label: 'Hub',        icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
    { id: 'chart', label: 'BrainChart', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-slate-100">
      <ToastContainer />

      {/* Header */}
      <header className="flex-shrink-0 h-14 px-4 md:px-6 flex items-center justify-between bg-white border-b border-slate-200 shadow-sm sticky top-0 z-40">
        <button onClick={() => setActiveView('home')} className="flex items-center gap-2.5 text-slate-800 hover:text-indigo-600 transition-colors">
          <span className="w-9 h-9 rounded-lg bg-slate-850 flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </span>
          <span className="font-semibold text-base tracking-tight hidden sm:inline">Brain Suite</span>
        </button>

        <nav className="flex items-center gap-0.5">
          {navItems.map((item) => (
            <button key={item.id} onClick={() => setActiveView(item.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeView === item.id ? 'bg-indigo-500 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}>
              <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
              </svg>
              <span className="hidden md:inline">{item.label}</span>
            </button>
          ))}
        </nav>

        <button onClick={() => setChatOpen(!chatOpen)}
          className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
            chatOpen ? 'bg-slate-700 text-white' : 'bg-slate-850 text-white hover:bg-slate-800'
          }`} title="AI Assistant">
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span className="hidden sm:inline">AI</span>
        </button>
      </header>

      {/* Main */}
      <main className="flex-1 flex flex-col min-h-0">
        {activeView === 'home' ? (
          <HomePage onNavigate={setActiveView} />
        ) : (
          <>
            <div className="flex-shrink-0 px-4 md:px-6 py-2.5 bg-white/80 backdrop-blur-sm border-b border-slate-200/60">
              <h1 className="text-sm font-semibold text-slate-800">{title}</h1>
              <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
            </div>
            <div className="flex-1 min-h-0 overflow-auto bg-slate-50">
              {(activeView === 'cfc' || activeView === 'hub') && <NetworkAnalysisView mode={activeView} />}
              {activeView === 'chart' && <BrainChartView />}
            </div>
          </>
        )}
      </main>

      <FloatingLLMChat
        isOpen={chatOpen}
        onToggle={() => setChatOpen(!chatOpen)}
        messages={chatMessages}
        input={chatInput}
        onInputChange={setChatInput}
        onSend={handleSendChat}
        isProcessing={isProcessing}
      />

      <style>{`
        @keyframes slide-up { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes fade-in  { from { opacity: 0; } to { opacity: 1; } }
        .animate-slide-up { animation: slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards; }
        .animate-fade-in  { animation: fade-in 0.45s ease-out forwards; }
      `}</style>
    </div>
  );
}
