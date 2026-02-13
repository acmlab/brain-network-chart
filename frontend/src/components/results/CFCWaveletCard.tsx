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

export default function CFCWaveletCard({ data, timestamp }: Props) {
  const [selectedWindow, setSelectedWindow] = useState(0)
  const [showConsole, setShowConsole] = useState(false)

  const cfc = useMemo(() => {
    if (!data.cfcs || !Array.isArray(data.cfcs)) return null
    return data.cfcs[selectedWindow] ?? null
  }, [data.cfcs, selectedWindow])

  const heatmapStats = useMemo(() => {
    if (!cfc) return null
    let min = Infinity, max = -Infinity, validCount = 0
    cfc.forEach(row => {
      if (Array.isArray(row)) row.forEach(val => {
        const n = Number(val)
        if (!isNaN(n) && isFinite(n)) { validCount++; if (n < min) min = n; if (n > max) max = n }
      })
    })
    return validCount > 0 && isFinite(min) && isFinite(max) ? { min, max, validCount } : null
  }, [cfc])

  const size = cfc?.length ?? 0
  const cellSize = Math.min(320 / Math.max(size, 1), 18)

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">CFC Wavelet Analysis</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Windows</div>
          <div className="stat-value">{data.num_windows}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">CFC Count</div>
          <div className="stat-value">{data.cfcs_count}</div>
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

      {/* Window slider */}
      {data.num_windows > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>Window</span>
          <input
            type="range" min={0} max={data.num_windows - 1} value={selectedWindow}
            onChange={e => setSelectedWindow(parseInt(e.target.value))}
            style={{ flex: 1, accentColor: '#7c3aed' }}
          />
          <span style={{ fontSize: 12, color: '#a5b4fc', fontWeight: 600, whiteSpace: 'nowrap' }}>
            {selectedWindow + 1}/{data.num_windows}
          </span>
        </div>
      )}

      {/* CFC Heatmap */}
      {cfc && heatmapStats ? (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>
              CFC Matrix — Window {selectedWindow + 1}
            </span>
            <span style={{ fontSize: 11, color: '#64748b' }}>{size}×{cfc[0]?.length ?? 0}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <div style={{ border: '1px solid #2d3250', borderRadius: 6, overflow: 'hidden' }}>
              {cfc.map((row, i) => (
                <div key={i} style={{ display: 'flex' }}>
                  {Array.isArray(row) && row.map((val, j) => {
                    const numVal = Number(val)
                    const isValid = !isNaN(numVal) && isFinite(numVal)
                    const normalized = isValid && heatmapStats.max > heatmapStats.min
                      ? (numVal - heatmapStats.min) / (heatmapStats.max - heatmapStats.min)
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
          <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b' }}>
            <span>Range: [{heatmapStats.min.toFixed(4)}, {heatmapStats.max.toFixed(4)}]</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span>Low</span>
              <div style={{ width: 60, height: 8, borderRadius: 4, background: 'linear-gradient(to right, #3b82f6, #ffffff, #ef4444)', border: '1px solid #2d3250' }} />
              <span>High</span>
            </div>
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: '16px 0', color: '#4b5563', fontSize: 13 }}>
          No CFC data for this window
        </div>
      )}

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
