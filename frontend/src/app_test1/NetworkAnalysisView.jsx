import { useEffect, useMemo, useState } from 'react';
import { ANALYSIS_METHODS } from './constants.js';
import { showToast } from './toast.jsx';
import { ErrorBanner, Spinner, StatusBadge, getHeatColor } from './ui.jsx';
import { RoiImagePanel } from './RoiImagePanel.jsx';

export const NetworkAnalysisView = ({ mode }) => {
  const initialMethod = mode === 'hub' ? 'hub_detection' : 'cfc_wavelet';

  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);
  const [taskDetail, setTaskDetail] = useState(null);
  const [selectedWindow, setSelectedWindow] = useState(0);
  const [selectedFileIndex, setSelectedFileIndex] = useState(0);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedMethod, setSelectedMethod] = useState(initialMethod);
  const [config, setConfig] = useState(ANALYSIS_METHODS[initialMethod].config);
  const [uploading, setUploading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [useCfcAvg, setUseCfcAvg] = useState(false);
  const [selectedNodeLabel, setSelectedNodeLabel] = useState(null);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [nodeColorMap, setNodeColorMap] = useState({});
  const [hoveredNodeId, setHoveredNodeId] = useState(null);

  const loadTasks = async () => {
    try {
      const res = await fetch('/api/tasks');
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (err) { console.error('Failed to load tasks:', err); }
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
    if (selectedTask) {
      setSelectedWindow(0);
      setSelectedFileIndex(0);
      setUseCfcAvg(false);
      loadTaskDetail(selectedTask);
    }
    else setTaskDetail(null);
  }, [selectedTask]);

  useEffect(() => { setSelectedNodeLabel(null); setSelectedNodeId(null); }, [selectedWindow, selectedTask, selectedFileIndex]);

  // Keep method/config and selected task in sync with current view (CFC vs Hub)
  useEffect(() => {
    const m = mode === 'hub' ? 'hub_detection' : 'cfc_wavelet';
    setSelectedMethod(m);
    setConfig(ANALYSIS_METHODS[m].config);
    setSelectedTask(null);
    setTaskDetail(null);
    setSelectedFileIndex(0);
    setUseCfcAvg(false);
  }, [mode]);

  const handleFileUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true);
    try {
      const isCsvTsv = (name) => name.toLowerCase().match(/\.(csv|tsv)$/);
      const isSingleOk = (name) => name.toLowerCase().match(/\.(csv|tsv|pkl|pickle)$/);
      const validCsvTsv = files.filter(f => isCsvTsv(f.name));
      const validSingle = files.filter(f => isSingleOk(f.name));
      const ignoredCount = files.length - validSingle.length;

      if (validSingle.length === 0) {
        showToast('No valid files found (.csv/.tsv/.pkl/.pickle)', 'warning');
        return;
      }

      if (ignoredCount > 0) {
        showToast(`Ignored ${ignoredCount} non-CSV/TSV files`, 'warning');
      }

      const formData = new FormData();
      if (files.length === 1) {
        formData.append('file', validSingle[0]);
      } else {
        if (validCsvTsv.length === 0) {
          showToast('Folder upload supports only .csv/.tsv files', 'warning');
          return;
        }
        validCsvTsv.forEach(f => formData.append('files', f));
      }

      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const data = await res.json();
      if (res.ok) {
        setUploadedFiles(prev => [
          ...prev,
          { id: data.file_id, name: data.filename, count: data.file_count }
        ]);
        setSelectedFile(data.file_id);
        showToast('Upload successful', 'success');
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

  const result = taskDetail?.result;
  const graphsByFile = useMemo(() => {
    if (!result?.graphs) return [];
    return Array.isArray(result.graphs[0]) ? result.graphs : [result.graphs];
  }, [result]);
  const cfcsByFile = useMemo(() => {
    if (!result?.cfcs) return [];
    return Array.isArray(result.cfcs[0]) ? result.cfcs : [result.cfcs];
  }, [result]);
  const hubResultsByFile = useMemo(() => {
    if (!result?.hub_results) return [];
    return Array.isArray(result.hub_results) ? result.hub_results : [result.hub_results];
  }, [result]);

  const fileCount = Math.max(1, result?.file_count || graphsByFile.length || cfcsByFile.length || 1);
  const fileNames = result?.file_names || [];
  const activeFileIndex = Math.min(selectedFileIndex, Math.max(0, fileCount - 1));
  const activeGraphs = graphsByFile[activeFileIndex] || [];
  const activeCfcs = cfcsByFile[activeFileIndex] || [];
  const activeHubResults = hubResultsByFile[activeFileIndex] || null;
  const activeLabel = Array.isArray(result?.labels?.[activeFileIndex])
    ? result.labels[activeFileIndex][0]
    : result?.labels?.[0];
  const windowsForSelectedFile =
    result?.num_windows_per_file?.[activeFileIndex]
    ?? activeGraphs.length
    ?? activeCfcs.length
    ?? result?.num_windows
    ?? 0;

  useEffect(() => {
    if (selectedFileIndex > fileCount - 1) setSelectedFileIndex(0);
  }, [fileCount, selectedFileIndex]);

  useEffect(() => {
    if (windowsForSelectedFile > 0 && selectedWindow > windowsForSelectedFile - 1) {
      setSelectedWindow(0);
    }
  }, [windowsForSelectedFile, selectedWindow]);

  const getCurrentWindow = (progress) => {
    const count = windowsForSelectedFile || taskDetail?.result?.num_windows || 0;
    if (!count) return 0;
    if (progress < 0.6) return Math.max(0, Math.floor(((progress - 0.2) / 0.4) * count));
    if (progress < 0.8) return Math.max(0, Math.floor(((progress - 0.6) / 0.2) * count));
    return count;
  };

  const cfcMatrixToShow = useMemo(() => {
    if (!result?.cfcs) return null;
    if (useCfcAvg && Array.isArray(result.cfc_avg_all_files) && result.cfc_avg_all_files.length > 0) {
      return result.cfc_avg_all_files[selectedWindow];
    }
    return activeCfcs[selectedWindow];
  }, [result, useCfcAvg, activeCfcs, selectedWindow]);

  const selectedNodeAvg = useMemo(() => {
    if (selectedNodeId === null || selectedNodeId === undefined) return null;
    if (!cfcsByFile.length) return null;
    const idx = Number(selectedNodeId);
    if (Number.isNaN(idx)) return null;
    const rows = [];
    cfcsByFile.forEach(fileCfcs => {
      const mat = fileCfcs?.[selectedWindow];
      if (Array.isArray(mat) && Array.isArray(mat[idx])) {
        rows.push(mat[idx]);
      }
    });
    if (rows.length === 0) return null;
    const len = rows[0].length;
    const sums = new Array(len).fill(0);
    rows.forEach(row => {
      for (let i = 0; i < len; i += 1) {
        sums[i] += Number(row[i]) || 0;
      }
    });
    return sums.map(v => v / rows.length);
  }, [selectedNodeId, selectedWindow, cfcsByFile]);

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

  const currentMethodKey = mode === 'hub' ? 'hub_detection' : 'cfc_wavelet';
  const filteredTasks = tasks.filter(task => !task.method || task.method === currentMethodKey);

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
                <p className="text-xs text-slate-500">Drop a folder (.csv/.tsv) or single file</p>
                <input
                  type="file"
                  accept=".pkl,.pickle,.csv,.tsv"
                  multiple
                  webkitdirectory="true"
                  onChange={handleFileUpload}
                  disabled={uploading}
                  className="sr-only"
                />
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
                    {uploadedFiles.map(file => (
                      <option key={file.id} value={file.id}>
                        {file.name}{file.count ? ` (${file.count} files)` : ''}
                      </option>
                    ))}
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
              {/* Fixed method per view (CFC or Hub) */}
              <div className="flex items-center justify-between mb-3">
                <div>
                  <p className="text-xs font-medium text-slate-500">Method</p>
                  <p className="text-[11px] text-slate-400">Fixed for this analysis view</p>
                </div>
                <span className="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-100 text-slate-700">
                  {mode === 'hub' ? 'Hub Detection' : 'CFC Wavelet'}
                </span>
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
              {filteredTasks.length === 0 ? (
                <p className="text-xs text-slate-400 text-center py-4">No tasks yet</p>
              ) : filteredTasks.map(task => (
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
                {windowsForSelectedFile > 0 && (
                  <div className="text-xs text-slate-400 mt-3">Window {getCurrentWindow(taskDetail.progress)} / {windowsForSelectedFile}</div>
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
                    { label: 'Method', value: taskDetail.method || 'N/A' },
                    { label: 'Label', value: activeLabel ?? 'N/A' },
                    { label: 'Windows', value: windowsForSelectedFile || 0 },
                    { label: 'Nodes', value: activeGraphs?.[0]?.num_nodes || 0 },
                  ].map(item => (
                    <div key={item.label} className="bg-slate-50 rounded-lg p-2.5">
                      <div className="text-xs text-slate-500">{item.label}</div>
                      <div className="text-sm font-semibold text-indigo-700 mt-0.5">{item.value}</div>
                    </div>
                  ))}
                </div>
              </div>

              {(fileCount > 1 || windowsForSelectedFile > 0) && (
                <div className="bg-white border border-slate-200 rounded-xl p-4">
                  <div className="flex items-center gap-2 text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-3">
                    <span>Scope</span>
                    <span className="text-slate-300">/</span>
                    <span className="text-slate-400 normal-case font-medium">File Index → Time Window</span>
                  </div>
                  <div className="flex items-start gap-4">
                    {fileCount > 1 && (
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-2">
                          <label className="text-xs font-semibold text-slate-700">File Index</label>
                          <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                            {activeFileIndex + 1} / {fileCount}
                          </span>
                        </div>
                        <input type="range" min="0" max={fileCount - 1} value={activeFileIndex}
                          onChange={(e) => setSelectedFileIndex(parseInt(e.target.value))}
                          className="w-full h-2 bg-slate-200 rounded-full appearance-none cursor-pointer accent-indigo-600" />
                        <div className="mt-1 text-[11px] text-slate-500 truncate">
                          {fileNames[activeFileIndex] || `File ${activeFileIndex + 1}`}
                        </div>
                      </div>
                    )}
                    {windowsForSelectedFile > 0 && (
                      <div className={`flex-1 min-w-0 ${fileCount > 1 ? 'pl-3 border-l border-slate-100' : ''}`}>
                        <div className="flex items-center justify-between mb-2">
                          <label className="text-xs font-semibold text-slate-600">Time Window (within file)</label>
                          <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
                            {selectedWindow + 1} / {windowsForSelectedFile}
                          </span>
                        </div>
                        <input type="range" min="0" max={windowsForSelectedFile - 1} value={selectedWindow}
                          onChange={(e) => setSelectedWindow(parseInt(e.target.value))}
                          className="w-full h-2 bg-slate-200 rounded-full appearance-none cursor-pointer accent-indigo-600" />
                      </div>
                    )}
                  </div>
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
                    <span><strong className="text-slate-700">{activeGraphs?.[selectedWindow]?.num_nodes || 0}</strong> nodes</span>
                    <span><strong className="text-slate-700">{activeGraphs?.[selectedWindow]?.num_edges || 0}</strong> edges</span>
                  </div>
                </div>
                <div className="flex justify-center">
                  {activeGraphs?.[selectedWindow]
                    ? renderNetwork(activeGraphs[selectedWindow], taskDetail.result.roi_names)
                    : <div className="text-sm text-slate-500">No graph data for this window</div>
                  }
                </div>
                {activeGraphs?.[selectedWindow] && (
                  <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between">
                    {selectedNodeLabel ? (
                      <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-indigo-500" />
                        Selected: {selectedNodeLabel}
                      </span>
                    ) : <span className="text-xs text-slate-400">Hover or click a node</span>}
                    {activeGraphs[selectedWindow]?.hub_nodes?.length > 0 && (
                      <span className="text-xs text-red-600 font-semibold">
                        Hubs: {activeGraphs[selectedWindow].hub_nodes.map((nodeId) => {
                          const idx = Number(nodeId);
                          const rn = taskDetail.result.roi_names;
                          return (Array.isArray(rn) && Number.isInteger(idx) && rn[idx]) ? rn[idx] : `${nodeId}`;
                        }).join(', ')}
                      </span>
                    )}
                  </div>
                )}
              </div>

            </div>
          ) : (
            <div className="h-full flex items-center justify-center bg-white border border-slate-200 rounded-xl">
              <p className="text-sm text-slate-400">No results available</p>
            </div>
          )}
        </div>

        {/* Right — ROI + Results */}
        <div className="col-span-3 flex flex-col gap-3 min-h-0">
          <div className="w-full" style={{ aspectRatio: '1 / 1' }}>
            <RoiImagePanel roiName={selectedNodeLabel} />
          </div>
          <div className="flex-1 min-h-0 overflow-auto bg-white border border-slate-200 rounded-xl p-4">
            {taskDetail?.result ? (
              <>
                {taskDetail.method === 'hub_detection' ? (
                  <>
                    <div className="flex items-center gap-2 mb-3">
                      <svg className="w-4 h-4 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                      </svg>
                      <h3 className="text-sm font-semibold text-slate-700">Hub Detection Results</h3>
                    </div>
                    {activeHubResults && (
                      <div className="bg-slate-50 rounded-lg border border-slate-200 p-4">
                        <div className="grid grid-cols-3 gap-3 mb-4">
                          {[
                            { label: 'Method', value: activeHubResults.method },
                            { label: 'Embedding (k)', value: taskDetail.result.method_specific?.hub_detection?.k || 2 },
                            { label: 'Hub Count', value: taskDetail.result.method_specific?.hub_detection?.hub_num || 1 },
                          ].map(item => (
                            <div key={item.label} className="bg-white rounded-lg p-2.5 shadow-sm">
                              <div className="text-xs text-slate-500">{item.label}</div>
                              <div className="text-sm font-semibold text-slate-700">{item.value}</div>
                            </div>
                          ))}
                        </div>
                        {activeHubResults.method === 'group' ? (
                          <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                            <div className="text-xs font-semibold text-red-700 mb-1">Group Common Hubs</div>
                            <div className="font-mono text-xs text-red-900">{activeHubResults.hub_nodes.join(', ')}</div>
                          </div>
                        ) : (
                          <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
                            <div className="text-xs font-semibold text-indigo-700 mb-1">Individual Hub — Window {selectedWindow + 1}</div>
                            <div className="font-mono text-xs text-indigo-900">
                              {activeHubResults.results?.[selectedWindow]?.hub_nodes.join(', ') || 'N/A'}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {Array.isArray(taskDetail.result.hub_rankings) && taskDetail.result.hub_rankings.length > 0 && (
                      <div className="mt-4 bg-white border border-slate-200 rounded-lg">
                        <div className="px-3.5 py-2.5 border-b border-slate-100 bg-slate-50 text-xs font-semibold text-slate-600">
                          Hub Frequency Ranking
                        </div>
                        <div className="max-h-40 overflow-auto divide-y divide-slate-100">
                          {taskDetail.result.hub_rankings.slice(0, 20).map((item, idx) => (
                            <div key={`${item.node_id}-${idx}`} className="px-3.5 py-2 flex items-center justify-between text-xs">
                              <span className="text-slate-600">
                                #{idx + 1} {item.roi_name || `Node ${item.node_id}`}
                              </span>
                              <span className="font-semibold text-slate-700">{item.count}</span>
                            </div>
                          ))}
                        </div>
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
                    {fileCount > 1 && Array.isArray(taskDetail.result.cfc_avg_all_files) && (
                      <label className="mb-2 flex items-center gap-2 text-xs text-slate-600">
                        <input
                          type="checkbox"
                          checked={useCfcAvg}
                          onChange={(e) => setUseCfcAvg(e.target.checked)}
                          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-400"
                        />
                        Average across files (matrix)
                      </label>
                    )}
                    {cfcMatrixToShow
                      ? renderCFCHeatmap(cfcMatrixToShow, selectedWindow)
                      : <div className="text-sm text-slate-500 text-center py-8">No CFC data for this window</div>
                    }
                    {fileCount > 1 && selectedNodeAvg && (
                      <div className="mt-4">
                        <div className="text-xs font-semibold text-slate-600 mb-2">
                          Selected Node Avg Across Files
                        </div>
                        <div className="border border-slate-200 rounded-lg overflow-x-auto">
                          <div className="flex min-w-max">
                            {(() => {
                              let min = Infinity;
                              let max = -Infinity;
                              selectedNodeAvg.forEach(v => { if (v < min) min = v; if (v > max) max = v; });
                              return selectedNodeAvg.map((val, idx) => {
                                const normalized = max > min ? (val - min) / (max - min) : 0;
                                return (
                                  <div
                                    key={idx}
                                    title={`Node ${idx}: ${val.toFixed(4)}`}
                                    style={{ width: 10, height: 20, backgroundColor: getHeatColor(normalized) }}
                                  />
                                );
                              });
                            })()}
                          </div>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            ) : (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">No results available</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
