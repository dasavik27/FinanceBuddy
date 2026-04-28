import { useState, useMemo } from 'react'
import {
  Box, Grid, Paper, Typography, Slider, TextField,
  InputAdornment, Alert, ToggleButtonGroup, ToggleButton, Autocomplete, Divider,
} from '@mui/material'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { useHoldings } from '../../hooks/useData'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../../api/client'
import { SectionHeader, MetricCard } from '../ui'
import { fmtInr } from '../../api/fmt'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'

export default function SipTab() {
  const { data: holdingsData } = useHoldings()
  const [calcMode,     setCalcMode]     = useState<'SIP' | 'Lumpsum'>('SIP')
  const [selectedFund, setSelectedFund] = useState<any>(null)
  
  const [monthlySip,   setMonthlySip]   = useState(10000)
  const [lumpsumAmt,   setLumpsumAmt]   = useState(100000)
  const [years,        setYears]        = useState(10)
  const [annualReturn, setAnnualReturn] = useState(12)
  const [stepupPct,    setStepupPct]    = useState(10)
  const [extSearch,    setExtSearch]    = useState('')

  const { data: searchRes, isFetching: searching } = useQuery({
    queryKey:  ['tickerSearch', extSearch],
    queryFn:   () => apiClient.searchTicker(extSearch),
    enabled:   extSearch.length >= 3,
    staleTime: 30_000,
  })

  // Aggregate searchable items
  const liveOptions = useMemo(() => {
    return (searchRes?.results ?? []).map((o: any) => ({
      name: `${o.symbol} - ${o.name}`,
      type: 'Search Results',
      return1Y: 15.0,
    }))
  }, [searchRes])

  const handleFundChange = (fund: any) => {
    setSelectedFund(fund)
    if (fund) {
      setAnnualReturn(Math.min(30, Math.max(5, Math.round(fund.return1Y))))
    }
  }

  // Projection engine
  const chartData = useMemo(() => {
    return Array.from({ length: years }, (_, i) => {
      const yr = i + 1
      const r  = annualReturn / 100 / 12

      if (calcMode === 'SIP') {
        const flatInv = monthlySip * 12 * yr
        const flatFV  = monthlySip * ((Math.pow(1 + r, yr * 12) - 1) / r) * (1 + r)

        let stepFV = 0; let stepInv = 0; let sip = monthlySip
        for (let y = 0; y < yr; y++) {
          stepInv += sip * 12
          stepFV   = (stepFV + sip * 12) * (1 + annualReturn / 100)
          sip     *= (1 + stepupPct / 100)
        }
        return {
          year: `Yr ${yr}`,
          'Flat SIP Growth': Math.round(flatFV),
          'Step-Up Growth':  Math.round(stepFV),
          'Invested (Flat)': Math.round(flatInv),
          'Invested (Step-Up)': Math.round(stepInv),
        }
      } else {
        const flatInv = lumpsumAmt
        const flatFV  = lumpsumAmt * Math.pow(1 + annualReturn / 100, yr)
        return {
          year: `Yr ${yr}`,
          'Lumpsum Growth': Math.round(flatFV),
          'Invested': Math.round(flatInv),
        }
      }
    })
  }, [calcMode, monthlySip, lumpsumAmt, years, annualReturn, stepupPct])

  // Aggregate totals
  const totals = useMemo(() => {
    const last = chartData[chartData.length - 1] as any
    if (!last) return null
    if (calcMode === 'SIP') {
      return {
        flat_inv:    last['Invested (Flat)'],
        flat_fv:     last['Flat SIP Growth'],
        flat_gain:   last['Flat SIP Growth'] - last['Invested (Flat)'],
        stepup_inv:  last['Invested (Step-Up)'],
        stepup_fv:   last['Step-Up Growth'],
        stepup_gain: last['Step-Up Growth'] - last['Invested (Step-Up)'],
        extra_wealth:last['Step-Up Growth'] - last['Flat SIP Growth'],
      }
    } else {
      return {
        inv:  last['Invested'],
        fv:   last['Lumpsum Growth'],
        gain: last['Lumpsum Growth'] - last['Invested'],
      }
    }
  }, [chartData, calcMode])

  return (
    <Box>
      <SectionHeader 
        title="SIP & Lumpsum Calculator" 
        subtitle="Perform institutional goal simulations using your live positions or broad proxies" 
      />

      <Grid container spacing={3}>
        {/* ── Controls Panel ────────────────────────────────────────── */}
        <Grid item xs={12} md={4}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
            <Typography variant="h6" fontWeight={700} color="#1E3A8A" sx={{ mb: 2 }}>
              Simulation Setup
            </Typography>

            {/* Fund Selector */}
            <Box sx={{ mb: 3 }}>
              <Autocomplete
                size="small"
                options={liveOptions}
                groupBy={(o) => o.type}
                getOptionLabel={(o) => o.name}
                value={selectedFund}
                onChange={(_, v) => handleFundChange(v)}
                inputValue={extSearch}
                onInputChange={(_, v) => setExtSearch(v)}
                loading={searching}
                renderInput={(params) => (
                  <TextField 
                    {...params} 
                    label="Search Investment Asset" 
                    placeholder="Search Funds, Tickers, Indices…"
                  />
                )}
                sx={{ mb: 1.5 }}
              />
              {selectedFund && (
                <Alert severity="success" icon={<TrendingUpIcon fontSize="inherit" />} sx={{ fontSize: 11, py: 0 }}>
                  Using Proxy return of {annualReturn}% (1Y metric).
                </Alert>
              )}
            </Box>

            {/* Mode Toggle */}
            <ToggleButtonGroup
              color="primary"
              value={calcMode}
              exclusive
              onChange={(_, v) => v && setCalcMode(v)}
              fullWidth
              size="small"
              sx={{ mb: 3 }}
            >
              <ToggleButton value="SIP" sx={{ fontWeight: 600 }}>SIP Mode</ToggleButton>
              <ToggleButton value="Lumpsum" sx={{ fontWeight: 600 }}>Lumpsum Mode</ToggleButton>
            </ToggleButtonGroup>

            {/* Value Slider */}
            {calcMode === 'SIP' ? (
              <Box sx={{ mb: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Monthly SIP Amount</Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#1D4ED8' }}>
                    {fmtInr(monthlySip)}
                  </Typography>
                </Box>
                <Slider
                  value={monthlySip}
                  onChange={(_, v) => setMonthlySip(v as number)}
                  min={1000} max={200000} step={1000}
                  sx={{ color: '#1D4ED8' }}
                />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="caption" color="text.secondary">₹1k</Typography>
                  <Typography variant="caption" color="text.secondary">₹2L</Typography>
                </Box>
              </Box>
            ) : (
              <Box sx={{ mb: 3 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Lumpsum Amount</Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#1D4ED8' }}>
                    {fmtInr(lumpsumAmt)}
                  </Typography>
                </Box>
                <Slider
                  value={lumpsumAmt}
                  onChange={(_, v) => setLumpsumAmt(v as number)}
                  min={5000} max={10000000} step={5000}
                  sx={{ color: '#1D4ED8' }}
                />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="caption" color="text.secondary">₹5k</Typography>
                  <Typography variant="caption" color="text.secondary">₹1Cr</Typography>
                </Box>
              </Box>
            )}

            {/* Years Slider */}
            <Box sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>Horizon (Years)</Typography>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#0F172A' }}>
                  {years} years
                </Typography>
              </Box>
              <Slider 
                value={years} 
                onChange={(_, v) => setYears(v as number)} 
                min={1} max={40} step={1} 
                sx={{ color: '#0F172A' }} 
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">1Y</Typography>
                <Typography variant="caption" color="text.secondary">40Y</Typography>
              </Box>
            </Box>

            {/* Returns Slider */}
            <Box sx={{ mb: calcMode === 'SIP' ? 3 : 1 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="body2" fontWeight={600}>Expected Return (CAGR)</Typography>
                <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#059669' }}>
                  {annualReturn}%
                </Typography>
              </Box>
              <Slider 
                value={annualReturn} 
                onChange={(_, v) => setAnnualReturn(v as number)} 
                min={4} max={30} step={0.5} 
                sx={{ color: '#059669' }} 
              />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" color="text.secondary">4%</Typography>
                <Typography variant="caption" color="text.secondary">30%</Typography>
              </Box>
            </Box>

            {/* Step-Up Slider (Only in SIP mode) */}
            {calcMode === 'SIP' && (
              <Box sx={{ mb: 2 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                  <Typography variant="body2" fontWeight={600}>Annual Step-Up (%)</Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 13, fontWeight: 600, color: '#7C3AED' }}>
                    {stepupPct}%
                  </Typography>
                </Box>
                <Slider 
                  value={stepupPct} 
                  onChange={(_, v) => setStepupPct(v as number)} 
                  min={0} max={30} step={1} 
                  sx={{ color: '#7C3AED' }} 
                />
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="caption" color="text.secondary">0%</Typography>
                  <Typography variant="caption" color="text.secondary">30%</Typography>
                </Box>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* ── Visual Projections ────────────────────────────────────── */}
        <Grid item xs={12} md={8}>
          {calcMode === 'SIP' ? (
            <>
              {/* SIP KPIs */}
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid item xs={12} sm={6}>
                  <MetricCard 
                    label="Flat SIP — Final Value" 
                    value={fmtInr(totals?.flat_fv ?? 0, true)} 
                    sub={`Invested: ${fmtInr(totals?.flat_inv ?? 0, true)}`}
                    accent="info" 
                  />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <MetricCard 
                    label="Step-Up SIP — Final Value" 
                    value={fmtInr(totals?.stepup_fv ?? 0, true)} 
                    sub={`Invested: ${fmtInr(totals?.stepup_inv ?? 0, true)}`}
                    accent="success" 
                  />
                </Grid>
              </Grid>

              {totals && (totals as any).extra_wealth > 0 && (
                <Paper sx={{
                  p: 2.5, mb: 3, borderRadius: 3,
                  background: 'linear-gradient(135deg, #1D4ED8 0%, #6D28D9 100%)',
                  color: '#fff',
                }}>
                  <Typography sx={{ fontSize: 12, fontWeight: 600, opacity: 0.8, mb: 0.5, textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                    Wealth Optimization Advantage
                  </Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '1.8rem', fontWeight: 500 }}>
                    +{fmtInr((totals as any).extra_wealth, true)}
                  </Typography>
                  <Typography sx={{ fontSize: 12, opacity: 0.7, mt: 0.5 }}>
                    Stepping up contributions by {stepupPct}% every year adds tremendous compounding power.
                  </Typography>
                </Paper>
              )}
            </>
          ) : (
            /* Lumpsum KPIs */
            <Grid container spacing={2} sx={{ mb: 3 }}>
              <Grid item xs={12} sm={6}>
                <MetricCard 
                  label="Principal Deposited" 
                  value={fmtInr(totals?.inv ?? 0, true)} 
                  sub="One-time Investment"
                  accent="info" 
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <MetricCard 
                  label="Estimated Wealth" 
                  value={fmtInr(totals?.fv ?? 0, true)} 
                  sub={`Net Profit: ${fmtInr(totals?.gain ?? 0, true)}`}
                  accent="success" 
                />
              </Grid>
            </Grid>
          )}

          {/* Graphical output */}
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
            <Typography variant="h6" fontWeight={700} color="#334155" sx={{ mb: 2 }}>
              Compounding Projection Roadmap
            </Typography>
            <ResponsiveContainer width="100%" height={320}>
              <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="grad1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#1D4ED8" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#1D4ED8" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="grad2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#10B981" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#10B981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="year" tick={{ fontSize: 11, fill: '#64748B' }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#64748B' }} tickLine={false} axisLine={false} tickFormatter={(v) => `₹${(v/100000).toFixed(1)}L`} />
                <Tooltip
                  formatter={(v: any) => [`₹${Number(v).toLocaleString('en-IN')}`, '']}
                  contentStyle={{ borderRadius: 12, border: '1px solid #E2E8F0', fontSize: 13 }}
                />
                <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />

                {calcMode === 'SIP' ? (
                  <>
                    <Area type="monotone" dataKey="Flat SIP Growth" stroke="#1D4ED8" strokeWidth={2} fill="url(#grad1)" dot={false} />
                    <Area type="monotone" dataKey="Step-Up Growth"  stroke="#10B981" strokeWidth={2.5} fill="url(#grad2)" dot={false} />
                  </>
                ) : (
                  <>
                    <Area type="monotone" dataKey="Invested" stroke="#94A3B8" strokeWidth={2} fill="none" dot={false} />
                    <Area type="monotone" dataKey="Lumpsum Growth" stroke="#10B981" strokeWidth={2.5} fill="url(#grad2)" dot={false} />
                  </>
                )}
              </AreaChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
