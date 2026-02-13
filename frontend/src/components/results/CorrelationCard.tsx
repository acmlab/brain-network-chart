import type { CorrelationResult } from '../../types'

interface Props {
  data: CorrelationResult
  timestamp: string
}

export default function CorrelationCard({ data, timestamp }: Props) {
  const r = data.correlation
  const absR = Math.abs(r)
  const strength =
    absR >= 0.7 ? 'Strong' :
    absR >= 0.4 ? 'Moderate' :
    absR >= 0.2 ? 'Weak' : 'Negligible'

  const barColor =
    absR >= 0.7 ? '#818cf8' :
    absR >= 0.4 ? '#60a5fa' :
    '#4b5563'

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">Pearson Correlation</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">r</div>
          <div className="stat-value" style={{ color: r >= 0 ? '#4ade80' : '#f87171' }}>
            {r.toFixed(4)}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">p-value</div>
          <div className="stat-value" style={{ fontSize: 14 }}>
            {data.p_value < 0.001 ? '< 0.001' : data.p_value.toFixed(4)}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">n samples</div>
          <div className="stat-value">{data.n_samples}</div>
        </div>
      </div>

      <div style={{ margin: '12px 0 4px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748b', marginBottom: 4 }}>
          <span>|r| = {absR.toFixed(3)}</span>
          <span>{strength}</span>
        </div>
        <div style={{ background: '#0f1117', borderRadius: 4, height: 8, overflow: 'hidden' }}>
          <div style={{ width: `${absR * 100}%`, height: '100%', background: barColor, borderRadius: 4, transition: 'width 0.4s' }} />
        </div>
      </div>

      <div style={{ marginTop: 10 }}>
        <span className={`badge ${data.significant ? 'badge-sig' : 'badge-nonsig'}`}>
          {data.significant ? 'Significant (p < 0.05)' : 'Not Significant'}
        </span>
      </div>

      <div className="explanation">{data['Explanation of results']}</div>
    </div>
  )
}
