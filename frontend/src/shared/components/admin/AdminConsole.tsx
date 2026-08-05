import { useState, useEffect, useMemo, type FormEvent } from 'react'
import {
  Box, Typography, Paper, Grid, TextField, InputAdornment, Button,
  Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions,
  CircularProgress, Alert, Snackbar, Tabs, Tab, LinearProgress,
  FormControl, Select, MenuItem, Checkbox, FormControlLabel, Radio, RadioGroup
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
import StorageIcon from '@mui/icons-material/Storage'
import SyncIcon from '@mui/icons-material/Sync'
import VisibilityIcon from '@mui/icons-material/Visibility'
import SpeedIcon from '@mui/icons-material/Speed'
import PieChartOutlineIcon from '@mui/icons-material/PieChartOutline'
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import BoltIcon from '@mui/icons-material/Bolt'
import FilterListIcon from '@mui/icons-material/FilterList'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep'
import TuneIcon from '@mui/icons-material/Tune'
import LayersClearIcon from '@mui/icons-material/LayersClear'
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

interface MfSyncLog {
  id: number
  triggered_by: string
  status: 'in_progress' | 'completed' | 'failed'
  schemes_updated: number
  portfolio_month: string
  duration_seconds: number
  error_message: string | null
  created_at: string | null
}

interface MfScheme {
  isin: string
  scheme_code: string
  scheme_name: string
  amc: string
  category: string
  aum_cr: number | null
  aum_formatted: string
  expense_ratio: number | null
  risk_level: string
  portfolio_date: string | null
  sectors_count: number
  holdings_count: number
  sectors: Array<{ sector: string; value: number }>
  holdings: Array<{ name: string; pct: number }>
  source: string
  updated_at: string | null
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
  const myUserId = useAppStore((s) => s.userId)
  
  // Navigation Tabs
  const [mainTab, setMainTab] = useState<'access' | 'users' | 'market-data'>('access')

  // Access Requests
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

  // Direct invite & suspend
  const [inviteName, setInviteName] = useState('')
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteLoading, setInviteLoading] = useState(false)
  const [suspendEmail, setSuspendEmail] = useState('')
  const [suspendLoading, setSuspendLoading] = useState(false)

  // User accounts
  const [accounts, setAccounts] = useState<AppUser[]>([])
  const [accountsLoading, setAccountsLoading] = useState(true)
  const [accountsRefreshing, setAccountsRefreshing] = useState(false)
  const [accountsError, setAccountsError] = useState<string | null>(null)
  const [accountSearch, setAccountSearch] = useState('')
  const [accountDrafts, setAccountDrafts] = useState<Record<string, { status: AppUser['status']; role: AppUser['role'] }>>({})
  const [savingUserId, setSavingUserId] = useState<string | null>(null)

  // Market Data / MF Sync
  const [mfStatus, setMfStatus] = useState<{ total_schemes: number; latest_portfolio_month: string; recent_logs: MfSyncLog[] } | null>(null)
  const [mfStatusLoading, setMfStatusLoading] = useState(false)
  const [mfTriggering, setMfTriggering] = useState(false)
  const [mfSchemes, setMfSchemes] = useState<MfScheme[]>([])
  const [mfSchemesLoading, setMfSchemesLoading] = useState(false)
  const [mfSearchQuery, setMfSearchQuery] = useState('')
  const [mfAmcFilter, setMfAmcFilter] = useState<string>('All')
  const [mfCategoryFilter, setMfCategoryFilter] = useState<string>('All')
  const [selectedScheme, setSelectedScheme] = useState<MfScheme | null>(null)

  // Selective AMC Ingestion & Purge Controls
  const [syncScope, setSyncScope] = useState<'top10' | 'top5' | 'all' | 'custom'>('top10')
  const [customAmcs, setCustomAmcs] = useState<string[]>(['HDFC', 'SBI', 'ICICI Prudential', 'Quant', 'Parag Parikh'])
  const [newAmcInput, setNewAmcInput] = useState('')
  const [syncedAmcs, setSyncedAmcs] = useState<Array<{ amc: string; schemes_count: number; total_aum_cr: number }>>([])
  const [purgeDialogOpen, setPurgeDialogOpen] = useState(false)
  const [purgeMode, setPurgeMode] = useState<'all' | 'amc'>('all')
  const [purgeTargetAmc, setPurgeTargetAmc] = useState<string>('')
  const [purgeConfirmText, setPurgeConfirmText] = useState('')
  const [purgeLoading, setPurgeLoading] = useState(false)

  const [snackbarMsg, setSnackbarMsg] = useState<{ text: string; severity: 'success' | 'info' | 'error' } | null>(null)

  const fetchRequests = async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    try {
      const data = await apiClient.getAccessRequests()
      setRequests(data.requests || [])
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to fetch access requests.')
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
        list.reduce((acc, u) => {
          acc[u.user_id] = { status: u.status, role: u.role }
          return acc
        }, {} as Record<string, { status: AppUser['status']; role: AppUser['role'] }>)
      )
    } catch (err: any) {
      setAccountsError(err?.response?.data?.detail || err?.message || 'Failed to load user accounts.')
    } finally {
      setAccountsLoading(false)
      setAccountsRefreshing(false)
    }
  }

  const fetchMfData = async (query = mfSearchQuery) => {
    setMfStatusLoading(true)
    setMfSchemesLoading(true)
    try {
      const [statusRes, schemesRes, amcsRes] = await Promise.all([
        apiClient.getMfSyncStatus(),
        apiClient.searchMfSchemes(query, 50, 0),
        apiClient.getSyncedAmcs().catch(() => ({ amcs: [] })),
      ])
      setMfStatus(statusRes)
      setMfSchemes(schemesRes.schemes || [])
      setSyncedAmcs(amcsRes.amcs || [])
      if (amcsRes.amcs && amcsRes.amcs.length > 0 && !purgeTargetAmc) {
        setPurgeTargetAmc(amcsRes.amcs[0].amc)
      }
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to load market data status.',
        severity: 'error',
      })
    } finally {
      setMfStatusLoading(false)
      setMfSchemesLoading(false)
    }
  }

  const handleTriggerMfSync = async () => {
    setMfTriggering(true)
    try {
      const payload = syncScope === 'custom'
        ? { amcs: customAmcs }
        : { preset: syncScope }
      const res = await apiClient.triggerMfSync(payload)
      setSnackbarMsg({
        text: res.message || `Successfully synced ${res.schemes_updated} mutual fund factsheets!`,
        severity: 'success',
      })
      await fetchMfData()
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to trigger AMFI sync.',
        severity: 'error',
      })
    } finally {
      setMfTriggering(false)
    }
  }

  const handlePurge = async () => {
    if (purgeMode === 'all' && purgeConfirmText.trim().toUpperCase() !== 'PURGE') {
      setSnackbarMsg({ text: 'Please type "PURGE" to confirm deleting all records.', severity: 'error' })
      return
    }
    if (purgeMode === 'amc' && !purgeTargetAmc) {
      setSnackbarMsg({ text: 'Please select an AMC to delete.', severity: 'error' })
      return
    }
    setPurgeLoading(true)
    try {
      const res = await apiClient.purgeMfSnapshots(
        purgeMode === 'all' ? { purge_all: true } : { amc: purgeTargetAmc }
      )
      setSnackbarMsg({
        text: res.message || `Deleted ${res.deleted_count} schemes from database.`,
        severity: 'success',
      })
      setPurgeDialogOpen(false)
      setPurgeConfirmText('')
      await fetchMfData()
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Purge operation failed.',
        severity: 'error',
      })
    } finally {
      setPurgeLoading(false)
    }
  }

  const handleSearchMf = async (q: string) => {
    setMfSearchQuery(q)
    setMfSchemesLoading(true)
    try {
      const schemesRes = await apiClient.searchMfSchemes(
        q,
        50,
        0,
        mfAmcFilter !== 'All' ? mfAmcFilter : undefined,
        mfCategoryFilter !== 'All' ? mfCategoryFilter : undefined
      )
      setMfSchemes(schemesRes.schemes || [])
    } catch (err: any) {
      console.error(err)
    } finally {
      setMfSchemesLoading(false)
    }
  }

  const handleSelectFilter = async (filterType: 'amc' | 'category', value: string) => {
    let nextAmc = mfAmcFilter
    let nextCat = mfCategoryFilter

    if (filterType === 'amc') {
      nextAmc = value
      setMfAmcFilter(value)
    } else {
      nextCat = value
      setMfCategoryFilter(value)
    }

    setMfSchemesLoading(true)
    try {
      const schemesRes = await apiClient.searchMfSchemes(
        mfSearchQuery,
        50,
        0,
        nextAmc !== 'All' ? nextAmc : undefined,
        nextCat !== 'All' ? nextCat : undefined
      )
      setMfSchemes(schemesRes.schemes || [])
    } catch (err: any) {
      console.error(err)
    } finally {
      setMfSchemesLoading(false)
    }
  }

  useEffect(() => {
    fetchRequests()
    fetchAccounts()
  }, [])

  useEffect(() => {
    if (mainTab === 'market-data') {
      fetchMfData()
    }
  }, [mainTab])

  const handleApprove = async (req: AccessRequest) => {
    setActionLoading(true)
    try {
      const res = await apiClient.approveAccessRequest(req.id, { method: 'invite' })
      setSnackbarMsg({
        severity: 'success',
        text: res.message || `Invite email sent to ${req.email}!`,
      })
      await Promise.all([fetchRequests(true), fetchAccounts(true)])
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to send invite email.',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleReject = async (req: AccessRequest) => {
    if (!window.confirm(`Reject and permanently remove request for ${req.email}?`)) return
    setActionLoading(true)
    try {
      const res = await apiClient.rejectAccessRequest(req.id)
      setSnackbarMsg({
        severity: 'info',
        text: res.message || `Request for ${req.email} rejected and deleted from database.`,
      })
      await fetchRequests(true)
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to reject request.',
      })
    } finally {
      setActionLoading(false)
    }
  }

  const handleInviteUser = async (e: FormEvent) => {
    e.preventDefault()
    const email = inviteEmail.trim().toLowerCase()
    const name = inviteName.trim()
    if (!email) {
      setSnackbarMsg({ severity: 'error', text: 'Email is required to invite a user.' })
      return
    }
    setInviteLoading(true)
    try {
      const res = await apiClient.inviteUser({ email, name: name || email.split('@')[0], method: 'invite' })
      setSnackbarMsg({ severity: 'success', text: res.message || `Invite email sent to ${email}!` })
      setInviteName('')
      setInviteEmail('')
      await Promise.all([fetchRequests(true), fetchAccounts(true)])
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to invite user.',
      })
    } finally {
      setInviteLoading(false)
    }
  }

  const handleSuspendUser = async (e: FormEvent) => {
    e.preventDefault()
    const email = suspendEmail.trim().toLowerCase()
    if (!email) {
      setSnackbarMsg({ severity: 'error', text: 'Email is required to suspend a user.' })
      return
    }
    if (!window.confirm(`Revoke access and block future logins for ${email}?`)) return
    setSuspendLoading(true)
    try {
      const res = await apiClient.suspendUser(email)
      setSnackbarMsg({ severity: 'info', text: res.message || `User ${email} access suspended.` })
      setSuspendEmail('')
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to suspend user.',
      })
    } finally {
      setSuspendLoading(false)
    }
  }

  const updateAccountDraft = (
    userId: string,
    field: 'status' | 'role',
    value: AppUser['status'] | AppUser['role']
  ) => {
    setAccountDrafts((prev) => ({
      ...prev,
      [userId]: {
        ...(prev[userId] || { status: 'pending', role: 'user' }),
        [field]: value,
      },
    }))
  }

  const handleSaveAccount = async (userId: string) => {
    const draft = accountDrafts[userId]
    if (!draft) return
    setSavingUserId(userId)
    try {
      await apiClient.updateAppUser(userId, { status: draft.status, role: draft.role })
      setSnackbarMsg({ severity: 'success', text: 'User account updated successfully.' })
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to update user account.',
      })
    } finally {
      setSavingUserId(null)
    }
  }

  const handleQuickActivate = async (user: AppUser) => {
    setSavingUserId(user.user_id)
    try {
      await apiClient.updateAppUser(user.user_id, { status: 'active' })
      setSnackbarMsg({ severity: 'success', text: `Account for ${user.email || user.user_id} activated!` })
      await fetchAccounts(true)
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to activate user account.',
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
    setDeleteLoading(true)
    try {
      const res = await apiClient.deleteAppUser(deleteTarget.user_id)
      setSnackbarMsg({
        severity: 'info',
        text: res.message || `Deleted account for ${deleteTarget.email || deleteTarget.user_id}.`,
      })
      setDeleteTarget(null)
      setDeleteConfirm('')
      await Promise.all([fetchAccounts(true), fetchRequests(true)])
    } catch (err: any) {
      setSnackbarMsg({
        severity: 'error',
        text: err?.response?.data?.detail || err?.message || 'Failed to delete user account.',
      })
    } finally {
      setDeleteLoading(false)
    }
  }

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const filteredRequests = useMemo(() => {
    return requests.filter((r) => {
      const q = searchQuery.toLowerCase().trim()
      const matchesSearch =
        !q ||
        r.name.toLowerCase().includes(q) ||
        r.email.toLowerCase().includes(q) ||
        r.notes.toLowerCase().includes(q) ||
        r.investor_type.toLowerCase().includes(q)
      const currentNorm = normalizeStatus(r.status)
      const matchesFilter = statusFilter === 'all' || currentNorm === statusFilter
      return matchesSearch && matchesFilter
    })
  }, [requests, searchQuery, statusFilter])

  const stats = useMemo(() => {
    const total = requests.length
    const pending = requests.filter((r) => normalizeStatus(r.status) === 'pending').length
    const approved = requests.filter((r) => normalizeStatus(r.status) === 'approved').length
    return { total, pending, approved }
  }, [requests])

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
              <AdminPanelSettingsIcon sx={{ fontSize: 28 }} />
            </Box>
            <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '-0.02em' }}>
              Admin Operations Cockpit
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ color: '#94A3B8' }}>
            User provisioning, access control, and AMFI mutual fund market disclosure synchronization.
          </Typography>
        </Box>

        <Button
          variant="outlined"
          startIcon={refreshing || accountsRefreshing || mfStatusLoading ? <CircularProgress size={16} sx={{ color: '#38BDF8' }} /> : <RefreshIcon />}
          onClick={() => {
            if (mainTab === 'access') fetchRequests(true)
            else if (mainTab === 'users') fetchAccounts(true)
            else fetchMfData()
          }}
          sx={{
            borderRadius: '12px',
            borderColor: 'rgba(255,255,255,0.1)',
            color: '#E2E8F0',
            textTransform: 'none',
            fontWeight: 600,
            '&:hover': { borderColor: '#38BDF8', bgcolor: 'rgba(56,189,248,0.05)' }
          }}
        >
          Refresh Data
        </Button>
      </Box>

      {/* Main Section Navigation Bar */}
      <Paper sx={{ p: 0.75, mb: 3.5, borderRadius: '16px', bgcolor: 'rgba(15, 23, 42, 0.75)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)' }}>
        <Tabs
          value={mainTab}
          onChange={(_, val) => setMainTab(val)}
          sx={{
            minHeight: 44,
            '& .MuiTab-root': {
              minHeight: 44,
              px: 3,
              borderRadius: '12px',
              color: '#94A3B8',
              fontWeight: 700,
              textTransform: 'none',
              fontSize: '0.9rem',
              transition: 'all 0.2s ease',
              '&.Mui-selected': { color: '#F8FAFC', bgcolor: 'rgba(56, 189, 248, 0.15)', border: '1px solid rgba(56, 189, 248, 0.3)' }
            },
            '& .MuiTabs-indicator': { display: 'none' }
          }}
        >
          <Tab value="access" icon={<PersonAddAlt1Icon sx={{ fontSize: 18, mr: 1 }} />} iconPosition="start" label={`Access Requests (${stats.pending} pending)`} />
          <Tab value="users" icon={<PersonIcon sx={{ fontSize: 18, mr: 1 }} />} iconPosition="start" label={`User Accounts (${accountStats.total})`} />
          <Tab
            value="market-data"
            icon={<StorageIcon sx={{ fontSize: 18, mr: 1 }} />}
            iconPosition="start"
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <span>Market Data / MF Sync</span>
                <Chip label="AMFI DB" size="small" sx={{ bgcolor: 'rgba(16, 185, 129, 0.2)', color: '#10B981', fontWeight: 800, fontSize: '0.68rem', height: 20 }} />
              </Box>
            }
          />
        </Tabs>
      </Paper>

      {/* ──────────────────────────────────────────────────────────────────────────
          SECTION 1: ACCESS REQUESTS
      ────────────────────────────────────────────────────────────────────────── */}
      {mainTab === 'access' && (
        <Box>
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
                  <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>Invite User</Typography>
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
                  <Grid item xs={12} sm={2}>
                    <Button
                      type="submit"
                      fullWidth
                      variant="contained"
                      disabled={inviteLoading}
                      startIcon={inviteLoading ? <CircularProgress size={16} color="inherit" /> : <SendIcon />}
                      sx={{ height: 40, borderRadius: '12px', bgcolor: '#38BDF8', textTransform: 'none', fontWeight: 700, '&:hover': { bgcolor: '#0284C7' } }}
                    >
                      Invite
                    </Button>
                  </Grid>
                </Grid>
              </Paper>
            </Grid>

            <Grid item xs={12} md={4}>
              <Paper
                component="form"
                onSubmit={handleSuspendUser}
                sx={{ p: 2.5, borderRadius: '18px', bgcolor: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                  <BlockIcon sx={{ color: '#EF4444', fontSize: 20 }} />
                  <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>Revoke Access</Typography>
                </Box>
                <TextField
                  size="small"
                  fullWidth
                  label="Email to suspend"
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
                  Suspend Access
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
                placeholder="Search leads..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ color: '#64748B', fontSize: 19 }} />
                    </InputAdornment>
                  )
                }}
                sx={{ ...adminFieldSx, minWidth: { xs: '100%', md: 280 } }}
              />
            </Box>
          </Paper>

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
                    PROFILE
                  </TableCell>
                  <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    INTENDED USE
                  </TableCell>
                  <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    SUBMITTED
                  </TableCell>
                  <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    STATUS
                  </TableCell>
                  <TableCell align="right" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.76rem', letterSpacing: '0.08em', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                    ACTIONS
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} align="center" sx={{ py: 8 }}>
                      <CircularProgress size={32} sx={{ color: '#38BDF8' }} />
                      <Typography variant="body2" sx={{ color: '#94A3B8', mt: 2 }}>
                        Loading submitted access requests...
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
                        {searchQuery ? 'Try adjusting your search criteria.' : 'Pending submissions will appear here.'}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredRequests.map((req) => {
                    const profileMeta = PROFILE_COLORS[req.investor_type] || PROFILE_COLORS.individual
                    const normStatus = normalizeStatus(req.status)
                    const isApproved = normStatus === 'approved'

                    return (
                      <TableRow
                        key={req.id}
                        sx={{
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' },
                          borderBottom: '1px solid rgba(255,255,255,0.04)',
                          transition: 'background 0.2s'
                        }}
                      >
                        <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                            <Box sx={{ width: 36, height: 36, borderRadius: '10px', bgcolor: profileMeta.bg, color: profileMeta.color, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '0.9rem' }}>
                              {req.name.charAt(0).toUpperCase()}
                            </Box>
                            <Box>
                              <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.92rem' }}>
                                {req.name}
                              </Typography>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.2 }}>
                                <Typography sx={{ color: '#94A3B8', fontSize: '0.78rem' }}>
                                  {req.email}
                                </Typography>
                                <Tooltip title={copiedId === req.id ? 'Copied!' : 'Copy Email'} arrow>
                                  <IconButton size="small" onClick={() => handleCopy(req.id, req.email)} sx={{ p: 0.2, color: '#64748B', '&:hover': { color: '#38BDF8' } }}>
                                    {copiedId === req.id ? <CheckIcon sx={{ fontSize: 13, color: '#10B981' }} /> : <ContentCopyIcon sx={{ fontSize: 13 }} />}
                                  </IconButton>
                                </Tooltip>
                              </Box>
                            </Box>
                          </Box>
                        </TableCell>

                        <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                          <Chip
                            label={profileMeta.label}
                            size="small"
                            sx={{
                              bgcolor: profileMeta.bg,
                              color: profileMeta.color,
                              fontWeight: 700,
                              fontSize: '0.72rem',
                              borderRadius: '8px',
                              border: `1px solid ${profileMeta.color}33`
                            }}
                          />
                        </TableCell>

                        <TableCell sx={{ borderBottom: 'none', py: 2, maxWidth: 260 }}>
                          <Typography sx={{ color: '#CBD5E1', fontSize: '0.82rem', lineHeight: 1.4 }} noWrap title={req.notes}>
                            {req.notes || '—'}
                          </Typography>
                        </TableCell>

                        <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                          <Typography sx={{ color: '#94A3B8', fontSize: '0.82rem' }}>
                            {req.created_at ? new Date(req.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                          </Typography>
                        </TableCell>

                        <TableCell sx={{ borderBottom: 'none', py: 2 }}>
                          <Chip
                            label={isApproved ? 'Approved' : 'Pending'}
                            size="small"
                            sx={{
                              bgcolor: isApproved ? 'rgba(16, 185, 129, 0.1)' : 'rgba(245, 158, 11, 0.1)',
                              color: isApproved ? '#10B981' : '#F59E0B',
                              fontWeight: 800,
                              fontSize: '0.72rem',
                              borderRadius: '8px',
                              border: isApproved ? '1px solid rgba(16, 185, 129, 0.2)' : '1px solid rgba(245, 158, 11, 0.2)'
                            }}
                          />
                        </TableCell>

                        <TableCell align="right" sx={{ borderBottom: 'none', py: 2 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                            {!isApproved ? (
                              <>
                                <Button
                                  size="small"
                                  variant="contained"
                                  startIcon={<SendIcon sx={{ fontSize: 13 }} />}
                                  onClick={() => handleApprove(req)}
                                  disabled={actionLoading}
                                  sx={{
                                    bgcolor: '#10B981',
                                    color: '#fff',
                                    borderRadius: '10px',
                                    textTransform: 'none',
                                    fontWeight: 700,
                                    fontSize: '0.78rem',
                                    '&:hover': { bgcolor: '#059669' }
                                  }}
                                >
                                  Invite
                                </Button>
                                <IconButton
                                  size="small"
                                  onClick={() => handleReject(req)}
                                  disabled={actionLoading}
                                  sx={{ color: '#64748B', '&:hover': { color: '#EF4444' } }}
                                >
                                  <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                                </IconButton>
                              </>
                            ) : (
                              <Button
                                size="small"
                                variant="outlined"
                                startIcon={<RefreshIcon sx={{ fontSize: 13 }} />}
                                onClick={() => handleApprove(req)}
                                disabled={actionLoading}
                                sx={{
                                  borderColor: 'rgba(56, 189, 248, 0.3)',
                                  color: '#38BDF8',
                                  borderRadius: '10px',
                                  textTransform: 'none',
                                  fontWeight: 700,
                                  fontSize: '0.75rem',
                                  '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.05)', borderColor: '#38BDF8' }
                                }}
                              >
                                Re-send Invite
                              </Button>
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
        </Box>
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          SECTION 2: USER ACCOUNTS & ROLES
      ────────────────────────────────────────────────────────────────────────── */}
      {mainTab === 'users' && (
        <Box>
          {/* User accounts stats */}
          <Paper sx={{ p: 2.5, mb: 3, borderRadius: '20px', bgcolor: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(255,255,255,0.08)', backdropFilter: 'blur(16px)' }}>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={6} sm={3}>
                <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700 }}>TOTAL ACCOUNTS</Typography>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', mt: 0.3 }}>{accountStats.total}</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700 }}>ACTIVE</Typography>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#10B981', mt: 0.3 }}>{accountStats.active}</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="caption" sx={{ color: '#F59E0B', fontWeight: 700 }}>PENDING</Typography>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#F59E0B', mt: 0.3 }}>{accountStats.pending}</Typography>
              </Grid>
              <Grid item xs={6} sm={3}>
                <Typography variant="caption" sx={{ color: '#38BDF8', fontWeight: 700 }}>ADMINS</Typography>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#38BDF8', mt: 0.3 }}>{accountStats.admins}</Typography>
              </Grid>
            </Grid>

            <TextField
              size="small"
              fullWidth
              placeholder="Search accounts by email or user id..."
              value={accountSearch}
              onChange={(e) => setAccountSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon sx={{ color: '#64748B', fontSize: 19 }} />
                  </InputAdornment>
                ),
              }}
              sx={adminFieldSx}
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
      )}

      {/* ──────────────────────────────────────────────────────────────────────────
          SECTION 3: MARKET DATA & MF DISCLOSURES SYNC (✨ NEW)
      ────────────────────────────────────────────────────────────────────────── */}
      {/* ──────────────────────────────────────────────────────────────────────────
          SECTION 3: MARKET DATA & MF DISCLOSURES SYNC (✨ MODERN REFINED)
      ────────────────────────────────────────────────────────────────────────── */}
      {mainTab === 'market-data' && (
        <Box>
          {/* Top Sync Trigger & Controls Banner */}
          <Paper
            sx={{
              p: 3.5,
              mb: 3.5,
              borderRadius: '24px',
              background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.85) 100%)',
              border: '1px solid rgba(56, 189, 248, 0.28)',
              boxShadow: '0 12px 40px rgba(0, 0, 0, 0.4), 0 0 20px rgba(56, 189, 248, 0.08)',
              backdropFilter: 'blur(24px)',
            }}
          >
            <Grid container spacing={3} alignItems="flex-start">
              <Grid item xs={12} lg={7}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1.2 }}>
                  <Box sx={{ p: 1.2, borderRadius: '12px', bgcolor: 'rgba(56, 189, 248, 0.15)', color: '#38BDF8' }}>
                    <SyncIcon sx={{ fontSize: 26 }} />
                  </Box>
                  <Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="h6" sx={{ fontWeight: 800, color: '#F8FAFC', letterSpacing: '-0.02em' }}>
                        AMFI Mutual Fund Portfolio Snapshot Engine
                      </Typography>
                      <Chip
                        label="MONTHLY DISCLOSURES"
                        size="small"
                        sx={{
                          height: 20,
                          fontSize: '0.65rem',
                          fontWeight: 800,
                          bgcolor: 'rgba(56, 189, 248, 0.15)',
                          color: '#38BDF8',
                          border: '1px solid rgba(56, 189, 248, 0.3)',
                        }}
                      />
                    </Box>
                    <Typography variant="caption" sx={{ color: '#64748B' }}>
                      Synchronizes official monthly AMC disclosures into PostgreSQL with custom ingestion scope
                    </Typography>
                  </Box>
                </Box>
                <Typography variant="body2" sx={{ color: '#94A3B8', maxWidth: 740, lineHeight: 1.6, mb: 2.5 }}>
                  Pull monthly portfolio holdings and sector weightages directly from AMFI into your database.
                  Choose a targeted AMC scope to keep database storage lightweight and queries lightning fast.
                </Typography>

                {/* Scope Selection Selector */}
                <Box sx={{ p: 2, borderRadius: '16px', bgcolor: 'rgba(2, 6, 23, 0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <Typography variant="caption" sx={{ color: '#38BDF8', fontWeight: 700, letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: 0.8, mb: 1.2 }}>
                    <TuneIcon sx={{ fontSize: 16 }} /> INGESTION SCOPE
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {[
                      { id: 'top10', label: 'Top 10 AMCs (~2.5k schemes)', desc: 'Recommended' },
                      { id: 'top5', label: 'Top 5 AMCs (~1.5k schemes)', desc: 'Lightweight' },
                      { id: 'all', label: 'All 44 AMCs (14,067 schemes)', desc: 'Full Universe' },
                      { id: 'custom', label: 'Custom AMCs', desc: `${customAmcs.length} selected` },
                    ].map((item) => {
                      const isSelected = syncScope === item.id
                      return (
                        <Button
                          key={item.id}
                          size="small"
                          onClick={() => setSyncScope(item.id as any)}
                          sx={{
                            borderRadius: '10px',
                            px: 1.8,
                            py: 0.6,
                            textTransform: 'none',
                            fontWeight: 700,
                            fontSize: '0.8rem',
                            bgcolor: isSelected ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.04)',
                            color: isSelected ? '#38BDF8' : '#94A3B8',
                            border: isSelected ? '1px solid #38BDF8' : '1px solid rgba(255, 255, 255, 0.08)',
                            '&:hover': {
                              bgcolor: isSelected ? 'rgba(56, 189, 248, 0.3)' : 'rgba(255, 255, 255, 0.08)',
                              color: '#fff',
                            },
                          }}
                        >
                          {item.label}
                        </Button>
                      )
                    })}
                  </Box>

                  {/* Collapsible Custom AMCs Selection */}
                  {syncScope === 'custom' && (
                    <Box sx={{ mt: 2, pt: 1.5, borderTop: '1px dashed rgba(255,255,255,0.1)' }}>
                      <Box sx={{ display: 'flex', gap: 1, mb: 1.5, alignItems: 'center' }}>
                        <TextField
                          size="small"
                          placeholder="Add new AMC (e.g. Zerodha, Jio, Helios, Navi)..."
                          value={newAmcInput}
                          onChange={(e) => setNewAmcInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                              const trimmed = newAmcInput.trim()
                              if (trimmed && !customAmcs.some((a) => a.toLowerCase() === trimmed.toLowerCase())) {
                                setCustomAmcs((prev) => [...prev, trimmed])
                                setNewAmcInput('')
                              }
                            }
                          }}
                          sx={{
                            flex: 1,
                            '& .MuiOutlinedInput-root': {
                              borderRadius: '10px',
                              bgcolor: 'rgba(255,255,255,0.04)',
                              color: '#F8FAFC',
                              fontSize: '0.8rem',
                              '& fieldset': { borderColor: 'rgba(255,255,255,0.12)' },
                              '&:hover fieldset': { borderColor: '#38BDF8' },
                            },
                          }}
                        />
                        <Button
                          variant="outlined"
                          size="small"
                          onClick={() => {
                            const trimmed = newAmcInput.trim()
                            if (trimmed && !customAmcs.some((a) => a.toLowerCase() === trimmed.toLowerCase())) {
                              setCustomAmcs((prev) => [...prev, trimmed])
                              setNewAmcInput('')
                            }
                          }}
                          disabled={!newAmcInput.trim()}
                          sx={{
                            borderRadius: '10px',
                            color: '#38BDF8',
                            borderColor: 'rgba(56, 189, 248, 0.4)',
                            textTransform: 'none',
                            fontWeight: 700,
                            fontSize: '0.78rem',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          + Add AMC
                        </Button>
                      </Box>

                      <Typography variant="caption" sx={{ color: '#94A3B8', display: 'block', mb: 1 }}>
                        Click to select/unselect AMCs to ingest:
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8 }}>
                        {Array.from(new Set([
                          ...customAmcs,
                          'HDFC', 'SBI', 'ICICI Prudential', 'Nippon India', 'Kotak',
                          'Axis', 'Quant', 'Parag Parikh', 'Mirae Asset', 'Tata',
                          'Groww', 'Zerodha', 'DSP', 'Bandhan', 'Canara Robeco', 'UTI',
                          'Motilal Oswal', 'Franklin Templeton', 'Aditya Birla Sun Life', 'Edelweiss', 'HSBC', 'Invesco'
                        ])).map((amc) => {
                          const active = customAmcs.includes(amc)
                          return (
                            <Chip
                              key={amc}
                              label={amc}
                              size="small"
                              onClick={() => {
                                setCustomAmcs((prev) =>
                                  prev.includes(amc) ? prev.filter((a) => a !== amc) : [...prev, amc]
                                )
                              }}
                              icon={active ? <CheckIcon sx={{ fontSize: '14px !important', color: '#38BDF8 !important' }} /> : undefined}
                              sx={{
                                fontSize: '0.75rem',
                                fontWeight: active ? 700 : 500,
                                bgcolor: active ? 'rgba(56, 189, 248, 0.18)' : 'rgba(255,255,255,0.03)',
                                color: active ? '#38BDF8' : '#64748B',
                                border: active ? '1px solid rgba(56, 189, 248, 0.4)' : '1px solid rgba(255,255,255,0.06)',
                                cursor: 'pointer',
                                '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.25)', color: '#fff' },
                              }}
                            />
                          )
                        })}
                      </Box>
                    </Box>
                  )}
                </Box>
              </Grid>

              {/* Action Buttons */}
              <Grid item xs={12} lg={5} sx={{ display: 'flex', flexDirection: 'column', alignItems: { xs: 'flex-start', lg: 'flex-end' }, gap: 1.5, mt: { xs: 1, lg: 0 } }}>
                <Button
                  variant="contained"
                  size="large"
                  onClick={handleTriggerMfSync}
                  disabled={mfTriggering || mfStatusLoading || (syncScope === 'custom' && customAmcs.length === 0)}
                  startIcon={mfTriggering ? <CircularProgress size={18} color="inherit" /> : <BoltIcon sx={{ color: '#0F172A' }} />}
                  sx={{
                    px: 3.5,
                    py: 1.4,
                    width: { xs: '100%', sm: 'auto' },
                    borderRadius: '16px',
                    bgcolor: '#38BDF8',
                    color: '#0F172A',
                    fontWeight: 800,
                    textTransform: 'none',
                    fontSize: '0.95rem',
                    boxShadow: '0 4px 24px rgba(56, 189, 248, 0.35)',
                    transition: 'all 0.2s ease-in-out',
                    '&:hover': { bgcolor: '#0284C7', color: '#fff', transform: 'translateY(-1px)', boxShadow: '0 6px 28px rgba(56, 189, 248, 0.45)' },
                  }}
                >
                  {mfTriggering ? 'Syncing Snapshots...' : `Sync ${syncScope === 'all' ? 'All AMCs' : syncScope === 'top10' ? 'Top 10 AMCs' : syncScope === 'top5' ? 'Top 5 AMCs' : `${customAmcs.length} AMCs`}`}
                </Button>

                <Button
                  variant="outlined"
                  size="medium"
                  onClick={() => setPurgeDialogOpen(true)}
                  disabled={mfTriggering || mfStatusLoading}
                  startIcon={<DeleteSweepIcon sx={{ color: '#F43F5E' }} />}
                  sx={{
                    px: 2.5,
                    py: 1.1,
                    width: { xs: '100%', sm: 'auto' },
                    borderRadius: '14px',
                    color: '#F43F5E',
                    borderColor: 'rgba(244, 63, 94, 0.35)',
                    bgcolor: 'rgba(244, 63, 94, 0.06)',
                    fontWeight: 700,
                    textTransform: 'none',
                    fontSize: '0.85rem',
                    '&:hover': {
                      borderColor: '#F43F5E',
                      bgcolor: 'rgba(244, 63, 94, 0.15)',
                      color: '#FDA4AF',
                    },
                  }}
                >
                  Database Storage & Purge
                </Button>

                {syncedAmcs.length > 0 && (
                  <Typography variant="caption" sx={{ color: '#64748B', textAlign: { xs: 'left', lg: 'right' } }}>
                    Currently loaded: <strong style={{ color: '#94A3B8' }}>{syncedAmcs.length} AMCs</strong> ({mfStatus?.total_schemes?.toLocaleString() || 0} schemes)
                  </Typography>
                )}
              </Grid>
            </Grid>
          </Paper>

          {/* Engine Operational KPI Cards */}
          <Grid container spacing={2.5} sx={{ mb: 3.5 }}>
            {/* 1. Total Schemes */}
            <Grid item xs={12} sm={6} md={3}>
              <Paper
                sx={{
                  p: 2.5,
                  borderRadius: '20px',
                  bgcolor: 'rgba(15, 23, 42, 0.65)',
                  border: '1px solid rgba(56, 189, 248, 0.15)',
                  transition: 'all 0.2s',
                  '&:hover': { borderColor: 'rgba(56, 189, 248, 0.35)', bgcolor: 'rgba(15, 23, 42, 0.8)' },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, letterSpacing: '0.04em' }}>
                    MASTER SCHEMES
                  </Typography>
                  <StorageIcon sx={{ fontSize: 20, color: '#38BDF8' }} />
                </Box>
                <Typography variant="h4" sx={{ fontWeight: 800, color: '#38BDF8', mt: 0.8 }}>
                  {mfStatusLoading ? <CircularProgress size={24} sx={{ color: '#38BDF8' }} /> : (mfStatus?.total_schemes?.toLocaleString() ?? '14,067')}
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 0.5 }}>
                  PostgreSQL Indexed Universe
                </Typography>
              </Paper>
            </Grid>

            {/* 2. Disclosure Period */}
            <Grid item xs={12} sm={6} md={3}>
              <Paper
                sx={{
                  p: 2.5,
                  borderRadius: '20px',
                  bgcolor: 'rgba(15, 23, 42, 0.65)',
                  border: '1px solid rgba(16, 185, 129, 0.15)',
                  transition: 'all 0.2s',
                  '&:hover': { borderColor: 'rgba(16, 185, 129, 0.35)', bgcolor: 'rgba(15, 23, 42, 0.8)' },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="caption" sx={{ color: '#10B981', fontWeight: 700, letterSpacing: '0.04em' }}>
                    DISCLOSURE CYCLE
                  </Typography>
                  <CheckCircleOutlineIcon sx={{ fontSize: 20, color: '#10B981' }} />
                </Box>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#10B981', mt: 1.1 }}>
                  {mfStatusLoading ? <CircularProgress size={24} sx={{ color: '#10B981' }} /> : mfStatus?.latest_portfolio_month ?? 'July 2026'}
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 0.5 }}>
                  AMFI Regulatory Disclosures
                </Typography>
              </Paper>
            </Grid>

            {/* 3. Sync Health */}
            <Grid item xs={12} sm={6} md={3}>
              <Paper
                sx={{
                  p: 2.5,
                  borderRadius: '20px',
                  bgcolor: 'rgba(15, 23, 42, 0.65)',
                  border: '1px solid rgba(168, 85, 247, 0.15)',
                  transition: 'all 0.2s',
                  '&:hover': { borderColor: 'rgba(168, 85, 247, 0.35)', bgcolor: 'rgba(15, 23, 42, 0.8)' },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="caption" sx={{ color: '#A855F7', fontWeight: 700, letterSpacing: '0.04em' }}>
                    DATABASE ENGINE
                  </Typography>
                  <SpeedIcon sx={{ fontSize: 20, color: '#A855F7' }} />
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.1 }}>
                  <Box
                    sx={{
                      width: 9,
                      height: 9,
                      borderRadius: '50%',
                      bgcolor: '#10B981',
                      boxShadow: '0 0 10px #10B981',
                    }}
                  />
                  <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC' }}>
                    Operational
                  </Typography>
                </Box>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 0.5 }}>
                  0ms Fast Factsheet Cache
                </Typography>
              </Paper>
            </Grid>

            {/* 4. Last Sync Execution */}
            <Grid item xs={12} sm={6} md={3}>
              <Paper
                sx={{
                  p: 2.5,
                  borderRadius: '20px',
                  bgcolor: 'rgba(15, 23, 42, 0.65)',
                  border: '1px solid rgba(245, 158, 11, 0.15)',
                  transition: 'all 0.2s',
                  '&:hover': { borderColor: 'rgba(245, 158, 11, 0.35)', bgcolor: 'rgba(15, 23, 42, 0.8)' },
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="caption" sx={{ color: '#F59E0B', fontWeight: 700, letterSpacing: '0.04em' }}>
                    LAST SYNC RUN
                  </Typography>
                  <SyncIcon sx={{ fontSize: 20, color: '#F59E0B' }} />
                </Box>
                <Typography variant="h5" sx={{ fontWeight: 800, color: '#F59E0B', mt: 1.1 }}>
                  {mfStatus?.recent_logs?.[0]
                    ? `${mfStatus.recent_logs[0].duration_seconds}s Speed`
                    : 'Ready'}
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B', display: 'block', mt: 0.5 }}>
                  {mfStatus?.recent_logs?.[0]?.created_at
                    ? `Synced at ${new Date(mfStatus.recent_logs[0].created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                    : 'Audit Trail Active'}
                </Typography>
              </Paper>
            </Grid>
          </Grid>

          {/* Sync Audit History */}
          <Paper sx={{ p: 2.5, mb: 3.5, borderRadius: '20px', bgcolor: 'rgba(15, 23, 42, 0.65)', border: '1px solid rgba(255,255,255,0.08)' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <StorageIcon sx={{ color: '#38BDF8', fontSize: 20 }} />
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1rem' }}>
                  Sync Audit History
                </Typography>
              </Box>
              <Typography variant="caption" sx={{ color: '#64748B' }}>
                Last 10 executions
              </Typography>
            </Box>

            <TableContainer sx={{ overflow: 'hidden' }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: 'rgba(2, 6, 23, 0.4)' }}>
                  <TableRow>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>LOG ID</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>TRIGGERED BY</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>STATUS</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>SCHEMES UPDATED</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>DURATION</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>PERIOD</TableCell>
                    <TableCell align="right" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>TIMESTAMP</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(!mfStatus?.recent_logs || mfStatus.recent_logs.length === 0) ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center" sx={{ py: 3, color: '#64748B' }}>
                        No sync logs recorded yet. Trigger a sync above to create the first audit entry.
                      </TableCell>
                    </TableRow>
                  ) : (
                    mfStatus.recent_logs.map((log) => (
                      <TableRow key={log.id} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                        <TableCell sx={{ color: '#94A3B8', fontFamily: 'monospace', fontSize: '0.8rem' }}>#{log.id}</TableCell>
                        <TableCell sx={{ color: '#F8FAFC', fontWeight: 600, fontSize: '0.82rem' }}>{log.triggered_by}</TableCell>
                        <TableCell>
                          <Chip
                            label={log.status.toUpperCase()}
                            size="small"
                            sx={{
                              height: 20,
                              fontSize: '0.68rem',
                              fontWeight: 800,
                              bgcolor: log.status === 'completed' ? 'rgba(16, 185, 129, 0.15)' : log.status === 'failed' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                              color: log.status === 'completed' ? '#10B981' : log.status === 'failed' ? '#EF4444' : '#F59E0B',
                            }}
                          />
                        </TableCell>
                        <TableCell sx={{ color: '#38BDF8', fontWeight: 700 }}>{log.schemes_updated?.toLocaleString() ?? 0}</TableCell>
                        <TableCell sx={{ color: '#CBD5E1', fontSize: '0.8rem' }}>{log.duration_seconds}s</TableCell>
                        <TableCell sx={{ color: '#94A3B8', fontSize: '0.8rem' }}>{log.portfolio_month || '—'}</TableCell>
                        <TableCell align="right" sx={{ color: '#64748B', fontSize: '0.78rem' }}>
                          {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          {/* Synced Schemes Explorer */}
          <Paper sx={{ p: 3, mb: 2, borderRadius: '22px', bgcolor: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(255,255,255,0.08)' }}>
            <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, alignItems: { xs: 'stretch', md: 'center' }, justifyContent: 'space-between', gap: 2, mb: 2.5 }}>
              <Box>
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.05rem' }}>
                  Synced Portfolio Factsheet Explorer
                </Typography>
                <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                  Instant search across all 14,067+ official AMC disclosures, sector weights, and verified holdings.
                </Typography>
              </Box>

              <TextField
                size="small"
                placeholder="Search scheme name, ISIN, or AMC..."
                value={mfSearchQuery}
                onChange={(e) => handleSearchMf(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ color: '#64748B', fontSize: 19 }} />
                    </InputAdornment>
                  ),
                }}
                sx={{ ...adminFieldSx, minWidth: { xs: '100%', md: 360 } }}
              />
            </Box>

            {/* Quick AMC & Category Filter Chips */}
            <Box sx={{ mb: 3 }}>
              {/* Category Filters */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mr: 0.5 }}>
                  <FilterListIcon sx={{ fontSize: 16, color: '#94A3B8' }} />
                  <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.72rem' }}>
                    CATEGORY:
                  </Typography>
                </Box>
                {['All', 'Large Cap', 'Flexi Cap', 'Small Cap', 'Mid Cap', 'Multi Cap', 'ELSS', 'Hybrid', 'Index', 'Debt'].map((cat) => {
                  const active = mfCategoryFilter === cat
                  return (
                    <Chip
                      key={cat}
                      label={cat === 'All' ? 'All Categories' : cat}
                      size="small"
                      onClick={() => handleSelectFilter('category', cat)}
                      sx={{
                        height: 24,
                        fontSize: '0.72rem',
                        fontWeight: active ? 800 : 500,
                        bgcolor: active ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255,255,255,0.04)',
                        color: active ? '#38BDF8' : '#94A3B8',
                        border: active ? '1px solid rgba(56, 189, 248, 0.5)' : '1px solid rgba(255,255,255,0.06)',
                        cursor: 'pointer',
                        '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.15)', color: '#38BDF8' },
                      }}
                    />
                  )
                })}
              </Box>

              {/* Top AMCs Filters */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mr: 0.5 }}>
                  <AccountBalanceIcon sx={{ fontSize: 16, color: '#94A3B8' }} />
                  <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.72rem' }}>
                    TOP AMCS:
                  </Typography>
                </Box>
                {['All', 'Groww', 'SBI', 'HDFC', 'ICICI Prudential', 'Nippon India', 'Kotak', 'Axis', 'Quant', 'Parag Parikh', 'Mirae Asset', 'Tata', 'Zerodha', 'DSP'].map((amc) => {
                  const active = mfAmcFilter === amc
                  return (
                    <Chip
                      key={amc}
                      label={amc === 'All' ? 'All AMCs' : amc}
                      size="small"
                      onClick={() => handleSelectFilter('amc', amc)}
                      sx={{
                        height: 24,
                        fontSize: '0.72rem',
                        fontWeight: active ? 800 : 500,
                        bgcolor: active ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255,255,255,0.04)',
                        color: active ? '#10B981' : '#94A3B8',
                        border: active ? '1px solid rgba(16, 185, 129, 0.5)' : '1px solid rgba(255,255,255,0.06)',
                        cursor: 'pointer',
                        '&:hover': { bgcolor: 'rgba(16, 185, 129, 0.15)', color: '#10B981' },
                      }}
                    />
                  )
                })}
              </Box>
            </Box>

            <TableContainer component={Paper} sx={{ borderRadius: '16px', bgcolor: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(255,255,255,0.06)', overflow: 'hidden' }}>
              <Table sx={{ minWidth: 800 }}>
                <TableHead sx={{ bgcolor: 'rgba(2, 6, 23, 0.5)' }}>
                  <TableRow>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>SCHEME & ISIN</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>CATEGORY</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>AUM (₹ CR)</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>RISK</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>DATA COVERAGE</TableCell>
                    <TableCell align="right" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>ACTIONS</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {mfSchemesLoading ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                        <CircularProgress size={28} sx={{ color: '#38BDF8' }} />
                        <Typography variant="body2" sx={{ color: '#94A3B8', mt: 1.5 }}>
                          Loading mutual fund disclosures...
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : mfSchemes.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                        <Typography variant="body1" sx={{ color: '#E2E8F0', fontWeight: 700 }}>
                          No mutual funds found
                        </Typography>
                        <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5 }}>
                          {mfSearchQuery ? 'Try a different search query.' : 'Click "Sync AMFI Snapshots" above to ingest schemes.'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    mfSchemes.map((scheme) => (
                      <TableRow key={scheme.isin} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                        <TableCell sx={{ py: 1.8 }}>
                          <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.88rem' }}>
                            {scheme.scheme_name}
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.3 }}>
                            <Typography sx={{ color: '#38BDF8', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                              {scheme.isin}
                            </Typography>
                            <Typography sx={{ color: '#64748B', fontSize: '0.75rem' }}>
                              • {scheme.amc}
                            </Typography>
                          </Box>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={scheme.category || 'Equity'}
                            size="small"
                            sx={{ bgcolor: 'rgba(56, 189, 248, 0.1)', color: '#38BDF8', fontWeight: 700, fontSize: '0.72rem', borderRadius: '8px' }}
                          />
                        </TableCell>
                        <TableCell sx={{ color: '#10B981', fontWeight: 800, fontSize: '0.9rem' }}>
                          {scheme.aum_formatted}
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={scheme.risk_level}
                            size="small"
                            sx={{
                              bgcolor: scheme.risk_level.includes('VERY HIGH') ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                              color: scheme.risk_level.includes('VERY HIGH') ? '#F87171' : '#F59E0B',
                              fontWeight: 800,
                              fontSize: '0.68rem',
                              borderRadius: '8px',
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" sx={{ color: '#CBD5E1', display: 'block' }}>
                            <strong>{scheme.holdings_count}</strong> holdings • <strong>{scheme.sectors_count}</strong> sectors
                          </Typography>
                          <Typography variant="caption" sx={{ color: '#64748B' }}>
                            TER: {scheme.expense_ratio ? `${scheme.expense_ratio}%` : 'N/A'}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={<VisibilityIcon sx={{ fontSize: 14 }} />}
                            onClick={() => setSelectedScheme(scheme)}
                            sx={{
                              borderRadius: '10px',
                              borderColor: 'rgba(56, 189, 248, 0.3)',
                              color: '#38BDF8',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              textTransform: 'none',
                              '&:hover': { bgcolor: 'rgba(56, 189, 248, 0.08)', borderColor: '#38BDF8' },
                            }}
                          >
                            Factsheet
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          {/* Factsheet Detailed Drawer / Modal */}
          <Dialog
            open={Boolean(selectedScheme)}
            onClose={() => setSelectedScheme(null)}
            maxWidth="md"
            fullWidth
            slotProps={{
              backdrop: { sx: { backdropFilter: 'blur(12px)', bgcolor: 'rgba(2, 6, 23, 0.75)' } },
            }}
            PaperProps={{
              sx: {
                borderRadius: '24px',
                background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
                border: '1px solid rgba(56, 189, 248, 0.3)',
                p: 2,
                color: '#fff',
              },
            }}
          >
            <DialogTitle sx={{ pb: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#F8FAFC' }}>
                    {selectedScheme?.scheme_name}
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mt: 0.5 }}>
                    <Chip label={`ISIN: ${selectedScheme?.isin}`} size="small" sx={{ bgcolor: 'rgba(56, 189, 248, 0.1)', color: '#38BDF8', fontWeight: 700, fontSize: '0.72rem' }} />
                    <Chip label={selectedScheme?.source || 'AMFI Official Disclosure'} size="small" sx={{ bgcolor: 'rgba(16, 185, 129, 0.15)', color: '#10B981', fontWeight: 700, fontSize: '0.72rem' }} />
                  </Box>
                </Box>
                <Chip
                  label={selectedScheme?.risk_level}
                  sx={{
                    bgcolor: selectedScheme?.risk_level?.includes('VERY HIGH') ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                    color: selectedScheme?.risk_level?.includes('VERY HIGH') ? '#F87171' : '#F59E0B',
                    fontWeight: 800,
                  }}
                />
              </Box>
            </DialogTitle>
            <DialogContent dividers sx={{ borderColor: 'rgba(255,255,255,0.08)' }}>
              <Grid container spacing={3} sx={{ mb: 2 }}>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>AUM</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#10B981' }}>{selectedScheme?.aum_formatted}</Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>EXPENSE RATIO (TER)</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#F8FAFC' }}>{selectedScheme?.expense_ratio ? `${selectedScheme.expense_ratio}%` : 'N/A'}</Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>PORTFOLIO DATE</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#CBD5E1' }}>{selectedScheme?.portfolio_date || 'July 2026'}</Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>CATEGORY</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#38BDF8' }}>{selectedScheme?.category}</Typography>
                </Grid>
              </Grid>

              <Grid container spacing={3}>
                {/* Holdings Column */}
                <Grid item xs={12} md={7}>
                  <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 1.5, fontSize: '0.95rem' }}>
                    Top 10 Holdings
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {selectedScheme?.holdings?.map((h, idx) => (
                      <Box key={idx} sx={{ p: 1.2, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.04)' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography sx={{ fontSize: '0.84rem', fontWeight: 600, color: '#E2E8F0' }}>
                            {idx + 1}. {h.name}
                          </Typography>
                          <Typography sx={{ fontSize: '0.84rem', fontWeight: 800, color: '#38BDF8' }}>
                            {h.pct}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, h.pct * 8)}
                          sx={{ height: 4, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.05)', '& .MuiLinearProgress-bar': { bgcolor: '#38BDF8' } }}
                        />
                      </Box>
                    ))}
                  </Box>
                </Grid>

                {/* Sectors Column */}
                <Grid item xs={12} md={5}>
                  <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 1.5, fontSize: '0.95rem' }}>
                    Sector Allocation
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {selectedScheme?.sectors?.map((s, idx) => (
                      <Box key={idx} sx={{ p: 1.2, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.04)' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Typography sx={{ fontSize: '0.84rem', fontWeight: 600, color: '#CBD5E1' }}>
                            {s.sector}
                          </Typography>
                          <Typography sx={{ fontSize: '0.84rem', fontWeight: 800, color: '#10B981' }}>
                            {s.value}%
                          </Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, s.value * 2)}
                          sx={{ height: 4, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.05)', '& .MuiLinearProgress-bar': { bgcolor: '#10B981' } }}
                        />
                      </Box>
                    ))}
                  </Box>
                </Grid>
              </Grid>
            </DialogContent>
            <DialogActions sx={{ px: 3, py: 2 }}>
              <Button onClick={() => setSelectedScheme(null)} sx={{ color: '#94A3B8', textTransform: 'none', fontWeight: 700 }}>
                Close
              </Button>
            </DialogActions>
          </Dialog>

          {/* Database Storage & Purge Safety Modal */}
          <Dialog
            open={purgeDialogOpen}
            onClose={() => !purgeLoading && setPurgeDialogOpen(false)}
            maxWidth="sm"
            fullWidth
            slotProps={{
              backdrop: { sx: { backdropFilter: 'blur(12px)', bgcolor: 'rgba(2, 6, 23, 0.75)' } },
            }}
            PaperProps={{
              sx: {
                borderRadius: '24px',
                background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
                border: '1px solid rgba(244, 63, 94, 0.35)',
                p: 1.5,
                color: '#fff',
              },
            }}
          >
            <DialogTitle sx={{ pb: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Box sx={{ p: 1, borderRadius: '12px', bgcolor: 'rgba(244, 63, 94, 0.15)', color: '#F43F5E' }}>
                  <DeleteSweepIcon sx={{ fontSize: 24 }} />
                </Box>
                <Box>
                  <Typography sx={{ fontSize: '1.2rem', fontWeight: 800, color: '#FDA4AF' }}>
                    Database Storage & Purge Engine
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                    Manage PostgreSQL mutual fund snapshot footprint and remove unwanted records
                  </Typography>
                </Box>
              </Box>
            </DialogTitle>

            <DialogContent sx={{ pt: 2 }}>
              {/* Mode selection Tabs */}
              <Box sx={{ display: 'flex', gap: 1, mb: 2.5 }}>
                <Button
                  variant={purgeMode === 'all' ? 'contained' : 'outlined'}
                  onClick={() => setPurgeMode('all')}
                  sx={{
                    flex: 1,
                    borderRadius: '12px',
                    textTransform: 'none',
                    fontWeight: 700,
                    bgcolor: purgeMode === 'all' ? 'rgba(244, 63, 94, 0.2)' : 'transparent',
                    color: purgeMode === 'all' ? '#FDA4AF' : '#94A3B8',
                    borderColor: purgeMode === 'all' ? '#F43F5E' : 'rgba(255,255,255,0.1)',
                  }}
                >
                  Purge Entire Database
                </Button>
                <Button
                  variant={purgeMode === 'amc' ? 'contained' : 'outlined'}
                  onClick={() => setPurgeMode('amc')}
                  sx={{
                    flex: 1,
                    borderRadius: '12px',
                    textTransform: 'none',
                    fontWeight: 700,
                    bgcolor: purgeMode === 'amc' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                    color: purgeMode === 'amc' ? '#38BDF8' : '#94A3B8',
                    borderColor: purgeMode === 'amc' ? '#38BDF8' : 'rgba(255,255,255,0.1)',
                  }}
                >
                  Delete Specific AMC
                </Button>
              </Box>

              {purgeMode === 'all' ? (
                <Box sx={{ p: 2, borderRadius: '16px', bgcolor: 'rgba(244, 63, 94, 0.08)', border: '1px solid rgba(244, 63, 94, 0.2)' }}>
                  <Alert severity="warning" sx={{ mb: 2, bgcolor: 'transparent', color: '#FDA4AF', p: 0 }}>
                    This will truncate the <strong>mf_portfolio_snapshots</strong> table and clear all {mfStatus?.total_schemes?.toLocaleString() || 0} fund disclosures from PostgreSQL.
                  </Alert>
                  <Typography sx={{ fontSize: '0.8rem', color: '#94A3B8', fontWeight: 700, mb: 0.8 }}>
                    TYPE <span style={{ color: '#F43F5E', fontWeight: 900 }}>PURGE</span> TO CONFIRM
                  </Typography>
                  <TextField
                    fullWidth
                    size="small"
                    value={purgeConfirmText}
                    onChange={(e) => setPurgeConfirmText(e.target.value)}
                    placeholder="PURGE"
                    sx={adminFieldSx}
                  />
                </Box>
              ) : (
                <Box sx={{ p: 2, borderRadius: '16px', bgcolor: 'rgba(2, 6, 23, 0.6)', border: '1px solid rgba(255,255,255,0.08)' }}>
                  <Typography sx={{ fontSize: '0.82rem', color: '#94A3B8', mb: 1.5 }}>
                    Select an AMC currently in your database to remove all its associated scheme records:
                  </Typography>
                  {syncedAmcs.length === 0 ? (
                    <Typography variant="body2" sx={{ color: '#64748B', fontStyle: 'italic' }}>
                      No AMCs found in the database.
                    </Typography>
                  ) : (
                    <FormControl fullWidth size="small">
                      <Select
                        value={purgeTargetAmc}
                        onChange={(e) => setPurgeTargetAmc(e.target.value)}
                        sx={{
                          bgcolor: 'rgba(255,255,255,0.05)',
                          color: '#F8FAFC',
                          borderRadius: '12px',
                          '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' },
                          '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#38BDF8' },
                          '& .MuiSvgIcon-root': { color: '#94A3B8' },
                        }}
                      >
                        {syncedAmcs.map((item) => (
                          <MenuItem key={item.amc} value={item.amc} sx={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>{item.amc}</span>
                            <span style={{ color: '#94A3B8', fontSize: '0.75rem', marginLeft: '12px' }}>({item.schemes_count} schemes)</span>
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  )}
                </Box>
              )}
            </DialogContent>

            <DialogActions sx={{ px: 3, pb: 2, pt: 1 }}>
              <Button
                onClick={() => setPurgeDialogOpen(false)}
                disabled={purgeLoading}
                sx={{ color: '#94A3B8', textTransform: 'none', fontWeight: 600 }}
              >
                Cancel
              </Button>
              <Button
                variant="contained"
                onClick={handlePurge}
                disabled={
                  purgeLoading ||
                  (purgeMode === 'all' && purgeConfirmText.trim().toUpperCase() !== 'PURGE') ||
                  (purgeMode === 'amc' && !purgeTargetAmc)
                }
                sx={{
                  borderRadius: '12px',
                  bgcolor: '#F43F5E',
                  color: '#fff',
                  fontWeight: 700,
                  textTransform: 'none',
                  px: 3,
                  '&:hover': { bgcolor: '#E11D48' },
                  '&.Mui-disabled': { bgcolor: 'rgba(244, 63, 94, 0.2)', color: 'rgba(255,255,255,0.3)' },
                }}
              >
                {purgeLoading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : purgeMode === 'all' ? 'Confirm Full Purge' : 'Delete AMC Schemes'}
              </Button>
            </DialogActions>
          </Dialog>
        </Box>
      )}

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
            Delete User Permanently
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
            {deleteLoading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Delete Forever'}
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
