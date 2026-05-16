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
  GlassTableContainer, GlassHeader
} from '../ui'
import { fmtInr, fmtPct } from '../../api/fmt'

// ── Constants & Config ───────────────────────────────────────────────────────
const CATEGORY_INSIGHTS: Record<string, { strategy: string, focus: string, timeline: string }> = {
  'Large Cap': {
    strategy: 'Allocates heavily to top 100 blue-chip entities. Acts as a core foundation that prioritizes capital preservation.',
    focus: 'Capital Stability & Dividend Yields',
    timeline: '3 - 5 Years'
  },
  'Mid Cap': {
    strategy: 'Targets fast-growing mid-tier companies ranked 101-250. Offers a balance of scalability and market agility.',
    focus: 'Aggressive Capital Appreciation',
    timeline: '5 - 7 Years'
  },
  'Small Cap': {
    strategy: 'Mandated to target high-alpha micro-companies. Leads aggressive bullish market trends but exhibits deeper volatile pullbacks.',
    focus: 'High Alpha Compounding',
    timeline: '7+ Years'
  },
  'Flexi/Multi Cap': {
    strategy: 'Unconstrained deployment allowing managers to shift between cap sizes based on economic tailwinds.',
    focus: 'All-Weather Diversification',
    timeline: '5 Years'
  },
  'ELSS': {
    strategy: 'Tax-saving equity funds with a 3-year statutory lock-in period. Promotes disciplined compounding.',
    focus: 'Section 80C Tax Breaks & Growth',
    timeline: '3+ Years'
  },
  'Index': {
    strategy: 'Passively tracks primary benchmarks like the Nifty 50. Minimizes active manager risk and maximizes cost efficiency.',
    focus: 'Low-Cost Market Beta',
    timeline: '3 - 5 Years'
  },
  'Debt': {
    strategy: 'Invests in sovereign securities, corporate debentures, and money market instruments to insulate against equity downturns.',
    focus: 'Yield Accrual & Capital Preservation',
    timeline: '1 - 3 Years'
  },
  'Hybrid': {
    strategy: 'Dynamic asset allocation models balancing equity growth momentum with fixed income stability.',
    focus: 'Risk-Adjusted Compounding',
    timeline: '3 - 5 Years'
  }
}

// ── Peer Audit Component ─────────────────────────────────────────────────────
function FundPeers({ fund }: { fund: any }) {
  const [peers, setPeers] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [sortBy, setSortBy] = useState<'ret1y' | 'ret3y' | 'ret5y' | 'alpha'>('ret1y')

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      try {
        const cat = fund?.cap_type || fund?.category || "Large Cap"
        const res = await apiClient.getCategoryPeers(cat)
        if (active && res && res.peers) setPeers(res.peers)
      } catch (e) { console.error(e) } 
      finally { if (active) setLoading(false) }
    }
    load()
    return () => { active = false }
  }, [fund?.cap_type, fund?.category])

  const sortedPeers = useMemo(() => {
    const arr = [...peers]
    arr.sort((a, b) => {
      if (sortBy === 'alpha') return (Number(b.alpha_num) || 0) - (Number(a.alpha_num) || 0)
      return (Number(b[sortBy]) || 0) - (Number(a[sortBy]) || 0)
    })
    return arr
  }, [peers, sortBy])

  if (loading) {
    return (
      <Box sx={{ mt: 4, pt: 4, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        <Typography variant="overline" sx={{ fontWeight: 800, color: 'primary.main', mb: 2, display: 'block', letterSpacing: '0.15em' }}>
          INSTITUTIONAL PEER AUDIT
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

  return (
    <Box sx={{ mt: 4, pt: 4, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <CompareArrowsIcon sx={{ color: 'primary.main', fontSize: 20 }} />
          <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>
            INSTITUTIONAL CATEGORY PEERS ({fund?.cap_type || fund?.category || 'Equity'})
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, bgcolor: 'rgba(0,0,0,0.3)', p: 0.5, borderRadius: '100px', border: '1px solid rgba(255,255,255,0.1)' }}>
          <Typography variant="caption" sx={{ px: 1, color: 'text.secondary', fontWeight: 700 }}>SORT:</Typography>
          {(['ret1y', 'ret3y', 'ret5y', 'alpha'] as const).map((key) => (
            <Button
              key={key}
              size="small"
              onClick={() => setSortBy(key)}
              sx={{
                minWidth: 'auto',
                px: 1.5,
                py: 0.5,
                borderRadius: '100px',
                fontSize: 11,
                fontWeight: 800,
                color: sortBy === key ? '#000' : 'text.secondary',
                bgcolor: sortBy === key ? 'primary.main' : 'transparent',
                '&:hover': { bgcolor: sortBy === key ? 'primary.main' : 'rgba(255,255,255,0.05)' }
              }}
            >
              {key === 'ret1y' ? '1Y RET' : key === 'ret3y' ? '3Y RET' : key === 'ret5y' ? '5Y RET' : 'ALPHA'}
            </Button>
          ))}
        </Box>
      </Box>
      <Grid container spacing={3}>
        {sortedPeers.slice(0, 5).map((p, i) => (
          <Grid item xs={12} sm={6} md={4} key={i}>
            <Paper sx={{ 
              p: 2.5, borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.02)', 
              border: '1px solid rgba(255,255,255,0.06)', position: 'relative', overflow: 'hidden',
              '&:hover': { bgcolor: 'rgba(255,255,255,0.04)', borderColor: 'primary.main' },
              transition: 'all 0.2s'
            }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, display: 'block', mb: 0.5 }}>
                {p.symbol || p.code || `PEER-${i+1}`}
              </Typography>
              <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#fff', mb: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {p.name}
              </Typography>

              <Grid container spacing={1.5} sx={{ bgcolor: 'rgba(0,0,0,0.3)', p: 1.5, borderRadius: '12px' }}>
                <Grid item xs={4}>
                  <Typography variant="caption" sx={{ color: sortBy === 'ret1y' ? 'primary.main' : 'text.secondary', display: 'block', fontSize: 10, fontWeight: 700 }}>1Y RET</Typography>
                  <Typography className="num" sx={{ fontWeight: 800, color: (p.ret1y ?? 0) >= 0 ? '#4EDE93' : '#FF516A', fontSize: 13 }}>
                    {p.ret1y ? `${p.ret1y >= 0 ? '+' : ''}${Number(p.ret1y).toFixed(1)}%` : '—'}
                  </Typography>
                </Grid>
                <Grid item xs={4}>
                  <Typography variant="caption" sx={{ color: sortBy === 'ret3y' ? 'primary.main' : 'text.secondary', display: 'block', fontSize: 10, fontWeight: 700 }}>3Y RET</Typography>
                  <Typography className="num" sx={{ fontWeight: 800, color: (p.ret3y ?? 0) >= 0 ? '#4EDE93' : '#FF516A', fontSize: 13 }}>
                    {p.ret3y ? `${p.ret3y >= 0 ? '+' : ''}${Number(p.ret3y).toFixed(1)}%` : '—'}
                  </Typography>
                </Grid>
                <Grid item xs={4}>
                  <Typography variant="caption" sx={{ color: sortBy === 'ret5y' ? 'primary.main' : 'text.secondary', display: 'block', fontSize: 10, fontWeight: 700 }}>5Y RET</Typography>
                  <Typography className="num" sx={{ fontWeight: 800, color: (p.ret5y ?? 0) >= 0 ? '#4EDE93' : '#FF516A', fontSize: 13 }}>
                    {p.ret5y ? `${p.ret5y >= 0 ? '+' : ''}${Number(p.ret5y).toFixed(1)}%` : '—'}
                  </Typography>
                </Grid>
                <Grid item xs={6} sx={{ mt: 0.5, pt: 1, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                  <Typography variant="caption" sx={{ color: sortBy === 'alpha' ? 'primary.main' : 'text.secondary', display: 'block', fontSize: 10, fontWeight: 700 }}>ALPHA</Typography>
                  <Typography className="num" sx={{ fontWeight: 800, color: '#fff', fontSize: 13 }}>
                    {p.alpha || '—'}
                  </Typography>
                </Grid>
                <Grid item xs={6} sx={{ mt: 0.5, pt: 1, borderTop: '1px solid rgba(255,255,255,0.05)', textAlign: 'right' }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', fontSize: 10, fontWeight: 700 }}>EXPENSE</Typography>
                  <Typography className="num" sx={{ fontWeight: 800, color: '#94A3B8', fontSize: 13 }}>
                    {p.expense ? `${Number(p.expense).toFixed(2)}%` : '—'}
                  </Typography>
                </Grid>
              </Grid>
            </Paper>
          </Grid>
        ))}
      </Grid>
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
  const [period, setPeriod] = useState('1Y')
  const [category, setCategory] = useState('All')
  const [sortBy, setSortBy] = useState('alpha_desc')
  const queryClient = useQueryClient()

  const { data, isLoading, isFetching, isError } = usePerformance(period)

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
        title="Performance Audit" 
        subtitle="Institutional-grade performance attribution, risk-adjusted alpha profiling, and peer benchmarking."
      />

      <motion.div initial="hidden" animate="visible" variants={containerVar}>
        {/* ── Top Hero Metrics Strip ────────────────────────────────────── */}
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {[
            { label: 'Portfolio XIRR', value: fmtPct(data?.portfolio_return ?? 0), sub: `Trailing ${period} compounding`, accent: 'success' as const, info: 'Exact money-weighted annualized return across uploaded CAS transactions.' },
            { label: 'Benchmark Index', value: fmtPct(data?.benchmark_return ?? 0), sub: data?.benchmark_label || 'Nifty 50', accent: 'info' as const, info: 'Benchmark index performance computed point-to-point over identical cashflow intervals.' },
            { label: 'Alpha Generated', value: `${(data?.alpha ?? 0) >= 0 ? '+' : ''}${fmtPct(data?.alpha ?? 0)}`, sub: 'Relative spot outperformance', accent: ((data?.alpha ?? 0) >= 0 ? 'success' : 'danger') as 'success' | 'danger', info: 'Excess return generated over benchmark beta.' },
            { label: 'Portfolio Verdict', value: `${data?.n_strong || 0}/${data?.funds?.length || 0}`, sub: 'Funds with "Strong" institutional rating', accent: 'warn' as const, info: 'Funds scoring highly across Consistency, Sharpe, and Alpha metrics.' },
          ].map((m, i) => (
            <Grid item xs={12} sm={6} md={3} key={i}>
              <motion.div variants={itemVar}>
                <MetricCard {...m} loading={isLoading || isFetching} />
              </motion.div>
            </Grid>
          ))}
        </Grid>

        {/* ── Advanced Filter & Sort Cockpit ───────────────────────────── */}
        <Paper className="glass" sx={{ p: 3.5, mb: 5, borderRadius: '28px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <Grid container spacing={3} alignItems="center">
            {/* Horizon Selector */}
            <Grid item xs={12} md={4}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <SpeedIcon sx={{ fontSize: 16, color: 'primary.main' }} />
                <Typography variant="overline" sx={{ fontWeight: 900, color: 'primary.main', letterSpacing: '0.15em' }}>AUDIT HORIZON</Typography>
              </Box>
              <PeriodSelector options={['1M', '6M', '1Y', '3Y', '5Y', 'All Time']} value={period} onChange={setPeriod} />
            </Grid>

            {/* Category Chips */}
            <Grid item xs={12} md={5}>
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
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>FUND vs BENCHMARK XIRR</TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>ALPHA FORCE</TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>SHARPE RATIO</TableCell>
                    <TableCell align="center" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>INSTITUTIONAL VERDICT</TableCell>
                    <TableCell align="right" sx={{ borderBottom: '1px solid rgba(255,255,255,0.06)', fontWeight: 900, color: 'text.secondary', fontSize: 11, letterSpacing: '0.05em' }}>INSPECTION</TableCell>
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
          <Typography sx={{ fontWeight: 800, fontSize: 15, color: '#fff', display: 'block', lineHeight: 1.2 }}>
            {fmtPct(xirrVal)}
          </Typography>
          <Box sx={{ display: 'inline-flex', alignItems: 'center', bgcolor: 'rgba(255,255,255,0.03)', px: 1, py: 0.25, borderRadius: '6px', mt: 0.5, border: '1px solid rgba(255,255,255,0.06)' }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10, fontWeight: 700 }}>
              {fund?.bench_display || 'Benchmark'}: <span style={{ color: '#94A3B8', fontWeight: 800 }}>{fmtPct(fund?.bench_xi)}</span>
            </Typography>
          </Box>
        </TableCell>
        <TableCell align="center" className="num" sx={{ fontWeight: 900, fontSize: 15, color: alphaVal >= 0 ? '#4EDE93' : '#FF516A' }}>
          {fmtPct(alphaVal)}
        </TableCell>
        <TableCell align="center" className="num" sx={{ fontWeight: 800, fontSize: 15, color: sharpeVal != null ? '#fff' : 'text.secondary' }}>
          {sharpeVal != null ? sharpeVal.toFixed(2) : '—'}
        </TableCell>
        <TableCell align="center">
          <VerdictChip verdict={fund?.verdict || 'Average'} />
        </TableCell>
        <TableCell align="right">
          <IconButton size="small" sx={{ color: expanded ? 'primary.main' : 'text.secondary', transform: expanded ? 'rotate(180deg)' : 'none', transition: '0.3s' }}>
            <ExpandMoreIcon />
          </IconButton>
        </TableCell>
      </TableRow>

      <TableRow>
        <TableCell colSpan={6} sx={{ p: 0, border: 'none' }}>
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
                          { label: 'Annualized Volatility (σ)', val: fund?.vol != null ? `${Number(fund.vol).toFixed(1)}%` : '—' },
                          { label: 'Tracking Error vs Benchmark', val: fund?.tracking_error != null ? `${Number(fund.tracking_error).toFixed(2)}%` : '—' },
                          { label: 'Market Beta (Systematic Risk)', val: fund?.beta != null ? Number(fund.beta).toFixed(2) : '1.00' },
                          { label: 'Maximum Drawdown (Peak to Trough)', val: fund?.max_dd != null ? `${Number(fund.max_dd).toFixed(1)}%` : '—' },
                          { label: 'Expense Ratio Drag (TER)', val: fund?.er != null ? `${Number(fund.er).toFixed(2)}%` : '—' },
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
                  <FundPeers fund={fund} />
                </Box>
              </motion.div>
            )}
          </AnimatePresence>
        </TableCell>
      </TableRow>
    </>
  )
}
