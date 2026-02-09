import { useEffect, useMemo, useState } from 'react';
import {
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { ErrorBanner, Spinner } from './ui.jsx';

export const BrainChartView = () => {
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
    { label: 'Full Range', min: -1, max: 80, cls: 'text-slate-600 bg-slate-100 hover:bg-slate-200' },
    { label: 'Childhood (0–25)', min: 0, max: 25, cls: 'text-blue-700 bg-blue-50 hover:bg-blue-100' },
    { label: 'Adolescence (13–30)', min: 13, max: 30, cls: 'text-violet-700 bg-violet-50 hover:bg-violet-100' },
    { label: 'Aging (40–80)', min: 40, max: 80, cls: 'text-amber-700 bg-amber-50 hover:bg-amber-100' },
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
                    {[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{n}</option>)}
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
                  <Line dataKey="p5" stroke="#475569" strokeWidth={1.5} strokeDasharray="5 4" dot={false} name="5th" />
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
