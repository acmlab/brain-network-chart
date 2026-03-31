import { useState, useEffect } from 'react'
import type { ResultItem, FileInfo } from '../types'
import { runCorrelation, runGroupComparison, applyFDRCorrection, detectOutliers, runCFCWaveletAnalysis, runHubDetection, getGrowthCurve, runNormativeAnalysis, listFiles, visualizeBoldAdj, } from '../api'
import { LOCAL_AGENT_URL } from '../constants'

const PHENOTYPES = [
  'Global mean of FC',
  'Global system segregation',
  'Visual system segregation (VIS)',
  'Somatomotor system segregation (SM)',
  'Dorsal attention system segregation (DA)',
  'Ventral attention system segregation (VA)',
  'Limbic system segregation (LIM)',
  'Frontoparietal system segregation (FP)',
  'Default mode system segregation (DM)',
]

function useUploadedFiles() {
  const [files, setFiles] = useState<FileInfo[]>([])
  useEffect(() => {
    listFiles().then(r => setFiles(r.files)).catch(() => {})
  }, [])
  return files
}

function usePhenotypes() {
  const [phenotypes, setPhenotypes] = useState<string[]>(PHENOTYPES)
  useEffect(() => {
    fetch('/get_phenotypes').then(r => r.json()).then(d => {
      if (d.phenotypes?.length) setPhenotypes(d.phenotypes)
    }).catch(() => {})
  }, [])
  return phenotypes
}

interface Props {
  onResult: (item: ResultItem) => void
}

function uid() { return Math.random().toString(36).slice(2) }
function timestamp() { return new Date().toLocaleTimeString() }

// ── Correlation ──────────────────────────────────────────────
function CorrelationForm({ onResult }: Props) {
  const [dataSource, setDataSource] = useState('mock_stats_data.csv')
  const [var1, setVar1] = useState('age')
  const [var2, setVar2] = useState('connectivity')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await runCorrelation(dataSource, var1, var2)
      onResult({ id: uid(), type: 'correlation', timestamp: timestamp(), data })
    } catch (e) {
      setError(String(e))
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">Run Correlation</div>
      <div className="form-row">
        <label className="form-label">Data Source (uploaded filename or JSON)</label>
        <input className="form-input" value={dataSource} onChange={e => setDataSource(e.target.value)} required placeholder="mock_stats_data.csv" />
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Variable 1</label>
          <input className="form-input" value={var1} onChange={e => setVar1(e.target.value)} required placeholder="age" />
        </div>
        <div>
          <label className="form-label">Variable 2</label>
          <input className="form-input" value={var2} onChange={e => setVar2(e.target.value)} required placeholder="connectivity" />
        </div>
      </div>
      <div className="example-hint">
        Example: <code>mock_stats_data.csv</code> · var1: <code>age</code> · var2: <code>connectivity</code>
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading}>
        {loading ? 'Running...' : 'Run Correlation'}
      </button>
    </form>
  )
}

// ── Group Comparison ─────────────────────────────────────────
function GroupComparisonForm({ onResult }: Props) {
  const [dataSource, setDataSource] = useState('mock_stats_data.csv')
  const [groupCol, setGroupCol] = useState('group')
  const [metricCol, setMetricCol] = useState('connectivity')
  const [groupA, setGroupA] = useState('Patient')
  const [groupB, setGroupB] = useState('Control')
  const [method, setMethod] = useState('ttest')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await runGroupComparison(dataSource, groupCol, metricCol, groupA, groupB, method)
      onResult({ id: uid(), type: 'group_comparison', timestamp: timestamp(), data })
    } catch (e) {
      setError(String(e))
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">Run Group Comparison</div>
      <div className="form-row">
        <label className="form-label">Data Source</label>
        <input className="form-input" value={dataSource} onChange={e => setDataSource(e.target.value)} required placeholder="mock_stats_data.csv" />
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Group Column</label>
          <input className="form-input" value={groupCol} onChange={e => setGroupCol(e.target.value)} required placeholder="group" />
        </div>
        <div>
          <label className="form-label">Metric Column</label>
          <input className="form-input" value={metricCol} onChange={e => setMetricCol(e.target.value)} required placeholder="connectivity" />
        </div>
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Group A</label>
          <input className="form-input" value={groupA} onChange={e => setGroupA(e.target.value)} required placeholder="Patient" />
        </div>
        <div>
          <label className="form-label">Group B</label>
          <input className="form-input" value={groupB} onChange={e => setGroupB(e.target.value)} required placeholder="Control" />
        </div>
      </div>
      <div className="form-row">
        <label className="form-label">Method</label>
        <select className="form-select" value={method} onChange={e => setMethod(e.target.value)}>
          <option value="ttest">T-Test (parametric)</option>
          <option value="mannwhitney">Mann-Whitney (non-parametric)</option>
        </select>
      </div>
      <div className="example-hint">
        Example: <code>mock_stats_data.csv</code> · group col: <code>group</code> · metric: <code>connectivity</code> · A: <code>Patient</code> · B: <code>Control</code>
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading}>
        {loading ? 'Running...' : 'Run Comparison'}
      </button>
    </form>
  )
}

// ── FDR Correction ───────────────────────────────────────────
function FDRForm({ onResult }: Props) {
  const [pValuesStr, setPValuesStr] = useState('0.001, 0.04, 0.05, 0.10, 0.50, 0.90')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const p_values = pValuesStr.split(/[,\s]+/).map(Number).filter(n => !isNaN(n))
      if (p_values.length === 0) throw new Error('No valid p-values entered')
      const data = await applyFDRCorrection(p_values)
      onResult({ id: uid(), type: 'fdr_correction', timestamp: timestamp(), data })
    } catch (e) {
      setError(String(e))
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">Apply FDR Correction</div>
      <div className="form-row">
        <label className="form-label">P-Values (comma or space separated)</label>
        <input
          className="form-input"
          value={pValuesStr}
          onChange={e => setPValuesStr(e.target.value)}
          required
          placeholder="0.001, 0.04, 0.05, 0.10, 0.90"
        />
      </div>
      <div className="example-hint">
        Enter raw p-values from multiple tests. FDR correction prevents false positives.
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading}>
        {loading ? 'Running...' : 'Apply FDR Correction'}
      </button>
    </form>
  )
}

// ── Outlier Detection ────────────────────────────────────────
function OutlierForm({ onResult }: Props) {
  const [dataSource, setDataSource] = useState('mock_stats_data.csv')
  const [column, setColumn] = useState('score')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await detectOutliers(dataSource, column)
      onResult({ id: uid(), type: 'outliers', timestamp: timestamp(), data })
    } catch (e) {
      setError(String(e))
    } finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">Detect Outliers</div>
      <div className="form-row">
        <label className="form-label">Data Source</label>
        <input className="form-input" value={dataSource} onChange={e => setDataSource(e.target.value)} required placeholder="mock_stats_data.csv" />
      </div>
      <div className="form-row">
        <label className="form-label">Column</label>
        <input className="form-input" value={column} onChange={e => setColumn(e.target.value)} required placeholder="score" />
      </div>
      <div className="example-hint">
        Example: <code>mock_stats_data.csv</code> · column: <code>score</code> (contains 1 outlier at S039)
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading}>
        {loading ? 'Running...' : 'Detect Outliers'}
      </button>
    </form>
  )
}

// ── CFC Wavelet Analysis ─────────────────────────────────────
function CFCWaveletForm({ onResult }: Props) {
  const files = useUploadedFiles()
  const [dataPath, setDataPath] = useState('')
  const [windowSize, setWindowSize] = useState(100)
  const [stepSize, setStepSize] = useState(90)
  const [padding, setPadding] = useState(true)
  const [ratio, setRatio] = useState(0.8)
  const [waveletsNum, setWaveletsNum] = useState(10)
  const [beta, setBeta] = useState(1.0)
  const [gamma, setGamma] = useState(0.005)
  const [maxIter, setMaxIter] = useState(100)
  const [nodeSelect, setNodeSelect] = useState(10)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await runCFCWaveletAnalysis({
        data_path: dataPath, window_size: windowSize, step_size: stepSize,
        padding, ratio, wavelets_num: waveletsNum, beta, gamma,
        max_iter: maxIter, node_select: nodeSelect,
      })
      onResult({ id: uid(), type: 'cfc_wavelet', timestamp: timestamp(), data })
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">CFC Wavelet Analysis</div>
      <div className="form-row">
        <label className="form-label">Data File or Folder</label>
        <select className="form-select" value={dataPath} onChange={e => setDataPath(e.target.value)} required>
          <option value="">Select uploaded file or folder…</option>
          {files.map(f => <option key={f.filename} value={f.filename}>{f.is_dir ? `📁 ${f.filename}` : f.filename}</option>)}
        </select>
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Window Size</label>
          <input className="form-input" type="number" value={windowSize} onChange={e => setWindowSize(Number(e.target.value))} min={10} />
        </div>
        <div>
          <label className="form-label">Step Size</label>
          <input className="form-input" type="number" value={stepSize} onChange={e => setStepSize(Number(e.target.value))} min={1} />
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', paddingBottom: 2 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#94a3b8', cursor: 'pointer' }}>
            <input type="checkbox" checked={padding} onChange={e => setPadding(e.target.checked)} />
            Padding
          </label>
        </div>
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Ratio</label>
          <input className="form-input" type="number" step="0.01" value={ratio} onChange={e => setRatio(Number(e.target.value))} min={0} max={1} />
        </div>
        <div>
          <label className="form-label">Wavelets Num</label>
          <input className="form-input" type="number" value={waveletsNum} onChange={e => setWaveletsNum(Number(e.target.value))} min={1} />
        </div>
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Beta</label>
          <input className="form-input" type="number" step="0.1" value={beta} onChange={e => setBeta(Number(e.target.value))} />
        </div>
        <div>
          <label className="form-label">Gamma</label>
          <input className="form-input" type="number" step="0.001" value={gamma} onChange={e => setGamma(Number(e.target.value))} />
        </div>
        <div>
          <label className="form-label">Max Iter</label>
          <input className="form-input" type="number" value={maxIter} onChange={e => setMaxIter(Number(e.target.value))} min={1} />
        </div>
      </div>
      <div className="form-row">
        <label className="form-label">Node Select</label>
        <input className="form-input" type="number" value={nodeSelect} onChange={e => setNodeSelect(Number(e.target.value))} min={1} />
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading || !dataPath}>
        {loading ? 'Running…' : 'Run CFC Analysis'}
      </button>
    </form>
  )
}

// ── Hub Detection ─────────────────────────────────────────────
function HubDetectionForm({ onResult }: Props) {
  const files = useUploadedFiles()
  const [dataPath, setDataPath] = useState('')
  const [ratio, setRatio] = useState(0.8)
  const [k, setK] = useState(2)
  const [hubNum, setHubNum] = useState(10)
  const [useGroup, setUseGroup] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await runHubDetection({
        data_path: dataPath, ratio, k, hub_num: hubNum, use_group: useGroup,
      })
      onResult({ id: uid(), type: 'hub_detection', timestamp: timestamp(), data })
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">Hub Detection</div>
      <div className="form-row">
        <label className="form-label">Data File or Folder</label>
        <select className="form-select" value={dataPath} onChange={e => setDataPath(e.target.value)} required>
          <option value="">Select uploaded file or folder…</option>
          {files.map(f => <option key={f.filename} value={f.filename}>{f.is_dir ? `📁 ${f.filename}` : f.filename}</option>)}
        </select>
      </div>
      <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
        <div>
          <label className="form-label">Ratio</label>
          <input className="form-input" type="number" step="0.01" value={ratio} onChange={e => setRatio(Number(e.target.value))} min={0} max={1} />
        </div>
        <div>
          <label className="form-label">k</label>
          <input className="form-input" type="number" value={k} onChange={e => setK(Number(e.target.value))} min={1} />
        </div>
        <div>
          <label className="form-label">Hub Num</label>
          <input className="form-input" type="number" value={hubNum} onChange={e => setHubNum(Number(e.target.value))} min={1} />
        </div>
      </div>
      <div className="form-row">
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#94a3b8', cursor: 'pointer' }}>
          <input type="checkbox" checked={useGroup} onChange={e => setUseGroup(e.target.checked)} />
          Use group mode
        </label>
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading || !dataPath}>
        {loading ? 'Running…' : 'Run Hub Detection'}
      </button>
    </form>
  )
}

// ── BrainChart (Growth Curve + Overlay) ──────────────────────
function BrainChartForm({ onResult }: Props) {
  const files = useUploadedFiles()
  const phenotypes = usePhenotypes()
  const [phenotype, setPhenotype] = useState(PHENOTYPES[0])
  const [overlayFile, setOverlayFile] = useState('')
  const [ageCol, setAgeCol] = useState('')
  const [valCol, setValCol] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      if (overlayFile && ageCol && valCol) {
        const resp = await runNormativeAnalysis({
          x_phenotype: phenotype, y_path: overlayFile, age_col: ageCol, val_col: valCol,
        })
        const { age, values, ...curveData } = resp.data
        onResult({
          id: uid(), type: 'growth_curve', timestamp: timestamp(),
          data: {
            status: resp.status,
            phenotype: resp.phenotype,
            elapsed_seconds: resp.elapsed_seconds,
            data: curveData,
            overlay: { age, values },
          },
        })
      } else {
        const curveResp = await getGrowthCurve(phenotype)
        onResult({
          id: uid(), type: 'growth_curve', timestamp: timestamp(),
          data: { ...curveResp },
        })
      }
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">BrainChart Growth Curve</div>
      <div className="form-row">
        <label className="form-label">Phenotype</label>
        <select className="form-select" value={phenotype} onChange={e => setPhenotype(e.target.value)}>
          {phenotypes.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>
      <div className="form-row">
        <label className="form-label">Overlay File (optional)</label>
        <select className="form-select" value={overlayFile} onChange={e => setOverlayFile(e.target.value)}>
          <option value="">None (curve only)</option>
          {files.map(f => <option key={f.filename} value={f.filename}>{f.filename}</option>)}
        </select>
      </div>
      {overlayFile && (
        <div className="form-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <div>
            <label className="form-label">Age Column</label>
            <input className="form-input" value={ageCol} onChange={e => setAgeCol(e.target.value)} placeholder="age" />
          </div>
          <div>
            <label className="form-label">Value Column</label>
            <input className="form-input" value={valCol} onChange={e => setValCol(e.target.value)} placeholder="fc_value" />
          </div>
        </div>
      )}
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading}>
        {loading ? 'Loading…' : 'Run BrainChart'}
      </button>
    </form>
  )
}

// ── Adj Visualization ─────────────────────────────────────────
function BoldAdjForm({ onResult }: Props) {
  const files = useUploadedFiles()
  const [dataPath, setDataPath] = useState('')
  const [ratio, setRatio] = useState(0.8)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    try {
      const data = await visualizeBoldAdj(dataPath, ratio)
      onResult({ id: uid(), type: 'bold_adj', timestamp: timestamp(), data })
    } catch (e) { setError(String(e)) }
    finally { setLoading(false) }
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">Adj Visualization</div>
      <div className="form-row">
        <label className="form-label">Data File or Folder</label>
        <select className="form-select" value={dataPath} onChange={e => setDataPath(e.target.value)} required>
          <option value="">Select uploaded file or folder…</option>
          {files.map(f => (
            <option key={f.filename} value={f.filename}>{f.is_dir ? `📁 ${f.filename}` : f.filename}</option>
          ))}
        </select>
      </div>
      <div className="form-row">
        <label className="form-label">Ratio</label>
        <input className="form-input" type="number" step="0.01" value={ratio} onChange={e => setRatio(Number(e.target.value))} min={0} max={1} />
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit" disabled={loading || !dataPath}>
        {loading ? 'Loading…' : 'Visualize'}
      </button>
    </form>
  )
}

// ── BIDS Conversion ──────────────────────────────────────────

function BidsConversionForm({ onResult }: Props) {
  const [dataDir, setDataDir] = useState('')
  const [outputDir, setOutputDir] = useState('')
  const [runMode, setRunMode] = useState<'local' | 'server'>('local')
  const [localAgentOnline, setLocalAgentOnline] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const ctrl = new AbortController()
        const t = setTimeout(() => ctrl.abort(), 2000)
        const r = await fetch(`${LOCAL_AGENT_URL}/health`, { signal: ctrl.signal })
        clearTimeout(t)
        if (!cancelled) setLocalAgentOnline(r.ok)
      } catch {
        if (!cancelled) setLocalAgentOnline(false)
      }
    }
    check()
    const id = setInterval(check, 3000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true); setError('')
    const params = new URLSearchParams({ data_dir: dataDir, output_dir: outputDir })
    onResult({
      id: uid(), type: 'bids_conversion', timestamp: timestamp(),
      data: {
        status: 'pending', data_dir: dataDir, output_dir: outputDir,
        n_nii: 0, n_errors: 0, n_warnings: 0, elapsed_seconds: 0,
        console_output: '', progress: [], report_html: null, return_code: -1,
        pending: true, stream_url: `/run_bids_conversion_stream?${params}`,
        run_mode: runMode,
      },
      onComplete: () => setLoading(false),
    })
  }

  return (
    <form onSubmit={handleSubmit} className="section">
      <div className="section-title">DICOM → BIDS Conversion</div>
      <div className="form-row">
        <label className="form-label">DICOM Source Directory</label>
        <input className="form-input" value={dataDir} onChange={e => setDataDir(e.target.value)} required placeholder="/data/ADNI_raw" />
      </div>
      <div className="form-row">
        <label className="form-label">BIDS Output Directory</label>
        <input className="form-input" value={outputDir} onChange={e => setOutputDir(e.target.value)} required placeholder="/data/bids_output" />
      </div>
      <div className="form-row">
        <label className="form-label">Run on</label>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', marginTop: 4 }}>
          {(['local', 'server'] as const).map(m => (
            <label key={m} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer', color: '#94a3b8' }}>
              <input
                type="radio"
                name="run_mode"
                value={m}
                checked={runMode === m}
                onChange={() => setRunMode(m)}
                style={{ accentColor: '#818cf8' }}
              />
              {m === 'local' ? 'Local agent' : 'Server'}
              {m === 'local' && (
                <span style={{
                  display: 'inline-block', width: 7, height: 7, borderRadius: '50%', marginLeft: 2,
                  background: localAgentOnline ? '#4ade80' : '#ef4444',
                }} title={localAgentOnline ? 'Online' : 'Offline'} />
              )}
            </label>
          ))}
        </div>
      </div>
      {error && <div className="error-msg">{error}</div>}
      <button className="btn btn-primary" type="submit"
        disabled={loading || !dataDir || !outputDir || (runMode === 'local' && !localAgentOnline)}>
        {loading ? 'Converting (may take several minutes)…'
          : (runMode === 'local' && !localAgentOnline) ? 'Local agent offline'
          : 'Start Conversion'}
      </button>
    </form>
  )
}

export default function StatsFormPanel({ onResult }: Props) {
  return (
    <>
      <BidsConversionForm onResult={onResult} />
      <BrainChartForm onResult={onResult} />
      <CFCWaveletForm onResult={onResult} />
      <HubDetectionForm onResult={onResult} />
      <BoldAdjForm onResult={onResult} />
      <CorrelationForm onResult={onResult} />
      <GroupComparisonForm onResult={onResult} />
      <FDRForm onResult={onResult} />
      <OutlierForm onResult={onResult} />
    </>
  )
}
