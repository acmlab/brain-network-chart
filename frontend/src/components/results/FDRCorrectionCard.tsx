import type { FDRResult } from '../../types'

interface Props {
  data: FDRResult
  timestamp: string
}

export default function FDRCorrectionCard({ data, timestamp }: Props) {
  const sigCount = data.significant_after_correction.filter(Boolean).length
  const total = data.original_p_values.length

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">FDR Correction (Benjamini-Hochberg)</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <div className="stat-box" style={{ flex: 1 }}>
          <div className="stat-label">Total Tests</div>
          <div className="stat-value">{total}</div>
        </div>
        <div className="stat-box" style={{ flex: 1 }}>
          <div className="stat-label">Significant</div>
          <div className="stat-value" style={{ color: '#4ade80' }}>{sigCount}</div>
        </div>
        <div className="stat-box" style={{ flex: 1 }}>
          <div className="stat-label">Rejected</div>
          <div className="stat-value" style={{ color: '#f87171' }}>{total - sigCount}</div>
        </div>
      </div>

      <table className="fdr-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Original p</th>
            <th>Corrected p</th>
            <th>Significant?</th>
          </tr>
        </thead>
        <tbody>
          {data.original_p_values.map((origP, i) => {
            const corrP = data.corrected_p_values[i]
            const sig = data.significant_after_correction[i]
            return (
              <tr key={i} className={sig ? 'sig-row' : 'nonsig-row'}>
                <td style={{ color: '#64748b' }}>{i + 1}</td>
                <td>{origP.toFixed(4)}</td>
                <td style={{ color: sig ? '#4ade80' : '#f87171' }}>{corrP.toFixed(4)}</td>
                <td>{sig ? '✓' : '✗'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="explanation">{data['Explanation of results']}</div>
    </div>
  )
}
