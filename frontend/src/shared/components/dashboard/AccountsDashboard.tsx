import React, { useState } from 'react'
import { Box, Typography, Paper, Grid, Stack, Chip, Button, IconButton, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, alpha } from '@mui/material'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import DeleteIcon from '@mui/icons-material/Delete'
import SecurityIcon from '@mui/icons-material/Security'
import ShieldIcon from '@mui/icons-material/Shield'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import ReceiptIcon from '@mui/icons-material/Receipt'
import CachedIcon from '@mui/icons-material/Cached'

import { apiClient } from '../../api/client'
import { useClearAllSessionsByPan, useLogout } from '../../store/appStore'

export default function AccountsDashboard() {
  const queryClient = useQueryClient()
  const clearSessions = useClearAllSessionsByPan()
  const logout = useLogout()
  const [deletePan, setDeletePan] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['accounts-summary'],
    queryFn: () => apiClient.getAccountsSummary(),
    refetchInterval: 10000 // Refresh every 10s just in case
  })

  const purgeMutation = useMutation({
    mutationFn: (panId: string) => apiClient.purgeAccount(panId),
    onSuccess: (_, variables) => {
      clearSessions(variables)
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      setDeletePan(null)
    }
  })

  const clearCacheMutation = useMutation({
    mutationFn: () => apiClient.clearSystemCaches(),
    onSuccess: () => {
      logout() // Instantly clears LocalStorage (PAN + tokens) and Zustand state
      queryClient.clear() // Destroys all React Query cache memory completely
    }
  })

  const handleConfirmDelete = () => {
    if (deletePan) {
      purgeMutation.mutate(deletePan)
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
          Manage your secure sessions, active modules, historical CAS uploads, and global system caches in one place.
        </Typography>
      </Box>

      {accounts.length === 0 ? (
        <Paper className="glass" sx={{ p: 6, borderRadius: '24px', textAlign: 'center', border: '1px solid rgba(255,255,255,0.05)' }}>
          <ShieldIcon sx={{ fontSize: 48, color: '#64748B', mb: 2 }} />
          <Typography variant="h6" sx={{ color: '#F8FAFC', fontWeight: 800, mb: 1 }}>No Active Accounts Found</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>You have not uploaded any CAS or AIS files recently.</Typography>
        </Paper>
      ) : (
        <Grid container spacing={3}>
          {accounts.map((acc: any) => {
            const hasMF = acc.sessions.some((s: any) => s.module === 'mutual_funds')
            const hasTax = acc.sessions.some((s: any) => s.module === 'tax_expert')
            
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
                    {hasMF && (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5, borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.03)' }}>
                        <AccountBalanceWalletIcon sx={{ color: '#38BDF8', fontSize: 20 }} />
                        <Typography variant="body2" sx={{ color: '#F8FAFC', fontWeight: 600 }}>Mutual Funds</Typography>
                      </Box>
                    )}
                    {hasTax && (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 1.5, borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.03)' }}>
                        <ReceiptIcon sx={{ color: '#F59E0B', fontSize: 20 }} />
                        <Typography variant="body2" sx={{ color: '#F8FAFC', fontWeight: 600 }}>Tax Expert (AIS)</Typography>
                      </Box>
                    )}
                  </Stack>
                </Paper>
              </Grid>
            )
          })}
        </Grid>
      )}



      {/* Global Cache Management */}
      <Box sx={{ mt: 6 }}>
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
            This action cannot be undone. You will need to re-upload your CAS or AIS files to access these modules again.
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
