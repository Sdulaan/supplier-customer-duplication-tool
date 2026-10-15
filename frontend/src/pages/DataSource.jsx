import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'
import { ENTITIES } from '../lib/entities'
import { setFetched } from '../lib/dataStore'
import { loadAllEnvironments, getActiveEnvId, setActiveEnvId, getToken, resolveVariables } from '../lib/environments'

const STAGE_LABEL = {
  general: 'General information',
  supplier_address: 'Addresses',
  supplier_payment: 'Payments'
}

// Fetches supplier / customer master data from IFS (GET only) through the backend,
// using the access token obtained by browser authorization.
export default function DataSourcePage() {
  const [envs, setEnvs] = useState([])
  const [envId, setEnvId] = useState('')

  useEffect(() => {
    loadAllEnvironments().then((all) => {
      setEnvs(all)
      setEnvId(getActiveEnvId(all))
    })
  }, [])
  const [selected, setSelected] = useState(['supplier', 'customer'])
  const [state, setState] = useState({ status: 'idle', error: '', results: null })

  const env = envs.find((e) => e.id === envId)
  const vars = resolveVariables(env)
  const token = envId ? getToken(envId) : null
  const ready = Boolean(vars.baseUrl && token && selected.length)

  function toggle(id) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  }

  async function fetchData() {
    setState({ status: 'fetching', error: '', results: null })
    try {
      const res = await fetch('/api/ifs/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: vars.baseUrl, accessToken: token.accessToken, entities: selected })
      })
      const body = await res.json().catch(() => null)
      if (!res.ok || !body?.success) throw new Error(body?.error || body?.detail || `Fetch failed (${res.status}).`)
      setFetched(body.results)
      setState({ status: 'done', error: '', results: body.results })
    } catch (err) {
      setState({ status: 'error', error: err.message, results: null })
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">DATA SOURCE</span>
          <h1>Fetch Data</h1>
          <p>Pull supplier and customer master data from IFS with GET requests, using your browser-authorized environment.</p>
        </div>
      </header>

      <div className="panel">
        <div className="section-heading">
          <div><span className="eyebrow">STEP 1</span><h2>Environment</h2></div>
          <Link to="/environments" className="button secondary">Manage environments</Link>
        </div>
        <div className="toolbar">
          <select value={envId} onChange={(e) => { setEnvId(e.target.value); setActiveEnvId(e.target.value) }} aria-label="Environment">
            {envs.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
          <span className="muted" style={{ fontSize: 13 }}>{vars.baseUrl || 'baseUrl not set'}</span>
        </div>
        {token ? (
          <div className="auth-banner success"><CheckCircleOutlineIcon fontSize="small" /> Authorized until {new Date(token.expiresAt).toLocaleTimeString()}.</div>
        ) : (
          <div className="auth-banner warning"><ErrorOutlineIcon fontSize="small" /> Not authorized. Open Environments and use “Authorize using browser”.</div>
        )}
      </div>

      <div className="panel">
        <div className="section-heading">
          <div><span className="eyebrow">STEP 2</span><h2>Entities to fetch</h2></div>
        </div>
        <div className="entity-grid">
          {ENTITIES.map((e) => (
            <label key={e.id} className={`entity-card ${selected.includes(e.id) ? 'active' : ''}`}>
              <input type="checkbox" checked={selected.includes(e.id)} onChange={() => toggle(e.id)} />
              <span><strong>{e.label}</strong><small>{e.description}</small></span>
            </label>
          ))}
        </div>
        {state.status === 'error' && <div className="auth-banner error"><ErrorOutlineIcon fontSize="small" /> {state.error}</div>}
        <div className="actions">
          <button onClick={fetchData} disabled={!ready || state.status === 'fetching'}>
            {state.status === 'fetching' ? 'Fetching…' : 'Fetch data'}
          </button>
        </div>
      </div>

      {state.results && (
        <div className="panel">
          <div className="section-heading">
            <div><span className="eyebrow">RESULT</span><h2>Fetched records</h2></div>
            <Link to="/duplicates" className="button">Review duplicates</Link>
          </div>
          <div className="table-wrap">
            <table className="plain">
              <thead><tr><th>Entity</th><th>Data set</th><th>Records</th><th>Errors</th></tr></thead>
              <tbody>
                {state.results.flatMap((r) =>
                  Object.entries(r.stages).map(([stage, s]) => (
                    <tr key={`${r.entity}-${stage}`}>
                      <td><b>{r.entity}</b></td>
                      <td>{STAGE_LABEL[stage] || stage} <span className="muted">({s.collection})</span></td>
                      <td>{s.records.length.toLocaleString()}</td>
                      <td>{s.errors.length ? <span className="badge HIGH">{s.errors.length}</span> : '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  )
}
