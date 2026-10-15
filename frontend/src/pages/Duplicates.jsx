import { useMemo, useState } from 'react'
import { ENTITIES, FIELDS } from '../lib/entities'

const STATUS_LABEL = { open: 'Open', confirmed: 'Confirmed', dismissed: 'Dismissed' }

export default function DuplicatesPage() {
  const [groups, setGroups] = useState([]) // filled once duplicate matching is implemented
  const [entity, setEntity] = useState('supplier')
  const [confidence, setConfidence] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState(null)

  const idKey = ENTITIES.find((e) => e.id === entity).idKey

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return groups.filter(
      (g) =>
        g.entity === entity &&
        (confidence === 'ALL' || g.confidence === confidence) &&
        (statusFilter === 'ALL' || g.status === statusFilter) &&
        (!q || g.records.some((r) => Object.values(r).some((v) => String(v).toLowerCase().includes(q))))
    )
  }, [groups, entity, confidence, statusFilter, query])

  const selected = visible.find((g) => g.id === selectedId) || visible[0] || null
  const countFor = (id) => groups.filter((g) => g.entity === id).length

  function setStatus(id, status) {
    setGroups((gs) => gs.map((g) => (g.id === id ? { ...g, status } : g)))
  }

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">DUPLICATE REVIEW</span>
          <h1>Suspected Duplicates</h1>
          <p>Compare matching records side by side, then confirm or dismiss each group.</p>
        </div>
      </header>

      <div className="tabs">
        {ENTITIES.map((e) => (
          <button key={e.id} className={`tab ${entity === e.id ? 'active' : ''}`} onClick={() => { setEntity(e.id); setSelectedId(null) }}>
            {e.label}s<small>{countFor(e.id)}</small>
          </button>
        ))}
      </div>

      <div className="toolbar">
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name, tax no., ID…" aria-label="Search" />
        <select value={confidence} onChange={(e) => setConfidence(e.target.value)} aria-label="Confidence">
          <option value="ALL">All confidence</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Status">
          <option value="ALL">All statuses</option>
          <option value="open">Open</option>
          <option value="confirmed">Confirmed</option>
          <option value="dismissed">Dismissed</option>
        </select>
      </div>

      {visible.length === 0 ? (
        <div className="panel"><div className="empty">No duplicate groups yet. Matching runs on fetched data once it is configured.</div></div>
      ) : (
        <div className="dup-layout">
          <div className="dup-list">
            {visible.map((g) => (
              <button key={g.id} className={`dup-item ${selected?.id === g.id ? 'active' : ''}`} onClick={() => setSelectedId(g.id)}>
                <span className="dup-item-top">
                  <strong>{g.records[0].name}</strong>
                  <span className={`badge ${g.confidence}`}>{g.score}%</span>
                </span>
                <small>{g.records.length} records · {g.reasons[0]}</small>
                <span><span className={`badge status-pill ${g.status}`}>{STATUS_LABEL[g.status]}</span></span>
              </button>
            ))}
          </div>

          {selected && (
            <div className="dup-detail">
              <div className="panel" style={{ marginBottom: 0 }}>
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">GROUP {selected.id}</span>
                    <h2>{selected.records[0].name}</h2>
                    <p className="muted" style={{ margin: '6px 0 0', fontSize: 13 }}>{selected.reasons.join(' · ')}</p>
                  </div>
                  <span className={`badge ${selected.confidence}`}>{selected.confidence} · {selected.score}%</span>
                </div>

                <div className="compare">
                  <table>
                    <thead>
                      <tr>
                        <th>Field</th>
                        {selected.records.map((r, i) => (
                          <th key={r[idKey]}>{r[idKey]}{i === 0 && <span className="master">MASTER</span>}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {FIELDS[entity].map(([key, label]) => {
                        const values = selected.records.map((r) => r[key] || '')
                        const same = values.every((v) => v === values[0])
                        return (
                          <tr key={key}>
                            <td className="field">{label}</td>
                            {values.map((v, i) => (
                              <td key={i} className={same ? 'same' : 'diff'}>{v || <span className="muted">—</span>}</td>
                            ))}
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="actions">
                  <button className="ghost" onClick={() => setStatus(selected.id, 'dismissed')} disabled={selected.status === 'dismissed'}>Not a duplicate</button>
                  <button onClick={() => setStatus(selected.id, 'confirmed')} disabled={selected.status === 'confirmed'}>Confirm duplicate</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  )
}
