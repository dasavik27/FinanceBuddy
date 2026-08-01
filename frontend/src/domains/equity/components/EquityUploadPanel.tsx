import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Box, Typography, Button, Alert, CircularProgress,
  Paper, Chip, Stack, Popover, IconButton, Tooltip, Tab, Tabs
} from '@mui/material'
import UploadFileIcon      from '@mui/icons-material/UploadFile'
import CheckCircleIcon     from '@mui/icons-material/CheckCircle'
import ShieldIcon          from '@mui/icons-material/Shield'
import HistoryIcon         from '@mui/icons-material/History'
import ChevronRightIcon    from '@mui/icons-material/ChevronRight'
import CloudUploadIcon     from '@mui/icons-material/CloudUpload'
import ShowChartIcon       from '@mui/icons-material/ShowChart'
import SwapHorizIcon       from '@mui/icons-material/SwapHoriz'
import CloseIcon           from '@mui/icons-material/Close'
import DeleteOutlineIcon   from '@mui/icons-material/DeleteOutline'
import { apiClient }       from '../../../shared/api/client'
import { useAppStore }     from '../../../shared/store/appStore'

function SyncOverlay({ state }: { state: 'syncing' | 'success' }) {
  const [msgIndex, setMsgIndex] = useState(0)
  const msgs = ['Authenticating...', 'Fetching live holdings...', 'Analyzing portfolio...', 'Almost there...']
  
  useEffect(() => {
    if (state !== 'syncing') return
    const interval = setInterval(() => {
      setMsgIndex((i) => Math.min(i + 1, msgs.length - 1))
    }, 1200)
    return () => clearInterval(interval)
  }, [state])

  return (
    <Box sx={{
      py: 12, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
    }}>
      <AnimatePresence mode="wait">
        {state === 'syncing' ? (
          <motion.div key="sync" initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.1 }} style={{ textAlign: 'center' }}>
            <CircularProgress size={56} thickness={4} sx={{ color: '#10B981', mb: 4 }} />
            <AnimatePresence mode="wait">
              <motion.div key={msgIndex} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }} transition={{ duration: 0.2 }}>
                <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.4rem' }}>{msgs[msgIndex]}</Typography>
              </motion.div>
            </AnimatePresence>
            <Typography sx={{ color: '#64748B', mt: 1.5, fontSize: '0.95rem' }}>Securely processing your data...</Typography>
          </motion.div>
        ) : (
          <motion.div key="success" initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: 'spring', bounce: 0.5 }}>
            <Box sx={{ width: 96, height: 96, borderRadius: '48px', background: 'rgba(16,185,129,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', mx: 'auto', mb: 3, border: '2px solid rgba(16,185,129,0.5)', boxShadow: '0 0 40px rgba(16,185,129,0.4)' }}>
              <CheckCircleIcon sx={{ fontSize: 48, color: '#10B981' }} />
            </Box>
            <Typography sx={{ color: '#10B981', fontWeight: 800, fontSize: '1.8rem', textAlign: 'center', letterSpacing: '-0.02em' }}>Success!</Typography>
          </motion.div>
        )}
      </AnimatePresence>
    </Box>
  )
}


function fmtDate(iso: string) {
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso))
}

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 0,
  }).format(v)
}

function HistoryList({ history, onSelect, activeSessionId, compact, onDelete }: any) {
  if (!history || history.length === 0) return (
    <Box sx={{ textAlign: 'center', py: compact ? 2 : 4 }}>
      <Typography sx={{ color: '#475569', fontSize: '0.85rem' }}>No previous sessions found</Typography>
    </Box>
  )

  return (
    <Stack spacing={compact ? 1 : 1.5}>
      {history.slice(0, 5).map((h: any, i: number) => {
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
                  ? 'linear-gradient(135deg, rgba(16,185,129,0.15) 0%, rgba(5,150,105,0.08) 100%)'
                  : 'linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
                border: `1px solid ${isActive ? 'rgba(16,185,129,0.5)' : 'rgba(255,255,255,0.07)'}`,
                borderRadius: '16px',
                cursor: isActive ? 'default' : 'pointer',
                transition: 'all 0.25s ease',
                '&:hover': isActive ? {} : {
                  background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(5,150,105,0.05) 100%)',
                  borderColor: 'rgba(16,185,129,0.35)',
                  transform: 'translateY(-1px)',
                  '& .chevron': { color: '#10B981', transform: 'translateX(3px)' },
                  '& .delete-btn': { opacity: 1 },
                },
              }}
            >
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Typography sx={{ color: '#CBD5E1', fontWeight: 700, fontSize: compact ? '0.78rem' : '0.88rem' }}>
                    {fmtDate(h.created_at)}
                  </Typography>
                  {isActive && (
                    <Chip label="Active" size="small" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, background: 'rgba(16,185,129,0.25)', color: '#34D399', borderRadius: '6px' }} />
                  )}
                  {h.statement_period && h.statement_period.includes('kite') && (
                    <Chip label="Zerodha Kite" size="small" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, background: 'rgba(235,91,60,0.2)', color: '#FF5722', borderRadius: '6px' }} />
                  )}
                </Box>
                <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mt: 1 }}>
                  <Chip label={`${h.num_funds || 0} Stocks`} size="small" sx={{ height: 20, fontSize: '0.7rem', fontWeight: 700, background: 'rgba(255,255,255,0.08)', color: '#E2E8F0', borderRadius: '6px' }} />
                  <Chip label={fmtINR(h.total_value || 0)} size="small" sx={{ height: 20, fontSize: '0.7rem', fontWeight: 800, background: 'rgba(78,222,147,0.1)', color: '#4EDE93', borderRadius: '6px' }} />
                </Box>
              </Box>
              
              {onDelete && (
                <IconButton 
                    size="small" 
                    className="delete-btn"
                    onClick={(e) => { e.stopPropagation(); onDelete(h.session_id); }}
                    sx={{ 
                        opacity: { xs: 1, md: 0 }, 
                        transition: 'opacity 0.2s', 
                        color: '#64748B', 
                        '&:hover': { color: '#EF4444', background: 'rgba(239,68,68,0.1)' },
                        mr: 1
                    }}
                >
                    <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              )}

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

export function SwitchEquityStatementButton({ sessionId }: { sessionId: string | null }) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)
  const [history, setHistory]   = useState<any[]>([])
  const setSessionById = useAppStore((s) => s.setSessionById)
  const open = Boolean(anchorEl)

  const fetchHistory = useCallback(() => {
    apiClient.getEquityHistory()
      .then((res) => { if (res?.history) setHistory(res.history) })
      .catch(console.error)
  }, [])

  useEffect(() => {
    if (open) fetchHistory()
  }, [open, fetchHistory])

  const handleSelect = (sid: string) => {
    setSessionById(sid, 'equity')
    setAnchorEl(null)
  }

  return (
    <>
      <Tooltip title="Switch portfolio or connect new account" placement="bottom">
        <Button
          variant="outlined"
          size="small"
          startIcon={<SwapHorizIcon sx={{ fontSize: 16 }} />}
          onClick={(e) => setAnchorEl(e.currentTarget)}
          sx={{
            borderColor: 'rgba(16,185,129,0.35)',
            color: '#94A3B8',
            textTransform: 'none',
            fontWeight: 700,
            fontSize: '0.82rem',
            borderRadius: '10px',
            px: 1.5,
            '&:hover': { borderColor: '#10B981', color: '#34D399', background: 'rgba(16,185,129,0.08)' },
          }}
        >
          Switch Portfolio
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
            mt: 1, width: 360, borderRadius: '20px',
            background: 'rgba(15,23,42,0.97)',
            border: '1px solid rgba(16,185,129,0.2)',
            boxShadow: '0 24px 60px rgba(0,0,0,0.6), 0 0 40px rgba(16,185,129,0.1)',
            backdropFilter: 'blur(20px)',
            overflow: 'hidden',
          }
        }}
      >
        <Box sx={{ px: 2.5, pt: 2.5, pb: 1.5, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <HistoryIcon sx={{ color: '#10B981', fontSize: 18 }} />
            <Typography sx={{ fontWeight: 800, fontSize: '0.9rem', color: '#F8FAFC' }}>Equity Portfolios</Typography>
          </Box>
          <IconButton size="small" onClick={() => setAnchorEl(null)} sx={{ color: '#475569', '&:hover': { color: '#94A3B8' } }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Box sx={{ px: 2.5, pb: 1.5 }}>
          <HistoryList 
            history={history} 
            onSelect={handleSelect} 
            activeSessionId={sessionId} 
            compact 
            onDelete={async (sid: string) => {
              try {
                await apiClient.deleteHistorySession(sid)
                setHistory(h => h.filter(x => x.session_id !== sid))
                if (sessionId === sid) setSessionById('', 'equity')
              } catch (e) {
                console.error(e)
              }
            }}
          />
        </Box>

        <Divider sx={{ borderColor: 'rgba(255,255,255,0.06)', mx: 2.5 }} />

        <Box sx={{ px: 2.5, pt: 2, pb: 2.5, textAlign: 'center' }}>
          <Button
            fullWidth variant="contained"
            onClick={() => { setSessionById('', 'equity'); setAnchorEl(null); }}
            sx={{
              py: 1, borderRadius: '12px', fontWeight: 700, fontSize: '0.85rem',
              background: 'linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%)',
              color: '#fff', textTransform: 'none',
              '&:hover': { background: 'rgba(255,255,255,0.15)' }
            }}
          >
            Connect New Portfolio
          </Button>
        </Box>
      </Popover>
    </>
  )
}

function Divider(props: any) {
    return <Box component="hr" {...props} />
}

export default function EquityUploadPanel() {
  const [tabIndex, setTabIndex] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [tradebookFile, setTradebookFile] = useState<File | null>(null)
  const [syncState, setSyncState] = useState<'idle' | 'syncing' | 'success'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])
  
  const setSession = useAppStore((s) => s.setSession)
  const setSessionById = useAppStore((s) => s.setSessionById)
  const userId = useAppStore((s) => s.userId)

  const fetchHistory = useCallback(() => {
    if (!userId) return
    apiClient.getEquityHistory()
      .then((res) => { if (res?.history) setHistory(res.history) })
      .catch(console.error)
  }, [userId])

  useEffect(() => { fetchHistory() }, [fetchHistory])

  const handleDeleteSession = async (sid: string) => {
    try {
      await apiClient.deleteHistorySession(sid)
      setHistory(h => h.filter(x => x.session_id !== sid))
      if (useAppStore.getState().equitySessionId === sid) {
        setSessionById('', 'equity')
      }
    } catch (e) {
      console.error(e)
    }
  }

  const kiteAttemptRef = useRef<string | null>(null)

  // Handle Kite OAuth Callback
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search)
    const requestToken = urlParams.get('request_token')
    const action = urlParams.get('action')
    
    if (requestToken && action === 'login' && kiteAttemptRef.current !== requestToken) {
      kiteAttemptRef.current = requestToken
      setSyncState('syncing')
      apiClient.connectKite(requestToken)
        .then(data => {
            setSyncState('success')
            setTimeout(() => {
                setSession(data.session_id, 'equity', data)
                window.history.replaceState({}, document.title, window.location.pathname)
            }, 1200)
        })
        .catch(err => {
            setError(err?.response?.data?.detail || 'Kite connect failed')
            setSyncState('idle')
        })
    }
  }, [setSession])


  const onDropHoldings = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const onDropTradebook = useCallback((accepted: File[]) => {
    if (accepted[0]) { setTradebookFile(accepted[0]); setError(null) }
  }, [])

  const holdingsDropzone = useDropzone({ onDrop: onDropHoldings, accept: { 'text/csv': ['.csv'] }, maxFiles: 1 })
  const tradebookDropzone = useDropzone({ onDrop: onDropTradebook, accept: { 'text/csv': ['.csv'] }, maxFiles: 1 })

  const handleAnalyzeCSV = async () => {
    if (!file) return setError('Please select a Holdings CSV.')
    setSyncState('syncing'); setError(null)
    try {
      const data = await apiClient.parseEquityCsv(file, tradebookFile || undefined)
      setSyncState('success')
      setTimeout(() => setSession(data.session_id, 'equity', data), 1200)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse CSV. Please check the file format.')
      setSyncState('idle')
    }
  }

  const handleKiteLogin = async () => {
      setSyncState('syncing'); setError(null)
      try {
          const res = await apiClient.getKiteLoginUrl()
          if (res.login_url) {
              window.location.href = res.login_url
          }
      } catch (e: any) {
          setError(e?.response?.data?.detail ?? 'Could not initiate Kite connection. Is the API Key configured on backend?')
          setSyncState('idle')
      }
  }

  const hasHistory = history && history.length > 0

  return (
    <Box sx={{ py: { xs: 4, md: 8 }, px: { xs: 2, md: 0 } }}>
      <motion.div initial={{ opacity: 0, y: -12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1.5, background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)', borderRadius: '40px', px: 2.5, py: 1, mb: 3 }}>
            <ShowChartIcon sx={{ color: '#10B981', fontSize: 18 }} />
            <Typography sx={{ color: '#10B981', fontWeight: 700, fontSize: '0.82rem', letterSpacing: '0.06em' }}>EQUITY DASHBOARD</Typography>
          </Box>
          <Typography variant="h4" sx={{ fontWeight: 900, color: '#F8FAFC', mb: 1.5, letterSpacing: '-0.02em' }}>
            {hasHistory ? 'Connect or Restore Portfolio' : 'Connect Your Broker'}
          </Typography>
          <Typography sx={{ color: '#64748B', fontSize: '1rem', maxWidth: 520, mx: 'auto' }}>
            Directly connect your Zerodha account for live sync, or upload your holdings CSV from any major broker (Zerodha, Groww).
          </Typography>
        </Box>
      </motion.div>

      <AnimatePresence mode="wait">
        {syncState !== 'idle' ? (
            <motion.div key="syncing" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
                <SyncOverlay state={syncState} />
            </motion.div>
        ) : (
            <motion.div key="upload" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }}>
              <Box sx={{
                display: 'grid',
                gridTemplateColumns: { xs: '1fr', lg: hasHistory ? '1fr 1fr' : '1fr' },
                gap: 4,
                maxWidth: hasHistory ? 1000 : 520,
                mx: 'auto',
              }}>
                {/* Upload Card */}
                <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1, duration: 0.45 }}>
                  <Paper className="glass" sx={{
                    borderRadius: '28px',
                    border: '1px solid rgba(16,185,129,0.25)',
                    background: 'rgba(15,23,42,0.8)',
                    boxShadow: '0 25px 60px rgba(0,0,0,0.6), 0 0 40px rgba(16,185,129,0.1)',
                    height: '100%', display: 'flex', flexDirection: 'column',
                    overflow: 'hidden'
                  }}>
                    <Tabs 
                        value={tabIndex} 
                        onChange={(_, v) => setTabIndex(v)} 
                        variant="fullWidth"
                        sx={{ 
                            borderBottom: '1px solid rgba(255,255,255,0.1)',
                            '& .MuiTab-root': { py: 2.5, fontWeight: 700, color: '#94A3B8', textTransform: 'none', fontSize: '0.95rem' },
                            '& .Mui-selected': { color: '#10B981 !important' },
                            '& .MuiTabs-indicator': { backgroundColor: '#10B981', height: 3 }
                        }}
                    >
                        <Tab label="Connect Zerodha API" />
                        <Tab label="CSV Upload" />
                    </Tabs>

                    <Box sx={{ p: { xs: 3, md: 5 }, flex: 1, display: 'flex', flexDirection: 'column' }}>
                        {error && (
                            <Alert severity="error" sx={{ mb: 3, borderRadius: '14px' }}>{error}</Alert>
                        )}

                        {tabIndex === 0 ? (
                            // Kite OAuth View
                            <Box sx={{ textAlign: 'center', py: 4, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                                <Box sx={{ width: 80, height: 80, mx: 'auto', mb: 3, borderRadius: '24px', background: 'rgba(235,91,60,0.1)', border: '1px solid rgba(235,91,60,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    <img src="https://kite.zerodha.com/static/images/kite-logo.svg" alt="Kite" width="40" style={{ filter: 'grayscale(0) brightness(1.2)' }} />
                                </Box>
                                <Typography sx={{ fontWeight: 800, fontSize: '1.2rem', color: '#F8FAFC', mb: 1.5 }}>Zerodha Kite Connect</Typography>
                                <Typography sx={{ color: '#94A3B8', fontSize: '0.9rem', mb: 4, px: 2 }}>
                                    Securely link your Zerodha account to automatically sync your holdings, positions, and live P&L.
                                </Typography>
                                <Button
                                    variant="contained" size="large"
                                    onClick={handleKiteLogin}
                                    sx={{
                                        py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1.05rem',
                                        background: 'linear-gradient(135deg, #FF5722 0%, #E64A19 100%)',
                                        color: '#fff',
                                        boxShadow: '0 8px 28px rgba(235,91,60,0.4)', textTransform: 'none',
                                        '&:hover': { background: 'linear-gradient(135deg, #E64A19 0%, #D84315 100%)', boxShadow: '0 12px 36px rgba(235,91,60,0.5)' },
                                    }}
                                >
                                    Login with Kite
                                </Button>
                            </Box>
                        ) : (
                            // CSV Upload View
                            <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                                <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mb: 2, fontWeight: 600 }}>1. Current Holdings CSV (Required)</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
                                    <Box
                                        {...holdingsDropzone.getRootProps()}
                                        component={motion.div as any}
                                        whileHover={{ scale: 1.01 }}
                                        whileTap={{ scale: 0.98 }}
                                        sx={{
                                            flex: 1,
                                            border: `2px dashed ${holdingsDropzone.isDragActive ? '#10B981' : file ? '#4EDE93' : 'rgba(255,255,255,0.1)'}`,
                                            borderRadius: '20px', p: 3, textAlign: 'center', cursor: 'pointer',
                                            background: holdingsDropzone.isDragActive ? 'rgba(16,185,129,0.08)' : file ? 'rgba(78,222,147,0.04)' : 'rgba(255,255,255,0.01)',
                                            transition: 'all 0.25s ease',
                                            '&:hover': { borderColor: file ? '#4EDE93' : '#10B981', background: file ? 'rgba(78,222,147,0.06)' : 'rgba(16,185,129,0.05)' },
                                        }}
                                    >
                                        <input {...holdingsDropzone.getInputProps()} />
                                        {file ? (
                                            <Box>
                                                <CheckCircleIcon sx={{ fontSize: 28, color: '#4EDE93', mb: 1 }} />
                                                <Typography sx={{ color: '#4EDE93', fontWeight: 800, fontSize: '0.9rem', mb: 0.5, wordBreak: 'break-word' }}>{file.name}</Typography>
                                            </Box>
                                        ) : (
                                            <Box>
                                                <CloudUploadIcon sx={{ fontSize: 28, color: '#10B981', mb: 1 }} />
                                                <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.9rem' }}>Upload Holdings CSV</Typography>
                                                <Typography sx={{ color: '#64748B', fontSize: '0.75rem', mt: 0.5 }}>Zerodha or Groww format</Typography>
                                            </Box>
                                        )}
                                    </Box>
                                    {file && (
                                        <Tooltip title="Remove file">
                                            <IconButton onClick={(e) => { e.stopPropagation(); setFile(null); }} sx={{ color: '#FF516A', bgcolor: 'rgba(255,81,106,0.1)', '&:hover': { bgcolor: 'rgba(255,81,106,0.2)' } }}>
                                                <CloseIcon />
                                            </IconButton>
                                        </Tooltip>
                                    )}
                                </Box>

                                <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mb: 2, mt: 1, fontWeight: 600 }}>2. Tradebook CSV (Optional, for Realized P&L)</Typography>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
                                    <Box
                                        {...tradebookDropzone.getRootProps()}
                                        component={motion.div as any}
                                        whileHover={{ scale: 1.01 }}
                                        whileTap={{ scale: 0.98 }}
                                        sx={{
                                            flex: 1,
                                            border: `2px dashed ${tradebookDropzone.isDragActive ? '#10B981' : tradebookFile ? '#4EDE93' : 'rgba(255,255,255,0.1)'}`,
                                            borderRadius: '20px', p: 3, textAlign: 'center', cursor: 'pointer',
                                            background: tradebookDropzone.isDragActive ? 'rgba(16,185,129,0.08)' : tradebookFile ? 'rgba(78,222,147,0.04)' : 'rgba(255,255,255,0.01)',
                                            transition: 'all 0.25s ease',
                                            '&:hover': { borderColor: tradebookFile ? '#4EDE93' : '#10B981', background: tradebookFile ? 'rgba(78,222,147,0.06)' : 'rgba(16,185,129,0.05)' },
                                        }}
                                    >
                                        <input {...tradebookDropzone.getInputProps()} />
                                        {tradebookFile ? (
                                            <Box>
                                                <CheckCircleIcon sx={{ fontSize: 28, color: '#4EDE93', mb: 1 }} />
                                                <Typography sx={{ color: '#4EDE93', fontWeight: 800, fontSize: '0.9rem', mb: 0.5, wordBreak: 'break-word' }}>{tradebookFile.name}</Typography>
                                            </Box>
                                        ) : (
                                            <Box>
                                                <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.9rem' }}>Upload Tradebook CSV</Typography>
                                                <Typography sx={{ color: '#64748B', fontSize: '0.75rem', mt: 0.5 }}>For capital gains estimates</Typography>
                                            </Box>
                                        )}
                                    </Box>
                                    {tradebookFile && (
                                        <Tooltip title="Remove file">
                                            <IconButton onClick={(e) => { e.stopPropagation(); setTradebookFile(null); }} sx={{ color: '#FF516A', bgcolor: 'rgba(255,81,106,0.1)', '&:hover': { bgcolor: 'rgba(255,81,106,0.2)' } }}>
                                                <CloseIcon />
                                            </IconButton>
                                        </Tooltip>
                                    )}
                                </Box>

                                <Button
                                    fullWidth variant="contained" size="large"
                                    onClick={handleAnalyzeCSV} disabled={!file}
                                    sx={{
                                        py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1.05rem',
                                        background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                                        color: '#fff', mt: 'auto',
                                        boxShadow: '0 8px 28px rgba(16,185,129,0.4)', textTransform: 'none',
                                        '&:hover': { background: 'linear-gradient(135deg, #059669 0%, #047857 100%)', boxShadow: '0 12px 36px rgba(16,185,129,0.5)' },
                                        '&.Mui-disabled': { background: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.5)' }
                                    }}
                                >
                                    Analyse Portfolio
                                </Button>
                            </Box>
                        )}

                        <Typography variant="caption" sx={{ display: 'block', textAlign: 'center', color: '#334155', mt: 3 }}>
                            <ShieldIcon sx={{ fontSize: 11, verticalAlign: 'middle', mr: 0.5, color: '#10B981' }} />
                            Data processed securely on your backend only
                        </Typography>
                    </Box>
                  </Paper>
                </motion.div>

                {/* History Card */}
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
                          <HistoryIcon sx={{ color: '#10B981', fontSize: 20 }} />
                          <Typography sx={{ fontWeight: 800, fontSize: '1rem', color: '#F8FAFC' }}>Previous Portfolios</Typography>
                        </Box>
                        <Chip label={`${history.length} saved`} size="small" sx={{ background: 'rgba(255,255,255,0.05)', color: '#64748B', fontSize: '0.7rem', fontWeight: 700, borderRadius: '8px' }} />
                      </Box>

                      <Typography sx={{ color: '#475569', fontSize: '0.82rem', mb: 2.5 }}>
                        Click any snapshot below to instantly restore that portfolio view.
                      </Typography>

                      <Box sx={{ flex: 1, overflowY: 'auto', pr: 1, mr: -1 }}>
                        <HistoryList history={history} onSelect={(sid: string) => setSessionById(sid, 'equity')} compact={false} onDelete={handleDeleteSession} />
                      </Box>
                    </Paper>
                  </motion.div>
                )}
              </Box>
            </motion.div>
        )}
      </AnimatePresence>
    </Box>
  )
}
