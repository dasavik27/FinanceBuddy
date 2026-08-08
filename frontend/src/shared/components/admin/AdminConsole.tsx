import { useState, useEffect, useMemo, useRef, type FormEvent } from 'react'
import {
  Box, Typography, Paper, Grid, TextField, InputAdornment, Button,
  Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  IconButton, Tooltip, Dialog, DialogTitle, DialogContent, DialogActions,
  CircularProgress, Alert, Snackbar, Tabs, Tab, LinearProgress,
  FormControl, Select, MenuItem, Collapse,
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
import BoltIcon from '@mui/icons-material/Bolt'
import FilterListIcon from '@mui/icons-material/FilterList'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import DeleteSweepIcon from '@mui/icons-material/DeleteSweep'
import TuneIcon from '@mui/icons-material/Tune'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import HistoryIcon from '@mui/icons-material/History'
import { apiClient } from '../../api/client'
import { useAppStore } from '../../store/appStore'

const BUILTIN_AMCS = [
  'HDFC', 'SBI', 'ICICI Prudential', 'Nippon India', 'Kotak',
  'Axis', 'Quant', 'Parag Parikh', 'Mirae Asset', 'Tata',
  'Groww', 'Zerodha', 'DSP', 'Bandhan', 'Canara Robeco', 'UTI',
  'Motilal Oswal', 'Franklin Templeton', 'Aditya Birla Sun Life', 'Edelweiss', 'HSBC', 'Invesco',
] as const

const SCOPE_OPTIONS = [
  {
    id: 'top5' as const,
    title: 'Top 5 AMCs',
    subtitle: 'HDFC · SBI · ICICI Prudential · Nippon India · Kotak',
    estimate: '~1,500 schemes',
    badge: 'Light',
    badgeColor: '#38BDF8',
  },
  {
    id: 'top10' as const,
    title: 'Top 10 AMCs',
    subtitle: 'Top 5 plus Axis, Quant, Parag Parikh, Mirae Asset, Tata',
    estimate: '~2,500 schemes',
    badge: 'Recommended',
    badgeColor: '#10B981',
  },
  {
    id: 'custom' as const,
    title: 'Choose AMCs',
    subtitle: 'Select exactly which fund houses to ingest',
    estimate: 'You decide',
    badge: 'Flexible',
    badgeColor: '#F59E0B',
  },
  {
    id: 'all' as const,
    title: 'Full catalogue',
    subtitle: 'Every open/closed/interval scheme in the AMFI feed',
    estimate: '~10–14k schemes',
    badge: 'Heavy',
    badgeColor: '#F43F5E',
  },
]

const MF_CATEGORIES = ['All', 'Large Cap', 'Large & Mid Cap', 'Flexi Cap', 'Small Cap', 'Mid Cap', 'Multi Cap', 'ELSS', 'Hybrid', 'Index', 'Debt'] as const
const MF_AMC_FILTERS = ['All', 'Groww', 'SBI', 'HDFC', 'ICICI Prudential', 'Nippon India', 'Kotak', 'Axis', 'Quant', 'Parag Parikh', 'Mirae Asset', 'Tata', 'Zerodha', 'DSP'] as const

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
  const [mfSchemesTotal, setMfSchemesTotal] = useState(0)
  const [mfSchemesLoading, setMfSchemesLoading] = useState(false)
  const [mfSearchQuery, setMfSearchQuery] = useState('')
  const [mfAmcFilter, setMfAmcFilter] = useState<string>('All')
  const [mfCategoryFilter, setMfCategoryFilter] = useState<string>('All')
  const [selectedScheme, setSelectedScheme] = useState<MfScheme | null>(null)
  const [mfPanel, setMfPanel] = useState<'ingest' | 'explore'>('ingest')
  const [auditExpanded, setAuditExpanded] = useState(false)
  const mfSearchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Selective AMC Ingestion & Purge Controls
  const [syncScope, setSyncScope] = useState<'top10' | 'top5' | 'all' | 'custom'>('top10')
  const [customAmcs, setCustomAmcs] = useState<string[]>(['HDFC', 'SBI', 'ICICI Prudential', 'Quant', 'Parag Parikh'])
  const [newAmcInput, setNewAmcInput] = useState('')
  const [syncedAmcs, setSyncedAmcs] = useState<Array<{ amc: string; schemes_count: number; total_aum_cr: number }>>([])
  const [purgeDialogOpen, setPurgeDialogOpen] = useState(false)
  const [purgeMode, setPurgeMode] = useState<'all' | 'amc'>('amc')
  const [purgeTargetAmc, setPurgeTargetAmc] = useState<string>('')
  const [purgeConfirmText, setPurgeConfirmText] = useState('')
  const [purgeLoading, setPurgeLoading] = useState(false)

  const selectedScope = SCOPE_OPTIONS.find((s) => s.id === syncScope) || SCOPE_OPTIONS[1]
  const syncActionLabel =
    syncScope === 'all'
      ? 'Sync full catalogue'
      : syncScope === 'top10'
        ? 'Sync Top 10 AMCs'
        : syncScope === 'top5'
          ? 'Sync Top 5 AMCs'
          : `Sync ${customAmcs.length} selected AMC${customAmcs.length === 1 ? '' : 's'}`
  const lastSync = mfStatus?.recent_logs?.[0] || null

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

  const loadMfSchemes = async (
    query = mfSearchQuery,
    amc = mfAmcFilter,
    category = mfCategoryFilter,
    append = false,
    offset = 0,
  ) => {
    setMfSchemesLoading(true)
    try {
      const schemesRes = await apiClient.searchMfSchemes(
        query,
        50,
        offset,
        amc !== 'All' ? amc : undefined,
        category !== 'All' ? category : undefined,
      )
      setMfSchemes((prev) => (append ? [...prev, ...(schemesRes.schemes || [])] : schemesRes.schemes || []))
      setMfSchemesTotal(schemesRes.total || 0)
    } catch (err: any) {
      console.error(err)
    } finally {
      setMfSchemesLoading(false)
    }
  }

  const fetchMfData = async () => {
    setMfStatusLoading(true)
    setMfSchemesLoading(true)
    try {
      const [statusRes, schemesRes, amcsRes] = await Promise.all([
        apiClient.getMfSyncStatus(),
        apiClient.searchMfSchemes(
          mfSearchQuery,
          50,
          0,
          mfAmcFilter !== 'All' ? mfAmcFilter : undefined,
          mfCategoryFilter !== 'All' ? mfCategoryFilter : undefined,
        ),
        apiClient.getSyncedAmcs().catch(() => ({ amcs: [] })),
      ])
      setMfStatus(statusRes)
      setMfSchemes(schemesRes.schemes || [])
      setMfSchemesTotal(schemesRes.total || 0)
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
    if (syncScope === 'custom' && customAmcs.length === 0) {
      setSnackbarMsg({ text: 'Select at least one AMC before syncing.', severity: 'error' })
      return
    }
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
      setMfPanel('explore')
    } catch (err: any) {
      setSnackbarMsg({
        text: err?.response?.data?.detail || err?.message || 'Failed to trigger AMFI sync.',
        severity: 'error',
      })
    } finally {
      setMfTriggering(false)
    }
  }

  const addCustomAmc = () => {
    const trimmed = newAmcInput.trim()
    if (!trimmed) return
    if (customAmcs.some((a) => a.toLowerCase() === trimmed.toLowerCase())) {
      setNewAmcInput('')
      return
    }
    setCustomAmcs((prev) => [...prev, trimmed])
    setNewAmcInput('')
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

  const handleSearchMf = (q: string) => {
    setMfSearchQuery(q)
    if (mfSearchTimer.current) clearTimeout(mfSearchTimer.current)
    mfSearchTimer.current = setTimeout(() => {
      loadMfSchemes(q, mfAmcFilter, mfCategoryFilter, false, 0)
    }, 300)
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
      setMfSchemesTotal(schemesRes.total || 0)
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
    void navigator.clipboard?.writeText?.(text)
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
                <span>MF Scheme Directory</span>
                {(mfStatus?.total_schemes ?? 0) > 0 && (
                  <Chip
                    label={`${mfStatus!.total_schemes.toLocaleString()} schemes`}
                    size="small"
                    sx={{ bgcolor: 'rgba(16, 185, 129, 0.2)', color: '#10B981', fontWeight: 800, fontSize: '0.68rem', height: 20 }}
                  />
                )}
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
          SECTION 3: AMFI DATA
      ────────────────────────────────────────────────────────────────────────── */}
      {mainTab === 'market-data' && (
        <Box>
          {/* Status strip */}
          <Paper
            sx={{
              p: 2,
              mb: 2.5,
              borderRadius: '16px',
              bgcolor: 'rgba(15, 23, 42, 0.7)',
              border: '1px solid rgba(255,255,255,0.08)',
              display: 'flex',
              flexWrap: 'wrap',
              alignItems: 'center',
              gap: 2,
              justifyContent: 'space-between',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
              <Box sx={{ p: 1, borderRadius: '10px', bgcolor: 'rgba(56, 189, 248, 0.12)', color: '#38BDF8' }}>
                <SyncIcon sx={{ fontSize: 22 }} />
              </Box>
              <Box>
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.05rem', lineHeight: 1.2 }}>
                  Mutual Fund Scheme Directory
                </Typography>
                <Typography variant="caption" sx={{ color: '#64748B' }}>
                  Ingest, browse, and audit verified AMFI scheme master records
                </Typography>
              </Box>
            </Box>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                      <Chip
                        size="small"
                label={mfStatusLoading ? 'Loading…' : `${(mfStatus?.total_schemes ?? 0).toLocaleString()} schemes in DB`}
                sx={{ bgcolor: 'rgba(56, 189, 248, 0.12)', color: '#38BDF8', fontWeight: 700 }}
              />
              <Chip
                size="small"
                label={mfStatus?.latest_portfolio_month || 'No disclosure month'}
                sx={{ bgcolor: 'rgba(16, 185, 129, 0.12)', color: '#10B981', fontWeight: 700 }}
              />
              <Chip
                size="small"
                label={
                  lastSync
                    ? `Last sync: ${lastSync.status}${lastSync.created_at ? ` · ${new Date(lastSync.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}` : ''}`
                    : 'Never synced'
                }
                        sx={{
                  bgcolor:
                    lastSync?.status === 'failed'
                      ? 'rgba(239, 68, 68, 0.12)'
                      : lastSync?.status === 'completed'
                        ? 'rgba(245, 158, 11, 0.12)'
                        : 'rgba(255,255,255,0.06)',
                  color:
                    lastSync?.status === 'failed'
                      ? '#F87171'
                      : lastSync?.status === 'completed'
                        ? '#F59E0B'
                        : '#94A3B8',
                  fontWeight: 700,
                }}
              />
              <Tooltip title="Refresh status">
                <IconButton
                  size="small"
                  onClick={() => fetchMfData()}
                  disabled={mfStatusLoading || mfTriggering}
                  sx={{ color: '#94A3B8' }}
                >
                  <RefreshIcon sx={{ fontSize: 18 }} />
                </IconButton>
              </Tooltip>
                    </Box>
          </Paper>

          {/* Primary panels */}
          <Paper
            sx={{
              p: 0.75,
              mb: 2.5,
              borderRadius: '14px',
              bgcolor: 'rgba(15, 23, 42, 0.55)',
              border: '1px solid rgba(255,255,255,0.06)',
              display: 'inline-flex',
            }}
          >
            {[
              { id: 'ingest' as const, label: '1. Ingest', icon: <TuneIcon sx={{ fontSize: 16 }} /> },
              { id: 'explore' as const, label: '2. Browse schemes', icon: <SearchIcon sx={{ fontSize: 16 }} /> },
            ].map((tab) => {
              const active = mfPanel === tab.id
                      return (
                        <Button
                  key={tab.id}
                  onClick={() => setMfPanel(tab.id)}
                  startIcon={tab.icon}
                          sx={{
                    px: 2.2,
                    py: 0.9,
                            borderRadius: '10px',
                            textTransform: 'none',
                            fontWeight: 700,
                    fontSize: '0.86rem',
                    color: active ? '#F8FAFC' : '#94A3B8',
                    bgcolor: active ? 'rgba(56, 189, 248, 0.16)' : 'transparent',
                    border: active ? '1px solid rgba(56, 189, 248, 0.35)' : '1px solid transparent',
                    '&:hover': { bgcolor: active ? 'rgba(56, 189, 248, 0.22)' : 'rgba(255,255,255,0.04)', color: '#fff' },
                  }}
                >
                  {tab.label}
                        </Button>
                      )
                    })}
          </Paper>

          {/* ── Ingest panel ─────────────────────────────────────────────── */}
          {mfPanel === 'ingest' && (
            <Paper
              sx={{
                p: { xs: 2.5, md: 3.5 },
                mb: 2.5,
                borderRadius: '20px',
                bgcolor: 'rgba(15, 23, 42, 0.72)',
                border: '1px solid rgba(56, 189, 248, 0.2)',
              }}
            >
              <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.05rem', mb: 0.5 }}>
                Ingestion scope
              </Typography>
              <Typography variant="body2" sx={{ color: '#94A3B8', mb: 2.5, maxWidth: 720 }}>
                Pick how much of the AMFI catalogue to pull into PostgreSQL. Smaller scopes stay faster and lighter.
              </Typography>

              <Grid container spacing={1.5} sx={{ mb: 2.5 }}>
                {SCOPE_OPTIONS.map((opt) => {
                  const active = syncScope === opt.id
                  return (
                    <Grid item xs={12} sm={6} key={opt.id}>
                      <Box
                        role="button"
                        tabIndex={0}
                        onClick={() => setSyncScope(opt.id)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            setSyncScope(opt.id)
                          }
                        }}
                        sx={{
                          p: 2,
                          height: '100%',
                          borderRadius: '14px',
                          cursor: 'pointer',
                          bgcolor: active ? 'rgba(56, 189, 248, 0.12)' : 'rgba(2, 6, 23, 0.45)',
                          border: active ? '1.5px solid #38BDF8' : '1px solid rgba(255,255,255,0.08)',
                          transition: 'border-color 0.15s, background 0.15s',
                          outline: 'none',
                          '&:hover': {
                            borderColor: active ? '#38BDF8' : 'rgba(56, 189, 248, 0.35)',
                            bgcolor: active ? 'rgba(56, 189, 248, 0.14)' : 'rgba(255,255,255,0.03)',
                          },
                          '&:focus-visible': { boxShadow: '0 0 0 2px rgba(56, 189, 248, 0.45)' },
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 1, mb: 0.8 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Box
                              sx={{
                                width: 18,
                                height: 18,
                                borderRadius: '50%',
                                border: active ? '5px solid #38BDF8' : '2px solid #64748B',
                                bgcolor: active ? '#0F172A' : 'transparent',
                                flexShrink: 0,
                              }}
                            />
                            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '0.95rem' }}>
                              {opt.title}
                            </Typography>
                  </Box>
                          <Chip
                            size="small"
                            label={opt.badge}
                            sx={{
                              height: 22,
                              fontSize: '0.68rem',
                              fontWeight: 800,
                              bgcolor: `${opt.badgeColor}22`,
                              color: opt.badgeColor,
                              border: `1px solid ${opt.badgeColor}55`,
                            }}
                          />
                        </Box>
                        <Typography variant="body2" sx={{ color: '#94A3B8', fontSize: '0.8rem', ml: 3.5, mb: 0.6, lineHeight: 1.45 }}>
                          {opt.subtitle}
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#64748B', ml: 3.5, fontWeight: 700 }}>
                          {opt.estimate}
                        </Typography>
                      </Box>
                    </Grid>
                  )
                })}
              </Grid>

                  {syncScope === 'custom' && (
                <Box
                  sx={{
                    p: 2,
                    mb: 2.5,
                    borderRadius: '14px',
                    bgcolor: 'rgba(2, 6, 23, 0.55)',
                    border: '1px solid rgba(245, 158, 11, 0.25)',
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.2, gap: 1, flexWrap: 'wrap' }}>
                    <Typography variant="caption" sx={{ color: '#F59E0B', fontWeight: 800, letterSpacing: '0.04em' }}>
                      SELECT AMCS ({customAmcs.length} selected)
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button
                        size="small"
                        onClick={() => setCustomAmcs([...BUILTIN_AMCS])}
                        sx={{ textTransform: 'none', fontSize: '0.75rem', color: '#94A3B8', minWidth: 0 }}
                      >
                        Select all
                      </Button>
                      <Button
                        size="small"
                        onClick={() => setCustomAmcs([])}
                        sx={{ textTransform: 'none', fontSize: '0.75rem', color: '#94A3B8', minWidth: 0 }}
                      >
                        Clear
                      </Button>
                    </Box>
                  </Box>
                      <Box sx={{ display: 'flex', gap: 1, mb: 1.5, alignItems: 'center' }}>
                        <TextField
                          size="small"
                      placeholder="Add AMC name (e.g. Helios, Navi)…"
                          value={newAmcInput}
                          onChange={(e) => setNewAmcInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault()
                          addCustomAmc()
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
                          '&:hover fieldset': { borderColor: '#F59E0B' },
                            },
                          }}
                        />
                        <Button
                          variant="outlined"
                          size="small"
                      onClick={addCustomAmc}
                          disabled={!newAmcInput.trim()}
                          sx={{
                            borderRadius: '10px',
                        color: '#F59E0B',
                        borderColor: 'rgba(245, 158, 11, 0.45)',
                            textTransform: 'none',
                            fontWeight: 700,
                            whiteSpace: 'nowrap',
                          }}
                        >
                      Add
                        </Button>
                      </Box>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8 }}>
                    {Array.from(new Set([...customAmcs, ...BUILTIN_AMCS])).map((amc) => {
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
                          icon={active ? <CheckIcon sx={{ fontSize: '14px !important', color: '#F59E0B !important' }} /> : undefined}
                              sx={{
                                fontSize: '0.75rem',
                                fontWeight: active ? 700 : 500,
                            bgcolor: active ? 'rgba(245, 158, 11, 0.16)' : 'rgba(255,255,255,0.03)',
                            color: active ? '#F59E0B' : '#64748B',
                            border: active ? '1px solid rgba(245, 158, 11, 0.4)' : '1px solid rgba(255,255,255,0.06)',
                                cursor: 'pointer',
                              }}
                            />
                          )
                        })}
                      </Box>
                    </Box>
                  )}

              {/* Action summary */}
              <Box
                sx={{
                  p: 2,
                  borderRadius: '14px',
                  bgcolor: 'rgba(2, 6, 23, 0.5)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  display: 'flex',
                  flexDirection: { xs: 'column', md: 'row' },
                  alignItems: { xs: 'stretch', md: 'center' },
                  justifyContent: 'space-between',
                  gap: 2,
                }}
              >
                <Box>
                  <Typography variant="caption" sx={{ color: '#64748B', fontWeight: 700, letterSpacing: '0.04em' }}>
                    READY TO RUN
                  </Typography>
                  <Typography sx={{ color: '#F8FAFC', fontWeight: 700, mt: 0.3 }}>
                    {selectedScope.title}
                    {syncScope === 'custom' ? ` · ${customAmcs.length} AMC${customAmcs.length === 1 ? '' : 's'}` : ''}
                  </Typography>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                    {selectedScope.estimate}
                    {syncedAmcs.length > 0
                      ? ` · DB currently has ${syncedAmcs.length} AMC${syncedAmcs.length === 1 ? '' : 's'}`
                      : ''}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', gap: 1.2, flexWrap: 'wrap' }}>
                <Button
                  variant="contained"
                  onClick={handleTriggerMfSync}
                  disabled={mfTriggering || mfStatusLoading}
                    startIcon={mfTriggering ? <CircularProgress size={18} color="inherit" /> : <BoltIcon />}
                  sx={{
                      px: 3,
                      py: 1.2,
                      borderRadius: '12px',
                    bgcolor: '#38BDF8',
                    color: '#0F172A',
                    fontWeight: 800,
                    textTransform: 'none',
                      fontSize: '0.92rem',
                      boxShadow: '0 4px 20px rgba(56, 189, 248, 0.3)',
                      '&:hover': { bgcolor: '#0EA5E9', color: '#fff' },
                      '&.Mui-disabled': { bgcolor: 'rgba(56, 189, 248, 0.2)', color: 'rgba(15,23,42,0.5)' },
                    }}
                  >
                    {mfTriggering ? 'Syncing…' : syncActionLabel}
                </Button>
                <Button
                  variant="outlined"
                  onClick={() => setPurgeDialogOpen(true)}
                  disabled={mfTriggering || mfStatusLoading}
                    startIcon={<DeleteSweepIcon />}
                  sx={{
                      px: 2.2,
                    py: 1.1,
                      borderRadius: '12px',
                      color: '#F87171',
                    borderColor: 'rgba(244, 63, 94, 0.35)',
                    textTransform: 'none',
                      fontWeight: 700,
                      '&:hover': { borderColor: '#F43F5E', bgcolor: 'rgba(244, 63, 94, 0.1)' },
                    }}
                  >
                    Purge data
                </Button>
                </Box>
                </Box>

              {mfTriggering && (
                <Box sx={{ mt: 2 }}>
                  <LinearProgress
                sx={{
                      height: 4,
                      borderRadius: 2,
                      bgcolor: 'rgba(56, 189, 248, 0.12)',
                      '& .MuiLinearProgress-bar': { bgcolor: '#38BDF8' },
                    }}
                  />
                  <Typography variant="caption" sx={{ color: '#94A3B8', mt: 1, display: 'block' }}>
                    Fetching AMFI feed and upserting schemes — this can take a minute for large scopes.
                  </Typography>
                </Box>
              )}
              </Paper>
          )}

          {/* ── Explore panel ────────────────────────────────────────────── */}
          {mfPanel === 'explore' && (
              <Paper
                sx={{
                p: { xs: 2.5, md: 3 },
                mb: 2.5,
                  borderRadius: '20px',
                bgcolor: 'rgba(15, 23, 42, 0.7)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <Box
                            sx={{
                  display: 'flex',
                  flexDirection: { xs: 'column', md: 'row' },
                  alignItems: { xs: 'stretch', md: 'center' },
                  justifyContent: 'space-between',
                  gap: 2,
                  mb: 2,
                }}
              >
              <Box>
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.05rem' }}>
                    Scheme explorer
                </Typography>
                <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                    {mfSchemesLoading
                      ? 'Searching…'
                      : `${mfSchemesTotal.toLocaleString()} match${mfSchemesTotal === 1 ? '' : 'es'} · showing ${mfSchemes.length}`}
                </Typography>
              </Box>
              <TextField
                size="small"
                  placeholder="Search name, ISIN, or AMC…"
                value={mfSearchQuery}
                onChange={(e) => handleSearchMf(e.target.value)}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <SearchIcon sx={{ color: '#64748B', fontSize: 19 }} />
                    </InputAdornment>
                  ),
                }}
                  sx={{ ...adminFieldSx, minWidth: { xs: '100%', md: 340 } }}
              />
            </Box>

              <Box sx={{ mb: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1.2 }}>
                  <FilterListIcon sx={{ fontSize: 16, color: '#94A3B8' }} />
                  <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.72rem', mr: 0.5 }}>
                    CATEGORY
                  </Typography>
                  {MF_CATEGORIES.map((cat) => {
                  const active = mfCategoryFilter === cat
                  return (
                    <Chip
                      key={cat}
                        label={cat === 'All' ? 'All' : cat}
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
                      }}
                    />
                  )
                })}
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                  <AccountBalanceIcon sx={{ fontSize: 16, color: '#94A3B8' }} />
                  <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.72rem', mr: 0.5 }}>
                    AMC
                  </Typography>
                  {MF_AMC_FILTERS.map((amc) => {
                  const active = mfAmcFilter === amc
                  return (
                    <Chip
                      key={amc}
                        label={amc === 'All' ? 'All' : amc}
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
                      }}
                    />
                  )
                })}
              </Box>
            </Box>

              <TableContainer
                component={Paper}
                sx={{ borderRadius: '14px', bgcolor: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(255,255,255,0.06)', overflow: 'hidden' }}
              >
                <Table sx={{ minWidth: 760 }}>
                <TableHead sx={{ bgcolor: 'rgba(2, 6, 23, 0.5)' }}>
                  <TableRow>
                      <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>SCHEME</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>CATEGORY</TableCell>
                      <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>AUM</TableCell>
                    <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>RISK</TableCell>
                      <TableCell sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }}>COVERAGE</TableCell>
                      <TableCell align="right" sx={{ color: '#94A3B8', fontWeight: 700, fontSize: '0.74rem' }} />
                  </TableRow>
                </TableHead>
                <TableBody>
                    {mfSchemesLoading && mfSchemes.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                        <CircularProgress size={28} sx={{ color: '#38BDF8' }} />
                      </TableCell>
                    </TableRow>
                  ) : mfSchemes.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6} align="center" sx={{ py: 6 }}>
                          <Typography sx={{ color: '#E2E8F0', fontWeight: 700 }}>No schemes found</Typography>
                          <Typography variant="body2" sx={{ color: '#64748B', mt: 0.5, mb: 1.5 }}>
                            {mfSearchQuery || mfAmcFilter !== 'All' || mfCategoryFilter !== 'All'
                              ? 'Try clearing filters or searching something else.'
                              : 'Ingest an AMC scope first, then browse here.'}
                        </Typography>
                          <Button
                            size="small"
                            variant="outlined"
                            onClick={() => setMfPanel('ingest')}
                            sx={{ textTransform: 'none', borderColor: 'rgba(56,189,248,0.4)', color: '#38BDF8' }}
                          >
                            Go to Ingest
                          </Button>
                      </TableCell>
                    </TableRow>
                  ) : (
                    mfSchemes.map((scheme) => (
                      <TableRow key={scheme.isin} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.02)' } }}>
                          <TableCell sx={{ py: 1.6 }}>
                            <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '0.86rem' }}>
                            {scheme.scheme_name}
                          </Typography>
                            <Typography sx={{ color: '#64748B', fontSize: '0.74rem', mt: 0.2 }}>
                              <span style={{ color: '#38BDF8', fontFamily: 'monospace' }}>{scheme.isin}</span>
                              {' · '}{scheme.amc}
                            </Typography>
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={scheme.category || 'Equity'}
                            size="small"
                              sx={{ bgcolor: 'rgba(56, 189, 248, 0.1)', color: '#38BDF8', fontWeight: 700, fontSize: '0.7rem', borderRadius: '8px' }}
                          />
                        </TableCell>
                          <TableCell sx={{ color: '#10B981', fontWeight: 800, fontSize: '0.88rem' }}>
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
                                fontSize: '0.66rem',
                              borderRadius: '8px',
                            }}
                          />
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" sx={{ color: '#CBD5E1', display: 'block' }}>
                              {scheme.holdings_count} holdings · {scheme.sectors_count} sectors
                          </Typography>
                          <Typography variant="caption" sx={{ color: '#64748B' }}>
                              TER {scheme.expense_ratio != null ? `${scheme.expense_ratio}%` : 'N/A'}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Button
                            size="small"
                              variant="text"
                            startIcon={<VisibilityIcon sx={{ fontSize: 14 }} />}
                            onClick={() => setSelectedScheme(scheme)}
                            sx={{
                              borderRadius: '10px',
                              color: '#38BDF8',
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              textTransform: 'none',
                            }}
                          >
                              View
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>

              {mfSchemes.length < mfSchemesTotal && (
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 2 }}>
                  <Button
                    variant="outlined"
                    disabled={mfSchemesLoading}
                    onClick={() => loadMfSchemes(mfSearchQuery, mfAmcFilter, mfCategoryFilter, true, mfSchemes.length)}
                    sx={{
                      textTransform: 'none',
                      fontWeight: 700,
                      borderColor: 'rgba(255,255,255,0.12)',
                      color: '#94A3B8',
                      borderRadius: '10px',
                    }}
                  >
                    {mfSchemesLoading ? 'Loading…' : `Load more (${mfSchemesTotal - mfSchemes.length} remaining)`}
                  </Button>
                </Box>
              )}
          </Paper>
          )}

          {/* Audit — collapsed by default, lowest priority */}
          <Paper
            sx={{
              mb: 2,
              borderRadius: '14px',
              bgcolor: 'rgba(15, 23, 42, 0.45)',
              border: '1px solid rgba(255,255,255,0.05)',
              overflow: 'hidden',
            }}
          >
            <Button
              fullWidth
              onClick={() => setAuditExpanded((v) => !v)}
              endIcon={auditExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
              startIcon={<HistoryIcon sx={{ fontSize: 18 }} />}
              sx={{
                justifyContent: 'space-between',
                px: 2,
                py: 1.25,
                color: '#64748B',
                textTransform: 'none',
                fontWeight: 600,
                fontSize: '0.82rem',
                '&:hover': { bgcolor: 'rgba(255,255,255,0.03)', color: '#94A3B8' },
              }}
            >
              <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                Sync history
                <Chip
                  size="small"
                  label={`${mfStatus?.recent_logs?.length ?? 0} recent`}
                  sx={{ height: 20, fontSize: '0.65rem', bgcolor: 'rgba(255,255,255,0.06)', color: '#64748B' }}
                />
              </Box>
            </Button>
            <Collapse in={auditExpanded}>
              <Box sx={{ px: 2, pb: 2 }}>
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.7rem' }}>WHEN</TableCell>
                        <TableCell sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.7rem' }}>BY</TableCell>
                        <TableCell sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.7rem' }}>STATUS</TableCell>
                        <TableCell sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.7rem' }}>SCHEMES</TableCell>
                        <TableCell sx={{ color: '#64748B', fontWeight: 700, fontSize: '0.7rem' }}>DURATION</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(!mfStatus?.recent_logs || mfStatus.recent_logs.length === 0) ? (
                        <TableRow>
                          <TableCell colSpan={5} sx={{ color: '#64748B', py: 2 }}>
                            No sync runs yet.
                          </TableCell>
                        </TableRow>
                      ) : (
                        mfStatus.recent_logs.map((log) => (
                          <TableRow key={log.id}>
                            <TableCell sx={{ color: '#94A3B8', fontSize: '0.78rem' }}>
                              {log.created_at ? new Date(log.created_at).toLocaleString() : '—'}
                            </TableCell>
                            <TableCell sx={{ color: '#CBD5E1', fontSize: '0.78rem' }}>{log.triggered_by}</TableCell>
                            <TableCell>
                              <Chip
                                label={log.status}
                                size="small"
                                sx={{
                                  height: 20,
                                  fontSize: '0.66rem',
                                  fontWeight: 700,
                                  bgcolor:
                                    log.status === 'completed'
                                      ? 'rgba(16, 185, 129, 0.12)'
                                      : log.status === 'failed'
                                        ? 'rgba(239, 68, 68, 0.12)'
                                        : 'rgba(245, 158, 11, 0.12)',
                                  color:
                                    log.status === 'completed'
                                      ? '#10B981'
                                      : log.status === 'failed'
                                        ? '#EF4444'
                                        : '#F59E0B',
                                }}
                              />
                            </TableCell>
                            <TableCell sx={{ color: '#94A3B8', fontSize: '0.78rem' }}>
                              {log.schemes_updated?.toLocaleString() ?? 0}
                            </TableCell>
                            <TableCell sx={{ color: '#64748B', fontSize: '0.78rem' }}>
                              {log.duration_seconds}s
                              {log.error_message ? (
                                <Tooltip title={log.error_message}>
                                  <Typography component="span" sx={{ color: '#F87171', ml: 1, fontSize: '0.72rem', cursor: 'help' }}>
                                    error
                                  </Typography>
                                </Tooltip>
                              ) : null}
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            </Collapse>
          </Paper>

          {/* Factsheet modal */}
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
                borderRadius: '20px',
                background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
                border: '1px solid rgba(56, 189, 248, 0.25)',
                p: 1.5,
                color: '#fff',
              },
            }}
          >
            <DialogTitle sx={{ pb: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 2 }}>
                <Box>
                  <Typography variant="h6" sx={{ fontWeight: 800, color: '#F8FAFC' }}>
                    {selectedScheme?.scheme_name}
                  </Typography>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.8, flexWrap: 'wrap' }}>
                    <Chip label={selectedScheme?.isin} size="small" sx={{ bgcolor: 'rgba(56, 189, 248, 0.1)', color: '#38BDF8', fontWeight: 700, fontSize: '0.7rem' }} />
                    <Chip label={selectedScheme?.amc} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.06)', color: '#94A3B8', fontWeight: 600, fontSize: '0.7rem' }} />
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
              <Grid container spacing={2} sx={{ mb: 2.5 }}>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>AUM</Typography>
                  <Typography sx={{ fontWeight: 800, color: '#10B981', fontSize: '1.05rem' }}>{selectedScheme?.aum_formatted}</Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>TER</Typography>
                  <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.05rem' }}>
                    {selectedScheme?.expense_ratio != null ? `${selectedScheme.expense_ratio}%` : 'N/A'}
                  </Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>PORTFOLIO DATE</Typography>
                  <Typography sx={{ fontWeight: 800, color: '#CBD5E1', fontSize: '1.05rem' }}>
                    {selectedScheme?.portfolio_date || '—'}
                  </Typography>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>CATEGORY</Typography>
                  <Typography sx={{ fontWeight: 800, color: '#38BDF8', fontSize: '1.05rem' }}>{selectedScheme?.category}</Typography>
                </Grid>
              </Grid>

              <Grid container spacing={3}>
                <Grid item xs={12} md={7}>
                  <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 1.2, fontSize: '0.92rem' }}>
                    Top holdings
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {selectedScheme?.holdings?.map((h, idx) => (
                      <Box key={idx} sx={{ p: 1.1, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.03)' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.4 }}>
                          <Typography sx={{ fontSize: '0.82rem', fontWeight: 600, color: '#E2E8F0' }}>
                            {idx + 1}. {h.name}
                          </Typography>
                          <Typography sx={{ fontSize: '0.82rem', fontWeight: 800, color: '#38BDF8' }}>{h.pct}%</Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, h.pct * 8)}
                          sx={{ height: 3, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.05)', '& .MuiLinearProgress-bar': { bgcolor: '#38BDF8' } }}
                        />
                      </Box>
                    ))}
                  </Box>
                </Grid>
                <Grid item xs={12} md={5}>
                  <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 1.2, fontSize: '0.92rem' }}>
                    Sector allocation
                  </Typography>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                    {selectedScheme?.sectors?.map((s, idx) => (
                      <Box key={idx} sx={{ p: 1.1, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.03)' }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.4 }}>
                          <Typography sx={{ fontSize: '0.82rem', fontWeight: 600, color: '#CBD5E1' }}>{s.sector}</Typography>
                          <Typography sx={{ fontSize: '0.82rem', fontWeight: 800, color: '#10B981' }}>{s.value}%</Typography>
                        </Box>
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(100, s.value * 2)}
                          sx={{ height: 3, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.05)', '& .MuiLinearProgress-bar': { bgcolor: '#10B981' } }}
                        />
                      </Box>
                    ))}
                  </Box>
                </Grid>
              </Grid>
            </DialogContent>
            <DialogActions sx={{ px: 3, py: 1.5 }}>
              <Button onClick={() => setSelectedScheme(null)} sx={{ color: '#94A3B8', textTransform: 'none', fontWeight: 700 }}>
                Close
              </Button>
            </DialogActions>
          </Dialog>

          {/* Purge dialog */}
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
                borderRadius: '20px',
                background: 'linear-gradient(180deg, #0F172A 0%, #0B132B 100%)',
                border: '1px solid rgba(244, 63, 94, 0.3)',
                p: 1.5,
                color: '#fff',
              },
            }}
          >
            <DialogTitle sx={{ pb: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Box sx={{ p: 1, borderRadius: '10px', bgcolor: 'rgba(244, 63, 94, 0.15)', color: '#F43F5E' }}>
                  <DeleteSweepIcon sx={{ fontSize: 22 }} />
                </Box>
                <Box>
                  <Typography sx={{ fontSize: '1.1rem', fontWeight: 800, color: '#FDA4AF' }}>Purge snapshot data</Typography>
                  <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                    Remove schemes from PostgreSQL. This cannot be undone.
                  </Typography>
                </Box>
              </Box>
            </DialogTitle>

            <DialogContent sx={{ pt: 2 }}>
              <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                <Button
                  variant={purgeMode === 'amc' ? 'contained' : 'outlined'}
                  onClick={() => setPurgeMode('amc')}
                  sx={{
                    flex: 1,
                    borderRadius: '10px',
                    textTransform: 'none',
                    fontWeight: 700,
                    bgcolor: purgeMode === 'amc' ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                    color: purgeMode === 'amc' ? '#38BDF8' : '#94A3B8',
                    borderColor: purgeMode === 'amc' ? '#38BDF8' : 'rgba(255,255,255,0.1)',
                  }}
                >
                  One AMC
                </Button>
                <Button
                  variant={purgeMode === 'all' ? 'contained' : 'outlined'}
                  onClick={() => setPurgeMode('all')}
                  sx={{
                    flex: 1,
                    borderRadius: '10px',
                    textTransform: 'none',
                    fontWeight: 700,
                    bgcolor: purgeMode === 'all' ? 'rgba(244, 63, 94, 0.2)' : 'transparent',
                    color: purgeMode === 'all' ? '#FDA4AF' : '#94A3B8',
                    borderColor: purgeMode === 'all' ? '#F43F5E' : 'rgba(255,255,255,0.1)',
                  }}
                >
                  Everything
                </Button>
              </Box>

              {purgeMode === 'all' ? (
                <Box sx={{ p: 2, borderRadius: '14px', bgcolor: 'rgba(244, 63, 94, 0.08)', border: '1px solid rgba(244, 63, 94, 0.2)' }}>
                  <Alert severity="warning" sx={{ mb: 2, bgcolor: 'transparent', color: '#FDA4AF', p: 0 }}>
                    Deletes all {(mfStatus?.total_schemes ?? 0).toLocaleString()} schemes. Seed data is not restored automatically.
                  </Alert>
                  <Typography sx={{ fontSize: '0.78rem', color: '#94A3B8', fontWeight: 700, mb: 0.8 }}>
                    Type <span style={{ color: '#F43F5E', fontWeight: 900 }}>PURGE</span> to confirm
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
                <Box sx={{ p: 2, borderRadius: '14px', bgcolor: 'rgba(2, 6, 23, 0.55)', border: '1px solid rgba(255,255,255,0.08)' }}>
                  <Typography sx={{ fontSize: '0.82rem', color: '#94A3B8', mb: 1.2 }}>
                    Choose an AMC currently in the database:
                  </Typography>
                  {syncedAmcs.length === 0 ? (
                    <Typography variant="body2" sx={{ color: '#64748B' }}>No AMCs in the database.</Typography>
                  ) : (
                    <FormControl fullWidth size="small">
                      <Select
                        value={purgeTargetAmc}
                        onChange={(e) => setPurgeTargetAmc(e.target.value)}
                        sx={{
                          bgcolor: 'rgba(255,255,255,0.05)',
                          color: '#F8FAFC',
                          borderRadius: '10px',
                          '& .MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(255,255,255,0.15)' },
                          '& .MuiSvgIcon-root': { color: '#94A3B8' },
                        }}
                      >
                        {syncedAmcs.map((item) => (
                          <MenuItem key={item.amc} value={item.amc}>
                            {item.amc}
                            <Typography component="span" sx={{ color: '#64748B', fontSize: '0.75rem', ml: 1 }}>
                              ({item.schemes_count})
                            </Typography>
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
                disabled={purgeLoading}
                sx={{
                  borderRadius: '10px',
                  bgcolor: '#F43F5E',
                  color: '#fff',
                  fontWeight: 700,
                  textTransform: 'none',
                  px: 2.5,
                  '&:hover': { bgcolor: '#E11D48' },
                  '&.Mui-disabled': { bgcolor: 'rgba(244, 63, 94, 0.2)', color: 'rgba(255,255,255,0.3)' },
                }}
              >
                {purgeLoading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : purgeMode === 'all' ? 'Purge all' : 'Purge AMC'}
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
