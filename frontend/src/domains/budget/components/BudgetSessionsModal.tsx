import { useState } from 'react'
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, Box,
  Typography, Stack, Chip, IconButton, Tooltip, CircularProgress, Divider
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import LayersIcon from '@mui/icons-material/Layers'
import CalendarTodayIcon from '@mui/icons-material/CalendarToday'

interface BudgetSessionsModalProps {
  open: boolean
  onClose: () => void
  sessions: any[]
  activeSessionId: string
  onSelectSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => Promise<void>
  loading?: boolean
}

const BANK_COLOR_MAP: Record<string, { bg: string, border: string, text: string }> = {
  HDFC: { bg: 'rgba(0, 75, 141, 0.15)', border: 'rgba(0, 75, 141, 0.4)', text: '#60a5fa' },
  ICICI: { bg: 'rgba(179, 39, 44, 0.15)', border: 'rgba(179, 39, 44, 0.4)', text: '#f87171' },
  SBI: { bg: 'rgba(40, 56, 144, 0.15)', border: 'rgba(40, 56, 144, 0.4)', text: '#38bdf8' },
  AXIS: { bg: 'rgba(151, 18, 74, 0.15)', border: 'rgba(151, 18, 74, 0.4)', text: '#f472b6' },
  KOTAK: { bg: 'rgba(237, 28, 36, 0.15)', border: 'rgba(237, 28, 36, 0.4)', text: '#fb7185' },
  GENERIC: { bg: 'rgba(100, 116, 139, 0.15)', border: 'rgba(100, 116, 139, 0.4)', text: '#94a3b8' },
}

export default function BudgetSessionsModal({
  open,
  onClose,
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  loading = false
}: BudgetSessionsModalProps) {
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleDelete = async (e: React.MouseEvent, sid: string) => {
    e.stopPropagation()
    if (window.confirm('Are you sure you want to delete this uploaded statement session?')) {
      setDeletingId(sid)
      await onDeleteSession(sid)
      setDeletingId(null)
    }
  }

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr)
      return new Intl.DateTimeFormat('en-IN', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      }).format(d)
    } catch {
      return dateStr
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          background: 'linear-gradient(180deg, #0f172a 0%, #020617 100%)',
          color: '#fff',
          borderRadius: 4,
          border: '1px solid rgba(255, 255, 255, 0.1)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.7)'
        }
      }}
    >
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <LayersIcon sx={{ color: '#818cf8', fontSize: 28 }} />
          <Box>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              Statement Sessions & Accounts History
            </Typography>
            <Typography variant="caption" sx={{ color: '#94a3b8' }}>
              Manage and toggle between uploaded bank accounts and credit cards
            </Typography>
          </Box>
        </Box>
        <IconButton onClick={onClose} sx={{ color: '#94a3b8', '&:hover': { color: '#fff' } }}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <Divider sx={{ borderColor: 'rgba(255, 255, 255, 0.08)' }} />

      <DialogContent sx={{ py: 3 }}>
        <Stack spacing={2}>
          {/* Master Consolidated Session Option */}
          <Box
            onClick={() => {
              onSelectSession('overall')
              onClose()
            }}
            sx={{
              p: 2.5,
              borderRadius: 3,
              cursor: 'pointer',
              background: activeSessionId === 'overall'
                ? 'linear-gradient(135deg, rgba(99, 102, 241, 0.2) 0%, rgba(79, 70, 229, 0.1) 100%)'
                : 'rgba(255, 255, 255, 0.02)',
              border: '1px solid',
              borderColor: activeSessionId === 'overall' ? '#818cf8' : 'rgba(255, 255, 255, 0.08)',
              transition: 'all 0.2s ease',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              '&:hover': {
                borderColor: '#818cf8',
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                transform: 'translateY(-1px)'
              }
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Box sx={{
                width: 44,
                height: 44,
                borderRadius: 2.5,
                background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)'
              }}>
                <LayersIcon sx={{ color: '#fff', fontSize: 24 }} />
              </Box>
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#fff' }}>
                    All Accounts Combined (Master View)
                  </Typography>
                  {activeSessionId === 'overall' && (
                    <Chip size="small" label="Active" color="primary" sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700 }} />
                  )}
                </Box>
                <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                  Aggregates all bank accounts and credit cards with cross-account deduplication
                </Typography>
              </Box>
            </Box>
            {activeSessionId === 'overall' && (
              <CheckCircleIcon sx={{ color: '#818cf8', fontSize: 24 }} />
            )}
          </Box>

          <Typography variant="overline" sx={{ color: '#64748b', fontWeight: 700, letterSpacing: 1, mt: 2 }}>
            Uploaded Account Sessions ({sessions.length})
          </Typography>

          {sessions.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 4, color: '#94a3b8' }}>
              <Typography variant="body2">No previous upload sessions recorded.</Typography>
            </Box>
          ) : (
            sessions.map((s) => {
              const isActive = activeSessionId === s.session_id
              const bankUpper = (s.bank || 'GENERIC').toUpperCase()
              const bankStyle = BANK_COLOR_MAP[bankUpper] || BANK_COLOR_MAP['GENERIC']
              const isDeleting = deletingId === s.session_id
              const accType = s.account_type || 'Savings Account'
              const isCard = accType.toLowerCase().includes('card')

              return (
                <Box
                  key={s.session_id}
                  onClick={() => {
                    onSelectSession(s.session_id)
                    onClose()
                  }}
                  sx={{
                    p: 2,
                    borderRadius: 3,
                    cursor: 'pointer',
                    background: isActive
                      ? bankStyle.bg
                      : 'rgba(255, 255, 255, 0.02)',
                    border: '1px solid',
                    borderColor: isActive ? bankStyle.text : 'rgba(255, 255, 255, 0.06)',
                    transition: 'all 0.2s ease',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    '&:hover': {
                      borderColor: bankStyle.text,
                      backgroundColor: bankStyle.bg,
                      transform: 'translateY(-1px)'
                    }
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, overflow: 'hidden' }}>
                    <Box sx={{
                      width: 40,
                      height: 40,
                      borderRadius: 2,
                      background: bankStyle.bg,
                      border: `1px solid ${bankStyle.border}`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0
                    }}>
                      {isCard ? (
                        <CreditCardIcon sx={{ color: bankStyle.text, fontSize: 20 }} />
                      ) : (
                        <AccountBalanceIcon sx={{ color: bankStyle.text, fontSize: 20 }} />
                      )}
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <Typography variant="body1" sx={{ fontWeight: 600, color: '#fff', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: 300 }}>
                          {s.filename || 'Bank Statement'}
                        </Typography>
                        <Chip
                          size="small"
                          label={bankUpper}
                          sx={{
                            height: 20,
                            fontSize: '0.65rem',
                            fontWeight: 700,
                            backgroundColor: bankStyle.bg,
                            color: bankStyle.text,
                            border: `1px solid ${bankStyle.border}`
                          }}
                        />
                        <Chip
                          size="small"
                          label={accType}
                          sx={{
                            height: 20,
                            fontSize: '0.65rem',
                            fontWeight: 600,
                            backgroundColor: 'rgba(255, 255, 255, 0.04)',
                            color: '#cbd5e1',
                            border: '1px solid rgba(255, 255, 255, 0.08)'
                          }}
                        />
                        {isActive && (
                          <Chip size="small" label="Active" color="primary" sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700 }} />
                        )}
                      </Box>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 0.5, color: '#94a3b8', fontSize: '0.75rem', flexWrap: 'wrap' }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <CalendarTodayIcon sx={{ fontSize: 12 }} />
                          <span>{formatDate(s.created_at)}</span>
                        </Box>
                        <span>•</span>
                        <span>{s.rows} txns</span>
                        <span>•</span>
                        <span style={{ color: '#34d399' }}>+₹{s.total_income.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                        <span>•</span>
                        <span style={{ color: '#f87171' }}>-₹{s.total_expense.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</span>
                      </Box>
                    </Box>
                  </Box>

                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 2, flexShrink: 0 }}>
                    {isActive && (
                      <CheckCircleIcon sx={{ color: bankStyle.text, fontSize: 22 }} />
                    )}
                    <Tooltip title="Delete this statement session">
                      <IconButton
                        size="small"
                        onClick={(e) => handleDelete(e, s.session_id)}
                        disabled={isDeleting}
                        sx={{
                          color: '#64748b',
                          '&:hover': { color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.1)' }
                        }}
                      >
                        {isDeleting ? <CircularProgress size={18} color="inherit" /> : <DeleteOutlineIcon fontSize="small" />}
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              )
            })
          )}
        </Stack>
      </DialogContent>

      <DialogActions sx={{ px: 3, py: 2, borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
        <Button onClick={onClose} sx={{ color: '#94a3b8', textTransform: 'none', fontWeight: 600 }}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  )
}
