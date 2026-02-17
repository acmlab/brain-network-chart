import { useState, useMemo } from 'react'
import type { CFCWaveletResult } from '../../types'

interface Props {
  data: CFCWaveletResult
  timestamp: string
}

function getHeatColor(normalized: number): string {
  const r = normalized > 0.5 ? 255 : Math.round(normalized * 2 * 255)
  const b = normalized < 0.5 ? 255 : Math.round((1 - normalized) * 2 * 255)
  const g = normalized < 0.5
    ? Math.round(normalized * 2 * 255)
    : Math.round((1 - normalized) * 2 * 255)
  return `rgb(${r},${g},${b})`
}

function CfcHeatmap({ matrix, title }: { matrix: number[][]; title: string }) {
  const displayMatrix = useMemo(() => {
    return matrix.map((row, i) => row.map((val, j) => (i === j ? 0 : val)))
  }, [matrix])

  const stats = useMemo(() => {
    let min = Infinity, max = -Infinity, validCount = 0
    displayMatrix.forEach(row => {
      if (Array.isArray(row)) row.forEach(val => {
        const n = Number(val)
        if (!isNaN(n) && isFinite(n)) { validCount++; if (n < min) min = n; if (n > max) max = n }
      })
    })
    if (validCount === 0 || !isFinite(min) || !isFinite(max)) return null
    const absMax = Math.max(Math.abs(min), Math.abs(max))
    return { min: -absMax, max: absMax, absMax }
  }, [displayMatrix])

  const size = matrix.length
  const cellSize = Math.min(200 / Math.max(size, 1), 14)

  if (!stats) return (
    <div style={{ textAlign: 'center', padding: '16px 0', color: '#4b5563', fontSize: 13 }}>No CFC data</div>
  )

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 11, color: '#64748b' }}>{size}×{matrix[0]?.length ?? 0}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <div style={{ border: '1px solid #2d3250', borderRadius: 6, overflow: 'hidden' }}>
          {displayMatrix.map((row, i) => (
            <div key={i} style={{ display: 'flex' }}>
              {Array.isArray(row) && row.map((val, j) => {
                const numVal = Number(val)
                const isValid = !isNaN(numVal) && isFinite(numVal)
                const normalized = isValid && stats.max > stats.min
                  ? (numVal - stats.min) / (stats.max - stats.min)
                  : 0
                return (
                  <div key={j}
                    style={{ width: cellSize, height: cellSize, backgroundColor: isValid ? getHeatColor(normalized) : '#334155' }}
                    title={`[${i},${j}]: ${isValid ? numVal.toFixed(4) : 'N/A'}`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
      <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3, fontSize: 11, color: '#64748b' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span>Low</span>
          <div style={{ width: 60, height: 8, borderRadius: 4, background: 'linear-gradient(to right, #3b82f6, #ffffff, #ef4444)', border: '1px solid #2d3250' }} />
          <span>High</span>
        </div>
        <span>±{stats.absMax.toFixed(4)}</span>
      </div>
    </div>
  )
}

export default function CFCWaveletCard({ data, timestamp }: Props) {
  const [selectedFile, setSelectedFile] = useState(0)
  const [selectedWindow, setSelectedWindow] = useState(0)
  const [showConsole, setShowConsole] = useState(false)

  const isFolderMode = (data.files_cfcs?.length ?? 0) > 1

  // Current file's window list
  const currentFileCfcs = useMemo(() => {
    if (isFolderMode && data.files_cfcs) return data.files_cfcs[selectedFile]?.cfcs ?? []
    return data.cfcs ?? []
  }, [isFolderMode, data.files_cfcs, data.cfcs, selectedFile])

  const numWindowsInFile = currentFileCfcs.length

  const windowCfc = useMemo(() => {
    return currentFileCfcs[selectedWindow] ?? null
  }, [currentFileCfcs, selectedWindow])

  const currentFileAvg = useMemo(() => {
    if (isFolderMode) return data.files_avg_cfcs?.[selectedFile]?.avg_cfc ?? null
    return data.avg_cfc ?? null
  }, [isFolderMode, data.files_avg_cfcs, data.avg_cfc, selectedFile])

  function handleFileChange(idx: number) {
    setSelectedFile(idx)
    setSelectedWindow(0)
  }

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">CFC Wavelet Analysis</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Total Windows</div>
          <div className="stat-value">{data.num_windows}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Files</div>
          <div className="stat-value">{data.files_cfcs?.length ?? 1}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Elapsed (s)</div>
          <div className="stat-value" style={{ color: '#a5b4fc' }}>{data.elapsed_seconds.toFixed(2)}</div>
        </div>
      </div>

      {/* Progress steps */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 12 }}>
        {data.progress.map((p, i) => {
          const color = p.step === 'error' ? '#f87171' : p.step === 'analyzing' ? '#fbbf24' : '#4ade80'
          const bg = p.step === 'error' ? '#450a0a' : p.step === 'analyzing' ? '#422006' : '#052e16'
          return (
            <span key={i} style={{ background: bg, color, borderRadius: 6, padding: '2px 8px', fontSize: 11 }}>
              {p.message}
            </span>
          )
        })}
      </div>

      {/* File selector (folder mode only) */}
      {isFolderMode && (
        <div className="form-row" style={{ marginBottom: 10 }}>
          <label style={{ fontSize: 12, color: '#94a3b8', display: 'block', marginBottom: 4 }}>File</label>
          <select
            className="form-select"
            value={selectedFile}
            onChange={e => handleFileChange(Number(e.target.value))}
          >
            {data.files_cfcs!.map((f, i) => (
              <option key={i} value={i}>{f.filename}</option>
            ))}
          </select>
        </div>
      )}

      {/* Window slider */}
      {numWindowsInFile > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>Window</span>
          <input
            type="range" min={0} max={numWindowsInFile - 1} value={selectedWindow}
            onChange={e => setSelectedWindow(parseInt(e.target.value))}
            style={{ flex: 1, accentColor: '#7c3aed' }}
          />
          <span style={{ fontSize: 12, color: '#a5b4fc', fontWeight: 600, whiteSpace: 'nowrap' }}>
            {selectedWindow + 1}/{numWindowsInFile}
          </span>
        </div>
      )}

      {/* Heatmaps side by side */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {windowCfc && windowCfc.length > 0 && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <CfcHeatmap
              matrix={windowCfc}
              title={isFolderMode
                ? `Window ${selectedWindow + 1}`
                : `Window ${selectedWindow + 1}`}
            />
          </div>
        )}
        {currentFileAvg && currentFileAvg.length > 0 && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <CfcHeatmap
              matrix={currentFileAvg}
              title={isFolderMode ? `File Avg` : 'Avg (all windows)'}
            />
          </div>
        )}
        {isFolderMode && data.avg_cfc && data.avg_cfc.length > 0 && (
          <div style={{ flex: 1, minWidth: 0 }}>
            <CfcHeatmap matrix={data.avg_cfc} title="Overall Avg" />
          </div>
        )}
      </div>

      {/* Console output toggle */}
      {data.console_output && (
        <div style={{ marginTop: 12 }}>
          <button
            onClick={() => setShowConsole(v => !v)}
            style={{ fontSize: 11, color: '#7c3aed', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          >
            {showConsole ? '▲ Hide' : '▼ Show'} console output
          </button>
          {showConsole && (
            <pre style={{
              marginTop: 6, padding: 8, background: '#0f1117', border: '1px solid #2d3250',
              borderRadius: 6, fontSize: 10, color: '#94a3b8', maxHeight: 120,
              overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            }}>
              {data.console_output}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
