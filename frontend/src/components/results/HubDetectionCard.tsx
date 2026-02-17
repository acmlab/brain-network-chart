import { useState, useMemo } from 'react'
import type { HubDetectionResult } from '../../types'

interface Props {
  data: HubDetectionResult
  timestamp: string
}

export default function HubDetectionCard({ data, timestamp }: Props) {
  const [selectedWindow, setSelectedWindow] = useState(0)
  const [showConsole, setShowConsole] = useState(false)

  const method = data.results?.method ?? 'unknown'
  const isGroup = method === 'group'

  const hubRankings = useMemo(() => {
    if (isGroup || !data.results?.results) return null
    const freq: Record<number, number> = {}
    for (const r of data.results.results) {
      for (const node of (r.hub_nodes ?? [])) {
        freq[node] = (freq[node] ?? 0) + 1
      }
    }
    return Object.entries(freq)
      .map(([node_id, count]) => ({ node_id: Number(node_id), count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 20)
  }, [data.results, isGroup])

  const currentWindowHubs = useMemo(() => {
    if (isGroup) return data.results?.hub_nodes ?? []
    return data.results?.results?.[selectedWindow]?.hub_nodes ?? []
  }, [data.results, isGroup, selectedWindow])

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">Hub Detection</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{
          padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
          background: isGroup ? '#14532d' : '#1e1b4b',
          color: isGroup ? '#4ade80' : '#a5b4fc',
        }}>
          {isGroup ? 'Group' : 'Individual'}
        </span>
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Files</div>
          <div className="stat-value">{data.num_windows}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Embedding k</div>
          <div className="stat-value">{data.k}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Hub Count</div>
          <div className="stat-value">{data.hub_num}</div>
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

      {/* Window slider for individual mode */}
      {!isGroup && data.num_windows > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>File</span>
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

      {/* Hub nodes */}
      <div style={{
        background: isGroup ? '#1c0505' : '#0d0f1e',
        border: `1px solid ${isGroup ? '#7f1d1d' : '#2d3250'}`,
        borderRadius: 8, padding: '10px 12px', marginBottom: 12,
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: isGroup ? '#f87171' : '#a5b4fc', marginBottom: 6 }}>
          {isGroup ? 'Group Common Hubs' : `Hub Nodes — File ${selectedWindow + 1}`}
        </div>
        {currentWindowHubs.length > 0 ? (
          <div style={{ fontFamily: 'monospace', fontSize: 12, color: isGroup ? '#fca5a5' : '#c7d2fe', lineHeight: 1.6 }}>
            {currentWindowHubs.map((idx, i) => {
              const roi = data.roi_list?.[idx]
              const label = roi ? `${idx} (${roi.name})` : `${idx}`
              return <span key={idx}>{i > 0 ? ', ' : ''}{label}</span>
            })}
          </div>
        ) : (
          <div style={{ fontSize: 12, color: '#4b5563' }}>No hub nodes</div>
        )}
      </div>

      {/* ROI composite + legend side by side */}
      {data.roi_list && currentWindowHubs.length > 0 && (() => {
        const PALETTE = ['#ef4444','#3b82f6','#22c55e','#f59e0b','#a855f7',
                         '#ec4899','#14b8a6','#f97316','#6366f1','#84cc16']
        const hubsWithRoi = currentWindowHubs.filter(idx => data.roi_list![idx]?.code)
        if (hubsWithRoi.length === 0) return null
        const roiIds = hubsWithRoi.map(idx => data.roi_list![idx].code)
        const url = `/roi_figs/composite?ids=${roiIds.join(',')}`
        return (
          <div style={{ display: 'flex', gap: 10, marginBottom: 12, alignItems: 'flex-start' }}>
            <img src={url} style={{ width: '50%', borderRadius: 6, display: 'block', flexShrink: 0 }} alt="Hub ROIs" />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#64748b', marginBottom: 2 }}>ROI Legend</div>
              {hubsWithRoi.map((idx, i) => {
                const roi = data.roi_list![idx]
                return (
                  <span key={idx} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
                    <span style={{ width: 9, height: 9, borderRadius: 2, background: PALETTE[i % PALETTE.length], display: 'inline-block', flexShrink: 0 }} />
                    <span style={{ color: '#94a3b8' }}>{roi.name}</span>
                  </span>
                )
              })}
            </div>
          </div>
        )
      })()}

      {/* Hub frequency ranking (individual mode only) */}
      {hubRankings && hubRankings.length > 0 && (
        <div style={{ border: '1px solid #2d3250', borderRadius: 8, overflow: 'hidden', marginBottom: 12 }}>
          <div style={{ padding: '8px 12px', background: '#0f1117', fontSize: 11, fontWeight: 600, color: '#64748b' }}>
            Hub Frequency Ranking
          </div>
          <div style={{ maxHeight: 160, overflowY: 'auto' }}>
            {hubRankings.map((item, idx) => {
              const roiName = data.roi_list?.[item.node_id]?.name
              return (
                <div key={item.node_id} style={{
                  padding: '6px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  fontSize: 12, borderTop: idx === 0 ? 'none' : '1px solid #1e2235',
                }}>
                  <span style={{ color: '#94a3b8' }}>
                    #{idx + 1} Node {item.node_id}
                    {roiName && <span style={{ color: '#64748b', marginLeft: 6 }}>{roiName}</span>}
                  </span>
                  <span style={{ fontWeight: 600, color: '#a5b4fc' }}>{item.count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Console output toggle */}
      {data.console_output && (
        <div>
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
