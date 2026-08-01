import { useMemo, useState } from 'react'
import { Box, Chip, Paper, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { fmtInr } from '../../../../shared/utils/fmt'
import { useClearSessionOnMissing, useEquityPerformance } from '../../hooks/useEquityData'
import { EquityTabError, EquityTabSkeleton, GLASS_PAPER } from './shared'

const PERIODS = ['1M', '3M', '6M', '1Y', '3Y'] as const

export default function PerformanceTab() {
  const [period, setPeriod] = useState<string>('1Y')
  const [benchmark, setBenchmark] = useState<string>('Nifty 50')

  const { data, isPending, isError, error, isPlaceholderData } = useEquityPerformance(period, benchmark)
  useClearSessionOnMissing(error)

  // Memoized: this zip ran on every render and handed recharts a new array identity
  // each time, defeating its internal bailout on a series of up to ~750 points. The
  // `portfolio`/`benchmark` reads were also unguarded, so a response with `dates` and
  // no `portfolio` threw inside render — which, under a single module-level
  // ErrorBoundary, blanked the whole equity dashboard including the tab bar.
  const chartData = useMemo(() => {
    const dates = data?.dates ?? []
    const portfolio = data?.portfolio ?? []
    const bench = data?.benchmark ?? []
    return dates.map((d, i) => ({
      date: d,
      portfolio: portfolio[i] ?? null,
      benchmark: bench[i] ?? null,
    }))
  }, [data])

  if (isPending) return <EquityTabSkeleton rows={7} />
  if (isError) return <EquityTabError error={error} label="performance" />

  const priced = data?.priced_symbols
  const total = data?.total_symbols
  const partial = priced != null && total != null && priced < total

  return (
    <Box>
      <Paper className="glass" sx={{ ...GLASS_PAPER, p: { xs: 2, md: 4 } }}>
        <Box
          sx={{
            display: 'flex', flexDirection: { xs: 'column', md: 'row' },
            justifyContent: 'space-between', alignItems: { xs: 'flex-start', md: 'center' },
            mb: 4, gap: 2,
          }}
        >
          <Box>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 0.5 }}>Portfolio Performance</Typography>
            <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem' }}>
              Mark-to-market comparison against {benchmark}
            </Typography>
            {/* Stated rather than silently charting a partial portfolio as if complete. */}
            {partial && (
              <Chip
                size="small"
                label={`${priced} of ${total} holdings have price history`}
                sx={{ mt: 1, background: 'rgba(245,158,11,0.15)', color: '#F59E0B', fontWeight: 600 }}
              />
            )}
          </Box>
          <ToggleButtonGroup
            value={period}
            exclusive
            onChange={(_, v) => v && setPeriod(v)}
            size="small"
            sx={{
              background: 'rgba(255,255,255,0.03)', p: 0.5, borderRadius: '12px',
              '& .MuiToggleButton-root': {
                border: 'none', borderRadius: '8px !important', color: '#64748B',
                fontWeight: 600, px: 2, textTransform: 'none',
                '&.Mui-selected': { background: 'rgba(16,185,129,0.15)', color: '#10B981' },
              },
            }}
          >
            {PERIODS.map((p) => (
              <ToggleButton key={p} value={p}>{p}</ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>

        <Box sx={{ height: 400, width: '100%', opacity: isPlaceholderData ? 0.6 : 1, transition: 'opacity 120ms' }}>
          {chartData.length === 0 ? (
            <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Typography sx={{ color: '#64748B' }}>Not enough historical data.</Typography>
            </Box>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorPort" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10B981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                <XAxis
                  dataKey="date"
                  stroke="#64748B"
                  fontSize={12}
                  tickFormatter={(v: string) => {
                    const d = new Date(v)
                    if (Number.isNaN(d.getTime())) return v
                    return `${d.getDate()} ${d.toLocaleString('default', { month: 'short' })}`
                  }}
                  minTickGap={30}
                />
                <YAxis
                  stroke="#64748B"
                  fontSize={12}
                  tickFormatter={(v: number) => fmtInr(v, true)}
                  domain={['auto', 'auto']}
                />
                <Tooltip
                  contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                  labelStyle={{ color: '#94A3B8', marginBottom: 4 }}
                  formatter={(value: number, name: string) => [
                    fmtInr(value),
                    name === 'portfolio' ? 'Your Portfolio' : benchmark,
                  ]}
                />
                <Area type="monotone" dataKey="benchmark" stroke="#64748B" fill="none" strokeWidth={2} strokeDasharray="5 5" connectNulls />
                <Area type="monotone" dataKey="portfolio" stroke="#10B981" fillOpacity={1} fill="url(#colorPort)" strokeWidth={3} connectNulls />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Box>
      </Paper>
    </Box>
  )
}
