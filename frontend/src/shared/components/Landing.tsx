import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Box, Typography, Button, TextField, Alert, CircularProgress,
  Collapse, GlobalStyles, Paper, Divider,
} from '@mui/material'
import GoogleIcon      from '@mui/icons-material/Google'
import LockIcon        from '@mui/icons-material/Lock'
import TrendingUpIcon  from '@mui/icons-material/TrendingUp'
import ShieldIcon      from '@mui/icons-material/Shield'
import api             from '../api/client'
import { apiClient }   from '../api/client'
import { useAppStore } from '../store/appStore'

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
  const [googleLoading, setGoogleLoading] = useState(false)
  const [error, setError]               = useState<string | null>(null)
  const [googleConfigured, setGoogleConfigured] = useState<boolean | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    apiClient.getGoogleConfig()
      .then((cfg) => setGoogleConfigured(cfg.configured))
      .catch(() => setGoogleConfigured(false))
  }, [])

  const handleGoogleSignIn = async () => {
    setGoogleLoading(true); setError(null)
    try {
      const { url } = await apiClient.getGoogleLoginUrl()
      window.location.href = url
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to initiate Google sign-in.')
      setGoogleLoading(false)
    }
  }

  return (
    <Box sx={{
      minHeight: '100vh',
      background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      p: { xs: 2, md: 4 }, position: 'relative', overflow: 'hidden',
    }}>
      {landingAnimations}

      {/* Background Glows */}
      <Box sx={{ position: 'absolute', top: '-10%', left: '10%', width: 600, height: 600, background: 'radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', bottom: '-20%', right: '10%', width: 700, height: 700, background: 'radial-gradient(circle, rgba(16,185,129,0.06) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', top: '30%', left: '50%', transform: 'translateX(-50%)', width: 800, height: 800, background: 'radial-gradient(circle, rgba(139,92,246,0.04) 0%, transparent 70%)', filter: 'blur(100px)', pointerEvents: 'none' }} />

      {/* Hero */}
      <Box sx={{ zIndex: 1, width: '100%', animation: 'fbRiseIn 600ms cubic-bezier(0.16,1,0.3,1) both' }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Box sx={{ width: 72, height: 72, borderRadius: '24px', mx: 'auto', mb: 3.5, background: 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 12px 35px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.08)' }}>
            <TrendingUpIcon sx={{ fontSize: 38, color: '#38BDF8' }} />
          </Box>
          <Typography variant="h1" sx={{ background: 'linear-gradient(180deg, #FFFFFF 0%, #94A3B8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', mb: 1.5, fontWeight: 900, letterSpacing: '-0.02em', lineHeight: 1.1, fontSize: { xs: '3rem', md: '4.5rem' } }}>
            Finance Buddy
          </Typography>
          <Typography variant="h6" sx={{ color: '#38BDF8', fontWeight: 700, letterSpacing: '0.15em', textTransform: 'uppercase', mb: 3 }}>
            One PAN. Total Financial Control.
          </Typography>
          <Typography variant="body1" sx={{ color: '#94A3B8', maxWidth: 600, mx: 'auto', lineHeight: 1.8, fontSize: '1.1rem' }}>
            Your unified wealth dashboard for <strong style={{ color: '#F8FAFC' }}>Indian Stocks, Mutual Funds, and Tax Optimization.</strong>
          </Typography>
        </Box>
      </Box>

      {/* Auth Card */}
      <Box sx={{ zIndex: 1, width: '100%', maxWidth: 480, animation: 'fbRiseIn 600ms cubic-bezier(0.16,1,0.3,1) 150ms both' }}>
        <Paper className="glass" sx={{ p: { xs: 4, md: 5 }, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(15,23,42,0.65)', backdropFilter: 'blur(20px)', boxShadow: '0 25px 50px -12px rgba(0,0,0,0.75), 0 0 60px rgba(56,189,248,0.1)', mb: 8 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3.5 }}>
            <Box>
              <Typography variant="overline" sx={{ color: '#94A3B8', fontWeight: 800, letterSpacing: '0.12em', display: 'block', textAlign: 'center', mb: 1 }}>
                SECURE ACCESS HUB
              </Typography>
            </Box>

          <Collapse in={!!error} unmountOnExit>
            <Alert severity="error" sx={{ mb: 3, borderRadius: '12px', bgcolor: 'rgba(239,68,68,0.1)', color: '#EF4444', '& .MuiAlert-icon': { color: '#EF4444' } }}>{error}</Alert>
          </Collapse>

          {/* Google Sign In — primary CTA */}
          <Button
            fullWidth variant="contained" size="large"
            onClick={handleGoogleSignIn} disabled={googleLoading || googleConfigured === false}
            startIcon={googleLoading ? <CircularProgress size={20} sx={{ color: '#fff' }} /> : <GoogleIcon />}
            sx={{
              py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1rem',
              background: 'linear-gradient(135deg, #4285F4 0%, #3367D6 100%)',
              boxShadow: '0 8px 25px rgba(66,133,244,0.4)', textTransform: 'none', mb: 1,
              '&:hover': { background: 'linear-gradient(135deg, #3367D6 0%, #2851A3 100%)', boxShadow: '0 12px 35px rgba(66,133,244,0.55)' },
              '&.Mui-disabled': { background: 'rgba(66,133,244,0.3)', color: 'rgba(255,255,255,0.5)' },
            }}
          >
            {googleLoading ? 'Redirecting to Google...' : googleConfigured === false ? 'Google Auth Not Configured' : 'Continue with Google'}
          </Button>

            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.75 }}>
              <ShieldIcon sx={{ fontSize: 12, color: '#4EDE93' }} />
              <Typography variant="caption" sx={{ color: '#334155', fontWeight: 600 }}>
                Zero data retention · Processed on your backend only
              </Typography>
            </Box>
          </Box>
        </Paper>
      </Box>

      <Typography variant="caption" display="block" textAlign="center" sx={{ mt: -4, mb: 2, color: '#334155', zIndex: 1, fontWeight: 600 }}>
        Finance Buddy v8.0 · SEBI CSCRF 2025 Compliant · Zero Data Retention Architecture
      </Typography>
    </Box>
  )
}
