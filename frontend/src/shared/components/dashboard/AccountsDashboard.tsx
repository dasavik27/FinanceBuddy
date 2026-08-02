import React, { useState } from 'react'
import { Box, Typography, Paper, Grid, Stack, Chip, Button, IconButton, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, Alert, Snackbar, alpha } from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import DeleteIcon from '@mui/icons-material/Delete'
import SecurityIcon from '@mui/icons-material/Security'
import ShieldIcon from '@mui/icons-material/Shield'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import ReceiptIcon from '@mui/icons-material/Receipt'
import CachedIcon from '@mui/icons-material/Cached'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'

import ShowChartIcon from '@mui/icons-material/ShowChart'
import LightbulbIcon from '@mui/icons-material/Lightbulb'

import { apiClient } from '../../api/client'
import { useLogout } from '../../store/appStore'

/**
 * Every domain that can own a session, keyed by the `upload_type` the registry stores.
 *
 * This page used to test `hasMF`/`hasTax` with two hardcoded comparisons, so an
 * account with equity or budget uploads showed "ACTIVE MODULES (3 Sessions)" above an
 * empty list - the count came from `sessions.length` but the rows were filtered to two
 * modules. Driving the list off a table means adding a domain is one entry here, and a
 * module nobody has mapped still renders (see the fallback below) instead of vanishing.
 */
const MODULES: Record<string, { label: string; icon: React.ReactNode }> = {
  mutual_funds: { label: 'Mutual Funds',      icon: <AccountBalanceWalletIcon sx={{ color: '#38BDF8', fontSize: 20 }} /> },
  equity:       { label: 'Indian Stocks',     icon: <ShowChartIcon sx={{ color: '#3B82F6', fontSize: 20 }} /> },
  tax_expert:   { label: 'Tax Expert (AIS)',  icon: <ReceiptIcon sx={{ color: '#F59E0B', fontSize: 20 }} /> },
  budget:       { label: 'Budget Analyzer',   icon: <LightbulbIcon sx={{ color: '#FBBF24', fontSize: 20 }} /> },
}

/** Modules present on an account, in MODULES order, with per-module session counts. */
function activeModules(sessions: { module: string }[]) {
  const counts = new Map<string, number>()
  for (const s of sessions) counts.set(s.module, (counts.get(s.module) ?? 0) + 1)

  const known = Object.keys(MODULES)
    .filter((k) => counts.has(k))
    .map((k) => ({ key: k, ...MODULES[k], count: counts.get(k)! }))

  // Anything the registry reports that this table does not know about. Shown rather
  // than dropped: a session the user cannot see is one they cannot reason about
  // before hitting Purge.
  const unknown = [...counts.keys()]
    .filter((k) => !(k in MODULES))
    .map((k) => ({ key: k, label: k, icon: <ShieldIcon sx={{ color: '#64748B', fontSize: 20 }} />, count: counts.get(k)! }))

  return [...known, ...unknown]
}

export default function AccountsDashboard() {
  const queryClient = useQueryClient()
  const logout = useLogout()
  const [deletePan, setDeletePan] = useState<string | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  const [snack, setSnack] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({
    open: false,
    msg: '',
    severity: 'success',
  })

  const { data, isLoading } = useQuery({
    queryKey: ['accounts-summary'],
    queryFn: () => apiClient.getAccountsSummary(),
  })

  const purgeMutation = useMutation({
    mutationFn: () => apiClient.purgeAccount(),
    onSuccess: () => {
      queryClient.clear()
      setDeletePan(null)
      logout()
    }
  })

  const clearCacheMutation = useMutation({
    mutationFn: () => apiClient.clearSystemCaches(),
    onSuccess: () => {
      logout()
      queryClient.clear()
    }
  })

  const handleExportData = async () => {
    try {
      setIsExporting(true)
      const exportData = await apiClient.exportAccount()
      const jsonStr = JSON.stringify(exportData, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const panTag = exportData?.pan || 'account'
      const dateTag = new Date().toISOString().slice(0, 10)
      a.download = `finance_buddy_export_${panTag}_${dateTag}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setSnack({ open: true, msg: 'Account data exported successfully as JSON archive.', severity: 'success' })
    } catch (err: any) {
      console.error('Export failed', err)
      setSnack({
        open: true,
        msg: err?.response?.data?.detail || 'Failed to export account data. Please check your session.',
        severity: 'error',
      })
    } finally {
      setIsExporting(false)
    }
  }

  const handleConfirmDelete = () => {
    if (deletePan) {
      purgeMutation.mutate()
    }
  }

  const accounts = data?.accounts || []

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress sx={{ color: '#6366F1' }} />
      </Box>
    )
  }

  return (
    <Box sx={{ pb: 8 }}>
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <Box sx={{ p: 1, borderRadius: '12px', bgcolor: alpha('#818CF8', 0.1) }}>
            <SecurityIcon sx={{ color: '#818CF8' }} />
          </Box>
          <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff' }}>Account Settings</Typography>
        </Box>
        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600, maxWidth: 600 }}>
          Manage your secure sessions, active modules, uploads across every domain, and global system caches in one place.
        </Typography>
      </Box>

      {accounts.length === 0 ? (
        <Paper className="glass" sx={{ p: 6, borderRadius: '24px', textAlign: 'center', border: '1px solid rgba(255,255,255,0.05)' }}>
          <ShieldIcon sx={{ fontSize: 48, color: '#64748B', mb: 2 }} />
          <Typography variant="h6" sx={{ color: '#F8FAFC', fontWeight: 800, mb: 1 }}>No Active Accounts Found</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>You have not uploaded any statements yet - a CAS, a broker file, an AIS or a bank statement will show up here.</Typography>
        </Paper>
      ) : (
        <Grid container spacing={3}>
          {accounts.map((acc: any) => {
            const modules = activeModules(acc.sessions || [])

            return (
              <Grid item xs={12} md={6} lg={4} key={acc.pan}>
                <Paper className="glass" sx={{ 
                  p: 3, borderRadius: '24px', border: '1px solid rgba(99, 102, 241, 0.2)',
                  background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.7) 100%)',
                  boxShadow: '0 10px 40px -10px rgba(0,0,0,0.5)',
                  position: 'relative', overflow: 'hidden'
                }}>
                  <Box sx={{ position: 'absolute', top: 0, left: 0, w: '100%', h: 4, background: 'linear-gradient(90deg, #6366F1, #38BDF8)', width: '100%', height: 4 }} />
                  
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
                    <Box>
                      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, letterSpacing: '0.1em' }}>PAN NUMBER</Typography>
                      <Typography variant="h6" sx={{ color: '#fff', fontWeight: 900, fontFamily: 'monospace', letterSpacing: '2px' }}>{acc.pan}</Typography>
                    </Box>
                    <IconButton size="small" onClick={() => setDeletePan(acc.pan)} sx={{ color: '#FF516A', bgcolor: alpha('#FF516A', 0.1), '&:hover': { bgcolor: alpha('#FF516A', 0.2) } }}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Box>

                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, mb: 1.5, display: 'block' }}>ACTIVE MODULES ({acc.sessions.length} Sessions)</Typography>
                  <Stack spacing={1}>
                    {modules.map((m) => (
                      <Box key={m.key} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5, borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.03)' }}>
                        {m.icon}
                        <Typography variant="body2" sx={{ color: '#F8FAFC', fontWeight: 600, flex: 1 }}>{m.label}</Typography>
                        {/* The per-module count is what makes the header total add up.
                            Without it, "3 Sessions" over two rows looks like a bug. */}
                        <Chip
                          label={m.count}
                          size="small"
                          sx={{ height: 20, fontSize: 11, fontWeight: 800, bgcolor: 'rgba(255,255,255,0.06)', color: 'text.secondary' }}
                        />
                      </Box>
                    ))}
                  </Stack>
                </Paper>
              </Grid>
            )
          })}
        </Grid>
      )}

      {/* Export Account Data Section */}
      <Box sx={{ mt: 6 }}>
        <Typography variant="h6" sx={{ color: '#F8FAFC', fontWeight: 800, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <FileDownloadIcon sx={{ color: '#38BDF8' }} /> Data Portability & Export
        </Typography>
        <Paper className="glass" sx={{ 
          p: 3, borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2
        }}>
          <Box>
            <Typography variant="body1" sx={{ color: '#F8FAFC', fontWeight: 700 }}>Export Complete Account Archive</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', maxWidth: 600 }}>
              Download a decrypted JSON snapshot of every session you own across all four modules - Mutual Funds, Indian Stocks, Tax Expert and Budget Analyzer. Useful for offline analysis or backing up your history before purging.
            </Typography>
          </Box>
          <Button 
            variant="contained" 
            startIcon={isExporting ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : <FileDownloadIcon />}
            onClick={handleExportData}
            disabled={isExporting}
            sx={{ 
              background: 'linear-gradient(135deg, #6366F1 0%, #38BDF8 100%)',
              color: '#fff',
              borderRadius: '12px',
              fontWeight: 800,
              px: 3,
              py: 1.2,
              boxShadow: '0 8px 24px rgba(99, 102, 241, 0.3)',
              '&:hover': {
                background: 'linear-gradient(135deg, #4F46E5 0%, #0284C7 100%)',
              }
            }}
          >
            {isExporting ? 'Exporting JSON...' : 'Export Account Data'}
          </Button>
        </Paper>
      </Box>

      {/* Global Cache Management */}
      <Box sx={{ mt: 4 }}>
        <Typography variant="h6" sx={{ color: '#F8FAFC', fontWeight: 800, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
          <CachedIcon sx={{ color: '#6366F1' }} /> Global System Caches
        </Typography>
        <Paper className="glass" sx={{ 
          p: 3, borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 2
        }}>
          <Box>
            <Typography variant="body1" sx={{ color: '#F8FAFC', fontWeight: 700 }}>Market Data & Application Caches</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', maxWidth: 600 }}>
              Clearing system caches will instantly wipe downloaded live NAVs, stock histories, and AMFI TER data from the server memory. It will force the system to download fresh market data from exchanges on the next request.
            </Typography>
          </Box>
          <Button 
            variant="outlined" 
            onClick={() => clearCacheMutation.mutate()}
            disabled={clearCacheMutation.isPending}
            sx={{ 
              color: '#38BDF8', borderColor: 'rgba(56,189,248,0.3)', borderRadius: '12px', fontWeight: 700, px: 3,
              '&:hover': { bgcolor: alpha('#38BDF8', 0.1), borderColor: '#38BDF8' }
            }}
          >
            {clearCacheMutation.isPending ? 'Clearing...' : 'Clear All Caches'}
          </Button>
        </Paper>
      </Box>

      <Snackbar 
        open={snack.open} 
        autoHideDuration={4000} 
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snack.severity} sx={{ borderRadius: '12px', fontWeight: 600 }}>
          {snack.msg}
        </Alert>
      </Snackbar>

      <Dialog 
        open={!!deletePan} 
        onClose={() => setDeletePan(null)}
        PaperProps={{
          className: "glass",
          sx: { bgcolor: '#0F172A', border: '1px solid rgba(255,81,106,0.3)', borderRadius: '24px', p: 1 }
        }}
      >
        <DialogTitle sx={{ color: '#F8FAFC', fontWeight: 900 }}>Purge Account Data?</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 500, mb: 2 }}>
            You are about to permanently delete all active sessions for PAN <Typography component="span" sx={{ color: '#fff', fontWeight: 800, fontFamily: 'monospace' }}>{deletePan}</Typography>.
          </Typography>
          <Typography variant="body2" sx={{ color: '#FF516A', fontWeight: 600 }}>
            This action cannot be undone. You will need to re-upload your statements to access these modules again.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeletePan(null)} sx={{ color: 'text.secondary', fontWeight: 700 }}>Cancel</Button>
          <Button 
            variant="contained" 
            onClick={handleConfirmDelete}
            disabled={purgeMutation.isPending}
            sx={{ 
              bgcolor: '#FF516A', color: '#fff', fontWeight: 800, borderRadius: '12px',
              '&:hover': { bgcolor: '#E11D48' }
            }}
          >
            {purgeMutation.isPending ? 'Purging...' : 'Delete Permanently'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
