import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/AppShell'
import Dashboard from './pages/Dashboard'
import Environments from './pages/Environments'
import Scans from './pages/Scans'
import NewScan from './pages/NewScan'
import ScanResults from './pages/ScanResults'
import OAuthCallback from './pages/OAuthCallback'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/environments" element={<Environments />} />
          <Route path="/supplier-scans" element={<Scans entity="supplier" />} />
          <Route path="/supplier-scans/new" element={<NewScan entity="supplier" />} />
          <Route path="/supplier-scans/:id" element={<ScanResults entity="supplier" />} />
          <Route path="/customer-scans" element={<Scans entity="customer" />} />
          <Route path="/customer-scans/new" element={<NewScan entity="customer" />} />
          <Route path="/customer-scans/:id" element={<ScanResults entity="customer" />} />
          <Route path="/suppliers" element={<Navigate to="/supplier-scans" replace />} />
          <Route path="/customers" element={<Navigate to="/customer-scans" replace />} />
          <Route path="/duplicates" element={<Navigate to="/supplier-scans" replace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
