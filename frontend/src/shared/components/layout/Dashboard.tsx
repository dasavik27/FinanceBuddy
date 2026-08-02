import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box, CircularProgress } from '@mui/material'
import { ErrorBoundary }    from '../ui'

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

function RouteFallback() {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
      <CircularProgress sx={{ color: '#6366F1' }} />
    </Box>
  )
}

export default function Dashboard() {
  return (
    <Box>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route index element={<ErrorBoundary fallbackMessage="Hub encountered an error."><DashboardHub /></ErrorBoundary>} />
          <Route path="mutual-funds/*" element={<ErrorBoundary fallbackMessage="Mutual Funds section encountered an error."><MutualFundsDashboard /></ErrorBoundary>} />
          <Route path="equity/*"        element={<ErrorBoundary fallbackMessage="Indian Stocks section encountered an error."><IndianStocksDashboard /></ErrorBoundary>} />
          <Route path="tax-expert/*"     element={<ErrorBoundary fallbackMessage="Tax Expert section encountered an error."><TaxExpertDashboard /></ErrorBoundary>} />
          <Route path="budget/*"         element={<ErrorBoundary fallbackMessage="Budget Analyzer section encountered an error."><BudgetDashboard /></ErrorBoundary>} />
          <Route path="accounts"         element={<ErrorBoundary fallbackMessage="Accounts Vault encountered an error."><AccountsDashboard /></ErrorBoundary>} />

          {/* Legacy redirect catches */}
          <Route path="holdings"     element={<Navigate to="/dashboard/mutual-funds/holdings" replace />} />
          <Route path="performance"  element={<Navigate to="/dashboard/mutual-funds/performance" replace />} />
          <Route path="compare"      element={<Navigate to="/dashboard/mutual-funds/compare" replace />} />
          <Route path="insights"     element={<Navigate to="/dashboard/mutual-funds/insights" replace />} />
          <Route path="rebalance"    element={<Navigate to="/dashboard/mutual-funds/insights" replace />} />
          <Route path="tax"          element={<Navigate to="/dashboard/tax-expert" replace />} />
          <Route path="journey"      element={<Navigate to="/dashboard/mutual-funds/journey" replace />} />
          <Route path="account"      element={<Navigate to="/dashboard/mutual-funds/account" replace />} />
          <Route path="*"            element={<Navigate to="/dashboard/mutual-funds" replace />} />
        </Routes>
      </Suspense>
    </Box>
  )
}
