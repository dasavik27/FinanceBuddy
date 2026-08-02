import { Suspense, lazy, useEffect } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Box, Tabs, Tab, Paper, Typography } from '@mui/material'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import { useMfSessionId, useAppStore } from '../../../shared/store/appStore'
import MFUploadPanel from './MFUploadPanel'
import { ErrorBoundary, TabFallback } from '../../../shared/components/ui'

// Tabs are lazy so opening Overview does not also download Compare, Performance and
// Statement History. Route-level splitting already existed one level up, in
// layout/Dashboard.tsx, but every tab was statically imported here — so the whole
// module landed in one 45 KB gzipped (177 KB raw) chunk regardless of which tab the
// user actually visited. CompareTab alone is the largest component in the app.
const OverviewTab    = lazy(() => import('./OverviewTab'))
const HoldingsTab    = lazy(() => import('./HoldingsTab'))
const PerformanceTab = lazy(() => import('./PerformanceTab'))
const CompareTab     = lazy(() => import('./CompareTab'))
const InsightsTab    = lazy(() => import('./InsightsTab'))
const JourneyTab     = lazy(() => import('./JourneyTab'))
const UploadHistory  = lazy(() => import('../../../shared/components/dashboard/UploadHistory'))

export default function MutualFundsDashboard() {
  const location = useLocation()
  const navigate = useNavigate()
  const sid = useMfSessionId()
  const setActiveModule = useAppStore((s) => s.setActiveModule)

  useEffect(() => {
    setActiveModule('mutual_funds')
  }, [setActiveModule])

  // ── No session: show smart upload / history panel ──
  if (!sid) {
    return <MFUploadPanel />
  }

  // ── Session active: full dashboard ──
  const pathParts = location.pathname.split('/')
  const currentTab = pathParts[pathParts.length - 1]
  const tabValue = ['overview', 'holdings', 'performance', 'compare', 'journey', 'insights', 'history'].includes(currentTab)
    ? currentTab
    : 'overview'

  const handleTabChange = (_event: React.SyntheticEvent, newValue: string) => {
    navigate(`/mutual-funds/${newValue}`)
  }

  return (
    <Box>
      <Paper
        className="glass"
        sx={{
          mb: 4,
          borderRadius: '16px',
          border: '1px solid rgba(255,255,255,0.05)',
          background: 'rgba(255,255,255,0.02)',
        }}
      >
        <Box display="flex" alignItems="center" justifyContent="space-between">
          {/* Module identity badge */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, pl: 2, flexShrink: 0 }}>
            <AccountBalanceIcon sx={{ color: '#6366F1', fontSize: 20 }} />
            <Typography sx={{ fontWeight: 800, fontSize: '0.82rem', color: '#475569', letterSpacing: '0.06em', display: { xs: 'none', md: 'block' } }}>
              MUTUAL FUNDS
            </Typography>
          </Box>

          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
            sx={{
              minHeight: 56,
              '& .MuiTab-root': {
                minHeight: 56,
                fontWeight: 700,
                textTransform: 'none',
                fontSize: '0.92rem',
              },
              '& .MuiTabs-indicator': {
                height: 3,
                borderRadius: '3px 3px 0 0',
              },
            }}
          >
            <Tab label="Overview"            value="overview"    />
            <Tab label="Holdings"            value="holdings"    />
            <Tab label="Performance"         value="performance" />
            <Tab label="Compare"             value="compare"     />
            <Tab label="Wealth Journey"      value="journey"     />
            <Tab label="Insights & Rebalance" value="insights"   />
            <Tab label="Statement History"   value="history"     />
          </Tabs>

        </Box>
      </Paper>

      <Suspense fallback={<TabFallback />}>
        <Routes>
          <Route index               element={<Navigate to="/mutual-funds/overview" replace />} />
          <Route path="overview"     element={<ErrorBoundary fallbackMessage="Overview tab encountered a rendering error."><OverviewTab /></ErrorBoundary>} />
          <Route path="holdings"     element={<ErrorBoundary fallbackMessage="Holdings tab encountered a rendering error."><HoldingsTab /></ErrorBoundary>} />
          <Route path="performance"  element={<ErrorBoundary fallbackMessage="Performance tab encountered a rendering error."><PerformanceTab /></ErrorBoundary>} />
          <Route path="compare"      element={<ErrorBoundary fallbackMessage="Compare tab encountered a rendering error."><CompareTab /></ErrorBoundary>} />
          <Route path="journey"      element={<ErrorBoundary fallbackMessage="Journey tab encountered a rendering error."><JourneyTab /></ErrorBoundary>} />
          <Route path="insights"     element={<ErrorBoundary fallbackMessage="Insights & Rebalance tab encountered a rendering error."><InsightsTab /></ErrorBoundary>} />
          <Route path="history"      element={<ErrorBoundary fallbackMessage="Statement History encountered a rendering error."><UploadHistory /></ErrorBoundary>} />
          <Route path="*"            element={<Navigate to="/mutual-funds/overview" replace />} />
        </Routes>
      </Suspense>
    </Box>
  )
}
