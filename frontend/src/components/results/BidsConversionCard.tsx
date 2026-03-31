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

interface RunningJob {
  stepLabel: string
  jobId: string
  es: EventSource
}

import { LOCAL_AGENT_URL as AGENT_URL } from '../../constants'

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
  const [pipelineDir, setPipelineDir] = useState('/ram/USERS/tao/code/new/bids')
  const [processDir, setProcessDir] = useState('process_output')
  const [scFcDir, setScFcDir] = useState('sc_fc_output')
  const [liveLog, setLiveLog] = useState('')
  const [finalData, setFinalData] = useState<BidsConversionResult | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  // Local agent state
  const [postProcMode, setPostProcMode] = useState<'local' | 'server'>('local')
  const [localAgentOnline, setLocalAgentOnline] = useState(false)
  const [runningJob, setRunningJob] = useState<RunningJob | null>(null)
  const [stepOutputs, setStepOutputs] = useState<Record<string, string[]>>({})
  const [expandedStep, setExpandedStep] = useState<string | null>(null)
  const [stepExitCodes, setStepExitCodes] = useState<Record<string, number>>({})
  const terminalEndRef = useRef<HTMLDivElement>(null)

  // BIDS conversion streaming — local agent first, fall back to server SSE
  useEffect(() => {
    if (!data.pending) return
    let cancelled = false
    let es: EventSource | null = null

    async function start() {
      const runMode = data.run_mode ?? 'local'

      // Try local agent
      if (runMode === 'local') {
        try {
          const ctrl = new AbortController()
          const t = setTimeout(() => ctrl.abort(), 2000)
          const hr = await fetch(`${AGENT_URL}/health`, { signal: ctrl.signal })
          clearTimeout(t)
          if (hr.ok && !cancelled) {
            const infoRes = await fetch(`${AGENT_URL}/info`)
            if (!infoRes.ok) throw new Error('agent /info not available')
            const info = await infoRes.json()
            if (!info.dir) throw new Error('agent /info missing dir')
            const scriptPath = `${info.dir}/dicom2bids_agent.py`
            const runRes = await fetch(`${AGENT_URL}/run`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                cmd: `"${info.python ?? 'python3'}" -u "${scriptPath}" "${data.data_dir}" "${data.output_dir}"`,
                cwd: info.dir,
              }),
            })
            const { job_id } = await runRes.json()
            if (cancelled) return
            es = new EventSource(`${AGENT_URL}/stream/${job_id}`)
            let doneReceived = false
            es.onmessage = (e) => {
              if (cancelled) return
              setLiveLog(prev => prev + e.data + '\n')
              logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
            }
            es.addEventListener('done', async (e) => {
              doneReceived = true
              es?.close()
              if (cancelled) return
              const { exit_code } = JSON.parse((e as MessageEvent).data)
              let report_html: string | null = null
              try {
                const rr = await fetch(
                  `${AGENT_URL}/read_file?path=${encodeURIComponent(data.output_dir + '/conversion_report.html')}`
                )
                if (rr.ok) report_html = await rr.text()
              } catch { /* report optional */ }
              const result = { ...data, pending: false, report_html, return_code: exit_code, status: exit_code === 0 ? 'success' : 'error' }
              setFinalData(result)
              if (!report_html) setShowLog(true)
              onComplete?.()
            })
            es.onerror = () => {
              if (doneReceived) return  // onerror after done = reconnect attempt, ignore
              es?.close()
              if (!cancelled) {
                setFinalData({ ...data, pending: false, return_code: -1, status: 'error', report_html: null })
                onComplete?.()
              }
            }
            return  // handled by local agent
          }
        } catch { /* local agent unavailable, fall through */ }
      }

      // Server SSE
      if (runMode === 'local') return  // local-only: stop if agent unavailable
      if (!data.stream_url || cancelled) return
      es = new EventSource(data.stream_url)
      let serverDone = false
      es.onmessage = (e) => {
        if (cancelled) return
        setLiveLog(prev => prev + e.data + '\n')
        logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
      }
      es.addEventListener('done', (e) => {
        serverDone = true
        es?.close()
        if (!cancelled) {
          const result = JSON.parse((e as MessageEvent).data)
          setFinalData(result)
          if (!result.report_html) setShowLog(true)
          onComplete?.()
        }
      })
      es.onerror = () => {
        if (serverDone) return
        es?.close()
      }
    }

    start()
    return () => { cancelled = true; es?.close() }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Local agent health polling
  useEffect(() => {
    let cancelled = false
    async function checkHealth() {
      try {
        const controller = new AbortController()
        const timer = setTimeout(() => controller.abort(), 2000)
        const r = await fetch(`${AGENT_URL}/health`, { signal: controller.signal })
        clearTimeout(timer)
        if (!cancelled) setLocalAgentOnline(r.ok)
      } catch {
        if (!cancelled) setLocalAgentOnline(false)
      }
    }
    checkHealth()
    const id = setInterval(checkHealth, 3000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => { runningJob?.es.close() }
  }, [runningJob])

  const d = finalData ?? data
  const isPending = data.pending && !finalData

  const B = d.output_dir
  const P = processDir
  const S = scFcDir
  const PS = pipelineDir

  const steps: Step[] = [
    {
      label: 'Install',
      note: 'Download container images (~24 GB, one-time)',
      cmd: `cd "${PS}" && bash install.sh`,
    },
    {
      label: 'Validate',
      note: 'Pre-flight checks (config, containers, tools)',
      cmd: `cd "${PS}" && bash validate.sh`,
    },
    {
      label: 'Pipeline',
      note: 'Run full pipeline (proc.sh)',
      cmd: `cd "${PS}" && bash proc.sh "${B}" "${P}" "${S}"`,
    },
  ]

  async function handleRun(step: Step) {
    if (runningJob) return
    if (postProcMode === 'local' && !localAgentOnline) return
    setStepOutputs(prev => ({ ...prev, [step.label]: [] }))
    setExpandedStep(step.label)

    const onLine = (line: string) => {
      setStepOutputs(prev => ({ ...prev, [step.label]: [...(prev[step.label] ?? []), line] }))
      setTimeout(() => terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 0)
    }
    const onDone = (exit_code: number) => {
      setStepExitCodes(prev => ({ ...prev, [step.label]: exit_code }))
      setRunningJob(null)
    }

    try {
      let es: EventSource
      if (postProcMode === 'local') {
        const resp = await fetch(`${AGENT_URL}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cmd: step.cmd, cwd: pipelineDir }),
        })
        if (!resp.ok) throw new Error(`Agent error ${resp.status}`)
        const { job_id } = await resp.json()
        es = new EventSource(`${AGENT_URL}/stream/${job_id}`)
        es.onmessage = (e) => onLine(e.data)
        es.addEventListener('done', (e) => {
          const { exit_code } = JSON.parse((e as MessageEvent).data)
          onDone(exit_code); es.close()
        })
        es.onerror = () => { onDone(-1); es.close() }
        setRunningJob({ stepLabel: step.label, jobId: job_id, es })
      } else {
        const params = new URLSearchParams({ cmd: step.cmd, cwd: d.output_dir ?? '' })
        es = new EventSource(`/run_command_stream?${params}`)
        es.onmessage = (e) => onLine(e.data)
        es.addEventListener('done', (e) => {
          const { exit_code } = JSON.parse((e as MessageEvent).data)
          onDone(exit_code); es.close()
        })
        es.onerror = () => { onDone(-1); es.close() }
        setRunningJob({ stepLabel: step.label, jobId: 'server', es })
      }
    } catch (err) {
      setStepOutputs(prev => ({ ...prev, [step.label]: [`[error] ${String(err)}`] }))
    }
  }

  async function handleCancel() {
    if (!runningJob) return
    try {
      await fetch(`${AGENT_URL}/cancel/${runningJob.jobId}`, { method: 'POST' })
    } catch { /* ignore */ }
    runningJob.es.close()
    setRunningJob(null)
  }

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
          <p style={{ fontSize: 12, color: '#ef4444', marginTop: 8 }}>
            Conversion failed (exit {d.return_code}) — see log below.
          </p>
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
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 10 }}>
            <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>
              Post-processing Command (process.sh)
            </span>
            <div style={{ display: 'flex', gap: 12 }}>
              {(['local', 'server'] as const).map(m => (
                <label key={m} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, cursor: 'pointer', color: '#64748b' }}>
                  <input
                    type="radio" name="postProcMode" value={m}
                    checked={postProcMode === m}
                    onChange={() => setPostProcMode(m)}
                    style={{ accentColor: '#818cf8' }}
                  />
                  {m === 'local' ? 'Local agent' : 'Server'}
                </label>
              ))}
            </div>
          </div>

          {/* Agent status (only relevant in local mode) */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <span style={{
              display: 'inline-block', width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
              background: localAgentOnline ? '#4ade80' : '#ef4444',
            }} />
            {localAgentOnline ? (
              <span style={{ fontSize: 11, color: '#4ade80' }}>Local agent connected</span>
            ) : (
              <span style={{ fontSize: 11, color: '#94a3b8' }}>
                Local agent offline &mdash; run:&nbsp;
                <code style={{
                  background: '#0a0d14', padding: '1px 6px', borderRadius: 3,
                  color: '#7dd3fc', fontSize: 11,
                }}>
                  python3 bids_local_agent.py
                </code>
              </span>
            )}
          </div>

          {/* Variable inputs */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
            {[
              { label: 'BIDS Dir', value: B, disabled: true, onChange: undefined },
              { label: 'Pipeline Dir', value: pipelineDir, disabled: false, onChange: setPipelineDir },
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
            {steps.map((s) => {
              const isRunningThis = runningJob?.stepLabel === s.label
              const isRunningOther = !!runningJob && !isRunningThis
              const outputs = stepOutputs[s.label] ?? []
              const exitCode = stepExitCodes[s.label]
              const hasExitCode = exitCode !== undefined
              const isExpanded = expandedStep === s.label

              return (
                <div key={s.label} style={{ borderRadius: 4, border: '1px solid #1e293b', overflow: 'hidden' }}>
                  {/* Header */}
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

                    {/* Exit code badge */}
                    {hasExitCode && (
                      <span style={{
                        fontSize: 10, padding: '1px 6px', borderRadius: 3,
                        background: exitCode === 0 ? '#14532d' : '#450a0a',
                        color: exitCode === 0 ? '#4ade80' : '#f87171',
                      }}>
                        {exitCode === 0 ? 'Done' : `Exit ${exitCode}`}
                      </span>
                    )}

                    <CopyButton text={s.cmd} />

                    {/* Run / Cancel */}
                    {isRunningThis ? (
                      <button onClick={handleCancel} style={{
                        fontSize: 10, padding: '1px 8px', borderRadius: 4,
                        border: '1px solid #7f1d1d', background: '#1e293b',
                        color: '#f87171', cursor: 'pointer', flexShrink: 0,
                      }}>
                        Cancel
                      </button>
                    ) : (
                      <button
                        onClick={() => handleRun(s)}
                        disabled={(postProcMode === 'local' && !localAgentOnline) || isRunningOther}
                        style={{
                          fontSize: 10, padding: '1px 8px', borderRadius: 4,
                          border: '1px solid #334155', background: '#1e293b',
                          color: ((postProcMode === 'local' && !localAgentOnline) || isRunningOther) ? '#334155' : '#a5b4fc',
                          cursor: ((postProcMode === 'local' && !localAgentOnline) || isRunningOther) ? 'not-allowed' : 'pointer',
                          flexShrink: 0,
                        }}
                      >
                        Run
                      </button>
                    )}

                    {/* Expand/collapse toggle */}
                    {outputs.length > 0 && (
                      <button
                        onClick={() => setExpandedStep(isExpanded ? null : s.label)}
                        style={{
                          fontSize: 10, padding: '1px 6px', borderRadius: 4,
                          border: '1px solid #334155', background: 'transparent',
                          color: '#64748b', cursor: 'pointer', flexShrink: 0,
                        }}
                      >
                        {isExpanded ? '▲' : '▼'}
                      </button>
                    )}
                  </div>

                  {/* Command */}
                  <pre style={{
                    margin: 0, padding: '6px 10px',
                    background: '#0a0d14', color: '#7dd3fc',
                    fontSize: 11, lineHeight: 1.6,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                  }}>
                    {s.cmd}
                  </pre>

                  {/* Terminal output */}
                  {isExpanded && outputs.length > 0 && (
                    <pre style={{
                      margin: 0, padding: '8px 10px',
                      background: '#050709', color: '#94a3b8',
                      fontSize: 10.5, lineHeight: 1.6,
                      maxHeight: 300, overflowY: 'auto',
                      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                      borderTop: '1px solid #1e293b',
                    }}>
                      {outputs.join('\n')}
                      {isRunningThis && <span style={{ color: '#4ade80' }}>█</span>}
                      <div ref={isRunningThis ? terminalEndRef : undefined} />
                    </pre>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
