import { useState } from 'react'
import {
  Box, Grid, Paper, Typography, Skeleton, Alert, Chip,
} from '@mui/material'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { motion } from 'framer-motion'
import { useSummary, useOverview, useAllocation } from '../../hooks/useData'
import { MetricCard, SectionHeader, PeriodSelector, ScoreRing, LoadingGrid } from '../ui'
import { fmtInr, fmtPct, gainColor } from '../../api/fmt'

const PERIODS = ['1M','3M','6M','1Y','3Y','5Y','ALL']

// ── Custom chart tooltip ──────────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <Box sx={{
      background: '#0F172A', borderRadius: 2, p: 1.5,
      border: '1px solid rgba(255,255,255,0.1)',
      boxShadow: '0 8px 24px rgba(0,0,0,0.3)',
    }}>
      <Typography sx={{ fontSize: 11, color: '#94A3B8', mb: 0.5, fontWeight: 600 }}>{label}</Typography>
      {payload.map((p: any) => (
        <Box key={p.name} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.25 }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: p.color, flexShrink: 0 }} />
          <Typography sx={{ fontSize: 12, color: '#E2E8F0', fontFamily: '"DM Mono",monospace' }}>
            {p.name}: {p.value?.toFixed(1)}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

// ── Donut chart (SVG, no dep) ─────────────────────────────────────────────────
function DonutChart({ data, size = 160 }: { data: { label: string; value: number; pct: number; color: string }[]; size?: number }) {
  const total  = data.reduce((a, b) => a + b.value, 0)
  const cx = size / 2; const cy = size / 2; const r = size * 0.36; const ir = size * 0.22
  let startAngle = -90
  const slices = data.filter(d => d.value > 0).map(d => {
    const angle = (d.value / total) * 360
    const s = startAngle; startAngle += angle
    return { ...d, startAngle: s, angle }
  })

  function polarToXY(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = (angleDeg * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }
  function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
    const s = polarToXY(cx, cy, r, startDeg)
    const e = polarToXY(cx, cy, r, endDeg)
    const large = endDeg - startDeg > 180 ? 1 : 0
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`
  }

  return (
    <svg width={size} height={size}>
      {slices.map((s, i) => {
        const outerPath = arcPath(cx, cy, r, s.startAngle, s.startAngle + s.angle - 0.5)
        const innerStart = polarToXY(cx, cy, ir, s.startAngle + s.angle - 0.5)
        const innerEnd   = polarToXY(cx, cy, ir, s.startAngle)
        const large = s.angle > 180 ? 1 : 0
        const d = `${outerPath} L ${innerStart.x} ${innerStart.y} A ${ir} ${ir} 0 ${large} 0 ${innerEnd.x} ${innerEnd.y} Z`
        return <path key={i} d={d} fill={s.color} opacity={0.9}>
          <title>{s.label}: {s.pct?.toFixed(1)}%</title>
        </path>
      })}
      <circle cx={cx} cy={cy} r={ir - 2} fill="#FFFFFF" />
    </svg>
  )
}

export default function OverviewTab() {
  const [period, setPeriod] = useState('1Y')
  const { data: sum,   isLoading: sumL }  = useSummary()
  const { data: ov,    isLoading: ovL }   = useOverview(period)
  const { data: alloc, isLoading: allocL } = useAllocation()

  // Build chart data
  const chartData = ov?.chart?.dates?.map((d: string, i: number) => ({
    date:      d.slice(5),   // MM-DD
    Portfolio: ov.chart.portfolio[i],
    Benchmark: ov.chart.benchmark[i],
  })) ?? []

  const portReturn  = ov?.port_pct  ?? 0
  const benchReturn = ov?.bench_pct ?? 0
  const alpha       = portReturn - benchReturn

  return (
    <Box>
      {/* ── KPI row ─────────────────────────────────────────────────── */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Portfolio Value',  value: fmtInr(sum?.total_value, true),    sub: `Invested ${fmtInr(sum?.total_invested, true)}`, accent: 'info' as const },
          { label: 'Total Gain / Loss',value: fmtInr(sum?.total_gain, true),     sub: fmtPct(sum?.gain_pct) + ' absolute return',      accent: (sum?.total_gain ?? 0) >= 0 ? 'success' as const : 'danger' as const },
          { label: 'Portfolio XIRR',   value: fmtPct(sum?.portfolio_xirr ?? 0), sub: `Benchmark XIRR ${fmtPct(sum?.bench_xirr ?? 0)}`,  accent: (sum?.alpha ?? 0) >= 0 ? 'success' as const : 'danger' as const },
          { label: 'Alpha',            value: fmtPct(sum?.alpha ?? 0),           sub: `vs ${sum?.is_partial ? 'Partial CAS' : 'Full CAS'}`, accent: (sum?.alpha ?? 0) >= 0 ? 'success' as const : 'danger' as const },
        ].map((card) => (
          <Grid item xs={12} sm={6} md={3} key={card.label}>
            <MetricCard {...card} loading={sumL} />
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          { label: 'Expense Drag / yr', value: fmtInr(sum?.expense_drag), sub: 'Estimated annual cost',         accent: 'warn' as const },
          { label: 'Funds',             value: String(sum?.num_funds ?? 0), sub: `${sum?.num_amcs ?? 0} AMCs`,  accent: 'info' as const },
          { label: 'Bench CAGR',        value: fmtPct(sum?.bench_cagr ?? 0), sub: 'Benchmark compound return', accent: 'none' as const },
          { label: 'SIP Consistency',   value: `${sum?.sip_score ?? 0}/10`,  sub: 'Score based on regularity', accent: 'success' as const },
        ].map((card) => (
          <Grid item xs={12} sm={6} md={3} key={card.label}>
            <MetricCard {...card} loading={sumL} />
          </Grid>
        ))}
      </Grid>

      {/* ── Performance chart ────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ p: 3, mb: 3, borderRadius: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2, flexWrap: 'wrap', gap: 2 }}>
          <Box>
            <SectionHeader title="Portfolio vs Benchmark" />
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, color: gainColor(portReturn), fontWeight: 600 }}>
                Portfolio {fmtPct(portReturn)}
              </Typography>
              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, color: '#94A3B8', fontWeight: 600 }}>
                {ov?.benchmark_name ?? 'Benchmark'} {fmtPct(benchReturn)}
              </Typography>
              <Chip
                size="small"
                label={`Alpha ${fmtPct(alpha)}`}
                sx={{
                  fontFamily: '"DM Mono",monospace', fontSize: 11, fontWeight: 700,
                  background: alpha >= 0 ? '#ECFDF5' : '#FEF2F2',
                  color: alpha >= 0 ? '#059669' : '#DC2626',
                }}
              />
            </Box>
          </Box>
          <PeriodSelector options={PERIODS} value={period} onChange={setPeriod} />
        </Box>
        {ovL ? <Skeleton variant="rectangular" height={260} sx={{ borderRadius: 2 }} /> : (
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="portGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#1D4ED8" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#1D4ED8" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="benchGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#94A3B8" stopOpacity={0.10} />
                  <stop offset="95%" stopColor="#94A3B8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v.toFixed(0)}`} />
              <Tooltip content={<ChartTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600, paddingTop: 8 }} />
              <Area type="monotone" dataKey="Portfolio" stroke="#1D4ED8" strokeWidth={2.5} fill="url(#portGrad)" dot={false} activeDot={{ r: 4 }} />
              <Area type="monotone" dataKey="Benchmark" stroke="#94A3B8" strokeWidth={1.5} fill="url(#benchGrad)" strokeDasharray="5 3" dot={false} activeDot={{ r: 3 }} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Paper>

      {/* ── Allocation row ───────────────────────────────────────────── */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {/* Broad asset class donut */}
        <Grid item xs={12} md={4}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, height: '100%' }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Asset Mix</Typography>
            {allocL ? <Skeleton variant="circular" width={160} height={160} sx={{ mx: 'auto' }} /> : (
              <>
                <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
                  <DonutChart data={(alloc?.broad ?? []).filter((d: any) => d.value > 0)} />
                </Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                  {(alloc?.broad ?? []).filter((d: any) => d.value > 0).map((d: any) => (
                    <Box key={d.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: d.color, flexShrink: 0 }} />
                        <Typography variant="body2" fontWeight={600}>{d.label}</Typography>
                      </Box>
                      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#64748B' }}>
                        {d.pct?.toFixed(1)}%
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </>
            )}
          </Paper>
        </Grid>

        {/* Cap size */}
        <Grid item xs={12} md={4}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, height: '100%' }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Cap Breakdown</Typography>
            {allocL ? <Skeleton variant="rectangular" height={180} sx={{ borderRadius: 2 }} /> : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {(alloc?.by_cap ?? []).map((d: any) => {
                  const pct = d.pct ?? 0
                  return (
                    <Box key={d['Cap Type']}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2" fontWeight={600}>{d['Cap Type']}</Typography>
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#64748B' }}>
                          {pct.toFixed(1)}% · {fmtInr(d['Market Value'], true)}
                        </Typography>
                      </Box>
                      <Box sx={{ background: '#F1F5F9', borderRadius: 999, height: 7, overflow: 'hidden' }}>
                        <Box sx={{
                          height: '100%', borderRadius: 999,
                          background: 'linear-gradient(90deg, #1D4ED8, #60A5FA)',
                          width: `${pct}%`, transition: 'width 600ms cubic-bezier(0,0,0,1)',
                        }} />
                      </Box>
                    </Box>
                  )
                })}
              </Box>
            )}
          </Paper>
        </Grid>

        {/* Plan type */}
        <Grid item xs={12} md={4}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, height: '100%' }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Direct vs Regular</Typography>
            {allocL ? <Skeleton variant="rectangular" height={180} sx={{ borderRadius: 2 }} /> : (
              <>
                {(alloc?.reg_pct ?? 0) > 10 ? (
                  <Alert severity="warning" sx={{ mb: 2, fontSize: 12 }}>
                    <strong>{alloc?.reg_pct?.toFixed(1)}%</strong> in Regular plans. Switching to Direct saves ~0.5–1.5% p.a.
                  </Alert>
                ) : (
                  <Alert severity="success" sx={{ mb: 2, fontSize: 12 }}>
                    Mostly Direct plans — excellent cost efficiency.
                  </Alert>
                )}
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {(alloc?.by_plan ?? []).map((d: any) => (
                    <Box key={d.Plan} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 1.5, background: '#F8FAFC', borderRadius: 2 }}>
                      <Typography variant="body2" fontWeight={700}>{d.Plan}</Typography>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#0F172A' }}>
                          {fmtInr(d['Market Value'], true)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">{d.pct?.toFixed(1)}%</Typography>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </>
            )}
          </Paper>
        </Grid>
      </Grid>

      {/* ── Portfolio Score ──────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
        <Grid container spacing={3} alignItems="center">
          <Grid item xs={12} md={3} sx={{ textAlign: 'center' }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Portfolio Score</Typography>
            <ScoreRing score={sum?.port_score ?? 0} size={120} />
          </Grid>
          <Grid item xs={12} md={9}>
            <Typography variant="h6" sx={{ mb: 2 }}>Score Breakdown</Typography>
            {[
              { label: 'Alpha vs Benchmark',  max: 30 },
              { label: 'Fund Diversification', max: 25 },
              { label: 'Direct Plan Usage',    max: 20 },
              { label: 'Concentration Risk',   max: 15 },
              { label: 'Category Balance',     max: 10 },
            ].map((item) => (
              <Box key={item.label} sx={{ mb: 1.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                  <Typography variant="body2" fontWeight={600}>{item.label}</Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11, color: '#94A3B8' }}>/{item.max}</Typography>
                </Box>
                <Box sx={{ background: '#F1F5F9', borderRadius: 999, height: 7 }}>
                  <Box sx={{
                    height: '100%', borderRadius: 999,
                    background: 'linear-gradient(90deg, #059669, #34D399)',
                    width: `${Math.min(100, (sum?.port_score ?? 0) / item.max * 100)}%`,
                    transition: 'width 600ms cubic-bezier(0,0,0,1)',
                  }} />
                </Box>
              </Box>
            ))}
          </Grid>
        </Grid>
      </Paper>
    </Box>
  )
}
