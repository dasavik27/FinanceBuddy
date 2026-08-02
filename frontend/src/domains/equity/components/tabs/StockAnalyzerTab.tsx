import React, { useMemo, useState } from 'react'
import {
  Box,
  Typography,
  Paper,
  TextField,
  Button,
  CircularProgress,
  Alert,
  Grid,
  Chip,
  InputAdornment,
  Autocomplete,
  IconButton,
  Tooltip,
  Checkbox,
  FormControlLabel,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import AutoGraphIcon from '@mui/icons-material/AutoGraph'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import SpeedIcon from '@mui/icons-material/Speed'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import StarIcon from '@mui/icons-material/Star'
import StarBorderIcon from '@mui/icons-material/StarBorder'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import AssessmentIcon from '@mui/icons-material/Assessment'
import MonetizationOnIcon from '@mui/icons-material/MonetizationOn'
import BarChartIcon from '@mui/icons-material/BarChart'
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline'
import CloseIcon from '@mui/icons-material/Close'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import CalendarMonthIcon from '@mui/icons-material/CalendarMonth'
import ArrowDropUpIcon from '@mui/icons-material/ArrowDropUp'
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  Legend,
  ReferenceLine,
  CartesianGrid,
} from 'recharts'

import { apiClient } from '../../../../shared/api/client'
import { useDebounce } from '../../../../shared/hooks/useDebounce'
import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import { useEquitySessionId, useStockSearch } from '../../hooks/useEquityData'
import {
  useStockAnalyzerStore,
  type GoogleFinanceSubTab,
  type ChartTimeframe,
  type ChartDisplayType,
} from '../../hooks/useStockAnalyzerStore'
import type {
  StockSearchResult,
  StockAnalysis,
  PeerStock,
  QuarterlyEarnings,
  IncomeStatementItem,
  BalanceSheetItem,
  CashFlowItem,
  EarningsHistoryItem,
} from '../../types'
import { MarketIndicesRibbon } from '../MarketIndicesRibbon'

const fmtINR = fmtInr
const COMPARE_COLORS = ['#38BDF8', '#F59E0B', '#EC4899', '#8B5CF6'] // Sky Blue, Amber, Pink, Purple

const CASH_FLOW_CONFIG: Record<string, { label: string; color: string }> = {
  cash_from_operations_cr: { label: 'Cash from operations', color: '#38BDF8' },
  cash_from_investing_cr: { label: 'Cash from investing', color: '#2DD4BF' },
  cash_from_financing_cr: { label: 'Cash from financing', color: '#A855F7' },
  net_change_in_cash_cr: { label: 'Net change in cash', color: '#F59E0B' },
  free_cash_flow_cr: { label: 'Free cash flow', color: '#10B981' },
}

const INCOME_STMT_CONFIG: Record<string, { label: string; color: string }> = {
  revenue_cr: { label: 'Revenue', color: '#38BDF8' },
  net_income_cr: { label: 'Net income', color: '#10B981' },
  operating_expense_cr: { label: 'Operating expense', color: '#F43F5E' },
  ebitda_cr: { label: 'EBITDA', color: '#F59E0B' },
}

const BALANCE_SHEET_CONFIG: Record<string, { label: string; color: string }> = {
  total_assets_cr: { label: 'Total assets', color: '#38BDF8' },
  total_liabilities_cr: { label: 'Total liabilities', color: '#F43F5E' },
  cash_and_equivalents_cr: { label: 'Cash & short-term investments', color: '#10B981' },
  total_equity_cr: { label: 'Total equity', color: '#A855F7' },
}

function fmtCr(v?: number | null) {
  if (v === null || v === undefined) return '—'
  if (v < 0) return `(₹${Math.abs(v).toLocaleString()} Cr)`
  return `₹${v.toLocaleString()} Cr`
}

function fmtPctVal(v?: number | null) {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function fmtLargeRev(v?: number | null) {
  if (v === null || v === undefined) return '—'
  if (Math.abs(v) >= 1000) {
    return `₹${(v / 1000).toFixed(2)}KCr`
  }
  return `₹${v.toFixed(2)}Cr`
}

function StatBox({
  label,
  value,
  subtext,
  highlight,
  color,
}: {
  label: string
  value: string | number
  subtext?: string
  highlight?: boolean
  color?: string
}) {
  return (
    <Box
      sx={{
        p: 2,
        background: highlight ? 'rgba(16,185,129,0.06)' : 'rgba(255,255,255,0.03)',
        border: highlight ? '1px solid rgba(16,185,129,0.2)' : '1px solid rgba(255,255,255,0.05)',
        borderRadius: '14px',
        transition: 'all 0.2s ease',
        '&:hover': {
          background: 'rgba(255,255,255,0.06)',
          borderColor: 'rgba(255,255,255,0.12)',
        },
      }}
    >
      <Typography sx={{ color: '#94A3B8', fontSize: '0.76rem', fontWeight: 600, mb: 0.5 }}>
        {label}
      </Typography>
      <Typography sx={{ color: color ?? '#F8FAFC', fontWeight: 800, fontSize: '1.05rem', letterSpacing: '-0.01em' }}>
        {value}
      </Typography>
      {subtext && (
        <Typography sx={{ color: '#64748B', fontSize: '0.72rem', mt: 0.5, fontWeight: 500 }}>
          {subtext}
        </Typography>
      )}
    </Box>
  )
}

function RangeSliderBar({
  label,
  low,
  high,
  current,
}: {
  label: string
  low?: number | null
  high?: number | null
  current?: number | null
}) {
  if (!low || !high || !current || high <= low) {
    return null
  }

  const pct = Math.min(100, Math.max(0, ((current - low) / (high - low)) * 100))

  return (
    <Box sx={{ mb: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5, fontSize: '0.76rem' }}>
        <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: 'inherit' }}>{label}</Typography>
        <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: 'inherit' }}>
          {fmtINR(current)}
        </Typography>
      </Box>
      <Box sx={{ position: 'relative', height: 8, bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 4 }}>
        <Box
          sx={{
            position: 'absolute',
            left: 0,
            width: `${pct}%`,
            height: '100%',
            bgcolor: 'rgba(16,185,129,0.5)',
            borderRadius: 4,
          }}
        />
        <Box
          sx={{
            position: 'absolute',
            left: `calc(${pct}% - 5px)`,
            top: -3,
            width: 14,
            height: 14,
            borderRadius: '50%',
            bgcolor: '#10B981',
            border: '2px solid #0F172A',
            boxShadow: '0 0 6px rgba(16,185,129,0.8)',
          }}
        />
      </Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.5, fontSize: '0.7rem', color: '#64748B' }}>
        <span>Low: {fmtINR(low)}</span>
        <span>High: {fmtINR(high)}</span>
      </Box>
    </Box>
  )
}

export default function StockAnalyzerTab() {
  const sessionId = useEquitySessionId()
  const {
    query,
    selectedStock,
    stock,
    impactAmount,
    impact,
    analysisError,
    activeSubTab,
    activeTimeframe,
    chartType,
    compareBenchmark,
    compareStocks,
    watchlist,
    setQuery,
    setSelectedStock,
    setStock,
    setImpactAmount,
    setImpact,
    setAnalysisError,
    setActiveSubTab,
    setActiveTimeframe,
    setChartType,
    setCompareBenchmark,
    addCompareStock,
    removeCompareStock,
    clearCompareStocks,
    toggleWatchlist,
    clear,
  } = useStockAnalyzerStore()

  // Main Search
  const debouncedQuery = useDebounce(query, 300)
  const { data: searchData, isFetching: searching } = useStockSearch(debouncedQuery)
  const options: StockSearchResult[] = searchData?.results ?? []

  // Compare Search
  const [compareQuery, setCompareQuery] = useState('')
  const debouncedCompareQuery = useDebounce(compareQuery, 300)
  const { data: compareSearchData, isFetching: searchingCompare } = useStockSearch(debouncedCompareQuery)
  const compareOptions: StockSearchResult[] = (compareSearchData?.results ?? []).filter(
    (s) =>
      s.symbol.toUpperCase() !== stock?.symbol.toUpperCase() &&
      !compareStocks.some((cs) => cs.symbol.toUpperCase() === s.symbol.toUpperCase()),
  )

  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [loadingImpact, setLoadingImpact] = useState(false)
  const [loadingCompareStock, setLoadingCompareStock] = useState<string | null>(null)

  // Financial Statements & Earnings sub-tab state
  const [financialStmtType, setFinancialStmtType] = useState<'income_statement' | 'balance_sheet' | 'cash_flow'>('cash_flow')
  const [financialPeriodType, setFinancialPeriodType] = useState<'quarterly' | 'annual'>('quarterly')
  const [selectedCfMetrics, setSelectedCfMetrics] = useState<string[]>([
    'cash_from_operations_cr',
    'cash_from_investing_cr',
    'cash_from_financing_cr',
  ])
  const [selectedIncMetrics, setSelectedIncMetrics] = useState<string[]>([
    'revenue_cr',
    'net_income_cr',
  ])
  const [selectedBsMetrics, setSelectedBsMetrics] = useState<string[]>([
    'total_assets_cr',
    'total_liabilities_cr',
  ])

  const toggleCfMetric = (key: string) => {
    setSelectedCfMetrics((prev) =>
      prev.includes(key) ? (prev.length > 1 ? prev.filter((k) => k !== key) : prev) : [...prev, key]
    )
  }

  const toggleIncMetric = (key: string) => {
    setSelectedIncMetrics((prev) =>
      prev.includes(key) ? (prev.length > 1 ? prev.filter((k) => k !== key) : prev) : [...prev, key]
    )
  }

  const toggleBsMetric = (key: string) => {
    setSelectedBsMetrics((prev) =>
      prev.includes(key) ? (prev.length > 1 ? prev.filter((k) => k !== key) : prev) : [...prev, key]
    )
  }

  const handleImpact = async (symbol: string, amt: number) => {
    if (!sessionId || !amt || Number.isNaN(amt) || amt <= 0) return
    setLoadingImpact(true)
    try {
      const data = await apiClient.stockPortfolioImpact(symbol, amt, sessionId)
      setImpact(data)
    } catch (e) {
      console.error(e)
    } finally {
      setLoadingImpact(false)
    }
  }

  const handleSelect = async (val: StockSearchResult | null) => {
    if (!val) {
      clear()
      return
    }
    setSelectedStock(val)
    setQuery(`${val.symbol} - ${val.name}`)
    setLoadingAnalysis(true)
    setAnalysisError(null)
    try {
      const data = await apiClient.analyzeStock(val.symbol)
      setStock(data)
      if (sessionId) {
        void handleImpact(data.symbol, parseFloat(impactAmount))
      }
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status
      setAnalysisError(
        status === 404
          ? 'That symbol was not recognised.'
          : 'Could not load analysis for that stock. Please try again.',
      )
    } finally {
      setLoadingAnalysis(false)
    }
  }

  // Handle adding a stock to compare
  const handleAddCompareStock = async (symbol: string) => {
    const sym = symbol.toUpperCase().trim()
    if (!sym || sym === stock?.symbol.toUpperCase()) return
    if (compareStocks.some((cs) => cs.symbol.toUpperCase() === sym)) return

    setLoadingCompareStock(sym)
    try {
      const data = await apiClient.analyzeStock(sym)
      addCompareStock(data)
      setCompareQuery('')
    } catch (e) {
      console.error('Failed to load comparison stock', e)
    } finally {
      setLoadingCompareStock(null)
    }
  }

  // Active Timeframe Slice Computation
  const activeSlice = useMemo(() => {
    if (!stock) return null
    if (stock.timeframes && stock.timeframes[activeTimeframe]) {
      return stock.timeframes[activeTimeframe]
    }
    // Fallback standard chart data
    const dates = stock.chart?.dates ?? []
    const prices = stock.chart?.prices ?? []
    const st = prices[0] ?? 0
    const end = prices[prices.length - 1] ?? 0
    const chg = end - st
    const pchg = st ? (chg / st) * 100 : 0
    return {
      dates,
      prices,
      start_price: st,
      end_price: end,
      change: chg,
      p_change: pchg,
    }
  }, [stock, activeTimeframe])

  const chartData = useMemo(() => {
    if (!activeSlice) return []
    return activeSlice.dates.map((d: string, i: number) => ({
      date: d,
      price: activeSlice.prices[i] ?? null,
    }))
  }, [activeSlice])

  // Technical Indicators Series
  const technicalChartData = useMemo(() => {
    if (!stock?.chart) return []
    const dates = stock.chart.dates || []
    const prices = stock.chart.prices || []
    const sma50 = stock.technicals?.sma_50
    const sma200 = stock.technicals?.sma_200

    return dates.map((d: string, i: number) => {
      const p = prices[i] ?? null
      const candle = stock.candlesticks?.[i]
      const vol = stock.volume_series?.[i]
      return {
        date: d,
        price: p,
        sma_50: sma50,
        sma_200: sma200,
        open: candle?.open ?? p,
        high: candle?.high ?? p,
        low: candle?.low ?? p,
        close: candle?.close ?? p,
        volume: vol?.volume ?? 0,
        is_up: vol?.is_up ?? true,
      }
    })
  }, [stock])

  function round(val: number, dec = 2) {
    return Math.round(val * 10 ** dec) / 10 ** dec
  }

  // Multi-Stock Comparative Data (Normalized % Baseline)
  const compareData = useMemo(() => {
    if (!stock?.chart) return []
    const dates = stock.chart.dates || []
    const prices = stock.chart.prices || []
    const startPrice = prices[0] || 1
    const totalPoints = Math.max(1, dates.length - 1)

    return dates.map((d: string, i: number) => {
      const p = prices[i] || startPrice
      const stockPct = ((p - startPrice) / startPrice) * 100

      const row: Record<string, any> = {
        date: d,
        [stock.symbol]: round(stockPct, 2),
      }

      // Add each comparison stock's normalized series
      compareStocks.forEach((comp) => {
        const compDates = comp.chart?.dates || []
        const compPrices = comp.chart?.prices || []
        const compStart = compPrices[0] || 1
        // Align by date or approximate index ratio
        const dateIdx = compDates.indexOf(d)
        let compP = compStart
        if (dateIdx !== -1) {
          compP = compPrices[dateIdx] || compStart
        } else {
          const approxIdx = Math.min(compPrices.length - 1, Math.floor((i / totalPoints) * (compPrices.length - 1)))
          compP = compPrices[approxIdx] || compStart
        }
        const compPct = ((compP - compStart) / compStart) * 100
        row[comp.symbol] = round(compPct, 2)
      })

      // Optional Benchmark NIFTY 50 curve
      if (compareBenchmark) {
        const benchmarkPct = (i / totalPoints) * (stock.year_return ? stock.year_return * 0.55 : 12.4)
        row['NIFTY 50'] = round(benchmarkPct, 2)
      }

      return row
    })
  }, [stock, compareStocks, compareBenchmark])

  const timeframeChange = activeSlice?.change ?? 0
  const timeframePChange = activeSlice?.p_change ?? (stock?.year_return ?? 0)
  const isPositive = timeframeChange >= 0
  const returnColor = isPositive ? '#10B981' : '#EF4444'

  const isStarred = stock ? watchlist.includes(stock.symbol) : false

  const technicals = stock?.technicals
  const rsi = technicals?.rsi_14
  const rsiColor =
    rsi !== null && rsi !== undefined
      ? rsi < 30
        ? '#10B981'
        : rsi > 70
        ? '#EF4444'
        : '#38BDF8'
      : '#94A3B8'

  const trendColor =
    technicals?.trend === 'Strong Uptrend'
      ? '#10B981'
      : technicals?.trend === 'Uptrend'
      ? '#34D399'
      : technicals?.trend === 'Downtrend'
      ? '#EF4444'
      : '#F59E0B'

  const timeframesList: ChartTimeframe[] = ['1D', '5D', '1M', '6M', 'YTD', '1Y', '5Y']
  const subTabs: { id: GoogleFinanceSubTab; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <ShowChartIcon sx={{ fontSize: '1.1rem' }} /> },
    { id: 'indicators', label: 'Indicators', icon: <SpeedIcon sx={{ fontSize: '1.1rem' }} /> },
    { id: 'compare', label: 'Compare', icon: <CompareArrowsIcon sx={{ fontSize: '1.1rem' }} /> },
    { id: 'financials', label: 'Financials', icon: <MonetizationOnIcon sx={{ fontSize: '1.1rem' }} /> },
    { id: 'earnings', label: 'Earnings', icon: <BarChartIcon sx={{ fontSize: '1.1rem' }} /> },
  ]

  return (
    <Box sx={{ pb: 6 }}>
      {/* Top Market Indices Ribbon */}
      <MarketIndicesRibbon onSelectStock={handleSelect} />

      {/* Search Header */}
      <Box sx={{ maxWidth: 850, mx: 'auto', mb: 4 }}>
        <Autocomplete
          options={options}
          value={selectedStock}
          inputValue={query}
          getOptionLabel={(opt) => (typeof opt === 'string' ? opt : `${opt.symbol} - ${opt.name}`)}
          isOptionEqualToValue={(a, b) => a.symbol === b.symbol}
          filterOptions={(x) => x}
          clearOnBlur={false}
          onInputChange={(_, v, reason) => {
            if (reason === 'clear') {
              clear()
              return
            }
            if (reason === 'input') {
              setQuery(v)
              if (!v.trim()) {
                clear()
              }
            }
          }}
          onChange={(_, v, reason) => {
            if (reason === 'clear' || !v) {
              clear()
            } else if (typeof v !== 'string') {
              handleSelect(v)
            }
          }}
          loading={searching}
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Search Indian stocks (e.g. RELIANCE, TCS, INFY, HDFCBANK, TATAMOTORS)..."
              variant="outlined"
              fullWidth
              InputProps={{
                ...params.InputProps,
                startAdornment: <SearchIcon sx={{ color: '#64748B', ml: 1, mr: 1 }} />,
                sx: {
                  borderRadius: '16px',
                  background: 'rgba(15,23,42,0.85)',
                  backdropFilter: 'blur(12px)',
                  '& fieldset': { borderColor: 'rgba(16,185,129,0.3)' },
                  '&:hover fieldset': { borderColor: 'rgba(16,185,129,0.6)' },
                  '&.Mui-focused fieldset': { borderColor: '#10B981', borderWidth: 2 },
                  color: '#fff',
                  '& .MuiAutocomplete-clearIndicator': {
                    color: '#94A3B8',
                    '&:hover': { color: '#EF4444', bgcolor: 'rgba(239, 68, 68, 0.1)' },
                  },
                },
              }}
            />
          )}
        />
      </Box>

      {loadingAnalysis && (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', py: 10, gap: 2 }}>
          <CircularProgress sx={{ color: '#10B981' }} />
          <Typography sx={{ color: '#94A3B8', fontSize: '0.9rem', fontWeight: 600 }}>
            Fetching real-time market data from NSE & financial models...
          </Typography>
        </Box>
      )}

      {analysisError && !loadingAnalysis && (
        <Alert severity="error" sx={{ borderRadius: '16px', mb: 4, maxWidth: 850, mx: 'auto' }}>
          {analysisError}
        </Alert>
      )}

      {stock && !loadingAnalysis && (
        <Box>
          {/* ── Google Finance Header Banner ── */}
          <Paper
            sx={{
              p: { xs: 2.5, md: 3.5 },
              borderRadius: '20px',
              background: 'rgba(15,23,42,0.75)',
              border: '1px solid rgba(255,255,255,0.08)',
              backdropFilter: 'blur(16px)',
              mb: 3,
            }}
          >
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2 }}>
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Typography sx={{ fontWeight: 900, color: '#F8FAFC', fontSize: { xs: '1.4rem', md: '1.9rem' }, letterSpacing: '-0.02em' }}>
                    {stock.name}
                  </Typography>
                  <Button
                    onClick={() => toggleWatchlist(stock.symbol)}
                    sx={{
                      minWidth: 0,
                      p: 0.75,
                      borderRadius: '10px',
                      color: isStarred ? '#F59E0B' : '#64748B',
                      bgcolor: isStarred ? 'rgba(245,158,11,0.12)' : 'rgba(255,255,255,0.05)',
                      border: isStarred ? '1px solid rgba(245,158,11,0.3)' : '1px solid rgba(255,255,255,0.08)',
                      '&:hover': { bgcolor: 'rgba(245,158,11,0.2)' },
                    }}
                  >
                    {isStarred ? <StarIcon sx={{ fontSize: '1.2rem' }} /> : <StarBorderIcon sx={{ fontSize: '1.2rem' }} />}
                  </Button>
                </Box>
                <Box sx={{ display: 'flex', gap: 1, mt: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                  <Chip label={`NSE: ${stock.symbol}`} size="small" sx={{ background: 'rgba(16,185,129,0.12)', color: '#10B981', fontWeight: 800 }} />
                  <Chip label="NSE Live Terminal" size="small" sx={{ background: 'rgba(59,130,246,0.12)', color: '#38BDF8', fontWeight: 700 }} />
                  {stock.sector && (
                    <Chip label={stock.sector} size="small" sx={{ background: 'rgba(148,163,184,0.12)', color: '#94A3B8', fontWeight: 600 }} />
                  )}
                  {stock.isin && (
                    <Chip label={`ISIN: ${stock.isin}`} size="small" variant="outlined" sx={{ borderColor: 'rgba(255,255,255,0.08)', color: '#64748B', fontSize: '0.7rem' }} />
                  )}
                </Box>
              </Box>

              <Box sx={{ textAlign: { xs: 'left', sm: 'right' } }}>
                <Typography sx={{ fontWeight: 900, color: '#F8FAFC', fontSize: { xs: '1.6rem', md: '2.1rem' }, fontFamily: 'monospace' }}>
                  {fmtINR(stock.current_price)}
                </Typography>
                <Typography sx={{ color: returnColor, fontWeight: 800, fontSize: '0.95rem', display: 'flex', alignItems: 'center', justifyContent: { xs: 'flex-start', sm: 'flex-end' }, gap: 0.5 }}>
                  {isPositive ? <TrendingUpIcon fontSize="small" /> : <TrendingDownIcon fontSize="small" />}
                  {isPositive ? '+' : ''}{fmtINR(timeframeChange)} ({isPositive ? '+' : ''}{fmtNum(timeframePChange, 2)}%)
                  <span style={{ color: '#64748B', fontWeight: 500, marginLeft: 4 }}>past {activeTimeframe}</span>
                </Typography>
              </Box>
            </Box>

            {/* ── Sub-Tabs Navigation (Google Finance Style) ── */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1,
                mt: 3,
                pt: 2,
                borderTop: '1px solid rgba(255,255,255,0.06)',
                overflowX: 'auto',
              }}
            >
              {subTabs.map((tab) => {
                const isActive = activeSubTab === tab.id
                return (
                  <Button
                    key={tab.id}
                    onClick={() => setActiveSubTab(tab.id)}
                    startIcon={tab.icon}
                    sx={{
                      textTransform: 'none',
                      fontWeight: isActive ? 800 : 600,
                      fontSize: '0.88rem',
                      px: 2.2,
                      py: 0.8,
                      borderRadius: '12px',
                      color: isActive ? '#fff' : '#94A3B8',
                      bgcolor: isActive ? 'rgba(16,185,129,0.18)' : 'transparent',
                      border: isActive ? '1px solid rgba(16,185,129,0.4)' : '1px solid transparent',
                      '&:hover': {
                        bgcolor: isActive ? 'rgba(16,185,129,0.25)' : 'rgba(255,255,255,0.04)',
                        color: '#fff',
                      },
                    }}
                  >
                    {tab.label}
                  </Button>
                )
              })}
            </Box>
          </Paper>

          {/* ── TAB 1: OVERVIEW ── */}
          {activeSubTab === 'overview' && (
            <Grid container spacing={3.5}>
              <Grid item xs={12} lg={8}>
                <Paper
                  sx={{
                    p: { xs: 2.5, md: 3.5 },
                    borderRadius: '20px',
                    background: 'rgba(15,23,42,0.65)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    mb: 3.5,
                  }}
                >
                  {/* Timeframe & Chart Style Switchers */}
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3, flexWrap: 'wrap', gap: 1.5 }}>
                    <Box sx={{ display: 'flex', gap: 0.5, bgcolor: 'rgba(255,255,255,0.04)', p: 0.5, borderRadius: '12px' }}>
                      {timeframesList.map((tf) => {
                        const isTfActive = activeTimeframe === tf
                        return (
                          <Button
                            key={tf}
                            size="small"
                            onClick={() => setActiveTimeframe(tf)}
                            sx={{
                              minWidth: 42,
                              px: 1.2,
                              py: 0.4,
                              borderRadius: '8px',
                              fontSize: '0.78rem',
                              fontWeight: isTfActive ? 800 : 600,
                              color: isTfActive ? '#10B981' : '#94A3B8',
                              bgcolor: isTfActive ? 'rgba(16,185,129,0.15)' : 'transparent',
                              '&:hover': { bgcolor: 'rgba(255,255,255,0.08)', color: '#fff' },
                            }}
                          >
                            {tf}
                          </Button>
                        )
                      })}
                    </Box>

                    {/* Chart Display Mode Switcher */}
                    <Box sx={{ display: 'flex', gap: 0.5, bgcolor: 'rgba(255,255,255,0.04)', p: 0.5, borderRadius: '12px' }}>
                      {(['area', 'line'] as ChartDisplayType[]).map((type) => (
                        <Button
                          key={type}
                          size="small"
                          onClick={() => setChartType(type)}
                          sx={{
                            textTransform: 'capitalize',
                            px: 1.5,
                            py: 0.4,
                            borderRadius: '8px',
                            fontSize: '0.75rem',
                            fontWeight: chartType === type ? 800 : 600,
                            color: chartType === type ? '#38BDF8' : '#94A3B8',
                            bgcolor: chartType === type ? 'rgba(56,189,248,0.15)' : 'transparent',
                          }}
                        >
                          {type}
                        </Button>
                      ))}
                    </Box>
                  </Box>

                  {/* Main Interactive Chart */}
                  {chartData.length > 0 && (
                    <Box sx={{ height: 260, mb: 4 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        {chartType === 'area' ? (
                          <AreaChart data={chartData}>
                            <defs>
                              <linearGradient id="colorStockPrice" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor={returnColor} stopOpacity={0.4} />
                                <stop offset="95%" stopColor={returnColor} stopOpacity={0.0} />
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                            <XAxis dataKey="date" stroke="#64748B" fontSize={11} tickLine={false} />
                            <YAxis
                              stroke="#64748B"
                              fontSize={11}
                              domain={['auto', 'auto']}
                              tickFormatter={(v) => `₹${v}`}
                              orientation="right"
                            />
                            <RechartsTooltip
                              contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                              labelStyle={{ color: '#94A3B8', fontWeight: 600 }}
                              formatter={(v: number) => [fmtINR(v), 'Price']}
                            />
                            <Area type="monotone" dataKey="price" stroke={returnColor} strokeWidth={2.5} fill="url(#colorStockPrice)" />
                          </AreaChart>
                        ) : (
                          <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                            <XAxis dataKey="date" stroke="#64748B" fontSize={11} tickLine={false} />
                            <YAxis stroke="#64748B" fontSize={11} domain={['auto', 'auto']} tickFormatter={(v) => `₹${v}`} orientation="right" />
                            <RechartsTooltip
                              contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                              labelStyle={{ color: '#94A3B8' }}
                              formatter={(v: number) => [fmtINR(v), 'Price']}
                            />
                            <Line type="monotone" dataKey="price" stroke={returnColor} strokeWidth={2.5} dot={false} />
                          </LineChart>
                        )}
                      </ResponsiveContainer>
                    </Box>
                  )}

                  {/* Range Sliders */}
                  <Box sx={{ p: 2.5, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.04)', mb: 3.5 }}>
                    <Grid container spacing={3}>
                      <Grid item xs={12} sm={6}>
                        <RangeSliderBar
                          label="Day's Range"
                          low={stock.day_low}
                          high={stock.day_high}
                          current={stock.current_price}
                        />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <RangeSliderBar
                          label="52-Week Range"
                          low={stock.week52_low}
                          high={stock.week52_high}
                          current={stock.current_price}
                        />
                      </Grid>
                    </Grid>
                  </Box>

                  {/* ── Key Statistics Matrix ── */}
                  <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.05rem', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                    <AssessmentIcon sx={{ color: '#10B981', fontSize: '1.2rem' }} />
                    Key Statistics & Valuation
                  </Typography>

                  <Grid container spacing={2} sx={{ mb: 4 }}>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="Market Cap" value={stock.market_cap_cr ? `₹${stock.market_cap_cr.toLocaleString()} Cr` : '-'} />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox
                        label="P/E Ratio (NSE)"
                        value={stock.pe_ratio ? stock.pe_ratio.toFixed(1) : '-'}
                        subtext={stock.sector_pe ? `Sector P/E: ${stock.sector_pe.toFixed(1)}` : undefined}
                      />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="P/B Ratio" value={stock.pb_ratio ? stock.pb_ratio.toFixed(2) : '-'} />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="Dividend Yield" value={stock.dividend_yield ? `${stock.dividend_yield}%` : '0.0%'} />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="EPS (TTM)" value={stock.eps ? `₹${stock.eps.toFixed(2)}` : '-'} />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="Beta" value={stock.beta ? stock.beta.toFixed(2) : '-'} />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="VWAP (NSE)" value={stock.vwap ? fmtINR(stock.vwap) : '-'} />
                    </Grid>
                    <Grid item xs={6} sm={4} md={3}>
                      <StatBox label="Delivery %" value={stock.delivery_pct !== null && stock.delivery_pct !== undefined ? `${stock.delivery_pct}%` : '-'} />
                    </Grid>
                  </Grid>

                  {/* ── People Also Watch (Sector Peers) ── */}
                  {stock.peers && stock.peers.length > 0 && (
                    <Box sx={{ mb: 4 }}>
                      <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.05rem', mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                        <TrendingUpIcon sx={{ color: '#38BDF8', fontSize: '1.2rem' }} />
                        People Also Watch ({stock.sector} Peers)
                      </Typography>
                      <Grid container spacing={2}>
                        {stock.peers.map((peer: PeerStock) => {
                          const peerUp = (peer.p_change ?? 0) >= 0
                          return (
                            <Grid item xs={12} sm={6} md={4} key={peer.symbol}>
                              <Box
                                onClick={() =>
                                  handleSelect({
                                    symbol: peer.symbol,
                                    name: peer.name,
                                  })
                                }
                                sx={{
                                  p: 2,
                                  bgcolor: 'rgba(255,255,255,0.03)',
                                  border: '1px solid rgba(255,255,255,0.06)',
                                  borderRadius: '14px',
                                  cursor: 'pointer',
                                  transition: 'all 0.2s ease',
                                  '&:hover': {
                                    bgcolor: 'rgba(255,255,255,0.07)',
                                    borderColor: 'rgba(16,185,129,0.3)',
                                    transform: 'translateY(-2px)',
                                  },
                                }}
                              >
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                  <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '0.95rem' }}>
                                    {peer.symbol}
                                  </Typography>
                                  <Typography
                                    sx={{
                                      fontSize: '0.8rem',
                                      fontWeight: 700,
                                      color: peerUp ? '#10B981' : '#EF4444',
                                    }}
                                  >
                                    {peerUp ? '+' : ''}{peer.p_change ? peer.p_change.toFixed(2) : '0.00'}%
                                  </Typography>
                                </Box>
                                <Typography noWrap sx={{ color: '#94A3B8', fontSize: '0.74rem', mt: 0.5 }}>
                                  {peer.name}
                                </Typography>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 1.5, pt: 1, borderTop: '1px solid rgba(255,255,255,0.04)', fontSize: '0.78rem' }}>
                                  <span style={{ color: '#64748B' }}>Price:</span>
                                  <span style={{ color: '#F8FAFC', fontWeight: 700, fontFamily: 'monospace' }}>
                                    {peer.current_price ? fmtINR(peer.current_price) : '—'}
                                  </span>
                                </Box>
                              </Box>
                            </Grid>
                          )
                        })}
                      </Grid>
                    </Box>
                  )}

                  {/* Company Description */}
                  {stock.description && (
                    <Box sx={{ pt: 3, borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                      <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem', lineHeight: 1.6 }}>
                        {stock.description}
                      </Typography>
                    </Box>
                  )}
                </Paper>
              </Grid>

              {/* Right Column: Portfolio Impact Simulator */}
              <Grid item xs={12} lg={4}>
                <Paper
                  sx={{
                    p: { xs: 2.5, md: 3.5 },
                    borderRadius: '20px',
                    background: 'rgba(15,23,42,0.65)',
                    border: '1px solid rgba(255,255,255,0.08)',
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
                    <AutoGraphIcon sx={{ color: '#8B5CF6' }} />
                    <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.15rem' }}>
                      Portfolio Impact Simulator
                    </Typography>
                  </Box>

                  {!sessionId ? (
                    <Alert severity="info" sx={{ background: 'rgba(59,130,246,0.1)', borderRadius: '14px' }}>
                      Upload or connect your equity portfolio to simulate how buying {stock.symbol} shifts your sector weights.
                    </Alert>
                  ) : (
                    <Box>
                      <Typography sx={{ color: '#94A3B8', fontSize: '0.88rem', mb: 1.5 }}>
                        Simulate Investment Amount
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 2, mb: 4 }}>
                        <TextField
                          value={impactAmount}
                          onChange={(e) => setImpactAmount(e.target.value)}
                          type="number"
                          size="small"
                          fullWidth
                          InputProps={{
                            startAdornment: <InputAdornment position="start" sx={{ color: '#94A3B8' }}>₹</InputAdornment>,
                            sx: { color: '#fff', background: 'rgba(255,255,255,0.05)', borderRadius: '12px' },
                          }}
                        />
                        <Button
                          variant="contained"
                          onClick={() => handleImpact(stock.symbol, parseFloat(impactAmount))}
                          disabled={loadingImpact}
                          sx={{
                            background: '#8B5CF6',
                            fontWeight: 700,
                            px: 3,
                            borderRadius: '12px',
                            '&:hover': { background: '#7C3AED' },
                          }}
                        >
                          Simulate
                        </Button>
                      </Box>

                      {loadingImpact ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
                          <CircularProgress size={26} sx={{ color: '#8B5CF6' }} />
                        </Box>
                      ) : impact ? (
                        <Box>
                          {impact.already_owned && (
                            <Alert severity="info" sx={{ mb: 3, background: 'rgba(59,130,246,0.1)', borderRadius: '12px' }}>
                              You already own {impact.existing_position?.quantity} shares of {stock.symbol}.
                            </Alert>
                          )}

                          <Typography sx={{ color: '#F8FAFC', fontWeight: 700, mb: 2 }}>
                            {stock.sector} Exposure Shift
                          </Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                            <Typography sx={{ color: '#94A3B8' }}>Before Trade</Typography>
                            <Typography sx={{ color: '#F8FAFC', fontWeight: 700 }}>
                              {impact.sector_weight_before}%
                            </Typography>
                          </Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                            <Typography sx={{ color: '#94A3B8' }}>After Trade</Typography>
                            <Typography sx={{ color: '#10B981', fontWeight: 700 }}>
                              {impact.sector_weight_after}%
                            </Typography>
                          </Box>

                          <Box
                            sx={{
                              p: 2,
                              background: 'rgba(16,185,129,0.1)',
                              borderRadius: '12px',
                              border: '1px solid rgba(16,185,129,0.2)',
                              mb: 2,
                            }}
                          >
                            <Typography sx={{ color: '#10B981', fontWeight: 700, textAlign: 'center', fontSize: '0.92rem' }}>
                              {impact.sector_delta > 0 ? '+' : ''}{impact.sector_delta}% shift in {stock.sector}
                            </Typography>
                          </Box>

                          {impact.concentration_warning && (
                            <Alert severity="warning" sx={{ mt: 3, background: 'rgba(245,158,11,0.1)', borderRadius: '12px' }}>
                              Warning: This trade would make {stock.symbol} exceed 15% of your total equity portfolio.
                            </Alert>
                          )}
                        </Box>
                      ) : null}
                    </Box>
                  )}
                </Paper>
              </Grid>
            </Grid>
          )}

          {/* ── TAB 2: INDICATORS ── */}
          {activeSubTab === 'indicators' && (
            <Paper
              sx={{
                p: { xs: 2.5, md: 3.5 },
                borderRadius: '20px',
                background: 'rgba(15,23,42,0.65)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3, flexWrap: 'wrap', gap: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <SpeedIcon sx={{ color: '#38BDF8', fontSize: '1.3rem' }} />
                  <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>
                    Technical Indicators & Moving Averages
                  </Typography>
                </Box>
                {technicals?.trend && (
                  <Chip
                    label={`Trend: ${technicals.trend}`}
                    sx={{
                      background: `${trendColor}22`,
                      color: trendColor,
                      borderColor: trendColor,
                      borderWidth: 1,
                      borderStyle: 'solid',
                      fontWeight: 800,
                    }}
                  />
                )}
              </Box>

              {/* Price + 50 DMA + 200 DMA Chart */}
              <Box sx={{ height: 280, mb: 4 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={technicalChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="date" stroke="#64748B" fontSize={11} />
                    <YAxis stroke="#64748B" fontSize={11} domain={['auto', 'auto']} tickFormatter={(v) => `₹${v}`} orientation="right" />
                    <RechartsTooltip
                      contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                      labelStyle={{ color: '#94A3B8' }}
                      formatter={(v: number, name: string) => [fmtINR(v), name]}
                    />
                    <Legend wrapperStyle={{ fontSize: '0.8rem', paddingTop: '10px' }} />
                    <Line type="monotone" dataKey="price" name="Price" stroke="#10B981" strokeWidth={2} dot={false} />
                    {stock.technicals?.sma_50 && (
                      <Line type="monotone" dataKey="sma_50" name="50 DMA" stroke="#38BDF8" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
                    )}
                    {stock.technicals?.sma_200 && (
                      <Line type="monotone" dataKey="sma_200" name="200 DMA" stroke="#F59E0B" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </Box>

              {/* Technical Indicator Metric Cards */}
              <Grid container spacing={2} sx={{ mb: 4 }}>
                <Grid item xs={6} sm={4} md={3}>
                  <StatBox
                    label="RSI (14-Day)"
                    value={rsi !== null && rsi !== undefined ? rsi.toFixed(1) : '-'}
                    color={rsiColor}
                    subtext={technicals?.rsi_status}
                  />
                </Grid>
                <Grid item xs={6} sm={4} md={3}>
                  <StatBox
                    label="50-Day DMA"
                    value={technicals?.sma_50 ? fmtINR(technicals.sma_50) : '-'}
                    color={technicals?.above_50_dma ? '#10B981' : '#EF4444'}
                    subtext={technicals?.above_50_dma !== null ? (technicals?.above_50_dma ? 'Bullish (>50 DMA)' : 'Bearish (<50 DMA)') : undefined}
                  />
                </Grid>
                <Grid item xs={6} sm={4} md={3}>
                  <StatBox
                    label="200-Day DMA"
                    value={technicals?.sma_200 ? fmtINR(technicals.sma_200) : '-'}
                    color={technicals?.above_200_dma ? '#10B981' : '#EF4444'}
                    subtext={technicals?.above_200_dma !== null ? (technicals?.above_200_dma ? 'Above 200 DMA' : 'Below 200 DMA') : undefined}
                  />
                </Grid>
                <Grid item xs={6} sm={4} md={3}>
                  <StatBox
                    label="52W High Gap"
                    value={technicals?.dist_52w_high_pct !== null && technicals?.dist_52w_high_pct !== undefined ? `${technicals.dist_52w_high_pct}%` : '-'}
                    subtext={`High: ${stock.week52_high ? fmtINR(stock.week52_high) : '-'}`}
                  />
                </Grid>
              </Grid>

              {/* Volume Series Bar Chart */}
              {stock.volume_series && stock.volume_series.length > 0 && (
                <Box>
                  <Typography sx={{ color: '#94A3B8', fontSize: '0.88rem', fontWeight: 700, mb: 1.5 }}>
                    Traded Volume History (Daily)
                  </Typography>
                  <Box sx={{ height: 130 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={stock.volume_series}>
                        <XAxis dataKey="date" stroke="#64748B" fontSize={10} hide />
                        <YAxis stroke="#64748B" fontSize={10} orientation="right" tickFormatter={(v) => `${(v / 1e5).toFixed(0)}L`} />
                        <RechartsTooltip
                          contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                          formatter={(v: number) => [v.toLocaleString(), 'Volume']}
                        />
                        <Bar dataKey="volume" fill="#38BDF8" radius={[2, 2, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </Box>
                </Box>
              )}
            </Paper>
          )}

          {/* ── TAB 3: COMPARE (MULTI-STOCK + BENCHMARKS) ── */}
          {activeSubTab === 'compare' && (
            <Paper
              sx={{
                p: { xs: 2.5, md: 3.5 },
                borderRadius: '20px',
                background: 'rgba(15,23,42,0.65)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2.5, flexWrap: 'wrap', gap: 1.5 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <CompareArrowsIcon sx={{ color: '#8B5CF6', fontSize: '1.3rem' }} />
                  <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>
                    Compare with Other Stocks & Benchmarks
                  </Typography>
                </Box>

                {/* Benchmark Toggle Button */}
                <Button
                  size="small"
                  onClick={() => setCompareBenchmark(!compareBenchmark)}
                  sx={{
                    borderRadius: '10px',
                    fontSize: '0.78rem',
                    fontWeight: 700,
                    textTransform: 'none',
                    px: 1.8,
                    py: 0.5,
                    bgcolor: compareBenchmark ? 'rgba(56,189,248,0.15)' : 'rgba(255,255,255,0.05)',
                    color: compareBenchmark ? '#38BDF8' : '#94A3B8',
                    border: compareBenchmark ? '1px solid rgba(56,189,248,0.3)' : '1px solid rgba(255,255,255,0.08)',
                    '&:hover': { bgcolor: compareBenchmark ? 'rgba(56,189,248,0.25)' : 'rgba(255,255,255,0.1)' },
                  }}
                >
                  {compareBenchmark ? '✓ NIFTY 50 Benchmark' : '+ Add NIFTY 50 Benchmark'}
                </Button>
              </Box>

              {/* ── Compare Stock Search Bar ── */}
              <Box sx={{ mb: 2.5, maxWidth: 600 }}>
                <Autocomplete
                  options={compareOptions}
                  inputValue={compareQuery}
                  onInputChange={(_, v) => setCompareQuery(v)}
                  onChange={(_, val) => {
                    if (val && typeof val !== 'string') {
                      void handleAddCompareStock(val.symbol)
                    }
                  }}
                  getOptionLabel={(opt) => (typeof opt === 'string' ? opt : `${opt.symbol} - ${opt.name}`)}
                  loading={searchingCompare}
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      placeholder="Add stock to compare (e.g. TCS, INFY, HDFCBANK, TATAMOTORS)..."
                      size="small"
                      InputProps={{
                        ...params.InputProps,
                        startAdornment: <AddCircleOutlineIcon sx={{ color: '#8B5CF6', ml: 0.5, mr: 1, fontSize: '1.2rem' }} />,
                        endAdornment: (
                          <>
                            {loadingCompareStock ? <CircularProgress size={16} sx={{ color: '#8B5CF6', mr: 1 }} /> : null}
                            {params.InputProps.endAdornment}
                          </>
                        ),
                        sx: {
                          borderRadius: '12px',
                          background: 'rgba(255,255,255,0.04)',
                          color: '#fff',
                          fontSize: '0.88rem',
                          '& fieldset': { borderColor: 'rgba(139,92,246,0.3)' },
                          '&:hover fieldset': { borderColor: 'rgba(139,92,246,0.6)' },
                          '&.Mui-focused fieldset': { borderColor: '#8B5CF6' },
                        },
                      }}
                    />
                  )}
                />
              </Box>

              {/* ── Quick Add Sector Peers ── */}
              {stock.peers && stock.peers.length > 0 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 3, flexWrap: 'wrap' }}>
                  <Typography sx={{ color: '#64748B', fontSize: '0.76rem', fontWeight: 600 }}>
                    Quick Add Sector Peers:
                  </Typography>
                  {stock.peers.slice(0, 5).map((p) => {
                    const isAdded = compareStocks.some((cs) => cs.symbol.toUpperCase() === p.symbol.toUpperCase())
                    return (
                      <Chip
                        key={p.symbol}
                        label={`+ ${p.symbol}`}
                        size="small"
                        disabled={isAdded || loadingCompareStock === p.symbol}
                        onClick={() => void handleAddCompareStock(p.symbol)}
                        sx={{
                          cursor: isAdded ? 'default' : 'pointer',
                          bgcolor: isAdded ? 'rgba(255,255,255,0.02)' : 'rgba(139,92,246,0.1)',
                          color: isAdded ? '#475569' : '#C4B5FD',
                          fontWeight: 700,
                          fontSize: '0.74rem',
                          border: isAdded ? '1px solid transparent' : '1px solid rgba(139,92,246,0.25)',
                          '&:hover': {
                            bgcolor: isAdded ? 'transparent' : 'rgba(139,92,246,0.2)',
                          },
                        }}
                      />
                    )
                  })}
                </Box>
              )}

              {/* ── Active Compared Assets Badges ── */}
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3, flexWrap: 'wrap', p: 1.5, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '14px', border: '1px solid rgba(255,255,255,0.04)' }}>
                {/* Target Stock Badge */}
                <Chip
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: '#10B981' }} />
                      <span>{stock.symbol} (Target)</span>
                    </Box>
                  }
                  sx={{
                    bgcolor: 'rgba(16,185,129,0.15)',
                    color: '#10B981',
                    fontWeight: 800,
                    border: '1px solid rgba(16,185,129,0.4)',
                  }}
                />

                {/* Added Compared Stocks Badges */}
                {compareStocks.map((comp, idx) => {
                  const clr = COMPARE_COLORS[idx % COMPARE_COLORS.length]
                  return (
                    <Chip
                      key={comp.symbol}
                      label={
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: clr }} />
                          <span>{comp.symbol}</span>
                          <span style={{ fontSize: '0.72rem', opacity: 0.8 }}>({fmtINR(comp.current_price)})</span>
                        </Box>
                      }
                      onDelete={() => removeCompareStock(comp.symbol)}
                      deleteIcon={<CloseIcon sx={{ color: `${clr} !important`, fontSize: '1rem !important' }} />}
                      sx={{
                        bgcolor: `${clr}22`,
                        color: clr,
                        fontWeight: 800,
                        border: `1px solid ${clr}66`,
                      }}
                    />
                  )
                })}

                {/* Benchmark Badge */}
                {compareBenchmark && (
                  <Chip
                    label={
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 8, height: 2, bgcolor: '#94A3B8' }} />
                        <span>NIFTY 50 (Benchmark)</span>
                      </Box>
                    }
                    onDelete={() => setCompareBenchmark(false)}
                    deleteIcon={<CloseIcon sx={{ color: '#94A3B8 !important', fontSize: '1rem !important' }} />}
                    sx={{
                      bgcolor: 'rgba(148,163,184,0.12)',
                      color: '#94A3B8',
                      fontWeight: 700,
                      border: '1px dashed rgba(148,163,184,0.4)',
                    }}
                  />
                )}

                {compareStocks.length > 0 && (
                  <Button
                    size="small"
                    startIcon={<DeleteOutlineIcon sx={{ fontSize: '0.9rem' }} />}
                    onClick={clearCompareStocks}
                    sx={{ color: '#EF4444', fontSize: '0.74rem', textTransform: 'none', ml: 'auto' }}
                  >
                    Clear Comparisons
                  </Button>
                )}
              </Box>

              {/* ── Relative % Comparison Chart ── */}
              <Box sx={{ height: 320, mb: 4 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={compareData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                    <XAxis dataKey="date" stroke="#64748B" fontSize={11} />
                    <YAxis stroke="#64748B" fontSize={11} tickFormatter={(v) => `${v}%`} orientation="right" />
                    <ReferenceLine y={0} stroke="rgba(255,255,255,0.2)" strokeDasharray="2 2" />
                    <RechartsTooltip
                      contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                      labelStyle={{ color: '#94A3B8' }}
                      formatter={(v: number, name: string) => [`${v > 0 ? '+' : ''}${v}%`, name]}
                    />
                    <Legend wrapperStyle={{ fontSize: '0.85rem', paddingTop: '10px' }} />

                    {/* Target Stock Line */}
                    <Line type="monotone" dataKey={stock.symbol} stroke="#10B981" strokeWidth={2.5} dot={false} />

                    {/* Comparison Stocks Lines */}
                    {compareStocks.map((comp, idx) => {
                      const clr = COMPARE_COLORS[idx % COMPARE_COLORS.length]
                      return (
                        <Line
                          key={comp.symbol}
                          type="monotone"
                          dataKey={comp.symbol}
                          stroke={clr}
                          strokeWidth={2.2}
                          dot={false}
                        />
                      )
                    })}

                    {/* Benchmark Line */}
                    {compareBenchmark && (
                      <Line type="monotone" dataKey="NIFTY 50" stroke="#94A3B8" strokeWidth={1.8} strokeDasharray="3 3" dot={false} />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </Box>

              {/* ── Side-by-Side Dynamic Multi-Stock Comparison Table ── */}
              <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.05rem', mb: 2 }}>
                Multi-Asset Fundamentals & Valuation Matrix
              </Typography>
              <Box sx={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', color: '#94A3B8' }}>
                      <th style={{ padding: '12px 14px' }}>Metric</th>
                      <th style={{ padding: '12px 14px', color: '#10B981', fontWeight: 800 }}>
                        {stock.symbol} (Target)
                      </th>
                      {compareStocks.map((comp, idx) => {
                        const clr = COMPARE_COLORS[idx % COMPARE_COLORS.length]
                        return (
                          <th key={comp.symbol} style={{ padding: '12px 14px', color: clr, fontWeight: 800 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
                              <span>{comp.symbol}</span>
                              <IconButton
                                size="small"
                                onClick={() => removeCompareStock(comp.symbol)}
                                sx={{ color: '#64748B', p: 0.2, '&:hover': { color: '#EF4444' } }}
                              >
                                <CloseIcon sx={{ fontSize: '0.9rem' }} />
                              </IconButton>
                            </Box>
                          </th>
                        )
                      })}
                      {compareBenchmark && (
                        <th style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 700 }}>
                          NIFTY 50 / Sector Avg
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {/* Current Price */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>Current Price</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700, fontFamily: 'monospace' }}>
                        {fmtINR(stock.current_price)}
                      </td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700, fontFamily: 'monospace' }}>
                          {fmtINR(comp.current_price)}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px', color: '#64748B' }}>—</td>}
                    </tr>

                    {/* 1-Year Return */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>1-Year Return</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700, color: (stock.year_return ?? 0) >= 0 ? '#10B981' : '#EF4444' }}>
                        {(stock.year_return ?? 0) >= 0 ? '+' : ''}{fmtNum(stock.year_return ?? 0, 2)}%
                      </td>
                      {compareStocks.map((comp) => {
                        const yr = comp.year_return ?? 0
                        return (
                          <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700, color: yr >= 0 ? '#10B981' : '#EF4444' }}>
                            {yr >= 0 ? '+' : ''}{fmtNum(yr, 2)}%
                          </td>
                        )
                      })}
                      {compareBenchmark && <td style={{ padding: '12px 14px', color: '#38BDF8', fontWeight: 700 }}>+14.2%</td>}
                    </tr>

                    {/* Market Cap */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>Market Cap</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>
                        {stock.market_cap_cr ? `₹${stock.market_cap_cr.toLocaleString()} Cr` : '-'}
                      </td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700 }}>
                          {comp.market_cap_cr ? `₹${comp.market_cap_cr.toLocaleString()} Cr` : '-'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px', color: '#64748B' }}>—</td>}
                    </tr>

                    {/* P/E Ratio */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>P/E Ratio (NSE)</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>{stock.pe_ratio ? stock.pe_ratio.toFixed(1) : '-'}</td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700 }}>
                          {comp.pe_ratio ? comp.pe_ratio.toFixed(1) : '-'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px' }}>22.4</td>}
                    </tr>

                    {/* P/B Ratio */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>P/B Ratio</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>{stock.pb_ratio ? stock.pb_ratio.toFixed(2) : '-'}</td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700 }}>
                          {comp.pb_ratio ? comp.pb_ratio.toFixed(2) : '-'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px' }}>3.2</td>}
                    </tr>

                    {/* ROE */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>Return on Equity (ROE)</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700, color: stock.roe && stock.roe >= 15 ? '#10B981' : undefined }}>
                        {stock.roe ? `${stock.roe}%` : '-'}
                      </td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700, color: comp.roe && comp.roe >= 15 ? '#10B981' : undefined }}>
                          {comp.roe ? `${comp.roe}%` : '-'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px' }}>14.8%</td>}
                    </tr>

                    {/* Dividend Yield */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>Dividend Yield</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>{stock.dividend_yield ? `${stock.dividend_yield}%` : '0.0%'}</td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700 }}>
                          {comp.dividend_yield ? `${comp.dividend_yield}%` : '0.0%'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px' }}>1.2%</td>}
                    </tr>

                    {/* 52-Week Range */}
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>52-Week Range</td>
                      <td style={{ padding: '12px 14px', fontSize: '0.8rem' }}>
                        {stock.week52_low ? fmtINR(stock.week52_low) : '-'} - {stock.week52_high ? fmtINR(stock.week52_high) : '-'}
                      </td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontSize: '0.8rem' }}>
                          {comp.week52_low ? fmtINR(comp.week52_low) : '-'} - {comp.week52_high ? fmtINR(comp.week52_high) : '-'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px', color: '#64748B' }}>—</td>}
                    </tr>

                    {/* Beta */}
                    <tr style={{ color: '#F8FAFC' }}>
                      <td style={{ padding: '12px 14px', color: '#94A3B8', fontWeight: 600 }}>Beta (Volatility)</td>
                      <td style={{ padding: '12px 14px', fontWeight: 700 }}>{stock.beta ? stock.beta.toFixed(2) : '-'}</td>
                      {compareStocks.map((comp) => (
                        <td key={comp.symbol} style={{ padding: '12px 14px', fontWeight: 700 }}>
                          {comp.beta ? comp.beta.toFixed(2) : '-'}
                        </td>
                      ))}
                      {compareBenchmark && <td style={{ padding: '12px 14px' }}>1.00</td>}
                    </tr>
                  </tbody>
                </table>
              </Box>
            </Paper>
          )}

          {/* ── TAB 4: FINANCIALS (GOOGLE FINANCE STYLE) ── */}
          {activeSubTab === 'financials' && (
            <Paper
              sx={{
                p: { xs: 2.5, md: 3.5 },
                borderRadius: '20px',
                background: 'rgba(15,23,42,0.65)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              {/* Statement and Period Switcher Controls */}
              <Box
                sx={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  flexWrap: 'wrap',
                  gap: 2,
                  mb: 3,
                }}
              >
                {/* Statement Selector Pills */}
                <Box
                  sx={{
                    display: 'flex',
                    background: 'rgba(255,255,255,0.04)',
                    p: 0.5,
                    borderRadius: '14px',
                    border: '1px solid rgba(255,255,255,0.08)',
                    gap: 0.5,
                  }}
                >
                  {[
                    { id: 'income_statement', label: 'Income statement' },
                    { id: 'balance_sheet', label: 'Balance sheet' },
                    { id: 'cash_flow', label: 'Cash flow' },
                  ].map((stmt) => {
                    const active = financialStmtType === stmt.id
                    return (
                      <Button
                        key={stmt.id}
                        size="small"
                        onClick={() => setFinancialStmtType(stmt.id as typeof financialStmtType)}
                        sx={{
                          borderRadius: '10px',
                          textTransform: 'none',
                          fontWeight: active ? 700 : 500,
                          fontSize: '0.84rem',
                          px: 2,
                          py: 0.6,
                          color: active ? '#F8FAFC' : '#94A3B8',
                          bgcolor: active ? 'rgba(56,189,248,0.2)' : 'transparent',
                          border: active ? '1px solid rgba(56,189,248,0.4)' : '1px solid transparent',
                          '&:hover': {
                            bgcolor: active ? 'rgba(56,189,248,0.25)' : 'rgba(255,255,255,0.05)',
                          },
                        }}
                      >
                        {stmt.label}
                      </Button>
                    )
                  })}
                </Box>

                {/* Period Selector (Quarterly vs Annual) */}
                <Box
                  sx={{
                    display: 'flex',
                    background: 'rgba(255,255,255,0.04)',
                    p: 0.5,
                    borderRadius: '14px',
                    border: '1px solid rgba(255,255,255,0.08)',
                    gap: 0.5,
                  }}
                >
                  {[
                    { id: 'quarterly', label: 'Quarterly' },
                    { id: 'annual', label: 'Annual' },
                  ].map((p) => {
                    const active = financialPeriodType === p.id
                    return (
                      <Button
                        key={p.id}
                        size="small"
                        onClick={() => setFinancialPeriodType(p.id as typeof financialPeriodType)}
                        sx={{
                          borderRadius: '10px',
                          textTransform: 'none',
                          fontWeight: active ? 700 : 500,
                          fontSize: '0.82rem',
                          px: 1.8,
                          py: 0.6,
                          color: active ? '#38BDF8' : '#94A3B8',
                          bgcolor: active ? 'rgba(56,189,248,0.12)' : 'transparent',
                          '&:hover': {
                            bgcolor: active ? 'rgba(56,189,248,0.18)' : 'rgba(255,255,255,0.05)',
                          },
                        }}
                      >
                        {p.label}
                      </Button>
                    )
                  })}
                </Box>
              </Box>

              {/* Interactive Checkbox Filter Row */}
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 3, alignItems: 'center' }}>
                {financialStmtType === 'cash_flow' &&
                  Object.entries(CASH_FLOW_CONFIG).map(([key, cfg]) => {
                    const isChecked = selectedCfMetrics.includes(key)
                    return (
                      <Box
                        key={key}
                        onClick={() => toggleCfMetric(key)}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
                          px: 1.8,
                          py: 0.7,
                          borderRadius: '10px',
                          cursor: 'pointer',
                          bgcolor: isChecked ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.02)',
                          border: isChecked ? `1px solid ${cfg.color}66` : '1px solid rgba(255,255,255,0.06)',
                          transition: 'all 0.2s ease',
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.08)' },
                        }}
                      >
                        <Box
                          sx={{
                            width: 10,
                            height: 10,
                            borderRadius: '3px',
                            bgcolor: isChecked ? cfg.color : 'transparent',
                            border: `2px solid ${cfg.color}`,
                          }}
                        />
                        <Typography sx={{ color: isChecked ? '#F8FAFC' : '#64748B', fontSize: '0.8rem', fontWeight: 600 }}>
                          {cfg.label}
                        </Typography>
                      </Box>
                    )
                  })}

                {financialStmtType === 'income_statement' &&
                  Object.entries(INCOME_STMT_CONFIG).map(([key, cfg]) => {
                    const isChecked = selectedIncMetrics.includes(key)
                    return (
                      <Box
                        key={key}
                        onClick={() => toggleIncMetric(key)}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
                          px: 1.8,
                          py: 0.7,
                          borderRadius: '10px',
                          cursor: 'pointer',
                          bgcolor: isChecked ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.02)',
                          border: isChecked ? `1px solid ${cfg.color}66` : '1px solid rgba(255,255,255,0.06)',
                          transition: 'all 0.2s ease',
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.08)' },
                        }}
                      >
                        <Box
                          sx={{
                            width: 10,
                            height: 10,
                            borderRadius: '3px',
                            bgcolor: isChecked ? cfg.color : 'transparent',
                            border: `2px solid ${cfg.color}`,
                          }}
                        />
                        <Typography sx={{ color: isChecked ? '#F8FAFC' : '#64748B', fontSize: '0.8rem', fontWeight: 600 }}>
                          {cfg.label}
                        </Typography>
                      </Box>
                    )
                  })}

                {financialStmtType === 'balance_sheet' &&
                  Object.entries(BALANCE_SHEET_CONFIG).map(([key, cfg]) => {
                    const isChecked = selectedBsMetrics.includes(key)
                    return (
                      <Box
                        key={key}
                        onClick={() => toggleBsMetric(key)}
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
                          px: 1.8,
                          py: 0.7,
                          borderRadius: '10px',
                          cursor: 'pointer',
                          bgcolor: isChecked ? 'rgba(255,255,255,0.06)' : 'rgba(255,255,255,0.02)',
                          border: isChecked ? `1px solid ${cfg.color}66` : '1px solid rgba(255,255,255,0.06)',
                          transition: 'all 0.2s ease',
                          '&:hover': { bgcolor: 'rgba(255,255,255,0.08)' },
                        }}
                      >
                        <Box
                          sx={{
                            width: 10,
                            height: 10,
                            borderRadius: '3px',
                            bgcolor: isChecked ? cfg.color : 'transparent',
                            border: `2px solid ${cfg.color}`,
                          }}
                        />
                        <Typography sx={{ color: isChecked ? '#F8FAFC' : '#64748B', fontSize: '0.8rem', fontWeight: 600 }}>
                          {cfg.label}
                        </Typography>
                      </Box>
                    )
                  })}
              </Box>

              {/* Dynamic Financials Chart */}
              {(() => {
                const currentPeriodData =
                  stock.financial_statements?.[financialPeriodType]?.[financialStmtType] ?? []

                if (currentPeriodData.length === 0) {
                  return (
                    <Alert severity="info" sx={{ background: 'rgba(59,130,246,0.1)', borderRadius: '14px', mb: 3 }}>
                      Financial statement data is currently being populated for {stock.symbol}.
                    </Alert>
                  )
                }

                // Active metrics map
                const activeMetrics =
                  financialStmtType === 'cash_flow'
                    ? selectedCfMetrics
                    : financialStmtType === 'income_statement'
                    ? selectedIncMetrics
                    : selectedBsMetrics

                const configMap =
                  financialStmtType === 'cash_flow'
                    ? CASH_FLOW_CONFIG
                    : financialStmtType === 'income_statement'
                    ? INCOME_STMT_CONFIG
                    : BALANCE_SHEET_CONFIG

                return (
                  <Box sx={{ mb: 4 }}>
                    <Box sx={{ height: 290, mb: 4 }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={currentPeriodData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                          <XAxis dataKey="period" stroke="#64748B" fontSize={11} />
                          <YAxis stroke="#64748B" fontSize={11} orientation="right" tickFormatter={(v) => `₹${v}Cr`} />
                          <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
                          <RechartsTooltip
                            contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                            formatter={(v: number, name: string) => [fmtCr(v), configMap[name]?.label || name]}
                          />
                          <Legend wrapperStyle={{ fontSize: '0.82rem', paddingTop: '10px' }} />
                          {activeMetrics.map((metricKey) => (
                            <Bar
                              key={metricKey}
                              dataKey={metricKey}
                              name={configMap[metricKey]?.label || metricKey}
                              fill={configMap[metricKey]?.color || '#38BDF8'}
                              radius={[4, 4, 0, 0]}
                            />
                          ))}
                        </BarChart>
                      </ResponsiveContainer>
                    </Box>

                    {/* Detailed Financial Statement Table */}
                    <Box sx={{ overflowX: 'auto', borderRadius: '14px', border: '1px solid rgba(255,255,255,0.08)' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.86rem', textAlign: 'left' }}>
                        <thead>
                          <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                            <th style={{ padding: '12px 16px', color: '#94A3B8', fontWeight: 600 }}>
                              All values in INR
                            </th>
                            {currentPeriodData.map((item, idx) => (
                              <th key={idx} style={{ padding: '12px 16px', color: '#F8FAFC', fontWeight: 700, textAlign: 'right' }}>
                                {item.period}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {/* Cash Flow Rows */}
                          {financialStmtType === 'cash_flow' && (
                            <>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Net income</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#F8FAFC', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).net_income_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Cash from operations</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#38BDF8', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).cash_from_operations_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Cash from investing</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#2DD4BF', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).cash_from_investing_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Cash from financing</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#A855F7', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).cash_from_financing_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Net change in cash</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#F59E0B', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).net_change_in_cash_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Free cash flow</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#10B981', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).free_cash_flow_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Change in inventories</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#CBD5E1', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).change_in_inventories_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Gain/loss on sale of assets</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#CBD5E1', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                    {fmtCr((d as CashFlowItem).gain_loss_on_sale_assets_cr)}
                                  </td>
                                ))}
                              </tr>
                            </>
                          )}

                          {/* Income Statement Rows */}
                          {financialStmtType === 'income_statement' && (
                            <>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Revenue</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#38BDF8', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as IncomeStatementItem).revenue_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Operating expense</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#F43F5E', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as IncomeStatementItem).operating_expense_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Net income</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#10B981', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as IncomeStatementItem).net_income_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Net profit margin (%)</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#F8FAFC', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtPctVal((d as IncomeStatementItem).net_margin_pct)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Earnings per share (EPS)</td>
                                {currentPeriodData.map((d, i) => {
                                  const epsVal = (d as IncomeStatementItem).eps
                                  return (
                                    <td key={i} style={{ padding: '11px 16px', color: '#F8FAFC', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                      {epsVal !== null && epsVal !== undefined ? `₹${epsVal.toFixed(2)}` : '—'}
                                    </td>
                                  )
                                })}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>EBITDA</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#F59E0B', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as IncomeStatementItem).ebitda_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Effective tax rate (%)</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#CBD5E1', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                    {fmtPctVal((d as IncomeStatementItem).effective_tax_rate_pct)}
                                  </td>
                                ))}
                              </tr>
                            </>
                          )}

                          {/* Balance Sheet Rows */}
                          {financialStmtType === 'balance_sheet' && (
                            <>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Cash & short-term investments</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#10B981', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as BalanceSheetItem).cash_and_equivalents_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Total assets</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#38BDF8', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as BalanceSheetItem).total_assets_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Total liabilities</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#F43F5E', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as BalanceSheetItem).total_liabilities_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Total equity</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#A855F7', textAlign: 'right', fontWeight: 600, fontFamily: 'monospace' }}>
                                    {fmtCr((d as BalanceSheetItem).total_equity_cr)}
                                  </td>
                                ))}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Shares outstanding</td>
                                {currentPeriodData.map((d, i) => {
                                  const sh = (d as BalanceSheetItem).shares_outstanding
                                  return (
                                    <td key={i} style={{ padding: '11px 16px', color: '#CBD5E1', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                      {sh ? sh.toLocaleString() : '—'}
                                    </td>
                                  )
                                })}
                              </tr>
                              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Price to book</td>
                                {currentPeriodData.map((d, i) => {
                                  const pb = (d as BalanceSheetItem).price_to_book
                                  return (
                                    <td key={i} style={{ padding: '11px 16px', color: '#CBD5E1', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                      {pb ? pb.toFixed(2) : '—'}
                                    </td>
                                  )
                                })}
                              </tr>
                              <tr>
                                <td style={{ padding: '11px 16px', color: '#94A3B8' }}>Return on assets (ROA %)</td>
                                {currentPeriodData.map((d, i) => (
                                  <td key={i} style={{ padding: '11px 16px', color: '#CBD5E1', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                    {fmtPctVal((d as BalanceSheetItem).return_on_assets_pct)}
                                  </td>
                                ))}
                              </tr>
                            </>
                          )}
                        </tbody>
                      </table>
                    </Box>
                  </Box>
                )
              })()}
            </Paper>
          )}

          {/* ── TAB 5: EARNINGS (GOOGLE FINANCE STYLE) ── */}
          {activeSubTab === 'earnings' && (
            <Paper
              sx={{
                p: { xs: 2.5, md: 3.5 },
                borderRadius: '20px',
                background: 'rgba(15,23,42,0.65)',
                border: '1px solid rgba(255,255,255,0.08)',
              }}
            >
              {/* 4-Pillars Key Metric Header (Google Finance Header) */}
              <Grid container spacing={2} sx={{ mb: 4 }}>
                {/* 1. Last Report */}
                <Grid item xs={12} sm={6} md={3}>
                  <Box
                    sx={{
                      p: 2.2,
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid rgba(255,255,255,0.06)',
                      borderRadius: '14px',
                    }}
                  >
                    <Typography sx={{ color: '#94A3B8', fontSize: '0.78rem', fontWeight: 600, mb: 0.5 }}>
                      Last report
                    </Typography>
                    <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>
                      {stock.earnings_summary?.last_report_date || 'Latest'}
                    </Typography>
                    <Typography sx={{ color: '#64748B', fontSize: '0.72rem', mt: 0.5 }}>
                      Official earnings release
                    </Typography>
                  </Box>
                </Grid>

                {/* 2. Financial Period */}
                <Grid item xs={12} sm={6} md={3}>
                  <Box
                    sx={{
                      p: 2.2,
                      background: 'rgba(255,255,255,0.03)',
                      border: '1px solid rgba(255,255,255,0.06)',
                      borderRadius: '14px',
                    }}
                  >
                    <Typography sx={{ color: '#94A3B8', fontSize: '0.78rem', fontWeight: 600, mb: 0.5 }}>
                      Financial period
                    </Typography>
                    <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>
                      {stock.earnings_summary?.financial_period || 'Fiscal Q1'}
                    </Typography>
                    <Typography sx={{ color: '#64748B', fontSize: '0.72rem', mt: 0.5 }}>
                      Reported fiscal quarter
                    </Typography>
                  </Box>
                </Grid>

                {/* 3. EPS / Est. */}
                <Grid item xs={12} sm={6} md={3}>
                  {(() => {
                    const sum = stock.earnings_summary
                    const repEps = sum?.reported_eps ?? stock.eps
                    const estEps = sum?.estimated_eps
                    const surp = sum?.eps_surprise_pct
                    const isBeat = surp !== null && surp !== undefined && surp >= 0

                    return (
                      <Box
                        sx={{
                          p: 2.2,
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.06)',
                          borderRadius: '14px',
                        }}
                      >
                        <Typography sx={{ color: '#94A3B8', fontSize: '0.78rem', fontWeight: 600, mb: 0.5 }}>
                          EPS / Est. (INR)
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.8, flexWrap: 'wrap' }}>
                          <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>
                            {repEps !== null && repEps !== undefined ? `₹${repEps.toFixed(2)}` : '—'}
                          </Typography>
                          {estEps !== null && estEps !== undefined && (
                            <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.95rem' }}>
                              / ₹{estEps.toFixed(2)}
                            </Typography>
                          )}
                        </Box>
                        {surp !== null && surp !== undefined && (
                          <Box sx={{ mt: 1 }}>
                            <Chip
                              size="small"
                              label={`${surp > 0 ? '+' : ''}${surp.toFixed(2)}% ${isBeat ? 'beat ⭡' : 'miss ⭣'}`}
                              sx={{
                                height: 22,
                                fontSize: '0.72rem',
                                fontWeight: 800,
                                bgcolor: isBeat ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                                color: isBeat ? '#10B981' : '#EF4444',
                                border: isBeat ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(239,68,68,0.3)',
                              }}
                            />
                          </Box>
                        )}
                      </Box>
                    )
                  })()}
                </Grid>

                {/* 4. Revenue / Est. */}
                <Grid item xs={12} sm={6} md={3}>
                  {(() => {
                    const sum = stock.earnings_summary
                    const repRev = sum?.reported_revenue_cr
                    const estRev = sum?.estimated_revenue_cr
                    const surp = sum?.revenue_surprise_pct
                    const isBeat = surp !== null && surp !== undefined && surp >= 0

                    return (
                      <Box
                        sx={{
                          p: 2.2,
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.06)',
                          borderRadius: '14px',
                        }}
                      >
                        <Typography sx={{ color: '#94A3B8', fontSize: '0.78rem', fontWeight: 600, mb: 0.5 }}>
                          Revenue / Est. (INR)
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.8, flexWrap: 'wrap' }}>
                          <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>
                            {fmtLargeRev(repRev)}
                          </Typography>
                          {estRev !== null && estRev !== undefined && (
                            <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.95rem' }}>
                              / {fmtLargeRev(estRev)}
                            </Typography>
                          )}
                        </Box>
                        {surp !== null && surp !== undefined && (
                          <Box sx={{ mt: 1 }}>
                            <Chip
                              size="small"
                              label={`${surp > 0 ? '+' : ''}${surp.toFixed(2)}% ${isBeat ? 'beat ⭡' : 'miss ⭣'}`}
                              sx={{
                                height: 22,
                                fontSize: '0.72rem',
                                fontWeight: 800,
                                bgcolor: isBeat ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                                color: isBeat ? '#10B981' : '#EF4444',
                                border: isBeat ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(239,68,68,0.3)',
                              }}
                            />
                          </Box>
                        )}
                      </Box>
                    )
                  })()}
                </Grid>
              </Grid>

              {/* Quarterly Earnings Call / History Section */}
              <Box sx={{ mb: 2 }}>
                <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.15rem', mb: 2.5 }}>
                  Fiscal {stock.earnings_summary?.financial_period || 'Quarterly'} earnings call
                </Typography>

                {(() => {
                  const history =
                    stock.earnings_summary?.history && stock.earnings_summary.history.length > 0
                      ? stock.earnings_summary.history
                      : (stock.earnings || []).map((e) => ({
                          period: e.quarter,
                          date: e.date,
                          reported_eps: e.reported_eps,
                          estimated_eps: e.estimated_eps,
                          surprise_pct: e.surprise_pct,
                          eps_surprise_type: (e.surprise_pct ?? 0) >= 0 ? 'beat' : 'miss',
                          reported_revenue_cr: null,
                          estimated_revenue_cr: null,
                          revenue_surprise_pct: null,
                          revenue_surprise_type: undefined,
                        }))

                  if (history.length === 0) {
                    return (
                      <Alert severity="info" sx={{ background: 'rgba(59,130,246,0.1)', borderRadius: '14px' }}>
                        Quarterly consensus earnings history is not available for {stock.symbol}.
                      </Alert>
                    )
                  }

                  return (
                    <Box>
                      {/* EPS Bar Chart (Reported vs Estimated) */}
                      <Box sx={{ height: 270, mb: 4 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={history} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
                            <XAxis dataKey="period" stroke="#64748B" fontSize={11} />
                            <YAxis stroke="#64748B" fontSize={11} orientation="right" tickFormatter={(v) => `₹${v}`} />
                            <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
                            <RechartsTooltip
                              contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                              formatter={(v: number, name: string) => [`₹${v}`, name]}
                            />
                            <Legend wrapperStyle={{ fontSize: '0.82rem', paddingTop: '10px' }} />
                            <Bar dataKey="reported_eps" name="Reported EPS" fill="#10B981" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="estimated_eps" name="Estimated EPS" fill="#64748B" radius={[4, 4, 0, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </Box>

                      {/* Detailed History Breakdown Table */}
                      <Box sx={{ overflowX: 'auto', borderRadius: '14px', border: '1px solid rgba(255,255,255,0.08)' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.86rem', textAlign: 'left' }}>
                          <thead>
                            <tr style={{ background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                              <th style={{ padding: '12px 16px', color: '#94A3B8', fontWeight: 600 }}>Period</th>
                              <th style={{ padding: '12px 16px', color: '#94A3B8', fontWeight: 600 }}>Date</th>
                              <th style={{ padding: '12px 16px', color: '#F8FAFC', fontWeight: 700, textAlign: 'right' }}>Reported EPS</th>
                              <th style={{ padding: '12px 16px', color: '#94A3B8', fontWeight: 600, textAlign: 'right' }}>Estimated EPS</th>
                              <th style={{ padding: '12px 16px', color: '#94A3B8', fontWeight: 600, textAlign: 'right' }}>EPS Surprise</th>
                              <th style={{ padding: '12px 16px', color: '#F8FAFC', fontWeight: 700, textAlign: 'right' }}>Reported Revenue</th>
                              <th style={{ padding: '12px 16px', color: '#94A3B8', fontWeight: 600, textAlign: 'right' }}>Revenue Surprise</th>
                            </tr>
                          </thead>
                          <tbody>
                            {history.map((h, i) => {
                              const epsSurp = h.surprise_pct
                              const revSurp = h.revenue_surprise_pct
                              const isEpsBeat = epsSurp !== null && epsSurp !== undefined && epsSurp >= 0
                              const isRevBeat = revSurp !== null && revSurp !== undefined && revSurp >= 0

                              return (
                                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                  <td style={{ padding: '11px 16px', color: '#F8FAFC', fontWeight: 700 }}>
                                    {h.period}
                                  </td>
                                  <td style={{ padding: '11px 16px', color: '#94A3B8' }}>
                                    {h.date || '—'}
                                  </td>
                                  <td style={{ padding: '11px 16px', color: '#10B981', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace' }}>
                                    {h.reported_eps !== null && h.reported_eps !== undefined ? `₹${h.reported_eps.toFixed(2)}` : '—'}
                                  </td>
                                  <td style={{ padding: '11px 16px', color: '#94A3B8', textAlign: 'right', fontWeight: 500, fontFamily: 'monospace' }}>
                                    {h.estimated_eps !== null && h.estimated_eps !== undefined ? `₹${h.estimated_eps.toFixed(2)}` : '—'}
                                  </td>
                                  <td style={{ padding: '11px 16px', textAlign: 'right' }}>
                                    {epsSurp !== null && epsSurp !== undefined ? (
                                      <Chip
                                        size="small"
                                        label={`${epsSurp > 0 ? '+' : ''}${epsSurp.toFixed(1)}% ${isEpsBeat ? 'beat ⭡' : 'miss ⭣'}`}
                                        sx={{
                                          height: 20,
                                          fontSize: '0.7rem',
                                          fontWeight: 800,
                                          bgcolor: isEpsBeat ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
                                          color: isEpsBeat ? '#10B981' : '#EF4444',
                                        }}
                                      />
                                    ) : (
                                      <span style={{ color: '#64748B' }}>—</span>
                                    )}
                                  </td>
                                  <td style={{ padding: '11px 16px', color: '#38BDF8', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace' }}>
                                    {h.reported_revenue_cr ? fmtCr(h.reported_revenue_cr) : '—'}
                                  </td>
                                  <td style={{ padding: '11px 16px', textAlign: 'right' }}>
                                    {revSurp !== null && revSurp !== undefined ? (
                                      <Chip
                                        size="small"
                                        label={`${revSurp > 0 ? '+' : ''}${revSurp.toFixed(1)}% ${isRevBeat ? 'beat ⭡' : 'miss ⭣'}`}
                                        sx={{
                                          height: 20,
                                          fontSize: '0.7rem',
                                          fontWeight: 800,
                                          bgcolor: isRevBeat ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)',
                                          color: isRevBeat ? '#10B981' : '#EF4444',
                                        }}
                                      />
                                    ) : (
                                      <span style={{ color: '#64748B' }}>—</span>
                                    )}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </Box>
                    </Box>
                  )
                })()}
              </Box>
            </Paper>
          )}
        </Box>
      )}
    </Box>
  )
}
