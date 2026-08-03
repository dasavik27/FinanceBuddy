import { useState, useEffect, useMemo } from 'react'
import {
  Box, Typography, Paper, Grid, TextField, InputAdornment, Button,
  Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions,
  CircularProgress, Alert, Snackbar, Tabs, Tab, alpha, useTheme
} from '@mui/material'
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings'
import SearchIcon from '@mui/icons-material/Search'
import ContentCopyIcon from '@mui/icons-material/ContentCopy'
import CheckIcon from '@mui/icons-material/Check'
import SendIcon from '@mui/icons-material/Send'
import VpnKeyIcon from '@mui/icons-material/VpnKey'
import BlockIcon from '@mui/icons-material/Block'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import PersonIcon from '@mui/icons-material/Person'
import { apiClient } from '../../api/client'

interface AccessRequest {
  id: string
  email: string
  name: string
  investor_type: string
  notes: string
  status: 'pending' | 'approved' | 'rejected'
  created_at: string | null
  reviewed_at: string | null
}

const PROFILE_COLORS: Record<string, { label: string; color: string; bg: string }> = {
  individual: { label: 'Individual', color: '#38BDF8', bg: 'rgba(56, 189, 248, 0.1)' },
  hni: { label: 'HNI / Wealth', color: '#A855F7', bg: 'rgba(168, 85, 247, 0.12)' },
  advisor: { label: 'Financial Advisor', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.12)' },
  tax_pro: { label: 'CA / Tax Expert', color: '#10B981', bg: 'rgba(16, 185, 129, 0.12)' },
  corporate: { label: 'Corporate', color: '#EC4899', bg: 'rgba(236, 72, 153, 0.12)' },
}

const normalizeStatus = (status: string | null | undefined): 'pending' | 'approved' => {
  const s = (status || '').toLowerCase().trim()
  if (s === 'approved') return 'approved'
  return 'pending'
}

export default function AdminConsole() {
  const theme = useTheme()
  const [requests, setRequests] = useState<AccessRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'approved'>('all')
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [provStatus, setProvStatus] = useState<{
    supabase_url_configured: boolean
    service_role_key_configured: boolean
    can_auto_provision: boolean
  } | null>(null)

  // Password provisioning modal
  const [passModalOpen, setPassModalOpen] = useState(false)
  const [activeRequest, setActiveRequest] = useState<AccessRequest | null>(null)
  const [customPassword, setCustomPassword] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  // Notification snackbar
  const [snackbarMsg, setSnackbarMsg] = useState<{ text: string; severity: 'success' | 'error' | 'warning' | 'info' } | null>(null)

  const fetchRequests = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const [data, statusData] = await Promise.all([
        apiClient.getAccessRequests(),
        apiClient.getProvisioningStatus().catch(() => null),
      ])
      setRequests(data.requests || [])
      if (statusData) setProvStatus(statusData)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load access requests.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    fetchRequests()
  }, [])

  const handleCopyEmail = (email: string, id: string) => {
    navigator.clipboard.writeText(email)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const handleApproveInvite = async (req: AccessRequest) => {
    setActionLoading(true)
    try {
      const res = await apiClient.approveAccessRequest(req.id, { method: 'invite' })
      setSnackbarMsg({
        text: res.message || `Invitation processed for ${req.email}`,
        severity: res.supabase_provisioned ? 'success' : 'warning',
      })
      await fetchRequests(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to approve request.',
        severity: 'error',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleOpenPasswordModal = (req: AccessRequest) => {
    setActiveRequest(req)
    setCustomPassword('Welcome@2026')
    setPassModalOpen(true)
  }

  const handleCreateWithPassword = async () => {
    if (!activeRequest || !customPassword.trim()) return
    setActionLoading(true)
    try {
      const res = await apiClient.approveAccessRequest(activeRequest.id, {
        method: 'create',
        password: customPassword.trim(),
      })
      setSnackbarMsg({
        text: res.message || `Account created for ${activeRequest.email}`,
        severity: res.supabase_provisioned ? 'success' : 'warning',
      })
      setPassModalOpen(false)
      await fetchRequests(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to provision user.',
        severity: 'error',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleReject = async (req: AccessRequest) => {
    setActionLoading(true)
    try {
      const res = await apiClient.rejectAccessRequest(req.id)
      setSnackbarMsg({
        text: res.message || `Request for ${req.email} rejected and deleted from database.`,
        severity: 'info',
      })
      await fetchRequests(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to delete request.',
        severity: 'error',
      })
    } finally {
      setActionLoading(false)
    }
  }

  // Derived Stats
  const stats = useMemo(() => {
    const total = requests.length
    const pending = requests.filter((r) => normalizeStatus(r.status) === 'pending').length
    const approved = requests.filter((r) => normalizeStatus(r.status) === 'approved').length
    return { total, pending, approved }
  }, [requests])

  // Filtered requests
  const filteredRequests = useMemo(() => {
    return requests.filter((req) => {
      const st = normalizeStatus(req.status)
      const matchesStatus = statusFilter === 'all' || st === statusFilter
      const q = searchQuery.toLowerCase().trim()
      const matchesSearch = !q || req.name.toLowerCase().includes(q) || req.email.toLowerCase().includes(q)
      return matchesStatus && matchesSearch
    })
  }, [requests, statusFilter, searchQuery])

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, maxWidth: 1400, mx: 'auto' }}>
      {/* Header */}
      <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'center' }, gap: 2, mb: 3 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
            <Box sx={{ p: 1, borderRadius: '12px', bgcolor: 'rgba(56, 189, 248, 0.1)', color: '#38BDF8', display: 'flex' }}>
              <AdminPanelSettingsIcon sx={{ fontSize: 26 }} />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '-0.02em' }}>
              Access Control & Provisioning
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ color: '#94A3B8' }}>
            Review prospective user requests, issue Supabase invites, or create credentials directly.
          </Typography>
        </Box>

        <Button
          variant="outlined"
          startIcon={refreshing ? <CircularProgress size={16} sx={{ color: '#38BDF8' }} /> : <RefreshIcon />}
          onClick={() => fetchRequests(true)}
          disabled={refreshing || loading}
          sx={{
            borderRadius: '12px',
            borderColor: 'rgba(255,255,255,0.1)',
            color: '#E2E8F0',
            textTransform: 'none',
            fontWeight: 600,
            '&:hover': { borderColor: '#38BDF8', bgcolor: 'rgba(56,189,248,0.05)' }
          }}
        >
          Refresh Leads
        </Button>
      </Box>

      {/* Supabase Service Role Notice Banner */}
      {provStatus && !provStatus.service_role_key_configured && (
        <Alert
          severity="warning"
          sx={{
            mb: 3,
            borderRadius: '16px',
            bgcolor: 'rgba(245, 158, 11, 0.08)',
            border: '1px solid rgba(245, 158, 11, 0.25)',
            color: '#FCD34D',
            '& .MuiAlert-icon': { color: '#F59E0B' }
          }}
        >
          <Typography sx={{ fontWeight: 700, fontSize: '0.88rem', mb: 0.3 }}>
            Automated Supabase Provisioning Requires Service Role Key
          </Typography>
          <Typography sx={{ fontSize: '0.82rem', color: '#CBD5E1' }}>
            To automatically invite users or create accounts via 1-click in Supabase, add <code>SUPABASE_SERVICE_ROLE_KEY=your_secret_key</code> to <code>backend/.env</code> (from <strong>Supabase Dashboard → Project Settings → API → service_role</strong>).
          </Typography>
        </Alert>
      )}

      {/* KPI Stats Cards */}
      <Grid container spacing={2.5} sx={{ mb: 4 }}>
        <Grid item xs={12} sm={4}>
          <Paper sx={{ p: 2.5, borderRadius: '18px', bgcolor: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.06)', backdropFilter: 'blur(16px)' }}>
            <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, letterSpacing: '0.05em' }}>
              TOTAL REQUESTS
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#F8FAFC', mt: 0.5 }}>
              {stats.total}
            </Typography>
          </Paper>
        </Grid>

        <Grid item xs={6} sm={4}>
          <Paper sx={{ p: 2.5, borderRadius: '18px', bgcolor: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.2)', backdropFilter: 'blur(16px)' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#F59E0B', fontWeight: 700, letterSpacing: '0.05em' }}>
                PENDING REVIEW
              </Typography>
              <HourglassEmptyIcon sx={{ fontSize: 18, color: '#F59E0B' }} />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#F59E0B', mt: 0.5 }}>
              {stats.pending}
            </Typography>
          </Paper>
        </Grid>

        <Grid item xs={6} sm={4}>
          <Paper sx={{ p: 2.5, borderRadius: '18px', bgcolor: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)', backdropFilter: 'blur(16px)' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700, letterSpacing: '0.05em' }}>
                APPROVED / PROVISIONED
              </Typography>
              <CheckCircleIcon sx={{ fontSize: 18, color: '#10B981' }} />
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 800, color: '#10B981', mt: 0.5 }}>
              {stats.approved}
            </Typography>
          </Paper>
        </Grid>
      </Grid>

      {/* Filter & Search Bar */}
      <Paper sx={{ p: 2, mb: 3, borderRadius: '20px', bgcolor: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(16px)' }}>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: { xs: 'stretch', md: 'center' }, justifyContent: 'space-between', gap: 2 }}>
          <Tabs
            value={statusFilter}
            onChange={(_, val) => setStatusFilter(val)}
            sx={{
              minHeight: 40,
              '& .MuiTab-root': {
                minHeight: 40,
                py: 0.5,
                px: 2,
                borderRadius: '10px',
                color: '#94A3B8',
                fontWeight: 700,
                textTransform: 'none',
                fontSize: '0.88rem',
                '&.Mui-selected': { color: '#38BDF8', bgcolor: 'rgba(56, 189, 248, 0.1)' }
              },
              '& .MuiTabs-indicator': { display: 'none' }
            }}
          >
            <Tab value="all" label={`All (${stats.total})`} />
            <Tab value="pending" label={`Pending (${stats.pending})`} />
            <Tab value="approved" label={`Approved (${stats.approved})`} />
          </Tabs>

          <TextField
            size="small"
            placeholder="Search by name or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: '#64748B', fontSize: 18 }} />
                </InputAdornment>
              ),
            }}
            sx={{
              minWidth: { xs: '100%', md: 320 },
              '& .MuiOutlinedInput-root': {
                borderRadius: '12px',
                bgcolor: 'rgba(2, 6, 23, 0.5)',
                color: '#fff',
                border: '1px solid rgba(255,255,255,0.08)',
                '& fieldset': { border: 'none' },
                '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                '&.Mui-focused': { borderColor: '#38BDF8' }
              },
              '& input::placeholder': { color: '#64748B', opacity: 1, fontSize: '0.88rem' }
            }}
          />
        </Box>
      </Paper>

      {/* Error alert */}
      {error && (
        <Alert severity="error" sx={{ mb: 3, borderRadius: '14px', bgcolor: 'rgba(239,68,68,0.1)', color: '#EF4444' }}>
          {error}
        </Alert>
      )}

      {/* Requests Table */}
      <TableContainer component={Paper} sx={{ borderRadius: '22px', bgcolor: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)', overflow: 'hidden' }}>
        <Table sx={{ minWidth: 800 }}>
          <TableHead sx={{ bgcolor: 'rgba(2, 6, 23, 0.4)' }}>
            <TableRow>
              <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                APPLICANT
              </TableCell>
              <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                INVESTOR PROFILE
              </TableCell>
              <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                PRIMARY INTEREST / NOTES
              </TableCell>
              <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                SUBMITTED
              </TableCell>
              <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                STATUS
              </TableCell>
              <TableCell align="right" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                PROVISIONING ACTIONS
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 8 }}>
                  <CircularProgress size={32} sx={{ color: '#38BDF8' }} />
                  <Typography variant="body2" sx={{ color: '#94A3B8', mt: 1.5 }}>
                    Loading access requests...
                  </Typography>
                </TableCell>
              </TableRow>
            ) : filteredRequests.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center" sx={{ py: 8 }}>
                  <Typography variant="body1" sx={{ color: '#E2E8F0', fontWeight: 700, mb: 0.5 }}>
                    No access requests found
                  </Typography>
                  <Typography variant="body2" sx={{ color: '#64748B' }}>
                    {searchQuery ? 'Try adjusting your search criteria.' : 'New early access submissions will appear here.'}
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              filteredRequests.map((req) => {
                const profileMeta = PROFILE_COLORS[req.investor_type] || PROFILE_COLORS.individual
                return (
                  <TableRow
                    key={req.id}
                    sx={{
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' },
                      borderBottom: '1px solid rgba(255,255,255,0.04)'
                    }}
                  >
                    {/* Applicant */}
                    <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                        <Box sx={{ width: 36, height: 36, borderRadius: '10px', bgcolor: 'rgba(56,189,248,0.1)', color: '#38BDF8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.9rem' }}>
                          {req.name.charAt(0).toUpperCase()}
                        </Box>
                        <Box>
                          <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.92rem' }}>
                            {req.name}
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.2 }}>
                            <Typography sx={{ color: '#94A3B8', fontSize: '0.8rem' }}>
                              {req.email}
                            </Typography>
                            <Tooltip title={copiedId === req.id ? 'Copied!' : 'Copy email'} arrow>
                              <IconButton size="small" onClick={() => handleCopyEmail(req.email, req.id)} sx={{ p: 0.3, color: copiedId === req.id ? '#10B981' : '#64748B' }}>
                                {copiedId === req.id ? <CheckIcon sx={{ fontSize: 13 }} /> : <ContentCopyIcon sx={{ fontSize: 13 }} />}
                              </IconButton>
                            </Tooltip>
                          </Box>
                        </Box>
                      </Box>
                    </TableCell>

                    {/* Profile */}
                    <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                      <Chip
                        label={profileMeta.label}
                        size="small"
                        sx={{
                          bgcolor: profileMeta.bg,
                          color: profileMeta.color,
                          fontWeight: 700,
                          fontSize: '0.74rem',
                          borderRadius: '8px',
                          border: `1px solid ${alpha(profileMeta.color, 0.25)}`
                        }}
                      />
                    </TableCell>

                    {/* Notes */}
                    <TableCell sx={{ borderBottom: 'none', py: 2, maxWidth: 260 }}>
                      <Typography sx={{ color: req.notes ? '#CBD5E1' : '#64748B', fontSize: '0.84rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {req.notes || '—'}
                      </Typography>
                    </TableCell>

                    {/* Submitted Date */}
                    <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                      <Typography sx={{ color: '#94A3B8', fontSize: '0.82rem' }}>
                        {req.created_at ? new Date(req.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                      </Typography>
                    </TableCell>

                    {/* Status */}
                    <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                      {normalizeStatus(req.status) === 'approved' ? (
                        <Chip label="Approved" size="small" sx={{ bgcolor: 'rgba(16, 185, 129, 0.12)', color: '#10B981', fontWeight: 700, fontSize: '0.75rem', border: '1px solid rgba(16, 185, 129, 0.3)' }} />
                      ) : (
                        <Chip label="Pending Review" size="small" sx={{ bgcolor: 'rgba(245, 158, 11, 0.12)', color: '#F59E0B', fontWeight: 700, fontSize: '0.75rem', border: '1px solid rgba(245, 158, 11, 0.3)' }} />
                      )}
                    </TableCell>

                    {/* Actions */}
                    <TableCell align="right" sx={{ borderBottom: 'none', py: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                        {normalizeStatus(req.status) === 'approved' ? (
                          <>
                            <Tooltip title="Re-send invite email" arrow>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<SendIcon sx={{ fontSize: '13px !important' }} />}
                                onClick={() => handleApproveInvite(req)}
                                disabled={actionLoading}
                                sx={{
                                  borderRadius: '10px',
                                  borderColor: 'rgba(16,185,129,0.3)',
                                  color: '#10B981',
                                  fontSize: '0.75rem',
                                  fontWeight: 700,
                                  textTransform: 'none',
                                  py: 0.4,
                                  px: 1.2,
                                  '&:hover': { bgcolor: 'rgba(16,185,129,0.08)' }
                                }}
                              >
                                Re-invite
                              </Button>
                            </Tooltip>
                            <Tooltip title="Delete record" arrow>
                              <IconButton size="small" onClick={() => handleReject(req)} disabled={actionLoading} sx={{ color: '#64748B', '&:hover': { color: '#EF4444' } }}>
                                <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                              </IconButton>
                            </Tooltip>
                          </>
                        ) : (
                          <>
                            <Tooltip title="Send Supabase automated invitation email" arrow>
                              <Button
                                size="small"
                                variant="contained"
                                startIcon={<SendIcon sx={{ fontSize: '14px !important' }} />}
                                onClick={() => handleApproveInvite(req)}
                                disabled={actionLoading}
                                sx={{
                                  borderRadius: '10px',
                                  background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
                                  fontSize: '0.78rem',
                                  fontWeight: 700,
                                  textTransform: 'none',
                                  py: 0.6,
                                  px: 1.4,
                                }}
                              >
                                Invite User
                              </Button>
                            </Tooltip>

                            <Tooltip title="Set initial password and provision directly" arrow>
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<VpnKeyIcon sx={{ fontSize: '14px !important' }} />}
                                onClick={() => handleOpenPasswordModal(req)}
                                disabled={actionLoading}
                                sx={{
                                  borderRadius: '10px',
                                  borderColor: 'rgba(255,255,255,0.15)',
                                  color: '#E2E8F0',
                                  fontSize: '0.78rem',
                                  fontWeight: 700,
                                  textTransform: 'none',
                                  py: 0.6,
                                  px: 1.2,
                                  '&:hover': { borderColor: '#38BDF8', bgcolor: 'rgba(56,189,248,0.08)' }
                                }}
                              >
                                Set Password
                              </Button>
                            </Tooltip>

                            <Tooltip title="Reject & delete from database" arrow>
                              <IconButton size="small" onClick={() => handleReject(req)} disabled={actionLoading} sx={{ color: '#64748B', '&:hover': { color: '#EF4444' } }}>
                                <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                              </IconButton>
                            </Tooltip>
                          </>
                        )}
                      </Box>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Set Password Provisioning Modal */}
      <Dialog
        open={passModalOpen}
        onClose={() => setPassModalOpen(false)}
        maxWidth="xs"
        fullWidth
        slotProps={{
          backdrop: { sx: { backdropFilter: 'blur(12px)', bgcolor: 'rgba(2, 6, 23, 0.7)' } }
        }}
        PaperProps={{
          sx: {
            borderRadius: '22px',
            background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: '0 25px 60px rgba(0, 0, 0, 0.8)',
            p: 1.5,
            color: '#fff',
          }
        }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Typography sx={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff' }}>
            Provision User with Password
          </Typography>
          <Typography sx={{ fontSize: '0.8rem', color: '#94A3B8', mt: 0.3 }}>
            Directly create credentials for <strong>{activeRequest?.email}</strong>
          </Typography>
        </DialogTitle>

        <DialogContent sx={{ pt: '12px !important' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <Box>
              <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.6 }}>
                INITIAL TEMPORARY PASSWORD
              </Typography>
              <TextField
                fullWidth
                size="small"
                value={customPassword}
                onChange={(e) => setCustomPassword(e.target.value)}
                disabled={actionLoading}
                placeholder="Enter password (e.g. Welcome@2026)"
                sx={{
                  '& .MuiOutlinedInput-root': {
                    borderRadius: '12px',
                    backgroundColor: 'rgba(2, 6, 23, 0.5)',
                    color: '#fff',
                    border: '1px solid rgba(255,255,255,0.08)',
                    '& fieldset': { border: 'none' },
                    '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                    '&.Mui-focused': { borderColor: '#38BDF8' }
                  }
                }}
              />
            </Box>

            <Alert severity="info" sx={{ borderRadius: '10px', bgcolor: 'rgba(56, 189, 248, 0.08)', color: '#38BDF8', fontSize: '0.8rem', py: 0.5, '& .MuiAlert-icon': { color: '#38BDF8' } }}>
              This creates the user in Supabase with auto-confirm enabled. You can share this temporary password with the user.
            </Alert>
          </Box>
        </DialogContent>

        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setPassModalOpen(false)} disabled={actionLoading} sx={{ color: '#94A3B8', textTransform: 'none' }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleCreateWithPassword}
            disabled={actionLoading || !customPassword.trim()}
            sx={{
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #0284C7 0%, #2563EB 100%)',
              fontWeight: 700,
              textTransform: 'none',
              px: 3,
            }}
          >
            {actionLoading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Create Account'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Snackbar notification */}
      <Snackbar
        open={Boolean(snackbarMsg)}
        autoHideDuration={4000}
        onClose={() => setSnackbarMsg(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
      >
        {snackbarMsg ? (
          <Alert severity={snackbarMsg.severity} sx={{ borderRadius: '12px', fontWeight: 600 }}>
            {snackbarMsg.text}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  )
}
