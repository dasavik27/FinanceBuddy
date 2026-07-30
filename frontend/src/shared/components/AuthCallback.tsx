/**
 * AuthCallback.tsx
 *
 * Handles the OAuth redirect from Google. Google sends the user back to
 * /auth/callback?code=xxx after they consent. This page:
 *   1. Picks up the `code` from the URL
 *   2. POSTs it to our backend /auth/google/callback
 *   3. If PAN is not yet linked → shows PanLinkScreen
 *   4. If PAN is linked → navigates to /dashboard
 *
 * This is a full-page component — rendered at the /auth/callback route.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Box, CircularProgress, Typography, Alert } from '@mui/material'
import { motion } from 'framer-motion'
import { apiClient } from '../api/client'
import { useAppStore } from '../store/appStore'
import PanLinkScreen from './PanLinkScreen'

export default function AuthCallback() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const setGoogleAuth = useAppStore((s) => s.setGoogleAuth)
  const [error, setError] = useState<string | null>(null)
  const [needsPan, setNeedsPan] = useState(false)
  const [callbackData, setCallbackData] = useState<any>(null)
  const didRun = useRef(false)

  useEffect(() => {
    // Strict mode fires effects twice in dev; guard prevents double token exchange.
    if (didRun.current) return
    didRun.current = true

    const code = searchParams.get('code')
    const errorParam = searchParams.get('error')

    if (errorParam) {
      setError(`Google declined access: ${errorParam}`)
      return
    }
    if (!code) {
      setError('No authorization code received from Google.')
      return
    }

    apiClient.googleCallback(code)
      .then((data) => {
        setCallbackData(data)
        if (!data.pan_linked) {
          // First login — need to collect PAN
          setNeedsPan(true)
        } else {
          // Already linked — store auth and go to dashboard
          setGoogleAuth(data.user, data.access_token, data.refresh_token, data.pan)
          navigate('/dashboard', { replace: true })
        }
      })
      .catch((e) => {
        const detail = e?.response?.data?.detail
        setError(typeof detail === 'string' ? detail : 'Sign-in failed. Please try again.')
      })
  }, [])

  if (error) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', p: 4, background: '#020617' }}>
        <Alert severity="error" sx={{ maxWidth: 480, borderRadius: '16px', fontWeight: 600 }}>{error}</Alert>
        <Typography
          onClick={() => navigate('/', { replace: true })}
          sx={{ mt: 3, color: '#6366F1', fontWeight: 700, cursor: 'pointer', '&:hover': { textDecoration: 'underline' } }}
        >
          ← Back to Login
        </Typography>
      </Box>
    )
  }

  if (needsPan && callbackData) {
    return (
      <PanLinkScreen
        refreshToken={callbackData.refresh_token}
        user={callbackData.user}
        onLinked={(data) => {
          setGoogleAuth(callbackData.user, data.access_token, data.refresh_token, data.pan)
          navigate('/dashboard', { replace: true })
        }}
      />
    )
  }

  // Loading state
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)' }}>
      <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}>
        <Box sx={{ textAlign: 'center' }}>
          <CircularProgress sx={{ color: '#6366F1', mb: 3 }} size={48} />
          <Typography sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '1rem' }}>
            Completing sign-in...
          </Typography>
          <Typography sx={{ color: '#475569', fontSize: '0.85rem', mt: 1 }}>
            Verifying your Google account
          </Typography>
        </Box>
      </motion.div>
    </Box>
  )
}
