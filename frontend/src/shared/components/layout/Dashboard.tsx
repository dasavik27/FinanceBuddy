import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Box, CircularProgress } from '@mui/material'
import { ErrorBoundary }    from '../ui'
import { useAppStore } from '../../store/appStore'

// Route-level code splitting. These were static imports, which meant every
// domain — including the whole tax-expert tree and its five tabs — landed in the
// single entry chunk and was downloaded even by users who only ever open Mutual
// Funds. Each domain now resolves to its own lazily fetched chunk.
const MutualFundsDashboard = lazy(() => import('../../../domains/mutual-funds/components/MutualFundsDashboard'))
const IndianStocksDashboard = lazy(() => import('../../../domains/equity/components/IndianStocksDashboard'))
const TaxExpertDashboard = lazy(() => import('../../../domains/tax-expert/components/TaxExpertDashboard'))
const AccountsDashboard = lazy(() => import('../dashboard/AccountsDashboard'))
const DashboardHub = lazy(() => import('../dashboard/DashboardHub'))
const BudgetDashboard = lazy(() => import('../../../domains/budget/components/BudgetDashboard'))
const AdminConsole = lazy(() => import('../admin/AdminConsole'))

function RouteFallback() {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <CircularProgress sx={{ color: '#6366F1' }} />
    </Box>
  )
}

/**
 * Rewrites a legacy /dashboard/<rest> URL to /<rest>.
 *
 * Domains used to be mounted under /dashboard (so /dashboard/equity). They are now
 * top-level, but old bookmarks, browser history and any link shared before the change
 * still point at the nested form, and a bare 404 there is a worse experience than a
 * redirect. Preserves the query string and hash so a deep link keeps its state.
 */
function LegacyDashboardRedirect() {
  const location = useLocation()
  const rest = location.pathname.replace(/^\/dashboard/, '') || '/'
  return <Navigate to={`${rest}${location.search}${location.hash}`} replace />
}

/** UI-only gate; APIs still enforce admin. Stops non-admins opening the console shell. */
function AdminOnly() {
  const role = useAppStore((s) => s.role)
  if (role !== 'admin') {
    return <Navigate to="/dashboard" replace />
  }
  return (
    <ErrorBoundary fallbackMessage="Admin Console encountered an error.">
      <AdminConsole />
    </ErrorBoundary>
  )
}

export default function Dashboard() {
  return (
    <Box>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          {/* The hub. Keeps the /dashboard path because that is what it is - the
              others are domains and now say so in their own URL. */}
          <Route path="dashboard"        element={<ErrorBoundary fallbackMessage="Hub encountered an error."><DashboardHub /></ErrorBoundary>} />

          <Route path="mutual-funds/*"   element={<ErrorBoundary fallbackMessage="Mutual Funds section encountered an error."><MutualFundsDashboard /></ErrorBoundary>} />
          <Route path="equity/*"         element={<ErrorBoundary fallbackMessage="Indian Stocks section encountered an error."><IndianStocksDashboard /></ErrorBoundary>} />
          <Route path="tax-expert/*"     element={<ErrorBoundary fallbackMessage="Tax Expert section encountered an error."><TaxExpertDashboard /></ErrorBoundary>} />
          <Route path="budget/*"         element={<ErrorBoundary fallbackMessage="Budget Analyzer section encountered an error."><BudgetDashboard /></ErrorBoundary>} />
          <Route path="accounts"         element={<ErrorBoundary fallbackMessage="Accounts Vault encountered an error."><AccountsDashboard /></ErrorBoundary>} />
          <Route path="admin"            element={<AdminOnly />} />

          {/* Legacy /dashboard/<domain> URLs. Ranked below the static "dashboard"
              route above, so the bare hub path is not swallowed by this. */}
          <Route path="dashboard/*"      element={<LegacyDashboardRedirect />} />

          {/* Legacy flat MF tab URLs, from before the domain split. */}
          <Route path="holdings"     element={<Navigate to="/mutual-funds/holdings" replace />} />
          <Route path="performance"  element={<Navigate to="/mutual-funds/performance" replace />} />
          <Route path="compare"      element={<Navigate to="/mutual-funds/compare" replace />} />
          <Route path="insights"     element={<Navigate to="/mutual-funds/insights" replace />} />
          <Route path="rebalance"    element={<Navigate to="/mutual-funds/insights" replace />} />
          <Route path="tax"          element={<Navigate to="/tax-expert" replace />} />
          <Route path="journey"      element={<Navigate to="/mutual-funds/journey" replace />} />
          <Route path="account"      element={<Navigate to="/mutual-funds/account" replace />} />

          {/* Unknown path lands on the hub rather than a domain: with four domains,
              guessing Mutual Funds is wrong three times out of four. */}
          <Route path="*"            element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Suspense>
    </Box>
  )
}
