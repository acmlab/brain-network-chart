import type { OutlierResult } from '../../types'

interface Props {
  data: OutlierResult
  timestamp: string
}

export default function OutlierDetectionCard({ data, timestamp }: Props) {
  const pct = ((data.outlier_count / data.total_samples) * 100).toFixed(1)

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">Outlier Detection (Z-Score)</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">Total Samples</div>
          <div className="stat-value">{data.total_samples}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Outliers</div>
          <div className="stat-value" style={{ color: data.outlier_count > 0 ? '#f87171' : '#4ade80' }}>
            {data.outlier_count}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Outlier %</div>
          <div className="stat-value" style={{ fontSize: 16 }}>{pct}%</div>
        </div>
      </div>

      {data.outlier_count > 0 ? (
        <>
          <div className="outlier-summary">
            Outlier values (|Z| &gt; 3):
          </div>
          <div className="outlier-list">
            {data.outlier_values.map((val, i) => (
              <span key={i} className="outlier-chip" title={`Index: ${data.outlier_indices[i]}`}>
                [{data.outlier_indices[i]}] {val.toFixed(4)}
              </span>
            ))}
          </div>
        </>
      ) : (
        <div style={{ color: '#4ade80', fontSize: 13, margin: '8px 0' }}>
          No outliers detected.
        </div>
      )}

      <div className="explanation">{data['Explanation of results']}</div>
    </div>
  )
}
