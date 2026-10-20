import { Link, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined'
import SettingsEthernetIcon from '@mui/icons-material/SettingsEthernet'
import FactCheckOutlinedIcon from '@mui/icons-material/FactCheckOutlined'
import MenuIcon from '@mui/icons-material/Menu'
import CloseIcon from '@mui/icons-material/Close'

const NAV = [
  { href: '/', label: 'Dashboard', icon: DashboardOutlinedIcon },
  { href: '/environments', label: 'Environments', icon: SettingsEthernetIcon },
  { href: '/supplier-scans', label: 'Supplier Scans', icon: FactCheckOutlinedIcon },
  { href: '/customer-scans', label: 'Customer Scans', icon: FactCheckOutlinedIcon },
]

export default function AppShell() {
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e) => e.key === 'Escape' && setMenuOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [menuOpen])

  return (
    <div className={`shell ${menuOpen ? 'sidebar-open' : ''}`}>
      <aside className="app-sidebar" id="app-navigation" aria-label="Main navigation">
        <div className="brand">
          <img src="/sebsa-logo.png" alt="SEBSA" className="brand-logo" />
        </div>
        <nav className="app-nav">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} to={href} onClick={() => setMenuOpen(false)} className={pathname === href || (href !== '/' && pathname.startsWith(href + '/')) ? 'active' : ''}>
              <Icon fontSize="small" /> {label}
            </Link>
          ))}
        </nav>
      </aside>
      <button type="button" className="app-sidebar-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />
      <button
        type="button"
        className="app-menu-toggle"
        aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
        aria-expanded={menuOpen}
        aria-controls="app-navigation"
        onClick={() => setMenuOpen((o) => !o)}
      >
        {menuOpen ? <CloseIcon /> : <MenuIcon />}
      </button>
      <div className="app-main-column">
        <div className="app-mobile-toolbar">
          <img src="/sebsa-logo.png" alt="SEBSA" className="brand-logo" />
        </div>
        <main><Outlet /></main>
      </div>
    </div>
  )
}
