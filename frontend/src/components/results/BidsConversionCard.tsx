import { useState } from 'react'
import type { BidsConversionResult } from '../../types'

interface Props {
  data: BidsConversionResult
  timestamp: string
}

export default function BidsConversionCard({ data, timestamp }: Props) {
  const [showLog, setShowLog] = useState(false)
  const [showReport, setShowReport] = useState(false)

  const success = data.n_errors === 0
  const statusColor = success ? '#4ade80' : '#f87171'
  const statusBg = success ? '#14532d' : '#450a0a'

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">DICOM → BIDS Conversion</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      {/* Status badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{
          padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
          background: statusBg, color: statusColor,
        }}>
          {success ? '✓ BIDS Valid' : `✗ ${data.n_errors} Errors`}
        </span>
        {data.n_warnings > 0 && (
          <span style={{
            padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
            background: '#422006', color: '#fbbf24',
          }}>
            {data.n_warnings} Warnings
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#64748b' }}>
          {data.elapsed_seconds}s
        </span>
      </div>

      {/* Stats grid */}
      <div className="stat-grid">
        <div className="stat-box">
          <div className="stat-label">NIfTI files</div>
          <div className="stat-value">{data.n_nii}</div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Errors</div>
          <div className="stat-value" style={{ color: data.n_errors > 0 ? '#f87171' : '#4ade80' }}>
            {data.n_errors}
          </div>
        </div>
        <div className="stat-box">
          <div className="stat-label">Warnings</div>
          <div className="stat-value" style={{ color: data.n_warnings > 0 ? '#fbbf24' : '#64748b' }}>
            {data.n_warnings}
          </div>
        </div>
      </div>

      {/* Paths */}
      <div style={{ fontSize: 11, color: '#64748b', marginTop: 10 }}>
        <div style={{ marginBottom: 2 }}>
          <span style={{ color: '#94a3b8' }}>Input: </span>
          <span style={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{data.data_dir}</span>
        </div>
        <div>
          <span style={{ color: '#94a3b8' }}>Output: </span>
          <span style={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>{data.output_dir}</span>
        </div>
      </div>

      {/* Progress steps */}
      {data.progress.length > 0 && (
        <div style={{ marginTop: 12 }}>
          {data.progress.map((p, i) => (
            <div key={i} style={{ display: 'flex', gap: 6, fontSize: 11, marginBottom: 3 }}>
              <span style={{ color: '#a5b4fc', minWidth: 36 }}>{p.step}</span>
              <span style={{ color: '#94a3b8' }}>{p.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
        {data.report_url && (
          <button
            className="btn-secondary"
            style={{ fontSize: 12, padding: '4px 12px' }}
            onClick={() => setShowReport(r => !r)}
          >
            {showReport ? 'Collapse Report' : 'View HTML Report'}
          </button>
        )}
        <button
          className="btn-secondary"
          style={{ fontSize: 12, padding: '4px 12px' }}
          onClick={() => setShowLog(l => !l)}
        >
          {showLog ? 'Collapse Log' : 'View Conversion Log'}
        </button>
      </div>

      {/* Embedded HTML report */}
      {showReport && data.report_url && (
        <div style={{ marginTop: 12, borderRadius: 6, overflow: 'hidden', border: '1px solid #1e293b' }}>
          <iframe
            src={data.report_url}
            style={{ width: '100%', height: 480, border: 'none', background: '#fff' }}
            title="BIDS Conversion Report"
          />
        </div>
      )}

      {/* Console log */}
      {showLog && (
        <pre style={{
          marginTop: 12, padding: 10, borderRadius: 6,
          background: '#0f1117', color: '#94a3b8',
          fontSize: 10.5, lineHeight: 1.6,
          overflowX: 'auto', maxHeight: 320, overflowY: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {data.console_output}
        </pre>
      )}
    </div>
  )
}
