import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { DECISIONS, RULES, SCAN_ENTITIES, TIER_BADGE, TIERS, downloadScanExcel, fetchJson, formatScanTime } from '../lib/scans'

const PAGE = 25

function Pairs({ pairs }) {
  return (
    <div className="compare">
      <table>
        <thead><tr><th>Pair</th><th>Score</th><th>Rules</th><th>Evidence</th><th>ML</th></tr></thead>
        <tbody>
          {pairs.map((p) => (
            <tr key={`${p.a}|${p.b}`}>
              <td className="field">{p.a} ↔ {p.b}</td>
              <td>{p.score}</td>
              <td>{Object.entries(p.rules).map(([k, v]) => `${k} ${v > 0 ? '+' : ''}${v}`).join(' · ') || '—'}</td>
              <td style={{ fontSize: 12 }}>{[...p.details.A01, ...p.details.A02, p.details.N01, p.details.L01, ...p.details.C].filter(Boolean).join(' · ')}</td>
              <td>{p.ml == null ? '—' : `${Math.round(p.ml * 100)}%`}{p.mlOnly ? ' (ML only)' : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function GroupCard({ group, scanId, decision, onDecision, label }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState({ decision: decision?.decision || '', comment: decision?.comment || '' })
  const [error, setError] = useState('')
  async function save(clear) {
    try {
      const body = await fetchJson(`/api/spec-dedup/scans/${scanId}/groups/${group.id}/decision`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(clear ? { decision: '', comment: '' } : draft)
      })
      if (clear) setDraft({ decision: '', comment: '' })
      onDecision(group.id, clear ? null : body.decision)
      setError('')
    } catch (e) { setError(e.message) }
  }
  const decided = decision?.decision
  return (
    <article className="group-card">
      <div className="group-head">
        <div>
          <p className="eyebrow">{group.id} · {TIERS[group.tier]}</p>
          <h2>{group.records[0].name || group.records[0].id}</h2>
          <small className="muted">{group.records.length} records{group.tags.length ? ` · ${group.tags.join(', ')}` : ''}{group.tags.includes('LINKED HIERARCHY') ? ' · do not auto-merge' : ''}</small>
        </div>
        <div className="group-head-actions">
          <span className={`badge ${TIER_BADGE[group.tier]}`}>Score {group.score}</span>
          {decided && <span className={`badge status-pill ${decided === DECISIONS[0] ? 'confirmed' : decided === DECISIONS[1] ? 'dismissed' : ''}`}>{decided}</span>}
          <button type="button" className="secondary" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Hide detail' : 'Show detail'}</button>
        </div>
      </div>
      <div className="member-preview">
        {group.records.slice(0, 6).map((r) => (
          <span key={r.id} className={r.id === group.survivor ? 'member survivor' : 'member'}>{r.id}{r.id === group.survivor && ' ★'}</span>
        ))}
        {group.records.length > 6 && <span className="member">+{group.records.length - 6} more</span>}
      </div>
      {open && (
        <div className="group-detail">
          <div className="compare">
            <table>
              <thead><tr><th>{label} Id</th><th>Name</th><th>Country</th><th>Category</th><th>Address</th><th>Phone / email</th><th>Survivor score</th></tr></thead>
              <tbody>
                {group.records.map((r) => (
                  <tr key={r.id} title={Object.entries(r.survivorBreakdown).map(([k, v]) => `${k}: ${v}`).join('\n')}>
                    <td className="field">{r.id}{r.id === group.survivor && <span className="master">SURVIVOR</span>}</td>
                    <td>{r.name}</td><td>{r.country}</td><td>{r.category}</td>
                    <td>{[r.address, r.city].filter(Boolean).join(', ') || <span className="muted">—</span>}</td>
                    <td>{[...r.phones, ...r.emails].join(', ') || <span className="muted">—</span>}</td>
                    <td>{r.survivorScore}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pairs pairs={group.pairs} />
          <p className="muted" style={{ fontSize: 12 }}>{Object.entries(RULES).map(([k, v]) => `${k} ${v}`).join(' · ')}. Hover a supplier row for its survivor scorecard.</p>
          <div className="decision-row">
            <select value={draft.decision} onChange={(e) => setDraft({ ...draft, decision: e.target.value })} aria-label="Human decision">
              <option value="">No decision</option>
              {DECISIONS.map((d) => <option key={d}>{d}</option>)}
            </select>
            <input value={draft.comment} onChange={(e) => setDraft({ ...draft, comment: e.target.value })} placeholder="Comment (included in the Excel report)" aria-label="Human comment" />
            <button type="button" onClick={() => save(false)} disabled={!draft.decision}>Save decision</button>
            {decided && <button type="button" className="ghost" onClick={() => save(true)}>Clear</button>}
          </div>
          {error && <p className="error" role="alert">{error}</p>}
        </div>
      )}
    </article>
  )
}

export default function ScanResults({ entity }) {
  const { id } = useParams()
  const cfg = SCAN_ENTITIES[entity]
  const noun = cfg.label.toLowerCase()
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [decisions, setDecisions] = useState({})
  const [view, setView] = useState('dup')
  const [tier, setTier] = useState('ALL')
  const [decisionFilter, setDecisionFilter] = useState('ALL')
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(0)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setData(null)
    fetchJson(`/api/spec-dedup/scans/${id}`).then((b) => { setData(b); setDecisions(b.decisions || {}) }, (e) => setError(e.message))
  }, [id])

  const groups = data?.groups || []
  const lanes = useMemo(() => ({
    dup: groups.filter((g) => g.lane === 'dup'), hier: groups.filter((g) => g.lane === 'hier'), watch: groups.filter((g) => g.lane === 'watch')
  }), [data])
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (lanes[view] || []).filter((g) => (tier === 'ALL' || String(g.tier) === tier) &&
      (decisionFilter === 'ALL' || (decisionFilter === 'NONE' ? !decisions[g.id] : decisions[g.id]?.decision === decisionFilter)) &&
      (!q || g.records.some((r) => `${r.id} ${r.name}`.toLowerCase().includes(q))))
  }, [lanes, view, tier, decisionFilter, query, decisions])
  useEffect(() => setPage(0), [view, tier, decisionFilter, query])

  const setDecision = (gid, d) => setDecisions((cur) => { const n = { ...cur }; if (d && d.decision) n[gid] = d; else delete n[gid]; return n })
  async function download() {
    setBusy(true)
    try { await downloadScanExcel(id) } catch (e) { setError(e.message) }
    setBusy(false)
  }

  if (error && !data) {
    return (
      <section className="panel unavailable-result" role="alert">
        <p className="eyebrow">Result unavailable</p><h1>Scan not available</h1><p>{error}</p>
        <div className="actions"><Link className="button" to={cfg.base}>Return to Dashboard</Link><Link className="button secondary" to={`${cfg.base}/new`}>Start a new scan</Link></div>
      </section>
    )
  }
  if (!data) return <p role="status">Loading scan…</p>

  const st = data.stats
  const dupRecords = new Set(lanes.dup.flatMap((g) => g.records.map((r) => r.id))).size
  const shown = visible.slice(page * PAGE, (page + 1) * PAGE)
  const reviewed = Object.keys(decisions).length

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">Scan results</span>
          <h1>{data.scan.name}</h1>
          <p>Scanned {formatScanTime(data.scan.createdAt)} · {st.suppliers.toLocaleString()} {noun}s loaded</p>
        </div>
        <div className="actions">
          <Link className="button secondary" to={cfg.base}>Dashboard</Link>
          <Link className="button secondary" to={`${cfg.base}/new`}>New Scan</Link>
          <button type="button" onClick={download} disabled={busy}>{busy ? 'Preparing…' : 'Download Excel'}</button>
        </div>
      </header>
      {error && <div className="error" role="alert">{error}</div>}
      {data.missingReports?.length > 0 && <p className="warning">Reports not found, so scoring ran without them: {data.missingReports.join(', ')}.</p>}
      <section className="banner"><b>Advisory candidate workflow.</b> {cfg.plural} that may be the same legal entity are grouped for review; nothing is merged, archived or changed in IFS automatically.</section>

      <section className="panel identity-summary">
        <div className="section-heading"><div><p className="eyebrow">Scan summary</p><h2>Suspected duplicate groups</h2></div>
          <div className="snapshot-meta"><span>{st.eligible.toLocaleString()} eligible · excluded {st.excluded.template} template, {st.excluded.oneTime} one-time, {st.excluded.internal} internal</span></div></div>
        <div className="cards compact-cards">
          <article><label>Tier 1 · Auto-confirm</label><strong>{st.byTier['1'] || 0}</strong></article>
          <article><label>Tier 2 · Steward review</label><strong>{st.byTier['2'] || 0}</strong></article>
          <article><label>Tier 3 · Split / hierarchy</label><strong>{st.byTier['3'] || 0}</strong></article>
          <article><label>Tier 4 · Watchlist</label><strong>{st.byTier['4'] || 0}</strong></article>
          <article><label>{cfg.plural} in duplicate groups</label><strong>{dupRecords}</strong></article>
          <article><label>Groups reviewed</label><strong>{reviewed}</strong><small>of {groups.length}</small></article>
        </div>
      </section>

      <div className="view-toggle" role="tablist">
        {[['dup', 'Duplicate groups', lanes.dup.length], ['hier', 'Functional splits & hierarchy', lanes.hier.length], ['watch', 'Audit watchlist', lanes.watch.length]].map(([k, label, n]) => (
          <button type="button" key={k} role="tab" aria-selected={view === k} className={view === k ? '' : 'secondary'} onClick={() => { setView(k); setTier('ALL') }}>{label} ({n})</button>
        ))}
      </div>

      <section className="panel group-filters">
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search ${noun} id or name…`} aria-label="Search" />
          {view === 'dup' && <select value={tier} onChange={(e) => setTier(e.target.value)} aria-label="Tier"><option value="ALL">All tiers</option><option value="1">Tier 1</option><option value="2">Tier 2</option></select>}
          <select value={decisionFilter} onChange={(e) => setDecisionFilter(e.target.value)} aria-label="Decision">
            <option value="ALL">All decisions</option><option value="NONE">No decision yet</option>{DECISIONS.map((d) => <option key={d}>{d}</option>)}
          </select>
        </div>
      </section>

      <div className="groups">
        {shown.length === 0 ? <div className="panel"><div className="empty">No groups match the filters.</div></div> :
          shown.map((g) => <GroupCard key={g.id} group={g} label={cfg.label} scanId={id} decision={decisions[g.id]} onDecision={setDecision} />)}
      </div>
      {visible.length > PAGE && (
        <nav className="pagination" aria-label="Group pages">
          <button type="button" className="secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span>Page {page + 1} of {Math.ceil(visible.length / PAGE)} · {visible.length} groups</span>
          <button type="button" className="secondary" disabled={(page + 1) * PAGE >= visible.length} onClick={() => setPage((p) => p + 1)}>Next</button>
        </nav>
      )}
    </>
  )
}
