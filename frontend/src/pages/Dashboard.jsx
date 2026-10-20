import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined'
import ContentCopyOutlinedIcon from '@mui/icons-material/ContentCopyOutlined'
import ScheduleOutlinedIcon from '@mui/icons-material/ScheduleOutlined'
import { SCAN_ENTITIES, fetchJson, formatScanTime } from '../lib/scans'

export default function DashboardPage() {
  const [scans, setScans] = useState(null)
  useEffect(() => { fetchJson('/api/spec-dedup/scans').then(setScans, () => setScans([])) }, [])

  const of = (entity) => (scans || []).filter((s) => s.entity === entity)
  const latest = scans?.[0]
  const fmt = (n) => (scans ? n.toLocaleString() : '—')
  const cards = [
    { label: 'Supplier Scans', value: fmt(of('supplier').length), icon: StorageOutlinedIcon, tone: 'accent' },
    { label: 'Customer Scans', value: fmt(of('customer').length), icon: StorageOutlinedIcon, tone: 'success' },
    { label: 'Groups Found', value: fmt((scans || []).reduce((n, s) => n + s.groups, 0)), icon: ContentCopyOutlinedIcon, tone: 'muted' },
    { label: 'Last Scan', value: latest ? formatScanTime(latest.createdAt) : '—', icon: ScheduleOutlinedIcon, tone: 'muted', small: true }
  ]

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">DASHBOARD</span>
          <h1>Supplier &amp; Customer Duplication</h1>
          <p>Add data from Quick Report files or an IFS environment, run a scan, and review suspected duplicates.</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <Link to={`${SCAN_ENTITIES.supplier.base}/new`} className="button">New supplier scan</Link>
          <Link to={`${SCAN_ENTITIES.customer.base}/new`} className="button secondary">New customer scan</Link>
        </div>
      </header>

      <div className="cards">
        {cards.map(({ label, value, icon: Icon, tone, small }) => (
          <article className="stat-card" key={label}>
            <div className="stat-card-head">
              <label>{label}</label>
              <span className={`stat-card-icon tone-${tone}`}><Icon fontSize="small" /></span>
            </div>
            <strong className={small ? 'sm' : ''}>{value}</strong>
          </article>
        ))}
      </div>

      {scans && scans.length === 0 && (
        <div className="panel">
          <div className="empty">No scans yet. Start a supplier or customer scan; every scan is saved with its Excel report.</div>
        </div>
      )}
    </>
  )
}
