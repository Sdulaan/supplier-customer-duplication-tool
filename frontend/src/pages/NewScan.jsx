import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'
import { SCAN_ENTITIES, fetchJson } from '../lib/scans'
import { loadAllEnvironments, getActiveEnvId, setActiveEnvId, getToken, resolveVariables } from '../lib/environments'

export default function NewScanPage({ entity }) {
  const cfg = SCAN_ENTITIES[entity]
  const navigate = useNavigate()
  const input = useRef(null)
  const [source, setSource] = useState('reports') // 'reports' (Quick Report files) | 'ifs' (IFS environment)
  const [files, setFiles] = useState([])
  const [name, setName] = useState('')
  const [useMl, setUseMl] = useState(true)
  const [conditions, setConditions] = useState([])
  const [selected, setSelected] = useState([])
  const [envs, setEnvs] = useState([])
  const [envId, setEnvId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!cfg.hasConditions) return
    fetchJson('/api/spec-dedup/conditions').then((c) => { setConditions(c); setSelected(c.map((x) => x.id)) }, () => setError('Could not load the duplicate-checking conditions. Is the backend running?'))
  }, [cfg.hasConditions])
  useEffect(() => {
    loadAllEnvironments().then((all) => { setEnvs(all); setEnvId(getActiveEnvId(all)) })
  }, [])

  const env = envs.find((e) => e.id === envId)
  const vars = resolveVariables(env)
  const token = envId ? getToken(envId) : null
  const ifsReady = Boolean(vars.baseUrl && token)
  const canRun = source === 'reports' ? files.length > 0 : ifsReady
  const toggle = (id) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  async function run() {
    setBusy(true)
    setError('')
    try {
      let body
      if (source === 'reports') {
        const form = new FormData()
        files.forEach((f) => form.append('files', f, f.name))
        form.append('entity', entity)
        form.append('useMl', useMl)
        form.append('name', name)
        form.append('conditions', selected.join(','))
        body = await fetchJson('/api/spec-dedup/upload', { method: 'POST', body: form })
      } else {
        body = await fetchJson('/api/spec-dedup/fetch', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entity, baseUrl: vars.baseUrl, accessToken: token.accessToken, name, useMl, conditions: cfg.hasConditions ? selected : null })
        })
      }
      navigate(`${cfg.base}/${body.scan.id}`)
    } catch (e) {
      setError(e.message)
      setBusy(false)
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">NEW SCAN</span>
          <h1>Run {cfg.label.toLowerCase()} duplicate scan</h1>
          <p>Add the data from Quick Report files or fetch it from an IFS environment, choose the checks, then run the scan.</p>
        </div>
        <div className="actions"><Link className="button secondary" to={cfg.base}>Dashboard</Link></div>
      </header>
      {error && <div className="error" role="alert"><b>Scan could not run</b><p>{error}</p></div>}

      <div className="tabs">
        <button className={`tab ${source === 'reports' ? 'active' : ''}`} onClick={() => setSource('reports')} disabled={busy}>Quick report files</button>
        <button className={`tab ${source === 'ifs' ? 'active' : ''}`} onClick={() => setSource('ifs')} disabled={busy}>IFS environment</button>
      </div>

      <div className="two-col">
        <section className="panel form">
          <h2>{source === 'reports' ? 'Upload' : 'IFS environment'}</h2>
          <label className="field-label">Scan name (optional)
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder={`e.g. Production ${cfg.label.toLowerCase()}s, Oct 2026`} disabled={busy} />
          </label>

          {source === 'reports' ? (
            <>
              <div className={`dropzone ${files.length ? 'has-files' : ''}`} onClick={() => !busy && input.current?.click()} role="button" tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
                onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (!busy) setFiles([...e.dataTransfer.files]) }}>
                <b>{files.length ? `${files.length} file${files.length === 1 ? '' : 's'} selected` : 'Select the Quick Report Excel files'}</b>
                <small>{files.length ? 'Click to choose again' : 'Click to browse, or drop the files here (.xlsx / .csv)'}</small>
                <input ref={input} type="file" multiple accept=".xlsx,.csv" hidden onChange={(e) => { setFiles([...e.target.files]); e.target.value = '' }} />
              </div>
              {files.length > 0 && <ul className="file-list">{files.map((f) => <li key={f.name}><span>{f.name}</span><small>{(f.size / 1024).toFixed(0)} KB</small></li>)}</ul>}
              <p className="muted" style={{ fontSize: 12, margin: 0 }}>{cfg.reportHint} Expected: {cfg.reports.join(', ')}.</p>
            </>
          ) : (
            <>
              <div className="toolbar" style={{ marginBottom: 0 }}>
                <select value={envId} onChange={(e) => { setEnvId(e.target.value); setActiveEnvId(e.target.value) }} aria-label="Environment" disabled={busy}>
                  {envs.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                </select>
                <Link to="/environments" className="button secondary">Manage environments</Link>
              </div>
              <span className="muted" style={{ fontSize: 13 }}>{vars.baseUrl || 'baseUrl not set for this environment'}</span>
              {token
                ? <div className="auth-banner success"><CheckCircleOutlineIcon fontSize="small" /> Authorized until {new Date(token.expiresAt).toLocaleTimeString()}.</div>
                : <div className="auth-banner warning"><ErrorOutlineIcon fontSize="small" /> Not authorized. Open Environments and sign in with your username and password.</div>}
              <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                Every {cfg.label.toLowerCase()} is read from IFS (GET only) with its addresses, communication methods and contacts, then scanned.
                {entity === 'supplier' && ' Reports the IFS projection does not expose (purchasing, payment ledger, invoicing, SRM) are not part of an IFS scan; use Quick report files for the full 10-table scoring.'}
              </p>
            </>
          )}
        </section>

        <div className="stack">
          {cfg.hasConditions && (
            <section className="panel">
              <h2>Duplicate-checking conditions</h2>
              <p className="muted" style={{ fontSize: 13 }}>{cfg.label} name is always compared. Tick the other evidence to use.</p>
              <div className="checks">
                {conditions.map((c) => (
                  <label key={c.id}>
                    <input type="checkbox" checked={selected.includes(c.id)} onChange={() => toggle(c.id)} disabled={busy} />
                    <span>{c.label}<small>{c.rule} · {c.detail}</small></span>
                  </label>
                ))}
              </div>
            </section>
          )}
          {cfg.hasConditions ? (
            <section className="panel">
              <h2>Learned scoring</h2>
              <label className="check-row"><input type="checkbox" checked={useMl} onChange={(e) => setUseMl(e.target.checked)} disabled={busy} /> Add the ML probability to each pair (advisory; rule scores decide the tier)</label>
            </section>
          ) : (
            <section className="panel">
              <h2>Checks used</h2>
              <p className="muted" style={{ fontSize: 13, margin: 0 }}>Customers are compared on tax / registration number, bank account, name (legal, phonetic, acronym), street address, phone, email, shared contact person and legacy ID, with penalties for conflicting registration numbers, branches and different countries.</p>
            </section>
          )}
        </div>
      </div>

      <div className="actions" style={{ marginTop: 18 }}>
        <button type="button" onClick={run} disabled={busy || !canRun}>{busy ? (source === 'ifs' ? 'Fetching and scanning…' : 'Scanning…') : source === 'ifs' ? `Fetch ${cfg.label.toLowerCase()}s and scan` : 'Run scan'}</button>
        {!canRun && <p className="validation-guidance">{source === 'reports' ? 'Run scan becomes available once the Excel files are selected.' : 'Fetching becomes available once the environment is authorized.'}</p>}
      </div>
      {busy && <section className="panel processing-state" role="status" aria-live="polite"><p className="eyebrow">Scan running</p><h2>Processing {cfg.label.toLowerCase()}s…</h2><p className="muted">{source === 'ifs' ? 'Fetching from IFS, scoring candidate pairs and saving the result. A large environment can take a few minutes.' : 'Scoring candidate pairs and saving the result. This usually takes a few seconds.'}</p></section>}
    </>
  )
}
