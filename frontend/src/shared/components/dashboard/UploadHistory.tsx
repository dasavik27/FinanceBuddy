import { useState, useEffect, useMemo, useCallback } from 'react'
import { Box, Typography, Paper, Grid, Chip, Button, Stack, CircularProgress, Alert, Switch, FormControlLabel, IconButton, Tooltip, Collapse } from '@mui/material'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import api, { apiClient } from '../../api/client'
import { useSessionId, useAppStore } from '../../store/appStore'
import HistoryIcon from '@mui/icons-material/History'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import CallMadeIcon from '@mui/icons-material/CallMade'
import CallReceivedIcon from '@mui/icons-material/CallReceived'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import InsightsIcon from '@mui/icons-material/Insights'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import SpeedIcon from '@mui/icons-material/Speed'
import StarsIcon from '@mui/icons-material/Stars'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import AddIcon from '@mui/icons-material/Add'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'

const fmtInr = (v: number) => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v || 0)

const formatDate = (dateString: string) => {
  const d = new Date(dateString)
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }).format(d)
}

export default function UploadHistory() {
  const currentSessionId = useSessionId()
  const { setSessionById, setSession, activeModule } = useAppStore()
  const [history, setHistory] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [comparingWith, setComparingWith] = useState<string | null>(null)
  const [compareResult, setCompareResult] = useState<any | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [hideClosed, setHideClosed] = useState(true)

  // ── Upload state ──
  const [showUpload, setShowUpload] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [uploadLoading, setUploadLoading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadPassword, setUploadPassword] = useState('')

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setUploadFile(accepted[0]); setUploadError(null) }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop, accept: { 'application/pdf': ['.pdf'] }, maxFiles: 1,
  })

  const handleUpload = async () => {
    if (!uploadFile) return
    setUploadLoading(true); setUploadError(null)
    try {
      const data = await apiClient.parseFile(uploadFile, uploadPassword, 'mutual_funds')
      setSession(data.session_id, 'mutual_funds', data)
      // Refresh history list
      const hist = await apiClient.getHistory(activeModule)
      setHistory(hist.history || [])
      setShowUpload(false)
      setUploadFile(null)
    } catch (e: any) {
      setUploadError(e?.response?.data?.detail ?? 'Failed to parse. Please check the file.')
    } finally {
      setUploadLoading(false)
    }
  }

  useEffect(() => {
    fetchHistory()
  }, [])

  const fetchHistory = async () => {
    try {
      const data = await apiClient.getHistory(activeModule)
      setHistory(data.history || [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  const handleCompare = async (targetSessionId: string) => {
    if (!currentSessionId) return
    setComparingWith(targetSessionId)
    setCompareLoading(true)
    try {
      // Compare Target (Older) vs Current (Newer)
      const { data } = await api.get(`/history/compare/${targetSessionId}/vs/${currentSessionId}`)
      setCompareResult(data)
    } catch (e) {
      console.error("Comparison failed", e)
    } finally {
      setCompareLoading(false)
    }
  }

  const restoreSession = (sessionId: string) => {
    setSessionById(sessionId, activeModule)
  }

  const handleDeleteSession = async (sessionId: string) => {
    if (!window.confirm("Are you sure you want to delete this session? This action cannot be undone.")) return
    try {
      await api.delete(`/history/${sessionId}`)
      setHistory(prev => prev.filter(h => h.session_id !== sessionId))
      if (comparingWith === sessionId) {
        setComparingWith(null)
        setCompareResult(null)
      }
      if (currentSessionId === sessionId) {
        window.alert("You deleted your active session. You will be redirected to upload a new one.")
        setSessionById(null as any, activeModule) // Clear state
      }
    } catch (err) {
      console.error(err)
      window.alert("Failed to delete session.")
    }
  }

  const groupedTransactions = useMemo(() => {
    if (!compareResult?.new_transactions) return []
    const map = new Map<string, any>()
    
    compareResult.new_transactions.forEach((tx: any) => {
      // Ignore transactions for funds that are closed (no longer in active_funds)
      if (hideClosed && compareResult.active_funds && Array.isArray(compareResult.active_funds)) {
        const activeSet = new Set(compareResult.active_funds.map((f: string) => f.trim().toLowerCase()))
        if (activeSet.size > 0 && !activeSet.has((tx.fund || '').trim().toLowerCase())) return
      }

      const typeLower = (tx.type || '').toLowerCase()
      // Use units sign as primary indicator, fallback to type strings
      const isRedemption = (tx.units < 0) || typeLower.includes('redemption') || typeLower.includes('switch out')
      const isPurchase = (tx.units > 0) || typeLower.includes('purchase') || typeLower.includes('sip') || typeLower.includes('switch in') || typeLower.includes('reinvestment') || typeLower.includes('stamp')
      
      const key = tx.fund
      if (!map.has(key)) {
        map.set(key, {
          fund: tx.fund,
          bought_amount: 0,
          sold_amount: 0,
          bought_units: 0,
          sold_units: 0,
          bought_count: 0,
          sold_count: 0,
          net_amount: 0
        })
      }
      
      const entry = map.get(key)
      const absAmount = Math.abs(tx.amount || 0)
      const absUnits = Math.abs(tx.units || 0)

      if (isRedemption && !isPurchase) {
        entry.sold_amount += absAmount
        entry.sold_units += absUnits
        entry.sold_count += 1
        entry.net_amount -= absAmount
      } else if (isPurchase) {
        entry.bought_amount += absAmount
        entry.bought_units += absUnits
        entry.bought_count += 1
        entry.net_amount += absAmount
      }
      // If it's a dividend payout (units == 0, not a reinvestment), we simply ignore it from bought/sold totals.
    })
    
    // Sort so largest absolute net shifts are at the top
    return Array.from(map.values()).sort((a, b) => Math.abs(b.net_amount) - Math.abs(a.net_amount))
  }, [compareResult, hideClosed])

  if (loading) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>

  const totalBought = compareResult?.new_transactions?.filter((tx: any) => (tx.units > 0) || tx.type.toLowerCase().includes('purchase') || tx.type.toLowerCase().includes('sip') || tx.type.toLowerCase().includes('switch in') || tx.type.toLowerCase().includes('reinvestment') || tx.type.toLowerCase().includes('stamp')).reduce((a: number, b: any) => a + Math.abs(b.amount || 0), 0) || 0;
  const totalSold = compareResult?.new_transactions?.filter((tx: any) => (tx.units < 0) || tx.type.toLowerCase().includes('redemption') || tx.type.toLowerCase().includes('switch out')).reduce((a: number, b: any) => a + Math.abs(b.amount || 0), 0) || 0;
  const netCapitalFlow = totalBought - totalSold;
  const organicGrowth = compareResult?.deltas?.portfolio_value_change ? (compareResult.deltas.portfolio_value_change - netCapitalFlow) : 0;
  const xirrShift = compareResult?.deltas?.xirr_shift || 0;

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', pb: 4 }}>

      {/* ── Header + Import toggle ── */}
      <Box sx={{ mb: 4, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ width: 48, height: 48, borderRadius: '16px', bgcolor: 'rgba(99,102,241,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <HistoryIcon sx={{ color: '#6366F1', fontSize: 28 }} />
          </Box>
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Statement History</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Restore a previous snapshot, import a new CAS, or run ledger reconciliation.</Typography>
          </Box>
        </Box>
        <Button
          variant={showUpload ? 'contained' : 'outlined'}
          startIcon={showUpload ? <ExpandMoreIcon /> : <AddIcon />}
          onClick={() => { setShowUpload(v => !v); setUploadFile(null); setUploadError(null) }}
          sx={{
            borderRadius: '12px', fontWeight: 800, textTransform: 'none',
            ...(showUpload
              ? { background: 'linear-gradient(135deg,#6366F1,#4F46E5)', boxShadow: '0 6px 20px rgba(99,102,241,0.4)' }
              : { borderColor: 'rgba(99,102,241,0.4)', color: '#818CF8', '&:hover': { borderColor: '#6366F1', bgcolor: 'rgba(99,102,241,0.08)' } }),
          }}
        >
          {showUpload ? 'Hide Upload' : 'Import New CAS'}
        </Button>
      </Box>

      {/* ── Inline upload panel (collapsible) ── */}
      <Collapse in={showUpload}>
        <Paper className="glass" sx={{
          p: 3, mb: 4, borderRadius: '20px',
          border: '1px solid rgba(99,102,241,0.25)',
          background: 'rgba(15,23,42,0.7)',
        }}>
          <Typography sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.8rem', letterSpacing: '0.08em', textTransform: 'uppercase', mb: 2 }}>
            Import New Statement
          </Typography>

          {uploadError && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: '12px' }}>{uploadError}</Alert>
          )}

          <Box
            {...getRootProps()}
            component={motion.div as any}
            whileHover={{ scale: 1.005 }}
            whileTap={{ scale: 0.99 }}
            sx={{
              border: `2px dashed ${isDragActive ? '#6366F1' : uploadFile ? '#4EDE93' : 'rgba(255,255,255,0.1)'}`,
              borderRadius: '16px', p: 3, textAlign: 'center', cursor: 'pointer',
              background: isDragActive ? 'rgba(99,102,241,0.07)' : uploadFile ? 'rgba(78,222,147,0.04)' : 'transparent',
              transition: 'all 0.2s ease',
              '&:hover': { borderColor: uploadFile ? '#4EDE93' : '#6366F1' },
            }}
          >
            <input {...getInputProps()} />
            {uploadFile ? (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, justifyContent: 'center', minWidth: 0 }}>
                <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 24, flexShrink: 0 }} />
                <Box sx={{ textAlign: 'left', minWidth: 0, flex: 1 }}>
                  <Typography sx={{ color: '#4EDE93', fontWeight: 800, fontSize: '0.9rem', wordBreak: 'break-all' }}>{uploadFile.name}</Typography>
                  <Typography sx={{ color: '#64748B', fontSize: '0.75rem' }}>{(uploadFile.size / 1024).toFixed(0)} KB · Click to replace</Typography>
                </Box>
              </Box>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, justifyContent: 'center' }}>
                <CloudUploadIcon sx={{ color: '#6366F1', fontSize: 28 }} />
                <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.9rem' }}>
                  {isDragActive ? 'Release to import' : 'Drag & drop your CAS PDF, or click to browse'}
                </Typography>
              </Box>
            )}
          </Box>

          {uploadFile && (
            <Box>
              <Box sx={{ mt: 3, mb: 1 }}>
                <Typography sx={{ color: '#94A3B8', fontSize: '0.8rem', mb: 1, fontWeight: 600 }}>PDF Password (Optional)</Typography>
                <input 
                  type="password" 
                  value={uploadPassword}
                  onChange={(e) => setUploadPassword(e.target.value)}
                  placeholder="Defaults to your PAN if left blank"
                  style={{
                    width: '100%', padding: '12px 16px', borderRadius: '12px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                    color: '#fff', outline: 'none', fontSize: '0.9rem'
                  }}
                />
              </Box>
              <Button
                fullWidth variant="contained" onClick={handleUpload} disabled={uploadLoading}
              sx={{
                mt: 3, py: 1.3, borderRadius: '14px', fontWeight: 800, textTransform: 'none',
                background: 'linear-gradient(135deg,#6366F1,#4F46E5)',
                color: '#fff',
                boxShadow: '0 6px 20px rgba(99,102,241,0.4)',
                '&:hover': { background: 'linear-gradient(135deg,#4F46E5,#4338CA)' },
                '&.Mui-disabled': { background: 'linear-gradient(135deg, rgba(99,102,241,0.7) 0%, rgba(79,70,229,0.7) 100%)', color: 'rgba(255,255,255,0.9)' }
              }}
            >
              {uploadLoading ? <><CircularProgress size={16} sx={{ color: '#fff', mr: 1 }} />Analysing Portfolio...</> : 'Analyse & Switch to New Statement'}
              </Button>
            </Box>
          )}
        </Paper>
      </Collapse>

      {history.length === 0 && (
        <Alert severity="info" sx={{ borderRadius: 3, bgcolor: 'rgba(255,255,255,0.05)', color: '#fff', mb: 3 }}>
          No historical uploads found. Use "Import New CAS" above to start tracking.
        </Alert>
      )}


      <Grid container spacing={4}>
        {/* Timeline Column */}
        <Grid item xs={12} md={5}>
          <Stack spacing={3}>
            {history.map((h, i) => {
              const isActive = h.session_id === currentSessionId
              const isTarget = h.session_id === comparingWith
              return (
                <Paper key={i} className="glass" sx={{ 
                  p: 3, borderRadius: '24px', 
                  border: isActive ? '2px solid #6366F1' : isTarget ? '2px solid #4EDE93' : '1px solid rgba(255,255,255,0.1)',
                  position: 'relative', overflow: 'hidden'
                }}>
                  {isActive && <Box sx={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', bgcolor: '#6366F1' }} />}
                  
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                    <Box>
                      <Typography variant="subtitle2" sx={{ color: '#fff', fontWeight: 800 }}>
                        {formatDate(h.created_at + 'Z')}
                      </Typography>
                      {h.statement_period && (
                        <Typography variant="caption" sx={{ color: '#38BDF8', fontWeight: 700, mt: 0.5, display: 'block' }}>
                          Period: {h.statement_period}
                        </Typography>
                      )}
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {isActive && <Chip label="ACTIVE" size="small" sx={{ bgcolor: 'rgba(99,102,241,0.2)', color: '#6366F1', fontWeight: 900 }} />}
                      <IconButton onClick={() => handleDeleteSession(h.session_id)} size="small" sx={{ color: 'rgba(255,255,255,0.3)', '&:hover': { color: '#FF516A', bgcolor: 'rgba(255,81,106,0.1)' } }}>
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </Box>

                  <Box sx={{ display: 'flex', gap: 3, mb: 3 }}>
                    <Box>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>PORTFOLIO VALUE</Typography>
                      <Typography variant="h6" className="num" sx={{ color: '#4EDE93', fontWeight: 800 }}>{fmtInr(h.total_value)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>INVESTED</Typography>
                      <Typography variant="h6" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(h.total_invested)}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>FUNDS</Typography>
                      <Typography variant="h6" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{h.num_funds}</Typography>
                    </Box>
                  </Box>

                  <Box sx={{ display: 'flex', gap: 2 }}>
                    {!isActive && (
                      <Button variant="outlined" size="small" onClick={() => restoreSession(h.session_id)} sx={{ borderRadius: 2, flex: 1, borderColor: 'rgba(255,255,255,0.2)', color: '#fff' }}>
                        RESTORE
                      </Button>
                    )}
                    {!isActive && (
                      <Button variant="contained" size="small" onClick={() => handleCompare(h.session_id)} sx={{ borderRadius: 2, flex: 1, bgcolor: '#38BDF8', color: '#000', fontWeight: 800 }}>
                        COMPARE
                      </Button>
                    )}
                  </Box>
                </Paper>
              )
            })}
          </Stack>
        </Grid>

        {/* Comparison Column */}
        <Grid item xs={12} md={7}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.1)', minHeight: 600 }}>
            {!comparingWith ? (
              <Box sx={{ textAlign: 'center', mt: 15 }}>
                <CompareArrowsIcon sx={{ fontSize: 64, color: 'rgba(255,255,255,0.1)', mb: 3 }} />
                <Typography variant="h5" sx={{ color: 'text.secondary', fontWeight: 900 }}>Select a baseline session</Typography>
                <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.3)', mt: 1, maxWidth: 300, mx: 'auto' }}>
                  Finance Buddy will perform a cryptographic ledger reconciliation against your current portfolio.
                </Typography>
              </Box>
            ) : compareLoading ? (
              <Box sx={{ textAlign: 'center', mt: 15 }}>
                <CircularProgress size={60} sx={{ color: '#38BDF8', mb: 3 }} />
                <Typography variant="h6" sx={{ color: '#38BDF8', fontWeight: 800 }}>Reconciling Ledgers...</Typography>
              </Box>
            ) : compareResult && (
              <Box sx={{ animation: 'fadeIn 0.5s ease-out' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 4 }}>
                  <Box sx={{ width: 40, height: 40, borderRadius: '12px', bgcolor: 'rgba(56, 189, 248, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <InsightsIcon sx={{ color: '#38BDF8' }} />
                  </Box>
                  <Box>
                    <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff', lineHeight: 1 }}>Ledger Reconciliation</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                       {(() => {
                         const baseline = history.find(h => h.session_id === compareResult.baseline_session)
                         const current = history.find(h => h.session_id === compareResult.current_session)
                         if (baseline && current) {
                           return `From ${formatDate(baseline.created_at + 'Z')} to ${formatDate(current.created_at + 'Z')}`
                         }
                         return 'Cryptographic Delta Analysis'
                      })()}
                    </Typography>
                  </Box>
                </Box>

                <Grid container spacing={2} sx={{ mb: 4 }}>
                  <Grid item xs={12} sm={4}>
                    <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(78, 222, 147, 0.05)', border: '1px solid rgba(78, 222, 147, 0.2)' }}>
                      <Typography variant="caption" sx={{ color: '#4EDE93', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <CallReceivedIcon fontSize="small" /> TOTAL BOUGHT
                      </Typography>
                      <Typography variant="h5" className="num" sx={{ color: '#fff', fontWeight: 900, mt: 1 }}>
                        {fmtInr(totalBought)}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(255, 81, 106, 0.05)', border: '1px solid rgba(255, 81, 106, 0.2)' }}>
                      <Typography variant="caption" sx={{ color: '#FF516A', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <CallMadeIcon fontSize="small" /> TOTAL SOLD
                      </Typography>
                      <Typography variant="h5" className="num" sx={{ color: '#fff', fontWeight: 900, mt: 1 }}>
                        {fmtInr(totalSold)}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(56, 189, 248, 0.05)', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                      <Typography variant="caption" sx={{ color: '#38BDF8', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <AccountBalanceWalletIcon fontSize="small" /> NET CAPITAL FLOW
                      </Typography>
                      <Typography variant="h5" className="num" sx={{ color: '#fff', fontWeight: 900, mt: 1 }}>
                        {netCapitalFlow >= 0 ? '+' : ''}{fmtInr(netCapitalFlow)}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>

                <Grid container spacing={2} sx={{ mb: 4 }}>
                  <Grid item xs={12} sm={4}>
                    <Box sx={{ p: 2, borderRadius: '20px', bgcolor: organicGrowth < 0 ? 'rgba(239, 68, 68, 0.05)' : 'rgba(168, 85, 247, 0.05)', border: `1px solid ${organicGrowth < 0 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(168, 85, 247, 0.2)'}`, height: '100%' }}>
                      <Typography variant="caption" sx={{ color: organicGrowth < 0 ? '#EF4444' : '#A855F7', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
                        {organicGrowth < 0 ? <TrendingDownIcon fontSize="small" /> : <TrendingUpIcon fontSize="small" />} MARKET IMPACT
                        <Tooltip title="The pure organic growth of your portfolio, strictly isolating market movements from any new capital you deposited or withdrew." arrow placement="top">
                          <InfoOutlinedIcon sx={{ fontSize: 14, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', ml: 'auto' }} />
                        </Tooltip>
                      </Typography>
                      <Typography variant="h6" className="num" sx={{ color: '#fff', fontWeight: 900, mt: 1 }}>
                        {organicGrowth >= 0 ? '+' : ''}{fmtInr(organicGrowth)}
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Pure organic growth</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Box sx={{ p: 2, borderRadius: '20px', bgcolor: xirrShift < 0 ? 'rgba(239, 68, 68, 0.05)' : 'rgba(234, 179, 8, 0.05)', border: `1px solid ${xirrShift < 0 ? 'rgba(239, 68, 68, 0.2)' : 'rgba(234, 179, 8, 0.2)'}`, height: '100%' }}>
                      <Typography variant="caption" sx={{ color: xirrShift < 0 ? '#EF4444' : '#EAB308', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
                        {xirrShift < 0 ? <TrendingDownIcon fontSize="small" /> : <SpeedIcon fontSize="small" />} XIRR SHIFT
                        <Tooltip title="The change in your annualized return velocity between these two ledger snapshots." arrow placement="top">
                          <InfoOutlinedIcon sx={{ fontSize: 14, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', ml: 'auto' }} />
                        </Tooltip>
                      </Typography>
                      <Typography variant="h6" className="num" sx={{ color: '#fff', fontWeight: 900, mt: 1 }}>
                        {xirrShift >= 0 ? '+' : ''}{xirrShift.toFixed(2)}%
                      </Typography>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Return velocity delta</Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <Box sx={{ p: 2, borderRadius: '20px', bgcolor: 'rgba(236, 72, 153, 0.05)', border: '1px solid rgba(236, 72, 153, 0.2)', height: '100%' }}>
                      <Typography variant="caption" sx={{ color: '#EC4899', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <StarsIcon fontSize="small" /> TOP GAINER
                        <Tooltip title="The specific mutual fund that generated the highest positive organic valuation leap, independent of your new SIPs into it." arrow placement="top">
                          <InfoOutlinedIcon sx={{ fontSize: 14, color: 'rgba(255,255,255,0.4)', cursor: 'pointer', ml: 'auto' }} />
                        </Tooltip>
                      </Typography>
                      <Typography variant="h6" sx={{ color: '#fff', fontWeight: 900, mt: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={
                        compareResult.deltas.organic_growth_by_fund && Object.keys(compareResult.deltas.organic_growth_by_fund).length > 0 
                          ? Object.entries(compareResult.deltas.organic_growth_by_fund as Record<string, number>).reduce((a, b) => a[1] > b[1] ? a : b)[0]
                          : 'N/A'
                      }>
                        {compareResult.deltas.organic_growth_by_fund && Object.keys(compareResult.deltas.organic_growth_by_fund).length > 0 
                          ? Object.entries(compareResult.deltas.organic_growth_by_fund as Record<string, number>).reduce((a, b) => a[1] > b[1] ? a : b)[0].substring(0, 15) + '...'
                          : 'N/A'}
                      </Typography>
                      <Typography variant="caption" sx={{ color: '#EC4899', fontWeight: 600 }}>
                        {compareResult.deltas.organic_growth_by_fund && Object.keys(compareResult.deltas.organic_growth_by_fund).length > 0 
                          ? `+${fmtInr(Object.entries(compareResult.deltas.organic_growth_by_fund as Record<string, number>).reduce((a, b) => a[1] > b[1] ? a : b)[1])}`
                          : ''} organic
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>

                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', mb: 2, borderBottom: '1px solid rgba(255,255,255,0.1)', pb: 1 }}>
                  <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 900 }}>TRANSACTION DELTAS</Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <FormControlLabel
                      control={<Switch checked={hideClosed} onChange={e => setHideClosed(e.target.checked)} size="small" sx={{ '& .MuiSwitch-switchBase.Mui-checked': { color: '#38BDF8' }, '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: '#38BDF8' } }} />}
                      label={<Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>Hide Closed</Typography>}
                    />
                    <Chip label={`${groupedTransactions.length} Funds`} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.1)', color: '#fff', fontWeight: 800 }} />
                  </Box>
                </Box>
                
                <Box sx={{ mt: 2, maxHeight: 400, overflowY: 'auto', pr: 1, '&::-webkit-scrollbar': { width: 4 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 2 } }}>
                  {compareResult.new_transactions.length === 0 ? (
                    <Box sx={{ p: 4, textAlign: 'center', bgcolor: 'rgba(78, 222, 147, 0.02)', borderRadius: '20px', border: '1px dashed rgba(78, 222, 147, 0.3)' }}>
                      <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 40, mb: 1 }} />
                      <Typography sx={{ color: '#fff', fontWeight: 800 }}>Identical Ledger</Typography>
                      <Typography variant="body2" sx={{ color: 'text.secondary' }}>No new transactions found since the baseline.</Typography>
                    </Box>
                  ) : groupedTransactions.length === 0 ? (
                    <Box sx={{ p: 4, textAlign: 'center', bgcolor: 'rgba(255, 255, 255, 0.02)', borderRadius: '20px', border: '1px dashed rgba(255, 255, 255, 0.2)' }}>
                      <Typography sx={{ color: '#fff', fontWeight: 800, mb: 1 }}>All Transactions Hidden</Typography>
                      <Typography variant="body2" sx={{ color: 'text.secondary' }}>The new transactions detected belong to completely closed funds. Disable "Hide Closed" to view them.</Typography>
                    </Box>
                  ) : (
                    <Stack spacing={2}>
                      {groupedTransactions.map((group: any, idx: number) => {
                        const isNetNegative = group.net_amount < 0
                        
                        return (
                          <Box key={idx} sx={{ 
                            p: 2.5, borderRadius: '16px', 
                            bgcolor: 'rgba(255,255,255,0.02)', 
                            borderLeft: `4px solid ${isNetNegative ? '#FF516A' : '#4EDE93'}`,
                            transition: 'transform 0.2s, background 0.2s',
                            '&:hover': { transform: 'translateX(4px)', bgcolor: 'rgba(255,255,255,0.04)' }
                          }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 1.5 }}>
                              <Typography variant="body1" sx={{ color: '#fff', fontWeight: 800, maxWidth: '70%', lineHeight: 1.2 }}>{group.fund}</Typography>
                              <Box sx={{ textAlign: 'right' }}>
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, display: 'block', mb: 0.5 }}>NET SHIFT</Typography>
                                <Chip 
                                  label={`${isNetNegative ? '-' : '+'}${fmtInr(Math.abs(group.net_amount))}`} 
                                  size="small" 
                                  sx={{ 
                                    height: 24, fontSize: 12, fontWeight: 900,
                                    bgcolor: isNetNegative ? 'rgba(255, 81, 106, 0.1)' : 'rgba(78, 222, 147, 0.1)', 
                                    color: isNetNegative ? '#FF516A' : '#4EDE93' 
                                  }} 
                                />
                              </Box>
                            </Box>

                            <Box sx={{ display: 'flex', gap: 3, p: 1.5, borderRadius: '12px', bgcolor: 'rgba(0,0,0,0.2)' }}>
                               <Box sx={{ flex: 1 }}>
                                 <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                   <CallReceivedIcon sx={{fontSize: 14, color: '#4EDE93'}}/> BOUGHT
                                 </Typography>
                                 <Typography variant="body2" className="num" sx={{ color: group.bought_amount > 0 ? '#fff' : 'text.disabled', fontWeight: 800, mt: 0.5 }}>
                                   {fmtInr(group.bought_amount)}
                                 </Typography>
                                 {group.bought_count > 0 && (
                                   <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                                     {group.bought_count} Txns • {group.bought_units.toFixed(3)} units
                                   </Typography>
                                 )}
                               </Box>
                               <Box sx={{ width: '1px', bgcolor: 'rgba(255,255,255,0.1)' }} />
                               <Box sx={{ flex: 1 }}>
                                 <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                   <CallMadeIcon sx={{fontSize: 14, color: '#FF516A'}}/> SOLD
                                 </Typography>
                                 <Typography variant="body2" className="num" sx={{ color: group.sold_amount > 0 ? '#fff' : 'text.disabled', fontWeight: 800, mt: 0.5 }}>
                                   {fmtInr(group.sold_amount)}
                                 </Typography>
                                 {group.sold_count > 0 && (
                                   <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
                                     {group.sold_count} Txns • {group.sold_units.toFixed(3)} units
                                   </Typography>
                                 )}
                               </Box>
                            </Box>
                          </Box>
                        )
                      })}
                    </Stack>
                  )}
                </Box>
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </Box>
  )
}
