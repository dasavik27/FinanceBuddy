import { Routes, Route, Navigate } from 'react-router-dom'
import { Box } from '@mui/material'
import MutualFundsDashboard from '../dashboard/MutualFundsDashboard'
import IndianStocksDashboard  from '../dashboard/IndianStocksDashboard'
import TaxExpertDashboard     from '../dashboard/TaxExpertDashboard'
import AccountsDashboard      from '../dashboard/AccountsDashboard'
import DashboardHub         from '../dashboard/DashboardHub'
import { ErrorBoundary }    from '../ui'

export default function Dashboard() {
  return (
    <Box>
      <Routes>
        <Route index element={<ErrorBoundary fallbackMessage="Hub encountered an error."><DashboardHub /></ErrorBoundary>} />
        <Route path="mutual-funds/*" element={<ErrorBoundary fallbackMessage="Mutual Funds section encountered an error."><MutualFundsDashboard /></ErrorBoundary>} />
        <Route path="indian-stocks/*"  element={<ErrorBoundary fallbackMessage="Indian Stocks section encountered an error."><IndianStocksDashboard /></ErrorBoundary>} />
        <Route path="tax-expert/*"     element={<ErrorBoundary fallbackMessage="Tax Expert section encountered an error."><TaxExpertDashboard /></ErrorBoundary>} />
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
    </Box>
  )
}
