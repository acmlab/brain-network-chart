import React, { useState, useEffect } from 'react';

// const API_BASE = 'http://localhost:8000';

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

const RoiImagePanel = ({ roiName }) => {
  const [roiId, setRoiId] = useState(null);
  console.log("Render image for:", roiName);
  useEffect(() => {
    if (!roiName) return;
    const cleanName = roiName.replace(/^Hub:\s*/, "");
    fetch(`/api/roi-id?name=${encodeURIComponent(cleanName)}`)
      .then(res => res.json())
      .then(data => setRoiId(data.roi_id))
      .catch(() => setRoiId(null));
  }, [roiName]);

  if (!roiName) {
    return <div className="text-sm text-gray-500">Click a node</div>;
  }

  if (!roiId) {
    return <div className="text-sm text-red-500">ROI image not found</div>;
  }

  const imgSrc = `/api/roi_figs/mask${roiId}_roi.png`;

  return (
    <div className="border rounded-lg p-4">
      <div className="font-medium text-sm mb-2">{roiName}</div>
      <img
        src={imgSrc}
        alt={roiName}
        className="w-full object-contain border"
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
    <div className="bg-white rounded-lg shadow p-4 flex flex-col h-full">
      <div className="font-medium text-sm mb-2">LLM Chat</div>
      <div className="flex-1 overflow-auto bg-gray-50 border rounded p-2 text-sm space-y-2">
        {messages.length === 0 ? (
          <div className="text-gray-500">No messages yet</div>
        ) : (
          messages.map((msg, idx) => (
            <div
              key={idx}
              className={msg.role === "user" ? "text-right" : "text-left"}
            >
              <span
                className={
                  msg.role === "user"
                    ? "inline-block bg-blue-600 text-white px-2 py-1 rounded"
                    : "inline-block bg-white border px-2 py-1 rounded"
                }
              >
                {msg.content}
              </span>
            </div>
          ))
        )}
      </div>
      <div className="mt-2">
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={3}
          placeholder="Type a message, press Enter to send"
          className="w-full border rounded px-2 py-1 text-sm"
        />
        <div className="mt-2 text-right">
          <button
            onClick={onSend}
            className="px-3 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
};

export default function BrainNetworkApp() {
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
      console.log('Task detail loaded:', data);
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
    // setChatMessages((prev) => [...prev, { role: "user", content }]);
    const nextMessages = [...chatMessages, { role: "user", content }];
    setChatMessages(nextMessages);
    setChatInput("");
    try {
      const res = await fetch(`/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // body: JSON.stringify({ prompt: content }),
        // body: JSON.stringify({ messages: nextMessages }),
        body: JSON.stringify({
          messages: nextMessages,
          task_id: selectedTask,
          window_idx: selectedWindow,
        })
        // body: JSON.stringify({ model: "qwen3", prompt: content }),
      });
      const data = await res.json();
      console.log("data:", data);
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
      const reply =
        data.response ||
        data.message ||
        (data.action === "set_node_color" ? "color updated" : "");
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
    console.log('Rendering CFC heatmap for window', index);
    
    if (!cfc || !Array.isArray(cfc) || cfc.length === 0) {
      return <div className="text-sm text-gray-500">No CFC data available</div>;
    }
    
    const size = cfc.length;
    const cellSize = Math.min(400 / size, 20);
    
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
      <div key={index} className="mb-6">
        <h4 className="text-sm font-semibold mb-2">
          Window {index + 1} - CFC Matrix ({size}x{cfc[0]?.length || 0})
        </h4>
        <div className="inline-block border border-gray-300">
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
        <div className="text-xs text-gray-600 mt-1">
          Range: [{min.toFixed(4)}, {max.toFixed(4)}]
        </div>
      </div>
    );
  };

  const renderNetwork = (graph, roiNames) => {
    if (!graph || !graph.nodes || !Array.isArray(graph.nodes)) {
      return <div className="text-sm text-gray-500">No graph data available</div>;
    }
    
    const width = 400;
    const height = 400;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = 150;
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
      <svg width={width} height={height} className="border border-gray-300">
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
          const baseR = pos.isHub ? 8 : 4;
          const r = isHovered ? baseR + 4 : baseR;

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
              x={pos.x + 10}
              y={pos.y - 10}
              className="text-xs fill-gray-800"
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
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-6">Brain Network Analysis</h1>
        
        {error && (
          <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded text-red-700">
            {error}
          </div>
        )}
        
        <div className="grid grid-cols-5 gap-6">
          <div className="col-span-1 space-y-4">
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold mb-4">Upload Data</h2>
              
              <input
                type="file"
                accept=".pkl,.pickle"
                onChange={handleFileUpload}
                disabled={uploading}
                className="w-full text-sm mb-3"
              />
              
              {uploading && (
                <p className="text-sm text-blue-600 mb-3">Uploading...</p>
              )}
              
              {uploadedFiles.length > 0 && (
                <div className="mt-3">
                  <label className="block text-sm font-medium mb-2">Uploaded Files</label>
                  <select
                    value={selectedFile || ''}
                    onChange={(e) => setSelectedFile(e.target.value)}
                    className="w-full px-2 py-1 border rounded text-sm"
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
            
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold mb-4">Analysis Method</h2>
              
              <div className="space-y-3">
                {Object.keys(ANALYSIS_METHODS).map(methodKey => (
                  <div
                    key={methodKey}
                    onClick={() => handleMethodChange(methodKey)}
                    className={`p-3 border rounded cursor-pointer transition ${
                      selectedMethod === methodKey
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <div className="font-medium text-sm">{ANALYSIS_METHODS[methodKey].name}</div>
                    <div className="text-xs text-gray-600 mt-1">
                      {ANALYSIS_METHODS[methodKey].description}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold mb-4">Configuration</h2>
              {renderConfigInputs()}
              
              <button
                onClick={handleRunAnalysis}
                disabled={!selectedFile || running}
                className={`w-full mt-4 py-2 px-4 rounded font-medium ${
                  !selectedFile || running
                    ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                    : 'bg-green-600 text-white hover:bg-green-700'
                }`}
              >
                {running ? 'Running Analysis...' : 'Run Analysis'}
              </button>
            </div>
            
            <div className="bg-white rounded-lg shadow p-4">
              <h2 className="text-lg font-semibold mb-4">Analysis Tasks</h2>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {tasks.length === 0 ? (
                  <p className="text-sm text-gray-500">No tasks yet</p>
                ) : (
                  tasks.map(task => (
                    <div
                      key={task.task_id}
                      className={`border rounded ${
                        selectedTask === task.task_id
                          ? 'border-blue-500 bg-blue-50'
                          : 'border-gray-200 bg-gray-50'
                      }`}
                    >
                      <button
                        onClick={() => setSelectedTask(task.task_id)}
                        className="w-full text-left px-3 py-2"
                      >
                        <div className="font-medium truncate text-sm">{task.filename || task.task_id}</div>
                        <div className="text-xs text-gray-500">
                          {task.method && <span className="font-semibold">[{task.method}]</span>} {task.status} - {(task.progress * 100).toFixed(0)}%
                        </div>
                      </button>
                      
                      <div className="px-3 pb-2 flex gap-2">
                        {(task.status === 'pending' || task.status === 'processing') && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCancelTask(task.task_id);
                            }}
                            className="flex-1 px-2 py-1 text-xs bg-yellow-500 text-white rounded hover:bg-yellow-600"
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
                            className="flex-1 px-2 py-1 text-xs bg-red-500 text-white rounded hover:bg-red-600"
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
          
          <div className="col-span-3 bg-white rounded-lg shadow p-6">
            {!taskDetail ? (
              <div className="text-center text-gray-500 py-20">
                Select a task to view results
              </div>
            ) : taskDetail.status === 'pending' || taskDetail.status === 'processing' ? (
              <div className="text-center py-20">
                <div className="text-lg font-semibold mb-2">Processing...</div>
                <div className="w-96 mx-auto bg-gray-200 rounded-full h-6 mb-2">
                  <div
                    className="bg-blue-600 h-6 rounded-full transition-all flex items-center justify-center text-white text-sm font-medium"
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
            ) : taskDetail.status === 'cancelled' ? (
              <div className="text-center text-orange-600 py-20">
                <div className="text-xl font-semibold mb-2">Task Cancelled</div>
                <div className="text-sm">This task was cancelled by the user</div>
              </div>
            ) : taskDetail.status === 'error' ? (
              <div className="text-center text-red-600 py-20">
                <div className="text-xl font-semibold mb-2">Error</div>
                <div className="text-sm">{taskDetail.error}</div>
              </div>
            ) : taskDetail.result ? (
              <div>
                <h2 className="text-xl font-semibold mb-4">Analysis Results</h2>
                
                <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded">
                  <p className="text-sm">
                    <strong>Method:</strong> {taskDetail.method || 'N/A'} | 
                    <strong> Windows:</strong> {taskDetail.result.num_windows || 0} | 
                    <strong> Nodes:</strong> {taskDetail.result.graphs?.[0]?.num_nodes || 0} | 
                    <strong> Label:</strong> {taskDetail.result.labels?.[0] || 'N/A'}
                  </p>
                </div>
                
                {taskDetail.result.num_windows > 0 && (
                  <>
                    <div className="mb-4">
                      <label className="block text-sm font-medium mb-2">Select Window</label>
                      <input
                        type="range"
                        min="0"
                        max={taskDetail.result.num_windows - 1}
                        value={selectedWindow}
                        onChange={(e) => setSelectedWindow(parseInt(e.target.value))}
                        className="w-full"
                      />
                      <div className="text-sm text-gray-600">
                        Window {selectedWindow + 1} / {taskDetail.result.num_windows}
                      </div>
                    </div>
                    
                    <div className="grid grid-cols-2 gap-6">
                      <div>
                        <h3 className="text-lg font-semibold mb-3">Network Graph</h3>
                        {taskDetail.result.graphs?.[selectedWindow] ? (
                          <>
                            {renderNetwork(taskDetail.result.graphs[selectedWindow], taskDetail.result.roi_names)}
                            <div className="mt-2 text-xs text-gray-600">
                              {selectedNodeLabel && (
                                <div className="text-gray-800 font-medium mb-1">
                                  Selected Node: {selectedNodeLabel}
                                </div>
                              )}
                              Nodes: {taskDetail.result.graphs[selectedWindow]?.num_nodes || 0} | 
                              Edges: {taskDetail.result.graphs[selectedWindow]?.num_edges || 0}
                              {taskDetail.result.graphs[selectedWindow]?.hub_nodes && 
                                taskDetail.result.graphs[selectedWindow].hub_nodes.length > 0 && (
                                <div className="text-red-600 font-medium mt-1">
                                  Hub Nodes: {taskDetail.result.graphs[selectedWindow].hub_nodes.map((nodeId) => {
                                    const idx = Number(nodeId);
                                    const roiNames = taskDetail.result.roi_names;
                                    const name = Array.isArray(roiNames) && Number.isInteger(idx) ? roiNames[idx] : null;
                                    return name ? `${nodeId} (${name})` : `${nodeId}`;
                                  }).join(', ')}
                                </div>
                              )}
                            </div>
                          </>
                        ) : (
                          <div className="text-sm text-gray-500">No graph data for this window</div>
                        )}
                      </div>
                      <RoiImagePanel roiName={selectedNodeLabel} />
                      <div>
                        {taskDetail.method === 'hub_detection' ? (
                          <>
                            <h3 className="text-lg font-semibold mb-3">Hub Detection Results</h3>
                            {taskDetail.result.hub_results && (
                              <div className="bg-gray-50 p-4 rounded border">
                                <div className="text-sm space-y-2">
                                  <div>
                                    <strong>Method:</strong> {taskDetail.result.hub_results.method}
                                  </div>
                                  <div>
                                    <strong>Embedding Dimension (k):</strong> {taskDetail.result.method_specific?.hub_detection?.k || 2}
                                  </div>
                                  <div>
                                    <strong>Hub Count:</strong> {taskDetail.result.method_specific?.hub_detection?.hub_num || 1}
                                  </div>
                                  {taskDetail.result.hub_results.method === 'group' ? (
                                    <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded">
                                      <strong className="text-red-700">Group Common Hubs:</strong>
                                      <div className="font-mono mt-1">{taskDetail.result.hub_results.hub_nodes.join(', ')}</div>
                                    </div>
                                  ) : (
                                    <div className="mt-3">
                                      <strong>Individual Hub (Window {selectedWindow + 1}):</strong>
                                      <div className="font-mono mt-1 text-red-600">
                                        {taskDetail.result.hub_results.results?.[selectedWindow]?.hub_nodes.join(', ') || 'N/A'}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </>
                        ) : (
                          <>
                            <h3 className="text-lg font-semibold mb-3">CFC Matrix</h3>
                            {taskDetail.result.cfcs?.[selectedWindow] ? 
                              renderCFCHeatmap(taskDetail.result.cfcs[selectedWindow], selectedWindow) :
                              <div className="text-sm text-gray-500">No CFC data for this window</div>
                            }
                          </>
                        )}
                      </div>
                    </div>
                    
                    {taskDetail.method === 'cfc_wavelet' && (
                      <div className="mt-6">
                        <h3 className="text-lg font-semibold mb-3">Wavelet Coefficients</h3>
                        {taskDetail.result.wavelets?.[selectedWindow] ? (
                          <div className="max-h-60 overflow-auto">
                            <pre className="text-xs bg-gray-50 p-3 rounded">
                              {JSON.stringify(taskDetail.result.wavelets[selectedWindow], null, 2).substring(0, 1000)}...
                            </pre>
                          </div>
                        ) : (
                          <div className="text-sm text-gray-500">No wavelet data for this window</div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div className="text-center text-gray-500 py-20">
                No results available
              </div>
            )}
          </div>
          <div className="col-span-1">
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
}
