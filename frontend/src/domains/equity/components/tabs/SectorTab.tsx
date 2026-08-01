import { useMemo } from 'react'
import { Box, Grid, Paper, Typography } from '@mui/material'
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import { useClearSessionOnMissing, useEquityAllocation } from '../../hooks/useEquityData'
import { CHART_COLORS, EquityTabError, EquityTabSkeleton, GLASS_PAPER } from './shared'

const TOOLTIP_STYLE = {
  borderRadius: '12px',
  background: '#0F172A',
  border: '1px solid rgba(255,255,255,0.1)',
} as const

export default function SectorTab() {
  const { data, isPending, isError, error } = useEquityAllocation()
  useClearSessionOnMissing(error)

  // Memoized: these slices fed straight into recharts as a fresh array identity on
  // every render, which defeats recharts' own re-render bailout. `by_sector` was also
  // read as `data.by_sector` behind only an `if (!data)` guard, so a partial response
  // threw a TypeError inside render.
  const sectors = useMemo(() => data?.by_sector ?? [], [data])
  const topSectors = useMemo(() => sectors.slice(0, 10), [sectors])
  const topIndustries = useMemo(() => (data?.by_industry ?? []).slice(0, 8), [data])

  if (isPending) return <EquityTabSkeleton rows={6} />
  if (isError) return <EquityTabError error={error} label="sector allocation" />

  if (sectors.length === 0) {
    return (
      <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4, textAlign: 'center' }}>
        <Typography sx={{ color: '#94A3B8' }}>No allocation data for this portfolio.</Typography>
      </Paper>
    )
  }

  return (
    <Box>
      <Grid container spacing={4}>
        <Grid item xs={12} lg={6}>
          <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4 }}>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Sector Allocation</Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', height: 400 }}>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={sectors}
                    cx="50%" cy="50%"
                    innerRadius={90} outerRadius={120}
                    paddingAngle={2}
                    dataKey="value"
                  >
                    {sectors.map((s, i) => (
                      // Keyed on the label, not the array index, so cell identity stays
                      // stable when the ordering changes.
                      <Cell key={s.label ?? `slice-${i}`} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: number) => fmtInr(v)} contentStyle={TOOLTIP_STYLE} />
                </PieChart>
              </ResponsiveContainer>
            </Box>
            <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mt: 2 }}>
              {topSectors.map((s, i) => (
                <Box key={s.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Box sx={{ width: 12, height: 12, borderRadius: '4px', background: CHART_COLORS[i % CHART_COLORS.length] }} />
                    <Typography sx={{ color: '#CBD5E1', fontSize: '0.85rem' }}>{s.label}</Typography>
                  </Box>
                  <Typography sx={{ fontWeight: 700, color: '#F8FAFC', fontSize: '0.85rem' }}>
                    {fmtNum(s.pct, 2)}%
                  </Typography>
                </Box>
              ))}
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} lg={6}>
          <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4, height: '100%' }}>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Top Industries</Typography>
            <Box sx={{ height: 400 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={topIndustries} layout="vertical" margin={{ left: 50, right: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                  <XAxis
                    type="number"
                    tickFormatter={(v) => fmtInr(v, true)}
                    stroke="#64748B"
                    fontSize={12}
                  />
                  <YAxis type="category" dataKey="industry" stroke="#64748B" fontSize={12} width={120} />
                  <Tooltip
                    cursor={{ fill: 'rgba(255,255,255,0.05)' }}
                    formatter={(v: number) => fmtInr(v)}
                    contentStyle={TOOLTIP_STYLE}
                  />
                  <Bar dataKey="value" fill="#8B5CF6" radius={[0, 4, 4, 0]} barSize={24} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
