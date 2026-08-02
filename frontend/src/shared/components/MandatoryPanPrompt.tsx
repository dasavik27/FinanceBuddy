import React, { useState } from 'react'
import {
  Box, Typography, Paper, TextField, Button, Alert, CircularProgress,
  Stack, GlobalStyles, alpha,
} from '@mui/material'
import ShieldIcon from '@mui/icons-material/Shield'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import LogoutIcon from '@mui/icons-material/Logout'
import ArrowForwardIcon from '@mui/icons-material/ArrowForward'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import { useMutation } from '@tanstack/react-query'

import { apiClient } from '../api/client'
import { useAppStore, useLogout } from '../store/appStore'

const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/

const promptAnimations = (
  <GlobalStyles styles={{
    '@keyframes panPromptRise': {
      from: { opacity: 0, transform: 'translateY(24px) scale(0.98)' },
      to:   { opacity: 1, transform: 'translateY(0) scale(1)' },
    },
    '@keyframes pulseHalo': {
      '0%, 100%': { transform: 'scale(1)', opacity: 0.4 },
      '50%': { transform: 'scale(1.08)', opacity: 0.7 },
    },
  }} />
)

export default function MandatoryPanPrompt() {
  const userId = useAppStore((s) => s.userId)
  const email = useAppStore((s) => s.email)
  const setIdentity = useAppStore((s) => s.setIdentity)
  const logout = useLogout()

  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const saveMutation = useMutation({
    mutationFn: (pan: string) => apiClient.setProfilePan(pan),
    onSuccess: (data) => {
      setIdentity({ userId, email, pan: data.pan })
    },
    onError: (e: any) => {
      setError(e?.response?.data?.detail ?? 'Failed to save PAN. Please check your network and try again.')
    },
  })

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    const pan = value.trim().toUpperCase()
    if (!pan) {
      setError('Please enter your 10-character PAN number.')
      return
    }
    if (!PAN_PATTERN.test(pan)) {
      setError('Invalid PAN format. Standard format is 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).')
      return
    }
    setError(null)
    saveMutation.mutate(pan)
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, sm: 3, md: 4 },
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {promptAnimations}

      {/* Ambient background glows */}
      <Box sx={{ position: 'absolute', top: '10%', left: '15%', width: 500, height: 500, background: 'radial-gradient(circle, rgba(56,189,248,0.08) 0%, transparent 70%)', filter: 'blur(90px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', bottom: '10%', right: '15%', width: 600, height: 600, background: 'radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 70%)', filter: 'blur(100px)', pointerEvents: 'none' }} />

      <Paper
        className="glass"
        sx={{
          width: '100%',
          maxWidth: 520,
          p: { xs: 3.5, sm: 5 },
          borderRadius: '28px',
          border: '1px solid rgba(99, 102, 241, 0.25)',
          background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.85) 0%, rgba(15, 23, 42, 0.9) 100%)',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.7), 0 0 30px rgba(99, 102, 241, 0.1)',
          position: 'relative',
          animation: 'panPromptRise 500ms cubic-bezier(0.16, 1, 0.3, 1) both',
          backdropFilter: 'blur(24px)',
        }}
      >
        {/* Top Gradient Stripe */}
        <Box sx={{ position: 'absolute', top: 0, left: 0, right: 0, height: 4, background: 'linear-gradient(90deg, #6366F1, #38BDF8, #10B981)', borderTopLeftRadius: '28px', borderTopRightRadius: '28px' }} />

        {/* Icon & Title */}
        <Box sx={{ textAlign: 'center', mb: 3.5 }}>
          <Box
            sx={{
              width: 64,
              height: 64,
              borderRadius: '20px',
              mx: 'auto',
              mb: 2.5,
              background: 'linear-gradient(135deg, rgba(56,189,248,0.15) 0%, rgba(99,102,241,0.15) 100%)',
              border: '1px solid rgba(56,189,248,0.3)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 8px 25px rgba(56,189,248,0.2)',
            }}
          >
            <ShieldIcon sx={{ fontSize: 32, color: '#38BDF8' }} />
          </Box>

          <Typography variant="h5" sx={{ color: '#fff', fontWeight: 900, mb: 1, letterSpacing: '-0.01em' }}>
            Permanent Account Number (PAN)
          </Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 500, lineHeight: 1.6 }}>
            To unlock your financial dashboard, please link your PAN. This is required to decrypt password-protected CAS statements and match your tax filings.
          </Typography>
        </Box>

        {/* Form */}
        <Box component="form" onSubmit={handleSubmit} noValidate>
          <Box sx={{ mb: 3 }}>
            <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, letterSpacing: '0.08em', mb: 1, display: 'block' }}>
              ENTER 10-CHARACTER PAN
            </Typography>
            <TextField
              autoFocus
              fullWidth
              value={value}
              onChange={(e) => {
                setValue(e.target.value.toUpperCase())
                if (error) setError(null)
              }}
              placeholder="ABCDE1234F"
              inputProps={{
                maxLength: 10,
                style: {
                  letterSpacing: '4px',
                  fontWeight: 800,
                  fontSize: '1.25rem',
                  fontFamily: 'monospace',
                  textAlign: 'center',
                },
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  bgcolor: 'rgba(15, 23, 42, 0.7)',
                  borderRadius: '16px',
                  border: '1px solid rgba(255, 255, 255, 0.1)',
                  transition: 'all 0.2s ease',
                  '&:hover': {
                    borderColor: 'rgba(56, 189, 248, 0.4)',
                  },
                  '&.Mui-focused': {
                    borderColor: '#38BDF8',
                    boxShadow: '0 0 0 3px rgba(56, 189, 248, 0.15)',
                  },
                },
                '& .MuiInputBase-input': {
                  color: '#F8FAFC',
                  py: 1.75,
                },
              }}
              autoComplete="off"
            />
          </Box>

          {error && (
            <Alert
              severity="error"
              sx={{
                mb: 3,
                borderRadius: '14px',
                bgcolor: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                color: '#FCA5A5',
              }}
            >
              {error}
            </Alert>
          )}

          {/* Security Guarantee Pill */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.25,
              p: 1.5,
              borderRadius: '14px',
              bgcolor: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              mb: 3.5,
            }}
          >
            <LockOutlinedIcon sx={{ color: '#10B981', fontSize: 18 }} />
            <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 500, fontSize: '0.78rem' }}>
              Encrypted at rest using AES-256-GCM. Never shared with third parties.
            </Typography>
          </Box>

          {/* Action Buttons */}
          <Stack spacing={1.5}>
            <Button
              type="submit"
              variant="contained"
              fullWidth
              disabled={saveMutation.isPending || value.trim().length === 0}
              endIcon={saveMutation.isPending ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : <ArrowForwardIcon />}
              sx={{
                py: 1.5,
                borderRadius: '14px',
                background: 'linear-gradient(135deg, #6366F1 0%, #38BDF8 100%)',
                color: '#fff',
                fontWeight: 800,
                fontSize: '0.95rem',
                textTransform: 'none',
                boxShadow: '0 8px 20px rgba(99, 102, 241, 0.35)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #4F46E5 0%, #0284C7 100%)',
                  boxShadow: '0 10px 25px rgba(99, 102, 241, 0.5)',
                },
                '&.Mui-disabled': {
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: 'rgba(255, 255, 255, 0.3)',
                },
              }}
            >
              {saveMutation.isPending ? 'Verifying & Saving...' : 'Continue to Dashboard'}
            </Button>

            <Button
              onClick={() => logout()}
              fullWidth
              startIcon={<LogoutIcon sx={{ fontSize: 18 }} />}
              sx={{
                py: 1.25,
                borderRadius: '14px',
                color: '#94A3B8',
                fontWeight: 600,
                textTransform: 'none',
                '&:hover': {
                  bgcolor: 'rgba(255, 255, 255, 0.04)',
                  color: '#F8FAFC',
                },
              }}
            >
              Sign out of {email || 'account'}
            </Button>
          </Stack>
        </Box>
      </Paper>
    </Box>
  )
}
