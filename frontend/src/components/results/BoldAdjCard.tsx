import { useState, useMemo } from 'react'
import type { BoldAdjResult } from '../../types'

interface Props {
  data: BoldAdjResult
  timestamp: string
}

export default function BoldAdjCard({ data, timestamp }: Props) {
  const [selectedWindow, setSelectedWindow] = useState(0)
  const [hoveredNodeId, setHoveredNodeId] = useState<number | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null)

  const getRoiLabel = (id: number) => {
    const roi = data.roi_list?.[id]
    return roi ? `${id} ${roi.name}` : `Node ${id}`
  }

  const graph = useMemo(() => {
    const matrix = data.adj_matrices[selectedWindow]
    if (!matrix) return null
    const n = matrix.length
    const nodes = Array.from({ length: n }, (_, i) => i)
    const edges: [number, number][] = []
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (matrix[i][j] > 0) edges.push([i, j])
      }
    }
    return { nodes, edges }
  }, [data.adj_matrices, selectedWindow])

  const positions = useMemo(() => {
    if (!graph) return []
    const cx = 200, cy = 200, r = 160
    return graph.nodes.map((id, i) => {
      const angle = (2 * Math.PI * i) / graph.nodes.length - Math.PI / 2
      return { id, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
    })
  }, [graph])

  const hoverLabel = hoveredNodeId !== null ? getRoiLabel(hoveredNodeId) : null

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">Adj Visualization</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Nodes</div>
          <div className="stat-value">{data.num_nodes}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Windows</div>
          <div className="stat-value">{data.num_windows}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Edges</div>
          <div className="stat-value">{graph?.edges.length ?? 0}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Ratio</div>
          <div className="stat-value">{data.ratio}</div>
        </div>
      </div>

      {data.num_windows > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 12, color: '#94a3b8', whiteSpace: 'nowrap' }}>Window</span>
          <input
            type="range" min={0} max={data.num_windows - 1} value={selectedWindow}
            onChange={e => { setSelectedWindow(parseInt(e.target.value)); setSelectedNodeId(null) }}
            style={{ flex: 1, accentColor: '#7c3aed' }}
          />
          <span style={{ fontSize: 12, color: '#a5b4fc', fontWeight: 600, whiteSpace: 'nowrap' }}>
            {selectedWindow + 1}/{data.num_windows}
          </span>
        </div>
      )}

      {graph ? (
        <>
          <svg viewBox="0 0 400 400" style={{ width: '100%', maxHeight: 260, borderRadius: 8, border: '1px solid #2d3250', background: '#0f1117' }}>
            {/* Edges */}
            {graph.edges.map(([s, t], i) => {
              const src = positions[s], tgt = positions[t]
              if (!src || !tgt) return null
              const isConnected = hoveredNodeId !== null && (s === hoveredNodeId || t === hoveredNodeId)
              return (
                <line key={i}
                  x1={src.x} y1={src.y} x2={tgt.x} y2={tgt.y}
                  stroke={isConnected ? '#fbbf24' : '#6366f1'}
                  strokeWidth={isConnected ? 2 : 0.8}
                  opacity={isConnected ? 1 : (hoveredNodeId !== null ? 0.05 : 0.5)}
                  pointerEvents="none"
                />
              )
            })}
            {/* Nodes */}
            {positions.map(pos => {
              const isSelected = selectedNodeId === pos.id
              const isHovered = hoveredNodeId === pos.id
              const nodeR = isHovered ? 8 : isSelected ? 7 : 5
              return (
                <circle key={pos.id}
                  cx={pos.x} cy={pos.y} r={nodeR}
                  fill={isSelected ? '#f59e0b' : '#7c3aed'}
                  stroke={isSelected ? '#fbbf24' : (isHovered ? '#e2e8f0' : '#a78bfa')}
                  strokeWidth={isSelected ? 2.5 : (isHovered ? 1.5 : 1)}
                  onMouseEnter={() => setHoveredNodeId(pos.id)}
                  onMouseLeave={() => setHoveredNodeId(null)}
                  onClick={() => setSelectedNodeId(prev => prev === pos.id ? null : pos.id)}
                  style={{ cursor: 'pointer' }}
                />
              )
            })}
          </svg>

          <div style={{ marginTop: 6, minHeight: 18, fontSize: 12, color: '#a5b4fc' }}>
            {hoverLabel
              ? <span style={{ color: '#94a3b8' }}>{hoverLabel}</span>
              : selectedNodeId !== null
                ? <span>{getRoiLabel(selectedNodeId)} — {graph.edges.filter(([s, t]) => s === selectedNodeId || t === selectedNodeId).length} connections</span>
                : <span style={{ color: '#475569' }}>Hover or click a node</span>
            }
          </div>
        </>
      ) : (
        <div style={{ textAlign: 'center', padding: 24, color: '#64748b', fontSize: 13 }}>No data</div>
      )}
    </div>
  )
}
