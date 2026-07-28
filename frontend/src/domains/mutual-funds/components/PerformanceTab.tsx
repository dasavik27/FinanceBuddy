import { useState, useEffect, useMemo } from 'react'
import {
  Box, Grid, Paper, Typography, Chip, Stack,
  Table, TableHead, TableRow, TableCell, TableBody, Skeleton,
  Button, IconButton, alpha, Select, MenuItem, FormControl
} from '@mui/material'
import { motion, AnimatePresence } from 'framer-motion'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import SortIcon from '@mui/icons-material/Sort'
import FilterAltOutlinedIcon from '@mui/icons-material/FilterAltOutlined'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import SpeedIcon from '@mui/icons-material/Speed'
import TimelineIcon from '@mui/icons-material/Timeline'

import { useQueryClient } from '@tanstack/react-query'
import { usePerformance } from '../../hooks/useData'
import { useSessionId } from '../../store/appStore'
import { apiClient } from '../../api/client'
import { 
  VerdictChip, CategoryBadge,
  PeriodSelector, SectionHeader, MetricCard,
  GlassTableContainer, GlassHeader, InfoTooltip
} from '../ui'
import { fmtInr, fmtPct } from '../../api/fmt'

import { CATEGORY_INSIGHTS } from '../../rules/tabCommon'

// ── Peer Comparison Component (Zerodha Coin style) ──────────────────────────
function FundPeers({ fund }: { fund: any }) {
  const [peers, setPeers] = useState<any[]>([])
  const [fallbackTriggered, setFallbackTriggered] = useState(false)
  const [loading, setLoading] = useState(false)
  const [sortBy, setSortBy] = useState<'ret1y' | 'ret3y' | 'ret5y' | 'sharpe'>('ret1y')

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      try {
        const cat = fund?.cap_type || fund?.category || "Large Cap"
        const res = await apiClient.getCategoryPeers(cat)
        if (active && res && res.peers) {
          setPeers(res.peers)
          setFallbackTriggered(res.fallback_triggered || false)
        }
      } catch (e) { console.error(e) } 
      finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [fund?.cap_type, fund?.category])

  const sortedPeers = useMemo(() => {
    const arr = [...peers]
    arr.sort((a, b) => {
      if (sortBy === 'sharpe') return (Number(b.sharpe) || 0) - (Number(a.sharpe) || 0)
      return (Number(b[sortBy]) || 0) - (Number(a[sortBy]) || 0)
    })
    return arr
  }, [peers, sortBy])

  if (loading) {
    return (
      <Box sx={{ mt: 4, pt: 4, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        <Typography variant="overline" sx={{ fontWeight: 800, color: 'primary.main', mb: 2, display: 'block', letterSpacing: '0.15em' }}>
          CATEGORY PEERS
        </Typography>
        <Grid container spacing={2}>
          {[1, 2, 3].map((n) => (
            <Grid item xs={12} md={4} key={n}>
              <Skeleton variant="rounded" height={150} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '16px' }} />
            </Grid>
          ))}
        </Grid>
      </Box>
    )
  }

  if (!peers.length) return null

  // Build the your-fund row from current fund data
  const yourFundRow = {
    name: fund?.fund || 'Your Fund',
    ret1y: fund?.fund_rolls?.[3] ?? null, // 1Y from roll_labels
    ret3y: fund?.fund_rolls?.[4] ?? null, // 3Y
    ret5y: fund?.fund_rolls?.[5] ?? null, // 5Y
    sharpe: fund?.sharpe,
    expense: fund?.er,
    consistency: `${fund?.consistency ?? 0}/10`,
    isYourFund: true,
  }

  // Determine rank among peers for the active sort column
  const allReturns = sortedPeers.map(p => Number(p[sortBy]) || 0)
  const yourVal = Number(yourFundRow[sortBy as keyof typeof yourFundRow]) || 0
  const rank = allReturns.filter(v => v > yourVal).length + 1
  const total = allReturns.length + 1

  const fmtRet = (v: any) => {
    if (v == null) return '—'
    const n = Number(v)
    return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
  }

  return (
    <Box sx={{ mt: 4, pt: 4, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <CompareArrowsIcon sx={{ color: 'primary.main', fontSize: 20 }} />
          <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>
            CATEGORY PEERS — {fund?.cap_type || fund?.category || 'Equity'}
          </Typography>
          <Chip label={`Rank ${rank} of ${total}`} size="small" sx={{
            bgcolor: rank <= 2 ? 'rgba(78, 222, 147, 0.15)' : rank <= total * 0.5 ? 'rgba(234, 179, 8, 0.15)' : 'rgba(255, 81, 106, 0.15)',
            color: rank <= 2 ? '#4EDE93' : rank <= total * 0.5 ? '#EAB308' : '#FF516A',
            fontWeight: 800, fontSize: 11, border: '1px solid',
            borderColor: rank <= 2 ? 'rgba(78, 222, 147, 0.3)' : rank <= total * 0.5 ? 'rgba(234, 179, 8, 0.3)' : 'rgba(255, 81, 106, 0.3)',
          }} />
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, bgcolor: 'rgba(0,0,0,0.3)', p: 0.5, borderRadius: '100px', border: '1px solid rgba(255,255,255,0.1)' }}>
          <Typography variant="caption" sx={{ px: 1, color: 'text.secondary', fontWeight: 700 }}>SORT:</Typography>
          {(['ret1y', 'ret3y', 'ret5y', 'sharpe'] as const).map((key) => (
            <Button
              key={key}
              size="small"
              onClick={() => setSortBy(key)}
              sx={{
                minWidth: 'auto', px: 1.5, py: 0.5, borderRadius: '100px',
                fontSize: 11, fontWeight: 800,
                color: sortBy === key ? '#000' : 'text.secondary',
                bgcolor: sortBy === key ? 'primary.main' : 'transparent',
                '&:hover': { bgcolor: sortBy === key ? 'primary.main' : 'rgba(255,255,255,0.05)' }
              }}
            >
              {key === 'ret1y' ? '1Y' : key === 'ret3y' ? '3Y' : key === 'ret5y' ? '5Y' : 'SHARPE'}
            </Button>
          ))}
        </Box>
      </Box>

      {fallbackTriggered && (
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, p: 2, mb: 3, bgcolor: 'rgba(234, 179, 8, 0.05)', borderRadius: '12px', border: '1px solid rgba(234, 179, 8, 0.2)' }}>
          <WarningAmberIcon sx={{ color: '#EAB308', fontSize: 20, mt: 0.25 }} />
          <Box>
            <Typography variant="caption" sx={{ display: 'block', color: '#EAB308', fontWeight: 800, mb: 0.5 }}>CATEGORY DEGRADATION ACTIVE</Typography>
            <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1.5 }}>
              We couldn't find enough active peers matching the niche category <b>"{fund?.cap_type || fund?.category}"</b>. To ensure your performance dashboard remains functional, we have temporarily fallen back to comparing against standard <b>Large Cap</b> industry benchmarks.
            </Typography>
          </Box>
        </Box>
      )}

      {/* Peer Table */}
      <Paper sx={{ borderRadius: '16px', overflow: 'hidden', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 800, fontSize: 10, color: 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>#</TableCell>
              <TableCell sx={{ fontWeight: 800, fontSize: 10, color: 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>FUND NAME</TableCell>
              <TableCell align="center" sx={{ fontWeight: 800, fontSize: 10, color: sortBy === 'ret1y' ? 'primary.main' : 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>1Y RET</TableCell>
              <TableCell align="center" sx={{ fontWeight: 800, fontSize: 10, color: sortBy === 'ret3y' ? 'primary.main' : 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>3Y RET</TableCell>
              <TableCell align="center" sx={{ fontWeight: 800, fontSize: 10, color: sortBy === 'ret5y' ? 'primary.main' : 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>5Y RET</TableCell>
              <TableCell align="center" sx={{ fontWeight: 800, fontSize: 10, color: sortBy === 'sharpe' ? 'primary.main' : 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>SHARPE</TableCell>
              <TableCell align="center" sx={{ fontWeight: 800, fontSize: 10, color: 'text.secondary', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>TER</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {/* Your Fund Row — Highlighted */}
            <TableRow sx={{ bgcolor: 'rgba(99, 102, 241, 0.08)', '& td': { borderBottom: '2px solid rgba(99, 102, 241, 0.25)' } }}>
              <TableCell sx={{ fontWeight: 900, color: 'primary.main', fontSize: 12 }}>{rank}</TableCell>
              <TableCell>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: 'primary.main', boxShadow: '0 0 8px #6366F1' }} />
                  <Typography variant="caption" sx={{ fontWeight: 800, color: '#fff', fontSize: 12 }}>
                    {String(fund?.fund || '').slice(0, 35)}{String(fund?.fund || '').length > 35 ? '...' : ''}
                  </Typography>
                  <Chip label="YOU" size="small" sx={{ height: 18, fontSize: 9, fontWeight: 900, bgcolor: 'primary.main', color: '#fff', ml: 0.5 }} />
                </Box>
              </TableCell>
              <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 12, color: (yourFundRow.ret1y ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>{fmtRet(yourFundRow.ret1y)}</TableCell>
              <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 12, color: (yourFundRow.ret3y ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>{fmtRet(yourFundRow.ret3y)}</TableCell>
              <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 12, color: (yourFundRow.ret5y ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>{fmtRet(yourFundRow.ret5y)}</TableCell>
              <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 12, color: '#fff' }}>{yourFundRow.sharpe != null ? Number(yourFundRow.sharpe).toFixed(2) : '—'}</TableCell>
              <TableCell align="center" className="num" sx={{ fontWeight: 700, fontSize: 12, color: '#94A3B8' }}>{yourFundRow.expense != null ? `${Number(yourFundRow.expense).toFixed(2)}%` : '—'}</TableCell>
            </TableRow>
            {/* Peer Rows */}
            {sortedPeers.slice(0, 5).map((p, i) => {
              const peerRank = allReturns.indexOf(Number(p[sortBy]) || 0) + (rank <= i + 1 ? 2 : 1)
              return (
                <TableRow key={i} sx={{ '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' }, '& td': { borderBottom: '1px solid rgba(255,255,255,0.03)' } }}>
                  <TableCell sx={{ fontWeight: 700, color: 'text.secondary', fontSize: 12 }}>{i + (i + 1 >= rank ? 2 : 1)}</TableCell>
                  <TableCell>
                    <Typography variant="caption" sx={{ fontWeight: 700, color: '#CBD5E1', fontSize: 11, display: 'block', maxWidth: 280, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {p.name}
                    </Typography>
                  </TableCell>
                  <TableCell align="center" className="num" sx={{ fontWeight: 700, fontSize: 12, color: (p.ret1y ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>{fmtRet(p.ret1y)}</TableCell>
                  <TableCell align="center" className="num" sx={{ fontWeight: 700, fontSize: 12, color: (p.ret3y ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>{fmtRet(p.ret3y)}</TableCell>
                  <TableCell align="center" className="num" sx={{ fontWeight: 700, fontSize: 12, color: (p.ret5y ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>{fmtRet(p.ret5y)}</TableCell>
                  <TableCell align="center" className="num" sx={{ fontWeight: 700, fontSize: 12, color: '#fff' }}>{p.sharpe != null ? Number(p.sharpe).toFixed(2) : '—'}</TableCell>
                  <TableCell align="center" className="num" sx={{ fontWeight: 700, fontSize: 12, color: '#94A3B8' }}>{p.expense ? `${Number(p.expense).toFixed(2)}%` : '—'}</TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  )
}

const containerVar = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } }
}

const itemVar = {
  hidden: { y: 10, opacity: 0 },
  visible: { y: 0, opacity: 1 }
}

export default function PerformanceTab() {
  const sid = useSessionId()
  const [category, setCategory] = useState('All')
  const [sortBy, setSortBy] = useState('alpha_desc')
  const queryClient = useQueryClient()

  // Always use 'All Time' for the overall portfolio XIRR context
  const { data, isLoading, isFetching, isError } = usePerformance('All Time')

  // Client-side Sort & Filter Engine
  const funds = useMemo(() => {
    const list = (data?.funds ?? []).filter((f: any) => {
      if (category === 'All') return true
      const fCat = f?.cap_type || f?.category || 'Other'
      return fCat.toUpperCase().includes(category.toUpperCase())
    })

    return [...list].sort((a: any, b: any) => {
      if (sortBy === 'alpha_desc') return (b?.alpha ?? -999) - (a?.alpha ?? -999)
      if (sortBy === 'xirr_desc')  return (b?.fund_xi ?? -999) - (a?.fund_xi ?? -999)
      if (sortBy === 'sharpe_desc') return (b?.sharpe ?? -999) - (a?.sharpe ?? -999)
      if (sortBy === 'consistency_desc') return (b?.consistency ?? -999) - (a?.consistency ?? -999)
      if (sortBy === 'vol_asc') return (a?.vol ?? 999) - (b?.vol ?? 999)
      return 0
    })
  }, [data?.funds, category, sortBy])

  if (isError) {
    return (
      <Box sx={{ py: 12, textAlign: 'center' }}>
        <WarningAmberIcon sx={{ fontSize: 60, color: 'warning.main', mb: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>Performance Audit Failed</Typography>
        <Typography variant="body1" sx={{ color: 'text.secondary', mb: 4 }}>The institutional analytics engine encountered a timeout. Please try again.</Typography>
        <Button variant="contained" onClick={() => queryClient.invalidateQueries()}>Retry Audit</Button>
      </Box>
    )
  }

  return (
    <Box sx={{ pb: 8 }}>
      <SectionHeader 
        title="Performance" 
        subtitle="Detailed fund-by-fund performance analysis against market benchmarks."
      />

      <motion.div initial="hidden" animate="visible" variants={containerVar}>
        {/* ── Top Hero Metrics Strip ────────────────────────────────────── */}
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {(() => {
            const portRet = data?.portfolio_return ?? 0
            const benchRet = data?.benchmark_return ?? 0
            const alphaVal = data?.alpha ?? 0
            const pScore = data?.portfolio_score ?? 5
            const nStrong = data?.n_strong || 0
            const nAvg = data?.n_average || 0
            const nWeak = data?.n_weak || 0
            const total = data?.funds?.length || 0
            const benchLabel = data?.benchmark_label || 'Nifty 50'

            return [
              {
                label: data?.is_absolute ? 'Your Returns (Absolute)' : 'Your Returns (XIRR)',
                value: fmtPct(portRet),
                sub: portRet >= 0
                  ? 'Your portfolio is generating positive returns'
                  : 'Your portfolio is currently in negative territory',
                accent: (portRet >= 0 ? 'success' : 'danger') as 'success' | 'danger',
                info: data?.is_absolute
                  ? `Absolute Return. Annualizing returns for holding periods under 1 year heavily distorts figures, so SEBI/industry standards mandate showing absolute returns instead.`
                  : `Annualized return (XIRR) calculated across all your SIP dates, lump sums, and redemptions. This is the true return on your money.`
              },
              {
                label: `${benchLabel} Returns`,
                value: fmtPct(benchRet),
                sub: benchRet >= portRet
                  ? `${benchLabel} would have done better`
                  : `You outperformed ${benchLabel}`,
                accent: 'info' as 'info',
                info: `If you had invested the same amounts on the same dates into ${benchLabel} instead, this is what you would have earned. Apples-to-apples comparison.`
              },
              {
                label: 'Simple Alpha',
                value: fmtPct(alphaVal),
                sub: alphaVal >= 2
                  ? 'Excellent — your fund picks are adding real value'
                  : alphaVal >= 0
                  ? 'Positive — marginally ahead of the market'
                  : 'Negative — an index fund may serve you better',
                accent: (alphaVal >= 0 ? 'success' : 'danger') as 'success' | 'danger',
                info: `Simple Alpha = Your Returns − ${benchLabel} Returns. Positive alpha means your actively managed funds justified their expense ratios. Negative alpha suggests passive index funds may be cheaper and better.`
              },
              {
                label: 'Portfolio Health',
                value: `${pScore}/10`,
                sub: `${nStrong} Strong · ${nAvg} Average · ${nWeak} Weak of ${total}`,
                accent: (pScore >= 7 ? 'success' : pScore >= 5 ? 'warn' : 'danger') as 'success' | 'warn' | 'danger',
                info: `Composite score based on: Alpha (30%), Sharpe ratio (25%), Consistency vs benchmark (25%), and Price stability (20%). Score ≥ 7 = Healthy portfolio. Score < 5 = Needs attention.`
              },
            ].map((m, i) => (
              <Grid item xs={12} sm={6} md={3} key={i}>
                <motion.div variants={itemVar}>
                  <MetricCard {...m} loading={isLoading || isFetching} />
                </motion.div>
              </Grid>
            ))
          })()}
        </Grid>

        {/* ── Advanced Filter & Sort Cockpit ───────────────────────────── */}
        <Paper className="glass" sx={{ p: 3.5, mb: 5, borderRadius: '28px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <Grid container spacing={3} alignItems="center">
            {/* Category Chips */}
            <Grid item xs={12} md={8}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <FilterAltOutlinedIcon sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>CATEGORY SPECTRUM</Typography>
              </Box>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ gap: 1 }}>
                {['All', 'Large Cap', 'Mid Cap', 'Small Cap', 'Flexi/Multi Cap', 'ELSS', 'Debt'].map(c => (
                  <Chip 
                    key={c} label={c} onClick={() => setCategory(c)}
                    sx={{ 
                      borderRadius: '12px', fontWeight: 800, fontSize: 11, py: 2, px: 0.5,
                      bgcolor: category === c ? 'primary.main' : 'rgba(255,255,255,0.03)',
                      color: category === c ? '#fff' : '#94A3B8',
                      border: '1px solid', borderColor: category === c ? 'primary.main' : 'rgba(255,255,255,0.08)',
                      '&:hover': { bgcolor: category === c ? 'primary.main' : 'rgba(255,255,255,0.08)' }
                    }} 
                  />
                ))}
              </Stack>
            </Grid>

            {/* Sort Engine Dropdown */}
            <Grid item xs={12} md={3}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <SortIcon sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>ATTRIBUTION SORT</Typography>
              </Box>
              <FormControl fullWidth size="small">
                <Select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  sx={{ 
                    borderRadius: '14px', bgcolor: 'rgba(0,0,0,0.3)', color: '#fff', fontWeight: 800, fontSize: 13,
                    border: '1px solid rgba(255,255,255,0.1)',
                    '& .MuiOutlinedInput-notchedOutline': { border: 'none' },
                    '& .MuiSvgIcon-root': { color: '#fff' }
                  }}
                  MenuProps={{ PaperProps: { sx: { bgcolor: '#0F172A', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '16px', mt: 1 } } }}
                >
                  <MenuItem value="alpha_desc" sx={{ fontSize: 13, fontWeight: 700, py: 1.5 }}>Alpha Generated (High to Low)</MenuItem>
                  <MenuItem value="xirr_desc" sx={{ fontSize: 13, fontWeight: 700, py: 1.5 }}>XIRR Return (High to Low)</MenuItem>
                  <MenuItem value="sharpe_desc" sx={{ fontSize: 13, fontWeight: 700, py: 1.5 }}>Sharpe Ratio (Risk-Adjusted)</MenuItem>
                  <MenuItem value="consistency_desc" sx={{ fontSize: 13, fontWeight: 700, py: 1.5 }}>Consistency Score (High to Low)</MenuItem>
                  <MenuItem value="vol_asc" sx={{ fontSize: 13, fontWeight: 700, py: 1.5 }}>Volatility (Low to High)</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Paper>

        {/* ── Master Performance Ledger ────────────────────────────────── */}
        {isLoading ? <Skeleton variant="rounded" height={500} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} /> : (
          <motion.div variants={itemVar}>
            <GlassTableContainer>
              <GlassHeader label={`Institutional Performance Ledger (${funds.length} Instruments)`} icon={VerifiedUserIcon} />
              <Table size="medium">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>INSTRUMENT & CATEGORY</TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>RETURN (%)</TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>3Y CAGR</TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>
                      ALPHA (%) <InfoTooltip title="The difference between your portfolio's XIRR and the Benchmark's XIRR. A positive Alpha means your portfolio is beating the market." size={12} />
                    </TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>
                      SHARPE <InfoTooltip title="Measures risk-adjusted return. A higher Sharpe ratio indicates better returns for the level of volatility." size={12} />
                    </TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>
                      SORTINO <InfoTooltip title="Similar to Sharpe, but only penalizes downside volatility (negative returns). Higher is better." size={12} />
                    </TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>VERDICT</TableCell>
                    <TableCell align="right" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>INSPECT</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {funds.map((f: any) => (
                    <PerformanceRow key={f?.fund || Math.random()} fund={f} color={f?.color || '#6366F1'} />
                  ))}
                </TableBody>
              </Table>
            </GlassTableContainer>
          </motion.div>
        )}
      </motion.div>
    </Box>
  )
}

function PerformanceRow({ fund, color }: { fund: any, color: string }) {
  const [expanded, setExpanded] = useState(false)
  const fundName = String(fund?.fund || fund?.name || 'Unknown Instrument')
  const xirrVal = Number(fund?.fund_xi ?? 0)
  const alphaVal = Number(fund?.alpha ?? 0)
  const sharpeVal = fund?.sharpe != null ? Number(fund.sharpe) : null
  const sortinoVal = fund?.sortino != null ? Number(fund.sortino) : null
  const ret3y = fund?.ret_3y != null ? Number(fund.ret_3y) : null

  const insight = CATEGORY_INSIGHTS[fund?.cap_type || fund?.category] || CATEGORY_INSIGHTS['Large Cap']

  return (
    <>
      <TableRow 
        onClick={() => setExpanded(!expanded)}
        sx={{ 
          cursor: 'pointer',
          '&:hover': { background: alpha(color, 0.08) },
          transition: 'background 0.2s ease',
          '& td': { borderBottom: '1px solid rgba(255,255,255,0.03)' }
        }}
      >
        <TableCell>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '4px', bgcolor: color, boxShadow: `0 0 12px ${color}`, flexShrink: 0 }} />
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 800, color: '#fff', fontSize: 14 }}>
                {fundName.length > 40 ? `${fundName.slice(0, 40)}...` : fundName}
              </Typography>
              <Stack direction="row" spacing={1} mt={0.75} alignItems="center">
                <CategoryBadge category={fund?.category || 'Equity'} />
                {fund?.cap_type && fund.cap_type !== fund.category && (
                  <CategoryBadge category={fund.cap_type} />
                )}
                {fund?.cur_value != null && (
                  <Typography variant="caption" sx={{ color: '#4EDE93', fontSize: 11, fontWeight: 800, ml: 1, bgcolor: 'rgba(78, 222, 147, 0.1)', px: 1, py: 0.25, borderRadius: '6px' }}>
                    Current Val: {fmtInr(fund.cur_value, true)}
                  </Typography>
                )}
              </Stack>
            </Box>
          </Box>
        </TableCell>
        <TableCell align="center" className="num" sx={{ py: 1.5 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 0.75 }}>
            <Typography sx={{ fontWeight: 800, fontSize: 15, color: '#fff', display: 'block', lineHeight: 1.2 }}>
              {fmtPct(xirrVal)}
            </Typography>
            {/* SEBI Compliance Trigger: Display 'ABS' badge if holding is < 1 Year */}
            {fund?.is_absolute && (
              <Chip label="ABS" size="small" sx={{ height: 16, fontSize: 9, fontWeight: 900, bgcolor: 'rgba(255,255,255,0.1)', color: '#94A3B8' }} title="Absolute Return (Holding period < 1 Year)" />
            )}
          </Box>
          <Box sx={{ display: 'inline-flex', alignItems: 'center', bgcolor: 'rgba(255,255,255,0.03)', px: 1, py: 0.25, borderRadius: '6px', mt: 0.5, border: '1px solid rgba(255,255,255,0.06)' }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, fontWeight: 700 }}>
              {fund?.bench_display || 'Benchmark'}: <span style={{ color: '#94A3B8', fontWeight: 800 }}>{fmtPct(fund?.bench_xi)}</span>
            </Typography>
          </Box>
        </TableCell>
        <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 14, color: ret3y != null ? (ret3y >= 0 ? '#4EDE93' : '#FF516A') : 'text.secondary' }}>
          {ret3y != null ? fmtPct(ret3y) : '—'}
        </TableCell>
        <TableCell align="center" className="num" sx={{ fontWeight: 900, fontSize: 15, color: alphaVal >= 0 ? '#4EDE93' : '#FF516A' }}>
          {fmtPct(alphaVal)}
        </TableCell>
        <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 15, color: sharpeVal != null ? '#fff' : 'text.secondary' }}>
          {sharpeVal != null ? sharpeVal.toFixed(2) : '—'}
        </TableCell>
        <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 15, color: sortinoVal != null ? '#fff' : 'text.secondary' }}>
          {sortinoVal != null ? sortinoVal.toFixed(2) : '—'}
        </TableCell>
        <TableCell align="center">
          <VerdictChip verdict={fund?.verdict || 'Average'} reason={fund?.verdict_reason} score={fund?.fund_score} />
        </TableCell>
        <TableCell align="right">
          <IconButton size="small" sx={{ color: expanded ? 'primary.main' : 'text.secondary', transform: expanded ? 'rotate(180deg)' : 'none', transition: '0.3s' }}>
            <ExpandMoreIcon />
          </IconButton>
        </TableCell>
      </TableRow>

      <TableRow>
        <TableCell colSpan={8} sx={{ p: 0, border: 'none' }}>
          <AnimatePresence>
            {expanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.35, ease: [0.23, 1, 0.32, 1] }}
                style={{ overflow: 'hidden' }}
              >
                <Box sx={{ p: 4, bgcolor: 'rgba(15, 23, 42, 0.6)', borderBottom: '2px solid rgba(99, 102, 241, 0.3)', boxShadow: 'inset 0 10px 30px rgba(0,0,0,0.5)' }}>
                  <Grid container spacing={4}>
                    {/* Left: Risk & Deviation Audit */}
                    <Grid item xs={12} md={4}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                        <ShowChartIcon sx={{ color: 'primary.main', fontSize: 18 }} />
                        <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>RISK & DEVIATION AUDIT</Typography>
                      </Box>
                      <Stack spacing={1.5} sx={{ p: 2.5, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                        {[
                          { label: <>Annualized Volatility (σ) <InfoTooltip title="The annualized standard deviation of daily returns. Higher volatility means larger price swings." size={12} /></>, val: fund?.vol != null ? `${Number(fund.vol).toFixed(1)}%` : '—' },
                          { label: 'Tracking Error vs Benchmark', val: fund?.tracking_error != null ? `${Number(fund.tracking_error).toFixed(2)}%` : '—' },
                          { label: <>Market Beta (Systematic Risk) <InfoTooltip title="Measures volatility relative to the market. Beta > 1 means the fund is more volatile than the market; Beta < 1 means it is less volatile." size={12} /></>, val: fund?.beta != null ? Number(fund.beta).toFixed(2) : '1.00' },
                          { label: <>Maximum Drawdown (Peak to Trough) <InfoTooltip title="The maximum observed loss from a peak to a trough. Indicates the worst-case historical drop." size={12} /></>, val: fund?.max_dd != null ? `${Number(fund.max_dd).toFixed(1)}%` : '—' },
                          { label: <>Expense Ratio Drag (TER) <InfoTooltip title="Total Expense Ratio (TER). The annual percentage fee charged by the AMC to manage this fund." size={12} /></>, val: fund?.er != null ? `${Number(fund.er).toFixed(2)}%` : '—' },
                        ].map((s, i) => (
                          <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', pb: 1, borderBottom: i < 4 ? '1px dashed rgba(255,255,255,0.06)' : 'none' }}>
                            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>{s.label}</Typography>
                            <Typography className="num" sx={{ fontSize: 13, fontWeight: 800, color: '#fff' }}>{s.val}</Typography>
                          </Box>
                        ))}
                      </Stack>
                    </Grid>

                    {/* Center: Capture & Efficiency Dynamics */}
                    <Grid item xs={12} md={4}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                        <TimelineIcon sx={{ color: 'primary.main', fontSize: 18 }} />
                        <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>CAPTURE & EFFICIENCY DYNAMICS</Typography>
                      </Box>
                      <Stack spacing={1.5} sx={{ p: 2.5, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.05)' }}>
                        {[
                          { label: 'Up-Market Capture Ratio', val: fund?.up_capture != null ? `${Number(fund.up_capture).toFixed(1)}%` : '—', color: (fund?.up_capture ?? 0) > 100 ? '#4EDE93' : '#fff' },
                          { label: 'Down-Market Capture Ratio', val: fund?.down_capture != null ? `${Number(fund.down_capture).toFixed(1)}%` : '—', color: (fund?.down_capture ?? 100) < 100 ? '#4EDE93' : '#FF516A' },
                          { label: 'Information Ratio (IR)', val: fund?.info_ratio != null ? Number(fund.info_ratio).toFixed(2) : '—', color: (fund?.info_ratio ?? 0) >= 0.5 ? '#4EDE93' : '#fff' },
                          { label: 'Calmar Ratio (Return/Drawdown)', val: fund?.calmar != null ? Number(fund.calmar).toFixed(2) : '—', color: '#fff' },
                          { label: 'Treynor Ratio (Return/Beta)', val: fund?.treynor != null ? Number(fund.treynor).toFixed(2) : '—', color: '#fff' },
                        ].map((s, i) => (
                          <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', pb: 1, borderBottom: i < 4 ? '1px dashed rgba(255,255,255,0.06)' : 'none' }}>
                            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>{s.label}</Typography>
                            <Typography className="num" sx={{ fontSize: 13, fontWeight: 900, color: s.color }}>{s.val}</Typography>
                          </Box>
                        ))}
                      </Stack>
                    </Grid>

                    {/* Right: Valuation Multiples & Radar Matrix */}
                    <Grid item xs={12} md={4}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                        <AccountBalanceIcon sx={{ color: 'primary.main', fontSize: 18 }} />
                        <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>VALUATION & RADAR PROFILE</Typography>
                      </Box>
                      <Paper sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(99, 102, 241, 0.08)', border: '1px solid rgba(99, 102, 241, 0.25)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: 'calc(100% - 36px)' }}>
                        <Box>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                            <Chip 
                              label={`ACTION: ${fund?.action ? String(fund.action).toUpperCase() : 'MONITOR'}`} 
                              sx={{ bgcolor: fund?.action === 'Hold' ? '#4EDE93' : fund?.action === 'Review' ? '#FF516A' : '#F59E0B', color: '#000', fontWeight: 900, fontSize: 11, px: 1 }} 
                            />
                            <Typography variant="caption" sx={{ color: '#fff', fontWeight: 800 }}>Consistency: {fund?.consistency ?? 5}/10</Typography>
                          </Box>

                          {!fund?.is_debt && (
                            <Grid container spacing={2} sx={{ mb: 2, bgcolor: 'rgba(0,0,0,0.3)', p: 1.5, borderRadius: '12px' }}>
                              <Grid item xs={6}>
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, fontWeight: 700, display: 'block' }}>EST. P/E RATIO</Typography>
                                <Typography className="num" sx={{ color: '#fff', fontWeight: 800, fontSize: 13 }}>{fund?.pe_ratio != null ? `${fund.pe_ratio}x` : 'N/A'}</Typography>
                              </Grid>
                              <Grid item xs={6}>
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, fontWeight: 700, display: 'block' }}>EST. P/B RATIO</Typography>
                                <Typography className="num" sx={{ color: '#fff', fontWeight: 800, fontSize: 13 }}>{fund?.pb_ratio != null ? `${fund.pb_ratio}x` : 'N/A'}</Typography>
                              </Grid>
                            </Grid>
                          )}

                          {fund?.is_debt && (
                            <Grid container spacing={2} sx={{ mb: 2, bgcolor: 'rgba(0,0,0,0.3)', p: 1.5, borderRadius: '12px' }}>
                              <Grid item xs={6}>
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, fontWeight: 700, display: 'block' }}>YIELD (YTM)</Typography>
                                <Typography className="num" sx={{ color: '#4EDE93', fontWeight: 800, fontSize: 13 }}>{fund.ytm_proxy ? `${fund.ytm_proxy}%` : '7.5%'}</Typography>
                              </Grid>
                              <Grid item xs={6}>
                                <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, fontWeight: 700, display: 'block' }}>DURATION</Typography>
                                <Typography className="num" sx={{ color: '#fff', fontWeight: 800, fontSize: 13 }}>{fund.modified_duration ? `${fund.modified_duration}Y` : '3.0Y'}</Typography>
                              </Grid>
                            </Grid>
                          )}

                          <Typography variant="caption" sx={{ color: '#94A3B8', lineHeight: 1.5, display: 'block' }}>
                            {insight.strategy}
                          </Typography>
                        </Box>
                      </Paper>
                    </Grid>
                  </Grid>
                  
                  {/* Institutional Peer Strip */}
                  {/* <FundPeers fund={fund} /> */}
                </Box>
              </motion.div>
            )}
          </AnimatePresence>
        </TableCell>
      </TableRow>
    </>
  )
}
