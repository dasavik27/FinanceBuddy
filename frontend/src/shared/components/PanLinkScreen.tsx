/**
 * PanLinkScreen.tsx
 *
 * Shown once after a user's first Google sign-in, when their Google account
 * has no PAN linked yet. Collects and validates the PAN, calls POST /auth/link-pan,
 * then hands control back to AuthCallback via the onLinked callback.
 */

import { useState } from 'react'
import {
  Box, Typography, TextField, Button, Alert, CircularProgress,
  Paper, Chip, Avatar,
} from '@mui/material'
import { motion } from 'framer-motion'
import LinkIcon from '@mui/icons-material/Link'
import LockIcon from '@mui/icons-material/Lock'
import ShieldIcon from '@mui/icons-material/Shield'
import { apiClient } from '../api/client'

interface Props {
  refreshToken: string
  user: { email: string; name: string; picture_url: string }
  onLinked: (data: any) => void
}

export default function PanLinkScreen({ refreshToken, user, onLinked }: Props) {
  const [pan, setPan]       = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)

  const handleLink = async () => {
    const clean = pan.trim().toUpperCase()
    if (!/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(clean)) {
      return setError('Invalid PAN format. It must be 10 characters (e.g. ABCDE1234F).')
    }
    setLoading(true); setError(null)
    try {
      const data = await apiClient.linkPan(clean, refreshToken)
      onLinked(data)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to link PAN. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box sx={{
      minHeight: '100vh',
      background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      p: { xs: 2, md: 4 },
    }}>
      {/* Background glows */}
      <Box sx={{ position: 'absolute', top: '10%', left: '15%', width: 500, height: 500, background: 'radial-gradient(circle, rgba(99,102,241,0.08) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', bottom: '10%', right: '15%', width: 400, height: 400, background: 'radial-gradient(circle, rgba(56,189,248,0.06) 0%, transparent 60%)', filter: 'blur(80px)', pointerEvents: 'none' }} />

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
        <Paper sx={{
          p: { xs: 4, md: 5.5 }, borderRadius: '32px', maxWidth: 480, width: '100%',
          background: 'rgba(15,23,42,0.85)',
          border: '1px solid rgba(99,102,241,0.25)',
          boxShadow: '0 25px 60px rgba(0,0,0,0.6), 0 0 60px rgba(99,102,241,0.1)',
          backdropFilter: 'blur(20px)',
        }}>

          {/* User info */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4, p: 2, background: 'rgba(99,102,241,0.08)', borderRadius: '16px', border: '1px solid rgba(99,102,241,0.15)' }}>
            <Avatar src={user.picture_url} sx={{ width: 44, height: 44, border: '2px solid rgba(99,102,241,0.4)' }}>
              {user.name?.[0]}
            </Avatar>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '0.9rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.name}
              </Typography>
              <Typography sx={{ color: '#64748B', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.email}
              </Typography>
            </Box>
            <Chip label="Google Verified" size="small" sx={{ background: 'rgba(78,222,147,0.1)', color: '#4EDE93', fontWeight: 800, fontSize: '0.65rem' }} />
          </Box>

          {/* Header */}
          <Box sx={{ textAlign: 'center', mb: 4 }}>
            <Box sx={{ width: 56, height: 56, mx: 'auto', mb: 2, borderRadius: '18px', background: 'linear-gradient(135deg, rgba(99,102,241,0.2) 0%, rgba(56,189,248,0.15) 100%)', border: '1px solid rgba(99,102,241,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <LinkIcon sx={{ fontSize: 28, color: '#818CF8' }} />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 900, color: '#F8FAFC', mb: 1, letterSpacing: '-0.02em' }}>
              Link Your PAN
            </Typography>
            <Typography sx={{ color: '#64748B', fontSize: '0.9rem', lineHeight: 1.6 }}>
              One last step. Enter your PAN to connect your financial data to your Google account.
              <br />
              <Typography component="span" sx={{ color: '#475569', fontSize: '0.82rem' }}>
                You'll only need to do this once.
              </Typography>
            </Typography>
          </Box>

          {error && (
            <Alert severity="error" sx={{ mb: 3, borderRadius: '12px' }}>{error}</Alert>
          )}

          <TextField
            fullWidth
            variant="outlined"
            label="PAN Number"
            value={pan}
            onChange={(e) => { setPan(e.target.value.toUpperCase()); setError(null) }}
            onKeyDown={(e) => e.key === 'Enter' && handleLink()}
            placeholder="e.g. ABCDE1234F"
            autoComplete="off"
            autoFocus
            InputProps={{
              startAdornment: <LockIcon sx={{ color: '#475569', mr: 1.5 }} />,
              sx: {
                color: '#fff', fontWeight: 700, letterSpacing: 2, fontSize: '1.05rem',
                bgcolor: 'rgba(0,0,0,0.2)', borderRadius: '14px',
                '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.08)' },
                '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' },
                '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#6366F1', borderWidth: 2 },
              }
            }}
            InputLabelProps={{ sx: { color: '#475569' } }}
            sx={{ mb: 3 }}
          />

          <Button
            fullWidth variant="contained" size="large"
            onClick={handleLink} disabled={loading || pan.length !== 10}
            sx={{
              py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1.05rem',
              background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
              boxShadow: '0 8px 25px rgba(99,102,241,0.4)', textTransform: 'none',
              '&:hover': { background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)' },
              '&.Mui-disabled': { background: 'rgba(99,102,241,0.3)', color: 'rgba(255,255,255,0.5)' },
            }}
          >
            {loading
              ? <><CircularProgress size={20} sx={{ color: '#fff', mr: 1.5 }} />Linking...</>
              : '🔗 Link PAN & Continue'}
          </Button>

          <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', mt: 2.5, color: '#334155' }}>
            <ShieldIcon sx={{ fontSize: 11, verticalAlign: 'middle', mr: 0.5, color: '#4EDE93' }} />
            Your PAN is stored on your own backend. Never shared externally.
          </Typography>
        </Paper>
      </motion.div>
    </Box>
  )
}
