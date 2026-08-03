import { useEffect, useState } from 'react'
import {
  Box, Typography, Button, Alert, CircularProgress, Collapse, GlobalStyles, Paper,
  TextField, InputAdornment, IconButton, Divider, Chip, Dialog, DialogTitle,
  DialogContent, DialogActions, MenuItem, Select, FormControl, InputLabel, alpha
} from '@mui/material'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import MailOutlineIcon from '@mui/icons-material/MailOutline'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import CloseIcon from '@mui/icons-material/Close'
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined'
import authClient, {
  type AccessRequestStatus,
  consumeOAuthErrorFromUrl,
  REQUEST_ACCESS_MESSAGE,
} from '../auth/authClient'
import { readAuthNotice } from '../auth/authNotice'

/** Google's mark, inline so it needs no network request and no extra package. */
const GoogleMark = () => (
  <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
    <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z" />
    <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z" />
    <path fill="#FBBC05" d="M3.97 10.72a5.41 5.41 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z" />
    <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z" />
  </svg>
)

const landingAnimations = (
  <GlobalStyles styles={{
    '@keyframes fbRiseIn': {
      from: { opacity: 0, transform: 'translateY(20px)' },
      to:   { opacity: 1, transform: 'translateY(0)' },
    },
    '@keyframes fbGlowPulse': {
      '0%, 100%': { opacity: 0.6, transform: 'scale(1)' },
      '50%': { opacity: 0.9, transform: 'scale(1.04)' },
    },
    '@media (prefers-reduced-motion: reduce)': {
      '*': { animation: 'none !important', transition: 'none !important' },
    },
  }} />
)

export default function Landing() {
  // Sign-in state
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [accessRequestStatus, setAccessRequestStatus] = useState<AccessRequestStatus | null>(null)

  // Request Access modal state
  const [requestModalOpen, setRequestModalOpen] = useState(false)
  const [reqName, setReqName] = useState('')
  const [reqEmail, setReqEmail] = useState('')
  const [reqType, setReqType] = useState('individual')
  const [reqNotes, setReqNotes] = useState('')
  const [reqLoading, setReqLoading] = useState(false)
  const [reqError, setReqError] = useState<string | null>(null)
  const [reqSuccess, setReqSuccess] = useState<string | null>(null)

  const showRaiseRequest = accessRequestStatus === 'none'
  const isPendingNotice = accessRequestStatus === 'pending'
  const showAccessInfo = showRaiseRequest || isPendingNotice || accessRequestStatus === 'approved'

  const openRequestAccess = () => {
    if (email.trim()) setReqEmail(email.trim())
    setRequestModalOpen(true)
  }

  const applyAccessStatus = async (emailTrim: string) => {
    const st = await authClient.checkAccessStatus(emailTrim)
    setAccessRequestStatus(st.access_request_status)
    setError(st.message)
  }

  // After sign-out (403) or OAuth bounce: show message from access_requests lookup.
  useEffect(() => {
    let cancelled = false

    const run = async () => {
      const notice = readAuthNotice()
      const hadOAuthError = consumeOAuthErrorFromUrl() !== null
      const emailHint = (notice?.email || email.trim()).trim()

      if (notice) {
        if (cancelled) return
        setAccessRequestStatus(notice.access_request_status)
        setError(notice.message)
        if (notice.email) setEmail(notice.email)
        setLoading(false)
        return
      }

      if (hadOAuthError && emailHint) {
        try {
          await applyAccessStatus(emailHint)
        } catch {
          if (!cancelled) {
            setAccessRequestStatus('none')
            setError(REQUEST_ACCESS_MESSAGE)
          }
        } finally {
          if (!cancelled) setLoading(false)
        }
      }
    }

    void run()
    return () => {
      cancelled = true
    }
  }, [])

  const handleEmailSignIn = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim() || !password) {
      setError('Please enter both email and password.')
      return
    }
    setLoading(true)
    setError(null)
    setAccessRequestStatus(null)
    try {
      await authClient.signInWithEmail(email.trim(), password)
      // App.tsx auth listener handles redirect to /dashboard
    } catch {
      try {
        await applyAccessStatus(email.trim())
      } catch {
        setError('Invalid email or password.')
        setAccessRequestStatus(null)
      }
      setLoading(false)
    }
  }

  const handleGoogleSignIn = async () => {
    setLoading(true)
    setError(null)
    setAccessRequestStatus(null)
    try {
      await authClient.signInWithGoogle()
    } catch {
      const emailTrim = email.trim()
      if (emailTrim) {
        try {
          await applyAccessStatus(emailTrim)
        } catch {
          setError('Could not start Google sign-in.')
          setAccessRequestStatus(null)
        }
      } else {
        setError('Could not start Google sign-in.')
      }
      setLoading(false)
    }
  }

  const handleRequestSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!reqName.trim() || !reqEmail.trim()) {
      setReqError('Please provide both your name and email address.')
      return
    }
    setReqLoading(true)
    setReqError(null)
    try {
      const res = await authClient.submitAccessRequest({
        name: reqName.trim(),
        email: reqEmail.trim(),
        investor_type: reqType,
        notes: reqNotes.trim(),
      })
      if (res.status === 'already_submitted') {
        setReqSuccess(
          res.message ||
            'Your access request is already pending. Please wait for an administrator to approve it.',
        )
      } else {
        setReqSuccess(res.message || 'Access request submitted successfully.')
      }
    } catch (err: any) {
      setReqError(err?.message || 'Failed to submit request. Please try again.')
    } finally {
      setReqLoading(false)
    }
  }

  const handleCloseRequestModal = () => {
    setRequestModalOpen(false)
    // Clear request form after transition
    setTimeout(() => {
      setReqName('')
      setReqEmail('')
      setReqType('individual')
      setReqNotes('')
      setReqError(null)
      setReqSuccess(null)
    }, 300)
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
        p: { xs: 2.5, md: 4 },
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
        <Box sx={{ textAlign: 'center', mb: 4 }}>
          {/* Main App Badge */}
          <Box
            sx={{
              width: 68, height: 68, borderRadius: '22px', mx: 'auto', mb: 2.5,
              background: 'linear-gradient(135deg, #1E293B 0%, #0F172A 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 12px 35px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.1)',
              border: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <TrendingUpIcon sx={{ fontSize: 34, color: '#38BDF8' }} />
          </Box>

          <Typography
            variant="h1"
            sx={{
              background: 'linear-gradient(180deg, #FFFFFF 0%, #94A3B8 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              mb: 1,
              fontWeight: 900,
              letterSpacing: '-0.02em',
              lineHeight: 1.1,
              fontSize: { xs: '2.5rem', md: '3.6rem' }
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
              fontSize: { xs: '0.85rem', md: '1rem' },
              mb: 1.5
            }}
          >
            Smart Wealth Dashboard
          </Typography>

          <Typography variant="body2" sx={{ color: '#94A3B8', maxWidth: 540, mx: 'auto', lineHeight: 1.6, fontSize: '0.95rem' }}>
            Unified analytics & portfolio intelligence spanning <strong style={{ color: '#F8FAFC' }}>Indian Stocks, Mutual Funds, and Tax Advisory.</strong>
          </Typography>
        </Box>
      </Box>

      {/* Sign-in Hub Card */}
      <Box sx={{
        zIndex: 1, width: '100%', maxWidth: 480,
        animation: 'fbRiseIn 600ms cubic-bezier(0.16,1,0.3,1) 120ms both',
      }}>
        <Paper
          className="glass"
          sx={{
            p: { xs: 3.5, md: 4 }, 
            borderRadius: '28px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(15, 23, 42, 0.65)',
            backdropFilter: 'blur(24px)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), 0 0 60px rgba(56, 189, 248, 0.08)',
            mb: 4
          }}
        >
          <Box component="form" onSubmit={handleEmailSignIn} sx={{ display: 'flex', flexDirection: 'column', gap: 2.2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="overline" sx={{ color: '#94A3B8', fontWeight: 800, letterSpacing: '0.12em' }}>
                SIGN IN
              </Typography>
              <Chip
                icon={<ShieldOutlinedIcon sx={{ fontSize: '14px !important', color: '#38BDF8' }} />}
                label="Private Access"
                size="small"
                sx={{
                  bgcolor: 'rgba(56, 189, 248, 0.08)',
                  color: '#38BDF8',
                  border: '1px solid rgba(56, 189, 248, 0.2)',
                  fontSize: '0.68rem',
                  fontWeight: 700,
                  height: 24,
                }}
              />
            </Box>

            {/* Email Field */}
            <TextField
              fullWidth
              size="medium"
              placeholder="Email address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
              autoComplete="email"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <MailOutlineIcon sx={{ color: '#64748b', fontSize: 20 }} />
                  </InputAdornment>
                ),
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: '14px',
                  backgroundColor: 'rgba(2, 6, 23, 0.5)',
                  color: '#fff',
                  border: '1px solid rgba(255,255,255,0.08)',
                  transition: 'all 0.2s ease',
                  '& fieldset': { border: 'none' },
                  '&:hover': { backgroundColor: 'rgba(2, 6, 23, 0.7)', borderColor: 'rgba(255,255,255,0.15)' },
                  '&.Mui-focused': { borderColor: '#38BDF8', boxShadow: '0 0 0 2px rgba(56, 189, 248, 0.2)' },
                },
                '& input::placeholder': { color: '#64748B', opacity: 1, fontSize: '0.92rem' }
              }}
            />

            {/* Password Field */}
            <TextField
              fullWidth
              size="medium"
              placeholder="Password"
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <LockOutlinedIcon sx={{ color: '#64748b', fontSize: 20 }} />
                  </InputAdornment>
                ),
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton
                      size="small"
                      onClick={() => setShowPassword(!showPassword)}
                      edge="end"
                      sx={{ color: '#64748b', '&:hover': { color: '#94a3b8' } }}
                    >
                      {showPassword ? <VisibilityOff sx={{ fontSize: 18 }} /> : <Visibility sx={{ fontSize: 18 }} />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  borderRadius: '14px',
                  backgroundColor: 'rgba(2, 6, 23, 0.5)',
                  color: '#fff',
                  border: '1px solid rgba(255,255,255,0.08)',
                  transition: 'all 0.2s ease',
                  '& fieldset': { border: 'none' },
                  '&:hover': { backgroundColor: 'rgba(2, 6, 23, 0.7)', borderColor: 'rgba(255,255,255,0.15)' },
                  '&.Mui-focused': { borderColor: '#38BDF8', boxShadow: '0 0 0 2px rgba(56, 189, 248, 0.2)' },
                },
                '& input::placeholder': { color: '#64748B', opacity: 1, fontSize: '0.92rem' }
              }}
            />

            {/* Access status / error message */}
            <Collapse in={!!error} unmountOnExit>
              <Alert
                severity={showAccessInfo ? 'info' : 'error'}
                action={
                  showRaiseRequest ? (
                    <Button
                      color="inherit"
                      size="small"
                      onClick={openRequestAccess}
                      sx={{ fontWeight: 700, textTransform: 'none', whiteSpace: 'nowrap' }}
                    >
                      Raise request
                    </Button>
                  ) : undefined
                }
                sx={{
                  borderRadius: '12px',
                  bgcolor: showAccessInfo ? 'rgba(56, 189, 248, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                  color: showAccessInfo ? '#7DD3FC' : '#EF4444',
                  border: showAccessInfo
                    ? '1px solid rgba(56, 189, 248, 0.25)'
                    : '1px solid rgba(239, 68, 68, 0.2)',
                  fontSize: '0.85rem',
                  py: 0.5,
                  alignItems: 'center',
                  '& .MuiAlert-icon': { color: showAccessInfo ? '#38BDF8' : '#EF4444' },
                }}
              >
                {error}
              </Alert>
            </Collapse>

            {/* Sign In CTA Button */}
            <Button
              fullWidth
              type="submit"
              disabled={loading}
              sx={{
                py: 1.6,
                mt: 0.5,
                borderRadius: '14px',
                background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
                color: '#fff',
                fontSize: '0.98rem',
                fontWeight: 700,
                textTransform: 'none',
                boxShadow: '0 4px 20px rgba(2, 132, 199, 0.35)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #0369A1 0%, #1D4ED8 100%)',
                  boxShadow: '0 6px 24px rgba(2, 132, 199, 0.5)',
                },
                '&.Mui-disabled': { background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.4)' },
              }}
            >
              {loading ? <CircularProgress size={22} sx={{ color: '#fff' }} /> : 'Sign In to Dashboard'}
            </Button>

            {/* Divider */}
            <Divider sx={{ my: 1, borderColor: 'rgba(255,255,255,0.06)' }}>
              <Typography sx={{ fontSize: '0.72rem', color: '#64748B', fontWeight: 700, letterSpacing: '0.08em' }}>
                OR
              </Typography>
            </Divider>

            {/* Google Login */}
            <Button
              fullWidth
              onClick={handleGoogleSignIn}
              disabled={loading}
              startIcon={loading ? undefined : <GoogleMark />}
              sx={{
                py: 1.4,
                borderRadius: '14px',
                bgcolor: 'rgba(255,255,255,0.04)',
                color: '#E2E8F0',
                border: '1px solid rgba(255,255,255,0.1)',
                fontSize: '0.92rem',
                fontWeight: 600,
                textTransform: 'none',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.08)', borderColor: 'rgba(255,255,255,0.2)' },
              }}
            >
              Continue with Google
            </Button>

            {/* Invite-Only Notice & Request Access CTA */}
            {!isPendingNotice && (
            <Box sx={{ mt: 1.5, pt: 2, borderTop: '1px solid rgba(255,255,255,0.06)', textAlign: 'center' }}>
              <Typography sx={{ fontSize: '0.82rem', color: '#94A3B8', mb: 0.8 }}>
                {showRaiseRequest
                  ? 'Need access? Submit a request and an admin will approve you.'
                  : "Don't have an authorized account?"}
              </Typography>
              <Button
                variant={showRaiseRequest ? 'contained' : 'text'}
                onClick={openRequestAccess}
                endIcon={<ArrowForwardIcon sx={{ fontSize: 16 }} />}
                sx={{
                  color: showRaiseRequest ? '#0F172A' : '#38BDF8',
                  bgcolor: showRaiseRequest ? '#38BDF8' : 'transparent',
                  fontSize: '0.86rem',
                  fontWeight: 700,
                  textTransform: 'none',
                  px: showRaiseRequest ? 2 : 0,
                  py: showRaiseRequest ? 0.8 : 0,
                  borderRadius: showRaiseRequest ? '12px' : 0,
                  '&:hover': {
                    color: showRaiseRequest ? '#0F172A' : '#7dd3fc',
                    bgcolor: showRaiseRequest ? '#7DD3FC' : 'transparent',
                  },
                }}
              >
                Request Early Access
              </Button>
            </Box>
            )}
          </Box>
        </Paper>
      </Box>

      {/* Footer */}
      <Typography variant="caption" display="block" textAlign="center" sx={{ color: '#475569', zIndex: 1, fontWeight: 600 }}>
        Finance Buddy v8.0 · SEBI CSCRF 2025 Compliant · Private Beta
      </Typography>

      {/* Request Access Glass Modal */}
      <Dialog
        open={requestModalOpen}
        onClose={handleCloseRequestModal}
        maxWidth="xs"
        fullWidth
        slotProps={{
          backdrop: {
            sx: {
              backdropFilter: 'blur(12px)',
              backgroundColor: 'rgba(2, 6, 23, 0.7)',
            }
          }
        }}
        PaperProps={{
          sx: {
            borderRadius: '24px',
            background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: '0 25px 60px rgba(0, 0, 0, 0.8)',
            p: 1.5,
            color: '#fff',
          }
        }}
      >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
          <Box>
            <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>
              Request Access
            </Typography>
            <Typography sx={{ fontSize: '0.8rem', color: '#94A3B8', mt: 0.2 }}>
              Join the private wealth intelligence beta
            </Typography>
          </Box>
          <IconButton size="small" onClick={handleCloseRequestModal} sx={{ color: '#64748B', '&:hover': { color: '#fff' } }}>
            <CloseIcon sx={{ fontSize: 20 }} />
          </IconButton>
        </DialogTitle>

        <DialogContent sx={{ pt: '12px !important' }}>
          {reqSuccess ? (
            <Box sx={{ py: 3, textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
              <Box sx={{
                width: 60, height: 60, borderRadius: '50%',
                bgcolor: 'rgba(78, 222, 147, 0.15)',
                border: '1px solid rgba(78, 222, 147, 0.3)',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
              }}>
                <CheckCircleOutlineIcon sx={{ fontSize: 34, color: '#4EDE93' }} />
              </Box>
              <Typography sx={{ fontSize: '1.1rem', fontWeight: 800, color: '#fff' }}>
                Request Submitted
              </Typography>
              <Typography sx={{ fontSize: '0.88rem', color: '#94A3B8', lineHeight: 1.6, maxWidth: 320 }}>
                {reqSuccess}
              </Typography>
              <Button
                variant="outlined"
                onClick={handleCloseRequestModal}
                sx={{
                  mt: 1.5,
                  borderRadius: '12px',
                  borderColor: 'rgba(255,255,255,0.15)',
                  color: '#fff',
                  px: 4,
                  '&:hover': { borderColor: '#38BDF8', bgcolor: 'rgba(56,189,248,0.1)' }
                }}
              >
                Back to Sign In
              </Button>
            </Box>
          ) : (
            <Box component="form" onSubmit={handleRequestSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {/* Full Name */}
              <Box>
                <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.6 }}>
                  FULL NAME *
                </Typography>
                <TextField
                  fullWidth
                  size="small"
                  placeholder="e.g. Rahul Sharma"
                  value={reqName}
                  onChange={(e) => setReqName(e.target.value)}
                  disabled={reqLoading}
                  required
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '12px',
                      backgroundColor: 'rgba(2, 6, 23, 0.5)',
                      color: '#fff',
                      border: '1px solid rgba(255,255,255,0.08)',
                      '& fieldset': { border: 'none' },
                      '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                      '&.Mui-focused': { borderColor: '#38BDF8' },
                    },
                    '& input::placeholder': { color: '#64748B', opacity: 1 }
                  }}
                />
              </Box>

              {/* Email */}
              <Box>
                <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.6 }}>
                  WORK OR PERSONAL EMAIL *
                </Typography>
                <TextField
                  fullWidth
                  size="small"
                  type="email"
                  placeholder="name@example.com"
                  value={reqEmail}
                  onChange={(e) => setReqEmail(e.target.value)}
                  disabled={reqLoading}
                  required
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '12px',
                      backgroundColor: 'rgba(2, 6, 23, 0.5)',
                      color: '#fff',
                      border: '1px solid rgba(255,255,255,0.08)',
                      '& fieldset': { border: 'none' },
                      '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                      '&.Mui-focused': { borderColor: '#38BDF8' },
                    },
                    '& input::placeholder': { color: '#64748B', opacity: 1 }
                  }}
                />
              </Box>

              {/* Investor Profile */}
              <Box>
                <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.6 }}>
                  INVESTOR PROFILE
                </Typography>
                <FormControl fullWidth size="small">
                  <Select
                    value={reqType}
                    onChange={(e) => setReqType(e.target.value)}
                    disabled={reqLoading}
                    sx={{
                      borderRadius: '12px',
                      backgroundColor: 'rgba(2, 6, 23, 0.5)',
                      color: '#fff',
                      border: '1px solid rgba(255,255,255,0.08)',
                      '& fieldset': { border: 'none' },
                      '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                      '&.Mui-focused': { borderColor: '#38BDF8' },
                      '& .MuiSvgIcon-root': { color: '#94a3b8' }
                    }}
                    MenuProps={{
                      PaperProps: {
                        sx: {
                          bgcolor: '#0f172a',
                          border: '1px solid rgba(255,255,255,0.1)',
                          color: '#fff',
                          '& .MuiMenuItem-root:hover': { bgcolor: 'rgba(56,189,248,0.12)' },
                          '& .MuiMenuItem-root.Mui-selected': { bgcolor: 'rgba(56,189,248,0.2)' }
                        }
                      }
                    }}
                  >
                    <MenuItem value="individual">Individual Investor</MenuItem>
                    <MenuItem value="hni">High Net-Worth Individual (HNI)</MenuItem>
                    <MenuItem value="advisor">Financial Advisor / Wealth Manager</MenuItem>
                    <MenuItem value="tax_pro">CA / Tax Professional</MenuItem>
                    <MenuItem value="corporate">Corporate Treasury</MenuItem>
                  </Select>
                </FormControl>
              </Box>

              {/* Optional Notes */}
              <Box>
                <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.6 }}>
                  PRIMARY INTEREST (OPTIONAL)
                </Typography>
                <TextField
                  fullWidth
                  size="small"
                  multiline
                  rows={2}
                  placeholder="e.g. Looking for unified stocks & mutual fund capital gains tracking"
                  value={reqNotes}
                  onChange={(e) => setReqNotes(e.target.value)}
                  disabled={reqLoading}
                  sx={{
                    '& .MuiOutlinedInput-root': {
                      borderRadius: '12px',
                      backgroundColor: 'rgba(2, 6, 23, 0.5)',
                      color: '#fff',
                      border: '1px solid rgba(255,255,255,0.08)',
                      '& fieldset': { border: 'none' },
                      '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                      '&.Mui-focused': { borderColor: '#38BDF8' },
                    },
                    '& textarea::placeholder': { color: '#64748B', opacity: 1 }
                  }}
                />
              </Box>

              {/* Error Message */}
              <Collapse in={!!reqError} unmountOnExit>
                <Alert 
                  severity="error" 
                  sx={{ 
                    borderRadius: '10px', 
                    bgcolor: 'rgba(239, 68, 68, 0.1)', 
                    color: '#EF4444', 
                    fontSize: '0.82rem',
                    py: 0.2,
                    '& .MuiAlert-icon': { color: '#EF4444' } 
                  }}
                >
                  {reqError}
                </Alert>
              </Collapse>

              {/* Submit CTA */}
              <Button
                fullWidth
                type="submit"
                disabled={reqLoading}
                sx={{
                  mt: 1,
                  py: 1.4,
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: '0.92rem',
                  textTransform: 'none',
                  boxShadow: '0 4px 16px rgba(2, 132, 199, 0.3)',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #0369A1 0%, #1D4ED8 100%)',
                  }
                }}
              >
                {reqLoading ? <CircularProgress size={20} sx={{ color: '#fff' }} /> : 'Submit Access Request'}
              </Button>
            </Box>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  )
}
