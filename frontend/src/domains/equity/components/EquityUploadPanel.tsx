import { useState, useCallback, useEffect, useRef } from 'react'
import { useDropzone, type FileRejection } from 'react-dropzone'
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
import { useQueryClient } from '@tanstack/react-query'
import { apiClient }       from '../../../shared/api/client'
import { useAppStore }     from '../../../shared/store/appStore'
import { SwitchSessionButton } from '../../../shared/components/dashboard/SwitchSessionButton'
import { UploadHistoryList } from '../../../shared/components/dashboard/UploadHistoryList'
import { invalidateEquityQueries } from '../../../shared/hooks/invalidateSessionQueries'
import { KITE_STATE_KEY } from '../hooks/useKiteOAuthCallback'

/** Mirrors MAX_UPLOAD_BYTES in backend/domains/equity/parser.py. */
const MAX_UPLOAD_MB = 8
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

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




export function SwitchEquityStatementButton({ sessionId }: { sessionId: string | null }) {
  const setSessionById = useAppStore((s) => s.setSessionById)
  const queryClient = useQueryClient()

  const fetchHistory = useCallback(async () => {
    const res = await apiClient.getEquityHistory()
    return res?.history ?? []
  }, [])

  const handleDelete = useCallback(async (sid: string) => {
    try {
      await apiClient.deleteHistorySession(sid)
      if (sessionId === sid) setSessionById('', 'equity')
      await invalidateEquityQueries(queryClient)
    } catch (e) {
      console.error(e)
    }
  }, [sessionId, setSessionById, queryClient])

  return (
    <SwitchSessionButton
      sessionId={sessionId}
      fetchHistory={fetchHistory}
      onSelect={async (sid) => {
        setSessionById(sid, 'equity')
        await invalidateEquityQueries(queryClient)
      }}
      onDelete={handleDelete}
      accent="emerald"
      buttonLabel="Switch Portfolio"
      tooltip="Switch portfolio or connect new account"
      popoverTitle="Equity Portfolios"
      itemLabel="Stocks"
      emptyText="No previous sessions found"
      renderBadges={(h) =>
        h.statement_period?.includes('kite') ? (
          <Chip
            label="Zerodha Kite"
            size="small"
            sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, background: 'rgba(235,91,60,0.2)', color: '#FF5722', borderRadius: '6px' }}
          />
        ) : null
      }
      renderFooter={(close) => (
        <Button
          fullWidth variant="contained"
          onClick={async () => {
            setSessionById('', 'equity')
            await invalidateEquityQueries(queryClient)
            close()
          }}
          sx={{
            py: 1, borderRadius: '12px', fontWeight: 700, fontSize: '0.85rem',
            background: 'linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0.05) 100%)',
            color: '#fff', textTransform: 'none',
            '&:hover': { background: 'rgba(255,255,255,0.15)' },
          }}
        >
          Connect New Portfolio
        </Button>
      )}
    />
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
  const queryClient = useQueryClient()

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
      await invalidateEquityQueries(queryClient)
    } catch (e) {
      console.error(e)
    }
  }

  // Tracked so pending timers can be cancelled on unmount.
  const timersRef = useRef<number[]>([])

  const later = useCallback((fn: () => void, ms: number) => {
    const id = window.setTimeout(fn, ms)
    timersRef.current.push(id)
  }, [])

  useEffect(() => () => {
    timersRef.current.forEach(window.clearTimeout)
    timersRef.current = []
  }, [])

  // Kite OAuth return is handled by IndianStocksDashboard (useKiteOAuthCallback)
  // so it still works on Analyzer / with an existing session.

  const onDropHoldings = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const onDropTradebook = useCallback((accepted: File[]) => {
    if (accepted[0]) { setTradebookFile(accepted[0]); setError(null) }
  }, [])

  const onRejected = useCallback((rejections: FileRejection[]) => {
    const reason = rejections[0]?.errors?.[0]?.code
    setError(
      reason === 'file-too-large'
        ? `That file is larger than ${MAX_UPLOAD_MB} MB. Export just your holdings or tradebook.`
        : 'Unsupported file. Upload a .csv or .xlsx export from your broker.',
    )
  }, [])

  const dropzoneOptions = {
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    },
    maxFiles: 1,
    // Rejected in the browser instead of uploading and being refused. The backend caps
    // this too (that is the real guard), but without maxSize the user waited out a
    // pointless upload of a file that could never be accepted.
    maxSize: MAX_UPLOAD_BYTES,
  } as const

  const holdingsDropzone = useDropzone({ ...dropzoneOptions, onDrop: onDropHoldings, onDropRejected: onRejected })
  const tradebookDropzone = useDropzone({ ...dropzoneOptions, onDrop: onDropTradebook, onDropRejected: onRejected })

  const handleAnalyzeCSV = async () => {
    if (!file) return setError('Please select a Holdings CSV.')
    setSyncState('syncing'); setError(null)
    try {
      const data = await apiClient.parseEquityCsv(file, tradebookFile || undefined)
      setSyncState('success')
      later(async () => {
        setSession(data.session_id, 'equity', data)
        await invalidateEquityQueries(queryClient)
        // Release the File handles; they were held until the panel happened to unmount.
        setFile(null)
        setTradebookFile(null)
      }, 1200)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse the file. Please check the format.')
      setSyncState('idle')
    }
  }

  const handleKiteLogin = async () => {
      setSyncState('syncing'); setError(null)
      try {
          const res = await apiClient.getKiteLoginUrl()
          if (res.login_url) {
              // Stashed so the return leg can still be verified if Zerodha does not echo
              // the state parameter back.
              if (res.state) sessionStorage.setItem(KITE_STATE_KEY, res.state)
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
            Directly connect your Zerodha account for live sync, or upload your holdings CSV or XLSX from any major broker (Zerodha, Groww).
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
                        <Tab label="CSV / XLSX Upload" />
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
                                <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mb: 2, fontWeight: 600 }}>1. Current Holdings (CSV or XLSX)</Typography>
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
                                                <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.9rem' }}>Upload Holdings File</Typography>
                                                <Typography sx={{ color: '#64748B', fontSize: '0.75rem', mt: 0.5 }}>CSV or XLSX (Zerodha/Groww format)</Typography>
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

                                <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mb: 2, mt: 1, fontWeight: 600 }}>2. Tradebook (Optional, for Realized P&L)</Typography>
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
                                                <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.9rem' }}>Upload Tradebook File</Typography>
                                                <Typography sx={{ color: '#64748B', fontSize: '0.75rem', mt: 0.5 }}>CSV or XLSX (Zerodha format)</Typography>
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
                                    onClick={handleAnalyzeCSV}
                                    disabled={!file}
                                    sx={{
                                        mt: 'auto', py: 1.8, borderRadius: '16px', fontWeight: 800, fontSize: '1.05rem',
                                        background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                                        color: '#fff', textTransform: 'none',
                                        '&:hover': { background: 'linear-gradient(135deg, #059669 0%, #047857 100%)', boxShadow: '0 12px 36px rgba(16,185,129,0.3)' },
                                        '&:disabled': { background: 'rgba(255,255,255,0.05)', color: '#475569' }
                                    }}
                                >
                                    Analyze Portfolio
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
                        <UploadHistoryList
                          history={history}
                          onSelect={async (sid) => {
                            setSessionById(sid, 'equity')
                            await invalidateEquityQueries(queryClient)
                          }}
                          onDelete={handleDeleteSession}
                          accent="emerald"
                          itemLabel="Stocks"
                          emptyText="No previous sessions found"
                          renderBadges={(h) =>
                            h.statement_period?.includes('kite') ? (
                              <Chip
                                label="Zerodha Kite"
                                size="small"
                                sx={{ height: 18, fontSize: '0.65rem', fontWeight: 800, background: 'rgba(235,91,60,0.2)', color: '#FF5722', borderRadius: '6px' }}
                              />
                            ) : null
                          }
                          compact={false}
                        />
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
