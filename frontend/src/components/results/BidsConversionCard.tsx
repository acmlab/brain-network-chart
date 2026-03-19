import { useState, useEffect, useRef } from 'react'
import type { BidsConversionResult } from '../../types'

interface Props {
  data: BidsConversionResult
  timestamp: string
  onComplete?: () => void
}

interface Step {
  label: string
  note: string
  cmd: string
}

const inputStyle: React.CSSProperties = {
  fontSize: 11, padding: '2px 6px', borderRadius: 4,
  background: '#1e293b', border: '1px solid #334155',
  color: '#e2e8f0', marginLeft: 4, width: 180,
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button onClick={handleCopy} style={{
      fontSize: 10, padding: '1px 8px', borderRadius: 4,
      border: '1px solid #334155',
      background: copied ? '#14532d' : '#1e293b',
      color: copied ? '#4ade80' : '#64748b',
      cursor: 'pointer', flexShrink: 0,
    }}>
      {copied ? '✓' : 'Copy'}
    </button>
  )
}

export default function BidsConversionCard({ data, timestamp, onComplete }: Props) {
  const [showLog, setShowLog] = useState(false)
  const [showPostProc, setShowPostProc] = useState(false)
  const [userTag, setUserTag] = useState('taowen')
  const [pathScript, setPathScript] = useState('/nas/longleaf/home/taowen/data')
  const [processDir, setProcessDir] = useState('process_output')
  const [scFcDir, setScFcDir] = useState('sc_fc_output')
  const [liveLog, setLiveLog] = useState('')
  const [finalData, setFinalData] = useState<BidsConversionResult | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!data.pending || !data.stream_url) return
    const es = new EventSource(data.stream_url)
    es.onmessage = (e) => {
      setLiveLog(prev => prev + e.data + '\n')
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    es.addEventListener('done', (e) => {
      setFinalData(JSON.parse((e as MessageEvent).data))
      es.close()
      onComplete?.()
    })
    return () => es.close()
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const d = finalData ?? data
  const isPending = data.pending && !finalData

  const B = d.output_dir
  const P = processDir
  const S = scFcDir
  const U = userTag
  const PS = pathScript

  const steps: Step[] = [
    {
      label: 'Setup',
      note: 'Create output directories',
      cmd: [
        `mkdir -p ${P}/abcd_monitor/${U}`,
        `mkdir -p ${P}/abcd_monitor_fc1/${U}`,
        `mkdir -p ${P}/abcd_monitor_fc2/${U}`,
        `mkdir -p ${P}/abcd_monitor_dwi/${U}`,
      ].join('\n'),
    },
    {
      label: 'Step 1',
      note: 'fMRIPrep (start from subject index 0)',
      cmd: `cd ${PS} && ./abcd-fmri_tdan ${U} 0 ${B} ${P}`,
    },
    {
      label: 'Step 2',
      note: 'XCP-D',
      cmd: `cd ${PS} && ./abcd-fc1-tdan ${U} ${P}`,
    },
    {
      label: 'Step 3',
      note: 'Extract FC matrix',
      cmd: `cd ${PS} && ./abcd-fc2-tdan ${U} ${P}`,
    },
    {
      label: 'Step 4',
      note: 'QSIPrep DWI',
      cmd: `cd ${PS} && ./abcd-dwi_tdan ${U} ${P}`,
    },
    {
      label: 'Step 5',
      note: 'Aggregate FC files',
      cmd: `cd ${PS} && python3 FC_exact.py --bids_dir ${B} --sc_fc_dir ${S}`,
    },
    {
      label: 'Step 6',
      note: 'Check SC .mat files',
      cmd: `cd ${PS} && python3 check_sc.py --process_dir ${P} --user ${U} --sc_fc_dir ${S}`,
    },
  ]

  return (
    <div className="result-card">
      <div className="result-card-header">
        <span className="result-card-title">DICOM → BIDS Conversion</span>
        <span className="result-card-time">{timestamp}</span>
      </div>

      {/* Live log while running */}
      {isPending && (
        <pre style={{
          marginTop: 8, padding: 10, borderRadius: 6,
          background: '#0f1117', color: '#94a3b8',
          fontSize: 10.5, lineHeight: 1.6,
          maxHeight: 400, overflowY: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {liveLog || 'Starting...'}
          <div ref={logEndRef} />
        </pre>
      )}

      {/* Inline HTML report when done */}
      {!isPending && (d.report_html
        ? (
          <div style={{ marginTop: 8, borderRadius: 6, overflow: 'hidden', border: '1px solid #1e293b' }}>
            <iframe
              srcDoc={d.report_html}
              style={{ width: '100%', height: 560, border: 'none', background: '#fff' }}
              title="BIDS Conversion Report"
            />
          </div>
        ) : (
          <p style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>Report not available.</p>
        )
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
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

      {/* Console log */}
      {showLog && (
        <pre style={{
          marginTop: 12, padding: 10, borderRadius: 6,
          background: '#0f1117', color: '#94a3b8',
          fontSize: 10.5, lineHeight: 1.6,
          overflowX: 'auto', maxHeight: 320, overflowY: 'auto',
          whiteSpace: 'pre-wrap', wordBreak: 'break-word',
        }}>
          {d.console_output || liveLog}
        </pre>
      )}

      {/* Post-processing panel */}
      {showPostProc && (
        <div style={{
          marginTop: 12, padding: 12, borderRadius: 6,
          background: '#0f1117', border: '1px solid #1e293b',
        }}>
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 10, fontWeight: 600 }}>
            Post-processing Command (process.sh)
          </div>

          {/* Variable inputs */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
            {[
              { label: 'BIDS Dir', value: B, disabled: true, onChange: undefined },
              { label: 'User Tag', value: userTag, disabled: false, onChange: setUserTag },
              { label: 'Script Dir', value: pathScript, disabled: false, onChange: setPathScript },
              { label: 'Process Dir', value: processDir, disabled: false, onChange: setProcessDir },
              { label: 'SC-FC Dir', value: scFcDir, disabled: false, onChange: setScFcDir },
            ].map(({ label, value, disabled, onChange }) => (
              <label key={label} style={{ fontSize: 11, color: '#64748b', display: 'flex', alignItems: 'center' }}>
                {label}:
                <input
                  value={value}
                  disabled={disabled}
                  onChange={e => onChange?.(e.target.value)}
                  style={{ ...inputStyle, opacity: disabled ? 0.5 : 1, width: label === 'BIDS Dir' || label === 'Script Dir' ? 260 : 160 }}
                />
              </label>
            ))}
          </div>

          {/* Steps */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {steps.map((s) => (
              <div key={s.label} style={{
                borderRadius: 4, border: '1px solid #1e293b', overflow: 'hidden',
              }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '4px 10px', background: '#151b27',
                }}>
                  <span style={{
                    fontSize: 10, fontWeight: 700, color: '#a5b4fc',
                    minWidth: 44, textTransform: 'uppercase', letterSpacing: '0.05em',
                  }}>
                    {s.label}
                  </span>
                  <span style={{ fontSize: 11, color: '#64748b', flex: 1 }}>{s.note}</span>
                  <CopyButton text={s.cmd} />
                </div>
                <pre style={{
                  margin: 0, padding: '6px 10px',
                  background: '#0a0d14', color: '#7dd3fc',
                  fontSize: 11, lineHeight: 1.6,
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                }}>
                  {s.cmd}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
