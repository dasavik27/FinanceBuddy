/**
 * TaxUploadPanel.tsx
 *
 * Smart upload experience for the Tax Expert domain.
 * - "No session" mode: full-page hero with upload zone + history side-by-side
 * - "Switch session" mode: compact popover with history list + mini upload zone
 *
 * History cards show FY (Financial Year) and AY (Assessment Year) as the primary
 * identifiers — the tax equivalent of Mutual Funds' statement_period.
 *
 * Design mirrors MFUploadPanel.tsx exactly.
 */

import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Box, Typography, Button, Alert, CircularProgress,
  Paper, Chip, Stack, Popover, Divider, IconButton, Tooltip,
} from '@mui/material'
import UploadFileIcon     from '@mui/icons-material/UploadFile'
import CheckCircleIcon    from '@mui/icons-material/CheckCircle'
import ShieldIcon         from '@mui/icons-material/Shield'
import HistoryIcon        from '@mui/icons-material/History'
import ChevronRightIcon   from '@mui/icons-material/ChevronRight'
import SwapHorizIcon      from '@mui/icons-material/SwapHoriz'
import CloudUploadIcon    from '@mui/icons-material/CloudUpload'
import CloseIcon          from '@mui/icons-material/Close'
import DescriptionIcon    from '@mui/icons-material/Description'
import { apiClient }      from '../../../shared/api/client'
import { useAppStore, useIsAuthenticated } from '../../../shared/store/appStore'

// ────────────────────────────────────────────────────────────────
// Shared helpers
// ────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso + 'Z'))
}

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0,
  }).format(v)
}

// ────────────────────────────────────────────────────────────────
// HistoryList — reused in both modes
// ────────────────────────────────────────────────────────────────

interface TaxHistoryItem {
  session_id: string
  fy: string
  ay: string
  name: string
  gross_salary: number
  created_at: string
}

/**
 * Assessment Year from Financial Year, e.g. "2024-25" -> "2025-26".
 *
 * The backend doesn't send this - it never has, on either branch's version of
 * get_sessions_by_user. Computed here rather than added server-side because it's a
 * pure display transform of a value the response already carries, and every other
 * caller of that endpoint (TaxHistoryTab, the summary screens) has no use for it.
 */
function deriveAY(fy: string): string {
  if (!fy || !fy.includes('-')) return ''
  const startYear = parseInt(fy.split('-')[0], 10)
  if (Number.isNaN(startYear)) return ''
  return `${startYear + 1}-${String(startYear + 2).slice(-2)}`
}

function withAY(sessions: any[]): TaxHistoryItem[] {
  return sessions.map((s) => ({ ...s, ay: s.ay || deriveAY(s.fy) }))
}

interface HistoryListProps {
  history: TaxHistoryItem[]
  onSelect: (sid: string) => void
  activeSessionId?: string | null
  compact?: boolean
}

function HistoryList({ history, onSelect, activeSessionId, compact }: HistoryListProps) {
  if (history.length === 0) return (
    <Box sx={{ textAlign: 'center', py: compact ? 2 : 4 }}>
      <Typography sx={{ color: '#475569', fontSize: '0.85rem' }}>No previous AIS sessions found</Typography>
    </Box>
  )

  return (
    <Stack spacing={compact ? 1 : 1.5}>
      {history.slice(0, 5).map((h, i) => {
        const isActive = h.session_id === activeSessionId
        return (
          <motion.div
            key={h.session_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <Box
              onClick={() => onSelect(h.session_id)}
              sx={{
                display: 'flex', alignItems: 'center',
                p: compact ? 1.5 : 2,
                background: isActive
                  ? 'linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(79,70,229,0.08) 100%)'
                  : 'linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
                border: `1px solid ${isActive ? 'rgba(99,102,241,0.5)' : 'rgba(255,255,255,0.07)'}`,
                borderRadius: '16px',
                cursor: isActive ? 'default' : 'pointer',
                transition: 'all 0.25s ease',
                '&:hover': isActive ? {} : {
                  background: 'linear-gradient(135deg, rgba(99,102,241,0.1) 0%, rgba(79,70,229,0.05) 100%)',
                  borderColor: 'rgba(99,102,241,0.35)',
                  transform: 'translateY(-1px)',
                  '& .chevron': { color: '#818CF8', transform: 'translateX(3px)' },
                },
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                {/* Primary identifiers: FY & AY */}
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.75, flexWrap: 'wrap' }}>
                  {h.fy && (
                    <Chip
                      label={`FY ${h.fy}`}
                      size="small"
                      sx={{ height: 20, fontSize: '0.72rem', fontWeight: 800, background: 'rgba(56,189,248,0.15)', color: '#38BDF8', borderRadius: '6px' }}
                    />
                  )}
                  {h.ay && (
                    <Chip
                      label={`AY ${h.ay}`}
                      size="small"
                      sx={{ height: 20, fontSize: '0.72rem', fontWeight: 800, background: 'rgba(99,102,241,0.15)', color: '#818CF8', borderRadius: '6px' }}
                    />
                  )}
                  {isActive && (
                    <Chip
                      label="Active"
                      size="small"
                      sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, background: 'rgba(99,102,241,0.25)', color: '#818CF8', borderRadius: '6px' }}
                    />
                  )}
                </Box>

                {/* Uploaded date */}
                <Typography sx={{ color: '#94A3B8', fontSize: compact ? '0.72rem' : '0.8rem', mb: 0.5 }}>
                  Uploaded: {fmtDate(h.created_at)}
                </Typography>

                {/* Stats row */}
                <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
                  {h.name && (
                    <Chip label={h.name} size="small" sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700, background: 'rgba(255,255,255,0.08)', color: '#E2E8F0', borderRadius: '6px' }} />
                  )}
                  {h.gross_salary > 0 && (
                    <Chip label={`Salary ${fmtINR(h.gross_salary)}`} size="small" sx={{ height: 20, fontSize: '0.7rem', fontWeight: 800, background: 'rgba(78,222,147,0.1)', color: '#4EDE93', borderRadius: '6px' }} />
                  )}
                </Box>
              </Box>

              {!isActive && (
                <ChevronRightIcon className="chevron" sx={{ color: '#475569', fontSize: 18, transition: 'all 0.25s ease', flexShrink: 0 }} />
              )}
            </Box>
          </motion.div>
        )
      })}
    </Stack>
  )
}

// ────────────────────────────────────────────────────────────────
// MiniDropzone — compact drop zone for the popover
// ────────────────────────────────────────────────────────────────

interface MiniDropzoneProps {
  onUploaded: () => void
}

function MiniDropzone({ onUploaded }: MiniDropzoneProps) {
  const [file, setFile]       = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const setSession = useAppStore((s) => s.setSession)

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  })

  const handleUpload = async () => {
    if (!file) return
    setLoading(true); setError(null)
    try {
      const data = await apiClient.parseAIS(file)
      setSession(data.session_id, 'tax_expert', data)
      onUploaded()
    } catch (e: any) {
      const type = e?.response?.data?.detail?.type
      if (type === 'AIS_UNKNOWN_CODE') {
        setError(`⚠️ New AIS code detected: ${e.response.data.detail.code}. Contact support.`)
      } else {
        setError(e?.response?.data?.detail ?? 'Failed to parse AIS. Please verify the file.')
      }
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
          borderRadius: '16px', p: 2.5, textAlign: 'center', cursor: 'pointer',
          background: isDragActive ? 'rgba(99,102,241,0.08)' : file ? 'rgba(78,222,147,0.04)' : 'rgba(255,255,255,0.02)',
          transition: 'all 0.25s ease',
          '&:hover': { borderColor: file ? '#4EDE93' : '#6366F1' },
        }}
      >
        <input {...getInputProps()} />
        {file ? (
          <Box>
            <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 28, mb: 0.5 }} />
            <Typography sx={{ color: '#4EDE93', fontWeight: 700, fontSize: '0.82rem', wordBreak: 'break-all' }}>{file.name}</Typography>
            <Typography sx={{ color: '#64748B', fontSize: '0.72rem' }}>{(file.size / 1024).toFixed(0)} KB · Click to replace</Typography>
          </Box>
        ) : (
          <Box>
            <CloudUploadIcon sx={{ color: '#6366F1', fontSize: 28, mb: 0.5 }} />
            <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.82rem' }}>
              {isDragActive ? 'Drop AIS PDF here' : 'Drop or click to upload new AIS'}
            </Typography>
          </Box>
        )}
      </Box>

      {file && (
        <Button
          fullWidth variant="contained" onClick={handleUpload} disabled={loading}
          sx={{
            mt: 1.5, py: 1.2, borderRadius: '12px', fontWeight: 800, fontSize: '0.88rem',
            background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)', color: '#fff',
            boxShadow: '0 6px 20px rgba(99,102,241,0.4)', textTransform: 'none',
            '&:hover': { background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)' },
            '&.Mui-disabled': { background: 'linear-gradient(135deg, rgba(99,102,241,0.7) 0%, rgba(79,70,229,0.7) 100%)', color: 'rgba(255,255,255,0.9)' }
          }}
        >
          {loading ? <><CircularProgress size={16} sx={{ color: '#fff', mr: 1 }} />Computing Taxes...</> : '🧮 Compute & Import'}
        </Button>
      )}
    </Box>
  )
}

// ────────────────────────────────────────────────────────────────
// SwitchTaxSessionButton — compact popover shown when session active
// ────────────────────────────────────────────────────────────────

interface SwitchTaxPopoverProps {
  sessionId: string | null
}

export function SwitchTaxSessionButton({ sessionId }: SwitchTaxPopoverProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [history, setHistory]   = useState<TaxHistoryItem[]>([])
  const setSessionById = useAppStore((s) => s.setSessionById)
  const isAuthenticated = useIsAuthenticated()
  const open = Boolean(anchorEl)

  const fetchHistory = useCallback(() => {
    if (!isAuthenticated) return
    apiClient.getTaxHistory()
      .then((res) => { if (res?.sessions) setHistory(withAY(res.sessions)) })
      .catch(console.error)
  }, [isAuthenticated])

  useEffect(() => {
    if (open) fetchHistory()
  }, [open, fetchHistory])

  const handleSelect = (sid: string) => {
    setSessionById(sid, 'tax_expert')
    setAnchorEl(null)
  }

  return (
    <>
      <Tooltip title="Switch AIS session or upload a new Annual Information Statement" placement="bottom">
        <Button
          variant="outlined" size="small"
          startIcon={<SwapHorizIcon sx={{ fontSize: 16 }} />}
          onClick={(e) => setAnchorEl(e.currentTarget)}
          sx={{
            borderColor: 'rgba(99,102,241,0.35)', color: '#94A3B8',
            textTransform: 'none', fontWeight: 700, fontSize: '0.82rem', borderRadius: '10px', px: 1.5,
            '&:hover': { borderColor: '#6366F1', color: '#818CF8', background: 'rgba(99,102,241,0.08)' },
          }}
        >
          Switch Session
        </Button>
      </Tooltip>

      <Popover
        open={open}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{
          sx: {
            mt: 1, width: 390, borderRadius: '20px',
            background: 'rgba(15,23,42,0.97)',
            border: '1px solid rgba(99,102,241,0.2)',
            boxShadow: '0 24px 60px rgba(0,0,0,0.6), 0 0 40px rgba(99,102,241,0.1)',
            backdropFilter: 'blur(20px)', overflow: 'hidden',
          }
        }}
      >
        <Box sx={{ px: 2.5, pt: 2.5, pb: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <HistoryIcon sx={{ color: '#6366F1', fontSize: 18 }} />
            <Typography sx={{ fontWeight: 800, fontSize: '0.9rem', color: '#F8FAFC' }}>AIS Sessions</Typography>
          </Box>
          <IconButton size="small" onClick={() => setAnchorEl(null)} sx={{ color: '#475569', '&:hover': { color: '#94A3B8' } }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ px: 2.5, pb: 1.5 }}>
          <HistoryList history={history} onSelect={handleSelect} activeSessionId={sessionId} compact />
        </Box>

        <Divider sx={{ borderColor: 'rgba(255,255,255,0.06)', mx: 2.5 }} />

        <Box sx={{ px: 2.5, pt: 2, pb: 2.5 }}>
          <Typography sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.72rem', letterSpacing: '0.08em', textTransform: 'uppercase', mb: 1.5 }}>
            Import New AIS
          </Typography>
          <MiniDropzone onUploaded={() => setAnchorEl(null)} />
        </Box>

        <Box sx={{ px: 2.5, pb: 2, textAlign: 'center' }}>
          <Typography variant="caption" sx={{ color: '#334155', fontSize: '0.68rem' }}>
            <ShieldIcon sx={{ fontSize: 10, verticalAlign: 'middle', mr: 0.5, color: '#4EDE93' }} />
            Processed on your backend only
          </Typography>
        </Box>
      </Popover>
    </>
  )
}

// ────────────────────────────────────────────────────────────────
// TaxUploadPanel — full page, shown when no session exists
// ────────────────────────────────────────────────────────────────

interface TaxUploadPanelProps {
  onSessionCreated: (sid: string, data: any) => void
  sessionExpired?: boolean
}

export default function TaxUploadPanel({ onSessionCreated, sessionExpired = false }: TaxUploadPanelProps) {
  const [file, setFile]       = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [history, setHistory] = useState<TaxHistoryItem[]>([])
  const setSessionById = useAppStore((s) => s.setSessionById)
  const isAuthenticated = useIsAuthenticated()

  const fetchHistory = useCallback(() => {
    if (!isAuthenticated) return
    apiClient.getTaxHistory()
      .then((res) => { if (res?.sessions) setHistory(withAY(res.sessions)) })
      .catch(console.error)
  }, [isAuthenticated])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  })

  const handleAnalyze = async () => {
    if (!file) return setError('Please drop or select an AIS PDF.')
    setLoading(true); setError(null)
    try {
      const data = await apiClient.parseAIS(file)
      onSessionCreated(data.session_id, data)
    } catch (e: any) {
      const type = e?.response?.data?.detail?.type
      if (type === 'AIS_UNKNOWN_CODE') {
        const code = e.response.data.detail.code
        setError(`⚠️ New AIS Information Code Detected: ${code}. Please contact support.`)
      } else if (type === 'AIS_STRUCTURE_CHANGED') {
        const msg = e.response.data.detail.message
        const diff = JSON.stringify(e.response.data.detail.diff, null, 2)
        setError(`⚠️ ${msg}\n\nDiff: ${diff}\n\nThe Income Tax Department updated the PDF format. Please contact support.`)
      } else {
        setError(
          typeof e?.response?.data?.detail === 'string'
            ? e.response.data.detail
            : 'Failed to parse AIS. Ensure this is a valid Annual Information Statement PDF.'
        )
      }
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
            <DescriptionIcon sx={{ color: '#818CF8', fontSize: 18 }} />
            <Typography sx={{ color: '#818CF8', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.06em' }}>TAX EXPERT · AIS ANALYSER</Typography>
          </Box>
          <Typography variant="h4" sx={{ fontWeight: 900, color: '#F8FAFC', mb: 1.5, letterSpacing: '-0.02em' }}>
            {hasHistory ? 'Welcome back — pick up where you left off' : 'Import Your Annual Information Statement'}
          </Typography>
          <Typography sx={{ color: '#64748B', fontSize: '1rem', maxWidth: 540, mx: 'auto' }}>
            {hasHistory
              ? 'Restore a previous AIS session instantly, or import a new PDF to compute taxes for a fresh financial year.'
              : 'Upload your AIS PDF from the Income Tax Portal to unlock your complete tax computation dashboard.'}
          </Typography>
        </Box>
      </motion.div>

      {/* Session-expired alert */}
      <AnimatePresence>
        {sessionExpired && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
            <Alert severity="warning" sx={{ mb: 4, borderRadius: '16px', fontWeight: 600, maxWidth: hasHistory ? 1000 : 520, mx: 'auto' }}>
              ⚡ Your previous session was lost (server restarted). Please re-upload your AIS to continue.
            </Alert>
          </motion.div>
        )}
      </AnimatePresence>

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
                {hasHistory ? 'Import New AIS' : 'Upload AIS PDF'}
              </Typography>
            </Box>
            <Typography sx={{ color: '#64748B', fontSize: '0.85rem', mb: 1 }}>
              Download from{' '}
              <Typography component="span" sx={{ color: '#818CF8', fontWeight: 700 }}>incometax.gov.in</Typography>
              {' '}→ AIS → Download PDF, then upload here.
            </Typography>

            <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 3 }}>
              {['1. Login to incometax.gov.in', '2. AIS → Download', '3. Upload here'].map((step, i) => (
                <Chip key={step} label={step} size="small" sx={{ fontSize: '0.65rem', fontWeight: 700, bgcolor: i === 2 ? 'rgba(99,102,241,0.15)' : 'rgba(255,255,255,0.05)', color: i === 2 ? '#818CF8' : '#94A3B8' }} />
              ))}
            </Box>

            {error && <Alert severity="error" sx={{ mb: 2.5, borderRadius: '14px' }}>{error}</Alert>}

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
                textAlign: 'center', cursor: 'pointer',
                background: isDragActive ? 'rgba(99,102,241,0.08)' : file ? 'rgba(78,222,147,0.04)' : 'rgba(255,255,255,0.01)',
                transition: 'all 0.25s ease', mb: 3,
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
                      <Box sx={{ width: 64, height: 64, mx: 'auto', mb: 2.5, borderRadius: '18px', background: 'linear-gradient(135deg, rgba(99,102,241,0.2) 0%, rgba(56,189,248,0.2) 100%)', border: '1px solid rgba(99,102,241,0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <UploadFileIcon sx={{ fontSize: 32, color: '#818CF8' }} />
                      </Box>
                    </motion.div>
                    <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1rem', mb: 0.75 }}>
                      {isDragActive ? 'Release to import' : 'Drag & drop your AIS PDF'}
                    </Typography>
                    <Typography sx={{ color: '#475569', fontSize: '0.85rem' }}>or click here to browse from your device</Typography>
                  </motion.div>
                )}
              </AnimatePresence>
            </Box>

            {file && (
              <Button
                fullWidth variant="contained" size="large"
                onClick={handleAnalyze} disabled={loading}
                sx={{
                  py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1.05rem',
                  background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)', color: '#fff',
                  boxShadow: '0 8px 28px rgba(99,102,241,0.45)', textTransform: 'none',
                  '&:hover': { background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)', boxShadow: '0 12px 36px rgba(99,102,241,0.6)' },
                  '&.Mui-disabled': { background: 'linear-gradient(135deg, rgba(99,102,241,0.7) 0%, rgba(79,70,229,0.7) 100%)', color: 'rgba(255,255,255,0.9)' }
                }}
              >
                {loading ? <><CircularProgress size={20} sx={{ color: '#fff', mr: 1.5 }} />Computing Taxes...</> : '🧮 Compute My Taxes'}
              </Button>
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
                  <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: '#F8FAFC' }}>Previous AIS Sessions</Typography>
                </Box>
                <Chip label={`${history.length} saved`} size="small" sx={{ background: 'rgba(255,255,255,0.05)', color: '#64748B', fontSize: '0.7rem', fontWeight: 700, borderRadius: '8px' }} />
              </Box>

              <Typography sx={{ color: '#475569', fontSize: '0.82rem', mb: 2.5 }}>
                Click any snapshot below to instantly restore that tax session by FY / AY.
              </Typography>

              <Box sx={{ flex: 1 }}>
                <HistoryList history={history} onSelect={(sid) => setSessionById(sid, 'tax_expert')} compact={false} />
              </Box>
            </Paper>
          </motion.div>
        )}
      </Box>
    </Box>
  )
}
