import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Button, TextField, Alert, CircularProgress,
  Collapse, GlobalStyles, Paper
} from '@mui/material'
import LockIcon         from '@mui/icons-material/Lock'
import TrendingUpIcon   from '@mui/icons-material/TrendingUp'
import api              from '../api/client'
import { useAppStore }  from '../store/appStore'
import authClient       from '../auth/authClient'

/** Google's mark, inline so it needs no network request and no extra package. */
const GoogleMark = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
    <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
    <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z" />
    <path fill="#FBBC05" d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z" />
    <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z" />
  </svg>
)

// The two entrance animations, as CSS. `prefers-reduced-motion` is honoured, which
// the framer-motion version did not do.
const landingAnimations = (
  <GlobalStyles styles={{
    '@keyframes fbRiseIn': {
      from: { opacity: 0, transform: 'translateY(20px)' },
      to:   { opacity: 1, transform: 'translateY(0)' },
    },
    '@media (prefers-reduced-motion: reduce)': {
      '*': { animation: 'none !important', transition: 'none !important' },
    },
  }} />
)

export default function Landing() {
  const [loginPan, setLoginPan] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)
  const setIdentity = useAppStore((s) => s.setIdentity)
  const navigate = useNavigate()

  const handleGoogleSignIn = async () => {
    setLoading(true); setError(null)
    try {
      // Redirects away; nothing after this runs on success.
      await authClient.signInWithGoogle()
    } catch (e: any) {
      setError(e?.message ?? 'Could not start sign-in.')
      setLoading(false)
    }
  }

  const handleLogin = async () => {
    if (!loginPan || loginPan.length !== 10) return setError("Please enter a valid 10-character PAN.")
    setLoading(true); setError(null)
    try {
      const res = await api.post('/auth/login', { pan: loginPan })
      setIdentity({ userId: res.data.user_id, pan: res.data.pan })
      navigate('/dashboard')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to login.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, md: 4 },
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {landingAnimations}

      {/* Dynamic Background Glows */}
      <Box sx={{ position: 'absolute', top: '-10%', left: '10%', width: 600, height: 600, background: 'radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', bottom: '-20%', right: '10%', width: 700, height: 700, background: 'radial-gradient(circle, rgba(16,185,129,0.06) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', top: '30%', left: '50%', transform: 'translateX(-50%)', width: 800, height: 800, background: 'radial-gradient(circle, rgba(139,92,246,0.04) 0%, transparent 70%)', filter: 'blur(100px)', pointerEvents: 'none' }} />

      {/* Hero Section */}
      <Box sx={{ zIndex: 1, width: '100%', animation: 'fbRiseIn 600ms cubic-bezier(0.16,1,0.3,1) both' }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          {/* Main App Badge */}
          <Box
            sx={{
              width: 72, height: 72, borderRadius: '24px', mx: 'auto', mb: 3.5,
              background: 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 12px 35px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <TrendingUpIcon sx={{ fontSize: 38, color: '#38BDF8' }} />
          </Box>

          <Typography
            variant="h1"
            sx={{
              background: 'linear-gradient(180deg, #FFFFFF 0%, #94A3B8 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              mb: 1.5,
              fontWeight: 900,
              letterSpacing: '-0.02em',
              lineHeight: 1.1,
              fontSize: { xs: '3rem', md: '4.5rem' }
            }}
          >
            Finance Buddy
          </Typography>

          <Typography 
            variant="h6" 
            sx={{ 
              color: '#38BDF8', 
              fontWeight: 700, 
              letterSpacing: '0.15em', 
              textTransform: 'uppercase',
              mb: 3
            }}
          >
            One PAN. Total Financial Control.
          </Typography>

          <Typography variant="body1" sx={{ color: '#94A3B8', maxWidth: 600, mx: 'auto', lineHeight: 1.8, fontSize: '1.1rem' }}>
            Enter your PAN to instantly unlock your unified wealth dashboard. 
            Experience institutional-grade analytics spanning <strong style={{ color: '#F8FAFC' }}>Indian Stocks, Mutual Funds, and Tax Optimization.</strong>
          </Typography>
        </Box>
      </Box>

      {/* PAN Login Hub */}
      <Box sx={{
        zIndex: 1, width: '100%', maxWidth: 540,
        animation: 'fbRiseIn 600ms cubic-bezier(0.16,1,0.3,1) 150ms both',
      }}>
        <Paper
          className="glass"
          sx={{
            p: { xs: 4, md: 5 }, borderRadius: '32px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(15, 23, 42, 0.6)',
            backdropFilter: 'blur(20px)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), 0 0 60px rgba(56, 189, 248, 0.1)',
            mb: 8
          }}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3.5 }}>
            <Box>
              <Typography variant="overline" sx={{ color: '#94A3B8', fontWeight: 800, letterSpacing: '0.1em', display: 'block', mb: 1 }}>
                SECURE ACCESS HUB
              </Typography>

              {/* Only rendered when a provider is configured. Unconfigured, the PAN
                  field below is the whole sign-in - which is what every existing
                  deployment does until VITE_SUPABASE_* is set. */}
              {authClient.isConfigured && (
                <>
                  <Button
                    fullWidth
                    onClick={handleGoogleSignIn}
                    disabled={loading}
                    startIcon={<GoogleMark />}
                    sx={{
                      py: 1.75,
                      mb: 2,
                      borderRadius: '16px',
                      bgcolor: '#fff',
                      color: '#1F2937',
                      fontSize: '1rem',
                      fontWeight: 700,
                      textTransform: 'none',
                      '&:hover': { bgcolor: '#F1F5F9' },
                      '&.Mui-disabled': { bgcolor: 'rgba(255,255,255,0.4)' },
                    }}
                  >
                    Continue with Google
                  </Button>

                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
                    <Box sx={{ flex: 1, height: '1px', bgcolor: 'rgba(255,255,255,0.08)' }} />
                    <Typography sx={{ color: '#475569', fontSize: '0.75rem', fontWeight: 700 }}>
                      OR CONTINUE WITH PAN
                    </Typography>
                    <Box sx={{ flex: 1, height: '1px', bgcolor: 'rgba(255,255,255,0.08)' }} />
                  </Box>
                </>
              )}

              <TextField
                fullWidth
                variant="outlined"
                value={loginPan}
                onChange={(e) => setLoginPan(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                placeholder="Enter 10-digit PAN (e.g. ABCDE1234F)"
                autoComplete="off"
                InputProps={{
                  startAdornment: <LockIcon sx={{ color: '#475569', mr: 1.5 }} />,
                  sx: { 
                    color: '#fff', 
                    fontWeight: 700, 
                    letterSpacing: 2, 
                    fontSize: '1.1rem',
                    bgcolor: 'rgba(0,0,0,0.2)',
                    borderRadius: '16px',
                    '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.05)' },
                    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.1)' },
                    '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#38BDF8', borderWidth: 2 }
                  }
                }}
              />
            </Box>

            {/* MUI's own Collapse rather than AnimatePresence: it does the same
                enter/exit height transition and is already in the bundle, whereas
                framer-motion was 36.7 KB gzipped in the first-paint graph for this
                and two fade-ins. */}
            <Collapse in={!!error} unmountOnExit>
              <Alert severity="error" sx={{ borderRadius: '12px', bgcolor: 'rgba(239, 68, 68, 0.1)', color: '#EF4444', '& .MuiAlert-icon': { color: '#EF4444' } }}>{error}</Alert>
            </Collapse>

            <Button
              variant="contained"
              fullWidth
              onClick={handleLogin}
              disabled={loading}
              sx={{
                py: 2,
                borderRadius: '16px',
                background: 'linear-gradient(135deg, #0EA5E9 0%, #2563EB 100%)',
                fontSize: '1.1rem',
                fontWeight: 800,
                textTransform: 'none',
                boxShadow: '0 8px 25px rgba(37, 99, 235, 0.4)',
                '&:hover': { background: 'linear-gradient(135deg, #0284C7 0%, #1D4ED8 100%)', boxShadow: '0 12px 35px rgba(37, 99, 235, 0.6)' }
              }}
            >
              {loading ? <CircularProgress size={28} sx={{ color: '#fff' }} /> : 'Unlock Finance Buddy'}
            </Button>
          </Box>
        </Paper>
      </Box>

      {/* Footer */}
      <Typography variant="caption" display="block" textAlign="center" sx={{ mt: 8, mb: 2, color: '#475569', zIndex: 1, fontWeight: 600 }}>
        Finance Buddy v8.0 · SEBI CSCRF 2025 Compliant · Zero Data Retention Architecture
      </Typography>
    </Box>
  )
}
