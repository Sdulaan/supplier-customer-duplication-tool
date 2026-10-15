import { Link } from 'react-router-dom'
import StorageOutlinedIcon from '@mui/icons-material/StorageOutlined'
import LinkOutlinedIcon from '@mui/icons-material/LinkOutlined'
import ScheduleOutlinedIcon from '@mui/icons-material/ScheduleOutlined'
import { getFetched, summarize } from '../lib/dataStore'

export default function DashboardPage() {
  const fetched = getFetched()
  const sum = summarize(fetched)
  const fmt = (n) => (n == null ? '—' : n.toLocaleString())

  const cards = [
    { label: 'Suppliers Fetched', value: fmt(sum.entities.supplier), icon: StorageOutlinedIcon, tone: 'accent' },
    { label: 'Customers Fetched', value: fmt(sum.entities.customer), icon: StorageOutlinedIcon, tone: 'success' },
    { label: 'Related Records', value: fetched ? fmt(sum.related) : '—', icon: LinkOutlinedIcon, tone: 'muted' },
    { label: 'Last Fetch', value: sum.fetchedAt ? new Date(sum.fetchedAt).toLocaleString() : '—', icon: ScheduleOutlinedIcon, tone: 'muted', small: true }
  ]

  return (
    <>
      <header className="page-head">
        <div>
          <span className="eyebrow">DASHBOARD</span>
          <h1>Supplier &amp; Customer Duplication</h1>
          <p>Authorize an environment, fetch supplier and customer data, and review suspected duplicates.</p>
        </div>
        <Link to="/data-source" className="button">Fetch data</Link>
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

      {!fetched && (
        <div className="panel">
          <div className="empty">No data fetched yet. Set up an environment, then fetch from Data Source.</div>
        </div>
      )}
    </>
  )
}
