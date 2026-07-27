import { useEffect } from 'react'
import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Box, Tabs, Tab, Paper } from '@mui/material'
import { useMfSessionId, useAppStore } from '../../store/appStore'
import DocumentUpload from './DocumentUpload'
import OverviewTab    from '../tabs/OverviewTab'
import HoldingsTab    from '../tabs/HoldingsTab'
import PerformanceTab from '../tabs/PerformanceTab'
import CompareTab     from '../tabs/CompareTab'
import InsightsRebalanceTab from '../tabs/InsightsRebalanceTab'
import JourneyTab from '../tabs/JourneyTab'
import { ErrorBoundary } from '../ui'

export default function MutualFundsDashboard() {
  const location = useLocation()
  const navigate = useNavigate()
  const sid = useMfSessionId()
  const setActiveModule = useAppStore((s) => s.setActiveModule)

  useEffect(() => {
    setActiveModule('mutual_funds')
  }, [setActiveModule])

  if (!sid) {
    return (
      <DocumentUpload 
        title="Import Your Mutual Funds"
        subtitle="Upload your detailed CAS PDF statement to generate your executive cockpit."
        dropText="Drag & drop your CAS PDF"
        dropSubText="or click anywhere in this box to browse from your device"
        uploadType="mutual_funds"
      />
    )
  }

  // Derive current tab from pathname
  const pathParts = location.pathname.split('/')
  const currentTab = pathParts[pathParts.length - 1]
  const tabValue = ['overview', 'holdings', 'performance', 'compare', 'journey', 'insights'].includes(currentTab) 
    ? currentTab 
    : 'overview'

  const handleTabChange = (_event: React.SyntheticEvent, newValue: string) => {
    navigate(`/dashboard/mutual-funds/${newValue}`)
  }

  return (
    <Box>
      <Paper 
        className="glass" 
        sx={{ 
          mb: 4, 
          borderRadius: '16px', 
          border: '1px solid rgba(255,255,255,0.05)',
          background: 'rgba(255,255,255,0.02)' 
        }}
      >
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
              fontSize: '0.95rem',
            },
            '& .MuiTabs-indicator': {
              height: 3,
              borderRadius: '3px 3px 0 0'
            }
          }}
        >
          <Tab label="Overview" value="overview" />
          <Tab label="Holdings" value="holdings" />
          <Tab label="Performance" value="performance" />
          <Tab label="Compare" value="compare" />
          <Tab label="Wealth Journey" value="journey" />
          <Tab label="Insights & Rebalance" value="insights" />
        </Tabs>
      </Paper>

      <Routes>
        <Route index               element={<Navigate to="/dashboard/mutual-funds/overview" replace />} />
        <Route path="overview"     element={<ErrorBoundary fallbackMessage="Overview tab encountered a rendering error."><OverviewTab /></ErrorBoundary>} />
        <Route path="holdings"     element={<ErrorBoundary fallbackMessage="Holdings tab encountered a rendering error."><HoldingsTab /></ErrorBoundary>} />
        <Route path="performance"  element={<ErrorBoundary fallbackMessage="Performance tab encountered a rendering error."><PerformanceTab /></ErrorBoundary>} />
        <Route path="compare"      element={<ErrorBoundary fallbackMessage="Compare tab encountered a rendering error."><CompareTab /></ErrorBoundary>} />
        <Route path="journey"      element={<ErrorBoundary fallbackMessage="Journey tab encountered a rendering error."><JourneyTab /></ErrorBoundary>} />
        <Route path="insights"     element={<ErrorBoundary fallbackMessage="Insights & Rebalance tab encountered a rendering error."><InsightsRebalanceTab /></ErrorBoundary>} />
        <Route path="*"            element={<Navigate to="/dashboard/mutual-funds/overview" replace />} />
      </Routes>
    </Box>
  )
}

