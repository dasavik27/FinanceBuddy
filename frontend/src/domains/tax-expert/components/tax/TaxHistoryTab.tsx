/**
 * Saved AIS uploads, with restore and delete.
 *
 * The mutual-funds side has had a Statement History page since early on; the tax
 * domain had none, and its `GET /tax-expert/tax-history` endpoint had no caller at
 * all. Until recently it could not have had a useful one: the backend listed
 * sessions by scanning an 8-entry in-memory cache, so anything evicted was invisible
 * even though it was still stored. That query is now against the database.
 */

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogContentText, DialogTitle, Paper, Stack, Typography, alpha,
} from '@mui/material'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import HistoryIcon from '@mui/icons-material/History'
import RestoreIcon from '@mui/icons-material/Restore'

import { apiClient } from '../../../../shared/api/client'
import { useAppStore } from '../../../../shared/store/appStore'

interface TaxHistoryEntry {
  session_id: string
  created_at: string | null
  updated_at: string | null
  name: string
  fy: string
  gross_salary: number
}

const inr = new Intl.NumberFormat('en-IN', {
  style: 'currency', currency: 'INR', maximumFractionDigits: 0,
})

function formatWhen(iso: string | null): string {
  if (!iso) return 'Unknown date'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return 'Unknown date'
  return parsed.toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function TaxHistoryTab() {
  const queryClient = useQueryClient()
  const activeSessionId = useAppStore((s) => s.taxSessionId)
  const clearSession = useAppStore((s) => s.clearSession)
  const setSessionById = useAppStore((s) => s.setSessionById)
  const [pendingDelete, setPendingDelete] = useState<TaxHistoryEntry | null>(null)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['tax-history'],
    queryFn: () => apiClient.getTaxHistory(),
  })

  const remove = useMutation({
    mutationFn: (sessionId: string) => apiClient.deleteTaxSession(sessionId),
    onSuccess: (_result, sessionId) => {
      // Deleting the session currently loaded would otherwise leave the dashboard
      // rendering a session that no longer exists, and every subsequent tab 404s.
      if (sessionId === activeSessionId) clearSession('tax_expert')
      queryClient.invalidateQueries({ queryKey: ['tax-history'] })
      queryClient.invalidateQueries({ queryKey: ['tax-sessions'] })
      queryClient.invalidateQueries({ queryKey: ['accounts-summary'] })
      queryClient.invalidateQueries({ queryKey: ['tax-summary'] })
      queryClient.invalidateQueries({ queryKey: ['tax-income'] })
      queryClient.invalidateQueries({ queryKey: ['tax-capital-gains'] })
      queryClient.invalidateQueries({ queryKey: ['tax-itr'] })
      setPendingDelete(null)
    },
  })

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress size={28} />
      </Box>
    )
  }

  if (isError) {
    return (
      <Alert severity="error" sx={{ borderRadius: '12px' }}>
        {(error as any)?.response?.data?.detail ?? 'Could not load your saved filings.'}
      </Alert>
    )
  }

  const sessions: TaxHistoryEntry[] = data?.sessions ?? []

  if (sessions.length === 0) {
    return (
      <Paper elevation={0} sx={{
        p: 6, textAlign: 'center', borderRadius: '20px',
        bgcolor: alpha('#0F172A', 0.4), border: '1px solid rgba(255,255,255,0.05)',
      }}>
        <HistoryIcon sx={{ fontSize: 44, color: '#334155', mb: 1.5 }} />
        <Typography sx={{ color: '#94A3B8', fontWeight: 700 }}>
          No saved filings yet
        </Typography>
        <Typography sx={{ color: '#64748B', fontSize: '0.875rem', mt: 0.5 }}>
          Upload an AIS statement and it will appear here.
        </Typography>
      </Paper>
    )
  }

  return (
    <Box>
      <Typography sx={{ color: '#94A3B8', fontSize: '0.875rem', mb: 2.5 }}>
        {sessions.length} saved {sessions.length === 1 ? 'filing' : 'filings'}. These are
        kept until you delete them.
      </Typography>

      <Stack spacing={2}>
        {sessions.map((entry) => {
          const isActive = entry.session_id === activeSessionId
          return (
            <Paper
              key={entry.session_id}
              elevation={0}
              sx={{
                p: 2.5,
                borderRadius: '16px',
                bgcolor: alpha('#0F172A', isActive ? 0.75 : 0.4),
                border: `1px solid ${isActive ? alpha('#38BDF8', 0.4) : 'rgba(255,255,255,0.05)'}`,
                display: 'flex',
                flexWrap: 'wrap',
                gap: 2,
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <Box sx={{ minWidth: 0 }}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                  <Typography sx={{ color: '#F1F5F9', fontWeight: 800 }}>
                    FY {entry.fy || '—'}
                  </Typography>
                  {isActive && (
                    <Chip
                      label="ACTIVE"
                      size="small"
                      sx={{
                        height: 20, fontSize: '0.65rem', fontWeight: 800,
                        bgcolor: alpha('#38BDF8', 0.15), color: '#38BDF8',
                      }}
                    />
                  )}
                </Stack>
                <Typography sx={{ color: '#64748B', fontSize: '0.8rem' }}>
                  {entry.name || 'Unnamed'} · uploaded {formatWhen(entry.created_at)}
                </Typography>
                <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', mt: 0.5 }}>
                  Gross salary {inr.format(entry.gross_salary || 0)}
                </Typography>
              </Box>

              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  startIcon={<RestoreIcon />}
                  disabled={isActive}
                  onClick={() => setSessionById(entry.session_id, 'tax_expert')}
                  sx={{ textTransform: 'none', fontWeight: 700, color: '#38BDF8' }}
                >
                  {isActive ? 'Loaded' : 'Restore'}
                </Button>
                <Button
                  size="small"
                  startIcon={<DeleteOutlineIcon />}
                  onClick={() => setPendingDelete(entry)}
                  sx={{ textTransform: 'none', fontWeight: 700, color: '#F87171' }}
                >
                  Delete
                </Button>
              </Stack>
            </Paper>
          )
        })}
      </Stack>

      {/* Confirmed, because this is now permanent - stored filings used to be swept
          after 24 hours regardless, and are not any more. */}
      <Dialog open={Boolean(pendingDelete)} onClose={() => !remove.isPending && setPendingDelete(null)}>
        <DialogTitle sx={{ fontWeight: 800 }}>Delete this filing?</DialogTitle>
        <DialogContent>
          {remove.isError && (
            <Alert severity="error" sx={{ mb: 2, borderRadius: '10px' }}>
              {(remove.error as any)?.response?.data?.detail || 'Failed to delete filing session.'}
            </Alert>
          )}
          <DialogContentText>
            The AIS data for FY {pendingDelete?.fy || '—'} will be permanently removed.
            You would need to upload the statement again to restore it.
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setPendingDelete(null)} disabled={remove.isPending} sx={{ textTransform: 'none' }}>
            Cancel
          </Button>
          <Button
            color="error"
            variant="contained"
            disabled={remove.isPending}
            onClick={() => pendingDelete && remove.mutate(pendingDelete.session_id)}
            sx={{ textTransform: 'none', fontWeight: 700 }}
          >
            {remove.isPending ? 'Deleting…' : 'Delete permanently'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
