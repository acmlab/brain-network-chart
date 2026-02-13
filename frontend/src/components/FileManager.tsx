import { useState, useEffect, useRef } from 'react'
import type { FileInfo } from '../types'
import { uploadFile, listFiles, deleteFile, parseCSV } from '../api'

interface CsvPreview {
  columns: string[]
  rows: string[][]
  total_rows: number
}

function CsvPreviewPanel({ filename }: { filename: string }) {
  const [preview, setPreview] = useState<CsvPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    setLoading(true); setError(''); setPreview(null)
    parseCSV(filename)
      .then(r => setPreview(r))
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [filename])

  if (loading) return <div style={{ padding: '8px 0', fontSize: 11, color: '#64748b' }}>Loading preview…</div>
  if (error) return <div style={{ padding: '8px 0', fontSize: 11, color: '#f87171' }}>{error}</div>
  if (!preview) return null

  return (
    <div style={{ marginTop: 8, background: '#0f1117', border: '1px solid #2d3250', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ padding: '5px 10px', background: '#13161f', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8' }}>Preview</span>
        <span style={{ fontSize: 10, color: '#4b5563' }}>{preview.total_rows} rows · {preview.columns.length} cols</span>
      </div>
      <div style={{ overflowX: 'auto', maxHeight: 180 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
          <thead>
            <tr>
              {preview.columns.map(col => (
                <th key={col} style={{
                  padding: '4px 8px', textAlign: 'left', color: '#a5b4fc',
                  borderBottom: '1px solid #2d3250', whiteSpace: 'nowrap',
                  background: '#13161f', fontWeight: 600, position: 'sticky', top: 0,
                }}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.rows.map((row, i) => (
              <tr key={i}>
                {row.map((cell, j) => (
                  <td key={j} style={{
                    padding: '3px 8px', color: '#94a3b8',
                    borderBottom: '1px solid #1e2235', whiteSpace: 'nowrap',
                    maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis',
                  }}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function FileManager() {
  const [files, setFiles] = useState<FileInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [expandedFile, setExpandedFile] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    try {
      const res = await listFiles()
      setFiles(res.files)
    } catch {
      setFiles([])
    }
  }

  useEffect(() => { refresh() }, [])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setError('')
    try {
      await uploadFile(file)
      await refresh()
    } catch (e) {
      setError(String(e))
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  async function handleDelete(filename: string) {
    try {
      await deleteFile(filename)
      if (expandedFile === filename) setExpandedFile(null)
      await refresh()
    } catch (e) {
      setError(String(e))
    }
  }

  function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  function isCsv(filename: string) {
    return /\.(csv|tsv|txt)$/i.test(filename)
  }

  return (
    <div className="section">
      <div className="section-title">File Manager</div>

      <div className="upload-area" onClick={() => inputRef.current?.click()}>
        <input ref={inputRef} type="file" accept=".csv,.json" onChange={handleUpload} />
        <div style={{ color: '#a5b4fc', fontSize: 13 }}>
          {uploading ? 'Uploading...' : 'Click to upload CSV / JSON'}
        </div>
        <div className="upload-hint">Files are stored on the server for analysis</div>
      </div>

      {error && <div className="error-msg">{error}</div>}

      {files.length > 0 ? (
        <ul className="file-list" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {files.map(f => (
            <li key={f.filename}>
              <div className="file-item">
                <span
                  className="file-name"
                  title={f.filename}
                  style={{ cursor: isCsv(f.filename) ? 'pointer' : 'default', color: isCsv(f.filename) ? '#a5b4fc' : undefined }}
                  onClick={() => isCsv(f.filename) && setExpandedFile(expandedFile === f.filename ? null : f.filename)}
                >
                  {isCsv(f.filename) && (
                    <span style={{ fontSize: 9, marginRight: 4, color: '#7c3aed' }}>
                      {expandedFile === f.filename ? '▼' : '▶'}
                    </span>
                  )}
                  {f.filename}
                </span>
                <span className="file-size">{formatSize(f.size)}</span>
                <button className="btn btn-danger" onClick={() => handleDelete(f.filename)}>
                  Delete
                </button>
              </div>
              {expandedFile === f.filename && isCsv(f.filename) && (
                <CsvPreviewPanel filename={f.filename} />
              )}
            </li>
          ))}
        </ul>
      ) : (
        <div style={{ fontSize: 12, color: '#4b5563' }}>No files uploaded yet.</div>
      )}
    </div>
  )
}
