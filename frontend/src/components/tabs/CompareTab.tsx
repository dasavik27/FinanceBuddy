import { fmtInr } from '../../api/fmt'
import { useState, useMemo, useEffect } from 'react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, BarChart, Bar, AreaChart, Area,
} from 'recharts'
import {
  Box, Grid, Paper, Typography, TextField,
  Chip, CircularProgress, Autocomplete, Table, TableHead,
  TableRow, TableCell, TableBody, Button, Tooltip as MuiTooltip,
  ToggleButtonGroup, ToggleButton, Stack, Tabs, Tab, Skeleton, Slider, Modal, IconButton,
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'
import { alpha } from '@mui/material/styles'
import { motion, AnimatePresence } from 'framer-motion'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import AssessmentIcon from '@mui/icons-material/Assessment'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

import { useQuery, useQueries, useQueryClient } from '@tanstack/react-query'
import { useHoldings, usePerformance } from '../../hooks/useData'
import { useSessionId } from '../../store/appStore'
import { apiClient } from '../../api/client'
import { SectionHeader, VerdictChip, MetricCard, GlassTableContainer, GlassHeader, OverlayLoader } from '../ui'
import { ChartTooltip } from '../charts/ChartTooltip'
import { gainColor } from '../../api/fmt'

// ── Constants & Config ───────────────────────────────────────────────────────
const COLORS = ['#6366F1', '#4EDE93', '#F472B6', '#FBBF24', '#FB7185']

// ── Motion Variants ──────────────────────────────────────────────────────────
const containerVar = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
}

const itemVar = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { type: 'spring', damping: 25, stiffness: 300 } }
}

function InfoTooltip({ text }: { text: string }) {
  return (
    <MuiTooltip title={text} arrow placement="top" sx={{ '& .MuiTooltip-tooltip': { bgcolor: '#0F172A', color: '#fff', fontSize: 12, p: 1.5, borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)' } }}>
      <span style={{ display: 'inline-flex', verticalAlign: 'middle' }}>
        <InfoOutlinedIcon sx={{ fontSize: 14, ml: 0.5, opacity: 0.6, cursor: 'pointer', '&:hover': { opacity: 1, color: 'primary.main' } }} />
      </span>
    </MuiTooltip>
  )
}

// ── Logic Helpers ────────────────────────────────────────────────────────────

function calculateDrawdown(values: number[]): number[] {
  if (!values || !values.length) return []
  let peak = -Infinity
  return values.map(v => {
    if (v > peak) peak = v
    return peak === 0 ? 0 : ((v / peak) - 1) * 100
  })
}

// ── Main Component ───────────────────────────────────────────────────────────
export default function CompareTab() {
  const sid = useSessionId()
  const [selectedFunds, setSelectedFunds] = useState<string[]>(() => {
    const saved = localStorage.getItem(`compare_funds_${sid}`)
    return saved ? JSON.parse(saved) : []
  })

  useEffect(() => {
    localStorage.setItem(`compare_funds_${sid}`, JSON.stringify(selectedFunds))
  }, [selectedFunds, sid])

  const [extSearch, setExtSearch] = useState('')
  const [extTicker, setExtTicker] = useState<{ symbol: string; name: string } | null>(() => {
    const saved = localStorage.getItem(`compare_bench_${sid}`)
    return saved ? JSON.parse(saved) : null
  })

  useEffect(() => {
    if (extTicker) localStorage.setItem(`compare_bench_${sid}`, JSON.stringify(extTicker))
  }, [extTicker, sid])
  const [mode, setMode] = useState<'Overview' | 'Technical' | 'Trends'>('Overview')
  const [activeTrend, setActiveTrend] = useState<'Trailing' | 'Rolling' | 'Wealth' | 'Drawdown'>('Trailing')
  const [showSim, setShowSim] = useState(false)
  const [sipAmount, setSipAmount] = useState(25000)
  const [lumpsumAmount, setLumpsumAmount] = useState(500000)
  const [simYears, setSimYears] = useState(15)
  const queryClient = useQueryClient()

  const { data: holdData, isLoading: holdL, isFetching: holdF } = useHoldings({ sort_by: 'Market Value' })
  const allHoldings = holdData?.holdings ?? []
  const fundNames = allHoldings.map((h: any) => h.Fund)

  const { data: searchRes } = useQuery({
    queryKey: ['tickerSearch', extSearch],
    queryFn: () => apiClient.searchTicker(extSearch),
    enabled: extSearch.length >= 3,
  })

  // 1. Identify all assets for historical fetching
  const selectedAssets = useMemo(() => {
    const funds = selectedFunds.map((fname: string) => {
      const h: any = allHoldings.find((x: any) => x.Fund === fname)
      return { id: h?.ISIN || fname, name: fname, type: 'fund', short: fname.split(' ')[0] }
    })
    const bench = extTicker ? [{ id: extTicker.symbol, name: extTicker.name, type: 'bench', short: extTicker.name?.split(' ')[0] || extTicker.symbol }] : []
    return [...funds, ...bench]
  }, [selectedFunds, extTicker, allHoldings])

  // 2. Multi-fetch individual histories
  const historyResults = useQueries({
    queries: selectedAssets.map((a: any) => ({
      queryKey: ['assetHistory', a.id],
      queryFn: () => apiClient.getBenchmarkHistory(a.id, 1825),
      enabled: !!a.id,
      staleTime: 24 * 60 * 60 * 1000,
    }))
  })

  // 3. Multi-fetch rolling returns
  const rollingResults = useQueries({
    queries: selectedAssets.map((a: any) => ({
      queryKey: ['rollingReturns', sid, a.id],
      queryFn: () => apiClient.getRollingReturns(sid || '', a.id, 3),
      enabled: !!sid && !!a.id && activeTrend === 'Rolling',
      staleTime: 24 * 60 * 60 * 1000,
    }))
  })

  const [period, setPeriod] = useState('1Y')
  const { data: perfData, isLoading: perfL, isFetching: perfF, isError: perfE, error: perfErr } = usePerformance(period, { 
    include_funds: selectedFunds.join(','),
    benchmark: extTicker?.symbol || extTicker?.name || 'Nifty 50'
  })

  const historiesFetching = historyResults.some((r: any) => r.isFetching) || rollingResults.some((r: any) => r.isFetching)

  const cleanCoreName = (name: string) => {
    if (!name) return ''
    return name.toLowerCase()
      .replace(/(direct|regular|plan|growth|idcw|option|tax saver|fund|-|\b\w\b)/gi, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  }

  // 4. Matrix calculation merging technicals + individual charts
  const allMatrix = useMemo(() => {
    return selectedAssets.map((asset: any, i: number) => {
      const h: any = allHoldings.find((x: any) => x.Fund === asset.name)
      const pFund: any = (perfData as any)?.funds?.find((x: any) => {
        const hIsin = h?.ISIN?.toUpperCase()
        const xIsin = x.isin?.toUpperCase()
        if (hIsin && xIsin && hIsin === xIsin) return true
        
        if (x.fund === asset.name) return true

        const coreX = cleanCoreName(x.fund)
        const coreA = cleanCoreName(asset.name)
        if (coreX && coreA && (coreX.includes(coreA) || coreA.includes(coreX))) return true

        const tokensX = coreX.split(' ').filter(t => t.length > 2)
        const tokensA = coreA.split(' ').filter(t => t.length > 2)
        if (!tokensX.length || !tokensA.length) return false
        const intersection = tokensX.filter(t => tokensA.includes(t))
        return (intersection.length / Math.max(tokensX.length, tokensA.length)) >= 0.6
      })
      const hist = historyResults[i]?.data ?? {}
      const isBench = asset.type === 'bench'
      const bStats: any = (perfData as any)?.benchmark_stats
      const trailingDict: Record<string, number> = {}
      if (isBench && bStats?.returns) {
        Object.assign(trailingDict, bStats.returns)
      } else if (pFund?.roll_labels && pFund?.fund_rolls) {
        pFund.roll_labels.forEach((lbl: string, idx: number) => {
          if (pFund.fund_rolls[idx] != null) trailingDict[lbl] = pFund.fund_rolls[idx]
        })
      }

      return {
        name: asset.short,
        shortName: asset.short,
        fullName: asset.name,
        id: asset.id,
        isBench,
        color: COLORS[i % COLORS.length],
        // Technicals
        alpha: isBench ? (bStats?.alpha ?? 0) : (pFund?.alpha || '—'),
        beta: isBench ? (bStats?.beta ?? 1) : (pFund?.beta || '—'),
        sharpe: isBench ? (bStats?.sharpe ?? '—') : (pFund?.sharpe || '—'),
        sortino: isBench ? (bStats?.sortino ?? '—') : (pFund?.sortino || '—'),
        volatility: isBench ? (bStats?.volatility ?? '—') : (pFund?.vol || '—'),
        consistency: isBench ? '100%' : (pFund?.consistency || '—'),
        risk: isBench ? 'Moderate' : (pFund?.verdict || 'Average'),
        // Performance
        return: isBench ? ((perfData as any)?.benchmark_return ?? 0) : (pFund?.return_period || 0),
        trailing: trailingDict,
        history: hist,
        chartDates: hist.dates || [],
        chartValues: hist.values || [], 
        drawdownValues: calculateDrawdown(hist.values || []),
        data: {
          '1Y Ret': trailingDict['1Y'] != null ? `${trailingDict['1Y'] >= 0 ? '+' : ''}${trailingDict['1Y'].toFixed(1)}%` : (pFund ? `${pFund.fund_xi?.toFixed(1)}%` : '—'),
          '3Y Ret': trailingDict['3Y'] != null ? `${trailingDict['3Y'] >= 0 ? '+' : ''}${trailingDict['3Y'].toFixed(1)}%` : '—',
          'Alpha': isBench ? '0.0%' : (pFund ? `${pFund.alpha >= 0 ? '+' : ''}${pFund.alpha.toFixed(1)}%` : '—'),
          'Sharpe': isBench ? (bStats?.sharpe?.toFixed(2) ?? '—') : (pFund?.sharpe?.toFixed(2) ?? '—'),
          'Sortino': isBench ? (bStats?.sortino?.toFixed(2) ?? '—') : (pFund?.sortino?.toFixed(2) ?? '—'),
          'Beta': isBench ? '1.00' : (pFund?.beta?.toFixed(2) ?? '—'),
          'Volatility': isBench ? (bStats?.volatility != null ? `${bStats.volatility}%` : '—') : (pFund?.vol != null ? `${pFund.vol.toFixed(1)}%` : '—'),
          'Max Drawdown': isBench ? (bStats?.max_drawdown != null ? `${bStats.max_drawdown.toFixed(1)}%` : '—') : (pFund?.max_dd != null ? `${Number(pFund.max_dd).toFixed(1)}%` : '—'),
          'Expense Ratio': pFund?.er != null ? `${Number(pFund.er).toFixed(2)}%` : '—',
          'Consistency': isBench ? '10/10' : (pFund ? `${pFund.consistency?.toFixed(1)}/10` : '—'),
          'Verdict': isBench ? 'Target' : (pFund?.verdict ?? 'Average'),
          'P/E Ratio': pFund?.pe_ratio != null ? pFund.pe_ratio.toFixed(1) : (pFund?.is_debt ? 'N/A (Debt)' : '—'),
          'P/B Ratio': pFund?.pb_ratio != null ? pFund.pb_ratio.toFixed(1) : (pFund?.is_debt ? 'N/A (Debt)' : '—'),
          'Day Chg.%': isBench ? ((perfData as any)?.benchmark_day_chg != null ? `${(perfData as any).benchmark_day_chg >= 0 ? '+' : ''}${(perfData as any).benchmark_day_chg.toFixed(2)}%` : '—') : (h?.['Day Chg.%'] != null ? `${h['Day Chg.%'] >= 0 ? '+' : ''}${h['Day Chg.%'].toFixed(2)}%` : '—'),
          AlphaVal: isBench ? 0 : (pFund?.alpha ?? 0),
          SharpeVal: isBench ? (bStats?.sharpe ?? 0) : (pFund?.sharpe ?? 0),
          SortinoVal: isBench ? (bStats?.sortino ?? 0) : (pFund?.sortino ?? 0),
          VolVal: isBench ? (bStats?.volatility ?? 0) : (pFund?.vol ?? 100),
          ConsistVal: isBench ? 10 : (pFund?.consistency ?? 0),
        },
      }
    })
  }, [selectedAssets, allHoldings, perfData, historyResults])

  const simCurveData = useMemo(() => {
    const yearsArr = Array.from({ length: simYears + 1 }, (_, i) => i)
    return yearsArr.map((y: number) => {
      const row: any = { year: `Year ${y}`, rawYear: y }
      allMatrix.forEach((m: any) => {
        const retStr = m.data['3Y Ret'] !== '—' ? m.data['3Y Ret'] : (m.data['1Y Ret'] !== '—' ? m.data['1Y Ret'] : '12%')
        const rateNum = parseFloat(retStr.replace(/[^0-9.-]/g, '')) || 12.0
        const r = rateNum / 100.0
        
        let fv = lumpsumAmount * Math.pow(1 + r, y)
        if (r > 0 && y > 0) {
          const annualSip = sipAmount * 12
          fv += annualSip * ((Math.pow(1 + r, y) - 1) / r) * (1 + r)
        }
        row[m.id] = Math.round(fv)
      })
      return row
    })
  }, [allMatrix, sipAmount, lumpsumAmount, simYears])



  const trailingChartData = useMemo(() => {
    const horizons = ['1M', '3M', '6M', '1Y', '3Y', '5Y']
    return horizons.map((h: string) => {
      const row: any = { horizon: h }
      allMatrix.forEach((m: any) => {
        row[m.id] = m.trailing[h] ?? null
      })
      return row
    })
  }, [allMatrix])

  const rollingChartData = useMemo(() => {
    const dateSet = new Set<string>()
    const maps: Record<string, Map<string, number>> = {}

    selectedAssets.forEach((asset: any, idx: number) => {
      const res = rollingResults[idx]?.data
      if (res && res.fund_series?.length) {
        const m = new Map<string, number>()
        res.fund_series.forEach((pt: any) => {
          dateSet.add(pt.date)
          m.set(pt.date, pt.value)
        })
        maps[asset.id] = m
      } else if (res && res.bench_series?.length && asset.type === 'bench') {
        const m = new Map<string, number>()
        res.bench_series.forEach((pt: any) => {
          dateSet.add(pt.date)
          m.set(pt.date, pt.value)
        })
        maps[asset.id] = m
      }
    })

    const sortedDates = Array.from(dateSet).sort()
    return sortedDates.map((date: string) => {
      const row: any = { date }
      selectedAssets.forEach((asset: any) => {
        if (maps[asset.id] && maps[asset.id].has(date)) {
          row[asset.id] = maps[asset.id].get(date)
        }
      })
      return row
    })
  }, [selectedAssets, rollingResults])

  const trendData = useMemo(() => {
    if (activeTrend === 'Trailing' || activeTrend === 'Rolling') return []

    const dateSet = new Set<string>()
    allMatrix.forEach((m: any) => m.chartDates?.forEach((d: string) => dateSet.add(d)))
    const sortedDates = Array.from(dateSet).sort()
    if (!sortedDates.length) return []

    const assetMaps = allMatrix.map((m: any) => {
      const valMap = new Map<string, number>()
      const ddMap = new Map<string, number>()
      m.chartDates?.forEach((d: string, idx: number) => {
        if (m.chartValues[idx] != null) valMap.set(d, m.chartValues[idx])
        if (m.drawdownValues[idx] != null) ddMap.set(d, m.drawdownValues[idx])
      })
      const firstVal = m.chartValues?.find((v: number) => v != null && v > 0) || 1
      return { id: m.id, map: valMap, ddMap, firstVal }
    })

    return sortedDates.map((date: string) => {
      const row: any = { date }
      assetMaps.forEach((adm: any) => {
        if (activeTrend === 'Wealth') {
          const val = adm.map.get(date)
          if (val != null) row[adm.id] = (val / adm.firstVal) * 10000
        } else if (activeTrend === 'Drawdown') {
          const dd = adm.ddMap.get(date)
          if (dd != null) row[adm.id] = dd
        }
      })
      return row
    })
  }, [allMatrix, activeTrend])

  // Top Metrics for Hero Cards
  const heroMetrics = useMemo(() => {
    if (allMatrix.length < 1) return null
    return {
      topAlpha: allMatrix.reduce((prev, curr) => (prev.data.AlphaVal > curr.data.AlphaVal) ? prev : curr),
      topSharpe: allMatrix.reduce((prev, curr) => (prev.data.SharpeVal > curr.data.SharpeVal) ? prev : curr),
      bestConsist: allMatrix.reduce((prev, curr) => (prev.data.ConsistVal > curr.data.ConsistVal) ? prev : curr),
      lowestVol: allMatrix.reduce((prev, curr) => (prev.data.VolVal < curr.data.VolVal) ? prev : curr),
    }
  }, [allMatrix])

  if (perfE && (perfErr as any)?.response?.status === 404) {
    return (
      <Box sx={{ py: 12, textAlign: 'center' }}>
        <WarningAmberIcon sx={{ fontSize: 60, color: 'error.main', mb: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>Session Expired</Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', mb: 4 }}>Please re-upload your CAS file to continue analysis.</Typography>
        <Button variant="contained" onClick={() => window.location.href = '/'}>Go to Upload</Button>
      </Box>
    )
  }

  if (perfE) {
    return (
      <Box sx={{ py: 12, textAlign: 'center' }}>
        <WarningAmberIcon sx={{ fontSize: 60, color: 'warning.main', mb: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>Data Pipeline Interrupted</Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', mb: 4 }}>The institutional performance engine encountered a processing delay. Please try refreshing.</Typography>
        <Button variant="contained" onClick={() => queryClient.invalidateQueries({ queryKey: ['performance'] })}>Retry Analytics</Button>
      </Box>
    )
  }

  return (
    <Box>
      <SectionHeader 
        title="Compare Funds" 
        subtitle="Compare funds side-by-side on performance, risk, and asset allocation."
      />

      <motion.div initial="hidden" animate="visible" variants={itemVar}>
        <Paper className="glass" sx={{ p: 4, mb: 4 }}>
          <Grid container spacing={4}>
            <Grid item xs={12} md={6}>
              <Typography variant="overline" sx={{ fontWeight: 800, color: 'primary.main', mb: 2, display: 'block', letterSpacing: '0.1em' }}>
                PORTFOLIO ASSETS
              </Typography>
              <Autocomplete
                multiple
                options={fundNames}
                value={selectedFunds}
                onChange={(_, newVal) => setSelectedFunds(newVal)}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => {
                    const { key, ...tagProps } = getTagProps({ index })
                    return (
                      <Chip key={key} variant="outlined" label={option} {...tagProps} 
                        sx={{ borderRadius: '10px', borderColor: 'rgba(255,255,255,0.2)', color: '#fff', fontWeight: 600, fontSize: 11 }} />
                    )
                  })
                }
                renderInput={(params) => <TextField {...params} label="Select Portfolio Assets" placeholder="Add funds to comparison" />}
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.03)' } }}
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <Typography variant="overline" sx={{ fontWeight: 800, color: 'primary.main', mb: 2, display: 'block', letterSpacing: '0.1em' }}>
                MARKET COMPARATOR & PEERS
              </Typography>
              <Autocomplete
                options={searchRes?.results || []}
                getOptionLabel={(o: any) => `${o.symbol} - ${o.name}`}
                value={extTicker}
                onChange={(_, newVal) => setExtTicker(newVal)}
                onInputChange={(_, val) => setExtSearch(val)}
                noOptionsText={extSearch.length < 3 ? 'Type at least 3 chars (e.g., RELIANCE, NIFTY)' : 'No matching peers'}
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.03)' } }}
                renderInput={(params) => <TextField {...params} label="Search Market Index or Peer Fund" placeholder="e.g., Nifty 50, S&P 500, Parag Parikh Flexi" />}
              />
            </Grid>
          </Grid>
        </Paper>
      </motion.div>

      {holdL || ((perfL || historiesFetching) && selectedAssets.length > 0) ? (
        <Stack spacing={3}>
          <Grid container spacing={2}>
            {[1, 2, 3, 4].map(n => (
              <Grid item xs={12} sm={6} md={3} key={n}>
                <Skeleton variant="rounded" height={130} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} />
              </Grid>
            ))}
          </Grid>
          <Skeleton variant="rounded" height={400} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} />
        </Stack>
      ) : allMatrix.length > 0 ? (
        <motion.div initial="hidden" animate="visible" variants={containerVar}>
          <Grid container spacing={2} sx={{ mb: 4 }}>
            {heroMetrics && [
              { label: 'Alpha Leader', value: heroMetrics.topAlpha.data.Alpha, sub: heroMetrics.topAlpha.shortName, accent: 'success', info: "Jensen's Alpha measures excess return generated by the manager above expected risk-adjusted market return." },
              { label: 'Risk-Adj Best', value: heroMetrics.topSharpe.data.Sharpe, sub: heroMetrics.topSharpe.shortName, accent: 'info', info: "Sharpe Ratio measures the excess return earned per unit of total portfolio volatility." },
              { label: 'Max Consistency', value: heroMetrics.bestConsist.data.Consistency, sub: heroMetrics.bestConsist.shortName, accent: 'warn', info: "Consistency Score measures the percentage of 3-year rolling windows where the fund outperformed its benchmark." },
              { label: 'Lowest Volatility', value: heroMetrics.lowestVol.data.Volatility, sub: heroMetrics.lowestVol.shortName, accent: 'none', info: "Annualized standard deviation of daily returns. Lower volatility indicates smoother price stability." },
            ].map((m, i) => (
              <Grid item xs={12} sm={6} md={3} key={i}>
                <MetricCard {...m as any} loading={holdL || holdF || perfL || perfF} />
              </Grid>
            ))}
          </Grid>

          <Box sx={{ mb: 4, display: 'flex', justifyContent: 'center' }}>
            <Tabs value={mode} onChange={(_, v) => setMode(v)}
              sx={{ bgcolor: 'rgba(19, 27, 46, 0.6)', backdropFilter: 'blur(20px)', borderRadius: '16px', p: '4px' }}>
              <Tab value="Overview" label="Matrix Overview" icon={<AssessmentIcon />} iconPosition="start" />
              <Tab value="Technical" label="Deep Technicals" icon={<CompareArrowsIcon />} iconPosition="start" />
              <Tab value="Trends" label="Trend Analysis" icon={<ShowChartIcon />} iconPosition="start" />
            </Tabs>
          </Box>

          <AnimatePresence mode="wait">
            <motion.div key={mode} variants={containerVar} initial="hidden" animate="visible" exit="hidden">
              {mode === 'Overview' && (
                <Grid container spacing={3}>
                  <Grid item xs={12} lg={8}>
                    <motion.div variants={itemVar}>
                      <GlassTableContainer>
                        <GlassHeader label="Comparison Matrix" icon={VerifiedUserIcon} />
                        <Table size="medium">
                          <TableHead>
                            <TableRow>
                              <TableCell sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>ASSET NAME</TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>1Y RET <InfoTooltip text="Trailing 1-year CAGR from NAV data." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>3Y RET <InfoTooltip text="Trailing 3-year CAGR (annualized)." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>ALPHA <InfoTooltip text="Jensen's Alpha: Excess return over the benchmark for the risk taken." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>SHARPE <InfoTooltip text="Excess return per unit of total volatility. Higher is better." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>SORTINO <InfoTooltip text="Excess return per unit of downside volatility. Better risk measure than Sharpe." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>VERDICT <InfoTooltip text="Multi-factor institutional quality score." /></TableCell>
                            </TableRow>
                          </TableHead>
                          <TableBody>
                            {allMatrix.map((m: any) => (
                              <TableRow key={m.id} sx={{ 
                                '&:hover': { background: alpha(m.color, 0.05), borderLeftColor: m.color },
                                transition: 'background 0.2s ease', borderLeft: `4px solid transparent`,
                              }}>
                                <TableCell sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}>
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                                    <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: m.color, boxShadow: `0 0 8px ${m.color}` }} />
                                    <Typography variant="body2" fontWeight={700} sx={{ maxWidth: 200, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.fullName}</Typography>
                                  </Box>
                                </TableCell>
                                <TableCell align="center" className="num" sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontWeight: 700 }}>{m.data['1Y Ret']}</TableCell>
                                <TableCell align="center" className="num" sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontWeight: 700 }}>{m.data['3Y Ret']}</TableCell>
                                <TableCell align="center" className="num" sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontWeight: 700, color: gainColor(m.data.AlphaVal) }}>{m.data.Alpha}</TableCell>
                                <TableCell align="center" className="num" sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontWeight: 700 }}>{m.data.Sharpe}</TableCell>
                                <TableCell align="center" className="num" sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)', fontWeight: 700 }}>{m.data.Sortino}</TableCell>
                                <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.02)' }}><VerdictChip verdict={m.data.Verdict} /></TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </GlassTableContainer>
                    </motion.div>
                  </Grid>
                  <Grid item xs={12} lg={4}>
                    <motion.div variants={itemVar}>
                      <Paper className="glass" sx={{ p: 3, height: '100%', minHeight: 400 }}>
                        <GlassHeader label="Risk-Return Radar" icon={AutoAwesomeIcon} />
                        <ResponsiveContainer width="100%" height={320}>
                          <RadarChart data={[
                            { metric: 'Alpha', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, Math.min(100, (m.data.AlphaVal + 10) * 5))])) },
                            { metric: 'Sharpe', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, Math.min(100, m.data.SharpeVal * 40))])) },
                            { metric: 'Sortino', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, Math.min(100, (m.data.SortinoVal ?? 0) * 30))])) },
                            { metric: 'Consistency', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, m.data.ConsistVal * 10])) },
                            { metric: 'Stability', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, 100 - m.data.VolVal * 3)])) },
                          ]}>
                            <PolarGrid stroke="rgba(255,255,255,0.1)" />
                            <PolarAngleAxis dataKey="metric" tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 700 }} />
                            {allMatrix.map((m: any) => (
                              <Radar key={m.id} name={m.shortName} dataKey={m.id} stroke={m.color} fill={m.color} fillOpacity={0.15} strokeWidth={2} />
                            ))}
                            <Legend />
                          </RadarChart>
                        </ResponsiveContainer>
                      </Paper>
                    </motion.div>
                  </Grid>
                </Grid>
              )}

              {mode === 'Technical' && (
                <Grid container spacing={2}>
                  {allMatrix.map((m: any, idx: number) => (
                    <Grid item xs={12} md={6} lg={3} key={idx}>
                      <motion.div variants={itemVar}>
                        <Paper className="glass" sx={{ p: 3, borderTop: `4px solid ${m.color}` }}>
                          <Typography variant="h6" sx={{ mb: 2, color: m.color }}>{m.shortName}</Typography>
                          <Stack spacing={2}>
                            {[
                              { label: 'Jensen\'s Alpha', val: m.data.Alpha, color: gainColor(m.data.AlphaVal), info: "Risk-adjusted excess return earned above the benchmark index." },
                              { label: 'Sharpe Ratio', val: m.data.Sharpe, info: "Total excess return earned per unit of overall volatility." },
                              { label: 'Sortino Ratio', val: m.data.Sortino, info: "Downside risk-adjusted return. Penalizes only negative volatility unlike Sharpe." },
                              { label: 'Beta (Market)', val: m.data.Beta, info: "Sensitivity to market movements. Beta = 1 means moves exactly with the market." },
                              { label: 'Volatility', val: m.data.Volatility, info: "Annualized standard deviation of daily returns. Higher = more price swings." },
                              { label: 'Max Drawdown', val: m.data['Max Drawdown'], info: "Largest peak-to-trough decline. Measures worst-case loss scenario." },
                              { label: 'Expense Ratio', val: m.data['Expense Ratio'], info: "Total annual fund management fee charged as % of AUM." },
                              { label: 'P/E Ratio', val: m.data['P/E Ratio'], info: "Price-to-Earnings valuation multiple of underlying portfolio holdings." },
                              { label: 'P/B Ratio', val: m.data['P/B Ratio'], info: "Price-to-Book valuation multiple of underlying portfolio holdings." },
                              { label: 'Consistency', val: m.data.Consistency, info: "% of 3-year rolling windows where fund beat its benchmark. 10/10 = always outperformed." },
                            ].map((stat, i) => (
                              <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>{stat.label}</Typography>
                                  <InfoTooltip text={stat.info} />
                                </Box>
                                <Typography className="num" sx={{ fontSize: 13, fontWeight: 700, color: (stat as any).color ?? '#fff' }}>{stat.val}</Typography>
                              </Box>
                            ))}
                          </Stack>
                        </Paper>
                      </motion.div>
                    </Grid>
                  ))}
                </Grid>
              )}

              {mode === 'Trends' && (
                <Paper className="glass" sx={{ p: 4, position: 'relative', minHeight: 450 }}>
                  {(historyResults.some((r: any) => r.isLoading) || rollingResults.some((r: any) => r.isLoading)) && (
                    <OverlayLoader message="Analyzing trend multi-vectors..." />
                  )}
                  <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                    <ToggleButtonGroup size="small" value={activeTrend} exclusive onChange={(_, v) => v && setActiveTrend(v)}>
                      <ToggleButton value="Trailing" sx={{ px: 3, py: 1, fontWeight: 700 }}>Trailing Returns (1M - 5Y)</ToggleButton>
                      {/* <ToggleButton value="Rolling" sx={{ px: 3, py: 1, fontWeight: 700 }}>3Y Rolling Return (Consistency)</ToggleButton> */}
                      <ToggleButton value="Wealth" sx={{ px: 3, py: 1, fontWeight: 700 }}>Wealth Growth (₹10k)</ToggleButton>
                      <ToggleButton value="Drawdown" sx={{ px: 3, py: 1, fontWeight: 700 }}>Risk Stress Test (Drawdown)</ToggleButton>
                    </ToggleButtonGroup>
                    <Typography variant="caption" sx={{ opacity: 0.5 }}>
                      {activeTrend === 'Trailing' ? 'Point-to-point trailing snapshot across horizons' : 
                       activeTrend === 'Rolling' ? '3-Year rolling return consistency curve over time' : 
                       activeTrend === 'Wealth' ? 'Historical compounding of ₹10,000 baseline' : 
                       'Historical peak-to-trough drawdown risk profile'}
                    </Typography>
                  </Box>

                  <ResponsiveContainer width="100%" height={400}>
                    {activeTrend === 'Trailing' ? (
                      <BarChart data={trailingChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                        <XAxis dataKey="horizon" tick={{ fill: '#94A3B8', fontSize: 12, fontWeight: 700 }} />
                        <YAxis tick={{ fill: '#94A3B8', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                        <Tooltip content={<ChartTooltip isPct />} />
                        <Legend verticalAlign="top" height={36} />
                        {allMatrix.map((m: any) => (
                          <Bar key={m.id} dataKey={m.id} name={m.shortName} fill={m.color} radius={[6, 6, 0, 0]} />
                        ))}
                      </BarChart>
                    ) : activeTrend === 'Rolling' ? (
                      <LineChart data={rollingChartData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                        <XAxis dataKey="date" hide />
                        <YAxis tick={{ fill: '#94A3B8', fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                        <Tooltip content={<ChartTooltip isPct />} />
                        <Legend verticalAlign="top" height={36} />
                        {allMatrix.map((m: any) => (
                          <Line key={m.id} name={m.shortName} type="monotone" dataKey={m.id} stroke={m.color} strokeWidth={3} dot={false} connectNulls />
                        ))}
                      </LineChart>
                    ) : (
                      <LineChart data={trendData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                        <XAxis dataKey="date" hide />
                        <YAxis tick={{ fill: '#94A3B8', fontSize: 11 }} tickFormatter={(v) => activeTrend === 'Wealth' ? `₹${(v/1000).toFixed(0)}k` : `${v}%`} />
                        <Tooltip content={<ChartTooltip isPct={activeTrend === 'Drawdown'} />} />
                        <Legend verticalAlign="top" height={36} />
                        {allMatrix.map((m: any) => (
                          <Line key={m.id} name={m.shortName} type="monotone" dataKey={m.id} stroke={m.color} strokeWidth={3} dot={false} connectNulls />
                        ))}
                      </LineChart>
                    )}
                  </ResponsiveContainer>
                </Paper>
              )}
            </motion.div>
          </AnimatePresence>

          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}>
            <Box sx={{ mt: 6, p: 4, borderRadius: '24px', background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(78, 222, 147, 0.1) 100%)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <Grid container spacing={4} alignItems="center">
                <Grid item xs={12} md={8}>
                  <Typography variant="h5" sx={{ mb: 1, fontWeight: 900 }}>Simulate Future Growth</Typography>
                  <Typography variant="body2" sx={{ opacity: 0.7 }}>Select assets or an external benchmark to unlock the SIP & Lumpsum compounding projection sandbox.</Typography>
                </Grid>
                <Grid item xs={12} md={4} sx={{ textAlign: 'right' }}>
                  <Button variant="contained" size="large" onClick={() => setShowSim(true)} startIcon={<TrendingUpIcon />}>
                    Launch Projection Sandbox
                  </Button>
                </Grid>
              </Grid>
            </Box>
          </motion.div>

          <Modal open={showSim} onClose={() => setShowSim(false)} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 3 }}>
            <Paper className="glass" sx={{ p: 5, width: '100%', maxWidth: 1000, maxHeight: '90vh', overflowY: 'auto', borderRadius: '32px', position: 'relative', border: '1px solid rgba(255,255,255,0.1)', outline: 'none' }}>
              <IconButton onClick={() => setShowSim(false)} sx={{ position: 'absolute', top: 24, right: 24, color: 'text.secondary' }}>
                <CloseIcon />
              </IconButton>
              <Typography variant="h4" sx={{ fontWeight: 900, mb: 1, color: 'primary.main' }}>SIP & Lumpsum Compounding Sandbox</Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', mb: 4 }}>
                Dynamic multi-vector wealth projection compounding historical return trajectories across your selected instruments.
              </Typography>

              <Grid container spacing={4} sx={{ mb: 6 }}>
                <Grid item xs={12} md={4}>
                  <Typography variant="overline" sx={{ fontWeight: 800, color: 'text.secondary', mb: 1, display: 'block' }}>Monthly SIP Amount</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 800, mb: 2 }}>{fmtInr(sipAmount)}</Typography>
                  <Slider value={sipAmount} min={0} max={200000} step={5000} onChange={(_, v) => setSipAmount(v as number)} valueLabelDisplay="auto" />
                </Grid>
                <Grid item xs={12} md={4}>
                  <Typography variant="overline" sx={{ fontWeight: 800, color: 'text.secondary', mb: 1, display: 'block' }}>Initial Lumpsum</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 800, mb: 2 }}>{fmtInr(lumpsumAmount)}</Typography>
                  <Slider value={lumpsumAmount} min={0} max={5000000} step={50000} onChange={(_, v) => setLumpsumAmount(v as number)} valueLabelDisplay="auto" />
                </Grid>
                <Grid item xs={12} md={4}>
                  <Typography variant="overline" sx={{ fontWeight: 800, color: 'text.secondary', mb: 1, display: 'block' }}>Investment Horizon</Typography>
                  <Typography variant="h5" sx={{ fontWeight: 800, mb: 2 }}>{simYears} Years</Typography>
                  <Slider value={simYears} min={5} max={30} step={1} onChange={(_, v) => setSimYears(v as number)} valueLabelDisplay="auto" />
                </Grid>
              </Grid>

              <Box sx={{ p: 3, bgcolor: 'rgba(0,0,0,0.2)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', mb: 2 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 3, color: 'text.secondary', letterSpacing: '0.1em' }}>PROJECTED WEALTH GROWTH CURVES</Typography>
                <ResponsiveContainer width="100%" height={380}>
                  <AreaChart data={simCurveData}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="year" tick={{ fill: '#94A3B8', fontSize: 11 }} />
                    <YAxis tick={{ fill: '#94A3B8', fontSize: 11 }} tickFormatter={(v) => `₹${(v/100000).toFixed(0)}L`} />
                    <Tooltip content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null
                      const totalInv = lumpsumAmount + (sipAmount * 12 * (payload[0].payload.rawYear || 0))
                      return (
                        <Paper className="glass" sx={{ p: 2, minWidth: 240, border: '1px solid rgba(255,255,255,0.1)' }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 800, mb: 1, color: 'primary.main' }}>{label}</Typography>
                          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 1 }}>
                            Total Invested: {fmtInr(totalInv)}
                          </Typography>
                          {payload.map((item: any) => (
                            <Box key={item.dataKey} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', my: 0.5 }}>
                              <Typography variant="body2" sx={{ color: item.color, fontWeight: 700 }}>{item.name}:</Typography>
                              <Typography variant="body2" sx={{ fontWeight: 800 }}>{fmtInr(Number(item.value))}</Typography>
                            </Box>
                          ))}
                        </Paper>
                      )
                    }} />
                    <Legend verticalAlign="top" height={36} />
                    {allMatrix.map((m: any) => (
                      <Area key={m.id} name={m.shortName} type="monotone" dataKey={m.id} stroke={m.color} fill={m.color} fillOpacity={0.15} strokeWidth={3} />
                    ))}
                  </AreaChart>
                </ResponsiveContainer>
              </Box>
            </Paper>
          </Modal>
        </motion.div>
      ) : (
        <Box sx={{ py: 12, textAlign: 'center' }}>
          <motion.div initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}>
            <AutoAwesomeIcon sx={{ fontSize: 80, color: 'rgba(255,255,255,0.05)', mb: 3 }} />
            <Typography variant="h4" sx={{ fontWeight: 900, mb: 1 }}>Initialize Comparison</Typography>
            <Typography variant="body1" sx={{ color: 'text.secondary' }}>Add assets from your portfolio or the global market to begin.</Typography>
          </motion.div>
        </Box>
      )}
    </Box>
  )
}
