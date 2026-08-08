import { fmtInr } from '../../../shared/utils/fmt'
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
import { useHoldings, usePerformance } from '../hooks/useData'
import { useDebounce } from '../../../shared/hooks/useDebounce'
import { useSessionId, useAppStore } from '../../../shared/store/appStore'
import { apiClient } from '../../../shared/api/client'
import { SectionHeader, VerdictChip, MetricCard, GlassTableContainer, GlassHeader, OverlayLoader, InfoTooltip } from '../../../shared/components/ui'
import { ChartTooltip } from '../../../shared/components/charts/ChartTooltip'
import { gainColor } from '../../../shared/utils/fmt'

import { COLORS, calculateDrawdown } from '../rules/tabCommon'

type PeerRef = { symbol: string; name: string; type?: string }

function parseComparePeers(raw: string | undefined): PeerRef[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      return parsed.filter((p) => p && p.symbol && p.name)
    }
    if (parsed && typeof parsed === 'object' && parsed.symbol) {
      return [{ symbol: String(parsed.symbol), name: String(parsed.name || parsed.symbol), type: parsed.type }]
    }
  } catch {
    // Legacy plain-string bench (e.g. "Nifty 50")
    return [{ symbol: raw, name: raw, type: 'Index' }]
  }
  return []
}

function isSchemeCode(symbol: string) {
  return /^\d{5,}$/.test(String(symbol || '').trim())
}

// ── Motion Variants ──────────────────────────────────────────────────────────
const containerVar = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
}

const itemVar = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { type: 'spring', damping: 25, stiffness: 300 } }
}

// ── Main Component ───────────────────────────────────────────────────────────
export default function CompareTab() {
  const sid = useSessionId() || 'default'
  
  const compareFundsState = useAppStore(s => s.compareFunds)
  const setCompareFunds = useAppStore(s => s.setCompareFunds)
  const compareBenchState = useAppStore(s => s.compareBench)
  const setCompareBench = useAppStore(s => s.setCompareBench)

  const selectedFunds = compareFundsState[sid] || []
  const setSelectedFunds = (funds: string[]) => setCompareFunds(sid, funds)

  const [extSearch, setExtSearch] = useState('')
  const extPeersRaw = compareBenchState[sid]
  const extPeers = useMemo(() => parseComparePeers(extPeersRaw), [extPeersRaw])
  const setExtPeers = (peers: PeerRef[]) => {
    setCompareBench(sid, peers.length ? JSON.stringify(peers) : '')
  }

  // Migrate legacy single-object / plain-string bench into a peer array once.
  useEffect(() => {
    if (!extPeersRaw) return
    const trimmed = extPeersRaw.trim()
    if (trimmed.startsWith('[')) return
    const migrated = parseComparePeers(extPeersRaw)
    if (migrated.length) setCompareBench(sid, JSON.stringify(migrated))
  }, [extPeersRaw, sid, setCompareBench])

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

  // One /compare/search per keystroke before this, all queued behind one worker.
  const debouncedExtSearch = useDebounce(extSearch, 300)

  const { data: searchRes, isFetching: searchingPeers } = useQuery({
    queryKey: ['tickerSearch', debouncedExtSearch],
    queryFn: () => apiClient.searchTicker(debouncedExtSearch),
    enabled: debouncedExtSearch.length >= 3,
    gcTime: 60 * 1000,
  })
  const selectedPeerSymbols = new Set(extPeers.map((p) => p.symbol))
  const peerOptions = (searchRes?.results || []).filter((o: any) => !selectedPeerSymbols.has(o.symbol))

  // Index (non scheme-code) used as the portfolio performance benchmark; default Nifty 50.
  const marketBenchmark = extPeers.find((p) => !isSchemeCode(p.symbol))?.symbol
    || extPeers.find((p) => !isSchemeCode(p.symbol))?.name
    || 'Nifty 50'

  // 1. Identify all assets for historical fetching
  const selectedAssets = useMemo(() => {
    const funds = selectedFunds.map((fname: string) => {
      const h: any = allHoldings.find((x: any) => x.Fund === fname)
      return { id: h?.ISIN || fname, name: fname, type: 'fund', short: fname.split(' ')[0] }
    })
    const peers = extPeers.map((p) => ({
      id: p.symbol,
      name: p.name,
      type: isSchemeCode(p.symbol) ? 'peer' : 'bench',
      short: (p.name || p.symbol).split(' ')[0],
    }))
    return [...funds, ...peers]
  }, [selectedFunds, extPeers, allHoldings])

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
    benchmark: marketBenchmark
  })

  const historiesFetching = historyResults.some((r: any) => r.isFetching) || rollingResults.some((r: any) => r.isFetching)

  // useQueries returns a NEW array (with new result wrapper objects) on every render,
  // so using it directly as a memo dependency meant the memo never cached — it
  // recomputed on every render, including a full calculateDrawdown pass over up to
  // 1,825 daily NAVs per selected asset. Depending on the extracted `.data`
  // references instead makes the dependency change only when data actually changes.
  //
  // A `.map(r => r.data)` still allocates a new array each render, so it is itself
  // memoized against a cheap identity signature of the underlying data.
  // The asset ids are part of the signature, not just the timestamps. Timestamps alone
  // are ambiguous: several entries are 0 while pending, and parallel fetches routinely
  // resolve within the same millisecond — so swapping one asset for another could leave
  // the signature unchanged. `histories` would then stay stale while `allMatrix`
  // recomputed against the new `selectedAssets`, and `histories[i]` would map one
  // fund's price history onto a different fund's row: wrong drawdown and return figures
  // rendered as fact.
  const assetSignature = selectedAssets.map((a: any) => a.id).join('|')
  const historySignature = assetSignature + '::' + historyResults.map((r: any) => r.dataUpdatedAt ?? 0).join('|')
  const rollingSignature = assetSignature + '::' + rollingResults.map((r: any) => r.dataUpdatedAt ?? 0).join('|')

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const histories = useMemo(() => historyResults.map((r: any) => r.data), [historySignature])
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const rollings = useMemo(() => rollingResults.map((r: any) => r.data), [rollingSignature])

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
      const hist = histories[i] ?? {}
      const isExternal = asset.type === 'bench' || asset.type === 'peer'
      const isBench = asset.type === 'bench'
      const bStats: any = (perfData as any)?.benchmark_stats
      const trailingDict: Record<string, number> = {}
      if (isExternal && hist?.returns) {
        Object.assign(trailingDict, hist.returns)
      } else if (isBench && bStats?.returns) {
        Object.assign(trailingDict, bStats.returns)
      } else if (pFund?.roll_labels && pFund?.fund_rolls) {
        pFund.roll_labels.forEach((lbl: string, idx: number) => {
          if (pFund.fund_rolls[idx] != null) trailingDict[lbl] = pFund.fund_rolls[idx]
        })
      }

      const extAlpha = hist?.alpha ?? (isBench ? (bStats?.alpha ?? 0) : null)
      const extSharpe = hist?.sharpe ?? (isBench ? bStats?.sharpe : null)
      const extSortino = hist?.sortino ?? (isBench ? bStats?.sortino : null)
      const extBeta = hist?.beta ?? (isBench ? (bStats?.beta ?? 1) : null)
      const extVol = hist?.volatility ?? (isBench ? bStats?.volatility : null)
      const extMaxDd = hist?.max_drawdown ?? (isBench ? bStats?.max_drawdown : null)
      const extConsist = hist?.consistency ?? (isBench ? 10 : null)

      return {
        name: asset.short,
        shortName: asset.short,
        fullName: asset.name,
        id: asset.id,
        isBench,
        isExternal,
        color: COLORS[i % COLORS.length],
        // Technicals
        alpha: isExternal ? (extAlpha ?? 'N/A') : (pFund?.alpha || 'N/A'),
        beta: isExternal ? (extBeta ?? 'N/A') : (pFund?.beta || 'N/A'),
        sharpe: isExternal ? (extSharpe ?? 'N/A') : (pFund?.sharpe || 'N/A'),
        sortino: isExternal ? (extSortino ?? 'N/A') : (pFund?.sortino || 'N/A'),
        volatility: isExternal ? (extVol ?? 'N/A') : (pFund?.vol || 'N/A'),
        consistency: isExternal ? (extConsist != null ? `${extConsist}` : 'N/A') : (pFund?.consistency || 'N/A'),
        risk: isBench ? 'Target' : (isExternal ? 'Peer' : (pFund?.verdict || 'Average')),
        // Performance
        return: isExternal
          ? (trailingDict['1Y'] ?? (perfData as any)?.benchmark_return ?? 0)
          : (pFund?.return_period || 0),
        trailing: trailingDict,
        history: hist,
        chartDates: hist.dates || [],
        chartValues: hist.values || [], 
        drawdownValues: calculateDrawdown(hist.values || []),
        data: {
          '1Y Ret': trailingDict['1Y'] != null ? `${trailingDict['1Y'] >= 0 ? '+' : ''}${trailingDict['1Y'].toFixed(1)}%` : (pFund ? `${pFund.fund_xi?.toFixed(1)}%` : 'N/A'),
          '3Y Ret': trailingDict['3Y'] != null ? `${trailingDict['3Y'] >= 0 ? '+' : ''}${trailingDict['3Y'].toFixed(1)}%` : 'N/A',
          'Alpha': isExternal
            ? (extAlpha != null ? `${extAlpha >= 0 ? '+' : ''}${Number(extAlpha).toFixed(1)}%` : 'N/A')
            : (pFund ? `${pFund.alpha >= 0 ? '+' : ''}${pFund.alpha.toFixed(1)}%` : 'N/A'),
          'Sharpe': isExternal
            ? (extSharpe != null ? Number(extSharpe).toFixed(2) : 'N/A')
            : (pFund?.sharpe?.toFixed(2) ?? 'N/A'),
          'Sortino': isExternal
            ? (extSortino != null ? Number(extSortino).toFixed(2) : 'N/A')
            : (pFund?.sortino?.toFixed(2) ?? 'N/A'),
          'Beta': isExternal
            ? (extBeta != null ? Number(extBeta).toFixed(2) : 'N/A')
            : (pFund?.beta?.toFixed(2) ?? 'N/A'),
          'Volatility': isExternal
            ? (extVol != null ? `${extVol}%` : 'N/A')
            : (pFund?.vol != null ? `${pFund.vol.toFixed(1)}%` : 'N/A'),
          'Max Drawdown': isExternal
            ? (extMaxDd != null ? `${Number(extMaxDd).toFixed(1)}%` : 'N/A')
            : (pFund?.max_dd != null ? `${Number(pFund.max_dd).toFixed(1)}%` : 'N/A'),
          'Expense Ratio': isExternal
            ? (hist?.ter != null ? `${Number(hist.ter).toFixed(2)}%` : 'N/A')
            : (pFund?.er != null ? `${Number(pFund.er).toFixed(2)}%` : 'N/A'),
          'Consistency': isExternal
            ? (extConsist != null ? `${Number(extConsist).toFixed(1)}/10` : 'N/A')
            : (pFund ? `${pFund.consistency?.toFixed(1)}/10` : 'N/A'),
          'Verdict': isBench ? 'Target' : (isExternal ? 'Peer' : (pFund?.verdict ?? 'Average')),
          // P/E & P/B are category-level estimates from config (not live fund holdings multiples).
          'P/E Ratio': pFund?.pe_ratio != null ? pFund.pe_ratio.toFixed(1) : (pFund?.is_debt ? 'N/A (Debt)' : 'N/A'),
          'P/B Ratio': pFund?.pb_ratio != null ? pFund.pb_ratio.toFixed(1) : (pFund?.is_debt ? 'N/A (Debt)' : 'N/A'),
          'Day Chg.%': (() => {
            if (isExternal) {
              const chg = hist?.day_chg ?? (isBench ? (perfData as any)?.benchmark_day_chg : null)
              return chg != null ? `${chg >= 0 ? '+' : ''}${Number(chg).toFixed(2)}%` : 'N/A'
            }
            return h?.['Day Chg.%'] != null
              ? `${h['Day Chg.%'] >= 0 ? '+' : ''}${h['Day Chg.%'].toFixed(2)}%`
              : 'N/A'
          })(),
          AlphaVal: isExternal ? (Number(extAlpha) || 0) : (pFund?.alpha ?? 0),
          SharpeVal: isExternal ? (Number(extSharpe) || 0) : (pFund?.sharpe ?? 0),
          SortinoVal: isExternal ? (Number(extSortino) || 0) : (pFund?.sortino ?? 0),
          VolVal: isExternal ? (Number(extVol) || 0) : (pFund?.vol ?? 100),
          ConsistVal: isExternal ? (Number(extConsist) || 0) : (pFund?.consistency ?? 0),
        },
      }
    })
  }, [selectedAssets, allHoldings, perfData, histories])

  // The three sandbox sliders call their setters continuously while dragging, and this
  // projection rebuilds a row per year per selected asset. Feeding the raw values in
  // meant every pixel of drag recomputed the projection and re-rendered an AreaChart,
  // a RadarChart and a BarChart — enough to visibly lock the tab.
  //
  // Debounced rather than switched to onChangeCommitted so the value labels above each
  // slider stay live while dragging; only the projection waits.
  const simParams = useMemo(
    () => ({ sip: sipAmount, lumpsum: lumpsumAmount, years: simYears }),
    [sipAmount, lumpsumAmount, simYears],
  )
  const simSettled = useDebounce(simParams, 200)

  const simCurveData = useMemo(() => {
    const yearsArr = Array.from({ length: simSettled.years + 1 }, (_, i) => i)
    return yearsArr.map((y: number) => {
      const row: any = { year: `Year ${y}`, rawYear: y }
      allMatrix.forEach((m: any) => {
        const retStr = m.data['3Y Ret'] !== '—' && m.data['3Y Ret'] !== 'N/A' ? m.data['3Y Ret'] : (m.data['1Y Ret'] !== '—' && m.data['1Y Ret'] !== 'N/A' ? m.data['1Y Ret'] : '12%')
        const rateNum = parseFloat(retStr.replace(/[^0-9.-]/g, '')) || 12.0
        const r = rateNum / 100.0

        let fv = simSettled.lumpsum * Math.pow(1 + r, y)
        if (r > 0 && y > 0) {
          const annualSip = simSettled.sip * 12
          fv += annualSip * ((Math.pow(1 + r, y) - 1) / r) * (1 + r)
        }
        row[m.id] = Math.round(fv)
      })
      return row
    })
  }, [allMatrix, simSettled])



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

  // Was an inline array literal in the JSX, so recharts received a new `data` prop on
  // every render and re-diffed all five axes even when nothing had changed.
  const radarData = useMemo(() => [
    { metric: 'Alpha', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, Math.min(100, (m.data.AlphaVal + 10) * 5))])) },
    { metric: 'Sharpe', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, Math.min(100, m.data.SharpeVal * 40))])) },
    { metric: 'Sortino', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, Math.min(100, (m.data.SortinoVal ?? 0) * 30))])) },
    { metric: 'Consistency', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, m.data.ConsistVal * 10])) },
    { metric: 'Stability', ...Object.fromEntries(allMatrix.map((m: any) => [m.id, Math.max(0, 100 - m.data.VolVal * 3)])) },
  ], [allMatrix])

  const rollingChartData = useMemo(() => {
    const dateSet = new Set<string>()
    const maps: Record<string, Map<string, number>> = {}

    selectedAssets.forEach((asset: any, idx: number) => {
      const res = rollings[idx]
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
  }, [selectedAssets, rollings])

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
                OTHER MUTUAL FUNDS & INDICES
              </Typography>
              <Autocomplete
                multiple
                options={peerOptions}
                value={extPeers}
                inputValue={extSearch}
                getOptionLabel={(o: any) => {
                  if (typeof o === 'string') return o
                  const kind = o.type === 'Mutual Fund' || isSchemeCode(o.symbol) ? 'Fund' : 'Index'
                  // Keep symbol in the label so scheme codes / tickers stay visible & matchable.
                  return `${o.symbol} · ${o.name} (${kind})`
                }}
                isOptionEqualToValue={(a: any, b: any) => a?.symbol === b?.symbol}
                filterOptions={(x) => x}
                clearOnBlur={false}
                loading={searchingPeers}
                onChange={(_, newVal) => {
                  setExtPeers(newVal.map((p: any) => ({
                    symbol: p.symbol,
                    name: p.name,
                    type: p.type,
                  })))
                  setExtSearch('')
                }}
                onInputChange={(_, val, reason) => {
                  if (reason === 'input') setExtSearch(val)
                  else if (reason === 'clear') setExtSearch('')
                }}
                noOptionsText={extSearch.length < 3 ? 'Type at least 3 chars (e.g., Parag, Quant, Nifty)' : (searchingPeers ? 'Searching…' : 'No matching mutual funds')}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => {
                    const { key, ...tagProps } = getTagProps({ index })
                    const kind = option.type === 'Mutual Fund' || isSchemeCode(option.symbol) ? 'Fund' : 'Index'
                    return (
                      <Chip
                        key={key}
                        variant="outlined"
                        label={`${option.name.split(' ').slice(0, 4).join(' ')} · ${kind}`}
                        {...tagProps}
                        sx={{ borderRadius: '10px', borderColor: 'rgba(255,255,255,0.2)', color: '#fff', fontWeight: 600, fontSize: 11 }}
                      />
                    )
                  })
                }
                sx={{ '& .MuiOutlinedInput-root': { borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.03)' } }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Search other mutual funds or indices"
                    placeholder="e.g., Parag Parikh Flexi, Mirae Midcap, Nifty 50"
                    InputProps={{
                      ...params.InputProps,
                      endAdornment: (
                        <>
                          {searchingPeers ? <CircularProgress color="inherit" size={16} /> : null}
                          {params.InputProps.endAdornment}
                        </>
                      ),
                    }}
                  />
                )}
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
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>1Y RET <InfoTooltip title="Trailing 1-year CAGR from NAV data." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>3Y RET <InfoTooltip title="Trailing 3-year CAGR (annualized)." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>ALPHA <InfoTooltip title="Jensen's Alpha: Excess return over the benchmark for the risk taken." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>SHARPE <InfoTooltip title="Excess return per unit of total volatility. Higher is better." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>SORTINO <InfoTooltip title="Excess return per unit of downside volatility. Better risk measure than Sharpe." /></TableCell>
                              <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.05)', fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>VERDICT <InfoTooltip title="Multi-factor institutional quality score." /></TableCell>
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
                          <RadarChart data={radarData}>
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
                              { label: 'P/E Ratio', val: m.data['P/E Ratio'], info: "Category-level P/E estimate (not a live holdings-weighted multiple)." },
                              { label: 'P/B Ratio', val: m.data['P/B Ratio'], info: "Category-level P/B estimate (not a live holdings-weighted multiple)." },
                              { label: 'Consistency', val: m.data.Consistency, info: "% of 3-year rolling windows where fund beat its benchmark. 10/10 = always outperformed." },
                            ].map((stat, i) => (
                              <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                                  <Typography variant="caption" sx={{ color: 'text.secondary' }}>{stat.label}</Typography>
                                  <InfoTooltip title={stat.info} />
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
