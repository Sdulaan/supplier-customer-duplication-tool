// OAuth2 Authorization Code + PKCE through a browser popup (Postman's "Authorize using browser").
// The popup lands on /oauth/callback, which posts the code back here; the backend then exchanges
// the code so the token endpoint never needs CORS.
import { resolveVariables, storeToken } from './environments'

export const REDIRECT_PATH = '/oauth/callback'

function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function randomString(len = 48) {
  return b64url(crypto.getRandomValues(new Uint8Array(len))).slice(0, len)
}

async function challengeFor(verifier) {
  return b64url(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier)))
}

export function redirectUri() {
  return `${window.location.origin}${REDIRECT_PATH}`
}

export async function authorizeInBrowser(env) {
  const v = resolveVariables(env)
  const missing = ['authUrl', 'tokenUrl', 'clientId'].filter((k) => !v[k])
  if (missing.length) throw new Error(`Set ${missing.join(', ')} in the environment first.`)

  const verifier = randomString(64)
  const state = randomString(24)
  let url
  try {
    url = new URL(v.authUrl)
  } catch {
    throw new Error('authUrl is not a valid URL.')
  }
  url.search = new URLSearchParams({
    response_type: 'code',
    client_id: v.clientId,
    redirect_uri: redirectUri(),
    scope: v.scope || 'openid',
    state,
    code_challenge: await challengeFor(verifier),
    code_challenge_method: 'S256'
  }).toString()

  const popup = window.open(url.toString(), 'ifs-oauth', 'width=520,height=720')
  if (!popup) throw new Error('The browser blocked the sign-in popup. Allow popups for this site and retry.')

  const code = await new Promise((resolve, reject) => {
    const timer = setInterval(() => {
      if (popup.closed) {
        cleanup()
        reject(new Error('Sign-in window was closed before authorization finished.'))
      }
    }, 500)
    function onMessage(event) {
      if (event.origin !== window.location.origin || event.data?.type !== 'oauth-callback') return
      cleanup()
      if (event.data.state !== state) return reject(new Error('Authorization state mismatch. Please retry.'))
      if (event.data.error) return reject(new Error(`Authorization failed: ${event.data.error_description || event.data.error}`))
      resolve(event.data.code)
    }
    function cleanup() {
      clearInterval(timer)
      window.removeEventListener('message', onMessage)
    }
    window.addEventListener('message', onMessage)
  })

  const res = await fetch('/api/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tokenUrl: v.tokenUrl,
      clientId: v.clientId,
      clientSecret: v.clientSecret || null,
      envName: env.fromFile ? env.name : null,
      code,
      redirectUri: redirectUri(),
      codeVerifier: verifier
    })
  })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body?.success) throw new Error(body?.error || `Token exchange failed (${res.status}).`)
  storeToken(env.id, body)
  return body
}

// Postman's "Password Credentials" grant: username/password are sent once to the backend, never stored.
export async function authorizeWithPassword(env, username, password) {
  const v = resolveVariables(env)
  const missing = ['tokenUrl', 'clientId'].filter((k) => !v[k])
  if (missing.length) throw new Error(`Set ${missing.join(', ')} in the environment first.`)
  const res = await fetch('/api/auth/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tokenUrl: v.tokenUrl,
      clientId: v.clientId,
      clientSecret: v.clientSecret || null,
      envName: env.fromFile ? env.name : null,
      username,
      password,
      scope: v.scope || 'openid'
    })
  })
  const body = await res.json().catch(() => null)
  if (!res.ok || !body?.success) throw new Error(body?.error || `Sign-in failed (${res.status}).`)
  storeToken(env.id, body)
  return body
}
