import { useEffect, useState } from 'react'
import {
  Box, Typography, Paper, TextField, Button, Alert, CircularProgress,
  InputAdornment, IconButton, Stack,
} from '@mui/material'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import ShieldIcon from '@mui/icons-material/Shield'
import LogoutIcon from '@mui/icons-material/Logout'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import authClient from '../auth/authClient'
import { apiClient } from '../api/client'
import { useAppStore, useLogout } from '../store/appStore'

const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/

type Props = {
  requirePassword: boolean
  requirePan: boolean
  onPasswordComplete: () => void
}

/**
 * First-time setup in a single panel.
 *
 * Shows password and/or PAN depending on what is still missing (invite → often
 * both; later visits → only the missing piece). Profile edits later go to /profile.
 */
export default function AccountSetupPrompt({
  requirePassword,
  requirePan,
  onPasswordComplete,
}: Props) {
  const userId = useAppStore((s) => s.userId)
  const email = useAppStore((s) => s.email)
  const setIdentity = useAppStore((s) => s.setIdentity)
  const logout = useLogout()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [pan, setPan] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Always start blank on (re)mount — do not keep typed values across reload.
  useEffect(() => {
    setPassword('')
    setConfirm('')
    setShowPassword(false)
    setPan('')
    setError(null)
  }, [])

  const title =
    requirePassword && requirePan
      ? 'Finish account setup'
      : requirePassword
        ? 'Create your password'
        : 'Link your PAN'

  const subtitle =
    requirePassword && requirePan
      ? 'Set a sign-in password and link your PAN to continue.'
      : requirePassword
        ? `Your invite link signed you in. Set a password so you can sign in with ${email || 'your email'} next time.`
        : 'PAN is required to decrypt CAS statements and match tax filings.'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    if (requirePassword) {
      if (password.trim().length < 8) {
        setError('Password must be at least 8 characters.')
        return
      }
      if (password !== confirm) {
        setError('Passwords do not match.')
        return
      }
    }

    let panValue = ''
    if (requirePan) {
      panValue = pan.trim().toUpperCase()
      if (!panValue) {
        setError('Please enter your 10-character PAN number.')
        return
      }
      if (!PAN_PATTERN.test(panValue)) {
        setError('Invalid PAN format. Use 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).')
        return
      }
    }

    setLoading(true)
    try {
      // Password first (keeps the session valid for the PAN API call). Clear the
      // password-setup flag only after the whole submit succeeds — otherwise App
      // remounts this form mid-flight as "PAN only" and drops the in-progress save.
      if (requirePassword) {
        await authClient.updatePassword(password)
      }
      if (requirePan) {
        const data = await apiClient.setProfilePan(panValue)
        setIdentity({ userId, email, pan: data.pan })
      }
      if (requirePassword) {
        onPasswordComplete()
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ||
        (err instanceof Error ? err.message : null) ||
        'Could not save. Please try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (!requirePassword && !requirePan) return null

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, sm: 3 },
      }}
    >
      <Paper
        elevation={0}
        sx={{
          maxWidth: 520,
          width: '100%',
          p: { xs: 3.5, sm: 4.5 },
          borderRadius: '24px',
          background: 'rgba(15, 23, 42, 0.85)',
          border: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <Box
            sx={{
              width: 64,
              height: 64,
              borderRadius: '18px',
              mx: 'auto',
              mb: 2,
              background: 'linear-gradient(135deg, rgba(56,189,248,0.2) 0%, rgba(99,102,241,0.2) 100%)',
              border: '1px solid rgba(56,189,248,0.35)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {requirePassword ? (
              <LockOutlinedIcon sx={{ color: '#38BDF8', fontSize: 30 }} />
            ) : (
              <ShieldIcon sx={{ color: '#38BDF8', fontSize: 30 }} />
            )}
          </Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', mb: 1 }}>
            {title}
          </Typography>
          <Typography sx={{ color: '#94A3B8', fontSize: '0.9rem', lineHeight: 1.55 }}>
            {subtitle}
          </Typography>
        </Box>

        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {requirePassword && (
            <>
              <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, letterSpacing: '0.08em' }}>
                PASSWORD
              </Typography>
              <TextField
                fullWidth
                type={showPassword ? 'text' : 'password'}
                label="New password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                autoComplete="new-password"
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        size="small"
                        onClick={() => setShowPassword((v) => !v)}
                        edge="end"
                        sx={{ color: '#64748b' }}
                      >
                        {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
                sx={fieldSx}
              />
              <TextField
                fullWidth
                type={showPassword ? 'text' : 'password'}
                label="Confirm password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                disabled={loading}
                autoComplete="new-password"
                sx={fieldSx}
              />
            </>
          )}

          {requirePan && (
            <>
              <Typography
                variant="caption"
                sx={{
                  color: '#94A3B8',
                  fontWeight: 700,
                  letterSpacing: '0.08em',
                  mt: requirePassword ? 1 : 0,
                }}
              >
                PAN
              </Typography>
              <TextField
                fullWidth
                value={pan}
                onChange={(e) => setPan(e.target.value.toUpperCase())}
                disabled={loading}
                placeholder="ABCDE1234F"
                inputProps={{
                  maxLength: 10,
                  style: {
                    letterSpacing: '4px',
                    fontWeight: 800,
                    fontSize: '1.15rem',
                    fontFamily: 'monospace',
                    textAlign: 'center',
                  },
                }}
                autoComplete="off"
                sx={fieldSx}
              />
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.25,
                  p: 1.5,
                  borderRadius: '12px',
                  bgcolor: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.05)',
                }}
              >
                <LockOutlinedIcon sx={{ color: '#10B981', fontSize: 18 }} />
                <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 500 }}>
                  Encrypted at rest. Never shared with third parties.
                </Typography>
              </Box>
            </>
          )}

          {error && (
            <Alert severity="error" sx={{ borderRadius: '12px' }}>
              {error}
            </Alert>
          )}

          <Stack spacing={1.25} sx={{ mt: 0.5 }}>
            <Button
              type="submit"
              fullWidth
              disabled={loading}
              endIcon={loading ? undefined : <ArrowForwardIcon />}
              sx={{
                py: 1.45,
                borderRadius: '14px',
                background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
                color: '#fff',
                fontWeight: 700,
                textTransform: 'none',
              }}
            >
              {loading ? (
                <CircularProgress size={22} sx={{ color: '#fff' }} />
              ) : requirePassword && requirePan ? (
                'Save & continue'
              ) : requirePassword ? (
                'Save password & continue'
              ) : (
                'Continue to dashboard'
              )}
            </Button>
            <Button
              onClick={() => void logout()}
              disabled={loading}
              startIcon={<LogoutIcon />}
              sx={{ color: '#94A3B8', textTransform: 'none' }}
            >
              Sign out{email ? ` of ${email}` : ''}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Box>
  )
}

const fieldSx = {
  '& .MuiOutlinedInput-root': {
    borderRadius: '12px',
    bgcolor: 'rgba(2, 6, 23, 0.5)',
    color: '#fff',
  },
  '& .MuiInputLabel-root': { color: '#94A3B8' },
  '& fieldset': { borderColor: 'rgba(255,255,255,0.12)' },
}
