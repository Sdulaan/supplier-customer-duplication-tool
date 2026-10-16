import { useEffect, useRef, useState } from 'react'
import AddIcon from '@mui/icons-material/Add'
import UploadFileOutlinedIcon from '@mui/icons-material/UploadFileOutlined'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlineOutlined'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'
import {
  loadAllEnvironments, saveEnvironments, getActiveEnvId, setActiveEnvId, newEnvironment,
  getToken, clearToken, parseEnvironmentFile
} from '../lib/environments'
import { authorizeInBrowser, authorizeWithPassword, redirectUri } from '../lib/oauth'

export default function EnvironmentsPage() {
  const [envs, setEnvs] = useState([])
  const [activeId, setActiveId] = useState('')
  const [auth, setAuth] = useState({ state: 'idle', error: '' })
  const [, bump] = useState(0)
  const [importMsg, setImportMsg] = useState(null)
  const [creds, setCreds] = useState(null) // { username, password } while the sign-in dialog is open
  const fileRef = useRef(null)

  useEffect(() => {
    loadAllEnvironments().then((all) => {
      setEnvs(all)
      setActiveId(getActiveEnvId(all))
    })
  }, [])

  const env = envs.find((e) => e.id === activeId) || envs[0]
  if (!env) return <p className="muted">Loading environments…</p>
  const token = getToken(env.id)
  const locked = Boolean(env.fromFile)

  function commit(next) {
    setEnvs(next)
    saveEnvironments(next)
  }
  function updateEnv(patch) {
    commit(envs.map((e) => (e.id === env.id ? { ...e, ...patch } : e)))
  }
  function updateVar(i, patch) {
    updateEnv({ variables: env.variables.map((v, idx) => (idx === i ? { ...v, ...patch } : v)) })
  }
  function select(id) {
    setActiveId(id)
    setActiveEnvId(id)
    setAuth({ state: 'idle', error: '' })
  }
  function addEnv() {
    const e = newEnvironment(`Environment ${envs.length + 1}`)
    commit([...envs, e])
    select(e.id)
  }
  function removeEnv() {
    if (envs.length === 1) return
    const rest = envs.filter((e) => e.id !== env.id)
    clearToken(env.id)
    commit(rest)
    select(rest[0].id)
  }

  async function importFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      const imported = parseEnvironmentFile(await file.text(), file.name)
      const local = envs.filter((e) => !e.fromFile)
      const kept = local.length === 1 && local[0].variables.every((v) => !v.value) ? [] : local
      const next = [...envs.filter((e) => e.fromFile), ...kept, ...imported]
      commit(next)
      select(imported[0].id)
      setImportMsg({ ok: true, text: `Imported ${imported.length} environment${imported.length > 1 ? 's' : ''} from ${file.name}. Enter your username and password to get a token.` })
      setCreds({ username: '', password: '' })
    } catch (err) {
      setImportMsg({ ok: false, text: err.message })
    }
  }

  async function authorize() {
    setAuth({ state: 'working', error: '' })
    try {
      await authorizeInBrowser(env)
      setAuth({ state: 'idle', error: '' })
    } catch (err) {
      setAuth({ state: 'error', error: err.message })
    }
    bump((n) => n + 1)
  }

  async function signIn(e) {
    e.preventDefault()
    const { username, password } = creds
    setAuth({ state: 'working', error: '' })
    try {
      await authorizeWithPassword(env, username, password)
      setAuth({ state: 'idle', error: '' })
      setCreds(null)
    } catch (err) {
      setAuth({ state: 'error', error: err.message })
    }
    bump((n) => n + 1)
  }

  return (
    <>
      {creds && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'grid', placeItems: 'center', zIndex: 50 }}>
          <form className="panel" onSubmit={signIn} style={{ width: 380, maxWidth: '90vw' }}>
            <div className="section-heading"><div><span className="eyebrow">SIGN IN</span><h2>{env.name}</h2></div></div>
            <label className="env-name">
              Username
              <input autoFocus value={creds.username} autoComplete="username" onChange={(e) => setCreds({ ...creds, username: e.target.value })} />
            </label>
            <label className="env-name">
              Password
              <input type="password" value={creds.password} autoComplete="current-password" onChange={(e) => setCreds({ ...creds, password: e.target.value })} />
            </label>
            {auth.state === 'error' && <div className="auth-banner error"><ErrorOutlineIcon fontSize="small" /> {auth.error}</div>}
            <div className="actions">
              <button type="button" className="ghost" onClick={() => { setCreds(null); setAuth({ state: 'idle', error: '' }) }}>Cancel</button>
              <button type="submit" disabled={auth.state === 'working' || !creds.username || !creds.password}>
                {auth.state === 'working' ? 'Signing in…' : 'Get access token'}
              </button>
            </div>
          </form>
        </div>
      )}
      <header className="page-head">
        <div>
          <span className="eyebrow">ENVIRONMENTS</span>
          <h1>Environments</h1>
          <p>Postman-style variable sets. Authorize in the browser to get an access token; nothing is stored on the server.</p>
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <input ref={fileRef} type="file" accept=".json,application/json" onChange={importFile} hidden />
          <button className="secondary" onClick={() => fileRef.current?.click()}><UploadFileOutlinedIcon fontSize="small" /> Import config file</button>
          <button onClick={addEnv}><AddIcon fontSize="small" /> New environment</button>
        </div>
      </header>
      {importMsg && (
        <div className={`auth-banner ${importMsg.ok ? 'success' : 'error'}`} style={{ marginTop: 0, marginBottom: 16 }}>{importMsg.text}</div>
      )}

      <div className="env-layout">
        <div className="panel env-list">
          {envs.map((e) => (
            <button key={e.id} className={`env-list-item ${e.id === env.id ? 'active' : ''}`} onClick={() => select(e.id)}>
              <strong>{e.name}</strong>
              {getToken(e.id) && <span className="badge LOW">Authorized</span>}
            </button>
          ))}
        </div>

        <div className="env-editor">
          <div className="panel">
            <div className="section-heading">
              <div><span className="eyebrow">VARIABLES</span><h2>{env.name}</h2></div>
              <button className="ghost" onClick={removeEnv} disabled={locked || envs.length === 1}><DeleteOutlineIcon fontSize="small" /> Delete</button>
            </div>
            <label className="env-name">
              Name
              <input value={env.name} disabled={locked} onChange={(e) => updateEnv({ name: e.target.value })} />
              {locked && <span className="field-hint">Defined in backend/environments.json (read-only here). The client secret stays on the server.</span>}
            </label>
            <div className="table-wrap">
              <table className="plain var-table">
                <thead><tr><th>Variable</th><th>Value</th><th /></tr></thead>
                <tbody>
                  {env.variables.map((v, i) => (
                    <tr key={i}>
                      <td><input value={v.key} disabled={locked} onChange={(e) => updateVar(i, { key: e.target.value })} placeholder="name" /></td>
                      <td>
                        <input
                          type={v.secret ? 'password' : 'text'}
                          value={v.value}
                          disabled={locked}
                          onChange={(e) => updateVar(i, { value: e.target.value })}
                          placeholder={v.hint || 'value'}
                          autoComplete="off"
                        />
                      </td>
                      <td>
                        <button className="ghost icon-btn" disabled={locked} aria-label="Remove variable" onClick={() => updateEnv({ variables: env.variables.filter((_, idx) => idx !== i) })}>
                          <DeleteOutlineIcon fontSize="small" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="actions" style={{ justifyContent: 'flex-start' }}>
              <button className="secondary" disabled={locked} onClick={() => updateEnv({ variables: [...env.variables, { key: '', value: '', secret: false }] })}>
                <AddIcon fontSize="small" /> Add variable
              </button>
            </div>
          </div>

          <div className="panel">
            <div className="section-heading">
              <div><span className="eyebrow">AUTHORIZATION</span><h2>OAuth 2.0 · Password Credentials or browser (PKCE)</h2></div>
            </div>
            <p className="muted" style={{ margin: '0 0 6px', fontSize: 13 }}>
              Register this callback URL on the IFS client: <code>{redirectUri()}</code>
            </p>

            {token && (
              <div className="auth-banner success">
                <CheckCircleOutlineIcon fontSize="small" /> Access token active until {new Date(token.expiresAt).toLocaleTimeString()}.
              </div>
            )}
            {auth.state === 'error' && (
              <div className="auth-banner error"><ErrorOutlineIcon fontSize="small" /> {auth.error}</div>
            )}

            <div className="actions">
              {token && <button className="ghost" onClick={() => { clearToken(env.id); bump((n) => n + 1) }}>Clear token</button>}
              <button className="secondary" onClick={authorize} disabled={auth.state === 'working'}>
                {auth.state === 'working' && !creds ? 'Waiting for sign-in…' : 'Authorize using browser'}
              </button>
              <button onClick={() => { setAuth({ state: 'idle', error: '' }); setCreds({ username: '', password: '' }) }} disabled={auth.state === 'working'}>
                {token ? 'Get new access token' : 'Sign in with username & password'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
