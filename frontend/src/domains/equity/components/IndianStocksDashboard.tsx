import { useEffect } from 'react'
import { Box } from '@mui/material'
import { useAppStore, useEquitySessionId } from '../../../shared/store/appStore'
import { ErrorBoundary } from '../../../shared/components/ui'
import EquityDashboard from './EquityDashboard'
import EquityUploadPanel from './EquityUploadPanel'

export default function IndianStocksDashboard() {
  const setActiveModule = useAppStore((s) => s.setActiveModule)
  const sessionId = useEquitySessionId()

  useEffect(() => {
    setActiveModule('indian_stocks')
  }, [setActiveModule])

  return (
    <Box>
      <ErrorBoundary fallbackMessage="Equity Dashboard encountered an error.">
        {sessionId ? (
          <EquityDashboard />
        ) : (
          <EquityUploadPanel />
        )}
      </ErrorBoundary>
    </Box>
  )
}
