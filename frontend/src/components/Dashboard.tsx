import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { Box, Tabs, Tab } from '@mui/material'
import OverviewTab    from './tabs/OverviewTab'
import PerformanceTab from './tabs/PerformanceTab'
import HoldingsTab    from './tabs/HoldingsTab'
import CompareTab     from './tabs/CompareTab'
import TaxTab         from './tabs/TaxTab'
import InsightsTab    from './tabs/InsightsTab'
import SipTab         from './tabs/SipTab'

const TABS = [
  { label: '📊 Overview',       path: '/dashboard' },
  { label: '📈 Performance',    path: '/dashboard/performance' },
  { label: '📋 Holdings',       path: '/dashboard/holdings' },
  { label: '🔀 Compare',        path: '/dashboard/compare' },
  { label: '🧾 Tax',            path: '/dashboard/tax' },
  { label: '💡 Smart Insights', path: '/dashboard/insights' },
  { label: '🔄 SIP Calculator', path: '/dashboard/sip' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const location = useLocation()
  const idx = TABS.findIndex(
    (t) => t.path === location.pathname ||
           (t.path !== '/dashboard' && location.pathname.startsWith(t.path))
  )
  const activeIdx = idx < 0 ? 0 : idx

  return (
    <Box>
      <Tabs
        value={activeIdx}
        onChange={(_, v) => navigate(TABS[v].path)}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ mb: 3, boxShadow: '0 1px 2px rgba(15,23,42,0.04), 0 1px 6px rgba(15,23,42,0.06)' }}
      >
        {TABS.map((t) => (
          <Tab key={t.path} label={t.label} sx={{ whiteSpace: 'nowrap' }} />
        ))}
      </Tabs>

      <Routes>
        <Route index               element={<OverviewTab />} />
        <Route path="performance"  element={<PerformanceTab />} />
        <Route path="holdings"     element={<HoldingsTab />} />
        <Route path="compare"      element={<CompareTab />} />
        <Route path="tax"          element={<TaxTab />} />
        <Route path="insights"     element={<InsightsTab />} />
        <Route path="sip"          element={<SipTab />} />
        <Route path="*"            element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Box>
  )
}
