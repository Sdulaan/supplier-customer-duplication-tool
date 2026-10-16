import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'
import { ENTITIES } from '../lib/entities'
import RecordBrowser from '../components/RecordBrowser'
import ReportImport from '../components/ReportImport'
import FileDownloadOutlinedIcon from '@mui/icons-material/FileDownloadOutlined'
import { setFetched, getFetched } from '../lib/dataStore'
import { loadAllEnvironments, getActiveEnvId, setActiveEnvId, getToken, resolveVariables } from '../lib/environments'

// Fetches one entity (supplier or customer) with everything connected to it from IFS (GET only),
// through the backend, using the access token from the Environments page.
export default function EntityDataPage({ entityId }) {
  const entity = ENTITIES.find((e) => e.id === entityId)
  const [source, setSource] = useState('api') // 'api' (IFS environment) | 'reports' (Quick report files)
  const [envs, setEnvs] = useState([])
  const [envId, setEnvId] = useState('')
  const [state, setState] = useState(() => {
    const prior = getFetched()?.results.find((r) => r.entity === entityId)
    return { status: prior ? 'done' : 'idle', error: '', result: prior || null }
  })

  useEffect(() => {
    loadAllEnvironments().then((all) => {
      setEnvs(all)
      setEnvId(getActiveEnvId(all))
    })
  }, [])

  const env = envs.find((e) => e.id === envId)
  const vars = resolveVariables(env)
  const token = envId ? getToken(envId) : null
  const ready = Boolean(vars.baseUrl && token)

  async function fetchData() {
    setState({ status: 'fetching', error: '', result: null })
    try {
      const res = await fetch('/api/ifs/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ baseUrl: vars.baseUrl, accessToken: token.accessToken, entities: [entityId] })
      })
      const body = await res.json().catch(() => null)
      if (!res.ok || !body?.success) throw new Error(body?.error || body?.detail || `Fetch failed (${res.status}).`)
      setFetched(body.results)
      setState({ status: 'done', error: '', result: body.results[0] })
    } catch (err) {
      setState({ status: 'error', error: err.message, result: null })
    }
  }

  const name = entity.label.toLowerCase()

  function onReportsLoaded(result) {
    setFetched([result])
    setState({ status: 'done', error: '', result })
  }

  async function exportExcel() {
    try {
      const res = await fetch(`/api/export/${entityId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ result: state.result })
      })
      if (!res.ok) throw new Error(`Export failed (${res.status}).`)
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = `${entityId}-mapped.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setState((s) => ({ ...s, error: err.message }))
    }
  }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">{entity.label.toUpperCase()}S</span>
          <h1>{entity.label} Data</h1>
          <p>Collect every {name} with all the data connected to it, either from an IFS environment or from Quick Report exports.</p>
        </div>
      </header>

      <div className="tabs">
        <button className={`tab ${source === 'api' ? 'active' : ''}`} onClick={() => setSource('api')}>IFS environment</button>
        <button className={`tab ${source === 'reports' ? 'active' : ''}`} onClick={() => setSource('reports')}>Quick report files</button>
      </div>

      {source === 'reports' && <ReportImport entity={entity} onLoaded={onReportsLoaded} loaded={Boolean(state.result)} />}

      {source === 'api' && <div className="panel">
        <div className="section-heading">
          <div><span className="eyebrow">ENVIRONMENT</span><h2>Source</h2></div>
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
          <div className="auth-banner warning"><ErrorOutlineIcon fontSize="small" /> Not authorized. Open Environments and sign in with your username and password.</div>
        )}
        {state.status === 'error' && <div className="auth-banner error"><ErrorOutlineIcon fontSize="small" /> {state.error}</div>}
        <div className="actions">
          <button onClick={fetchData} disabled={!ready || state.status === 'fetching'}>
            {state.status === 'fetching' ? `Fetching ${name}s…` : `Fetch ${name}s`}
          </button>
        </div>
      </div>}

      {state.status === 'error' && source === 'reports' && <div className="auth-banner error"><ErrorOutlineIcon fontSize="small" /> {state.error}</div>}
      {state.result && (
        <RecordBrowser
          entity={entity}
          result={state.result}
          actions={<button className="secondary" onClick={exportExcel}><FileDownloadOutlinedIcon fontSize="small" /> Download Excel</button>}
        />
      )}
    </>
  )
}
