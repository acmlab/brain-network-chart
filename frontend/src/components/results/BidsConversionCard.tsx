import { useState, useRef } from 'react'
import type { BidsConversionResult } from '../../types'

interface Props {
  data: BidsConversionResult
  timestamp: string
}

export default function BidsConversionCard({ data, timestamp }: Props) {
  const [showLog, setShowLog] = useState(false)
  const [showReport, setShowReport] = useState(false)
  const [showPostProc, setShowPostProc] = useState(false)
  const [copied, setCopied] = useState(false)
  const [processDir, setProcessDir] = useState('process_output')
  const [scFcDir, setScFcDir] = useState('sc_fc_output')
  const cmdRef = useRef<HTMLPreElement>(null)

  const postProcCmd = `bash process.sh ${data.output_dir} ${processDir} ${scFcDir}`

  const handleCopy = () => {
    navigator.clipboard.writeText(postProcCmd)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

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
      <div style={{ display: 'flex', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
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
        <button
          className="btn-secondary"
          style={{ fontSize: 12, padding: '4px 12px' }}
          onClick={() => setShowPostProc(p => !p)}
        >
          {showPostProc ? 'Collapse Post-processing' : 'Post-processing Command'}
        </button>
      </div>

      {/* Post-processing command panel */}
      {showPostProc && (
        <div style={{
          marginTop: 12, padding: 12, borderRadius: 6,
          background: '#0f1117', border: '1px solid #1e293b',
        }}>
          <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 8, fontWeight: 600 }}>
            Post-processing Command (process.sh)
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
            <label style={{ fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
              Process Dir:
              <input
                value={processDir}
                onChange={e => setProcessDir(e.target.value)}
                style={{
                  fontSize: 11, padding: '2px 6px', borderRadius: 4,
                  background: '#1e293b', border: '1px solid #334155',
                  color: '#e2e8f0', marginLeft: 4, width: 160,
                }}
              />
            </label>
            <label style={{ fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center', gap: 4 }}>
              SC-FC Dir:
              <input
                value={scFcDir}
                onChange={e => setScFcDir(e.target.value)}
                style={{
                  fontSize: 11, padding: '2px 6px', borderRadius: 4,
                  background: '#1e293b', border: '1px solid #334155',
                  color: '#e2e8f0', marginLeft: 4, width: 160,
                }}
              />
            </label>
          </div>
          <pre ref={cmdRef} style={{
            padding: '8px 10px', borderRadius: 4,
            background: '#0a0d14', color: '#7dd3fc',
            fontSize: 11, lineHeight: 1.6, margin: 0,
            whiteSpace: 'pre-wrap', wordBreak: 'break-all',
          }}>
            {postProcCmd}
          </pre>
          <button
            onClick={handleCopy}
            style={{
              marginTop: 8, fontSize: 11, padding: '3px 10px',
              borderRadius: 4, border: '1px solid #334155',
              background: copied ? '#14532d' : '#1e293b',
              color: copied ? '#4ade80' : '#94a3b8',
              cursor: 'pointer',
            }}
          >
            {copied ? '✓ Copied' : 'Copy'}
          </button>
        </div>
      )}

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
