import React, { useState, useEffect, useMemo } from 'react';
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
    }
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
    }
  },
};

// Floating LLM Chat Component
const FloatingLLMChat = ({ isOpen, onToggle, messages, input, onInputChange, onSend }) => {
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <>
      {/* Toggle Button */}
      <button
        onClick={onToggle}
        className={`fixed bottom-6 right-6 w-14 h-14 rounded-2xl shadow-panel flex items-center justify-center transition-all duration-200 z-50 ${
          isOpen 
            ? 'bg-slate-600 hover:bg-slate-700 text-white' 
            : 'bg-slate-850 text-white hover:shadow-glow'
        }`}
        title={isOpen ? "Close Chat" : "Open AI Assistant"}
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

      {/* Chat Panel */}
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
                <p className="text-sm">Start a conversation...</p>
              </div>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm ${
                      msg.role === "user"
                        ? "bg-slate-850 text-white rounded-br-md"
                        : "bg-white text-slate-700 border border-slate-200/80 rounded-bl-md shadow-sm"
                    }`}
                  >
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
              placeholder="Type a message... (Enter to send)"
              className="w-full border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 resize-none transition-shadow"
            />
            <div className="mt-2 flex justify-end">
              <button
                onClick={onSend}
                disabled={!input.trim()}
                className="px-4 py-2 text-sm font-medium bg-slate-850 text-white rounded-xl hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
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

// Home Page Component
const HomePage = ({ onNavigate }) => {
  const features = [
    {
      id: 'cfc',
      title: 'CFC Wavelet Analysis',
      description: 'Cross-Frequency Coupling using Harmonic Wavelets for brain signal analysis',
      icon: (
        <svg className="w-16 h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
      color: 'from-blue-500 to-cyan-500',
      stats: ['Time-Frequency Analysis', 'Wavelet Decomposition', 'Coupling Metrics']
    },
    {
      id: 'hub',
      title: 'Hub Detection',
      description: 'Detect hub nodes in brain networks using Grassmann manifold optimization',
      icon: (
        <svg className="w-16 h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
        </svg>
      ),
      color: 'from-purple-500 to-pink-500',
      stats: ['Network Topology', 'Hub Identification', 'Manifold Optimization']
    },
    {
      id: 'chart',
      title: 'BrainChart',
      description: 'Lifespan normative growth curves for brain phenotypes and measurements',
      icon: (
        <svg className="w-16 h-16" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      color: 'from-green-500 to-teal-500',
      stats: ['Growth Curves', 'Centile Analysis', 'Age Normalization']
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50/30 to-slate-100 p-8 md:p-12">
      <div className="max-w-6xl mx-auto">
        {/* Hero */}
        <div className="text-center mb-14 animate-fade-in">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-2xl bg-slate-850 text-white shadow-panel mb-6">
            <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-slate-800 tracking-tight mb-3">
            Brain Network Analysis Suite
          </h1>
          <p className="text-lg text-slate-600 max-w-2xl mx-auto">
            Advanced tools for brain signal analysis, network topology detection, and normative growth curve modeling
          </p>
        </div>

        {/* Feature Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
          {features.map((feature, idx) => (
            <div
              key={feature.id}
              className="group bg-white rounded-2xl border border-slate-200/80 overflow-hidden transition-all duration-300 hover:shadow-panel hover:border-indigo-200 hover:-translate-y-0.5 cursor-pointer animate-slide-up"
              style={{ animationDelay: `${idx * 100}ms` }}
              onClick={() => onNavigate(feature.id)}
            >
              <div className={`bg-gradient-to-br ${feature.color} p-6 text-white`}>
                <div className="flex justify-center mb-3 opacity-95">
                  {React.cloneElement(feature.icon, { className: 'w-14 h-14' })}
                </div>
                <h2 className="text-xl font-semibold text-center tracking-tight">{feature.title}</h2>
              </div>
              <div className="p-5">
                <p className="text-slate-600 text-sm leading-relaxed mb-4">
                  {feature.description}
                </p>
                <ul className="space-y-2 mb-5">
                  {feature.stats.map((stat, i) => (
                    <li key={i} className="flex items-center text-sm text-slate-700">
                      <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 mr-2.5" />
                      {stat}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={(e) => { e.stopPropagation(); onNavigate(feature.id); }}
                  className={`w-full py-2.5 rounded-xl font-medium text-sm bg-gradient-to-r ${feature.color} text-white flex items-center justify-center gap-2 hover:opacity-95 transition-opacity`}
                >
                  Launch
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>

        <p className="text-center text-slate-500 text-sm">
          Powered by advanced machine learning and signal processing
        </p>
      </div>
    </div>
  );
};

// Loading Page Component
const LoadingPage = () => {
  return (
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
        <p className="text-white/70 text-sm">Initializing analysis modules...</p>
      </div>
    </div>
  );
};

const RoiImagePanel = ({ roiName }) => {
  const [roiId, setRoiId] = useState(null);
  
  useEffect(() => {
    if (!roiName) return;
    const cleanName = roiName.replace(/^Hub:\s*/, "");
    fetch(`/api/roi-id?name=${encodeURIComponent(cleanName)}`)
      .then(res => res.json())
      .then(data => setRoiId(data.roi_id))
      .catch(() => setRoiId(null));
  }, [roiName]);

  if (!roiName) {
    return (
      <div className="h-full flex items-center justify-center border-2 border-dashed border-gray-300 rounded-lg">
        <div className="text-center text-gray-400">
          <svg className="mx-auto h-12 w-12 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          <p className="text-sm">Click a node to view ROI</p>
        </div>
      </div>
    );
  }

  if (!roiId) {
    return (
      <div className="h-full flex items-center justify-center border-2 border-red-200 rounded-lg bg-red-50">
        <p className="text-sm text-red-600">ROI image not found</p>
      </div>
    );
  }

  const imgSrc = `/api/roi_figs/mask${roiId}_roi.png`;

  return (
    <div className="h-full border-2 border-gray-300 rounded-lg p-3 bg-white">
      <div className="font-semibold text-sm mb-2 text-gray-700">{roiName}</div>
      <img
        src={imgSrc}
        alt={roiName}
        className="w-full h-auto object-contain"
      />
    </div>
  );
};

const LlmChatPanel = ({ messages, input, onInputChange, onSend }) => {
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <div className="h-full flex flex-col bg-white rounded-lg shadow-lg border border-gray-200">
      <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white px-4 py-3 rounded-t-lg">
        <h3 className="font-semibold flex items-center">
          <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          LLM Assistant
        </h3>
      </div>
      
      <div className="flex-1 overflow-auto p-4 space-y-3 bg-gray-50">
        {messages.length === 0 ? (
          <div className="text-center text-gray-400 mt-8">
            <p className="text-sm">No messages yet</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] px-4 py-2 rounded-lg ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white rounded-br-none"
                    : "bg-white border border-gray-200 text-gray-800 rounded-bl-none shadow-sm"
                }`}
              >
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              </div>
            </div>
          ))
        )}
      </div>
      
      <div className="p-4 border-t border-gray-200 bg-white rounded-b-lg">
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          placeholder="Type a message... (Enter to send, Shift+Enter for new line)"
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
        />
        <div className="mt-2 flex justify-end">
          <button
            onClick={onSend}
            disabled={!input.trim()}
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors flex items-center"
          >
            <svg className="w-4 h-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
            Send
          </button>
        </div>
      </div>
    </div>
  );
};

// BrainChart Component
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
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load phenotypes');
        return res.json();
      })
      .then((data) => {
        setPhenotypes(data.phenotypes);
        if (data.phenotypes.length > 0) {
          setPhenotype(data.phenotypes[0]);
        }
      })
      .catch((err) => {
        console.error(err);
        setError('Failed to load phenotypes: ' + err.message);
      });
  }, []);

  useEffect(() => {
    if (!phenotype) return;

    let alive = true;
    setLoadingCurve(true);
    setCurveError(null);
    setCurveData(null);

    fetch(`/chart_api/curve/${encodeURIComponent(phenotype)}`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load curve');
        return res.json();
      })
      .then((data) => {
        if (!alive) return;
        setCurveData(data);
        setLoadingCurve(false);
      })
      .catch((err) => {
        if (!alive) return;
        console.error(err);
        setCurveError(err.message);
        setLoadingCurve(false);
      });

    return () => {
      alive = false;
    };
  }, [phenotype]);

  const chartData = useMemo(() => {
    if (!curveData) return [];
    const { X, centiles } = curveData;
    return X.map((x, i) => ({
      age: x,
      p5: centiles[i][0],
      p25: centiles[i][1],
      p50: centiles[i][2],
      p75: centiles[i][3],
      p95: centiles[i][4],
    }));
  }, [curveData]);

  const yAxisDomain = useMemo(() => {
    if (!autoScale) {
      return [yMin, yMax];
    }
    
    if (chartData.length === 0) return [0, 1];
    
    let min = Infinity;
    let max = -Infinity;
    
    chartData.forEach(d => {
      [d.p5, d.p25, d.p50, d.p75, d.p95].forEach(val => {
        if (val < min) min = val;
        if (val > max) max = val;
      });
    });
    
    if (overlay) {
      overlay.values.forEach(val => {
        if (val < min) min = val;
        if (val > max) max = val;
      });
    }
    
    const margin = (max - min) * 0.1;
    return [min - margin, max + margin];
  }, [chartData, overlay, autoScale, yMin, yMax]);

  const handleFileChange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;

    setFile(f);
    setOverlay(null);
    setError(null);
    setCsvPreview(null);

    const formData = new FormData();
    formData.append('file', f);

    try {
      const res = await fetch(`/chart_api/parse-csv`, {
        method: 'POST',
        body: formData,
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to parse CSV');
      }
      
      setCsvPreview(data);
      setAgeCol(data.columns[0] || '');
      setValCol(data.columns[1] || data.columns[0] || '');
    } catch (err) {
      console.error('Parse error:', err);
      setError('Failed to parse CSV: ' + err.message);
    }
  };

  const handleOverlay = async () => {
    if (!file || !ageCol || !valCol || !phenotype) {
      setError('Please select file and columns first');
      return;
    }

    setOverlayLoading(true);
    setError(null);
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const url = `/chart_api/overlay?age_col=${encodeURIComponent(ageCol)}&val_col=${encodeURIComponent(valCol)}&phenotype=${encodeURIComponent(phenotype)}`;
      
      const res = await fetch(url, {
        method: 'POST',
        body: formData,
      });
      
      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.detail || 'Overlay failed');
      }
      
      setOverlay(data);
    } catch (err) {
      console.error('Overlay error:', err);
      setError('Overlay failed: ' + err.message);
    } finally {
      setOverlayLoading(false);
    }
  };

  return (
    <div className="h-full overflow-auto p-6">
      {error && (
        <div className="mb-4 p-4 bg-red-50 border-l-4 border-red-500 rounded text-red-700 flex items-start">
          <svg className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <div className="flex-1">
            <span>{error}</span>
            <button 
              onClick={() => setError(null)}
              className="ml-4 text-red-600 text-sm underline"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* Left Panel - Controls */}
        <div className="col-span-3 space-y-4">
          <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
            <h3 className="text-lg font-semibold mb-4 flex items-center text-gray-700">
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Normative Curves
            </h3>

            <label className="block text-sm font-medium text-gray-700 mb-2">Phenotype</label>
            <select
              value={phenotype}
              onChange={(e) => setPhenotype(e.target.value)}
              className="w-full border border-gray-300 px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {phenotypes.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>

            {curveData && (
              <div className="mt-3 p-2 bg-green-50 border border-green-200 rounded text-xs text-green-800">
                ✓ Loaded: {curveData.keys.join(', ')}
              </div>
            )}
          </div>

          {/* Chart Settings */}
          <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
            <h3 className="text-sm font-semibold mb-3 text-gray-700">Chart Settings</h3>
            
            {/* Y Axis */}
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-600 mb-2">Y Axis (Value)</h4>
              <div className="mb-2">
                <label className="flex items-center text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={autoScale}
                    onChange={(e) => setAutoScale(e.target.checked)}
                    className="mr-2"
                  />
                  Auto-scale
                </label>
              </div>

              {!autoScale && (
                <div className="space-y-2 pl-4">
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Min</label>
                    <input
                      type="number"
                      step="0.1"
                      value={yMin}
                      onChange={(e) => setYMin(parseFloat(e.target.value))}
                      className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-600 mb-1">Max</label>
                    <input
                      type="number"
                      step="0.1"
                      value={yMax}
                      onChange={(e) => setYMax(parseFloat(e.target.value))}
                      className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                    />
                  </div>
                </div>
              )}
              
              <div className="mt-2 pl-4">
                <label className="block text-xs text-gray-600 mb-1">Decimal places</label>
                <select
                  value={yAxisDecimals}
                  onChange={(e) => setYAxisDecimals(parseInt(e.target.value))}
                  className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                >
                  <option value="0">0</option>
                  <option value="1">1</option>
                  <option value="2">2</option>
                  <option value="3">3</option>
                  <option value="4">4</option>
                </select>
              </div>
            </div>

            {/* X Axis */}
            <div className="mb-4">
              <h4 className="text-xs font-medium text-gray-600 mb-2">X Axis (Age)</h4>
              <div className="space-y-2 pl-4">
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Min (years)</label>
                  <input
                    type="number"
                    step="1"
                    value={xMin}
                    onChange={(e) => {
                      const num = parseFloat(e.target.value);
                      if (!isNaN(num)) setXMin(num);
                    }}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600 mb-1">Max (years)</label>
                  <input
                    type="number"
                    step="1"
                    value={xMax}
                    onChange={(e) => {
                      const num = parseFloat(e.target.value);
                      if (!isNaN(num)) setXMax(num);
                    }}
                    className="w-full px-2 py-1 text-sm border border-gray-300 rounded"
                  />
                </div>
              </div>
            </div>

            {/* Quick Buttons */}
            <div className="space-y-2">
              <button
                onClick={() => {
                  setXMin(-1);
                  setXMax(80);
                  setAutoScale(true);
                }}
                className="w-full px-3 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 rounded transition-colors"
              >
                Reset to Default
              </button>
              
              {overlay && overlay.age.length > 0 && (
                <button
                  onClick={() => {
                    const ages = overlay.age;
                    const minAge = Math.min(...ages);
                    const maxAge = Math.max(...ages);
                    const range = maxAge - minAge;
                    const padding = Math.max(5, range * 0.2);
                    
                    setXMin(Math.floor(minAge - padding));
                    setXMax(Math.ceil(maxAge + padding));
                    setAutoScale(true);
                  }}
                  className="w-full px-3 py-1.5 text-xs bg-green-50 hover:bg-green-100 text-green-700 rounded transition-colors"
                >
                  📍 Focus on Your Data
                </button>
              )}
              
              <button
                onClick={() => {
                  setXMin(0);
                  setXMax(25);
                  setAutoScale(true);
                }}
                className="w-full px-3 py-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 rounded transition-colors"
              >
                Childhood (0-25yr)
              </button>
              <button
                onClick={() => {
                  setXMin(13);
                  setXMax(30);
                  setAutoScale(true);
                }}
                className="w-full px-3 py-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 rounded transition-colors"
              >
                Adolescence (13-30yr)
              </button>
              <button
                onClick={() => {
                  setXMin(40);
                  setXMax(80);
                  setAutoScale(true);
                }}
                className="w-full px-3 py-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 rounded transition-colors"
              >
                Aging (40-80yr)
              </button>
            </div>
          </div>
        </div>

        {/* Center - Chart */}
        <div className="col-span-6 bg-white rounded-lg shadow-md p-6 border border-gray-200">
          <h2 className="text-xl font-semibold mb-4 text-gray-800">
            Lifespan normative growth curve: {phenotype}
          </h2>

          {loadingCurve ? (
            <div className="h-96 flex items-center justify-center text-gray-500">
              <svg className="animate-spin h-12 w-12 text-indigo-600" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
          ) : curveError ? (
            <div className="h-96 flex items-center justify-center text-red-600">
              Error: {curveError}
            </div>
          ) : chartData.length === 0 ? (
            <div className="h-96 flex items-center justify-center text-gray-400">
              No data available
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart 
                data={chartData}
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="age"
                  label={{ value: 'Age (yr)', position: 'insideBottom', offset: -5 }}
                  domain={xAxisDomain}
                  type="number"
                  tick={{ fontSize: 12 }}
                />
                <YAxis 
                  label={{ value: phenotype, angle: -90, position: 'insideLeft' }}
                  domain={yAxisDomain}
                  width={85}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(value) => value.toFixed(yAxisDecimals)}
                />
                <Tooltip />
                <Legend />

                <Line dataKey="p5" stroke="#000" strokeWidth={2} strokeDasharray="5 5" dot={false} name="5th" />
                <Line dataKey="p25" stroke="#000" strokeWidth={2} strokeDasharray="5 5" dot={false} name="25th" />
                <Line dataKey="p50" stroke="#000" strokeWidth={3.5} dot={false} name="50th (Median)" />
                <Line dataKey="p75" stroke="#000" strokeWidth={2} strokeDasharray="5 5" dot={false} name="75th" />
                <Line dataKey="p95" stroke="#000" strokeWidth={2} strokeDasharray="5 5" dot={false} name="95th" />

                {overlay && (
                  <Scatter
                    data={overlay.age.map((a, i) => ({
                      age: a,
                      value: overlay.values[i],
                    }))}
                    dataKey="value"
                    fill="#ef4444"
                    name="Your data"
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Right - Data Upload */}
        <div className="col-span-3 bg-white rounded-lg shadow-md p-4 border border-gray-200">
          <h3 className="text-lg font-semibold mb-4 flex items-center text-gray-700">
            <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Overlay Your Data
          </h3>

          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Upload CSV/TSV
            </label>
            <input
              type="file"
              accept=".csv,.tsv,.txt"
              onChange={handleFileChange}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
            />
            <p className="text-xs text-gray-500 mt-1">
              CSV, TSV formats supported
            </p>
          </div>

          {csvPreview && (
            <>
              <div className="mb-3 p-2 bg-blue-50 border border-blue-200 rounded">
                <p className="text-xs text-blue-800">
                  ✓ {csvPreview.rows} rows, {csvPreview.columns.length} columns
                </p>
              </div>

              <div className="space-y-3 mb-3">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Age column (months)</label>
                  <select
                    value={ageCol}
                    onChange={(e) => setAgeCol(e.target.value)}
                    className="w-full border border-gray-300 px-2 py-1.5 rounded text-sm"
                  >
                    {csvPreview.columns.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">Value column</label>
                  <select
                    value={valCol}
                    onChange={(e) => setValCol(e.target.value)}
                    className="w-full border border-gray-300 px-2 py-1.5 rounded text-sm"
                  >
                    {csvPreview.columns.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="mb-3">
                <p className="text-xs font-medium text-gray-700 mb-1">Preview:</p>
                <div className="overflow-auto max-h-32 border border-gray-200 rounded text-xs">
                  <table className="min-w-full">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        {csvPreview.columns.map((col) => (
                          <th key={col} className="px-2 py-1 text-left font-medium text-gray-700 border-b">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {csvPreview.preview.map((row, i) => (
                        <tr key={i} className="border-b hover:bg-gray-50">
                          {csvPreview.columns.map((col) => (
                            <td key={col} className="px-2 py-1 text-gray-600">
                              {row[col]}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <button
                onClick={handleOverlay}
                disabled={overlayLoading || !ageCol || !valCol}
                className="w-full bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors text-sm font-medium"
              >
                {overlayLoading ? 'Computing…' : 'Overlay on Curve'}
              </button>
              
              {overlay && (
                <div className="mt-3 p-2 bg-green-50 border border-green-200 rounded">
                  <p className="text-xs text-green-800">
                    ✓ Overlayed {overlay.age.length} data points
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

// Network Analysis View
const NetworkAnalysisView = () => {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskDetail, setTaskDetail] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState(0);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedMethod, setSelectedMethod] = useState('cfc_wavelet');
  const [config, setConfig] = useState(ANALYSIS_METHODS.cfc_wavelet.config);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [selectedNodeLabel, setSelectedNodeLabel] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [nodeColorMap, setNodeColorMap] = useState({});
  const [chatMessages, setChatMessages] = useState([
    { role: "assistant", content: "Hi! I can help interpret the current network results." }
  ]);
  const [chatInput, setChatInput] = useState("");
  const [hoveredNodeId, setHoveredNodeId] = useState(null);

  const loadTasks = async () => {
    try {
      const res = await fetch(`/api/tasks`);
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    }
  };

  const loadTaskDetail = async (taskId) => {
    try {
      const res = await fetch(`/api/task/${taskId}`);
      const data = await res.json();
      setTaskDetail(data);
      setError(null);
      
      if (data.status === 'pending' || data.status === 'processing') {
        setTimeout(() => loadTaskDetail(taskId), 2000);
      }
    } catch (err) {
      console.error('Failed to load task detail:', err);
      setError('Failed to load task detail: ' + err.message);
    }
  };

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedTask) {
      setSelectedWindow(0);
      loadTaskDetail(selectedTask);
    } else {
      setTaskDetail(null);
    }
  }, [selectedTask]);

  useEffect(() => {
    setSelectedNodeLabel(null);
    setSelectedNodeId(null);
  }, [selectedWindow, selectedTask]);

  const handleSendChat = async () => {
    const content = chatInput.trim();
    if (!content) return;
    
    const nextMessages = [...chatMessages, { role: "user", content }];
    setChatMessages(nextMessages);
    setChatInput("");
    
    try {
      const res = await fetch(`/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          task_id: selectedTask,
          window_idx: selectedWindow,
        })
      });
      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.detail || "LLM request failed");
      }
      
      if (data.action === "set_node_color") {
        const { node_ids, color } = data.payload || {};
        if (Array.isArray(node_ids) && color) {
          setNodeColorMap(prev => {
            const next = { ...prev };
            node_ids.forEach(id => {
              next[id] = color;
            });
            return next;
          });
        }
      }
      
      const reply = data.response || data.message || (data.action === "set_node_color" ? "Color updated" : "");
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: reply || "(No response)" }
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err.message}` }
      ]);
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch(`/api/upload`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      
      if (res.ok) {
        setUploadedFiles([...uploadedFiles, { id: data.file_id, name: file.name }]);
        setSelectedFile(data.file_id);
        alert('File uploaded successfully!');
      } else {
        alert('Upload failed: ' + data.detail);
      }
    } catch (err) {
      alert('Upload error: ' + err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleCancelTask = async (taskId) => {
    if (!confirm('Are you sure you want to cancel this task?')) return;
    
    try {
      const res = await fetch(`/api/task/${taskId}/cancel`, {
        method: 'POST',
      });
      
      if (res.ok) {
        loadTasks();
        if (selectedTask === taskId) {
          loadTaskDetail(taskId);
        }
      } else {
        const data = await res.json();
        alert('Cancel failed: ' + data.detail);
      }
    } catch (err) {
      alert('Cancel error: ' + err.message);
    }
  };

  const handleDeleteTask = async (taskId) => {
    if (!confirm('Are you sure you want to delete this task?')) return;
    
    try {
      const res = await fetch(`/api/task/${taskId}`, {
        method: 'DELETE',
      });
      
      if (res.ok) {
        if (selectedTask === taskId) {
          setSelectedTask(null);
          setTaskDetail(null);
        }
        loadTasks();
      } else {
        const data = await res.json();
        alert('Delete failed: ' + data.detail);
      }
    } catch (err) {
      alert('Delete error: ' + err.message);
    }
  };

  const handleRunAnalysis = async () => {
    if (!selectedFile) {
      alert('Please select a file first');
      return;
    }

    setRunning(true);
    try {
      const res = await fetch(`/api/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          file_id: selectedFile,
          method: selectedMethod,
          config: config,
        }),
      });
      const data = await res.json();
      
      if (res.ok) {
        setSelectedTask(data.task_id);
        loadTasks();
      } else {
        alert('Analysis failed: ' + data.detail);
      }
    } catch (err) {
      alert('Analysis error: ' + err.message);
    } finally {
      setRunning(false);
    }
  };

  const handleMethodChange = (method) => {
    setSelectedMethod(method);
    setConfig(ANALYSIS_METHODS[method].config);
  };

  const getCurrentWindow = (progress) => {
    if (!taskDetail?.result?.num_windows) return 0;
    
    if (progress < 0.6) {
      const graphProgress = (progress - 0.2) / 0.4;
      return Math.max(0, Math.floor(graphProgress * taskDetail.result.num_windows));
    } else if (progress < 0.8) {
      const waveletProgress = (progress - 0.6) / 0.2;
      return Math.max(0, Math.floor(waveletProgress * taskDetail.result.num_windows));
    } else {
      return taskDetail.result.num_windows;
    }
  };

  const renderCFCHeatmap = (cfc, index) => {
    if (!cfc || !Array.isArray(cfc) || cfc.length === 0) {
      return <div className="text-sm text-gray-500">No CFC data available</div>;
    }
    
    const size = cfc.length;
    const cellSize = Math.min(350 / size, 20);
    
    let min = Infinity, max = -Infinity;
    let validCount = 0;
    cfc.forEach(row => {
      if (Array.isArray(row)) {
        row.forEach(val => {
          const numVal = Number(val);
          if (!isNaN(numVal) && isFinite(numVal)) {
            validCount++;
            if (numVal < min) min = numVal;
            if (numVal > max) max = numVal;
          }
        });
      }
    });
    
    if (validCount === 0 || !isFinite(min) || !isFinite(max)) {
      return (
        <div className="text-sm text-gray-500">
          Invalid CFC data (found {validCount} valid numbers)
        </div>
      );
    }
    
    return (
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <h4 className="text-sm font-semibold mb-3 text-gray-700">
          CFC Matrix - Window {index + 1} ({size}×{cfc[0]?.length || 0})
        </h4>
        <div className="inline-block border-2 border-gray-300 rounded">
          {cfc.map((row, i) => (
            <div key={i} className="flex">
              {Array.isArray(row) && row.map((val, j) => {
                const numVal = Number(val);
                const isValid = !isNaN(numVal) && isFinite(numVal);
                const normalized = isValid && max > min ? (numVal - min) / (max - min) : 0;
                const color = isValid 
                  ? `rgb(${Math.floor(255 * (1 - normalized))}, ${Math.floor(255 * (1 - normalized))}, 255)`
                  : '#cccccc';
                return (
                  <div
                    key={j}
                    style={{
                      width: cellSize,
                      height: cellSize,
                      backgroundColor: color,
                    }}
                    title={`[${i},${j}]: ${isValid ? numVal.toFixed(4) : 'Invalid'}`}
                  />
                );
              })}
            </div>
          ))}
        </div>
        <div className="text-xs text-gray-600 mt-2 flex items-center justify-between">
          <span>Range: [{min.toFixed(4)}, {max.toFixed(4)}]</span>
          <div className="flex items-center gap-2">
            <span>Low</span>
            <div className="w-20 h-3 bg-gradient-to-r from-white to-blue-600 border border-gray-300 rounded"></div>
            <span>High</span>
          </div>
        </div>
      </div>
    );
  };

  const renderNetwork = (graph, roiNames) => {
    if (!graph || !graph.nodes || !Array.isArray(graph.nodes)) {
      return (
        <div className="h-full flex items-center justify-center border-2 border-dashed border-gray-300 rounded-lg">
          <p className="text-sm text-gray-400">No graph data available</p>
        </div>
      );
    }
    
    const width = 450;
    const height = 450;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = 180;
    const hubNodes = graph.hub_nodes || [];
    
    const positions = graph.nodes.map((node, i) => {
      const angle = (2 * Math.PI * i) / graph.nodes.length;
      return {
        id: node,
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
        isHub: hubNodes.includes(node),
      };
    });

    const getRoiLabel = (nodeId, isHub) => {
      const idx = Number(nodeId);
      const hasName = Array.isArray(roiNames) && Number.isInteger(idx) && roiNames[idx];
      if (hasName) {
        return isHub ? `Hub: ${roiNames[idx]}` : roiNames[idx];
      }
      return isHub ? `Hub Node ${nodeId}` : `Node ${nodeId}`;
    };
    
    return (
      <svg width={width} height={height} className="border-2 border-gray-300 rounded-lg bg-white">
        {graph.edges && Array.isArray(graph.edges) && graph.edges.map((edge, i) => {
          if (!Array.isArray(edge) || edge.length < 2) return null;

          const source = positions.find(p => p.id === edge[0]);
          const target = positions.find(p => p.id === edge[1]);
          if (!source || !target) return null;

          const isConnected =
            hoveredNodeId &&
            (edge[0] === hoveredNodeId || edge[1] === hoveredNodeId);

          const opacity = isConnected ? 0.9 : 0.15;
          const stroke = isConnected ? "#f59e0b" : "#999";
          const strokeWidth = isConnected ? 2 : 1;

          return (
            <line
              key={i}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={stroke}
              strokeWidth={strokeWidth}
              opacity={opacity}
              pointerEvents="none"
            />
          );
        })}
        
        {positions.map(pos => {
          const isSelected = selectedNodeId === pos.id;
          const isHovered  = hoveredNodeId === pos.id;
          const fillColor = nodeColorMap[pos.id] ?? (pos.isHub ? "#ef4444" : "#4299e1");
          const baseR = pos.isHub ? 8 : 5;
          const r = isHovered ? baseR + 3 : baseR;

          return (
            <circle
              key={pos.id}
              cx={pos.x}
              cy={pos.y}
              r={r}
              fill={fillColor}
              stroke={isSelected ? "#f59e0b" : (pos.isHub ? "#dc2626" : "#2b6cb0")}
              strokeWidth={isSelected ? 3 : (pos.isHub ? 2 : 1)}
              onMouseEnter={() => setHoveredNodeId(pos.id)}
              onMouseLeave={() => setHoveredNodeId(null)}
              onClick={() => {
                setSelectedNodeLabel(getRoiLabel(pos.id, pos.isHub));
                setSelectedNodeId(pos.id);
              }}
              className="cursor-pointer transition-all duration-150"
            />
          );
        })}
        {positions.map(pos => {
          const isHovered = hoveredNodeId === pos.id;
          if (!isHovered) return null;

          return (
            <text
              key={`label-${pos.id}`}
              x={pos.x + 12}
              y={pos.y - 12}
              className="text-xs fill-gray-800 font-medium"
              pointerEvents="none"
            >
              {getRoiLabel(pos.id, pos.isHub)}
            </text>
          );
        })}
      </svg>
    );
  };

  const renderConfigInputs = () => {
    const method = ANALYSIS_METHODS[selectedMethod];
    
    return (
      <div className="space-y-3 text-sm">
        {Object.keys(method.config).map(key => (
          <div key={key}>
            <label className="block text-gray-700 font-medium mb-1 capitalize">
              {key.replace(/_/g, ' ')}
            </label>
            {typeof method.config[key] === 'boolean' ? (
              <label className="flex items-center cursor-pointer">
                <input
                  type="checkbox"
                  checked={config[key]}
                  onChange={(e) => setConfig({...config, [key]: e.target.checked})}
                  className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                />
                <span className="ml-2 text-sm">
                  {config[key] ? 'Enabled' : 'Disabled'}
                </span>
              </label>
            ) : (
              <input
                type="number"
                step={key.includes('ratio') || key.includes('min_err') || key.includes('beta') || key.includes('gamma') ? '0.01' : '1'}
                value={config[key]}
                onChange={(e) => {
                  const value = key.includes('ratio') || key.includes('min_err') || key.includes('beta') || key.includes('gamma')
                    ? parseFloat(e.target.value)
                    : parseInt(e.target.value);
                  setConfig({...config, [key]: value || method.config[key]});
                }}
                className="w-full px-2 py-1 border rounded focus:ring-2 focus:ring-blue-500"
              />
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="h-full overflow-auto p-6">
      {error && (
        <div className="mb-4 p-4 bg-red-50 border-l-4 border-red-500 rounded text-red-700 flex items-start">
          <svg className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
          </svg>
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-12 gap-6 h-full">
        {/* Control Panel - Left */}
        <div className="col-span-3 space-y-4 overflow-y-auto">
          {/* Upload Section */}
          <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
            <h2 className="text-lg font-semibold mb-3 flex items-center text-gray-700">
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              Upload Data
            </h2>
            
            <input
              type="file"
              accept=".pkl,.pickle"
              onChange={handleFileUpload}
              disabled={uploading}
              className="w-full text-sm mb-3 file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
            />
            
            {uploading && (
              <p className="text-sm text-blue-600 mb-3 flex items-center">
                <svg className="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Uploading...
              </p>
            )}
            
            {uploadedFiles.length > 0 && (
              <div className="mt-3">
                <label className="block text-sm font-medium mb-2 text-gray-700">Uploaded Files</label>
                <select
                  value={selectedFile || ''}
                  onChange={(e) => setSelectedFile(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                >
                  <option value="">Select a file...</option>
                  {uploadedFiles.map(file => (
                    <option key={file.id} value={file.id}>
                      {file.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          
          {/* Configuration Section */}
          <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
            <h2 className="text-lg font-semibold mb-3 flex items-center text-gray-700">
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
              </svg>
              Configuration
            </h2>
            <div className="max-h-96 overflow-y-auto">
              {renderConfigInputs()}
            </div>
            
            <button
              onClick={handleRunAnalysis}
              disabled={!selectedFile || running}
              className={`w-full mt-4 py-3 px-4 rounded-lg font-semibold flex items-center justify-center ${
                !selectedFile || running
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-gradient-to-r from-green-500 to-green-600 text-white hover:from-green-600 hover:to-green-700 shadow-md'
              }`}
            >
              {running ? (
                <>
                  <svg className="animate-spin h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Running...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Run Analysis
                </>
              )}
            </button>
          </div>
          
          {/* Tasks List */}
          <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
            <h2 className="text-lg font-semibold mb-3 flex items-center text-gray-700">
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              Tasks
            </h2>
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {tasks.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-4">No tasks yet</p>
              ) : (
                tasks.map(task => (
                  <div
                    key={task.task_id}
                    className={`border rounded-lg overflow-hidden transition-all ${
                      selectedTask === task.task_id
                        ? 'border-indigo-500 bg-indigo-50 shadow-md'
                        : 'border-gray-200 bg-white hover:border-gray-300'
                    }`}
                  >
                    <button
                      onClick={() => setSelectedTask(task.task_id)}
                      className="w-full text-left px-3 py-3"
                    >
                      <div className="font-medium truncate text-sm">{task.filename || task.task_id}</div>
                      <div className="text-xs text-gray-600 mt-1">
                        {task.method && <span className="font-semibold bg-gray-200 px-2 py-0.5 rounded">{task.method}</span>}
                        <span className="ml-2">{task.status}</span>
                        <span className="ml-2">({(task.progress * 100).toFixed(0)}%)</span>
                      </div>
                    </button>
                    
                    <div className="px-3 pb-2 flex gap-2">
                      {(task.status === 'pending' || task.status === 'processing') && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleCancelTask(task.task_id);
                          }}
                          className="flex-1 px-2 py-1.5 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600 font-medium"
                        >
                          Cancel
                        </button>
                      )}
                      {(task.status === 'completed' || task.status === 'error' || task.status === 'cancelled') && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteTask(task.task_id);
                          }}
                          className="flex-1 px-2 py-1.5 text-xs bg-red-500 text-white rounded hover:bg-red-600 font-medium"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
        
        {/* Visualization Area - Center */}
        <div className="col-span-6 space-y-4">
          {!taskDetail ? (
            <div className="h-full flex items-center justify-center bg-white rounded-lg shadow-md border-2 border-dashed border-gray-300">
              <div className="text-center text-gray-400">
                <svg className="mx-auto h-16 w-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
                <p className="text-lg font-medium">Select a task to view results</p>
              </div>
            </div>
          ) : taskDetail.status === 'pending' || taskDetail.status === 'processing' ? (
            <div className="h-full flex items-center justify-center bg-white rounded-lg shadow-md">
              <div className="text-center py-12 px-6">
                <svg className="animate-spin h-12 w-12 mx-auto mb-4 text-indigo-600" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                <div className="text-lg font-semibold mb-4 text-gray-700">Processing Analysis...</div>
                <div className="w-96 mx-auto bg-gray-200 rounded-full h-8 mb-3 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-indigo-500 to-purple-600 h-8 rounded-full transition-all duration-300 flex items-center justify-center text-white text-sm font-bold shadow-lg"
                    style={{ width: `${taskDetail.progress * 100}%` }}
                  >
                    {taskDetail.progress > 0.05 && `${(taskDetail.progress * 100).toFixed(1)}%`}
                  </div>
                </div>
                {taskDetail.result?.num_windows && (
                  <div className="text-sm text-gray-600 mt-4">
                    Processing window {getCurrentWindow(taskDetail.progress)} / {taskDetail.result.num_windows}
                  </div>
                )}
              </div>
            </div>
          ) : taskDetail.status === 'cancelled' ? (
            <div className="h-full flex items-center justify-center bg-white rounded-lg shadow-md">
              <div className="text-center text-orange-600">
                <svg className="mx-auto h-16 w-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="text-xl font-semibold mb-2">Task Cancelled</div>
                <div className="text-sm">This task was cancelled by the user</div>
              </div>
            </div>
          ) : taskDetail.status === 'error' ? (
            <div className="h-full flex items-center justify-center bg-white rounded-lg shadow-md">
              <div className="text-center text-red-600">
                <svg className="mx-auto h-16 w-16 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div className="text-xl font-semibold mb-2">Analysis Error</div>
                <div className="text-sm max-w-md">{taskDetail.error}</div>
              </div>
            </div>
          ) : taskDetail.result ? (
            <div className="space-y-4">
              {/* Info Banner */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border-l-4 border-indigo-500 p-4 rounded-lg shadow-sm">
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
                  <div><strong className="text-gray-700">Method:</strong> <span className="text-indigo-700 font-medium">{taskDetail.method || 'N/A'}</span></div>
                  <div><strong className="text-gray-700">Label:</strong> <span className="text-indigo-700 font-medium">{taskDetail.result.labels?.[0] || 'N/A'}</span></div>
                  <div><strong className="text-gray-700">Windows:</strong> <span className="text-indigo-700 font-medium">{taskDetail.result.num_windows || 0}</span></div>
                  <div><strong className="text-gray-700">Nodes:</strong> <span className="text-indigo-700 font-medium">{taskDetail.result.graphs?.[0]?.num_nodes || 0}</span></div>
                </div>
              </div>
              
              {/* Window Selector */}
              {taskDetail.result.num_windows > 0 && (
                <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
                  <label className="block text-sm font-semibold mb-3 text-gray-700">Select Time Window</label>
                  <input
                    type="range"
                    min="0"
                    max={taskDetail.result.num_windows - 1}
                    value={selectedWindow}
                    onChange={(e) => setSelectedWindow(parseInt(e.target.value))}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
                  />
                  <div className="flex justify-between text-sm text-gray-600 mt-2">
                    <span>Window {selectedWindow + 1}</span>
                    <span>of {taskDetail.result.num_windows}</span>
                  </div>
                </div>
              )}
              
              {/* Network Visualization */}
              <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
                <h3 className="text-lg font-semibold mb-3 flex items-center text-gray-700">
                  <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
                  </svg>
                  Network Graph
                </h3>
                <div className="flex justify-center">
                  {taskDetail.result.graphs?.[selectedWindow] ? (
                    renderNetwork(taskDetail.result.graphs[selectedWindow], taskDetail.result.roi_names)
                  ) : (
                    <div className="text-sm text-gray-500">No graph data for this window</div>
                  )}
                </div>
                {taskDetail.result.graphs?.[selectedWindow] && (
                  <div className="mt-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 space-y-1">
                    {selectedNodeLabel && (
                      <div className="text-gray-800 font-semibold text-sm">
                        Selected: {selectedNodeLabel}
                      </div>
                    )}
                    <div className="flex items-center justify-between">
                      <span>Nodes: <strong>{taskDetail.result.graphs[selectedWindow]?.num_nodes || 0}</strong></span>
                      <span>Edges: <strong>{taskDetail.result.graphs[selectedWindow]?.num_edges || 0}</strong></span>
                    </div>
                    {taskDetail.result.graphs[selectedWindow]?.hub_nodes && 
                      taskDetail.result.graphs[selectedWindow].hub_nodes.length > 0 && (
                      <div className="text-red-600 font-medium pt-2 border-t border-gray-200">
                        Hub Nodes: {taskDetail.result.graphs[selectedWindow].hub_nodes.map((nodeId) => {
                          const idx = Number(nodeId);
                          const roiNames = taskDetail.result.roi_names;
                          const name = Array.isArray(roiNames) && Number.isInteger(idx) ? roiNames[idx] : null;
                          return name ? `${name}` : `${nodeId}`;
                        }).join(', ')}
                      </div>
                    )}
                  </div>
                )}
              </div>
              
              {/* Analysis Results */}
              <div className="bg-white rounded-lg shadow-md p-4 border border-gray-200">
                {taskDetail.method === 'hub_detection' ? (
                  <>
                    <h3 className="text-lg font-semibold mb-3 flex items-center text-gray-700">
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      Hub Detection Results
                    </h3>
                    {taskDetail.result.hub_results && (
                      <div className="bg-gradient-to-br from-gray-50 to-gray-100 p-4 rounded-lg border border-gray-200">
                        <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                          <div className="bg-white p-3 rounded shadow-sm">
                            <div className="text-gray-500 text-xs mb-1">Method</div>
                            <div className="font-semibold text-gray-800">{taskDetail.result.hub_results.method}</div>
                          </div>
                          <div className="bg-white p-3 rounded shadow-sm">
                            <div className="text-gray-500 text-xs mb-1">Embedding Dimension (k)</div>
                            <div className="font-semibold text-gray-800">{taskDetail.result.method_specific?.hub_detection?.k || 2}</div>
                          </div>
                          <div className="bg-white p-3 rounded shadow-sm col-span-2">
                            <div className="text-gray-500 text-xs mb-1">Hub Count</div>
                            <div className="font-semibold text-gray-800">{taskDetail.result.method_specific?.hub_detection?.hub_num || 1}</div>
                          </div>
                        </div>
                        {taskDetail.result.hub_results.method === 'group' ? (
                          <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded">
                            <div className="font-semibold text-red-700 mb-2">Group Common Hubs</div>
                            <div className="font-mono text-sm text-red-900">{taskDetail.result.hub_results.hub_nodes.join(', ')}</div>
                          </div>
                        ) : (
                          <div className="bg-white border-l-4 border-indigo-500 p-4 rounded shadow-sm">
                            <div className="font-semibold text-gray-700 mb-2">Individual Hub (Window {selectedWindow + 1})</div>
                            <div className="font-mono text-sm text-indigo-700">
                              {taskDetail.result.hub_results.results?.[selectedWindow]?.hub_nodes.join(', ') || 'N/A'}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <h3 className="text-lg font-semibold mb-3 flex items-center text-gray-700">
                      <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
                      </svg>
                      CFC Matrix
                    </h3>
                    {taskDetail.result.cfcs?.[selectedWindow] ? 
                      renderCFCHeatmap(taskDetail.result.cfcs[selectedWindow], selectedWindow) :
                      <div className="text-sm text-gray-500 text-center py-8">No CFC data for this window</div>
                    }
                  </>
                )}
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center bg-white rounded-lg shadow-md">
              <div className="text-center text-gray-400">
                <p className="text-lg">No results available</p>
              </div>
            </div>
          )}
        </div>
        
        {/* Right Panel - ROI Image & Chat */}
        <div className="col-span-3 space-y-4">
          {/* ROI Image Panel */}
          <div className="h-[45%]">
            <RoiImagePanel roiName={selectedNodeLabel} />
          </div>
          
          {/* LLM Chat Panel */}
          <div className="h-[55%]">
            <LlmChatPanel
              messages={chatMessages}
              input={chatInput}
              onInputChange={setChatInput}
              onSend={handleSendChat}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

// Main App Component
export default function UnifiedBrainApp() {
  const [activeView, setActiveView] = useState('home'); // 'home', 'cfc', 'hub', 'chart'
  const [isLoading, setIsLoading] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([
    { role: "assistant", content: "Hi! I can help interpret your analysis results." }
  ]);
  const [chatInput, setChatInput] = useState("");
  const [selectedTask, setSelectedTask] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState(0);

  // Simulate initial loading
  useEffect(() => {
    setTimeout(() => {
      setIsLoading(false);
    }, 1500);
  }, []);

  const handleSendChat = async () => {
    const content = chatInput.trim();
    if (!content) return;
    
    const nextMessages = [...chatMessages, { role: "user", content }];
    setChatMessages(nextMessages);
    setChatInput("");
    
    try {
      const res = await fetch(`/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: nextMessages,
          task_id: selectedTask,
          window_idx: selectedWindow,
        })
      });
      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.detail || "LLM request failed");
      }
      
      const reply = data.response || data.message || "";
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: reply || "(No response)" }
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err.message}` }
      ]);
    }
  };

  const handleNavigate = (view) => {
    setActiveView(view);
  };

  const getViewTitle = () => {
    switch (activeView) {
      case 'cfc':
        return { title: 'CFC Wavelet Analysis', subtitle: 'Cross-Frequency Coupling using Harmonic Wavelets' };
      case 'hub':
        return { title: 'Hub Detection Analysis', subtitle: 'Detect hub nodes in brain networks using Grassmann manifold optimization' };
      case 'chart':
        return { title: 'BrainChart Analysis', subtitle: 'Lifespan normative growth curves for brain phenotypes' };
      default:
        return { title: '', subtitle: '' };
    }
  };

  if (isLoading) {
    return <LoadingPage />;
  }

  if (activeView === 'home') {
    return (
      <>
        <HomePage onNavigate={handleNavigate} />
        <FloatingLLMChat
          isOpen={chatOpen}
          onToggle={() => setChatOpen(!chatOpen)}
          messages={chatMessages}
          input={chatInput}
          onInputChange={setChatInput}
          onSend={handleSendChat}
          taskId={selectedTask}
          windowIdx={selectedWindow}
        />
      </>
    );
  }

  const { title, subtitle } = getViewTitle();

  return (
    <div className="min-h-screen bg-slate-50/80">
      <div className="flex h-screen">
        {/* Left Sidebar - Function Selection */}
        <aside className="w-[72px] flex-shrink-0 flex flex-col items-center py-5 gap-1 bg-slate-850 border-r border-slate-700/50 shadow-panel">
          <button
            onClick={() => setActiveView('home')}
            className="w-12 h-12 rounded-xl flex flex-col items-center justify-center text-slate-400 hover:text-white hover:bg-white/10 transition-all duration-200"
            title="Home"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            <span className="text-[10px] font-medium mt-0.5">Home</span>
          </button>
          <div className="w-8 border-t border-slate-600/60 my-2" />
          <button
            onClick={() => setActiveView('cfc')}
            className={`relative w-12 h-12 rounded-xl flex flex-col items-center justify-center transition-all duration-200 ${
              activeView === 'cfc'
                ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
                : 'text-slate-400 hover:text-white hover:bg-white/10'
            }`}
            title="CFC Analysis"
          >
            {activeView === 'cfc' && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-r-full" />}
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
            </svg>
            <span className="text-[10px] font-medium mt-0.5">CFC</span>
          </button>
          <button
            onClick={() => setActiveView('hub')}
            className={`relative w-12 h-12 rounded-xl flex flex-col items-center justify-center transition-all duration-200 ${
              activeView === 'hub'
                ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
                : 'text-slate-400 hover:text-white hover:bg-white/10'
            }`}
            title="Hub Detection"
          >
            {activeView === 'hub' && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-r-full" />}
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
            </svg>
            <span className="text-[10px] font-medium mt-0.5">Hub</span>
          </button>
          <button
            onClick={() => setActiveView('chart')}
            className={`relative w-12 h-12 rounded-xl flex flex-col items-center justify-center transition-all duration-200 ${
              activeView === 'chart'
                ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30'
                : 'text-slate-400 hover:text-white hover:bg-white/10'
            }`}
            title="BrainChart"
          >
            {activeView === 'chart' && <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-r-full" />}
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span className="text-[10px] font-medium mt-0.5">Chart</span>
          </button>
        </aside>

        {/* Main Content Area */}
        <div className="flex-1 flex flex-col overflow-hidden bg-white rounded-l-2xl shadow-panel">
          {/* Header */}
          <header className="flex-shrink-0 px-8 py-4 border-b border-slate-100 bg-white/90">
            <h1 className="text-xl font-semibold tracking-tight text-slate-800">{title}</h1>
            <p className="text-sm text-slate-500 mt-0.5">{subtitle}</p>
          </header>

          {/* Content */}
          <div className="flex-1 overflow-hidden">
            {(activeView === 'cfc' || activeView === 'hub') && <NetworkAnalysisView mode={activeView} />}
            {activeView === 'chart' && <BrainChartView />}
          </div>
        </div>
      </div>

      {/* Floating LLM Chat */}
      <FloatingLLMChat
        isOpen={chatOpen}
        onToggle={() => setChatOpen(!chatOpen)}
        messages={chatMessages}
        input={chatInput}
        onInputChange={setChatInput}
        onSend={handleSendChat}
        taskId={selectedTask}
        windowIdx={selectedWindow}
      />

      {/* CSS for animations */}
      <style>{`
        @keyframes slide-up {
          from { opacity: 0; transform: translateY(16px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fade-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .animate-slide-up {
          animation: slide-up 0.35s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
        .animate-fade-in {
          animation: fade-in 0.5s ease-out forwards;
        }
      `}</style>
    </div>
  );
}
