import { useMemo, useState } from 'react'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined'

// Technical columns that carry no business meaning.
const HIDDEN = new Set(['luname', 'keyref', 'objgrants'])
const isHidden = (key) => key.startsWith('@odata') || key.startsWith('_') || HIDDEN.has(key.toLowerCase())

const LIST_LIMIT = 300

export function humanize(key) {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\bArray\b/, '')
    .trim()
}

function show(v) {
  if (v === null || v === undefined || v === '') return ''
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

function visibleEntries(record) {
  return Object.entries(record).filter(([k, v]) => !isHidden(k) && show(v) !== '')
}

function childNames(stages, parentPath) {
  const depth = parentPath ? parentPath.split('/').length + 1 : 1
  return Object.keys(stages).filter((k) => {
    if (k === 'general') return false
    const parts = k.split('/')
    if (parts.length === depth) return (!parentPath || k.startsWith(`${parentPath}/`)) && !(parentPath && isDetached(stages, k))
    // Quick report data without the parent's address (e.g. contacts) is shown at the supplier level instead
    return !parentPath && parts.length > depth && isDetached(stages, k)
  })
}

function isDetached(stages, key) {
  const records = stages[key].records
  return records.length > 0 && records.every((r) => r._parent === undefined && r.AddressId == null)
}

const OWNER_KEYS = ['SupplierId', 'CustomerId', 'Identity'] // all name the supplier / customer
const LINK_KEYS = ['AddressId', 'Company', 'PartyType']

const ownerOf = (r) => OWNER_KEYS.map((k) => r[k]).find((v) => v != null)

// Does `child` belong to `parent`? Uses the parent index tagged by the backend; for data without it (Quick report
// files), matches the owner ID (called SupplierId, CustomerId or Identity depending on the data set) and the shared keys.
function belongsTo(child, parentIdx, parentRecord, rootId) {
  if (child._parent !== undefined) return child._parent === parentIdx
  if (!parentRecord) return false
  const owner = ownerOf(child) ?? child._SupplierId ?? child._CustomerId
  if (owner != null && String(owner) !== String(rootId)) return false
  const shared = LINK_KEYS.filter((k) => child[k] != null && parentRecord[k] != null)
  if (shared.some((k) => String(child[k]) !== String(parentRecord[k]))) return false
  // a record without the parent's address belongs to the supplier itself, not to one of its addresses
  if (parentRecord.AddressId != null && child.AddressId == null) return false
  return owner != null || shared.length > 0
}

function FieldGrid({ record }) {
  const entries = visibleEntries(record)
  if (!entries.length) return <p className="muted">No details.</p>
  return (
    <dl className="field-grid">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt>{humanize(k)}</dt>
          <dd>{show(v)}</dd>
        </div>
      ))}
    </dl>
  )
}

function RecordTable({ records }) {
  const columns = [...new Set(records.flatMap((r) => visibleEntries(r).map(([k]) => k)))]
  return (
    <div className="table-wrap data-table">
      <table className="plain">
        <thead><tr>{columns.map((c) => <th key={c}>{humanize(c)}</th>)}</tr></thead>
        <tbody>
          {records.map((r, i) => (
            <tr key={i}>{columns.map((c) => <td key={c} title={show(r[c])}>{show(r[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function cardTitle(record) {
  const entries = visibleEntries(record)
  const id = entries.find(([k]) => /^addressid$/i.test(k)) || entries.find(([k]) => /id$/i.test(k)) || entries[0]
  const desc = entries.find(([k]) => /^(name|description|address1|address)$/i.test(k) && k !== id?.[0])
  return { title: id ? show(id[1]) : 'Record', subtitle: desc ? show(desc[1]) : '' }
}

// Sections for the data connected to one parent record; recurses into nested relations.
function Relations({ stages, parentPath, parentIdx, parentRecord, rootId, level = 0 }) {
  const empty = []
  const sections = []
  for (const key of childNames(stages, parentPath)) {
    const all = stages[key].records
    const records = all.map((r, index) => ({ r, index })).filter(({ r }) => belongsTo(r, parentIdx, parentRecord, rootId))
    const label = humanize(key.split('/').pop())
    if (!records.length) {
      empty.push(label)
      continue
    }
    const nested = childNames(stages, key)
    sections.push(
      <details key={key} className={`rel-section level-${Math.min(level, 2)}`} open={level === 0}>
        <summary>
          <span>{label}</span>
          <small>{records.length}</small>
        </summary>
        <div className="rel-body">
          {nested.length ? (
            records.map(({ r, index }) => {
              const { title, subtitle } = cardTitle(r)
              return (
                <div key={index} className="rel-card">
                  <div className="rel-card-head">
                    <strong>{title}</strong>
                    {subtitle && <span className="muted">{subtitle}</span>}
                  </div>
                  <FieldGrid record={r} />
                  <Relations stages={stages} parentPath={key} parentIdx={index} parentRecord={r} rootId={rootId} level={level + 1} />
                </div>
              )
            })
          ) : records.length === 1 ? (
            <FieldGrid record={records[0].r} />
          ) : (
            <RecordTable records={records.map(({ r }) => r)} />
          )}
        </div>
      </details>
    )
  }
  return (
    <>
      {sections}
      {level === 0 && empty.length > 0 && (
        <p className="muted rel-empty">No data for: {empty.join(', ')}</p>
      )}
    </>
  )
}

// Master/detail view: pick a supplier or customer (ID + name) and see everything connected to it underneath.
export default function RecordBrowser({ entity, result, actions }) {
  const stages = result.stages
  const general = stages.general.records
  const idKey = `${entity.label}Id`
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(0)

  const nameOf = (r) => show(r.Name ?? r.name ?? r.Description ?? '')
  const list = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = general.map((r, index) => ({ r, index }))
    return q ? all.filter(({ r }) => show(r[idKey]).toLowerCase().includes(q) || nameOf(r).toLowerCase().includes(q)) : all
  }, [general, query, idKey])

  const failed = Object.entries(stages).filter(([, s]) => s.errors.length)
  const current = general[selected]

  return (
    <div className="panel">
      <div className="section-heading">
        <div><span className="eyebrow">RESULT</span><h2>{general.length.toLocaleString()} {entity.label.toLowerCase()}s</h2></div>
        {actions}
      </div>
      {failed.length > 0 && (
        <div className="auth-banner error" style={{ display: 'block' }}>
          <ErrorOutlineIcon fontSize="small" /> Some related data could not be loaded:
          <ul style={{ margin: '6px 0 0 18px' }}>
            {failed.map(([k, s]) => (
              <li key={k}>{humanize(k.split('/').pop())}: {s.errors[0].error}{s.errors.length > 1 ? ` (+${s.errors.length - 1} more)` : ''}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="master-detail">
        <div className="master-list">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={`Search ${entity.label.toLowerCase()} ID or name…`} aria-label="Search" />
          <div className="master-items">
            {list.slice(0, LIST_LIMIT).map(({ r, index }) => (
              <button key={index} className={`master-item ${index === selected ? 'active' : ''}`} onClick={() => setSelected(index)}>
                <strong>{show(r[idKey])}</strong>
                <span>{nameOf(r) || '—'}</span>
              </button>
            ))}
            {list.length > LIST_LIMIT && <p className="muted" style={{ fontSize: 12, padding: 8 }}>Showing {LIST_LIMIT} of {list.length.toLocaleString()}. Refine the search.</p>}
            {!list.length && <p className="muted" style={{ padding: 8 }}>No matches.</p>}
          </div>
        </div>

        <div className="master-detail-pane">
          {current ? (
            <>
              <header className="detail-head">
                <div>
                  <span className="eyebrow">{entity.label.toUpperCase()}</span>
                  <h3>{nameOf(current) || show(current[idKey])}</h3>
                </div>
                <span className="badge LOW">{show(current[idKey])}</span>
              </header>
              <details className="rel-section level-0" open>
                <summary><span>General information</span></summary>
                <div className="rel-body"><FieldGrid record={current} /></div>
              </details>
              <Relations stages={stages} parentPath="" parentIdx={selected} parentRecord={current} rootId={current[idKey]} />
            </>
          ) : (
            <div className="empty">No {entity.label.toLowerCase()} records.</div>
          )}
        </div>
      </div>
    </div>
  )
}
