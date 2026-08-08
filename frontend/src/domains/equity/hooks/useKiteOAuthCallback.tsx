import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Box, CircularProgress, Typography, Alert } from '@mui/material'
import { AnimatePresence, motion } from 'framer-motion'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'
import { invalidateEquityQueries } from '../../../shared/hooks/invalidateSessionQueries'

/** Must match EquityUploadPanel — parked across the Zerodha redirect. */
export const KITE_STATE_KEY = 'equity.kite.oauth.state'

/**
 * Handles Zerodha Kite OAuth return at the equity (or app) shell level.
 *
 * Previously this lived only inside EquityUploadPanel, so the callback never ran when
 * the user landed on Stock Analyzer, had an existing session, or when Zerodha redirected
 * to a path that did not mount the upload panel.
 */
export function useKiteOAuthCallback() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setSession = useAppStore((s) => s.setSession)
  const [syncState, setSyncState] = useState<'idle' | 'syncing' | 'success'>('idle')
  const [error, setError] = useState<string | null>(null)
  const attemptRef = useRef<string | null>(null)
  const timersRef = useRef<number[]>([])

  const later = useCallback((fn: () => void, ms: number) => {
    const id = window.setTimeout(fn, ms)
    timersRef.current.push(id)
  }, [])

  useEffect(() => () => {
    timersRef.current.forEach(window.clearTimeout)
    timersRef.current = []
  }, [])

  const clearOAuthParams = useCallback(() => {
    const url = new URL(window.location.href)
    url.searchParams.delete('request_token')
    url.searchParams.delete('action')
    url.searchParams.delete('status')
    url.searchParams.delete('state')
    window.history.replaceState({}, document.title, `${url.pathname}${url.search}${url.hash}`)
  }, [])

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const requestToken = urlParams.get('request_token')
    const action = urlParams.get('action')
    const status = urlParams.get('status')
    const state = urlParams.get('state') || sessionStorage.getItem(KITE_STATE_KEY) || ''

    if (!requestToken || action !== 'login') return
    if (status && status !== 'success') {
      setError('Zerodha login was cancelled or failed. Please try again.')
      clearOAuthParams()
      sessionStorage.removeItem(KITE_STATE_KEY)
      return
    }
    if (attemptRef.current === requestToken) return
    attemptRef.current = requestToken

    if (!state) {
      setError('This Zerodha login could not be verified. Please start the connection again.')
      clearOAuthParams()
      return
    }

    // Always land on Equity Overview so the new session tabs are visible.
    if (!window.location.pathname.startsWith('/equity')) {
      navigate(`/equity/overview${window.location.search}`, { replace: true })
    }

    setSyncState('syncing')
    setError(null)
    apiClient.connectKite(requestToken, state)
      .then(async (data) => {
        sessionStorage.removeItem(KITE_STATE_KEY)
        setSession(data.session_id, 'equity', data)
        await invalidateEquityQueries(queryClient)
        setSyncState('success')
        later(() => {
          clearOAuthParams()
          setSyncState('idle')
          navigate('/equity/overview', { replace: true })
        }, 900)
      })
      .catch((err) => {
        setError(err?.response?.data?.detail || 'Kite connect failed')
        setSyncState('idle')
        sessionStorage.removeItem(KITE_STATE_KEY)
        clearOAuthParams()
      })
  }, [setSession, clearOAuthParams, later, navigate, queryClient])

  return { syncState, error, clearError: () => setError(null) }
}

/** Full-page overlay while Kite OAuth completes outside the upload panel. */
export function KiteOAuthOverlay({
  syncState,
  error,
  onDismissError,
}: {
  syncState: 'idle' | 'syncing' | 'success'
  error: string | null
  onDismissError?: () => void
}) {
  if (syncState === 'idle' && !error) return null

  return (
    <Box sx={{
      position: 'fixed', inset: 0, zIndex: 1400,
      bgcolor: 'rgba(7, 12, 24, 0.92)', backdropFilter: 'blur(8px)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      px: 3,
    }}>
      {error ? (
        <Alert
          severity="error"
          onClose={onDismissError}
          sx={{ maxWidth: 480, bgcolor: 'rgba(255,81,106,0.12)', color: '#FF516A', border: '1px solid rgba(255,81,106,0.35)' }}
        >
          {error}
        </Alert>
      ) : (
        <AnimatePresence mode="wait">
          {syncState === 'syncing' ? (
            <motion.div key="sync" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ textAlign: 'center' }}>
              <CircularProgress size={56} thickness={4} sx={{ color: '#10B981', mb: 3 }} />
              <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.35rem' }}>Connecting Zerodha Kite…</Typography>
              <Typography sx={{ color: '#64748B', mt: 1 }}>Fetching holdings and building your equity session.</Typography>
            </motion.div>
          ) : (
            <motion.div key="ok" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }}>
              <CheckCircleIcon sx={{ fontSize: 64, color: '#10B981', display: 'block', mx: 'auto', mb: 2 }} />
              <Typography sx={{ color: '#10B981', fontWeight: 800, fontSize: '1.5rem', textAlign: 'center' }}>Connected</Typography>
            </motion.div>
          )}
        </AnimatePresence>
      )}
    </Box>
  )
}
