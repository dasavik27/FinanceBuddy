/**
 * MFUploadPanel.tsx
 *
 * Smart upload experience for the Mutual Funds domain.
 * - "No session" mode: full-page hero with upload zone + history side-by-side
 * - "Switch statement" mode: compact popover with history list + mini upload zone
 *
 * History shows last 3 CAS snapshots with one-click restore. Upload zone auto-
 * uses the logged-in PAN as the PDF password (no manual entry required).
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Box, Typography, Button, Alert, CircularProgress,
  Paper, Chip, Stack, Popover, Divider, IconButton, Tooltip,
} from '@mui/material'
import UploadFileIcon      from '@mui/icons-material/UploadFile'
import CheckCircleIcon     from '@mui/icons-material/CheckCircle'
import ShieldIcon          from '@mui/icons-material/Shield'
import HistoryIcon         from '@mui/icons-material/History'
import ChevronRightIcon    from '@mui/icons-material/ChevronRight'
import SwapHorizIcon       from '@mui/icons-material/SwapHoriz'
import CloudUploadIcon     from '@mui/icons-material/CloudUpload'
import CloseIcon           from '@mui/icons-material/Close'
import AccountBalanceIcon  from '@mui/icons-material/AccountBalance'
import { apiClient }       from '../../../shared/api/client'
import { useAppStore }     from '../../../shared/store/appStore'
import { SwitchSessionButton } from '../../../shared/components/dashboard/SwitchSessionButton'
import { UploadHistoryList } from '../../../shared/components/dashboard/UploadHistoryList'
import type { UploadHistoryListProps } from '../../../shared/components/dashboard/UploadHistoryList'

// ────────────────────────────────────────────────────────────────
// Shared helpers
// ────────────────────────────────────────────────────────────────



// ────────────────────────────────────────────────────────────────
// HistoryList — reused in both modes
// ────────────────────────────────────────────────────────────────

// Shared with the equity panel; see shared/components/dashboard/UploadHistoryList.
function HistoryList(props: Omit<UploadHistoryListProps, 'accent' | 'itemLabel' | 'renderBadges'>) {
  return (
    <UploadHistoryList
      {...props}
      accent="indigo"
      itemLabel="Funds"
      renderBadges={(h) =>
        h.statement_period ? (
          <Typography sx={{ color: '#38BDF8', fontWeight: 600, fontSize: '0.7rem' }}>
            Period: {h.statement_period}
          </Typography>
        ) : null
      }
    />
  )
}

// ────────────────────────────────────────────────────────────────
// MiniDropzone — compact drop zone for the popover
// ────────────────────────────────────────────────────────────────

interface MiniDropzoneProps {
  onUploaded: () => void
}

function MiniDropzone({ onUploaded }: MiniDropzoneProps) {
  const [file, setFile]     = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const setSession = useAppStore((s) => s.setSession)
  const setIdentity = useAppStore((s) => s.setIdentity)

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  })

  const handleUpload = async () => {
    if (!file) return
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.parseFile(file, password, 'mutual_funds')
      setSession(data.session_id, 'mutual_funds', data)
      if (password.trim()) {
        setIdentity({ userId: useAppStore.getState().userId, pan: password.trim().toUpperCase() })
      }
      onUploaded()
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse. Please check the file.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box>
      {error && (
        <Alert severity="error" sx={{ mb: 1.5, borderRadius: '12px', fontSize: '0.8rem' }}>{error}</Alert>
      )}
      <Box
        {...getRootProps()}
        component={motion.div as any}
        whileHover={{ scale: 1.01 }}
        whileTap={{ scale: 0.98 }}
        sx={{
          border: `2px dashed ${isDragActive ? '#6366F1' : file ? '#4EDE93' : 'rgba(255,255,255,0.12)'}`,
          borderRadius: '16px',
          p: 2.5,
          textAlign: 'center',
          cursor: 'pointer',
          background: isDragActive ? 'rgba(99,102,241,0.08)' : file ? 'rgba(78,222,147,0.04)' : 'rgba(255,255,255,0.02)',
          transition: 'all 0.25s ease',
          '&:hover': { borderColor: file ? '#4EDE93' : '#6366F1' },
        }}
      >
        <input {...getInputProps()} />
        {file ? (
          <Box>
            <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 28, mb: 0.5 }} />
            <Typography sx={{ color: '#4EDE93', fontWeight: 700, fontSize: '0.82rem', wordBreak: 'break-all' }}>
              {file.name}
            </Typography>
            <Typography sx={{ color: '#64748B', fontSize: '0.72rem' }}>{(file.size / 1024).toFixed(0)} KB · Click to replace</Typography>
          </Box>
        ) : (
          <Box>
            <CloudUploadIcon sx={{ color: '#6366F1', fontSize: 28, mb: 0.5 }} />
            <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.82rem' }}>
              {isDragActive ? 'Drop CAS PDF here' : 'Drop or click to upload new CAS'}
            </Typography>
          </Box>
        )}
      </Box>

      {file && (
        <Box>
          <Box sx={{ mt: 2, mb: 1 }}>
            <Typography sx={{ color: '#94A3B8', fontSize: '0.75rem', mb: 0.5, fontWeight: 600 }}>PDF Password (Optional)</Typography>
            <input 
              type="password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Defaults to PAN if blank"
              style={{
                width: '100%', padding: '10px 14px', borderRadius: '10px',
                background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                color: '#fff', outline: 'none', fontSize: '0.85rem'
              }}
            />
          </Box>
          <Button
            fullWidth variant="contained" onClick={handleUpload} disabled={loading}
            sx={{
              mt: 1.5, py: 1.2, borderRadius: '12px', fontWeight: 800, fontSize: '0.88rem',
              background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
              color: '#fff',
              boxShadow: '0 6px 20px rgba(99,102,241,0.4)', textTransform: 'none',
              '&:hover': { background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)' },
              '&.Mui-disabled': { background: 'linear-gradient(135deg, rgba(99,102,241,0.7) 0%, rgba(79,70,229,0.7) 100%)', color: 'rgba(255,255,255,0.9)' }
            }}
          >
            {loading ? <><CircularProgress size={16} sx={{ color: '#fff', mr: 1 }} />Importing...</> : 'Import & Analyse'}
          </Button>
        </Box>
      )}
    </Box>
  )
}

// ────────────────────────────────────────────────────────────────
// SwitchStatementPopover — shown when a session already exists
// ────────────────────────────────────────────────────────────────

interface SwitchPopoverProps {
  sessionId: string | null
}

export function SwitchStatementButton({ sessionId }: SwitchPopoverProps) {
  const setSessionById = useAppStore((s) => s.setSessionById)
  const pan = useAppStore((s) => s.pan)

  const fetchHistory = useCallback(async () => {
    if (!pan) return []
    const res = await apiClient.getHistory('mutual_funds')
    return res?.history ?? []
  }, [pan])

  return (
    <SwitchSessionButton
      sessionId={sessionId}
      fetchHistory={fetchHistory}
      onSelect={(sid) => setSessionById(sid, 'mutual_funds')}
      accent="indigo"
      buttonLabel="Switch Statement"
      tooltip="Switch portfolio statement or upload a new CAS"
      popoverTitle="Portfolio Statements"
      itemLabel="Funds"
      renderBadges={(h) =>
        h.statement_period ? (
          <Typography sx={{ color: '#38BDF8', fontWeight: 600, fontSize: '0.7rem' }}>
            Period: {h.statement_period}
          </Typography>
        ) : null
      }
      footerTitle="Import New Statement"
      renderFooter={(close) => <MiniDropzone onUploaded={close} />}
    />
  )
}

// ────────────────────────────────────────────────────────────────
// MFUploadPanel — full page, shown when no session exists
// ────────────────────────────────────────────────────────────────

export default function MFUploadPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [password, setPassword] = useState('')
  const [history, setHistory] = useState<any[]>([])
  const setSession = useAppStore((s) => s.setSession)
  const setSessionById = useAppStore((s) => s.setSessionById)
  const pan = useAppStore((s) => s.pan)
  const setIdentity = useAppStore((s) => s.setIdentity)

  const fetchHistory = useCallback(() => {
    if (!pan) return
    apiClient.getHistory('mutual_funds')
      .then((res) => { if (res?.history) setHistory(res.history) })
      .catch(console.error)
  }, [pan])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  })

  const handleAnalyze = async () => {
    if (!file) return setError('Please drop or select a CAS PDF.')
    setLoading(true); setError(null)
    try {
      const data = await apiClient.parseFile(file, password, 'mutual_funds')
      setSession(data.session_id, 'mutual_funds', data)
      if (password.trim()) {
        setIdentity({ userId: useAppStore.getState().userId, pan: password.trim().toUpperCase() })
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse. Please check the file.')
    } finally {
      setLoading(false)
    }
  }

  const hasHistory = history.length > 0

  return (
    <Box sx={{ py: { xs: 4, md: 8 }, px: { xs: 2, md: 0 } }}>
      {/* Page header */}
      <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1.5, background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: '40px', px: 2.5, py: 1, mb: 3 }}>
            <AccountBalanceIcon sx={{ color: '#818CF8', fontSize: 18 }} />
            <Typography sx={{ color: '#818CF8', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.06em' }}>MUTUAL FUNDS PORTFOLIO</Typography>
          </Box>
          <Typography variant="h4" sx={{ fontWeight: 900, color: '#F8FAFC', mb: 1.5, letterSpacing: '-0.02em' }}>
            {hasHistory ? 'Welcome back — pick up where you left off' : 'Import Your CAS Statement'}
          </Typography>
          <Typography sx={{ color: '#64748B', fontSize: '1rem', maxWidth: 520, mx: 'auto' }}>
            {hasHistory
              ? 'Restore a previous portfolio snapshot instantly, or import a fresh CAS PDF to get updated analytics.'
              : 'Upload your CAMS / Karvy Consolidated Account Statement to unlock your full portfolio analytics cockpit.'}
          </Typography>
        </Box>
      </motion.div>

      {/* Two-column (or single) layout */}
      <Box sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', lg: hasHistory ? '1fr 1fr' : '1fr' },
        gap: 4,
        maxWidth: hasHistory ? 1000 : 520,
        mx: 'auto',
      }}>

        {/* ── Upload card ── */}
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.45 }}>
          <Paper className="glass" sx={{
            p: { xs: 3, md: 5 }, borderRadius: '28px',
            border: '1px solid rgba(99,102,241,0.25)',
            background: 'rgba(15,23,42,0.8)',
            boxShadow: '0 25px 60px rgba(0,0,0,0.6), 0 0 40px rgba(99,102,241,0.1)',
            height: '100%', display: 'flex', flexDirection: 'column',
          }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
              <CloudUploadIcon sx={{ color: '#6366F1', fontSize: 22 }} />
              <Typography sx={{ fontWeight: 800, fontSize: '1.1rem', color: '#F8FAFC' }}>
                {hasHistory ? 'Import New Statement' : 'Upload CAS PDF'}
              </Typography>
            </Box>
            <Typography sx={{ color: '#64748B', fontSize: '0.85rem', mb: 3 }}>
              Your PAN is used automatically to unlock the PDF — no password needed.
            </Typography>

            {error && (
              <Alert severity="error" sx={{ mb: 2.5, borderRadius: '14px' }}>{error}</Alert>
            )}

            {/* Drop zone */}
            <Box
              {...getRootProps()}
              component={motion.div as any}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              sx={{
                flex: 1, minWidth: 0,
                border: `2px dashed ${isDragActive ? '#6366F1' : file ? '#4EDE93' : 'rgba(255,255,255,0.1)'}`,
                borderRadius: '20px',
                p: { xs: 4, md: 6 },
                textAlign: 'center',
                cursor: 'pointer',
                background: isDragActive ? 'rgba(99,102,241,0.08)' : file ? 'rgba(78,222,147,0.04)' : 'rgba(255,255,255,0.01)',
                transition: 'all 0.25s ease',
                mb: 3,
                '&:hover': { borderColor: file ? '#4EDE93' : '#6366F1', background: file ? 'rgba(78,222,147,0.06)' : 'rgba(99,102,241,0.05)' },
              }}
            >
              <input {...getInputProps()} />
              <AnimatePresence mode="wait">
                {file ? (
                  <motion.div key="file" initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.85 }}>
                    <Box sx={{ width: 56, height: 56, mx: 'auto', mb: 2, borderRadius: '50%', background: 'rgba(78,222,147,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <CheckCircleIcon sx={{ fontSize: 28, color: '#4EDE93' }} />
                    </Box>
                    <Typography sx={{ color: '#4EDE93', fontWeight: 800, fontSize: '1rem', mb: 0.5, wordBreak: 'break-all', px: 2 }}>{file.name}</Typography>
                    <Typography sx={{ color: '#64748B', fontSize: '0.8rem' }}>{(file.size / 1024).toFixed(0)} KB · Click to replace</Typography>
                  </motion.div>
                ) : (
                  <motion.div key="empty" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                    <motion.div animate={{ y: [0, -7, 0] }} transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}>
                      <Box sx={{ width: 64, height: 64, mx: 'auto', mb: 2.5, borderRadius: '18px', background: 'linear-gradient(135deg, rgba(99,102,241,0.2) 0%, rgba(79,70,229,0.2) 100%)', border: '1px solid rgba(99,102,241,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <UploadFileIcon sx={{ fontSize: 32, color: '#818CF8' }} />
                      </Box>
                    </motion.div>
                    <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1rem', mb: 0.75 }}>
                      {isDragActive ? 'Release to import' : 'Drag & drop your CAS PDF'}
                    </Typography>
                    <Typography sx={{ color: '#475569', fontSize: '0.85rem' }}>or click here to browse from your device</Typography>
                  </motion.div>
                )}
              </AnimatePresence>
            </Box>

            {file && (
              <Box>
                <Box sx={{ mb: 2 }}>
                  <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mb: 1, fontWeight: 600 }}>PDF Password (Optional)</Typography>
                  <input 
                    type="password" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Defaults to your PAN if left blank"
                    style={{
                      width: '100%', padding: '14px 18px', borderRadius: '14px',
                      background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                      color: '#fff', outline: 'none', fontSize: '0.95rem'
                    }}
                  />
                </Box>
                <Button
                  fullWidth variant="contained" size="large"
                  onClick={handleAnalyze} disabled={loading}
                  sx={{
                    py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1.05rem',
                    background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
                    color: '#fff',
                    boxShadow: '0 8px 28px rgba(99,102,241,0.45)', textTransform: 'none',
                    '&:hover': { background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)', boxShadow: '0 12px 36px rgba(99,102,241,0.6)' },
                    '&.Mui-disabled': { background: 'linear-gradient(135deg, rgba(99,102,241,0.7) 0%, rgba(79,70,229,0.7) 100%)', color: 'rgba(255,255,255,0.9)' }
                  }}
                >
                  {loading ? <><CircularProgress size={20} sx={{ color: '#fff', mr: 1.5 }} />Analysing Portfolio...</> : 'Analyse Portfolio'}
                </Button>
              </Box>
            )}

            <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', color: '#334155', mt: 2 }}>
              <ShieldIcon sx={{ fontSize: 11, verticalAlign: 'middle', mr: 0.5, color: '#4EDE93' }} />
              Processed on your backend only — never shared
            </Typography>
          </Paper>
        </motion.div>

        {/* ── History card ── */}
        {hasHistory && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2, duration: 0.45 }} style={{ height: '100%' }}>
            <Paper className="glass" sx={{
              p: { xs: 3, md: 4.5 }, borderRadius: '28px',
              border: '1px solid rgba(255,255,255,0.06)',
              background: 'rgba(15,23,42,0.6)',
              height: '100%', display: 'flex', flexDirection: 'column',
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <HistoryIcon sx={{ color: '#6366F1', fontSize: 20 }} />
                  <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: '#F8FAFC' }}>Previous Statements</Typography>
                </Box>
                <Chip label={`${history.length} saved`} size="small" sx={{ background: 'rgba(255,255,255,0.05)', color: '#64748B', fontSize: '0.7rem', fontWeight: 700, borderRadius: '8px' }} />
              </Box>

              <Typography sx={{ color: '#475569', fontSize: '0.82rem', mb: 2.5 }}>
                Click any snapshot below to instantly restore that portfolio view.
              </Typography>

              <Box sx={{ flex: 1 }}>
                <HistoryList history={history} onSelect={(sid) => setSessionById(sid, 'mutual_funds')} compact={false} />
              </Box>
            </Paper>
          </motion.div>
        )}
      </Box>
    </Box>
  )
}