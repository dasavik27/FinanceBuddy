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
      {/*
        The dashboard renders with or without a portfolio. It used to be gated entirely
        behind `sessionId`, which put the Stock Analyzer — the one feature here that
        needs no holdings at all — behind uploading a broker statement. A new user had
        nothing to look at until they had a file to hand. The portfolio *tabs* still
        need a session and show the upload panel themselves.
      */}
      <ErrorBoundary fallbackMessage="Equity Dashboard encountered an error.">
        <EquityDashboard hasSession={Boolean(sessionId)} />
      </ErrorBoundary>
    </Box>
  )
}
