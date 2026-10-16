import { useEffect, useRef, useState } from 'react'
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'
import RadioButtonUncheckedIcon from '@mui/icons-material/RadioButtonUncheckedOutlined'

// Second way to collect data: IFS Quick Report exports (xlsx / csv), one per data set, mapped by the report code in the
// file name (SUP01_..., CUS04_...). Works with the mapped workbook exported from this tool too.
export default function ReportImport({ entity, onLoaded, loaded }) {
  const [catalog, setCatalog] = useState([])
  const [files, setFiles] = useState([])
  const [assign, setAssign] = useState({}) // file name -> report code chosen by hand ('' = auto-detect)
  const [status, setStatus] = useState({ state: 'idle', error: '' })
  const [summary, setSummary] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => {
    fetch(`/api/catalog/${entity.id}`)
      .then((r) => r.json())
      .then((b) => setCatalog(b.reports || []))
      .catch(() => setCatalog([]))
  }, [entity.id])

  function addFiles(list) {
    const incoming = [...list]
    setFiles((prev) => [...prev.filter((p) => !incoming.some((n) => n.name === p.name)), ...incoming])
    setSummary(null)
  }

  async function load() {
    setStatus({ state: 'working', error: '' })
    try {
      const form = new FormData()
      files.forEach((f) => form.append('files', f, f.name))
      form.append('assignments', JSON.stringify(Object.fromEntries(Object.entries(assign).filter(([, v]) => v))))
      const res = await fetch(`/api/import/${entity.id}`, { method: 'POST', body: form })
      const body = await res.json().catch(() => null)
      if (!res.ok || !body?.success) throw new Error(body?.error || body?.detail?.[0]?.msg || `Import failed (${res.status}).`)
      setSummary(body.result)
      setStatus({ state: 'idle', error: '' })
      onLoaded(body.result)
    } catch (err) {
      setStatus({ state: 'error', error: err.message })
    }
  }

  const rowsByCode = Object.fromEntries((summary?.report || []).map((r) => [r.code, r.rows || 0]))
  const placed = Object.fromEntries((summary?.report || []).map((r) => [r.file, r]))
  const skipped = Object.fromEntries((summary?.unmatched || []).map((u) => [u.file, u.reason]))
  const name = entity.label.toLowerCase()

  return (
    <div className="panel">
      <div className="section-heading">
        <div><span className="eyebrow">QUICK REPORTS</span><h2>Import report files</h2></div>
      </div>
      <p className="muted" style={{ margin: '0 0 12px', fontSize: 13 }}>
        Run each {name} Quick Report in IFS, export it to Excel and add all the files here. Files are matched to a data set by the report
        code at the start of the name, or detected from their columns, and you can pick the report by hand. SQL for every report is in <code>ifs-quick-reports/</code>.
      </p>

      <div
        className="drop-zone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); addFiles(e.dataTransfer.files) }}
        onClick={() => inputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
      >
        <UploadFileOutlinedIcon />
        <span><strong>Drop report files here</strong> or click to choose (.xlsx, .csv)</span>
        <input ref={inputRef} type="file" multiple accept=".xlsx,.csv" hidden onChange={(e) => { addFiles(e.target.files); e.target.value = '' }} />
      </div>

      <ul className="report-list">
        {catalog.map((c) => {
          const matched = files.some((f) => f.name.toUpperCase().replace(/[\s-]/g, '_').startsWith(c.code)) || Object.values(assign).includes(c.code)
          const rows = rowsByCode[c.code]
          return (
            <li key={c.code} className={matched || rows !== undefined ? 'ok' : ''}>
              {matched || rows !== undefined ? <CheckCircleOutlineIcon fontSize="small" /> : <RadioButtonUncheckedIcon fontSize="small" />}
              <code>{c.name}</code>
              <span className="muted">{c.stage.split('/').join(' › ')}</span>
              {rows !== undefined && <small>{rows.toLocaleString()} rows</small>}
            </li>
          )
        })}
      </ul>

      {files.length > 0 && (
        <div className="file-list">
          {files.map((f) => {
            const hit = placed[f.name]
            const hitName = hit ? catalog.find((c) => c.code === hit.code)?.name : null
            return (
              <div key={f.name} className="file-row">
                <span className="file-name" title={f.name}>{f.name}</span>
                <select
                  value={assign[f.name] || ''}
                  onChange={(e) => { setAssign({ ...assign, [f.name]: e.target.value }); setSummary(null) }}
                  aria-label={`Report for ${f.name}`}
                >
                  <option value="">Auto-detect</option>
                  {catalog.map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}
                </select>
                {hit && <small className="ok-text">→ {hitName} · {hit.rows.toLocaleString()} rows{hit.how === 'content' ? ' (detected from columns)' : ''}</small>}
                {!hit && skipped[f.name] && <small className="warn-text">{skipped[f.name]}</small>}
              </div>
            )
          })}
        </div>
      )}
      {summary?.unmatched?.some((u) => !files.some((f) => f.name === u.file)) && (
        <div className="auth-banner warning" style={{ display: 'block' }}>
          <ErrorOutlineIcon fontSize="small" /> Not used:
          <ul style={{ margin: '6px 0 0 18px' }}>
            {summary.unmatched.filter((u) => !files.some((f) => f.name === u.file)).map((u, i) => <li key={i}>{u.file}: {u.reason}</li>)}
          </ul>
        </div>
      )}
      {status.state === 'error' && <div className="auth-banner error"><ErrorOutlineIcon fontSize="small" /> {status.error}</div>}
      <div className="actions">
        {files.length > 0 && <button className="ghost" onClick={() => { setFiles([]); setAssign({}); setSummary(null) }}>Clear files</button>}
        <button onClick={load} disabled={!files.length || status.state === 'working'}>
          {status.state === 'working' ? 'Mapping…' : loaded ? 'Reload and map' : 'Load and map'}
        </button>
      </div>
    </div>
  )
}
