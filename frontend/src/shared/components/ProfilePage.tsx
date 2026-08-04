/**
 * Signed-in account settings: display name, PAN, password.
 *
 * Reached from the topbar badge menu. Data export / account deletion stay on
 * /accounts (vault) so this page stays focused on identity preferences.
 */

import { FormEvent, ReactNode, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import BadgeIcon from '@mui/icons-material/Badge'
import LockOutlinedIcon from '@mui/icons-material/LockOutlined'
import PersonOutlineIcon from '@mui/icons-material/PersonOutline'
import SecurityIcon from '@mui/icons-material/Security'
import Visibility from '@mui/icons-material/Visibility'
import VisibilityOff from '@mui/icons-material/VisibilityOff'
import { useMutation } from '@tanstack/react-query'

import { apiClient } from '../api/client'
import authClient from '../auth/authClient'
import { useAppStore } from '../store/appStore'

const PAN_PATTERN = /^[A-Z]{5}[0-9]{4}[A-Z]$/

const fieldSx = {
  '& .MuiOutlinedInput-root': {
    borderRadius: '12px',
    bgcolor: 'rgba(255,255,255,0.03)',
    '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' },
    '&:hover fieldset': { borderColor: 'rgba(56,189,248,0.35)' },
    '&.Mui-focused fieldset': { borderColor: '#38BDF8' },
  },
  '& .MuiInputLabel-root': { color: '#94A3B8' },
  '& .MuiInputBase-input': { color: '#F8FAFC' },
}

function SectionCard({
  icon,
  title,
  subtitle,
  children,
}: {
  icon: ReactNode
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <Box
      sx={{
        p: { xs: 2.5, sm: 3 },
        borderRadius: '20px',
        background: 'rgba(15, 23, 42, 0.72)',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      <Stack direction="row" spacing={1.5} alignItems="flex-start" sx={{ mb: 2.5 }}>
        <Box
          sx={{
            width: 40,
            height: 40,
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(135deg, rgba(56,189,248,0.15) 0%, rgba(99,102,241,0.15) 100%)',
            border: '1px solid rgba(56,189,248,0.25)',
            color: '#38BDF8',
            flexShrink: 0,
          }}
        >
          {icon}
        </Box>
        <Box>
          <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.05rem' }}>
            {title}
          </Typography>
          <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mt: 0.35, lineHeight: 1.45 }}>
            {subtitle}
          </Typography>
        </Box>
      </Stack>
      {children}
    </Box>
  )
}

export default function ProfilePage() {
  const navigate = useNavigate()
  const email = useAppStore((s) => s.email)
  const displayName = useAppStore((s) => s.displayName)
  const pan = useAppStore((s) => s.pan)
  const status = useAppStore((s) => s.status)
  const role = useAppStore((s) => s.role)
  const userId = useAppStore((s) => s.userId)
  const setIdentity = useAppStore((s) => s.setIdentity)

  const [nameValue, setNameValue] = useState(displayName ?? '')
  const [nameMsg, setNameMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [panValue, setPanValue] = useState(pan ?? '')
  const [panMsg, setPanMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    setNameValue(displayName ?? '')
  }, [displayName])

  useEffect(() => {
    setPanValue(pan ?? '')
  }, [pan])

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [passwordMsg, setPasswordMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const saveName = useMutation({
    mutationFn: (value: string) => apiClient.updateProfile({ display_name: value }),
    onSuccess: (data) => {
      setIdentity({
        userId,
        displayName: data.display_name ?? null,
      })
      setNameValue(data.display_name ?? '')
      setNameMsg({ type: 'success', text: 'Display name saved.' })
    },
    onError: (e: any) => {
      setNameMsg({
        type: 'error',
        text: e?.response?.data?.detail ?? 'Could not save display name.',
      })
    },
  })

  const savePan = useMutation({
    mutationFn: (value: string) => apiClient.setProfilePan(value),
    onSuccess: (data) => {
      setIdentity({ userId, pan: data.pan })
      setPanValue(data.pan ?? '')
      setPanMsg({ type: 'success', text: 'PAN saved.' })
    },
    onError: (e: any) => {
      setPanMsg({
        type: 'error',
        text: e?.response?.data?.detail ?? 'Could not save your PAN.',
      })
    },
  })

  const savePassword = useMutation({
    mutationFn: (value: string) => authClient.updatePassword(value),
    onSuccess: () => {
      setPassword('')
      setConfirm('')
      setPasswordMsg({ type: 'success', text: 'Password updated.' })
    },
    onError: (e: any) => {
      setPasswordMsg({
        type: 'error',
        text: e?.message ?? e?.response?.data?.detail ?? 'Could not update password.',
      })
    },
  })

  const onSaveName = (e: FormEvent) => {
    e.preventDefault()
    setNameMsg(null)
    saveName.mutate(nameValue.trim())
  }

  const onSavePan = (e: FormEvent) => {
    e.preventDefault()
    setPanMsg(null)
    const next = panValue.trim().toUpperCase()
    if (!PAN_PATTERN.test(next)) {
      setPanMsg({ type: 'error', text: 'That does not look like a PAN. Format: ABCDE1234F.' })
      return
    }
    savePan.mutate(next)
  }

  const onSavePassword = (e: FormEvent) => {
    e.preventDefault()
    setPasswordMsg(null)
    if (password.trim().length < 8) {
      setPasswordMsg({ type: 'error', text: 'Password must be at least 8 characters.' })
      return
    }
    if (password !== confirm) {
      setPasswordMsg({ type: 'error', text: 'Passwords do not match.' })
      return
    }
    savePassword.mutate(password)
  }

  const initials = (displayName || email || pan || '?').substring(0, 2).toUpperCase()

  return (
    <Box
      sx={{
        maxWidth: 720,
        mx: 'auto',
        px: { xs: 2, sm: 3 },
        py: { xs: 3, sm: 4 },
      }}
    >
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate(-1)}
        sx={{
          mb: 2.5,
          color: '#94A3B8',
          textTransform: 'none',
          fontWeight: 700,
          '&:hover': { color: '#F8FAFC', bgcolor: 'rgba(255,255,255,0.04)' },
        }}
      >
        Back
      </Button>

      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 3.5 }}>
        <Box
          sx={{
            width: 56,
            height: 56,
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #6366F1 0%, #38BDF8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontWeight: 800,
            fontSize: '1.1rem',
            boxShadow: '0 8px 24px rgba(99, 102, 241, 0.28)',
          }}
        >
          {initials}
        </Box>
        <Box>
          <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '-0.02em' }}>
            Profile
          </Typography>
          <Typography sx={{ color: '#94A3B8', fontSize: '0.9rem', mt: 0.25 }}>
            {email ?? 'Signed-in account'}
          </Typography>
        </Box>
      </Stack>

      <Stack spacing={2.5}>
        <SectionCard
          icon={<PersonOutlineIcon fontSize="small" />}
          title="Account"
          subtitle="Read-only identity details from your sign-in."
        >
          <Stack spacing={1.25}>
            <Row label="Email" value={email ?? '—'} />
            <Row label="Status" value={(status ?? '—').toString()} />
            <Row label="Role" value={role === 'admin' ? 'Admin' : 'User'} />
          </Stack>
        </SectionCard>

        <SectionCard
          icon={<PersonOutlineIcon fontSize="small" />}
          title="Display name"
          subtitle="Shown on the account badge. Leave blank to use your email."
        >
          <Box component="form" onSubmit={onSaveName}>
            <TextField
              fullWidth
              label="Display name"
              value={nameValue}
              onChange={(e) => setNameValue(e.target.value)}
              inputProps={{ maxLength: 64 }}
              sx={{ ...fieldSx, mb: 1.5 }}
            />
            {nameMsg && (
              <Alert severity={nameMsg.type} sx={{ mb: 1.5, borderRadius: '12px' }}>
                {nameMsg.text}
              </Alert>
            )}
            <Button
              type="submit"
              variant="contained"
              disabled={saveName.isPending}
              sx={{
                textTransform: 'none',
                fontWeight: 700,
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
              }}
            >
              {saveName.isPending ? 'Saving…' : 'Save name'}
            </Button>
          </Box>
        </SectionCard>

        <SectionCard
          icon={<BadgeIcon fontSize="small" />}
          title="PAN"
          subtitle="Used to unlock CAS PDFs and match AIS. Encrypted at rest."
        >
          <Box component="form" onSubmit={onSavePan}>
            <TextField
              fullWidth
              label="PAN"
              value={panValue}
              onChange={(e) => setPanValue(e.target.value.toUpperCase())}
              placeholder="ABCDE1234F"
              inputProps={{
                maxLength: 10,
                style: { letterSpacing: 2, fontWeight: 700, fontFamily: 'monospace' },
              }}
              autoComplete="off"
              sx={{ ...fieldSx, mb: 1.5 }}
            />
            {panMsg && (
              <Alert severity={panMsg.type} sx={{ mb: 1.5, borderRadius: '12px' }}>
                {panMsg.text}
              </Alert>
            )}
            <Button
              type="submit"
              variant="contained"
              disabled={savePan.isPending}
              sx={{
                textTransform: 'none',
                fontWeight: 700,
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
              }}
            >
              {savePan.isPending ? 'Saving…' : pan ? 'Update PAN' : 'Save PAN'}
            </Button>
          </Box>
        </SectionCard>

        <SectionCard
          icon={<LockOutlinedIcon fontSize="small" />}
          title="Password"
          subtitle="Updates your FinanceBuddy sign-in password (email / invite accounts)."
        >
          <Box component="form" onSubmit={onSavePassword}>
            <Stack spacing={1.5} sx={{ mb: 1.5 }}>
              <TextField
                fullWidth
                type={showPassword ? 'text' : 'password'}
                label="New password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
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
                autoComplete="new-password"
                sx={fieldSx}
              />
            </Stack>
            {passwordMsg && (
              <Alert severity={passwordMsg.type} sx={{ mb: 1.5, borderRadius: '12px' }}>
                {passwordMsg.text}
              </Alert>
            )}
            <Button
              type="submit"
              variant="contained"
              disabled={savePassword.isPending || !password}
              sx={{
                textTransform: 'none',
                fontWeight: 700,
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
              }}
            >
              {savePassword.isPending ? 'Updating…' : 'Update password'}
            </Button>
          </Box>
        </SectionCard>

        <SectionCard
          icon={<SecurityIcon fontSize="small" />}
          title="Privacy & data"
          subtitle="Export or permanently delete the data stored for this account."
        >
          <Button
            variant="outlined"
            onClick={() => navigate('/accounts')}
            sx={{
              textTransform: 'none',
              fontWeight: 700,
              borderRadius: '12px',
              borderColor: 'rgba(78, 222, 147, 0.45)',
              color: '#4EDE93',
              '&:hover': {
                borderColor: '#4EDE93',
                bgcolor: 'rgba(78, 222, 147, 0.08)',
              },
            }}
          >
            Open accounts vault
          </Button>
        </SectionCard>
      </Stack>
    </Box>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        gap: 2,
        py: 1,
        borderBottom: '1px solid rgba(255,255,255,0.05)',
        '&:last-of-type': { borderBottom: 'none' },
      }}
    >
      <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', fontWeight: 600 }}>{label}</Typography>
      <Typography
        sx={{
          color: '#F8FAFC',
          fontSize: '0.85rem',
          fontWeight: 700,
          textAlign: 'right',
          wordBreak: 'break-all',
          textTransform: label === 'Status' || label === 'Role' ? 'capitalize' : 'none',
        }}
      >
        {value}
      </Typography>
    </Box>
  )
}
