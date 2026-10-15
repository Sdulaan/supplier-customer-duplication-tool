// Postman-style environments: named sets of {{variables}}, kept in localStorage.
// Access tokens live in sessionStorage only.
const ENV_KEY = 'sebsa_dup_environments'
const ACTIVE_KEY = 'sebsa_dup_active_env'
const TOKEN_KEY = 'sebsa_dup_tokens'

export const DEFAULT_VARIABLES = [
  { key: 'baseUrl', value: '', secret: false, hint: 'https://<ifs-host> (GET calls go to {{baseUrl}}/main/ifsapplications/projection/v1/...)' },
  { key: 'authUrl', value: '', secret: false, hint: 'Authorization endpoint opened in the browser' },
  { key: 'tokenUrl', value: '', secret: false, hint: 'Token endpoint (code exchange)' },
  { key: 'clientId', value: '', secret: false, hint: '' },
  { key: 'clientSecret', value: '', secret: true, hint: 'Optional for public clients (PKCE)' },
  { key: 'scope', value: 'openid', secret: false, hint: '' }
]

function read(key, store = localStorage) {
  try {
    return JSON.parse(store.getItem(key))
  } catch {
    return null
  }
}

export function newEnvironment(name = 'New environment') {
  return { id: crypto.randomUUID(), name, variables: DEFAULT_VARIABLES.map((v) => ({ ...v })) }
}

export function loadEnvironments() {
  const envs = read(ENV_KEY)
  return Array.isArray(envs) && envs.length ? envs : [newEnvironment('Default')]
}

export function saveEnvironments(envs) {
  localStorage.setItem(ENV_KEY, JSON.stringify(envs.filter((e) => !e.fromFile)))
}

export function getActiveEnvId(envs) {
  const id = localStorage.getItem(ACTIVE_KEY)
  return envs.some((e) => e.id === id) ? id : envs[0].id
}

export function setActiveEnvId(id) {
  localStorage.setItem(ACTIVE_KEY, id)
}

// Resolve variables by name, expanding nested {{other}} references (max 5 levels).
export function resolveVariables(env) {
  const raw = Object.fromEntries((env?.variables || []).filter((v) => v.key).map((v) => [v.key, v.value ?? '']))
  const out = {}
  for (const [k, v] of Object.entries(raw)) {
    let value = String(v)
    for (let i = 0; i < 5 && /\{\{\w+\}\}/.test(value); i++) {
      value = value.replace(/\{\{(\w+)\}\}/g, (_, name) => raw[name] ?? '')
    }
    out[k] = value.trim()
  }
  return out
}

export function getToken(envId) {
  const entry = (read(TOKEN_KEY, sessionStorage) || {})[envId]
  if (!entry || entry.expiresAt <= Date.now() + 15000) return null
  return entry
}

export function storeToken(envId, token) {
  const all = read(TOKEN_KEY, sessionStorage) || {}
  all[envId] = { accessToken: token.accessToken, expiresAt: Date.now() + (token.expiresIn || 3600) * 1000 }
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify(all))
}

export function clearToken(envId) {
  const all = read(TOKEN_KEY, sessionStorage) || {}
  delete all[envId]
  sessionStorage.setItem(TOKEN_KEY, JSON.stringify(all))
}

// Environments from backend/environments.json: read-only here, secrets stay on the server.
export async function loadAllEnvironments() {
  const local = loadEnvironments().filter((e) => !e.fromFile)
  let fileEnvs = []
  try {
    const res = await fetch('/api/environments')
    if (res.ok) {
      const body = await res.json()
      fileEnvs = body.environments.map((e) => ({
        id: `file:${e.name}`,
        name: e.name,
        fromFile: true,
        variables: Object.entries(e.variables).map(([key, value]) => ({ key, value: String(value), secret: false }))
      }))
    }
  } catch {
    // backend not running: fall back to browser-saved environments only
  }
  return [...fileEnvs, ...local]
}

// Parse an uploaded config file into environments. Accepts:
//  - this tool's format: { "environments": [{ "name", "variables": { key: value } }] } (or a single such object)
//  - a Postman environment export: { "name", "values": [{ "key", "value", "enabled" }] }
export function parseEnvironmentFile(text) {
  let data
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error('The file is not valid JSON.')
  }
  const items = Array.isArray(data?.environments) ? data.environments : [data]
  const envs = items.map((item, i) => {
    let variables
    if (Array.isArray(item?.values)) {
      variables = item.values.filter((v) => v?.key && v.enabled !== false).map((v) => ({ key: String(v.key), value: String(v.value ?? '') }))
    } else if (item?.variables && typeof item.variables === 'object') {
      variables = Object.entries(item.variables).map(([key, value]) => ({ key, value: String(value ?? '') }))
    } else {
      return null
    }
    const defaults = DEFAULT_VARIABLES.filter((d) => !variables.some((v) => v.key === d.key)).map((d) => ({ ...d }))
    return {
      id: crypto.randomUUID(),
      name: String(item.name || `Imported ${i + 1}`),
      variables: [
        ...variables.map((v) => ({ ...v, secret: /secret|password/i.test(v.key), hint: '' })),
        ...defaults
      ]
    }
  }).filter(Boolean)
  if (!envs.length) throw new Error('No environments found. Expected "environments" or a Postman "values" list.')
  return envs
}
