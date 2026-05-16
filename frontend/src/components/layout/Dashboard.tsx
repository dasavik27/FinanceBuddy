import { Routes, Route, Navigate } from 'react-router-dom'
import { Box } from '@mui/material'
import OverviewTab    from '../tabs/OverviewTab'
import HoldingsTab    from '../tabs/HoldingsTab'
import PerformanceTab from '../tabs/PerformanceTab'
import CompareTab     from '../tabs/CompareTab'
import InsightsRebalanceTab from '../tabs/InsightsRebalanceTab'
import TaxStrategyTab from '../tabs/TaxStrategyTab'
import { ErrorBoundary } from '../ui'

export default function Dashboard() {

  return (
    <Box>
      <Routes>
        <Route index               element={<ErrorBoundary fallbackMessage="Overview tab encountered a rendering error."><OverviewTab /></ErrorBoundary>} />
        <Route path="holdings"     element={<ErrorBoundary fallbackMessage="Holdings tab encountered a rendering error."><HoldingsTab /></ErrorBoundary>} />
        <Route path="performance"  element={<ErrorBoundary fallbackMessage="Performance tab encountered a rendering error."><PerformanceTab /></ErrorBoundary>} />
        <Route path="rebalance"    element={<Navigate to="/dashboard/insights?tab=rebalance" replace />} />
        <Route path="compare"      element={<ErrorBoundary fallbackMessage="Compare tab encountered a rendering error."><CompareTab /></ErrorBoundary>} />
        <Route path="insights"     element={<ErrorBoundary fallbackMessage="Insights & Rebalance tab encountered a rendering error."><InsightsRebalanceTab /></ErrorBoundary>} />
        <Route path="tax"          element={<ErrorBoundary fallbackMessage="Tax Strategy tab encountered a rendering error."><TaxStrategyTab /></ErrorBoundary>} />
        <Route path="*"            element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Box>
  )
}
