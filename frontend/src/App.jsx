import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppShell from './components/AppShell'
import Dashboard from './pages/Dashboard'
import Environments from './pages/Environments'
import EntityData from './pages/DataSource'
import Duplicates from './pages/Duplicates'
import OAuthCallback from './pages/OAuthCallback'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route element={<AppShell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/environments" element={<Environments />} />
          <Route path="/suppliers" element={<EntityData key="supplier" entityId="supplier" />} />
          <Route path="/customers" element={<EntityData key="customer" entityId="customer" />} />
          <Route path="/data-source" element={<Navigate to="/suppliers" replace />} />
          <Route path="/duplicates" element={<Duplicates />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
