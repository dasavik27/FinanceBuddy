import { useEffect } from 'react'
import { Box } from '@mui/material'
import { useAppStore, useEquitySessionId } from '../../../shared/store/appStore'
import { ErrorBoundary } from '../../../shared/components/ui'
import EquityDashboard from './EquityDashboard'
import { KiteOAuthOverlay, useKiteOAuthCallback } from '../hooks/useKiteOAuthCallback'

export default function IndianStocksDashboard() {
  const setActiveModule = useAppStore((s) => s.setActiveModule)
  const sessionId = useEquitySessionId()
  // Always mounted for /equity/* so Zerodha redirects complete even on Analyzer
  // or when an existing session hides EquityUploadPanel.
  const { syncState, error, clearError } = useKiteOAuthCallback()

  useEffect(() => {
    setActiveModule('indian_stocks')
  }, [setActiveModule])

  return (
    <Box>
      <KiteOAuthOverlay syncState={syncState} error={error} onDismissError={clearError} />
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
