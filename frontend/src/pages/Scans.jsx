import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { SCAN_ENTITIES, SOURCE_LABEL, downloadScanExcel, fetchJson, formatScanTime } from '../lib/scans'

function ScanRow({ scan, base, noun, latest, onChanged, onError }) {
  const [busy, setBusy] = useState(false)
  async function download() {
    setBusy(true)
    try { await downloadScanExcel(scan.id) } catch (e) { onError(e.message) }
    setBusy(false)
  }
  async function remove() {
    if (!window.confirm(`Delete "${scan.name}" and its Excel report?`)) return
    await fetch(`/api/spec-dedup/scans/${scan.id}`, { method: 'DELETE' })
    onChanged()
  }
  const t = scan.byTier || {}
  return (
    <article className={`history-row ${latest ? 'latest-scan' : ''}`}>
      <div>
        <p className="eyebrow">{latest ? 'Latest scan' : `Scan ${scan.id}`}</p>
        <h3>{scan.name}</h3>
        <div className="history-meta">
          <span className="scan-state completed">Completed</span>
          <span>{SOURCE_LABEL[scan.source] || scan.source}</span>
          <span>{scan.eligible.toLocaleString()} {noun}s</span>
          <span>{scan.groups} groups</span>
          <span>T1 {t[1] || 0} · T2 {t[2] || 0} · T3 {t[3] || 0} · T4 {t[4] || 0}</span>
          <span>{formatScanTime(scan.createdAt)}</span>
        </div>
      </div>
      <div className="history-actions">
        <button type="button" className="ghost" onClick={remove}>Delete</button>
        <button type="button" className="secondary" onClick={download} disabled={busy}>{busy ? 'Preparing…' : 'Download Excel'}</button>
        <Link className="button" to={`${base}/${scan.id}`}>Open results</Link>
      </div>
    </article>
  )
}

export default function ScansPage({ entity }) {
  const cfg = SCAN_ENTITIES[entity]
  const noun = cfg.label.toLowerCase()
  const [scans, setScans] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => fetchJson(`/api/spec-dedup/scans?entity=${entity}`).then((s) => { setScans(s); setError('') }, () => { setScans([]); setError('Scan history could not be loaded. Check that the backend is running, then reload this page.') }), [entity])
  useEffect(() => { setScans(null); load() }, [load])

  const latest = scans?.[0] || null
  const recent = scans?.slice(1) || []
  const groups = (scans || []).reduce((n, s) => n + s.groups, 0)

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">{cfg.label.toUpperCase()} SCANS</span>
          <h1>{cfg.label} duplicate review</h1>
          <p>Start a scan from Quick Report files or an IFS environment, or reopen a previous result.</p>
        </div>
        <Link className="button" to={`${cfg.base}/new`}>Start new scan</Link>
      </header>
      <section className="banner"><b>Candidate detection, not automatic merging.</b> Scored groups support review decisions; human review remains authoritative.</section>

      <div className="cards">
        <article><label>Total scans</label><strong>{scans?.length ?? '…'}</strong></article>
        <article><label>Groups found</label><strong>{scans ? groups.toLocaleString() : '…'}</strong></article>
        <article><label>Latest scan</label><strong>{latest ? latest.groups : '—'}</strong><small>{latest ? 'groups' : ''}</small></article>
      </div>

      {error && <div className="error" role="alert">{error}</div>}

      <section className="panel scan-history">
        <div className="section-heading"><div><p className="eyebrow">Latest scan</p><h2>Most recent activity</h2></div></div>
        {scans === null ? <p role="status">Loading scan history…</p> : latest ? <ScanRow scan={latest} base={cfg.base} noun={noun} latest onChanged={load} onError={setError} key={latest.id} /> : (
          <div className="empty actionable-empty"><h3>No scans yet</h3><p>Start a new scan to create the first result.</p><Link className="button" to={`${cfg.base}/new`}>Start a new scan</Link></div>
        )}
      </section>

      <section className="panel scan-history">
        <div className="section-heading"><div><p className="eyebrow">Recent scans</p><h2>Previous scan history</h2></div><span>{scans?.length || 0} total</span></div>
        {scans === null ? <p role="status">Loading recent scans…</p> : recent.length ? (
          <div className="history-list">{recent.map((s) => <ScanRow scan={s} base={cfg.base} noun={noun} key={s.id} onChanged={load} onError={setError} />)}</div>
        ) : (
          <div className="empty actionable-empty"><h3>{latest ? 'No earlier scans' : 'History is empty'}</h3><p>{latest ? 'The latest scan is currently the only scan.' : 'Completed scans will appear here.'}</p></div>
        )}
      </section>
    </>
  )
}
