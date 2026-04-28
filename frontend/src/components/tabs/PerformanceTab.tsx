import { useState } from 'react'
import {
  Box, Grid, Paper, Typography, Chip, Skeleton, Alert,
  Table, TableHead, TableRow, TableCell, TableBody,
  Accordion, AccordionSummary, AccordionDetails, Select,
  MenuItem, FormControl, InputLabel, Stack,
} from '@mui/material'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Cell,
} from 'recharts'
import { usePerformance } from '../../hooks/useData'
import { VerdictChip, CategoryBadge, PlanBadge, RiskPill, PeriodSelector, SectionHeader } from '../ui'
import { fmtInr, fmtPct, gainColor } from '../../api/fmt'
import type { FundResult } from '../../api/client'

const PERIODS = ['1M','6M','1Y','3Y','5Y','All Time']

export default function PerformanceTab() {
  const [period,  setPeriod]  = useState('1Y')
  const [verdict, setVerdict] = useState('All')
  const [action,  setAction]  = useState('All')
  const [sortBy,  setSortBy]  = useState('alpha_desc')
  const [expanded, setExpanded] = useState<string | false>(false)

  const { data, isLoading, error } = usePerformance(period, { verdict, action, sort_by: sortBy })

  const funds = data?.funds ?? []

  return (
    <Box>
      {/* ── Summary KPIs ─────────────────────────────────────────────── */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Portfolio Return',  value: fmtPct(data?.portfolio_return ?? 0) },
          { label: 'Benchmark Return',  value: fmtPct(data?.benchmark_return ?? 0) },
          { label: 'Alpha',             value: fmtPct(data?.alpha ?? 0) },
          { label: 'Avg Fund Alpha',    value: fmtPct(data?.avg_alpha ?? 0) },
        ].map((k) => (
          <Grid item xs={6} md={3} key={k.label}>
            <Paper elevation={1} sx={{ p: 2.5, borderRadius: 3, textAlign: 'center' }}>
              <Typography variant="overline" display="block">{k.label}</Typography>
              {isLoading ? <Skeleton width="60%" sx={{ mx: 'auto' }} /> : (
                <Typography sx={{
                  fontFamily: '"DM Mono",monospace', fontSize: '1.4rem', fontWeight: 500,
                  color: gainColor(parseFloat(k.value)),
                }}>
                  {k.value}
                </Typography>
              )}
            </Paper>
          </Grid>
        ))}
      </Grid>

      {/* ── Verdict summary chips ────────────────────────────────────── */}
      {!isLoading && (
        <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
          {[
            { label: `${data?.n_strong ?? 0} Strong`,  bg: '#ECFDF5', color: '#059669', border: '#A7F3D0' },
            { label: `${data?.n_average ?? 0} Average`, bg: '#FFFBEB', color: '#D97706', border: '#FDE68A' },
            { label: `${data?.n_weak ?? 0} Weak`,      bg: '#FEF2F2', color: '#DC2626', border: '#FECACA' },
          ].map((c) => (
            <Box key={c.label} sx={{
              px: 2, py: 0.75, borderRadius: 999, fontSize: 12,
              fontWeight: 700, background: c.bg, color: c.color, border: `1px solid ${c.border}`,
            }}>
              {c.label}
            </Box>
          ))}
        </Box>
      )}

      {/* ── Filters row ──────────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ p: 2, mb: 3, borderRadius: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
          <PeriodSelector options={PERIODS} value={period} onChange={setPeriod} />
          <Box sx={{ flex: 1 }} />
          {[
            { label: 'Verdict', value: verdict, onChange: setVerdict, options: ['All','Strong','Average','Weak'] },
            { label: 'Action',  value: action,  onChange: setAction,  options: ['All','Keep','Review','Replace with Index'] },
            { label: 'Sort By', value: sortBy,  onChange: setSortBy,  options: [
              { v:'alpha_desc',  l:'Alpha ↓' }, { v:'alpha_asc', l:'Alpha ↑' },
              { v:'fund_xi',     l:'XIRR ↓'  }, { v:'consistency', l:'Consistency' }, { v:'name', l:'Name' },
            ]},
          ].map((f) => (
            <FormControl size="small" sx={{ minWidth: 140 }} key={f.label}>
              <InputLabel sx={{ fontSize: 12 }}>{f.label}</InputLabel>
              <Select value={f.value} label={f.label} onChange={(e) => f.onChange(e.target.value as string)} sx={{ fontSize: 12 }}>
                {f.options.map((o: any) =>
                  typeof o === 'string'
                    ? <MenuItem key={o} value={o} sx={{ fontSize: 12 }}>{o}</MenuItem>
                    : <MenuItem key={o.v} value={o.v} sx={{ fontSize: 12 }}>{o.l}</MenuItem>
                )}
              </Select>
            </FormControl>
          ))}
        </Box>
      </Paper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>Failed to load performance data.</Alert>}

      {/* ── Fund cards (accordion) ───────────────────────────────────── */}
      {isLoading
        ? Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} variant="rectangular" height={72} sx={{ borderRadius: 2, mb: 1 }} />
          ))
        : funds.map((fund: FundResult) => (
          <Accordion
            key={fund.fund}
            expanded={expanded === fund.fund}
            onChange={(_, isExp) => setExpanded(isExp ? fund.fund : false)}
            sx={{ mb: 1 }}
          >
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flex: 1, flexWrap: 'wrap', mr: 1 }}>
                {/* Color dot */}
                <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: fund.color, flexShrink: 0 }} />

                <Typography variant="body2" fontWeight={700} sx={{ flex: 1, minWidth: 160 }}>
                  {fund.fund.length > 45 ? fund.fund.slice(0, 45) + '…' : fund.fund}
                </Typography>

                <Stack direction="row" spacing={0.75} flexWrap="wrap" sx={{ gap: 0.75 }}>
                  <CategoryBadge category={fund.category} />
                  <PlanBadge plan={fund.plan} />
                  <VerdictChip verdict={fund.verdict} />
                </Stack>

                <Box sx={{ display: 'flex', gap: 2, ml: 'auto', flexShrink: 0 }}>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="overline" display="block">Fund XIRR</Typography>
                    <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: gainColor(fund.fund_xi) }}>
                      {fmtPct(fund.fund_xi)}
                    </Typography>
                  </Box>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="overline" display="block">Alpha</Typography>
                    <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: gainColor(fund.alpha) }}>
                      {fmtPct(fund.alpha)}
                    </Typography>
                  </Box>
                </Box>
              </Box>
            </AccordionSummary>

            <AccordionDetails>
              <Grid container spacing={2}>
                {/* ── Stats grid ── */}
                <Grid item xs={12} md={5}>
                  <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.5 }}>
                    {[
                      { label: 'Benchmark',    value: fund.bench_display },
                      { label: 'Bench XIRR',   value: fmtPct(fund.bench_xi) },
                      { label: 'Current Value',value: fmtInr(fund.cur_value, true) },
                      { label: 'Consistency',  value: `${fund.consistency}/10` },
                      { label: 'Sharpe Ratio', value: fund.sharpe.toFixed(2) },
                      { label: 'Sortino',      value: fund.sortino.toFixed(2) },
                      { label: 'Beta',         value: fund.beta.toFixed(2) },
                      { label: 'Max Drawdown', value: `${fund.max_dd}%` },
                      { label: 'Expense Ratio',value: `${fund.er.toFixed(2)}%` },
                      { label: 'Cat. Rank',    value: `${fund.cat_rank}/${fund.cat_total}` },
                    ].map((s) => (
                      <Box key={s.label} sx={{ background: '#F8FAFC', borderRadius: 2, p: 1.5 }}>
                        <Typography variant="overline" display="block" sx={{ mb: 0.25 }}>{s.label}</Typography>
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#0F172A' }}>
                          {s.value}
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                  <Box sx={{ mt: 1.5, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                    <RiskPill label={fund.risk_label} />
                    <Box sx={{
                      px: 1.5, py: 0.4, borderRadius: 999, fontSize: 11, fontWeight: 700,
                      background: '#EFF6FF', color: '#1D4ED8', border: '1px solid #BFDBFE',
                    }}>
                      Action: {fund.action}
                    </Box>
                  </Box>
                </Grid>

                {/* ── Rolling returns bar chart ── */}
                <Grid item xs={12} md={7}>
                  <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Rolling Returns vs Benchmark</Typography>
                  <ResponsiveContainer width="100%" height={180}>
                    <BarChart
                      data={fund.roll_labels.map((l: string, i: number) => ({
                        period: l,
                        Fund:      fund.fund_rolls[i],
                        Benchmark: fund.bench_rolls[i],
                      }))}
                      barCategoryGap="30%"
                      margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                      <XAxis dataKey="period" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v.toFixed(0)}%`} />
                      <Tooltip
                        formatter={(v: any) => `${Number(v).toFixed(2)}%`}
                        contentStyle={{ borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 12 }}
                      />
                      <Bar dataKey="Fund"      fill="#1D4ED8" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Benchmark" fill="#CBD5E1" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </Grid>
              </Grid>
            </AccordionDetails>
          </Accordion>
        ))
      }

      {!isLoading && funds.length === 0 && (
        <Alert severity="info">No funds match the current filters.</Alert>
      )}
    </Box>
  )
}
