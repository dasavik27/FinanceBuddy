import { useCallback, useMemo, useState } from 'react'
import {
  Box, Typography, Button, CircularProgress, Card, Grid,
  Tabs, Tab, Chip, Stack, LinearProgress, Divider, TextField,
  InputAdornment, IconButton, Select, MenuItem, FormControl,
  Popover, Badge
} from '@mui/material'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import SavingsIcon from '@mui/icons-material/Savings'
import HistoryIcon from '@mui/icons-material/History'
import LayersIcon from '@mui/icons-material/Layers'
import DescriptionIcon from '@mui/icons-material/Description'
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward'
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward'
import StorefrontIcon from '@mui/icons-material/Storefront'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import LocalFireDepartmentIcon from '@mui/icons-material/LocalFireDepartment'
import TodayIcon from '@mui/icons-material/Today'
import SearchIcon from '@mui/icons-material/Search'
import ClearIcon from '@mui/icons-material/Clear'
import QrCodeIcon from '@mui/icons-material/QrCode'
import LocalAtmIcon from '@mui/icons-material/LocalAtm'
import AutorenewIcon from '@mui/icons-material/Autorenew'
import RestartAltIcon from '@mui/icons-material/RestartAlt'
import CloseIcon from '@mui/icons-material/Close'
import TuneIcon from '@mui/icons-material/Tune'
import PieChartIcon from '@mui/icons-material/PieChart'
import ArrowBackIcon from '@mui/icons-material/ArrowBack'
import {
  budgetErrorDetail, budgetErrorStatus, useBudgetCategories, useBudgetOverview,
  useBudgetSessions, useBudgetTransactions, useDeleteBudgetSession,
  useInvalidateBudgetAnalytics, useResetSessionOnMissing, useUploadStatement,
  TRANSACTIONS_PAGE_SIZE,
} from '../hooks/useBudget'
import { useDebounce } from '../../../shared/hooks/useDebounce'
import type {
  BudgetCategoriesResponse, BudgetCategorySlice, BudgetFilters, BudgetTransaction,
} from '../types'
import {
  PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend, AreaChart, Area
} from 'recharts'
import TransactionsTab from './TransactionsTab'
import RulesTab from './RulesTab'
import AccountsTab from './AccountsTab'
import InsightsTab from './InsightsTab'
import MoneyFlowCard from './MoneyFlowCard'
import TransfersExcludedCard from './TransfersExcludedCard'
import BudgetSessionsModal from './BudgetSessionsModal'
import UploadStatementModal from './UploadStatementModal'
import BudgetHealth503020Card from './BudgetHealth503020Card'

const CATEGORY_COLORS = [
  '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
  '#ec4899', '#06b6d4', '#84cc16', '#3b82f6', '#f97316'
]

/** Donut slices before the tail is merged into "Other". One per CATEGORY_COLORS entry,
 *  so no two slices ever share a colour. */
const DONUT_SLICES = CATEGORY_COLORS.length

/** The merged tail. Deliberately neutral so it does not read as a category. */
const OTHER_COLOR = '#64748b'

const MERCHANT_COLORS = [
  '#38bdf8', '#fbbf24', '#f472b6', '#a78bfa', '#34d399', 
  '#fb7185', '#818cf8', '#2dd4bf', '#fca5a5', '#c084fc'
]

const BANK_COLOR_MAP: Record<string, { bg: string, border: string, text: string }> = {
  HDFC: { bg: 'rgba(0, 75, 141, 0.15)', border: 'rgba(0, 75, 141, 0.4)', text: '#60a5fa' },
  ICICI: { bg: 'rgba(179, 39, 44, 0.15)', border: 'rgba(179, 39, 44, 0.4)', text: '#f87171' },
  SBI: { bg: 'rgba(40, 56, 144, 0.15)', border: 'rgba(40, 56, 144, 0.4)', text: '#38bdf8' },
  AXIS: { bg: 'rgba(151, 18, 74, 0.15)', border: 'rgba(151, 18, 74, 0.4)', text: '#f472b6' },
  KOTAK: { bg: 'rgba(237, 28, 36, 0.15)', border: 'rgba(237, 28, 36, 0.4)', text: '#fb7185' },
  GENERIC: { bg: 'rgba(100, 116, 139, 0.15)', border: 'rgba(100, 116, 139, 0.4)', text: '#94a3b8' },
  UNKNOWN: { bg: 'rgba(100, 116, 139, 0.15)', border: 'rgba(100, 116, 139, 0.4)', text: '#94a3b8' },
}

const DATE_RANGE_OPTIONS = [
  { value: 'all', label: 'All' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: '180d', label: '180D' },
  { value: 'ytd', label: 'YTD' },
]

const AMOUNT_BRACKET_OPTIONS = [
  { value: 'all', label: 'All Amounts' },
  { value: 'micro', label: 'Micro (< ₹500)' },
  { value: 'small', label: 'Small (₹500 – ₹2k)' },
  { value: 'medium', label: 'Medium (₹2k – ₹10k)' },
  { value: 'large', label: 'Large (> ₹10k)' },
]

// Stable fallbacks. A fresh `[]` or `{}` per render would give TransactionsTab and the
// memoised derivations below a new prop identity on every render, which is exactly what
// React.memo is there to avoid.
const EMPTY_TRANSACTIONS: BudgetTransaction[] = []
const EMPTY_STRINGS: string[] = []
const EMPTY_LIST: any[] = []
const EMPTY_CATEGORY_DATA: BudgetCategoriesResponse = { categories: [], nature_summary: {} }

const PAYMENT_MODE_OPTIONS = [
  { value: 'all', label: 'All Modes' },
  { value: 'upi', label: 'UPI / QR', icon: <QrCodeIcon style={{ fontSize: 13 }} /> },
  { value: 'card', label: 'Card / POS', icon: <CreditCardIcon style={{ fontSize: 13 }} /> },
  { value: 'netbanking', label: 'NetBanking / IMPS', icon: <AccountBalanceIcon style={{ fontSize: 13 }} /> },
  { value: 'atm', label: 'ATM Cash', icon: <LocalAtmIcon style={{ fontSize: 13 }} /> },
  { value: 'autodebit', label: 'Auto-Debit / NACH', icon: <AutorenewIcon style={{ fontSize: 13 }} /> },
]

export default function BudgetDashboard() {
  const [sessionId, setSessionId] = useState<string>('overall')
  const [activeTab, setActiveTab] = useState(0)
  
  // Modals & Popovers
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [isSessionsModalOpen, setIsSessionsModalOpen] = useState(false)
  const [filterAnchorEl, setFilterAnchorEl] = useState<null | HTMLElement>(null)
  
  // Global Filters
  const [bankFilter, setBankFilter] = useState<string>('all')
  const [accountTypeFilter, setAccountTypeFilter] = useState<string>('all')
  const [flowFilter, setFlowFilter] = useState<string>('all') // 'all', 'debit', 'credit'
  const [dateRangeFilter, setDateRangeFilter] = useState<string>('all')
  const [amountBracketFilter, setAmountBracketFilter] = useState<string>('all')
  const [paymentModeFilter, setPaymentModeFilter] = useState<string>('all')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Card-Specific Interactive Filters
  const [merchantFlowTab, setMerchantFlowTab] = useState<'debit' | 'credit'>('debit')
  const [categoryFlowTab, setCategoryFlowTab] = useState<'debit' | 'credit'>('debit')
  const [categoryNatureFilter, setCategoryNatureFilter] = useState<string>('all') // 'all', 'needs', 'wants', 'investments', 'transfers'
  const [categorySortBy, setCategorySortBy] = useState<'amount' | 'count' | 'name'>('amount')
  const [categorySearch, setCategorySearch] = useState<string>('')
  const [dowMetric, setDowMetric] = useState<'spend' | 'count' | 'avg_spend'>('spend')

  // Upload / delete feedback. The parse report and the server's `detail` string both
  // belong on screen, not in console.error.
  const [uploadNotice, setUploadNotice] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // Count active non-default filters
  const advancedFiltersCount = [
    flowFilter !== 'all',
    amountBracketFilter !== 'all',
    paymentModeFilter !== 'all',
    categoryFilter !== 'all',
    accountTypeFilter !== 'all'
  ].filter(Boolean).length

  const totalActiveFiltersCount = [
    bankFilter !== 'all',
    accountTypeFilter !== 'all',
    flowFilter !== 'all',
    dateRangeFilter !== 'all',
    amountBracketFilter !== 'all',
    paymentModeFilter !== 'all',
    categoryFilter !== 'all',
    searchQuery.trim() !== ''
  ].filter(Boolean).length

  const resetAllFilters = useCallback(() => {
    setBankFilter('all')
    setAccountTypeFilter('all')
    setFlowFilter('all')
    setDateRangeFilter('all')
    setAmountBracketFilter('all')
    setPaymentModeFilter('all')
    setCategoryFilter('all')
    setSearchQuery('')
    setCategoryNatureFilter('all')
    setCategorySearch('')
  }, [])

  /**
   * One debounce for the filter set, at the shared 300ms every other call site uses.
   *
   * This replaces a hand-rolled 200ms `setTimeout` over ten filter states that fired
   * three GETs per change and four on mount - eight under StrictMode. A react-query
   * key change is a fetch, so it is the free-text input that has to settle; the
   * dropdowns and chips change once per click and go straight through.
   */
  const debouncedSearch = useDebounce(searchQuery, 300)

  const currentFilters: BudgetFilters = useMemo(() => ({
    bank: bankFilter,
    accountType: accountTypeFilter,
    txnType: flowFilter,
    dateRange: dateRangeFilter,
    amountBracket: amountBracketFilter,
    paymentMode: paymentModeFilter,
    category: categoryFilter,
    search: debouncedSearch,
  }), [
    bankFilter, accountTypeFilter, flowFilter, dateRangeFilter,
    amountBracketFilter, paymentModeFilter, categoryFilter, debouncedSearch,
  ])

  /**
   * The category card's own Debits/Credits toggle is a *sub*-filter.
   *
   * It used to overwrite `txnType` unconditionally, so with the global flow filter set
   * to "Credits (In)" the donut quietly showed debits - contradicting the filter chip
   * displayed directly above it. It now only applies when the global filter is "all".
   */
  const categoryFilters: BudgetFilters = useMemo(() => ({
    ...currentFilters,
    txnType: flowFilter === 'all' ? categoryFlowTab : flowFilter,
  }), [currentFilters, flowFilter, categoryFlowTab])

  const sessionsQuery = useBudgetSessions()
  const overviewQuery = useBudgetOverview(sessionId, currentFilters)
  const categoriesQuery = useBudgetCategories(sessionId, categoryFilters)
  /*
   * The full page is fetched only while the Transactions tab is mounted.
   *
   * This was unconditional at TRANSACTIONS_PAGE_SIZE (1000). On Overview - the tab
   * you land on - the entire payload was downloaded, JSON-parsed and held in memory
   * to produce two numbers: the count in the tab label and `transactions.length === 0`
   * in the empty check. Both come from `total`, which the endpoint returns whatever
   * the limit is, so a 1-row page answers them just as well. Re-fetched on every
   * filter and search keystroke, so the waste repeated.
   *
   * The two query keys differ by `limit`, so switching to the tab issues one real
   * fetch rather than reusing the 1-row page.
   */
  const transactionsQuery = useBudgetTransactions(
    sessionId, currentFilters, activeTab === 1 ? TRANSACTIONS_PAGE_SIZE : 1,
  )

  const uploadMutation = useUploadStatement()
  const deleteMutation = useDeleteBudgetSession()
  const invalidateAnalytics = useInvalidateBudgetAnalytics()

  // A session that is not the caller's now answers 404 instead of leaking rows, so a
  // stale id here is an expected state. Fall back to the consolidated view rather than
  // parking on an error the user has no control to dismiss.
  useResetSessionOnMissing(overviewQuery.error, sessionId, setSessionId)

  const sessionsList = sessionsQuery.data ?? EMPTY_LIST

  // "This account holds no statements at all" - distinct from "the current filters
  // match nothing" and from "the request failed". Gated on isSuccess so the first
  // paint, before the list has arrived, is not mistaken for an empty account and does
  // not flash the upload prompt at someone who has data.
  const hasNoStatements = sessionsQuery.isSuccess && sessionsList.length === 0

  const overview = overviewQuery.data ?? null
  const categoryData = categoriesQuery.data ?? EMPTY_CATEGORY_DATA
  // The endpoint pages, so `total` is the count before truncation. Keeping both means
  // the tab label and the table can say "500 of 8,412" rather than presenting the
  // first page as the whole result.
  const transactions = transactionsQuery.data?.transactions ?? EMPTY_TRANSACTIONS
  const transactionsTotal = transactionsQuery.data?.total ?? transactions.length
  const transactionsTruncated = transactionsQuery.data?.has_more ?? false

  /**
   * A 404 from /overview means "this session has no rows", which is the empty state -
   * everything else is a genuine failure and has to say so. The three getters this
   * replaces returned null/[]/{} on any error, so a 500 rendered "No accounts uploaded
   * yet" with an Upload CTA over data that was actually there.
   */
  const realError = (error: unknown) => (error && budgetErrorStatus(error) !== 404 ? error : null)
  const analyticsError: unknown =
    realError(overviewQuery.error) ?? realError(transactionsQuery.error) ?? realError(categoriesQuery.error)

  const loadErrorMessage = analyticsError
    ? budgetErrorDetail(analyticsError, 'Could not load your budget data. Please try again.')
    : null

  const handleModalUpload = useCallback(async (file: File, bank: string, accountType: string): Promise<string | null> => {
    setActionError(null)
    setUploadNotice(null)
    try {
      const result = await uploadMutation.mutateAsync({ file, bank, accountType })
      resetAllFilters()
      setSessionId('overall')

      // The parse report is shown, not logged. A statement that only half-parsed has
      // to say so, otherwise the dashboard describes part of the user's spending as
      // if it were all of it.
      const skipped = result.skipped ?? 0
      if (skipped > 0 || result.truncated) {
        const reasons = Object.entries(result.reasons || {})
          .map(([reason, count]) => `${reason}: ${count}`)
          .join(', ')
        const parts = [`${result.parsed ?? 0} transactions imported`]
        if (skipped > 0) {
          parts.push(`${skipped} row${skipped === 1 ? '' : 's'} skipped${reasons ? ` (${reasons})` : ''}`)
        }
        if (result.truncated) {
          parts.push('the file exceeded the import limit, so only the first rows were read')
        }
        setUploadNotice(`${parts.join(', ')}.`)
      }
      return null
    } catch (e) {
      // 422 carries the reason for an oversized or unsupported file; 400 explains
      // which columns the parser did find. Both are useful, so both are shown - here
      // for after the dialog closes, and returned for the dialog itself.
      const detail = budgetErrorDetail(e, 'Upload failed.')
      setActionError(detail)
      return detail
    }
  }, [uploadMutation, resetAllFilters])

  const handleDeleteSession = useCallback(async (sid: string) => {
    setActionError(null)
    try {
      await deleteMutation.mutateAsync(sid)
      if (sessionId === sid) setSessionId('overall')
    } catch (e) {
      setActionError(budgetErrorDetail(e, 'Delete failed.'))
    }
  }, [deleteMutation, sessionId])

  /**
   * Refresh after an edit made inside a tab.
   *
   * Was: mutate filter state - which re-triggered the debounced fetch effect - *and*
   * call the fetcher directly, so every single inline category edit cost a full
   * four-endpoint reload twice over. Invalidation refetches only the three analytics
   * queries, once, and this identity is stable so it does not defeat the memoised
   * children.
   */
  const refreshAllData = useCallback(() => { invalidateAnalytics() }, [invalidateAnalytics])

  // Stable identities for the memoised children below - an inline arrow would give
  // them a new prop every render and make React.memo a no-op.
  const closeSessionsModal = useCallback(() => setIsSessionsModalOpen(false), [])
  const selectSession = useCallback((sid: string) => setSessionId(sid), [])
  const selectCategory = useCallback((catName: string) => setCategoryFilter(catName), [])

  const activeSessionMeta = sessionsList.find(s => s.session_id === sessionId)
  const uniqueBanks: string[] = overview?.banks || EMPTY_STRINGS
  const uniqueAccountTypes: string[] = overview?.account_types || EMPTY_STRINGS
  const uniqueCategories: string[] = categoryData?.all_categories || overview?.categories || EMPTY_STRINGS
  const health = overview?.health_metrics || {}

  const activeMerchantsList = merchantFlowTab === 'debit'
    ? (overview?.top_merchants || EMPTY_LIST)
    : (overview?.top_inflows || EMPTY_LIST)

  const bankBreakdown = overview?.bank_breakdown || EMPTY_LIST

  // Filtered & Sorted Categories for the Category Card (When not in drill-down)
  const processedCategories = useMemo(() => {
    let list = [...(categoryData.categories || [])]
    
    // Filter by nature
    if (categoryNatureFilter !== 'all') {
      list = list.filter(c => (c.nature || 'other').toLowerCase() === categoryNatureFilter.toLowerCase())
    }
    
    // Filter by mini search
    if (categorySearch.trim() !== '') {
      const q = categorySearch.toLowerCase()
      list = list.filter(c => (c.category || '').toLowerCase().includes(q))
    }
    
    // Sort
    if (categorySortBy === 'amount') {
      list.sort((a, b) => b.amount - a.amount)
    } else if (categorySortBy === 'count') {
      list.sort((a, b) => (b.count || 0) - (a.count || 0))
    } else if (categorySortBy === 'name') {
      list.sort((a, b) => (a.category || '').localeCompare(b.category || ''))
    }
    
    return list
  }, [categoryData.categories, categoryNatureFilter, categorySearch, categorySortBy])

  const totalFilteredCategoryAmount = processedCategories.reduce((sum, c) => sum + (c.amount || 0), 0)

  /**
   * Donut slices: the biggest DONUT_SLICES categories, with the tail merged into one
   * "Other" slice.
   *
   * The chart was fed `processedCategories` whole, which broke in three ways once a
   * user had more than a handful of categories - and rules-based categorisation means
   * 20-40 is normal:
   *
   *   - `paddingAngle={3}` is 3 degrees *per slice*. At 30 categories that is 90 of
   *     the available 360 spent on gaps; past ~40 the padding exceeds the full circle
   *     and Recharts draws overlapping, wrong-sized arcs.
   *   - CATEGORY_COLORS has 10 entries and the index wraps, so the 11th category is
   *     the same colour as the 1st and adjacent slices could be identical.
   *   - Sub-1% slices are thinner than their own stroke, so the donut degrades into a
   *     ring of hairlines that cannot be hovered.
   *
   * The full list is untouched - it is a scrollable ranked list below, which is the
   * right control for the long tail. The donut answers "where does the money go",
   * which a top-N plus remainder answers better than 40 slivers.
   */
  const donutData = useMemo(() => {
    if (processedCategories.length <= DONUT_SLICES) return processedCategories
    const head = processedCategories.slice(0, DONUT_SLICES - 1)
    const tail = processedCategories.slice(DONUT_SLICES - 1)
    return [
      ...head,
      {
        category: `Other (${tail.length})`,
        amount: tail.reduce((sum, c) => sum + (c.amount || 0), 0),
        isOther: true,
      },
    ]
  }, [processedCategories])

  /**
   * Category totals keyed by name, for the in-card Select.
   *
   * That Select ran a `.find()` over `categoryData.categories` inside its `.map()`
   * over `uniqueCategories` - O(n x m) rebuilt on every render of the dashboard, over
   * a dropdown that lists every category the user has.
   */
  const categoryByName = useMemo(() => {
    const map = new Map<string, BudgetCategorySlice>()
    for (const item of categoryData.categories || []) {
      map.set((item.category || '').toLowerCase(), item)
    }
    return map
  }, [categoryData.categories])

  const isCategoryDrilldown = categoryData?.is_drilldown && categoryFilter !== 'all'
  const drilldownStats = categoryData?.category_stats

  // Only a first load blanks the screen. A refetch keeps the previous data on screen
  // via placeholderData, so it must not fall into this branch.
  if (!overview && overviewQuery.isPending) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
        <CircularProgress size={48} sx={{ color: '#6366f1' }} />
      </Box>
    )
  }

  return (
    <Box sx={{ p: { xs: 2, md: 4 }, color: '#fff', maxWidth: 1440, margin: '0 auto' }}>
      {/* Top Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3, flexWrap: 'wrap', gap: 2 }}>
        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            <Typography variant="h4" sx={{ fontWeight: 700, letterSpacing: '-0.02em', background: 'linear-gradient(90deg, #fff 0%, #cbd5e1 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Master Budget & Accounts
            </Typography>
            {/* Active Session Indicator */}
            <Chip
              icon={sessionId === 'overall' ? <LayersIcon style={{ fontSize: 16, color: '#818cf8' }} /> : <DescriptionIcon style={{ fontSize: 16, color: '#34d399' }} />}
              label={sessionId === 'overall' ? 'All Accounts Combined' : `${activeSessionMeta?.bank || 'Bank'} (${activeSessionMeta?.account_type || 'Account'})`}
              onClick={() => setIsSessionsModalOpen(true)}
              clickable
              sx={{
                background: sessionId === 'overall' ? 'rgba(99, 102, 241, 0.15)' : 'rgba(16, 185, 129, 0.15)',
                border: '1px solid',
                borderColor: sessionId === 'overall' ? 'rgba(99, 102, 241, 0.4)' : 'rgba(16, 185, 129, 0.4)',
                color: sessionId === 'overall' ? '#a5b4fc' : '#6ee7b7',
                fontWeight: 600,
                fontSize: '0.8rem',
                cursor: 'pointer'
              }}
            />
          </Box>
          <Typography variant="body2" sx={{ color: '#94a3b8', mt: 0.5 }}>
            Multi-bank accounts overview, debit vs credit flow tracking, and cash flow intelligence
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap' }}>
          {/* Accounts & Statements History Button */}
          <Button
            variant="outlined"
            startIcon={<HistoryIcon />}
            onClick={() => setIsSessionsModalOpen(true)}
            sx={{
              color: '#cbd5e1',
              borderColor: 'rgba(255,255,255,0.15)',
              textTransform: 'none',
              fontWeight: 600,
              borderRadius: 2,
              px: 2,
              '&:hover': { borderColor: '#818cf8', backgroundColor: 'rgba(99, 102, 241, 0.08)' }
            }}
          >
            Accounts & Statements ({sessionsList.length})
          </Button>
          
          {/* Upload Statement Button */}
          <Button
            variant="contained"
            onClick={() => setIsUploadModalOpen(true)}
            startIcon={<CloudUploadIcon />}
            disabled={uploadMutation.isPending}
            sx={{
              background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
              px: 2.5, py: 1, borderRadius: 2,
              fontWeight: 600,
              textTransform: 'none',
              boxShadow: '0 4px 14px 0 rgba(99, 102, 241, 0.39)',
              '&:hover': { background: 'linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)' }
            }}
          >
            Upload Statement
          </Button>
        </Box>
      </Box>

      {/* Tabs */}
      <Tabs 
        value={activeTab} 
        onChange={(_, nv) => setActiveTab(nv)} 
        sx={{ 
          mb: 2.5, 
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          '& .MuiTab-root': { color: '#94a3b8', fontWeight: 600, textTransform: 'none', fontSize: '1rem' },
          '& .Mui-selected': { color: '#818cf8 !important' },
          '& .MuiTabs-indicator': { backgroundColor: '#818cf8' }
        }}
      >
        <Tab label="Overview & Analytics" />
        <Tab label={`Transactions (${transactionsTotal.toLocaleString('en-IN')})`} />
        <Tab label="Accounts & Cards" />
        <Tab label="Insights" />
        <Tab label="Rules Engine" />
      </Tabs>

      {actionError && (
        <Card sx={{ p: 2, mb: 3, backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 2 }}>
          <Typography color="#fca5a5">{actionError}</Typography>
        </Card>
      )}

      {/* Parse report from the last upload: rows the parser could not read, and
          whether the file was cut short at the import limit. */}
      {uploadNotice && (
        <Card sx={{ p: 2, mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 2, backgroundColor: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: 2 }}>
          <Typography color="#fcd34d">{uploadNotice}</Typography>
          <IconButton size="small" onClick={() => setUploadNotice(null)} sx={{ color: '#fcd34d' }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Card>
      )}

      {/* ULTRA-SLEEK COMPACT GLOBAL FILTER BAR */}
      <Box sx={{ mb: 3.5 }}>
        <Box sx={{ 
          p: 1.5, px: 2, 
          background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(30, 41, 59, 0.45) 100%)', 
          border: '1px solid rgba(255, 255, 255, 0.08)', 
          borderRadius: '18px', 
          boxShadow: '0 8px 24px rgba(0, 0, 0, 0.25)',
          backdropFilter: 'blur(16px)',
          display: 'flex', 
          alignItems: 'center', 
          justifyContent: 'space-between', 
          gap: 1.5, 
          flexWrap: 'wrap' 
        }}>
          {/* Left: Compact Live Search */}
          <TextField
            size="small"
            placeholder="Search transactions, payees, tags..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            sx={{
              flex: { xs: '1 1 100%', sm: '1 1 240px', md: '1 1 300px' },
              '& .MuiOutlinedInput-root': {
                backgroundColor: 'rgba(255, 255, 255, 0.04)',
                borderRadius: '12px',
                color: '#f8fafc',
                fontSize: '0.86rem',
                height: 38,
                transition: 'all 0.2s ease',
                '& fieldset': { borderColor: 'rgba(255, 255, 255, 0.09)' },
                '&:hover fieldset': { borderColor: '#818cf8' },
                '&.Mui-focused': {
                  backgroundColor: 'rgba(255, 255, 255, 0.07)',
                  '& fieldset': { borderColor: '#6366f1', borderWidth: '1.5px' },
                }
              }
            }}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon sx={{ color: '#818cf8', fontSize: 18 }} />
                </InputAdornment>
              ),
              endAdornment: searchQuery ? (
                <InputAdornment position="end">
                  <IconButton size="small" onClick={() => setSearchQuery('')} sx={{ color: '#94a3b8', p: 0.5 }}>
                    <ClearIcon style={{ fontSize: 15 }} />
                  </IconButton>
                </InputAdornment>
              ) : null
            }}
          />

          {/* Center/Right: Bank Selector + Time Horizon Segment + Advanced Filter Popover Button */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.2, flexWrap: 'wrap', ml: 'auto' }}>
            
            {/* Bank Selector Dropdown */}
            {uniqueBanks.length > 0 && (
              <FormControl size="small">
                <Select
                  value={bankFilter}
                  onChange={(e) => setBankFilter(e.target.value)}
                  displayEmpty
                  sx={{
                    height: 38,
                    color: bankFilter === 'all' ? '#cbd5e1' : '#38bdf8',
                    backgroundColor: bankFilter === 'all' ? 'rgba(255, 255, 255, 0.04)' : 'rgba(56, 189, 248, 0.12)',
                    borderRadius: '12px',
                    fontSize: '0.82rem',
                    fontWeight: 700,
                    border: '1px solid',
                    borderColor: bankFilter === 'all' ? 'rgba(255, 255, 255, 0.1)' : 'rgba(56, 189, 248, 0.35)',
                    transition: 'all 0.2s ease',
                    '& .MuiSelect-select': { py: 0.8, pr: 3 },
                    '& fieldset': { border: 'none' },
                    '&:hover': {
                      borderColor: '#38bdf8',
                      backgroundColor: 'rgba(56, 189, 248, 0.18)'
                    }
                  }}
                >
                  <MenuItem value="all" sx={{ fontSize: '0.82rem', fontWeight: 600 }}>🏛️ All Banks</MenuItem>
                  {uniqueBanks.map((b: string) => (
                    <MenuItem key={b} value={b} sx={{ fontSize: '0.82rem', fontWeight: 600 }}>
                      {b.toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            {/* Time Horizon Segmented Pill */}
            <Box sx={{ 
              display: 'flex', 
              background: 'rgba(255, 255, 255, 0.04)', 
              borderRadius: '12px', 
              p: 0.4, 
              border: '1px solid rgba(255, 255, 255, 0.08)' 
            }}>
              {DATE_RANGE_OPTIONS.map((opt) => {
                const isSelected = dateRangeFilter === opt.value
                return (
                  <Button
                    key={opt.value}
                    size="small"
                    onClick={() => setDateRangeFilter(opt.value)}
                    sx={{
                      minWidth: 40,
                      px: 1.3,
                      py: 0.5,
                      fontSize: '0.76rem',
                      fontWeight: isSelected ? 800 : 600,
                      borderRadius: '9px',
                      textTransform: 'none',
                      color: isSelected ? '#fff' : '#94a3b8',
                      background: isSelected ? 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)' : 'transparent',
                      boxShadow: isSelected ? '0 2px 8px rgba(99, 102, 241, 0.4)' : 'none',
                      transition: 'all 0.2s ease',
                      '&:hover': { 
                        background: isSelected ? 'linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)' : 'rgba(255, 255, 255, 0.06)',
                        color: '#fff'
                      }
                    }}
                  >
                    {opt.label}
                  </Button>
                )
              })}
            </Box>

            {/* More Filters Popover Trigger Button */}
            <Badge badgeContent={advancedFiltersCount} color="primary" sx={{ '& .MuiBadge-badge': { backgroundColor: '#6366f1', color: '#fff', fontWeight: 700 } }}>
              <Button
                variant="outlined"
                size="small"
                startIcon={<TuneIcon style={{ fontSize: 16 }} />}
                onClick={(e) => setFilterAnchorEl(e.currentTarget)}
                sx={{
                  height: 38,
                  color: advancedFiltersCount > 0 ? '#a5b4fc' : '#cbd5e1',
                  borderColor: advancedFiltersCount > 0 ? '#6366f1' : 'rgba(255, 255, 255, 0.12)',
                  backgroundColor: advancedFiltersCount > 0 ? 'rgba(99, 102, 241, 0.12)' : 'rgba(255, 255, 255, 0.03)',
                  borderRadius: '12px',
                  textTransform: 'none',
                  fontSize: '0.82rem',
                  fontWeight: 700,
                  px: 1.8,
                  transition: 'all 0.2s ease',
                  '&:hover': { borderColor: '#818cf8', backgroundColor: 'rgba(99, 102, 241, 0.2)' }
                }}
              >
                Filters
              </Button>
            </Badge>

            {/* Global Reset Button if active */}
            {totalActiveFiltersCount > 0 && (
              <IconButton 
                size="small" 
                onClick={resetAllFilters}
                title="Reset all filters"
                sx={{ 
                  color: '#f87171', 
                  backgroundColor: 'rgba(239, 68, 68, 0.12)', 
                  border: '1px solid rgba(239, 68, 68, 0.25)',
                  borderRadius: '12px',
                  p: 0.9, 
                  '&:hover': { backgroundColor: 'rgba(239, 68, 68, 0.25)', borderColor: '#ef4444' } 
                }}
              >
                <RestartAltIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
        </Box>

        {/* Dismissible Active Filter Chips Row */}
        {totalActiveFiltersCount > 0 && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1.2, px: 0.5, flexWrap: 'wrap' }}>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 600 }}>Active filters:</Typography>
            
            {bankFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Bank: ${bankFilter.toUpperCase()}`} 
                onDelete={() => setBankFilter('all')} 
                sx={{ backgroundColor: 'rgba(96, 165, 250, 0.15)', color: '#60a5fa', borderColor: 'rgba(96, 165, 250, 0.3)', border: '1px solid', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}
            
            {flowFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Flow: ${flowFilter === 'debit' ? 'Debits Only' : 'Credits Only'}`} 
                onDelete={() => setFlowFilter('all')} 
                sx={{ backgroundColor: flowFilter === 'debit' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(16, 185, 129, 0.15)', color: flowFilter === 'debit' ? '#f87171' : '#34d399', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}

            {dateRangeFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Time: ${dateRangeFilter.toUpperCase()}`} 
                onDelete={() => setDateRangeFilter('all')} 
                sx={{ backgroundColor: 'rgba(99, 102, 241, 0.15)', color: '#a5b4fc', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}

            {amountBracketFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Amount: ${AMOUNT_BRACKET_OPTIONS.find(a => a.value === amountBracketFilter)?.label || amountBracketFilter}`} 
                onDelete={() => setAmountBracketFilter('all')} 
                sx={{ backgroundColor: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}

            {paymentModeFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Mode: ${paymentModeFilter.toUpperCase()}`} 
                onDelete={() => setPaymentModeFilter('all')} 
                sx={{ backgroundColor: 'rgba(167, 139, 250, 0.15)', color: '#c4b5fd', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}

            {categoryFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Category: ${categoryFilter}`} 
                onDelete={() => setCategoryFilter('all')} 
                sx={{ backgroundColor: 'rgba(236, 72, 153, 0.15)', color: '#f472b6', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}

            {accountTypeFilter !== 'all' && (
              <Chip 
                size="small" 
                label={`Account: ${accountTypeFilter}`} 
                onDelete={() => setAccountTypeFilter('all')} 
                sx={{ backgroundColor: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', fontSize: '0.75rem', fontWeight: 600 }} 
              />
            )}

            <Button 
              size="small" 
              onClick={resetAllFilters}
              sx={{ color: '#f43f5e', textTransform: 'none', fontSize: '0.75rem', p: 0.2, minWidth: 'auto', fontWeight: 600 }}
            >
              Clear all
            </Button>
          </Box>
        )}
      </Box>

      {/* MORE FILTERS POPOVER MODAL */}
      <Popover
        open={Boolean(filterAnchorEl)}
        anchorEl={filterAnchorEl}
        onClose={() => setFilterAnchorEl(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        transformOrigin={{ vertical: 'top', horizontal: 'right' }}
        PaperProps={{
          sx: {
            p: 2.5,
            width: 360,
            backgroundColor: '#0f172a',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 3,
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5)',
            color: '#fff'
          }
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>Advanced Filters</Typography>
          <IconButton size="small" onClick={() => setFilterAnchorEl(null)} sx={{ color: '#94a3b8' }}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Box>

        <Stack spacing={2.5}>
          {/* Cash Flow Direction */}
          <Box>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 1 }}>
              Flow Direction
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              {[
                { val: 'all', label: 'All' },
                { val: 'debit', label: 'Debits (Out)', color: '#ef4444' },
                { val: 'credit', label: 'Credits (In)', color: '#10b981' }
              ].map((f) => (
                <Chip
                  key={f.val}
                  size="small"
                  label={f.label}
                  clickable
                  onClick={() => setFlowFilter(f.val)}
                  sx={{
                    fontWeight: 600,
                    backgroundColor: flowFilter === f.val ? (f.color ? `${f.color}25` : '#6366f1') : 'rgba(255,255,255,0.04)',
                    color: flowFilter === f.val ? (f.color || '#fff') : '#94a3b8',
                    border: '1px solid',
                    borderColor: flowFilter === f.val ? (f.color || '#818cf8') : 'rgba(255,255,255,0.08)'
                  }}
                />
              ))}
            </Box>
          </Box>

          {/* Amount Brackets */}
          <Box>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 1 }}>
              Spend Size Bracket
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8 }}>
              {AMOUNT_BRACKET_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  size="small"
                  label={opt.label}
                  clickable
                  onClick={() => setAmountBracketFilter(opt.value)}
                  sx={{
                    fontWeight: 600,
                    backgroundColor: amountBracketFilter === opt.value ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255,255,255,0.04)',
                    color: amountBracketFilter === opt.value ? '#fbbf24' : '#94a3b8',
                    border: '1px solid',
                    borderColor: amountBracketFilter === opt.value ? '#fbbf24' : 'rgba(255,255,255,0.08)'
                  }}
                />
              ))}
            </Box>
          </Box>

          {/* Payment Modes */}
          <Box>
            <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 1 }}>
              Payment Channel
            </Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8 }}>
              {PAYMENT_MODE_OPTIONS.map((opt) => (
                <Chip
                  key={opt.value}
                  size="small"
                  label={opt.label}
                  icon={opt.icon ? <span style={{ color: paymentModeFilter === opt.value ? '#fff' : '#a78bfa' }}>{opt.icon}</span> : undefined}
                  clickable
                  onClick={() => setPaymentModeFilter(opt.value)}
                  sx={{
                    fontWeight: 600,
                    backgroundColor: paymentModeFilter === opt.value ? 'rgba(167, 139, 250, 0.25)' : 'rgba(255,255,255,0.04)',
                    color: paymentModeFilter === opt.value ? '#c4b5fd' : '#94a3b8',
                    border: '1px solid',
                    borderColor: paymentModeFilter === opt.value ? '#a78bfa' : 'rgba(255,255,255,0.08)'
                  }}
                />
              ))}
            </Box>
          </Box>

          {/* Category Dropdown */}
          {uniqueCategories.length > 0 && (
            <Box>
              <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 1 }}>
                Category
              </Typography>
              <FormControl size="small" fullWidth>
                <Select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  sx={{
                    color: '#fff',
                    backgroundColor: 'rgba(255,255,255,0.04)',
                    borderRadius: 2,
                    fontSize: '0.85rem',
                    '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' }
                  }}
                >
                  <MenuItem value="all" sx={{ fontSize: '0.8rem' }}>All Categories</MenuItem>
                  {uniqueCategories.map((c: string) => (
                    <MenuItem key={c} value={c} sx={{ fontSize: '0.8rem' }}>{c}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>
          )}

          {/* Account Type */}
          {uniqueAccountTypes.length > 0 && (
            <Box>
              <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 1 }}>
                Account Type
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.8 }}>
                <Chip
                  size="small"
                  label="All Types"
                  clickable
                  onClick={() => setAccountTypeFilter('all')}
                  sx={{
                    fontWeight: 600,
                    backgroundColor: accountTypeFilter === 'all' ? '#38bdf8' : 'rgba(255,255,255,0.04)',
                    color: accountTypeFilter === 'all' ? '#0f172a' : '#cbd5e1'
                  }}
                />
                {uniqueAccountTypes.map((a: string) => (
                  <Chip
                    key={a}
                    size="small"
                    label={a}
                    clickable
                    onClick={() => setAccountTypeFilter(a)}
                    sx={{
                      fontWeight: 600,
                      backgroundColor: accountTypeFilter === a ? '#0284c7' : 'rgba(255,255,255,0.04)',
                      color: accountTypeFilter === a ? '#fff' : '#38bdf8'
                    }}
                  />
                ))}
              </Box>
            </Box>
          )}

          <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)' }} />

          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Button
              size="small"
              onClick={resetAllFilters}
              sx={{ color: '#f43f5e', textTransform: 'none', fontSize: '0.75rem', fontWeight: 600 }}
            >
              Reset Filters
            </Button>
            <Button
              variant="contained"
              size="small"
              onClick={() => setFilterAnchorEl(null)}
              sx={{ background: '#6366f1', textTransform: 'none', fontSize: '0.8rem', fontWeight: 600, borderRadius: 1.5 }}
            >
              Apply
            </Button>
          </Box>
        </Stack>
      </Popover>
      
      {hasNoStatements ? (
        /* Checked before the error branch, and before any data is read.

           Deleting the last statement left the dashboard showing the deleted
           numbers. `/analytics/overall/overview` answers 404 for an empty ledger,
           useResetSessionOnMissing ignores 404 when the session is already
           'overall' (there is nowhere to fall back to), so nothing cleared - and
           `placeholderData: keepPreviousData` kept the previous response on screen
           behind the failed refetch.

           The session list is the authoritative answer to "does this user have any
           data", it is invalidated by the same delete, and it does not depend on the
           analytics endpoints agreeing about what empty means. */
        <Card sx={{ textAlign: 'center', p: 8, background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.1)', borderRadius: 4 }}>
          <AccountBalanceIcon sx={{ fontSize: 64, color: '#6366f1', mb: 2, opacity: 0.8 }} />
          <Typography variant="h5" sx={{ fontWeight: 600, color: '#f8fafc' }}>
            No statements yet
          </Typography>
          <Typography variant="body2" sx={{ color: '#94a3b8', mt: 1, maxWidth: 500, mx: 'auto', mb: 3 }}>
            Upload statements from HDFC, ICICI, SBI, Axis, Kotak, or other banks to start tracking.
          </Typography>
          <Button
            variant="contained"
            onClick={() => setIsUploadModalOpen(true)}
            startIcon={<CloudUploadIcon />}
            sx={{
              background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
              px: 3, py: 1.2, borderRadius: 2, fontWeight: 600, textTransform: 'none'
            }}
          >
            Upload Statement
          </Button>
        </Card>
      ) : loadErrorMessage ? (
        /* A failed load is never the empty state. The three getters this replaces
           returned null/[]/{} on any error, so a 500 rendered "No accounts uploaded
           yet" with an Upload CTA - over data the user had already uploaded. */
        <Card sx={{ textAlign: 'center', p: 8, background: 'rgba(239, 68, 68, 0.05)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: 4 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, color: '#fca5a5' }}>
            Could not load your budget data
          </Typography>
          <Typography variant="body2" sx={{ color: '#94a3b8', mt: 1, maxWidth: 560, mx: 'auto', mb: 3 }}>
            {loadErrorMessage}
          </Typography>
          <Button
            variant="contained"
            onClick={refreshAllData}
            startIcon={<RestartAltIcon />}
            sx={{ background: '#6366f1', px: 3, py: 1.2, borderRadius: 2, fontWeight: 600, textTransform: 'none' }}
          >
            Retry
          </Button>
        </Card>
      ) : (!overview || (overview.total_income === 0 && overview.total_expense === 0 && transactions.length === 0)) ? (
        <Card sx={{ textAlign: 'center', p: 8, background: 'rgba(255,255,255,0.02)', border: '1px dashed rgba(255,255,255,0.1)', borderRadius: 4 }}>
          <AccountBalanceIcon sx={{ fontSize: 64, color: '#6366f1', mb: 2, opacity: 0.8 }} />
          <Typography variant="h5" sx={{ fontWeight: 600, color: '#f8fafc' }}>
            {totalActiveFiltersCount > 0 ? 'No transactions match the selected filters' : 'No accounts uploaded yet'}
          </Typography>
          <Typography variant="body2" sx={{ color: '#94a3b8', mt: 1, maxWidth: 500, mx: 'auto', mb: 3 }}>
            {totalActiveFiltersCount > 0 
              ? 'Try clearing some of your search queries, amount brackets, or time filters.'
              : 'Upload statements from HDFC, ICICI, SBI, Axis, Kotak, or other banks to start tracking.'}
          </Typography>
          {totalActiveFiltersCount > 0 ? (
            <Button
              variant="contained"
              onClick={resetAllFilters}
              startIcon={<RestartAltIcon />}
              sx={{ background: '#6366f1', px: 3, py: 1.2, borderRadius: 2, fontWeight: 600, textTransform: 'none' }}
            >
              Reset All Filters
            </Button>
          ) : (
            <Button
              variant="contained"
              onClick={() => setIsUploadModalOpen(true)}
              startIcon={<CloudUploadIcon />}
              sx={{
                background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
                px: 3, py: 1.2, borderRadius: 2, fontWeight: 600, textTransform: 'none'
              }}
            >
              Upload Statement
            </Button>
          )}
        </Card>
      ) : (
        <>
          {/* TAB 0: OVERVIEW & ANALYTICS */}
          {activeTab === 0 && (
            <Box>
              {/* Why the KPIs below are smaller than the sum of the statements. The
                  correction is often lakhs; unexplained, it reads as a bug. */}
              <TransfersExcludedCard sessionId={sessionId} />

              {/* Primary KPIs: Inflow, Outflow, Net Balance, Savings Rate */}
              <Grid container spacing={2.5} sx={{ mb: 3.5 }}>
                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2.8, 
                    borderRadius: '20px',
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(16, 185, 129, 0.05) 100%)', 
                    border: '1px solid rgba(16, 185, 129, 0.25)', 
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)',
                    backdropFilter: 'blur(16px)',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      transform: 'translateY(-3px)',
                      borderColor: 'rgba(16, 185, 129, 0.45)',
                      boxShadow: '0 16px 36px rgba(16, 185, 129, 0.15)'
                    }
                  }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" sx={{ color: '#94a3b8', fontWeight: 700, fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        Total Inflow
                      </Typography>
                      <Box sx={{ p: 0.8, borderRadius: '10px', bgcolor: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.25)', display: 'flex', alignItems: 'center' }}>
                        <ArrowUpwardIcon sx={{ color: '#34d399', fontSize: 18 }} />
                      </Box>
                    </Box>
                    <Typography variant="h4" sx={{ mt: 1.5, fontWeight: 800, color: '#34d399', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
                      +₹{overview.total_income.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#94a3b8', mt: 0.5, display: 'block', fontWeight: 500 }}>
                      Deposits, Salary & Income
                    </Typography>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2.8, 
                    borderRadius: '20px',
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(239, 68, 68, 0.05) 100%)', 
                    border: '1px solid rgba(239, 68, 68, 0.25)', 
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)',
                    backdropFilter: 'blur(16px)',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      transform: 'translateY(-3px)',
                      borderColor: 'rgba(239, 68, 68, 0.45)',
                      boxShadow: '0 16px 36px rgba(239, 68, 68, 0.15)'
                    }
                  }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" sx={{ color: '#94a3b8', fontWeight: 700, fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        Total Outflow
                      </Typography>
                      <Box sx={{ p: 0.8, borderRadius: '10px', bgcolor: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.25)', display: 'flex', alignItems: 'center' }}>
                        <ArrowDownwardIcon sx={{ color: '#f87171', fontSize: 18 }} />
                      </Box>
                    </Box>
                    <Typography variant="h4" sx={{ mt: 1.5, fontWeight: 800, color: '#f87171', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
                      -₹{overview.total_expense.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#94a3b8', mt: 0.5, display: 'block', fontWeight: 500 }}>
                      Expenses, Card Spends & Bills
                    </Typography>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2.8, 
                    borderRadius: '20px',
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(56, 189, 248, 0.05) 100%)', 
                    border: '1px solid rgba(56, 189, 248, 0.25)', 
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)',
                    backdropFilter: 'blur(16px)',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      transform: 'translateY(-3px)',
                      borderColor: 'rgba(56, 189, 248, 0.45)',
                      boxShadow: '0 16px 36px rgba(56, 189, 248, 0.15)'
                    }
                  }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" sx={{ color: '#94a3b8', fontWeight: 700, fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        Net Cash Flow
                      </Typography>
                      <Box sx={{ p: 0.8, borderRadius: '10px', bgcolor: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.25)', display: 'flex', alignItems: 'center' }}>
                        <SavingsIcon sx={{ color: '#38bdf8', fontSize: 18 }} />
                      </Box>
                    </Box>
                    <Typography variant="h4" sx={{ mt: 1.5, fontWeight: 800, color: overview.net_savings >= 0 ? '#38bdf8' : '#fb7185', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
                      {overview.net_savings >= 0 ? '+' : ''}₹{overview.net_savings.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                    </Typography>
                    <Typography variant="caption" sx={{ color: overview.net_savings >= 0 ? '#38bdf8' : '#fb7185', mt: 0.5, display: 'block', fontWeight: 600 }}>
                      {overview.net_savings >= 0 ? '✨ Surplus cash flow' : '⚠️ Deficit spend'}
                    </Typography>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2.8, 
                    borderRadius: '20px',
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(167, 139, 250, 0.05) 100%)', 
                    border: '1px solid rgba(167, 139, 250, 0.25)', 
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.25)',
                    backdropFilter: 'blur(16px)',
                    transition: 'all 0.25s ease',
                    '&:hover': {
                      transform: 'translateY(-3px)',
                      borderColor: 'rgba(167, 139, 250, 0.45)',
                      boxShadow: '0 16px 36px rgba(167, 139, 250, 0.15)'
                    }
                  }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography variant="body2" sx={{ color: '#94a3b8', fontWeight: 700, fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        Savings Rate
                      </Typography>
                      <Box sx={{ p: 0.8, borderRadius: '10px', bgcolor: 'rgba(167, 139, 250, 0.12)', border: '1px solid rgba(167, 139, 250, 0.25)', display: 'flex', alignItems: 'center' }}>
                        <TrendingUpIcon sx={{ color: '#a78bfa', fontSize: 18 }} />
                      </Box>
                    </Box>
                    <Typography variant="h4" sx={{ mt: 1.5, fontWeight: 800, color: '#a78bfa', fontVariantNumeric: 'tabular-nums', letterSpacing: '-0.02em' }}>
                      {overview.savings_rate.toFixed(1)}%
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#94a3b8', mt: 0.5, display: 'block', fontWeight: 500 }}>
                      Ratio of Inflows saved
                    </Typography>
                  </Card>
                </Grid>
              </Grid>

              {/* Financial Health & Velocity Row */}
              <Grid container spacing={2} sx={{ mb: 4 }}>
                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2, 
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.6) 0%, rgba(30, 41, 59, 0.3) 100%)', 
                    border: '1px solid rgba(255, 255, 255, 0.06)', 
                    borderRadius: '16px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 1.5,
                    transition: 'all 0.2s ease',
                    '&:hover': { transform: 'translateY(-2px)', borderColor: 'rgba(255, 255, 255, 0.12)' }
                  }}>
                    <Box sx={{ p: 1, borderRadius: '12px', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.25)', color: '#f87171', display: 'flex' }}>
                      <LocalFireDepartmentIcon fontSize="small" />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', fontWeight: 600, fontSize: '0.72rem' }}>Avg Monthly Burn</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#fff', fontVariantNumeric: 'tabular-nums' }}>
                        ₹{(health.avg_monthly_burn || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}/mo
                      </Typography>
                    </Box>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2, 
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.6) 0%, rgba(30, 41, 59, 0.3) 100%)', 
                    border: '1px solid rgba(255, 255, 255, 0.06)', 
                    borderRadius: '16px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 1.5,
                    transition: 'all 0.2s ease',
                    '&:hover': { transform: 'translateY(-2px)', borderColor: 'rgba(255, 255, 255, 0.12)' }
                  }}>
                    <Box sx={{ p: 1, borderRadius: '12px', background: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.25)', color: '#38bdf8', display: 'flex' }}>
                      <TodayIcon fontSize="small" />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', fontWeight: 600, fontSize: '0.72rem' }}>Avg Daily Spend</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#fff', fontVariantNumeric: 'tabular-nums' }}>
                        ₹{(health.avg_daily_spend || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}/day
                      </Typography>
                    </Box>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2, 
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.6) 0%, rgba(30, 41, 59, 0.3) 100%)', 
                    border: '1px solid rgba(255, 255, 255, 0.06)', 
                    borderRadius: '16px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 1.5,
                    transition: 'all 0.2s ease',
                    '&:hover': { transform: 'translateY(-2px)', borderColor: 'rgba(255, 255, 255, 0.12)' }
                  }}>
                    <Box sx={{ p: 1, borderRadius: '12px', background: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.25)', color: '#f87171', display: 'flex' }}>
                      <TrendingDownIcon fontSize="small" />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', fontWeight: 600, fontSize: '0.72rem' }}>Largest Outflow (Debit)</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#f87171', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }} title={health.largest_debit?.description}>
                        ₹{(health.largest_debit?.amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </Typography>
                    </Box>
                  </Card>
                </Grid>

                <Grid item xs={12} sm={6} md={3}>
                  <Card sx={{ 
                    p: 2, 
                    background: 'linear-gradient(135deg, rgba(15, 23, 42, 0.6) 0%, rgba(30, 41, 59, 0.3) 100%)', 
                    border: '1px solid rgba(255, 255, 255, 0.06)', 
                    borderRadius: '16px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: 1.5,
                    transition: 'all 0.2s ease',
                    '&:hover': { transform: 'translateY(-2px)', borderColor: 'rgba(255, 255, 255, 0.12)' }
                  }}>
                    <Box sx={{ p: 1, borderRadius: '12px', background: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.25)', color: '#34d399', display: 'flex' }}>
                      <TrendingUpIcon fontSize="small" />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', fontWeight: 600, fontSize: '0.72rem' }}>Largest Inflow (Credit)</Typography>
                      <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#34d399', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }} title={health.largest_credit?.description}>
                        ₹{(health.largest_credit?.amount || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                      </Typography>
                    </Box>
                  </Card>
                </Grid>
              </Grid>

              {/* Comprehensive 50 / 30 / 20 Budget Health & Rule Evaluation Suite */}
              {overview.budget_50_30_20 && (
                <BudgetHealth503020Card 
                  data={overview.budget_50_30_20}
                  onCategoryClick={selectCategory}
                />
              )}

              {/* Bank & Accounts Breakdown Cards with Direct-Click Filter */}
              {bankBreakdown.length > 0 && (
                <Box sx={{ mb: 4 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                    <Typography variant="h6" sx={{ fontWeight: 600, color: '#f1f5f9' }}>
                      Accounts & Bank Breakdown
                    </Typography>
                    {bankFilter !== 'all' && (
                      <Button
                        size="small"
                        onClick={() => setBankFilter('all')}
                        sx={{ color: '#60a5fa', textTransform: 'none', fontSize: '0.75rem', fontWeight: 600 }}
                      >
                        ← Show All Banks
                      </Button>
                    )}
                  </Box>
                  <Grid container spacing={2.5}>
                    {bankBreakdown.map((b: any) => {
                      const bankUpper = b.bank.toUpperCase()
                      const style = BANK_COLOR_MAP[bankUpper] || BANK_COLOR_MAP['GENERIC']
                      const isSelected = bankFilter.toUpperCase() === bankUpper
                      const isCard = (b.account_type || '').toLowerCase().includes('card')
                      return (
                        <Grid item xs={12} sm={6} md={12 / Math.min(bankBreakdown.length, 3)} key={b.bank}>
                          <Card 
                            onClick={() => setBankFilter(isSelected ? 'all' : b.bank)}
                            sx={{ 
                              p: 2.2, 
                              background: isSelected ? style.bg : 'rgba(255,255,255,0.02)', 
                              border: '1px solid',
                              borderColor: isSelected ? style.text : 'rgba(255,255,255,0.08)',
                              borderRadius: 3,
                              cursor: 'pointer',
                              transition: 'all 0.2s ease',
                              boxShadow: isSelected ? `0 0 15px ${style.border}` : 'none',
                              '&:hover': { transform: 'translateY(-2px)', borderColor: style.text }
                            }}
                          >
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5 }}>
                              <Stack direction="row" spacing={1} alignItems="center">
                                <Chip 
                                  label={bankUpper} 
                                  icon={<AccountBalanceIcon style={{ color: style.text }} />}
                                  size="small"
                                  sx={{ backgroundColor: isSelected ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.05)', color: '#fff', fontWeight: 700, border: `1px solid ${style.border}` }}
                                />
                                <Chip
                                  label={b.account_type || 'Savings Account'}
                                  icon={isCard ? <CreditCardIcon style={{ fontSize: 12, color: '#f472b6' }} /> : undefined}
                                  size="small"
                                  sx={{ backgroundColor: 'rgba(255,255,255,0.04)', color: '#cbd5e1', fontSize: '0.7rem' }}
                                />
                              </Stack>
                              <Typography variant="caption" sx={{ color: isSelected ? style.text : '#94a3b8', fontWeight: 600 }}>
                                {isSelected ? '● Active' : 'Filter'}
                              </Typography>
                            </Box>
                            
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.8 }}>
                              <Typography variant="caption" sx={{ color: '#94a3b8' }}>Inflow (Credits):</Typography>
                              <Typography variant="body2" sx={{ fontWeight: 600, color: '#34d399' }}>+₹{b.income.toLocaleString('en-IN')}</Typography>
                            </Box>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.8 }}>
                              <Typography variant="caption" sx={{ color: '#94a3b8' }}>Outflow (Debits):</Typography>
                              <Typography variant="body2" sx={{ fontWeight: 600, color: '#f87171' }}>-₹{b.expense.toLocaleString('en-IN')}</Typography>
                            </Box>
                            <Divider sx={{ my: 0.8, borderColor: 'rgba(255,255,255,0.06)' }} />
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <Typography variant="caption" sx={{ color: '#94a3b8' }}>{b.transactions} txns</Typography>
                              <Typography variant="body2" sx={{ fontWeight: 700, color: b.net >= 0 ? '#38bdf8' : '#fb7185' }}>
                                Net: ₹{b.net.toLocaleString('en-IN')}
                              </Typography>
                            </Box>
                          </Card>
                        </Grid>
                      )
                    })}
                  </Grid>
                </Box>
              )}

              {/* Row: Cumulative Net Wealth Area Chart & Monthly Trend Bar Chart */}
              <Grid container spacing={3} sx={{ mb: 4 }}>
                {/* Cumulative Cash Flow Trajectory */}
                <Grid item xs={12} lg={6}>
                  <Card sx={{ p: 3, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 3, height: 420 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <ShowChartIcon sx={{ color: '#818cf8', fontSize: 20 }} />
                        <Typography variant="h6" sx={{ fontWeight: 600 }}>Cumulative Cash Flow Trajectory</Typography>
                      </Box>
                    </Box>
                    <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 2 }}>
                      Net cumulative savings & liquidity progression over time
                    </Typography>
                    {overview.cumulative_trend && overview.cumulative_trend.length > 0 ? (
                      <ResponsiveContainer width="100%" height="82%">
                        <AreaChart data={overview.cumulative_trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <defs>
                            <linearGradient id="cumColor" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#818cf8" stopOpacity={0.4}/>
                              <stop offset="95%" stopColor="#818cf8" stopOpacity={0.0}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                          <XAxis dataKey="date" stroke="rgba(255,255,255,0.4)" fontSize={11} />
                          <YAxis stroke="rgba(255,255,255,0.4)" fontSize={11} tickFormatter={(v) => `₹${v >= 1000 ? `${(v/1000).toFixed(0)}k` : v}`} />
                          <RechartsTooltip 
                            formatter={(value: number) => [`₹${value.toLocaleString('en-IN')}`, 'Cumulative Balance']}
                            contentStyle={{ backgroundColor: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} 
                          />
                          <Area type="monotone" dataKey="cumulative" stroke="#818cf8" strokeWidth={2.5} fillOpacity={1} fill="url(#cumColor)" />
                        </AreaChart>
                      </ResponsiveContainer>
                    ) : (
                      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '70%', color: '#94a3b8' }}>
                        <Typography variant="body2">No trajectory data available</Typography>
                      </Box>
                    )}
                  </Card>
                </Grid>

                {/* Monthly Trend Bar Chart */}
                <Grid item xs={12} lg={6}>
                  <Card sx={{ p: 3, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 3, height: 420 }}>
                    <Typography variant="h6" sx={{ mb: 0.5, fontWeight: 600 }}>Monthly Inflows vs Outflows</Typography>
                    <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 2 }}>
                      Monthly credit vs debit trajectory
                    </Typography>
                    {overview.monthly_trend && overview.monthly_trend.length > 0 ? (
                      <ResponsiveContainer width="100%" height="82%">
                        <BarChart data={overview.monthly_trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                          <XAxis dataKey="month" stroke="rgba(255,255,255,0.4)" fontSize={12} />
                          <YAxis stroke="rgba(255,255,255,0.4)" fontSize={12} tickFormatter={(v) => `₹${v >= 1000 ? `${(v/1000).toFixed(0)}k` : v}`} />
                          <RechartsTooltip 
                            formatter={(value: number) => `₹${value.toLocaleString('en-IN')}`}
                            contentStyle={{ backgroundColor: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} 
                          />
                          <Legend wrapperStyle={{ paddingTop: 10 }} />
                          <Bar dataKey="income" name="Credits (Inflow)" fill="#10b981" radius={[4, 4, 0, 0]} />
                          <Bar dataKey="expense" name="Debits (Outflow)" fill="#ef4444" radius={[4, 4, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '70%', color: '#94a3b8' }}>
                        <Typography variant="body2">No monthly breakdown available</Typography>
                      </Box>
                    )}
                  </Card>
                </Grid>
              </Grid>

              {/* Row: Top Merchants / Payees & ADVANCED SPENDING BY CATEGORY SUITE */}
              <Grid container spacing={3} sx={{ mb: 4 }}>
                
                {/* 1. TOP PAYEES & MERCHANTS CARD WITH CARD-SPECIFIC TOGGLE */}
                <Grid item xs={12} lg={5}>
                  <Card sx={{ p: 3, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 3, height: 490, display: 'flex', flexDirection: 'column' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5, flexWrap: 'wrap', gap: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <StorefrontIcon sx={{ color: merchantFlowTab === 'debit' ? '#f59e0b' : '#34d399', fontSize: 20 }} />
                        <Typography variant="h6" sx={{ fontWeight: 600 }}>
                          {merchantFlowTab === 'debit' ? 'Top Payees (Expenses)' : 'Top Inflows (Sources)'}
                        </Typography>
                      </Box>

                      {/* Card-Specific Toggle: Outflow vs Inflow */}
                      <Box sx={{ display: 'flex', background: 'rgba(255,255,255,0.04)', borderRadius: 2, p: 0.3, border: '1px solid rgba(255,255,255,0.08)' }}>
                        <Button
                          size="small"
                          onClick={() => setMerchantFlowTab('debit')}
                          sx={{
                            px: 1.2, py: 0.3, fontSize: '0.7rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: merchantFlowTab === 'debit' ? '#fff' : '#94a3b8',
                            backgroundColor: merchantFlowTab === 'debit' ? 'rgba(239, 68, 68, 0.25)' : 'transparent',
                            '&:hover': { backgroundColor: 'rgba(239, 68, 68, 0.35)' }
                          }}
                        >
                          Outflows
                        </Button>
                        <Button
                          size="small"
                          onClick={() => setMerchantFlowTab('credit')}
                          sx={{
                            px: 1.2, py: 0.3, fontSize: '0.7rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: merchantFlowTab === 'credit' ? '#fff' : '#94a3b8',
                            backgroundColor: merchantFlowTab === 'credit' ? 'rgba(16, 185, 129, 0.25)' : 'transparent',
                            '&:hover': { backgroundColor: 'rgba(16, 185, 129, 0.35)' }
                          }}
                        >
                          Inflows
                        </Button>
                      </Box>
                    </Box>
                    <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 2 }}>
                      {merchantFlowTab === 'debit' ? 'Highest debit spend recipients and frequencies' : 'Highest deposit and credit sources'}
                    </Typography>

                    {activeMerchantsList && activeMerchantsList.length > 0 ? (
                      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.2, overflowY: 'auto', pr: 1, flex: 1 }}>
                        {activeMerchantsList.map((m: any, idx: number) => {
                          const maxAmt = activeMerchantsList[0]?.amount || 1
                          const pct = (m.amount / maxAmt) * 100
                          const isDebit = merchantFlowTab === 'debit'
                          return (
                            <Box key={m.merchant} sx={{ p: 1.2, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 2 }}>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, overflow: 'hidden' }}>
                                  <Chip label={`#${idx + 1}`} size="small" sx={{ height: 18, fontSize: '0.65rem', fontWeight: 700, backgroundColor: isDebit ? 'rgba(245, 158, 11, 0.15)' : 'rgba(16, 185, 129, 0.15)', color: isDebit ? '#fbbf24' : '#34d399' }} />
                                  <Typography variant="body2" sx={{ fontWeight: 600, color: '#f1f5f9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 180 }}>
                                    {m.merchant}
                                  </Typography>
                                </Box>
                                <Box sx={{ textAlign: 'right' }}>
                                  <Typography variant="body2" sx={{ fontWeight: 700, color: isDebit ? '#f87171' : '#34d399' }}>
                                    {isDebit ? '-₹' : '+₹'}{m.amount.toLocaleString('en-IN')}
                                  </Typography>
                                  <Typography variant="caption" sx={{ color: '#94a3b8' }}>
                                    {m.count} {m.count === 1 ? 'payment' : 'payments'}
                                  </Typography>
                                </Box>
                              </Box>
                              <LinearProgress 
                                variant="determinate" 
                                value={pct} 
                                sx={{ 
                                  height: 4, 
                                  borderRadius: 2, 
                                  backgroundColor: 'rgba(255,255,255,0.04)',
                                  '& .MuiLinearProgress-bar': { backgroundColor: isDebit ? '#f59e0b' : '#10b981', borderRadius: 2 }
                                }} 
                              />
                            </Box>
                          )
                        })}
                      </Box>
                    ) : (
                      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flex: 1, color: '#94a3b8' }}>
                        <Typography variant="body2">No records matching filter</Typography>
                      </Box>
                    )}
                  </Card>
                </Grid>

                {/* 2. ADVANCED CATEGORY SPEND ANALYTICS (MULTI-CATEGORY VS DRILLDOWN) */}
                <Grid item xs={12} lg={7}>
                  <Card sx={{ p: 3, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 3, height: 490, display: 'flex', flexDirection: 'column' }}>
                    
                    {/* Header Row 1: Title, Category Selector Dropdown & Flow Tabs */}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                        <PieChartIcon sx={{ color: '#818cf8', fontSize: 20 }} />
                        <Typography variant="h6" sx={{ fontWeight: 600 }}>
                          {isCategoryDrilldown ? `${categoryFilter} Drilldown` : 'Category Spend Analytics'}
                        </Typography>

                        {/* In-Card Direct Category Selector Dropdown */}
                        <FormControl size="small">
                          <Select
                            value={categoryFilter}
                            onChange={(e) => setCategoryFilter(e.target.value)}
                            sx={{
                              height: 30,
                              fontSize: '0.78rem',
                              fontWeight: 600,
                              color: categoryFilter === 'all' ? '#cbd5e1' : '#f472b6',
                              backgroundColor: categoryFilter === 'all' ? 'rgba(255,255,255,0.04)' : 'rgba(236, 72, 153, 0.15)',
                              borderRadius: 1.8,
                              border: '1px solid',
                              borderColor: categoryFilter === 'all' ? 'rgba(255,255,255,0.1)' : 'rgba(236, 72, 153, 0.4)',
                              '& .MuiSelect-select': { py: 0.4, pr: 2.5 },
                              '& fieldset': { border: 'none' }
                            }}
                          >
                            <MenuItem value="all" sx={{ fontSize: '0.8rem' }}>🏷️ All Categories ({(categoryData.categories || []).length})</MenuItem>
                            {uniqueCategories.map((c: string) => {
                              const match = categoryByName.get(c.toLowerCase())
                              return (
                                <MenuItem key={c} value={c} sx={{ fontSize: '0.8rem', fontWeight: 600, display: 'flex', justifyContent: 'space-between', gap: 2 }}>
                                  <span>{c}</span>
                                  {match && (
                                    <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                                      ₹{match.amount >= 100000 ? `${(match.amount / 100000).toFixed(1)}L` : match.amount >= 1000 ? `${(match.amount / 1000).toFixed(0)}k` : match.amount}
                                    </span>
                                  )}
                                </MenuItem>
                              )
                            })}
                          </Select>
                        </FormControl>

                        {/* Back to All Categories button if drilldown */}
                        {isCategoryDrilldown && (
                          <Button
                            size="small"
                            startIcon={<ArrowBackIcon style={{ fontSize: 13 }} />}
                            onClick={() => setCategoryFilter('all')}
                            sx={{
                              height: 30,
                              fontSize: '0.72rem',
                              fontWeight: 600,
                              color: '#a5b4fc',
                              backgroundColor: 'rgba(99, 102, 241, 0.15)',
                              borderRadius: 1.8,
                              textTransform: 'none',
                              px: 1.2,
                              '&:hover': { backgroundColor: 'rgba(99, 102, 241, 0.25)' }
                            }}
                          >
                            All Categories
                          </Button>
                        )}
                      </Box>

                      {/* Flow Selector (Debits vs Credits) */}
                      <Box sx={{ display: 'flex', background: 'rgba(255,255,255,0.04)', borderRadius: 2, p: 0.3, border: '1px solid rgba(255,255,255,0.08)' }}>
                        <Button
                          size="small"
                          onClick={() => { setCategoryFlowTab('debit'); setCategoryNatureFilter('all') }}
                          sx={{
                            px: 1.2, py: 0.3, fontSize: '0.7rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: categoryFlowTab === 'debit' ? '#fff' : '#94a3b8',
                            backgroundColor: categoryFlowTab === 'debit' ? 'rgba(99, 102, 241, 0.35)' : 'transparent',
                            '&:hover': { backgroundColor: 'rgba(99, 102, 241, 0.45)' }
                          }}
                        >
                          Debits
                        </Button>
                        <Button
                          size="small"
                          onClick={() => { setCategoryFlowTab('credit'); setCategoryNatureFilter('all') }}
                          sx={{
                            px: 1.2, py: 0.3, fontSize: '0.7rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: categoryFlowTab === 'credit' ? '#fff' : '#94a3b8',
                            backgroundColor: categoryFlowTab === 'credit' ? 'rgba(16, 185, 129, 0.35)' : 'transparent',
                            '&:hover': { backgroundColor: 'rgba(16, 185, 129, 0.45)' }
                          }}
                        >
                          Credits
                        </Button>
                      </Box>
                    </Box>

                    {/* VIEW A: SPECIFIC CATEGORY DRILLDOWN MODE */}
                    {isCategoryDrilldown && drilldownStats ? (
                      <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
                        {/* Category KPI Metric Pills */}
                        <Grid container spacing={1.5} sx={{ mb: 2 }}>
                          <Grid item xs={6} sm={3}>
                            <Box sx={{ p: 1.2, background: 'rgba(236, 72, 153, 0.08)', border: '1px solid rgba(236, 72, 153, 0.2)', borderRadius: 2 }}>
                              <Typography variant="caption" sx={{ color: '#f472b6', display: 'block' }}>Total Spent</Typography>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#fff' }}>
                                ₹{drilldownStats.amount.toLocaleString('en-IN')}
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Box sx={{ p: 1.2, background: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.2)', borderRadius: 2 }}>
                              <Typography variant="caption" sx={{ color: '#a5b4fc', display: 'block' }}>% of Total Spend</Typography>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#fff' }}>
                                {drilldownStats.percentage_of_total.toFixed(1)}%
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Box sx={{ p: 1.2, background: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.2)', borderRadius: 2 }}>
                              <Typography variant="caption" sx={{ color: '#38bdf8', display: 'block' }}>Txn Count</Typography>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#fff' }}>
                                {drilldownStats.count} txns
                              </Typography>
                            </Box>
                          </Grid>
                          <Grid item xs={6} sm={3}>
                            <Box sx={{ p: 1.2, background: 'rgba(52, 211, 153, 0.08)', border: '1px solid rgba(52, 211, 153, 0.2)', borderRadius: 2 }}>
                              <Typography variant="caption" sx={{ color: '#34d399', display: 'block' }}>Avg Ticket Size</Typography>
                              <Typography variant="subtitle1" sx={{ fontWeight: 700, color: '#fff' }}>
                                ₹{drilldownStats.avg_ticket.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                              </Typography>
                            </Box>
                          </Grid>
                        </Grid>

                        {/* Drilldown Merchants Breakdown (Donut + Ranked List) */}
                        {drilldownStats.merchants && drilldownStats.merchants.length > 0 ? (
                          <Box sx={{ display: 'flex', flex: 1, flexDirection: { xs: 'column', sm: 'row' }, alignItems: 'center', gap: 2, overflow: 'hidden' }}>
                            {/* Merchant Donut Chart */}
                            <Box sx={{ width: { xs: '100%', sm: '42%' }, height: 210 }}>
                              <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                  <Pie
                                    data={drilldownStats.merchants}
                                    dataKey="amount"
                                    nameKey="merchant"
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={48}
                                    outerRadius={78}
                                    paddingAngle={3}
                                  >
                                    {drilldownStats.merchants.map((_: any, index: number) => (
                                      <Cell key={`mcell-${index}`} fill={MERCHANT_COLORS[index % MERCHANT_COLORS.length]} stroke="rgba(0,0,0,0.5)" />
                                    ))}
                                  </Pie>
                                  <RechartsTooltip 
                                    formatter={(value: number, name: string) => [`₹${value.toLocaleString('en-IN')}`, name]}
                                    contentStyle={{ backgroundColor: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} 
                                  />
                                </PieChart>
                              </ResponsiveContainer>
                            </Box>

                            {/* Merchant List */}
                            <Box sx={{ width: { xs: '100%', sm: '58%' }, height: '100%', maxHeight: 220, overflowY: 'auto', pr: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
                              <Typography variant="caption" sx={{ color: '#94a3b8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 0.5 }}>
                                Payees / Merchants for {categoryFilter}
                              </Typography>
                              {drilldownStats.merchants.map((m: any, idx: number) => {
                                const mColor = MERCHANT_COLORS[idx % MERCHANT_COLORS.length]
                                return (
                                  <Box key={m.merchant} sx={{ p: 1, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)' }}>
                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.4 }}>
                                      <Typography variant="caption" sx={{ fontWeight: 700, color: '#f8fafc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140 }}>
                                        {m.merchant}
                                      </Typography>
                                      <Box sx={{ textAlign: 'right' }}>
                                        <Typography variant="caption" sx={{ fontWeight: 700, color: '#fff' }}>
                                          ₹{m.amount.toLocaleString('en-IN')}
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: '#94a3b8', ml: 0.8, fontSize: '0.68rem' }}>
                                          ({m.percentage.toFixed(0)}%)
                                        </Typography>
                                      </Box>
                                    </Box>
                                    <LinearProgress 
                                      variant="determinate" 
                                      value={m.percentage} 
                                      sx={{ 
                                        height: 4, 
                                        borderRadius: 2, 
                                        backgroundColor: 'rgba(255,255,255,0.05)',
                                        '& .MuiLinearProgress-bar': { backgroundColor: mColor, borderRadius: 2 }
                                      }} 
                                    />
                                  </Box>
                                )
                              })}
                            </Box>
                          </Box>
                        ) : (
                          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flex: 1, color: '#94a3b8' }}>
                            <Typography variant="body2">No payees found in this category</Typography>
                          </Box>
                        )}
                      </Box>
                    ) : (
                      /* VIEW B: OVERALL MULTI-CATEGORY MODE */
                      <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
                        {/* Direct Dynamic Category Filter Pills + Mini Search & Sort */}
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 1.2 }}>
                          {/* Quick Clickable Category Pills */}
                          <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap', alignItems: 'center', flex: 1, minWidth: 240 }}>
                            {/* "All" Button */}
                            <Chip
                              size="small"
                              label={`All (${(categoryData.categories || []).length})`}
                              clickable
                              onClick={() => setCategoryFilter('all')}
                              sx={{
                                height: 26,
                                fontSize: '0.72rem',
                                fontWeight: categoryFilter === 'all' ? 700 : 500,
                                backgroundColor: categoryFilter === 'all' ? '#6366f1' : 'rgba(255,255,255,0.03)',
                                color: categoryFilter === 'all' ? '#fff' : '#94a3b8',
                                border: '1px solid',
                                borderColor: categoryFilter === 'all' ? '#818cf8' : 'rgba(255,255,255,0.08)'
                              }}
                            />

                            {/* Direct Category Badges with Live Amount & Color Dot */}
                            {(categoryData.categories || []).map((cat: any, idx: number) => {
                              const isSel = categoryFilter.toLowerCase() === cat.category.toLowerCase()
                              const catColor = CATEGORY_COLORS[idx % CATEGORY_COLORS.length]
                              const formattedAmt = cat.amount >= 100000 
                                ? `₹${(cat.amount / 100000).toFixed(1)}L` 
                                : cat.amount >= 1000 
                                  ? `₹${(cat.amount / 1000).toFixed(0)}k` 
                                  : `₹${cat.amount.toLocaleString('en-IN')}`

                              return (
                                <Chip
                                  key={cat.category}
                                  size="small"
                                  icon={<span style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: catColor, marginLeft: 6, marginRight: -4, display: 'inline-block' }} />}
                                  label={`${cat.category} • ${formattedAmt}`}
                                  clickable
                                  onClick={() => setCategoryFilter(isSel ? 'all' : cat.category)}
                                  sx={{
                                    height: 26,
                                    fontSize: '0.72rem',
                                    fontWeight: isSel ? 700 : 500,
                                    backgroundColor: isSel ? `${catColor}25` : 'rgba(255,255,255,0.03)',
                                    color: isSel ? '#fff' : '#cbd5e1',
                                    border: '1px solid',
                                    borderColor: isSel ? catColor : 'rgba(255,255,255,0.08)',
                                    '&:hover': { backgroundColor: 'rgba(255,255,255,0.08)' }
                                  }}
                                />
                              )
                            })}
                          </Box>

                          {/* Mini Category Filter Search + Sort Control */}
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 'auto' }}>
                            <TextField
                              size="small"
                              placeholder="Search category..."
                              value={categorySearch}
                              onChange={(e) => setCategorySearch(e.target.value)}
                              sx={{
                                width: 135,
                                '& .MuiOutlinedInput-root': {
                                  backgroundColor: 'rgba(255,255,255,0.03)',
                                  borderRadius: 1.5,
                                  color: '#fff',
                                  fontSize: '0.75rem',
                                  height: 26,
                                  '& fieldset': { borderColor: 'rgba(255,255,255,0.08)' }
                                }
                              }}
                            />

                            <FormControl size="small">
                              <Select
                                value={categorySortBy}
                                onChange={(e) => setCategorySortBy(e.target.value as any)}
                                sx={{
                                  height: 26,
                                  fontSize: '0.7rem',
                                  color: '#cbd5e1',
                                  backgroundColor: 'rgba(255,255,255,0.03)',
                                  borderRadius: 1.5,
                                  '& fieldset': { borderColor: 'rgba(255,255,255,0.08)' }
                                }}
                              >
                                <MenuItem value="amount" sx={{ fontSize: '0.75rem' }}>Amount (₹)</MenuItem>
                                <MenuItem value="count" sx={{ fontSize: '0.75rem' }}>Txn Count</MenuItem>
                                <MenuItem value="name" sx={{ fontSize: '0.75rem' }}>Name (A-Z)</MenuItem>
                              </Select>
                            </FormControl>
                          </Box>
                        </Box>

                        {/* Donut & Interactive Ranked List */}
                        {processedCategories.length > 0 ? (
                          <Box sx={{ display: 'flex', flex: 1, flexDirection: { xs: 'column', sm: 'row' }, alignItems: 'center', gap: 2, overflow: 'hidden' }}>
                            {/* Donut Chart */}
                            <Box sx={{ width: { xs: '100%', sm: '42%' }, height: 210 }}>
                              <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                  <Pie
                                    data={donutData}
                                    dataKey="amount"
                                    nameKey="category"
                                    cx="50%"
                                    cy="50%"
                                    innerRadius={48}
                                    outerRadius={78}
                                    /* Scaled to the slice count: a fixed 3 degrees is
                                       fine for 4 slices and eats a quarter of the
                                       circle at 10. */
                                    paddingAngle={donutData.length > 6 ? 1 : 3}
                                    minAngle={2}
                                  >
                                    {donutData.map((entry: any, index: number) => (
                                      <Cell
                                        key={`cell-${entry.category}`}
                                        fill={entry.isOther ? OTHER_COLOR : CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                                        stroke="rgba(0,0,0,0.5)"
                                      />
                                    ))}
                                  </Pie>
                                  <RechartsTooltip 
                                    formatter={(value: number, name: string) => [`₹${value.toLocaleString('en-IN')}`, name]}
                                    contentStyle={{ backgroundColor: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} 
                                  />
                                </PieChart>
                              </ResponsiveContainer>
                            </Box>

                            {/* Interactive Ranked Category Breakdown */}
                            <Box sx={{ width: { xs: '100%', sm: '58%' }, height: '100%', maxHeight: 220, overflowY: 'auto', pr: 1, display: 'flex', flexDirection: 'column', gap: 1 }}>
                              {processedCategories.map((cat: any, idx: number) => {
                                const pct = totalFilteredCategoryAmount > 0 ? (cat.amount / totalFilteredCategoryAmount) * 100 : 0
                                // Matches the donut: rows inside the top N carry their
                                // slice colour, the tail carries the "Other" grey it was
                                // merged into. Previously this wrapped the palette every
                                // 10 rows, so row 11 was the same colour as row 1 and the
                                // list stopped being a legend for the chart beside it.
                                const inDonut = processedCategories.length <= DONUT_SLICES || idx < DONUT_SLICES - 1
                                const color = inDonut ? CATEGORY_COLORS[idx % CATEGORY_COLORS.length] : OTHER_COLOR
                                const isCatSelected = categoryFilter.toLowerCase() === cat.category.toLowerCase()
                                const natureEmoji = cat.nature === 'needs' ? '🛡️' : cat.nature === 'wants' ? '🎯' : cat.nature === 'investments' ? '📈' : '🏷️'
                                
                                return (
                                  <Box 
                                    key={cat.category}
                                    onClick={() => setCategoryFilter(isCatSelected ? 'all' : cat.category)}
                                    sx={{ 
                                      cursor: 'pointer', 
                                      p: 0.9, 
                                      borderRadius: 2, 
                                      backgroundColor: isCatSelected ? 'rgba(99, 102, 241, 0.15)' : 'rgba(255,255,255,0.02)',
                                      border: '1px solid',
                                      borderColor: isCatSelected ? '#818cf8' : 'rgba(255,255,255,0.04)',
                                      transition: 'all 0.15s ease',
                                      '&:hover': { backgroundColor: 'rgba(255,255,255,0.05)', borderColor: color } 
                                    }}
                                  >
                                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.3 }}>
                                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, overflow: 'hidden' }}>
                                        <span style={{ fontSize: '0.8rem' }}>{natureEmoji}</span>
                                        <Typography variant="caption" sx={{ fontWeight: 700, color: isCatSelected ? color : '#f8fafc', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 140 }}>
                                          {cat.category}
                                        </Typography>
                                        {cat.count && (
                                          <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.68rem' }}>
                                            ({cat.count} txns)
                                          </Typography>
                                        )}
                                      </Box>
                                      <Box sx={{ textAlign: 'right' }}>
                                        <Typography variant="caption" sx={{ fontWeight: 700, color: isCatSelected ? color : '#fff' }}>
                                          ₹{cat.amount.toLocaleString('en-IN')}
                                        </Typography>
                                        <Typography variant="caption" sx={{ color: '#94a3b8', ml: 0.8, fontSize: '0.68rem' }}>
                                          ({pct.toFixed(0)}%)
                                        </Typography>
                                      </Box>
                                    </Box>
                                    <LinearProgress 
                                      variant="determinate" 
                                      value={pct} 
                                      sx={{ 
                                        height: 4, 
                                        borderRadius: 2, 
                                        backgroundColor: 'rgba(255,255,255,0.05)',
                                        '& .MuiLinearProgress-bar': { backgroundColor: color, borderRadius: 2 }
                                      }} 
                                    />
                                    {cat.top_merchants && cat.top_merchants.length > 0 && (
                                      <Typography variant="caption" sx={{ color: '#64748b', fontSize: '0.65rem', display: 'block', mt: 0.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        Top: {cat.top_merchants.map((m: any) => m.name).join(', ')}
                                      </Typography>
                                    )}
                                  </Box>
                                )
                              })}
                            </Box>
                          </Box>
                        ) : (
                          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flex: 1, color: '#94a3b8' }}>
                            <Typography variant="body2">No categories matching selection</Typography>
                          </Box>
                        )}
                      </Box>
                    )}
                  </Card>
                </Grid>
              </Grid>

              {/* Row: Day of Week Spend Pattern & Subscriptions / Alerts */}
              <Grid container spacing={3}>
                {/* 3. DAY OF WEEK SPEND WITH METRIC SWITCHER */}
                <Grid item xs={12} lg={6}>
                  <Card sx={{ p: 3, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 3, height: '100%' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5, flexWrap: 'wrap', gap: 1 }}>
                      <Typography variant="h6" sx={{ fontWeight: 600 }}>Spending by Day of Week</Typography>
                      
                      {/* Metric Switcher: Spend vs Txn Count vs Avg Spend */}
                      <Box sx={{ display: 'flex', background: 'rgba(255,255,255,0.04)', borderRadius: 2, p: 0.3, border: '1px solid rgba(255,255,255,0.08)' }}>
                        <Button
                          size="small"
                          onClick={() => setDowMetric('spend')}
                          sx={{
                            px: 1, py: 0.2, fontSize: '0.68rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: dowMetric === 'spend' ? '#fff' : '#94a3b8',
                            backgroundColor: dowMetric === 'spend' ? '#6366f1' : 'transparent',
                          }}
                        >
                          Total ₹
                        </Button>
                        <Button
                          size="small"
                          onClick={() => setDowMetric('count')}
                          sx={{
                            px: 1, py: 0.2, fontSize: '0.68rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: dowMetric === 'count' ? '#fff' : '#94a3b8',
                            backgroundColor: dowMetric === 'count' ? '#6366f1' : 'transparent',
                          }}
                        >
                          Txn Count
                        </Button>
                        <Button
                          size="small"
                          onClick={() => setDowMetric('avg_spend')}
                          sx={{
                            px: 1, py: 0.2, fontSize: '0.68rem', fontWeight: 600, textTransform: 'none', borderRadius: 1.5,
                            color: dowMetric === 'avg_spend' ? '#fff' : '#94a3b8',
                            backgroundColor: dowMetric === 'avg_spend' ? '#6366f1' : 'transparent',
                          }}
                        >
                          Avg ₹/Txn
                        </Button>
                      </Box>
                    </Box>
                    <Typography variant="caption" sx={{ color: '#94a3b8', display: 'block', mb: 2 }}>
                      {dowMetric === 'spend' ? 'Total debit volume per day of week' : dowMetric === 'count' ? 'Number of transactions executed per weekday' : 'Average spend ticket per day'}
                    </Typography>
                    {overview.day_of_week_spend && overview.day_of_week_spend.length > 0 ? (
                      <ResponsiveContainer width="100%" height={250}>
                        <BarChart data={overview.day_of_week_spend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                          <XAxis dataKey="day" stroke="rgba(255,255,255,0.4)" fontSize={12} />
                          <YAxis 
                            stroke="rgba(255,255,255,0.4)" 
                            fontSize={12} 
                            tickFormatter={(v) => dowMetric === 'count' ? v : `₹${v >= 1000 ? `${(v/1000).toFixed(0)}k` : v}`} 
                          />
                          <RechartsTooltip 
                            formatter={(value: number) => dowMetric === 'count' ? [`${value} transactions`, 'Count'] : [`₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`, dowMetric === 'avg_spend' ? 'Avg Spend/Txn' : 'Total Spend']}
                            contentStyle={{ backgroundColor: '#0f172a', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }} 
                          />
                          <Bar 
                            dataKey={dowMetric} 
                            name={dowMetric === 'count' ? 'Transaction Count' : dowMetric === 'avg_spend' ? 'Avg Spend' : 'Total Spend'} 
                            fill={dowMetric === 'count' ? '#38bdf8' : '#6366f1'} 
                            radius={[4, 4, 0, 0]} 
                          />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200, color: '#94a3b8' }}>
                        <Typography variant="body2">No day-of-week data</Typography>
                      </Box>
                    )}
                  </Card>
                </Grid>

                {/* Spend Acceleration Alert & Detected Subscriptions */}
                <Grid item xs={12} lg={6}>
                  <Stack spacing={2.5} sx={{ height: '100%' }}>
                    {overview.biggest_change && (
                      <Card sx={{ p: 2.5, background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(239, 68, 68, 0.02) 100%)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: 3 }}>
                        <Typography variant="caption" sx={{ color: '#f87171', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                          ⚠️ Spend Acceleration Alert
                        </Typography>
                        <Typography variant="h6" sx={{ fontWeight: 700, color: '#fff', mt: 0.5 }}>{overview.biggest_change.category}</Typography>
                        <Typography variant="body2" sx={{ color: '#cbd5e1', mt: 0.5 }}>
                          Outflow in this category expanded by <strong style={{ color: '#f87171' }}>₹{overview.biggest_change.increase_amount.toLocaleString('en-IN')}</strong> compared to the previous 30-day window.
                        </Typography>
                      </Card>
                    )}
                    
                    {overview.recurring_charges && overview.recurring_charges.length > 0 && (
                      <Card sx={{ p: 2.5, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 3, flex: 1 }}>
                        <Typography variant="caption" sx={{ color: '#818cf8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, display: 'block', mb: 1.5 }}>
                          🔄 Detected Subscriptions & Recurring Charges
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                          {/* Grouped server-side by (description, amount), so that pair
                              is the stable identity - the index was not. */}
                          {overview.recurring_charges.slice(0, 4).map((rc: any) => (
                            <Box key={`${rc.description}-${rc.amount}`} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 1.2, background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.04)', borderRadius: 2 }}>
                              <Box sx={{ overflow: 'hidden', mr: 2 }}>
                                <Typography variant="body2" sx={{ fontWeight: 600, color: '#f1f5f9', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: 200 }}>
                                  {rc.description}
                                </Typography>
                                <Typography variant="caption" sx={{ color: '#94a3b8' }}>Recurring pattern</Typography>
                              </Box>
                              <Box sx={{ textAlign: 'right', minWidth: 80 }}>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: '#f87171' }}>₹{rc.amount.toLocaleString('en-IN')}</Typography>
                                <Typography variant="caption" sx={{ color: '#94a3b8' }}>{rc.frequency} payments</Typography>
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      </Card>
                    )}
                  </Stack>
                </Grid>
              </Grid>

              {/* Income -> needs/wants/investments -> categories. The most legible way
                  to show a budget, and the thing the donut cannot say. */}
              <MoneyFlowCard sessionId={sessionId} />
            </Box>
          )}

          {/* TAB 1: TRANSACTIONS */}
          {activeTab === 1 && (
            <TransactionsTab
              transactions={transactions}
              uniqueBanks={uniqueBanks}
              onTransactionsUpdated={refreshAllData}
              totalAvailable={transactionsTotal}
              truncated={transactionsTruncated}
            />
          )}

          {/* TAB 2: ACCOUNTS & CARDS */}
          {/* Mounted only when selected. Each of these tabs owns several queries, and
              the hooks are `enabled` off their own mount - a tab the user never opens
              should cost nothing. */}
          {activeTab === 2 && <AccountsTab sessionId={sessionId} />}

          {/* TAB 3: INSIGHTS */}
          {activeTab === 3 && <InsightsTab sessionId={sessionId} />}

          {/* TAB 4: RULES ENGINE */}
          {activeTab === 4 && (
            <RulesTab onRulesApplied={refreshAllData} />
          )}
        </>
      )}

      {/* Statement Sessions & History Modal */}
      <BudgetSessionsModal
        open={isSessionsModalOpen}
        onClose={closeSessionsModal}
        sessions={sessionsList}
        activeSessionId={sessionId}
        onSelectSession={selectSession}
        onDeleteSession={handleDeleteSession}
      />

      {/* Explicit Bank & Account Type Upload Modal */}
      <UploadStatementModal
        open={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onUpload={handleModalUpload}
        loading={uploadMutation.isPending}
      />
    </Box>
  )
}
