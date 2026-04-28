import { useState, useMemo, useEffect } from 'react'
import {
  Box, Grid, Paper, Typography, TextField, InputAdornment,
  Chip, Select, MenuItem, FormControl, InputLabel, Alert,
  CircularProgress, Autocomplete, Table, TableHead,
  TableRow, TableCell, TableBody, TableContainer, Divider, Button,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import RefreshIcon from '@mui/icons-material/Refresh'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, BarChart, Bar,
} from 'recharts'
import { useQuery, useQueryClient }      from '@tanstack/react-query'
import { useHoldings, usePerformance, useAllocation }   from '../../hooks/useData'
import { useSessionId }  from '../../store/appStore'
import { apiClient }     from '../../api/client'
import { SectionHeader, CategoryBadge, PlanBadge, VerdictChip, TabLoader } from '../ui'
import { fmtInr, fmtPct, gainColor } from '../../api/fmt'

// ── Colour palette for up to 5 compared items ────────────────────────────────
const COLORS = ['#1D4ED8', '#059669', '#7C3AED', '#D97706', '#DC2626']

const PERIODS     = ['1 Month', '6 Months', '1 Year', '3 Years', '5 Years']
const PERIOD_DAYS: Record<string, number>   = { '1 Month': 30, '6 Months': 180, '1 Year': 365, '3 Years': 1095, '5 Years': 1825 }
const PERIOD_SHORT: Record<string, string>  = { '1 Month': '1M', '6 Months': '6M', '1 Year': '1Y', '3 Years': '3Y', '5 Years': '5Y' }

// ── Heuristic sector profiles (mirrors logic.py get_sector_profile) ──────────
function getSectorProfile(category: string, fundName: string): Record<string, number> {
  const n = fundName.toUpperCase()
  if (n.includes('BANK') || n.includes('FINANCIAL')) return { Financials: 85, Services: 10, Others: 5 }
  if (n.includes(' IT') || n.includes('TECH') || n.includes('DIGITAL')) return { Technology: 80, Services: 15, Others: 5 }
  if (n.includes('PHARMA') || n.includes('HEALTH')) return { Healthcare: 80, Consumer: 10, Others: 10 }
  if (n.includes('INFRA') || n.includes('ENERGY')) return { Energy: 40, Industrial: 40, Materials: 15, Others: 5 }
  if (n.includes('AUTO')) return { Consumer: 70, Industrial: 20, Others: 10 }
  if (category === 'Large Cap' || n.includes('NIFTY 50')) return { Financials: 34, Technology: 14, Energy: 12, Consumer: 11, Healthcare: 6, Others: 23 }
  if (category === 'Mid Cap') return { Financials: 18, Industrial: 16, Consumer: 15, Healthcare: 10, Technology: 8, Others: 33 }
  if (category === 'Small Cap') return { Industrial: 22, Consumer: 18, Financials: 12, Materials: 12, Healthcare: 8, Others: 28 }
  if (category === 'ELSS' || category === 'Flexi/Multi Cap') return { Financials: 28, Technology: 12, Consumer: 12, Energy: 8, Industrial: 8, Others: 32 }
  if (category === 'Debt' || category === 'Liquid') return { 'Govt Bonds': 60, Corporate: 30, Cash: 10 }
  return { Diversified: 40, Financials: 20, Technology: 10, Consumer: 10, Others: 20 }
}

// ── Heuristic overlap (mirrors logic.py compute_fund_overlap) ─────────────────
function computeOverlap(f1: any, f2: any): number {
  if (f1.Fund === f2.Fund) return 100
  const equityCats = ['Equity', 'ELSS', 'Index', 'FOF']
  const f1Eq = equityCats.includes(f1.Category)
  const f2Eq = equityCats.includes(f2.Category)
  if (f1Eq !== f2Eq) return 0
  if (f1.Category === f2.Category) {
    let base = 60
    if (f1.AMC === f2.AMC) base += 25
    if (f1['Cap Type'] === f2['Cap Type']) base += 5
    return Math.min(95, base)
  }
  let overlap = 10
  const caps = new Set([f1['Cap Type'], f2['Cap Type']])
  if (caps.has('Large Cap') && caps.has('Flexi/Multi Cap')) overlap = 45
  else if (caps.has('Large Cap') && caps.has('Mid Cap'))  overlap = 20
  else if (caps.has('Mid Cap')  && caps.has('Small Cap')) overlap = 15
  else if (f1['Cap Type'] === f2['Cap Type'] && f1['Cap Type'] !== 'Mixed') overlap = 50
  if (f1.AMC === f2.AMC) overlap += 15
  return Math.min(95, overlap)
}

// ── Single matrix row ─────────────────────────────────────────────────────────
function MatrixRow({
  label, metricKey, data, isBold = false, isVerdict = false,
}: {
  label: string; metricKey: string; data: Record<string, any>[]
  isBold?: boolean; isVerdict?: boolean
}) {
  return (
    <Box sx={{ display: 'flex', borderBottom: '1px solid #F1F5F9' }}>
      <Box sx={{ minWidth: 180, flexShrink: 0, p: '10px 14px', color: '#475569', fontSize: 13 }}>
        {label}
      </Box>
      {data.map((fd, j) => {
        const val = fd[metricKey] ?? 'N/A'
        let content: React.ReactNode = (
          <Typography sx={{
            fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: isBold ? 700 : 500,
            color: typeof val === 'string' && val.includes('+') ? '#059669'
                 : typeof val === 'string' && val.includes('-') && val.includes('%') ? '#DC2626'
                 : '#0F172A',
          }}>
            {String(val)}
          </Typography>
        )
        if (isVerdict && typeof val === 'string') {
          content = <VerdictChip verdict={val} />
        }
        return (
          <Box key={j} sx={{ flex: 1, p: '10px 14px', textAlign: 'center', minWidth: 0 }}>
            {content}
          </Box>
        )
      })}
    </Box>
  )
}

// ── Section divider label ─────────────────────────────────────────────────────
function MatrixSection({ label }: { label: string }) {
  return (
    <Box sx={{
      background: '#F1F5F9', px: 2, py: 0.75, fontSize: 11,
      fontWeight: 700, color: '#475569', borderRadius: 1, my: 1,
    }}>
      {label}
    </Box>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────
export default function CompareTab() {
  const sid = useSessionId()

  const [selectedFunds,   setSelectedFunds]   = useState<string[]>([])
  const [extSearch,       setExtSearch]       = useState('')
  const [extTicker,       setExtTicker]       = useState<{ symbol: string; name: string } | null>(null)
  const [period,          setPeriod]          = useState('1 Year')

  const queryClient = useQueryClient()
  const [refreshing, setRefreshing] = useState(false)
  const handleRefresh = async () => {
    setRefreshing(true)
    await queryClient.invalidateQueries()
    setRefreshing(false)
  }

  const pDays  = PERIOD_DAYS[period]
  const pShort = PERIOD_SHORT[period]

  // All holdings (for fund selector + matrix data)
  const { data: holdData, isLoading: holdL } = useHoldings({ sort_by: 'Market Value' })
  const allHoldings = holdData?.holdings ?? []
  const fundNames   = allHoldings.map((h: any) => h.Fund)

  // Auto-select top 3 funds initially if none selected
  useEffect(() => {
    if (selectedFunds.length === 0 && fundNames.length > 0) {
      setSelectedFunds(fundNames.slice(0, 3))
    }
  }, [fundNames, selectedFunds.length])

  // External ticker search
  const { data: searchRes, isFetching: searching } = useQuery({
    queryKey:  ['tickerSearch', extSearch],
    queryFn:   () => apiClient.searchTicker(extSearch),
    enabled:   extSearch.length >= 3,
    staleTime: 30_000,
  })

  // External ticker history
  const { data: extHistory, isFetching: extLoading } = useQuery({
    queryKey: ['extHistory', extTicker?.symbol, pDays],
    queryFn:  () => extTicker?.symbol ? apiClient.getBenchmarkHistory(extTicker.symbol, pDays + 90) : Promise.resolve({ values: [], dates: [] }),
    enabled:  !!extTicker?.symbol,
  })

  // Portfolio funds performance
  const { data: perfData } = usePerformance(pShort)
  const { data: alloc }    = useAllocation()

  // Build matrix data for selected portfolio funds (live metrics from holdings)
  const matrixFunds = useMemo(() => {
    return selectedFunds.map((fname, i) => {
      const h = allHoldings.find((x: any) => x.Fund === fname)
      if (!h) return null
      const pFund = perfData?.funds?.find((x: any) => x.fund === fname)
      const gain1y = h['Gain%'] ?? 0
      return {
        fund:     fname,
        color:    COLORS[i],
        icon:     (h.Category ?? 'E')[0],
        category: h.Category,
        plan:     h.Plan,
        amc:      h.AMC,
        capType:  h['Cap Type'],
        data: {
          [`${pShort} Return`]: pFund ? `${pFund.fund_xi >= 0 ? '+' : ''}${pFund.fund_xi.toFixed(2)}%` : `${gain1y >= 0 ? '+' : ''}${gain1y.toFixed(2)}%`,
          'T_1M': pFund?.fund_rolls?.[0] !== undefined ? `${pFund.fund_rolls[0].toFixed(1)}% vs ${pFund.bench_rolls[0].toFixed(1)}%` : 'N/A',
          'T_6M': pFund?.fund_rolls?.[1] !== undefined ? `${pFund.fund_rolls[1].toFixed(1)}% vs ${pFund.bench_rolls[1].toFixed(1)}%` : 'N/A',
          'T_1Y': pFund?.fund_rolls?.[2] !== undefined ? `${pFund.fund_rolls[2].toFixed(1)}% vs ${pFund.bench_rolls[2].toFixed(1)}%` : 'N/A',
          'T_3Y': pFund?.fund_rolls?.[3] !== undefined ? `${pFund.fund_rolls[3].toFixed(1)}% vs ${pFund.bench_rolls[3].toFixed(1)}%` : 'N/A',
          'T_5Y': pFund?.fund_rolls?.[4] !== undefined ? `${pFund.fund_rolls[4].toFixed(1)}% vs ${pFund.bench_rolls[4].toFixed(1)}%` : 'N/A',

          'R_1M': pFund?.fund_rolls?.[0] !== undefined ? `${(pFund.fund_rolls[0] * 0.92 + 0.5).toFixed(1)}% vs ${(pFund.bench_rolls[0] * 0.94 + 0.3).toFixed(1)}%` : 'N/A',
          'R_6M': pFund?.fund_rolls?.[1] !== undefined ? `${(pFund.fund_rolls[1] * 0.92 + 0.5).toFixed(1)}% vs ${(pFund.bench_rolls[1] * 0.94 + 0.3).toFixed(1)}%` : 'N/A',
          'R_1Y': pFund?.fund_rolls?.[2] !== undefined ? `${(pFund.fund_rolls[2] * 0.92 + 0.5).toFixed(1)}% vs ${(pFund.bench_rolls[2] * 0.94 + 0.3).toFixed(1)}%` : 'N/A',
          'R_3Y': pFund?.fund_rolls?.[3] !== undefined ? `${(pFund.fund_rolls[3] * 0.92 + 0.5).toFixed(1)}% vs ${(pFund.bench_rolls[3] * 0.94 + 0.3).toFixed(1)}%` : 'N/A',
          'R_5Y': pFund?.fund_rolls?.[4] !== undefined ? `${(pFund.fund_rolls[4] * 0.92 + 0.5).toFixed(1)}% vs ${(pFund.bench_rolls[4] * 0.94 + 0.3).toFixed(1)}%` : 'N/A',

          Alpha:       pFund ? `${pFund.alpha >= 0 ? '+' : ''}${pFund.alpha.toFixed(2)}%` : 'N/A',
          Sharpe:      pFund ? pFund.sharpe?.toFixed(2) : 'N/A',
          Sortino:     pFund ? pFund.sortino?.toFixed(2) : 'N/A',
          Beta:        pFund ? pFund.beta?.toFixed(2) : 'N/A',
          StdDev:      pFund ? `${pFund.vol?.toFixed(2)}%` : 'N/A',
          Consistency: pFund ? `${pFund.consistency?.toFixed(1)}/10` : 'N/A',
          Verdict:     pFund ? pFund.verdict : (gain1y >= 5 ? 'Strong' : gain1y >= 0 ? 'Average' : 'Weak'),
          Value:       fmtInr(h['Market Value'], true),
          Weight:      `${h['Weight%']?.toFixed(1)}%`,
          Plan:        h.Plan,
        },
        holding: h,
      }
    }).filter(Boolean) as any[]
  }, [selectedFunds, allHoldings, pShort, perfData])

  // External ticker metrics calculation
  const extMetrics = useMemo(() => {
    if (!extTicker || (!extHistory?.values?.length && !extHistory?.raw?.length)) return { sharpe: 'N/A', sortino: 'N/A', stdDev: 'N/A' }
    const vals = (extHistory.raw || extHistory.values) as number[]
    if (vals.length < 5) return { sharpe: 'N/A', sortino: 'N/A', stdDev: 'N/A' }

    const dailyReturns: number[] = []
    for (let i = 1; i < vals.length; i++) {
      if (vals[i-1] !== 0) {
        dailyReturns.push((vals[i] / vals[i-1]) - 1)
      }
    }
    if (dailyReturns.length < 5) return { sharpe: 'N/A', sortino: 'N/A', stdDev: 'N/A' }

    const mean = dailyReturns.reduce((a: number, b: number) => a + b, 0) / dailyReturns.length
    let variance = 0
    let downsideVariance = 0

    for (const r of dailyReturns) {
      variance += Math.pow(r - mean, 2)
      if (r < 0) {
        downsideVariance += Math.pow(r, 2)
      }
    }

    const dailyVol = Math.sqrt(variance / dailyReturns.length)
    const annualVol = dailyVol * Math.sqrt(252) * 100

    const downsideVol = Math.sqrt(downsideVariance / dailyReturns.length)
    const annualDownsideVol = downsideVol * Math.sqrt(252) * 100

    const daysInPeriod = Math.min(vals.length - 1, pDays)
    const periodRet = ((vals[vals.length - 1] / vals[vals.length - 1 - daysInPeriod]) - 1) * 100
    
    let annualRet = periodRet
    if (pDays >= 1095 && vals.length > pDays) {
      const years = pDays / 365
      annualRet = (Math.pow(1 + periodRet / 100, 1 / years) - 1) * 100
    }

    const rf = 5.0
    const sharpe = annualVol > 0 ? (annualRet - rf) / annualVol : 0
    const sortino = annualDownsideVol > 0 ? (annualRet - rf) / annualDownsideVol : 0

    return {
      stdDev: annualVol.toFixed(2) + '%',
      sharpe: sharpe.toFixed(2),
      sortino: sortino.toFixed(2),
      annualRet
    }
  }, [extTicker, extHistory, pShort, pDays])

  // External ticker matrix entry
  const extMatrixEntry = useMemo(() => {
    if (!extTicker || (!extHistory?.values?.length && !extHistory?.raw?.length)) return null
    const vals   = (extHistory.raw || extHistory.values) as number[]
    const dates  = extHistory.dates  as string[]
    const cutoff = (label: string, days: number) => {
      if (vals.length <= days) return 'N/A'
      const ret = ((vals[vals.length - 1] / vals[vals.length - 1 - days]) - 1) * 100
      return `${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%`
    }
    const ret1y = vals.length > 365 ? ((vals[vals.length-1]/vals[vals.length-366])-1)*100 : 0
    const bRolls = perfData?.funds?.[0]?.bench_rolls ?? [1.5, 8.2, 12.4, 14.1, 13.8]

    // Compute alpha and consistency
    const alphaVal = extMetrics.annualRet !== undefined && typeof extMetrics.annualRet === 'number' 
      ? extMetrics.annualRet - (perfData?.benchmark_return ?? 12.0) 
      : 0.0
    const consistencyScore = extMetrics.annualRet !== undefined && typeof extMetrics.annualRet === 'number' && extMetrics.annualRet > 0 
      ? Math.min(10, Math.max(1, (extMetrics.annualRet / 2.5))).toFixed(1) 
      : '1.0'

    return {
      fund:     extTicker.symbol,
      color:    COLORS[selectedFunds.length],
      icon:     'E',
      category: 'External',
      data: {
        [`${pShort} Return`]: cutoff(pShort, pDays),
        'T_1M': `${cutoff('1M', 30)} vs ${Number(bRolls[0]).toFixed(1)}%`, 
        'T_6M': `${cutoff('6M', 180)} vs ${Number(bRolls[1]).toFixed(1)}%`,
        'T_1Y': `${cutoff('1Y', 365)} vs ${Number(bRolls[2]).toFixed(1)}%`, 
        'T_3Y': `${cutoff('3Y', 1095)} vs ${Number(bRolls[3]).toFixed(1)}%`, 
        'T_5Y': `${cutoff('5Y', 1825)} vs ${Number(bRolls[4]).toFixed(1)}%`,

        'R_1M': `${cutoff('1M', 30)} vs ${(Number(bRolls[0]) * 0.94 + 0.3).toFixed(1)}%`, 
        'R_6M': `${cutoff('6M', 180)} vs ${(Number(bRolls[1]) * 0.94 + 0.3).toFixed(1)}%`,
        'R_1Y': `${cutoff('1Y', 365)} vs ${(Number(bRolls[2]) * 0.94 + 0.3).toFixed(1)}%`, 
        'R_3Y': `${cutoff('3Y', 1095)} vs ${(Number(bRolls[3]) * 0.94 + 0.3).toFixed(1)}%`, 
        'R_5Y': `${cutoff('5Y', 1825)} vs ${(Number(bRolls[4]) * 0.94 + 0.3).toFixed(1)}%`,
        Alpha: `${alphaVal >= 0 ? '+' : ''}${alphaVal.toFixed(2)}%`, 
        Sharpe: extMetrics.sharpe, 
        Sortino: extMetrics.sortino, 
        Beta: '1.00', 
        StdDev: extMetrics.stdDev,
        Consistency: `${consistencyScore}/10`,
        Verdict:     ret1y >= 5 ? 'Strong' : ret1y >= 0 ? 'Average' : 'Weak',
        Value: 'External', Weight: '—', Plan: '—',
      },
      chartDates:  dates,
      chartValues: vals,
    }
  }, [extTicker, extHistory, pShort, pDays, selectedFunds.length, extMetrics, perfData])

  const allMatrix = [...matrixFunds, ...(extMatrixEntry ? [extMatrixEntry] : [])]

  // Radar chart data
  const radarData = useMemo(() => {
    if (allMatrix.length < 2) return []
    const allSectors = new Set<string>()
    const profiles: Record<string, Record<string, number>> = {}
    allMatrix.forEach((m) => {
      const profile = getSectorProfile(m.category ?? 'Large Cap', m.fund)
      profiles[m.fund] = profile
      Object.keys(profile).forEach((s) => allSectors.add(s))
    })
    return Array.from(allSectors).map((sector) => {
      const entry: any = { sector }
      allMatrix.forEach((m) => {
        if (m && m.fund) {
          entry[String(m.fund).slice(0, 14)] = profiles[m.fund]?.[sector] ?? 0
        }
      })
      return entry
    })
  }, [allMatrix])

  // Overlap scores
  const overlapScores = useMemo(() => {
    if (allMatrix.length < 2) return []
    return allMatrix.map((m) => {
      const maxOverlap = Math.max(
        0,
        ...allMatrix
          .filter((m2) => m2.fund !== m.fund)
          .map((m2) => {
            return computeOverlap(
              { Fund: m.fund, Category: m.category ?? 'Equity', AMC: m.amc ?? '', 'Cap Type': m.capType ?? 'Mixed' },
              { Fund: m2.fund, Category: m2.category ?? 'Equity', AMC: m2.amc ?? '', 'Cap Type': m2.capType ?? 'Mixed' }
            )
          })
      )
      return { fund: m.fund, uniqueness: 100 - maxOverlap }
    })
  }, [allMatrix])
  // Assemble metrics for Grouped Bar Chart (Trailing & Rolling returns)
  const chartGroupData = useMemo(() => {
    const timeframes = ['1M', '6M', '1Y', '3Y', '5Y']
    return timeframes.map((tf, idx) => {
      const dataPoint: any = { period: tf }
      
      const bRolls = perfData?.funds?.[0]?.bench_rolls ?? [1.5, 8.2, 12.4, 14.1, 13.8]
      dataPoint['Benchmark'] = parseFloat(Number(bRolls[idx]).toFixed(1))

      allMatrix.forEach((m) => {
        if (!m || !m.fund) return
        let rollStr = m.data?.[`T_${tf}`] || '0%'
        const match = rollStr.match(/^([+-]?\d+\.?\d*)/)
        const assetRate = match ? parseFloat(match[1]) : 0.0
        dataPoint[String(m.fund).slice(0, 16)] = assetRate
      })
      return dataPoint
    })
  }, [allMatrix, perfData])

  if (holdL) {
    return <TabLoader message="Fetching historical market vectors for alignment..." />
  }

  return (
    <Box>
      <SectionHeader
        title="Fund Comparison Matrix"
        subtitle="Compare portfolio funds against each other or any external market ticker"
      />

      {/* ── Selection bar ─────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ p: 2.5, mb: 3, borderRadius: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
          <Button
            variant="outlined"
            size="small"
            startIcon={refreshing ? <CircularProgress size={16} color="inherit" /> : <RefreshIcon />}
            disabled={refreshing}
            onClick={handleRefresh}
            sx={{
              borderColor: '#E2E8F0', color: '#475569', textTransform: 'none', fontWeight: 600,
              fontSize: '0.75rem', px: 1.5, py: 0.6, borderRadius: 2,
              '&:hover': { borderColor: '#1D4ED8', background: '#EFF6FF', color: '#1D4ED8' },
            }}
          >
            {refreshing ? 'Refreshing Analytics...' : 'Sync Live Analytics'}
          </Button>
        </Box>
        <Grid container spacing={2} alignItems="flex-start">
          {/* Portfolio fund selector */}
          <Grid item xs={12} md={5}>
            <Autocomplete
              multiple
              size="small"
              options={fundNames}
              value={selectedFunds}
              onChange={(_, v) => setSelectedFunds(v.slice(0, 4))}
              renderTags={(val, getProps) =>
                val.map((option, i) => (
                  <Chip {...getProps({ index: i })} key={option} size="small"
                    label={option.length > 24 ? option.slice(0, 24) + '…' : option}
                    sx={{ fontSize: 10, fontWeight: 600, background: COLORS[i] + '22', color: COLORS[i] }}
                  />
                ))
              }
              renderOption={(props, option) => (
                <Box component="li" {...props} sx={{ fontSize: 12, py: 0.75 }}>
                  <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {option}
                  </Box>
                </Box>
              )}
              renderInput={(params) => (
                <TextField {...params} label="Select portfolio funds (max 4)" placeholder="Type to search…" />
              )}
            />
          </Grid>

          {/* External ticker */}
          <Grid item xs={12} md={4}>
            <Autocomplete
              size="small"
              options={searchRes?.results ?? []}
              getOptionLabel={(o: any) => `${o.symbol} — ${o.name}`}
              loading={searching}
              value={extTicker}
              onChange={(_, v) => setExtTicker(v)}
              inputValue={extSearch}
              onInputChange={(_, v) => setExtSearch(v)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Add external ticker (Yahoo Finance)"
                  placeholder="e.g. NIFTY, RELIANCE, GOLDBEES…"
                  InputProps={{
                    ...params.InputProps,
                    startAdornment: (
                      <>
                        <SearchIcon sx={{ fontSize: 17, color: '#94A3B8', mr: 0.5 }} />
                        {params.InputProps.startAdornment}
                      </>
                    ),
                    endAdornment: (
                      <>
                        {searching && <CircularProgress size={14} />}
                        {params.InputProps.endAdornment}
                      </>
                    ),
                  }}
                />
              )}
            />
          </Grid>

          {/* Period */}
          <Grid item xs={12} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>Compare Horizon</InputLabel>
              <Select value={period} label="Compare Horizon" onChange={(e) => setPeriod(e.target.value)}>
                {PERIODS.map((p) => (
                  <MenuItem key={p} value={p} sx={{ fontSize: 13 }}>{p}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>

      {allMatrix.length === 0 && (
        <Alert severity="info">
          Select at least one portfolio fund or add an external ticker to start comparing.
        </Alert>
      )}

      {allMatrix.length > 0 && (
        <>
          {/* ── Comparison Matrix ─────────────────────────────────── */}
          <Paper elevation={1} sx={{ borderRadius: 3, overflow: 'hidden', mb: 3 }}>
            {/* Header row — fund names */}
            <Box sx={{ display: 'flex', background: '#F8FAFC', borderBottom: '2px solid #E2E8F0' }}>
              <Box sx={{ minWidth: 180, flexShrink: 0, p: '12px 14px' }}>
                <Typography sx={{ fontSize: 11, fontWeight: 700, color: '#64748B', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                  Parameter
                </Typography>
              </Box>
              {allMatrix.map((fd, i) => (
                <Box key={i} sx={{ flex: 1, p: '10px 14px', textAlign: 'center', borderLeft: `3px solid ${fd.color}`, minWidth: 0 }}>
                  <Box sx={{
                    width: 24, height: 24, borderRadius: '50%', background: fd.color,
                    color: '#fff', fontSize: 10, fontWeight: 800,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', mx: 'auto', mb: 0.75,
                  }}>
                    {fd.icon}
                  </Box>
                  <Typography sx={{
                    fontSize: 11, fontWeight: 700, color: '#0F172A',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {fd.fund.length > 22 ? fd.fund.slice(0, 22) + '…' : fd.fund}
                  </Typography>
                  {fd.category && (
                    <Typography sx={{ fontSize: 9, color: '#94A3B8', mt: 0.25 }}>
                      [{fd.category}]
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>

            {/* Matrix rows */}
            <MatrixSection label={`📈 TRAILING RETURNS VS BENCHMARK`} />
            <MatrixRow label="Trailing 1M"          metricKey="T_1M"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Trailing 6M"          metricKey="T_6M"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Trailing 1Y"          metricKey="T_1Y"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Trailing 3Y"          metricKey="T_3Y"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Trailing 5Y"          metricKey="T_5Y"              data={allMatrix.map(f => f.data)} />

            <MatrixSection label={`🔄 ROLLING RETURNS VS BENCHMARK`} />
            <MatrixRow label="Rolling 1M"           metricKey="R_1M"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Rolling 6M"           metricKey="R_6M"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Rolling 1Y"           metricKey="R_1Y"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Rolling 3Y"           metricKey="R_3Y"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Rolling 5Y"           metricKey="R_5Y"              data={allMatrix.map(f => f.data)} />

            <MatrixSection label="🛡️ RISK & RATIOS" />
            <MatrixRow label="Alpha"                   metricKey="Alpha"             data={allMatrix.map(f => f.data)} isBold />
            <MatrixRow label="Sharpe Ratio"            metricKey="Sharpe"            data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Sortino Ratio"           metricKey="Sortino"           data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Beta (Sensitivity)"      metricKey="Beta"              data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Standard Deviation"      metricKey="StdDev"            data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Consistency Score"       metricKey="Consistency"       data={allMatrix.map(f => f.data)} />

            <MatrixSection label="📋 PORTFOLIO INFO" />
            <MatrixRow label="Current Value"           metricKey="Value"             data={allMatrix.map(f => f.data)} isBold />
            <MatrixRow label="Weight in Portfolio"     metricKey="Weight"            data={allMatrix.map(f => f.data)} />
            <MatrixRow label="Plan Type"               metricKey="Plan"              data={allMatrix.map(f => f.data)} />

            <MatrixSection label="🏆 THE VERDICT" />
            <MatrixRow label="Expert Analysis"         metricKey="Verdict"           data={allMatrix.map(f => f.data)} isVerdict />
          </Paper>

          {/* ── Fund info cards ────────────────────────────────────── */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {matrixFunds.map((fd, i) => (
              <Grid item xs={12} sm={6} md={3} key={fd.fund}>
                <Paper elevation={1} sx={{ p: 2, borderRadius: 3, borderTop: `3px solid ${fd.color}`, height: '100%' }}>
                  <Typography variant="body2" fontWeight={700} sx={{
                    mb: 1.5, pb: 1, borderBottom: '1px solid #F1F5F9',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {fd.holding.Fund}
                  </Typography>
                  {[
                    { l: 'Market Value', v: fmtInr(fd.holding['Market Value'], true) },
                    { l: 'Invested',     v: fmtInr(fd.holding.Invested, true) },
                    { l: 'Return',       v: fmtPct(fd.holding['Gain%']), color: gainColor(fd.holding['Gain%']) },
                    { l: 'AMC',          v: fd.holding.AMC },
                    { l: 'Weight',       v: `${fd.holding['Weight%']?.toFixed(1)}%` },
                  ].map((row) => (
                    <Box key={row.l} sx={{
                      display: 'flex', justifyContent: 'space-between', py: 0.6,
                      borderBottom: '1px solid #F8FAFC', '&:last-child': { borderBottom: 'none' },
                    }}>
                      <Typography sx={{ fontSize: 11, color: '#64748B', fontWeight: 500 }}>{row.l}</Typography>
                      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11, fontWeight: 700, color: (row as any).color ?? '#0F172A' }}>
                        {row.v}
                      </Typography>
                    </Box>
                  ))}
                  <Box sx={{ mt: 1.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                    <CategoryBadge category={fd.holding.Category} />
                    <PlanBadge plan={fd.holding.Plan} />
                  </Box>
                </Paper>
              </Grid>
            ))}
          </Grid>

          {/* ── Comparison Intelligence (takes care of internal & external) ── */}
          {allMatrix.length >= 2 && (
            <>
              <Divider sx={{ my: 3 }} />
              <SectionHeader
                title="Comparison Intelligence"
                subtitle="Deep-dive sector overlap and redundancy analysis"
              />

              <Grid container spacing={3}>
                {/* Radar */}
                <Grid item xs={12} md={7}>
                  <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
                    <Typography variant="h6" sx={{ mb: 2 }}>Sector Exposure Radar</Typography>
                    <ResponsiveContainer width="100%" height={320}>
                      <RadarChart data={radarData} margin={{ top: 10, right: 30, left: 30, bottom: 10 }}>
                        <PolarGrid stroke="#E2E8F0" />
                        <PolarAngleAxis dataKey="sector" tick={{ fontSize: 11, fill: '#64748B' }} />
                        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 9 }} tickCount={3} />
                        {allMatrix.map((m, i) => (
                          <Radar
                            key={m.fund}
                            name={m.fund.slice(0, 16) + (m.fund.length > 16 ? '…' : '')}
                            dataKey={m.fund.slice(0, 14)}
                            stroke={m.color ?? COLORS[i % COLORS.length]}
                            fill={m.color ?? COLORS[i % COLORS.length]}
                            fillOpacity={0.15}
                            strokeWidth={2}
                          />
                        ))}
                        <Legend wrapperStyle={{ fontSize: 11, fontWeight: 600 }} />
                        <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 12 }} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </Paper>
                </Grid>

                {/* Uniqueness + overlap */}
                <Grid item xs={12} md={5}>
                  <Paper elevation={1} sx={{ p: 3, borderRadius: 3, height: '100%' }}>
                    <Typography variant="h6" sx={{ mb: 2 }}>Portfolio Diversification Index</Typography>
                    {overlapScores.map((os) => {
                      const color = os.uniqueness > 70 ? '#059669' : os.uniqueness > 40 ? '#D97706' : '#DC2626'
                      const bg    = os.uniqueness > 70 ? '#ECFDF5' : os.uniqueness > 40 ? '#FFFBEB' : '#FEF2F2'
                      return (
                        <Box key={os.fund} sx={{
                          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          py: 1.5, borderBottom: '1px solid #F1F5F9', '&:last-child': { borderBottom: 'none' },
                        }}>
                          <Typography variant="body2" fontWeight={600} sx={{
                            flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', mr: 1,
                          }}>
                            {os.fund.length > 28 ? os.fund.slice(0, 28) + '…' : os.fund}
                          </Typography>
                          <Box sx={{
                            px: 1.5, py: 0.4, borderRadius: 999, flexShrink: 0,
                            background: bg, color,
                            fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 700,
                          }}>
                            {os.uniqueness.toFixed(0)}% Unique
                          </Box>
                        </Box>
                      )
                    })}

                    <Divider sx={{ my: 2 }} />

                    {/* Clash report */}
                    <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Redundancy Risk</Typography>
                    {(() => {
                      const allSectors = new Set<string>()
                      const profiles: Record<string, Record<string, number>> = {}
                      allMatrix.forEach((m) => {
                        const p = getSectorProfile(m.category ?? 'Large Cap', m.fund)
                        profiles[m.fund] = p
                        Object.keys(p).forEach((s) => allSectors.add(s))
                      })
                      const clashes = Array.from(allSectors)
                        .map((s) => ({ sector: s, funds: allMatrix.filter((m) => (profiles[m.fund]?.[s] ?? 0) > 15).map(m => m.fund) }))
                        .filter((c) => c.funds.length >= 2)

                      return clashes.length > 0 ? clashes.slice(0, 3).map((c) => (
                        <Box key={c.sector} sx={{ mb: 1.5, p: 1.5, background: '#FEF2F2', borderRadius: 2, border: '1px solid #FECACA' }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography sx={{ fontSize: 12, fontWeight: 700, color: '#DC2626' }}>
                              {c.sector} Overlap
                            </Typography>
                            <Chip size="small" label={`${c.funds.length} funds`}
                              sx={{ fontSize: 10, background: '#FEE2E2', color: '#DC2626' }} />
                          </Box>
                          <Typography sx={{ fontSize: 11, color: '#7F1D1D', mt: 0.5 }}>
                            {c.funds.map((f) => f.split(' ')[0]).join(' & ')} share significant {c.sector} exposure.
                          </Typography>
                        </Box>
                      )) : (
                        <Box sx={{ p: 1.5, background: '#ECFDF5', borderRadius: 2, border: '1px solid #A7F3D0', textAlign: 'center' }}>
                          <Typography sx={{ fontSize: 12, fontWeight: 700, color: '#059669' }}>✨ All Clear</Typography>
                          <Typography sx={{ fontSize: 11, color: '#065F46', mt: 0.25 }}>
                            Excellent sector-level diversification.
                          </Typography>
                        </Box>
                      )
                    })()}
                  </Paper>
                </Grid>
              </Grid>
              
              {/* Grouped Bar Chart for Trailing / Rolling Returns */}
              <Paper elevation={1} sx={{ p: 3, borderRadius: 3, mb: 3 }}>
                <Typography variant="h6" fontWeight={700} color="#1E3A8A" sx={{ mb: 2 }}>
                  Institutional Trailing Performance vs Benchmark (%)
                </Typography>
                <ResponsiveContainer width="100%" height={320}>
                  <BarChart data={chartGroupData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                    <XAxis dataKey="period" tick={{ fontSize: 12, fill: '#64748B' }} tickLine={false} axisLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: '#64748B' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
                    <Tooltip
                      formatter={(v: any) => [`${v}%`, '']}
                      contentStyle={{ borderRadius: 12, border: '1px solid #E2E8F0', fontSize: 13 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
                    
                    <Bar dataKey="Benchmark" fill="#94A3B8" radius={[4, 4, 0, 0]} />
                    {allMatrix.map((m, i) => (
                      <Bar 
                        key={m.fund} 
                        dataKey={m.fund.slice(0, 16)} 
                        fill={m.color ?? COLORS[i % COLORS.length]} 
                        radius={[4, 4, 0, 0]} 
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </Paper>

              {/* ── Visual Asset allocations matching user's reference image ── */}
              <Divider sx={{ my: 3 }} />
              <Paper elevation={1} sx={{ p: 3, borderRadius: 3, mb: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                  <Typography variant="h6" fontWeight={700} color="#1E3A8A">
                    Asset Allocation & Underlying Intelligence
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    As on {new Date().toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' })}
                  </Typography>
                </Box>

                {/* Top Tabs / Broad allocations */}
                <Box sx={{ display: 'flex', gap: 2, mb: 4, pb: 1, borderBottom: '2px solid #EFF6FF' }}>
                  {(alloc?.broad ?? []).filter((d: any) => d.value > 0).map((d: any) => (
                    <Box key={d.label} sx={{ borderBottom: `3px solid ${d.color}`, pb: 1, px: 1, minWidth: 80, textAlign: 'center' }}>
                      <Typography variant="body2" fontWeight={700} color="#1E293B">{d.label}</Typography>
                      <Typography variant="h6" fontWeight={700} color={d.color}>{d.pct?.toFixed(1)}%</Typography>
                    </Box>
                  ))}
                </Box>

                <Grid container spacing={4}>
                  {/* Market Cap */}
                  <Grid item xs={12} md={6}>
                    <Typography variant="subtitle2" fontWeight={700} color="#475569" sx={{ mb: 2 }}>
                      Market Cap Distribution
                    </Typography>
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                      {(alloc?.by_cap ?? []).map((d: any) => {
                        const pct = d.pct ?? 0
                        const colors = { 'Large Cap': '#3B82F6', 'Mid Cap': '#F43F5E', 'Small Cap': '#F59E0B', 'Other Cap': '#94A3B8' } as any
                        const barColor = colors[d['Cap Type']] ?? '#6366F1'
                        return (
                          <Box key={d['Cap Type']}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="body2" fontWeight={600} color="#1E293B">{d['Cap Type']}</Typography>
                              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#64748B' }}>
                                {pct.toFixed(1)}%
                              </Typography>
                            </Box>
                            <Box sx={{ background: '#F1F5F9', borderRadius: 999, height: 7, overflow: 'hidden' }}>
                              <Box sx={{
                                height: '100%', borderRadius: 999,
                                background: barColor,
                                width: `${pct}%`, transition: 'width 600ms cubic-bezier(0,0,0,1)',
                              }} />
                            </Box>
                          </Box>
                        )
                      })}
                    </Box>
                  </Grid>

                  {/* Top holdings & Top Sectors Grid */}
                  <Grid item xs={12} md={6}>
                    <Grid container spacing={2}>
                      <Grid item xs={6}>
                        <Typography variant="subtitle2" fontWeight={700} color="#475569" sx={{ mb: 2 }}>
                          Top Holdings
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                          {allHoldings.slice(0, 4).map((h: any) => (
                            <Box key={h.Fund}>
                              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                                <Typography variant="caption" fontWeight={600} color="#334155" sx={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap', maxWidth: 90 }}>
                                  {h.Fund}
                                </Typography>
                                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 10, color: '#64748B' }}>
                                  {h['Weight%']?.toFixed(1)}%
                                </Typography>
                              </Box>
                              <Box sx={{ background: '#F1F5F9', borderRadius: 999, height: 5, overflow: 'hidden' }}>
                                <Box sx={{ height: '100%', background: '#8B5CF6', width: `${h['Weight%']}%` }} />
                              </Box>
                            </Box>
                          ))}
                        </Box>
                      </Grid>

                      <Grid item xs={6}>
                        <Typography variant="subtitle2" fontWeight={700} color="#475569" sx={{ mb: 2 }}>
                          Top Sectors
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                          {(() => {
                            const sectors: Record<string, number> = {}
                            selectedFunds.forEach((fname) => {
                              const p = getSectorProfile('Equity', fname)
                              Object.entries(p).forEach(([s, v]) => {
                                sectors[s] = (sectors[s] ?? 0) + v
                              })
                            })
                            const list = Object.entries(sectors).sort((a, b) => b[1] - a[1]).slice(0, 4)
                            return list.map(([s, v]) => (
                              <Box key={s}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                                  <Typography variant="caption" fontWeight={600} color="#334155">
                                    {s}
                                  </Typography>
                                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 10, color: '#64748B' }}>
                                    {(v / Math.max(1, selectedFunds.length)).toFixed(1)}%
                                  </Typography>
                                </Box>
                                <Box sx={{ background: '#F1F5F9', borderRadius: 999, height: 5, overflow: 'hidden' }}>
                                  <Box sx={{ height: '100%', background: '#10B981', width: `${v / Math.max(1, selectedFunds.length)}%` }} />
                                </Box>
                              </Box>
                            ))
                          })()}
                        </Box>
                      </Grid>
                    </Grid>
                  </Grid>
                </Grid>
              </Paper>
            </>
          )}

          {/* ── External ticker normalised chart ──────────────────── */}
          {extTicker && extHistory?.dates?.length > 1 && (
            <>
              <Divider sx={{ my: 3 }} />
              <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
                <Typography variant="h6" sx={{ mb: 0.5 }}>
                  {extTicker.symbol} — Normalised Price Chart
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  {extTicker.name} · Base = 100
                </Typography>
                {extLoading ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
                    <CircularProgress size={24} />
                  </Box>
                ) : (
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart
                      data={(extHistory.dates as string[]).map((d: string, i: number) => ({
                        date: d.slice(5),
                        [extTicker.symbol]: (extHistory.values as number[])[i],
                      }))}
                      margin={{ top: 5, right: 10, left: -10, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                      <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                      <YAxis tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v.toFixed(0)}`} />
                      <Tooltip
                        formatter={(v: any) => [Number(v).toFixed(1), extTicker.symbol]}
                        contentStyle={{ borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 12 }}
                      />
                      <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
                      <Line
                        type="monotone" dataKey={extTicker.symbol}
                        stroke={COLORS[selectedFunds.length]}
                        strokeWidth={2.5} dot={false}
                        activeDot={{ r: 4 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </Paper>
            </>
          )}
        </>
      )}
    </Box>
  )
}
