import { useState, useEffect, useMemo, type FormEvent } from 'react'
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
import BlockIcon from '@mui/icons-material/Block'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import RefreshIcon from '@mui/icons-material/Refresh'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import PersonIcon from '@mui/icons-material/Person'
import PersonAddAlt1Icon from '@mui/icons-material/PersonAddAlt1'
import { apiClient } from '../../api/client'
import { useAppStore } from '../../store/appStore'

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

interface AppUser {
  user_id: string
  email: string | null
  status: 'pending' | 'active' | 'suspended'
  role: 'user' | 'admin'
  created_at: string | null
  last_seen_at: string | null
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

const adminFieldSx = {
  '& .MuiOutlinedInput-root': {
    borderRadius: '12px',
    bgcolor: 'rgba(2, 6, 23, 0.5)',
    color: '#fff',
    '& fieldset': { borderColor: 'rgba(255,255,255,0.08)' },
    '&:hover fieldset': { borderColor: 'rgba(255,255,255,0.15)' },
    '&.Mui-focused fieldset': { borderColor: '#38BDF8' },
  },
  '& .MuiInputLabel-root': { color: '#94A3B8' },
  '& .MuiInputLabel-root.Mui-focused': { color: '#38BDF8' },
  '& select': { color: '#fff' },
}

export default function AdminConsole() {
  const theme = useTheme()
  const myUserId = useAppStore((s) => s.userId)
  const [requests, setRequests] = useState<AccessRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AppUser | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<'all' | 'pending' | 'approved'>('all')
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const [actionLoading, setActionLoading] = useState(false)

  // Direct invite form (invite email only — user sets their own password)
  const [inviteName, setInviteName] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteLoading, setInviteLoading] = useState(false)

  // Suspend form
  const [suspendEmail, setSuspendEmail] = useState('')
  const [suspendLoading, setSuspendLoading] = useState(false)

  // Fresh page load: keep invite/suspend fields empty (avoid browser/session leftovers).
  useEffect(() => {
    setInviteName('')
    setInviteEmail('')
    setSuspendEmail('')
    setAccountSearch('')
  }, [])

  // User accounts
  const [accounts, setAccounts] = useState<AppUser[]>([])
  const [accountsLoading, setAccountsLoading] = useState(true)
  const [accountsRefreshing, setAccountsRefreshing] = useState(false)
  const [accountsError, setAccountsError] = useState<string | null>(null)
  const [accountSearch, setAccountSearch] = useState('')
  const [accountDrafts, setAccountDrafts] = useState<Record<string, { status: AppUser['status']; role: AppUser['role'] }>>({})
  const [savingUserId, setSavingUserId] = useState<string | null>(null)

  // Notification snackbar
  const [snackbarMsg, setSnackbarMsg] = useState<{ text: string; severity: 'success' | 'error' | 'warning' | 'info' } | null>(null)

  const fetchRequests = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const data = await apiClient.getAccessRequests()
      setRequests(data.requests || [])
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to load access requests.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  const fetchAccounts = async (isRefresh = false) => {
    if (isRefresh) setAccountsRefreshing(true)
    else setAccountsLoading(true)
    setAccountsError(null)
    try {
      const data = await apiClient.getAppUsers()
      const list = data.users || []
      setAccounts(list)
      setAccountDrafts(
        Object.fromEntries(list.map((u) => [u.user_id, { status: u.status, role: u.role }])),
      )
    } catch (err: any) {
      setAccountsError(err?.response?.data?.detail || err?.message || 'Failed to load user accounts.')
    } finally {
      setAccountsLoading(false)
      setAccountsRefreshing(false)
    }
  }

  useEffect(() => {
    fetchRequests()
    fetchAccounts()
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
        text: res.message || `Invite sent to ${req.email}. They will set their own password.`,
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

  const handleInviteUser = async (e: FormEvent) => {
    e.preventDefault()
    if (!inviteName.trim() || !inviteEmail.trim()) {
      setSnackbarMsg({ text: 'Name and email are required to invite a user.', severity: 'error' })
      return
    }
    setInviteLoading(true)
    try {
      const res = await apiClient.inviteUser({
        name: inviteName.trim(),
        email: inviteEmail.trim(),
        method: 'invite',
        notes: 'Admin invite',
      })
      setSnackbarMsg({
        text: res.message || `Invite email sent to ${inviteEmail.trim()}. They will set their own password.`,
        severity: res.supabase_provisioned ? 'success' : 'warning',
      })
      setInviteName('')
      setInviteEmail('')
      await fetchRequests(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to invite user.',
        severity: 'error',
      })
    } finally {
      setInviteLoading(false)
    }
  }

  const handleSuspendUser = async (e: FormEvent) => {
    e.preventDefault()
    if (!suspendEmail.trim()) {
      setSnackbarMsg({ text: 'Enter an email to suspend.', severity: 'error' })
      return
    }
    setSuspendLoading(true)
    try {
      const res = await apiClient.suspendUser(suspendEmail.trim())
      setSnackbarMsg({
        text: res.message || `Suspended ${suspendEmail.trim()}`,
        severity: res.supabase_banned ? 'success' : 'warning',
      })
      setSuspendEmail('')
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to suspend user.',
        severity: 'error',
      })
    } finally {
      setSuspendLoading(false)
    }
  }

  const handleSuspendFromRow = async (email: string) => {
    setActionLoading(true)
    try {
      const res = await apiClient.suspendUser(email)
      setSnackbarMsg({
        text: res.message || `Suspended ${email}`,
        severity: res.supabase_banned ? 'success' : 'warning',
      })
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to suspend user.',
        severity: 'error',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleSaveAccount = async (userId: string) => {
    const draft = accountDrafts[userId]
    const original = accounts.find((a) => a.user_id === userId)
    if (!draft || !original) return

    const payload: { status?: AppUser['status']; role?: AppUser['role'] } = {}
    if (draft.status !== original.status) payload.status = draft.status
    if (draft.role !== original.role) payload.role = draft.role

    if (!payload.status && !payload.role) {
      setSnackbarMsg({ text: 'No changes to save for this account.', severity: 'info' })
      return
    }

    setSavingUserId(userId)
    try {
      const res = await apiClient.updateAppUser(userId, payload)
      setSnackbarMsg({
        text: `Updated ${res.user.email || userId} (${res.user.status}, ${res.user.role})`,
        severity: 'success',
      })
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to update account.',
        severity: 'error',
      })
    } finally {
      setSavingUserId(null)
    }
  }

  const handleQuickActivate = async (user: AppUser) => {
    setSavingUserId(user.user_id)
    try {
      await apiClient.updateAppUser(user.user_id, { status: 'active' })
      setSnackbarMsg({
        text: `Activated ${user.email || user.user_id}`,
        severity: 'success',
      })
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to activate account.',
        severity: 'error',
      })
    } finally {
      setSavingUserId(null)
    }
  }

  const openDeleteUser = (user: AppUser) => {
    setDeleteTarget(user)
    setDeleteConfirm('')
  }

  const handleConfirmDeleteUser = async () => {
    if (!deleteTarget) return
    const expected = (deleteTarget.email || deleteTarget.user_id).trim().toLowerCase()
    if (deleteConfirm.trim().toLowerCase() !== expected) {
      setSnackbarMsg({
        text: 'Type the user email (or id) exactly to confirm permanent delete.',
        severity: 'error',
      })
      return
    }
    setDeleteLoading(true)
    try {
      const res = await apiClient.deleteAppUser(deleteTarget.user_id)
      setSnackbarMsg({
        text: res.message || `Deleted ${deleteTarget.email || deleteTarget.user_id}`,
        severity: 'success',
      })
      setDeleteTarget(null)
      setDeleteConfirm('')
      await Promise.all([fetchAccounts(true), fetchRequests(true)])
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to delete user.',
        severity: 'error',
      })
    } finally {
      setDeleteLoading(false)
    }
  }

  const updateAccountDraft = (
    userId: string,
    field: 'status' | 'role',
    value: AppUser['status'] | AppUser['role'],
  ) => {
    setAccountDrafts((prev) => ({
      ...prev,
      [userId]: { ...prev[userId], [field]: value },
    }))
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

  const filteredAccounts = useMemo(() => {
    const q = accountSearch.toLowerCase().trim()
    return accounts.filter((u) => {
      if (!q) return true
      return (u.email || '').toLowerCase().includes(q) || u.user_id.toLowerCase().includes(q)
    })
  }, [accounts, accountSearch])

  const accountStats = useMemo(() => {
    const active = accounts.filter((u) => u.status === 'active').length
    const pending = accounts.filter((u) => u.status === 'pending').length
    const suspended = accounts.filter((u) => u.status === 'suspended').length
    const admins = accounts.filter((u) => u.role === 'admin').length
    return { total: accounts.length, active, pending, suspended, admins }
  }, [accounts])

  const statusChipSx = (status: AppUser['status']) => {
    if (status === 'active') return { bgcolor: 'rgba(16, 185, 129, 0.12)', color: '#10B981', border: '1px solid rgba(16, 185, 129, 0.3)' }
    if (status === 'suspended') return { bgcolor: 'rgba(239, 68, 68, 0.12)', color: '#F87171', border: '1px solid rgba(239, 68, 68, 0.3)' }
    return { bgcolor: 'rgba(245, 158, 11, 0.12)', color: '#F59E0B', border: '1px solid rgba(245, 158, 11, 0.3)' }
  }

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
            Review access requests, manage user accounts, issue invites, and assign roles.
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

      {/* Direct invite + suspend */}
      <Grid container spacing={2.5} sx={{ mb: 4 }}>
        <Grid item xs={12} md={8}>
          <Paper
            component="form"
            onSubmit={handleInviteUser}
            sx={{ p: 2.5, borderRadius: '18px', bgcolor: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.06)' }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <PersonAddAlt1Icon sx={{ color: '#38BDF8', fontSize: 20 }} />
              <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>Invite user</Typography>
            </Box>
            <Grid container spacing={1.5}>
              <Grid item xs={12} sm={5}>
                <TextField
                  size="small"
                  fullWidth
                  label="Name"
                  value={inviteName}
                  onChange={(e) => setInviteName(e.target.value)}
                  sx={adminFieldSx}
                />
              </Grid>
              <Grid item xs={12} sm={5}>
                <TextField
                  size="small"
                  fullWidth
                  label="Email"
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  sx={adminFieldSx}
                />
              </Grid>
              <Grid item xs={12} sm={2} sx={{ display: 'flex', alignItems: 'center' }}>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={inviteLoading}
                  startIcon={inviteLoading ? <CircularProgress size={16} color="inherit" /> : <SendIcon />}
                  sx={{ borderRadius: '12px', textTransform: 'none', fontWeight: 700, bgcolor: '#38BDF8', color: '#0F172A', '&:hover': { bgcolor: '#7DD3FC' } }}
                >
                  Send invite
                </Button>
              </Grid>
              <Grid item xs={12}>
                <Typography sx={{ fontSize: '0.78rem', color: '#64748B' }}>
                  Sends a Supabase invite email. The user sets their own password after opening the link.
                </Typography>
              </Grid>
            </Grid>
          </Paper>
        </Grid>
        <Grid item xs={12} md={4}>
          <Paper
            component="form"
            onSubmit={handleSuspendUser}
            sx={{ p: 2.5, borderRadius: '18px', bgcolor: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(239,68,68,0.2)', height: '100%' }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
              <BlockIcon sx={{ color: '#F87171', fontSize: 20 }} />
              <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>Suspend user</Typography>
            </Box>
            <TextField
              size="small"
              fullWidth
              label="Email"
              type="email"
              value={suspendEmail}
              onChange={(e) => setSuspendEmail(e.target.value)}
              sx={{ ...adminFieldSx, mb: 1.5 }}
            />
            <Button
              type="submit"
              variant="outlined"
              disabled={suspendLoading}
              startIcon={suspendLoading ? <CircularProgress size={16} color="inherit" /> : <BlockIcon />}
              sx={{ borderRadius: '12px', textTransform: 'none', fontWeight: 700, borderColor: 'rgba(239,68,68,0.4)', color: '#FCA5A5', '&:hover': { borderColor: '#EF4444', bgcolor: 'rgba(239,68,68,0.08)' } }}
            >
              Suspend access
            </Button>
          </Paper>
        </Grid>
      </Grid>

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
                            <Tooltip title="Suspend app access" arrow>
                              <IconButton
                                size="small"
                                onClick={() => handleSuspendFromRow(req.email)}
                                disabled={actionLoading}
                                sx={{ color: '#64748B', '&:hover': { color: '#F87171' } }}
                              >
                                <BlockIcon sx={{ fontSize: 18 }} />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title="Delete record" arrow>
                              <IconButton size="small" onClick={() => handleReject(req)} disabled={actionLoading} sx={{ color: '#64748B', '&:hover': { color: '#EF4444' } }}>
                                <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                              </IconButton>
                            </Tooltip>
                          </>
                        ) : (
                          <>
                            <Tooltip title="Approve and send invite email — user sets their own password" arrow>
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
                                Approve & invite
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

      {/* User accounts section */}
      <Box sx={{ mt: 6, mb: 2 }}>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'center' }, gap: 2, mb: 2.5 }}>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
              <Box sx={{ p: 1, borderRadius: '12px', bgcolor: 'rgba(168, 85, 247, 0.1)', color: '#A855F7', display: 'flex' }}>
                <PersonIcon sx={{ fontSize: 22 }} />
              </Box>
              <Typography variant="h6" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '-0.02em' }}>
                User accounts
              </Typography>
            </Box>
            <Typography variant="body2" sx={{ color: '#94A3B8' }}>
              Activate pending users and assign admin or user roles for provisioned accounts.
            </Typography>
          </Box>
          <Button
            variant="outlined"
            startIcon={accountsRefreshing ? <CircularProgress size={16} sx={{ color: '#A855F7' }} /> : <RefreshIcon />}
            onClick={() => fetchAccounts(true)}
            disabled={accountsRefreshing || accountsLoading}
            sx={{
              borderRadius: '12px',
              borderColor: 'rgba(255,255,255,0.1)',
              color: '#E2E8F0',
              textTransform: 'none',
              fontWeight: 600,
              '&:hover': { borderColor: '#A855F7', bgcolor: 'rgba(168,85,247,0.05)' }
            }}
          >
            Refresh accounts
          </Button>
        </Box>

        <Grid container spacing={2} sx={{ mb: 2.5 }}>
          <Grid item xs={6} sm={3}>
            <Paper sx={{ p: 2, borderRadius: '14px', bgcolor: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
              <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700 }}>TOTAL ACCOUNTS</Typography>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', mt: 0.3 }}>{accountStats.total}</Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Paper sx={{ p: 2, borderRadius: '14px', bgcolor: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
              <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700 }}>ACTIVE</Typography>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#10B981', mt: 0.3 }}>{accountStats.active}</Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Paper sx={{ p: 2, borderRadius: '14px', bgcolor: 'rgba(245, 158, 11, 0.05)', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
              <Typography variant="caption" sx={{ color: '#F59E0B', fontWeight: 700 }}>PENDING</Typography>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#F59E0B', mt: 0.3 }}>{accountStats.pending}</Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} sm={3}>
            <Paper sx={{ p: 2, borderRadius: '14px', bgcolor: 'rgba(56, 189, 248, 0.05)', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
              <Typography variant="caption" sx={{ color: '#38BDF8', fontWeight: 700 }}>ADMINS</Typography>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#38BDF8', mt: 0.3 }}>{accountStats.admins}</Typography>
            </Paper>
          </Grid>
        </Grid>

        <Paper sx={{ p: 2, mb: 2, borderRadius: '16px', bgcolor: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(255,255,255,0.08)' }}>
          <TextField
            size="small"
            fullWidth
            placeholder="Search accounts by email or user id..."
            value={accountSearch}
            onChange={(e) => setAccountSearch(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: '#64748B', fontSize: 18 }} />
                </InputAdornment>
              ),
            }}
            sx={{
              '& .MuiOutlinedInput-root': {
                borderRadius: '12px',
                bgcolor: 'rgba(2, 6, 23, 0.5)',
                color: '#fff',
                border: '1px solid rgba(255,255,255,0.08)',
                '& fieldset': { border: 'none' },
                '&:hover': { borderColor: 'rgba(255,255,255,0.15)' },
                '&.Mui-focused': { borderColor: '#A855F7' }
              },
              '& input::placeholder': { color: '#64748B', opacity: 1 }
            }}
          />
        </Paper>

        {accountsError && (
          <Alert severity="error" sx={{ mb: 2, borderRadius: '14px', bgcolor: 'rgba(239,68,68,0.1)', color: '#EF4444' }}>
            {accountsError}
          </Alert>
        )}

        <TableContainer component={Paper} sx={{ borderRadius: '22px', bgcolor: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)', overflow: 'hidden' }}>
          <Table sx={{ minWidth: 760 }}>
            <TableHead sx={{ bgcolor: 'rgba(2, 6, 23, 0.4)' }}>
              <TableRow>
                <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  ACCOUNT
                </TableCell>
                <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  STATUS
                </TableCell>
                <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  ROLE
                </TableCell>
                <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  LAST SEEN
                </TableCell>
                <TableCell align="right" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  ACTIONS
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {accountsLoading ? (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 6 }}>
                    <CircularProgress size={28} sx={{ color: '#A855F7' }} />
                    <Typography variant="body2" sx={{ color: '#94A3B8', mt: 1.5 }}>
                      Loading user accounts...
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : filteredAccounts.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 6 }}>
                    <Typography variant="body1" sx={{ color: '#E2E8F0', fontWeight: 700, mb: 0.5 }}>
                      No user accounts found
                    </Typography>
                    <Typography variant="body2" sx={{ color: '#64748B' }}>
                      {accountSearch ? 'Try a different search term.' : 'Provisioned users will appear here after their first sign-in.'}
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                filteredAccounts.map((user) => {
                  const draft = accountDrafts[user.user_id] || { status: user.status, role: user.role }
                  const hasChanges = draft.status !== user.status || draft.role !== user.role
                  const isSaving = savingUserId === user.user_id
                  return (
                    <TableRow key={user.user_id} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' }, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                      <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                        <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.9rem' }}>
                          {user.email || '—'}
                        </Typography>
                        <Typography sx={{ color: '#64748B', fontSize: '0.75rem', fontFamily: 'monospace', mt: 0.3 }}>
                          {user.user_id}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                        <TextField
                          size="small"
                          select
                          value={draft.status}
                          onChange={(e) => updateAccountDraft(user.user_id, 'status', e.target.value as AppUser['status'])}
                          SelectProps={{ native: true }}
                          disabled={isSaving}
                          sx={{ ...adminFieldSx, minWidth: 130 }}
                        >
                          <option value="pending">Pending</option>
                          <option value="active">Active</option>
                          <option value="suspended">Suspended</option>
                        </TextField>
                      </TableCell>
                      <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                        <TextField
                          size="small"
                          select
                          value={draft.role}
                          onChange={(e) => updateAccountDraft(user.user_id, 'role', e.target.value as AppUser['role'])}
                          SelectProps={{ native: true }}
                          disabled={isSaving}
                          sx={{ ...adminFieldSx, minWidth: 110 }}
                        >
                          <option value="user">User</option>
                          <option value="admin">Admin</option>
                        </TextField>
                      </TableCell>
                      <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                        <Typography sx={{ color: '#94A3B8', fontSize: '0.82rem' }}>
                          {user.last_seen_at
                            ? new Date(user.last_seen_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
                            : '—'}
                        </Typography>
                        {!hasChanges && (
                          <Chip
                            label={user.status}
                            size="small"
                            sx={{ mt: 0.6, fontWeight: 700, fontSize: '0.7rem', borderRadius: '8px', ...statusChipSx(user.status) }}
                          />
                        )}
                      </TableCell>
                      <TableCell align="right" sx={{ borderBottom: 'none', py: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                          {user.status === 'pending' && (
                            <Button
                              size="small"
                              variant="outlined"
                              onClick={() => handleQuickActivate(user)}
                              disabled={isSaving}
                              sx={{
                                borderRadius: '10px',
                                borderColor: 'rgba(16,185,129,0.3)',
                                color: '#10B981',
                                fontSize: '0.75rem',
                                fontWeight: 700,
                                textTransform: 'none',
                              }}
                            >
                              Activate
                            </Button>
                          )}
                          <Button
                            size="small"
                            variant="contained"
                            onClick={() => handleSaveAccount(user.user_id)}
                            disabled={isSaving || !hasChanges}
                            sx={{
                              borderRadius: '10px',
                              textTransform: 'none',
                              fontWeight: 700,
                              fontSize: '0.75rem',
                              bgcolor: hasChanges ? '#A855F7' : 'rgba(148,163,184,0.2)',
                              color: hasChanges ? '#fff' : '#64748B',
                              '&:hover': { bgcolor: hasChanges ? '#9333EA' : 'rgba(148,163,184,0.2)' },
                            }}
                          >
                            {isSaving ? <CircularProgress size={14} sx={{ color: '#fff' }} /> : 'Save'}
                          </Button>
                          <Tooltip
                            title={
                              user.user_id === myUserId
                                ? 'You cannot delete your own account here'
                                : 'Permanently delete account and all data'
                            }
                            arrow
                          >
                            <span>
                              <IconButton
                                size="small"
                                onClick={() => openDeleteUser(user)}
                                disabled={isSaving || deleteLoading || user.user_id === myUserId}
                                sx={{ color: '#64748B', '&:hover': { color: '#EF4444' } }}
                              >
                                <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </Box>
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Box>

      {/* Permanent delete confirmation */}
      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => !deleteLoading && setDeleteTarget(null)}
        maxWidth="xs"
        fullWidth
        slotProps={{
          backdrop: { sx: { backdropFilter: 'blur(12px)', bgcolor: 'rgba(2, 6, 23, 0.7)' } },
        }}
        PaperProps={{
          sx: {
            borderRadius: '22px',
            background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            p: 1.5,
            color: '#fff',
          },
        }}
      >
        <DialogTitle sx={{ pb: 1 }}>
          <Typography sx={{ fontSize: '1.15rem', fontWeight: 800, color: '#FCA5A5' }}>
            Delete user permanently
          </Typography>
          <Typography sx={{ fontSize: '0.82rem', color: '#94A3B8', mt: 0.5, lineHeight: 1.5 }}>
            This removes the app account, sessions, portfolios, budget data, access requests,
            and the Supabase login for{' '}
            <strong style={{ color: '#F8FAFC' }}>{deleteTarget?.email || deleteTarget?.user_id}</strong>.
            This cannot be undone.
          </Typography>
        </DialogTitle>
        <DialogContent sx={{ pt: '12px !important' }}>
          <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.8 }}>
            TYPE EMAIL TO CONFIRM
          </Typography>
          <TextField
            fullWidth
            size="small"
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            disabled={deleteLoading}
            placeholder={deleteTarget?.email || deleteTarget?.user_id || ''}
            sx={adminFieldSx}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button
            onClick={() => setDeleteTarget(null)}
            disabled={deleteLoading}
            sx={{ color: '#94A3B8', textTransform: 'none' }}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={() => void handleConfirmDeleteUser()}
            disabled={
              deleteLoading ||
              !deleteTarget ||
              deleteConfirm.trim().toLowerCase() !==
                (deleteTarget.email || deleteTarget.user_id).trim().toLowerCase()
            }
            sx={{
              borderRadius: '12px',
              bgcolor: '#EF4444',
              fontWeight: 700,
              textTransform: 'none',
              px: 2.5,
              '&:hover': { bgcolor: '#DC2626' },
            }}
          >
            {deleteLoading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Delete forever'}
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
