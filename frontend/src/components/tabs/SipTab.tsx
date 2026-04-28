import { useState } from 'react'
import {
  Box, Grid, Paper, Typography, Slider, TextField,
  InputAdornment, Alert,
} from '@mui/material'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { SectionHeader, MetricCard } from '../ui'
import { fmtInr } from '../../api/fmt'

export default function SipTab() {
  const [monthlySip,   setMonthlySip]   = useState(10000)
  const [years,        setYears]        = useState(10)
  const [annualReturn, setAnnualReturn] = useState(12)
  const [stepupPct,    setStepupPct]    = useState(10)

  const { data, isLoading } = useQuery({
    queryKey:  ['sipProjection', monthlySip, years, annualReturn, stepupPct],
    queryFn:   () => apiClient.sipProjection({
      monthly_sip:   monthlySip,
      years,
      annual_return: annualReturn,
      stepup_pct:    stepupPct,
    }),
    staleTime: 60_000,
  })

  // Build year-by-year chart data
  const chartData = Array.from({ length: years }, (_, i) => {
    const yr = i + 1
    const r  = annualReturn / 100 / 12
    // flat
    const flatInv = monthlySip * 12 * yr
    const flatFV  = monthlySip * ((Math.pow(1 + r, yr * 12) - 1) / r) * (1 + r)
    // stepup
    let stepFV = 0; let stepInv = 0; let sip = monthlySip
    for (let y = 0; y < yr; y++) {
      stepInv += sip * 12
      stepFV   = (stepFV + sip * 12) * (1 + annualReturn / 100)
      sip     *= (1 + stepupPct / 100)
    }
    return {
      year:       `Y${yr}`,
      'Flat SIP':   Math.round(flatFV / 1000),
      'Step-Up SIP':Math.round(stepFV / 1000),
      'Invested (Flat)': Math.round(flatInv / 1000),
    }
  })

  return (
    <Box>
      <SectionHeader title="SIP Calculator" subtitle="Compare flat vs step-up SIP — see the power of annual increment" />

      <Grid container spacing={3}>
        {/* ── Controls ──────────────────────────────────────────────── */}
        <Grid item xs={12} md={4}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
            <Typography variant="h6" sx={{ mb: 3 }}>Inputs</Typography>

            {/* Monthly SIP */}
            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>Monthly SIP</Typography>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#1D4ED8' }}>
                  {fmtInr(monthlySip)}
                </Typography>
              </Box>
              <Slider
                value={monthlySip}
                onChange={(_, v) => setMonthlySip(v as number)}
                min={500} max={100000} step={500}
                sx={{ color: '#1D4ED8' }}
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">₹500</Typography>
                <Typography variant="caption" color="text.secondary">₹1L</Typography>
              </Box>
            </Box>

            {/* Years */}
            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>Investment Period</Typography>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#1D4ED8' }}>
                  {years} years
                </Typography>
              </Box>
              <Slider value={years} onChange={(_, v) => setYears(v as number)} min={1} max={30} step={1} sx={{ color: '#1D4ED8' }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">1Y</Typography>
                <Typography variant="caption" color="text.secondary">30Y</Typography>
              </Box>
            </Box>

            {/* Expected Return */}
            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>Expected Annual Return</Typography>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#059669' }}>
                  {annualReturn}%
                </Typography>
              </Box>
              <Slider value={annualReturn} onChange={(_, v) => setAnnualReturn(v as number)} min={4} max={25} step={0.5} sx={{ color: '#059669' }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">4%</Typography>
                <Typography variant="caption" color="text.secondary">25%</Typography>
              </Box>
            </Box>

            {/* Step-Up */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>Annual Step-Up</Typography>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#7C3AED' }}>
                  {stepupPct}%
                </Typography>
              </Box>
              <Slider value={stepupPct} onChange={(_, v) => setStepupPct(v as number)} min={0} max={30} step={1} sx={{ color: '#7C3AED' }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">0%</Typography>
                <Typography variant="caption" color="text.secondary">30%</Typography>
              </Box>
            </Box>

            <Alert severity="info" sx={{ fontSize: 11 }}>
              Step-Up SIP increases your monthly contribution by {stepupPct}% every year — matching your salary increments.
            </Alert>
          </Paper>
        </Grid>

        {/* ── Results ───────────────────────────────────────────────── */}
        <Grid item xs={12} md={8}>
          {/* KPI comparison */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {[
              { label: 'Flat SIP — Final Value',    value: fmtInr(data?.flat_fv, true),    sub: `Invested ${fmtInr(data?.flat_inv, true)} · Gain ${fmtInr(data?.flat_gain, true)}`,    accent: 'info' as const },
              { label: 'Step-Up SIP — Final Value', value: fmtInr(data?.stepup_fv, true),  sub: `Invested ${fmtInr(data?.stepup_inv, true)} · Gain ${fmtInr(data?.stepup_gain, true)}`, accent: 'success' as const },
            ].map((card) => (
              <Grid item xs={12} sm={6} key={card.label}>
                <MetricCard {...card} loading={isLoading} />
              </Grid>
            ))}
          </Grid>

          {/* Extra wealth banner */}
          {data && (
            <Paper sx={{
              p: 2.5, mb: 3, borderRadius: 3,
              background: 'linear-gradient(135deg, #1D4ED8 0%, #6D28D9 100%)',
              color: '#fff',
            }}>
              <Typography sx={{ fontSize: 12, fontWeight: 600, opacity: 0.8, mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Extra Wealth from Step-Up
              </Typography>
              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '1.8rem', fontWeight: 500, letterSpacing: '-0.5px' }}>
                {fmtInr(data.extra_wealth, true)}
              </Typography>
              <Typography sx={{ fontSize: 12, opacity: 0.7, mt: 0.5 }}>
                By increasing your SIP by {stepupPct}% each year, you generate {fmtInr(data.extra_wealth, true)} more over {years} years.
              </Typography>
            </Paper>
          )}

          {/* Chart */}
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Growth Projection (₹ Thousands)</Typography>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="flatGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#1D4ED8" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#1D4ED8" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="stepGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#059669" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#059669" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="year" tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} tickFormatter={(v) => `₹${v}K`} />
                <Tooltip
                  formatter={(v: any, name: string) => [`₹${Number(v).toLocaleString('en-IN')}K`, name]}
                  contentStyle={{ borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
                <Area type="monotone" dataKey="Flat SIP"    stroke="#1D4ED8" strokeWidth={2} fill="url(#flatGrad)" dot={false} />
                <Area type="monotone" dataKey="Step-Up SIP" stroke="#059669" strokeWidth={2.5} fill="url(#stepGrad)" dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
