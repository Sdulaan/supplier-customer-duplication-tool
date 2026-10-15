import { useEffect, useState } from 'react'

// Popup landing page: hands the authorization result back to the opener and closes.
export default function OAuthCallback() {
  const [message, setMessage] = useState('Finishing sign-in…')

  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const payload = {
      type: 'oauth-callback',
      code: p.get('code'),
      state: p.get('state'),
      error: p.get('error'),
      error_description: p.get('error_description')
    }
    if (window.opener) {
      window.opener.postMessage(payload, window.location.origin)
      window.close()
    } else {
      setMessage('This window was not opened by the duplication tool. You can close it.')
    }
  }, [])

  return <div className="login-page"><div className="login-card"><p className="login-sub">{message}</p></div></div>
}
