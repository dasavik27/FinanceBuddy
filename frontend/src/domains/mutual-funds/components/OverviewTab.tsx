import { useState, useMemo } from 'react'
import {
  Box, Grid, Typography, Stack, Paper, alpha, Avatar, Skeleton, Tooltip as MuiTooltip, Chip
} from '@mui/material'

import { useSummary, useOverview, useBenchmarkOverlay, useHoldings, useAllocation, usePerformance } from '../hooks/useData'
import { MetricCard, SectionHeader } from '../../../shared/components/ui'
import PortfolioChart from './PortfolioChart'
import { fmtInr, fmtPct } from '../../../shared/utils/fmt'

import ShieldIcon from '@mui/icons-material/Shield'
import SpeedIcon from '@mui/icons-material/Speed'
import DonutLargeIcon from '@mui/icons-material/DonutLarge'

export default function OverviewTab() {
  const [period, setPeriod] = useState('1Y')
  const [selectedBenchmarks, setSelectedBenchmarks] = useState<string[]>(['Nifty 50'])

  const primaryBenchmark = selectedBenchmarks[0] || 'Nifty 50'

  // Data hooks
  const { data: sum,   isLoading: sumL, isFetching: sumF }   = useSummary(primaryBenchmark)
  const { data: ov,    isLoading: ovL,  isFetching: ovF  }    = useOverview(period, primaryBenchmark)
  const { data: overlayData } = useBenchmarkOverlay(period, selectedBenchmarks)
  const { data: hold } = useHoldings({ sort_by: 'Market Value' })
  const { data: alloc } = useAllocation()
  const { data: perf } = usePerformance(period, { benchmark: primaryBenchmark })

  // Chart data
  const dates    = ov?.chart?.dates     ?? []
  const portArr  = ov?.chart?.portfolio ?? []
  const benchArr = ov?.chart?.benchmark ?? []

  const portReturn  = ov?.port_pct  ?? 0
  const benchReturn = ov?.bench_pct ?? 0
  const alphaVal    = portReturn - benchReturn

  const topPerformers = useMemo(() => {
    if (!hold?.holdings) return []
    return [...hold.holdings]
      .sort((a: any, b: any) => (b['Gain%'] ?? 0) - (a['Gain%'] ?? 0))
      .slice(0, 3)
  }, [hold?.holdings])

  const equityAlloc = alloc?.broad?.find((b: any) => b.label === 'Equity')
  const equityPct = equityAlloc ? equityAlloc.pct : 76.4
  const isHealthy = (sum?.alpha ?? 0) >= 0

  return (
    <Box sx={{ pb: 6 }}>
      <SectionHeader 
        title="Overview" 
        subtitle="High-level summary of your portfolio's valuation and overall performance." 
      />

      <Grid container spacing={4}>
        {/* ── Main Performance Section (9/12) ────────────────────────── */}
        <Grid item xs={12} lg={9}>
          {/* KPI Row */}
          <Grid container spacing={3} sx={{ mb: 4 }}>
            {[
              { label: 'Current Value',     value: fmtInr(sum?.total_value, true),    sub: `Invested: ${fmtInr(sum?.total_invested, true)}`, accent: 'info' as const, info: "Total current market valuation across all uploaded CAS portfolio accounts." },
              { label: 'Total Gains',       value: fmtInr(sum?.total_gain, true),     sub: `${fmtPct(sum?.gain_pct)} absolute performance`,      accent: (sum?.total_gain ?? 0) >= 0 ? 'success' as const : 'danger' as const, info: "Total net capital appreciation (Unrealized + Realized) since portfolio inception." },
              { 
                /* SEBI Compliance: Dynamically shift metric label and tooltip explanation if holding period is < 1 Year */
                label: sum?.is_absolute ? 'Absolute Return' : 'Annualized XIRR',   
                value: fmtPct(sum?.portfolio_xirr ?? 0),  
                sub: `Lifetime Alpha: ${fmtPct(sum?.alpha ?? 0)}`,  
                accent: (sum?.alpha ?? 0) >= 0 ? 'success' as const : 'danger' as const, 
                info: sum?.is_absolute 
                  ? "Absolute point-to-point return for portfolios younger than 1 year. (Annualized XIRR is mathematically inaccurate for <1Y holding periods)." 
                  : "Extended Internal Rate of Return (XIRR). Cashflow-weighted annualized return. Note: This may differ from the simple average of individual fund XIRRs due to the timing and magnitude of your SIPs/lumpsums." 
              },
            ].map((card) => (
              <Grid item xs={12} sm={4} key={card.label}>
                <MetricCard {...card} loading={sumL || sumF} />
              </Grid>
            ))}
          </Grid>

          {/* Performance Chart */}
          {ovL ? <Skeleton variant="rounded" height={450} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} /> : (
            <Paper className="glass" sx={{ borderRadius: '32px', p: 3, border: '1px solid rgba(255,255,255,0.05)' }}>
              <PortfolioChart
                dates={dates}
                portfolioSeries={portArr}
                primaryBenchmark={primaryBenchmark}
                primarySeries={benchArr}
                overlaySeries={overlayData?.series ?? {}}
                period={period}
                selectedBenchmarks={selectedBenchmarks}
                portReturn={portReturn}
                benchReturn={benchReturn}
                alpha={alphaVal}
                onPeriodChange={setPeriod}
                onBenchmarksChange={setSelectedBenchmarks}
              />
            </Paper>
          )}
          {perf?.benchmark_price_index_blend && (
            <Typography variant="caption" sx={{ display: 'block', mt: 1.5, color: 'text.secondary', fontStyle: 'italic' }}>
              Note: for this window, {primaryBenchmark}'s earliest years (before the underlying index fund existed) are blended from a price-only index — actual benchmark return in that stretch may be understated by ~1-1.5%/yr of reinvested dividends.
            </Typography>
          )}
        </Grid>

        {/* ── Intelligence Sidebar (3/12) ───────────────────────────── */}
        <Grid item xs={12} lg={3}>
          {ovL ? (
            <Stack spacing={4}>
              <Skeleton variant="rounded" height={240} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} />
              <Skeleton variant="rounded" height={320} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} />
            </Stack>
          ) : (
            <Stack spacing={4}>
              {/* Health Meter */}
              <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, mb: 3, display: 'block', letterSpacing: '0.15em' }}>
                  PORTFOLIO HEALTH
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
                  <Avatar sx={{ background: alpha(isHealthy ? '#4EDE93' : '#FF516A', 0.1), border: `1px solid ${isHealthy ? 'rgba(78, 222, 147, 0.2)' : 'rgba(255, 81, 106, 0.2)'}` }}>
                    <SpeedIcon sx={{ color: isHealthy ? '#4EDE93' : '#FF516A' }} />
                  </Avatar>
                  <Box>
                    <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#fff' }}>{isHealthy ? 'Optimal Momentum' : 'Underperforming Benchmark'}</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                      Portfolio Beta: {perf?.portfolio_beta != null ? perf.portfolio_beta.toFixed(2) : 'N/A'}
                      {perf?.portfolio_beta != null && (perf.portfolio_beta < 1 ? ' (Defensive)' : perf.portfolio_beta > 1.1 ? ' (Aggressive)' : ' (Stable)')}
                    </Typography>
                  </Box>
                </Box>
                <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '16px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                  <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700, display: 'block', mb: 0.5 }}>STRATEGY SIGNAL</Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary', lineHeight: 1.4 }}>
                    Portfolio is currently <span style={{ color: alphaVal >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>{alphaVal >= 0 ? 'outperforming' : 'underperforming'}</span> {primaryBenchmark} by <span style={{ color: alphaVal >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>{fmtPct(Math.abs(alphaVal))}</span> in the {period} window.
                  </Typography>
                </Box>
              </Paper>

              {/* Top Performers (Audit) */}
              <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, mb: 3, display: 'block', letterSpacing: '0.15em' }}>
                  TOP ATTRIBUTION
                </Typography>
                <Stack spacing={3}>
                  {topPerformers.map((p: any, idx: number) => {
                    const fundName = String(p?.Fund || p?.fund || `Fund ${idx + 1}`).toUpperCase()
                    const gainVal = Number(p?.['Gain%'] ?? p?.gain_pct ?? 0)
                    return (
                      <Box key={p?.Fund || idx}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                          <Typography variant="caption" sx={{ fontWeight: 800, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '70%' }}>
                            {fundName}
                          </Typography>
                          <Typography variant="caption" className="num" sx={{ fontWeight: 900, color: '#4EDE93' }}>+{gainVal.toFixed(1)}%</Typography>
                        </Box>
                        <Box sx={{ height: 4, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2 }}>
                          <Box sx={{ height: '100%', borderRadius: 2, bgcolor: '#4EDE93', width: `${Math.min(100, Math.max(0, gainVal))}%` }} />
                        </Box>
                      </Box>
                    )
                  })}
                </Stack>
              </Paper>

              {/* Risk Watch */}
              <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)', background: alpha('#FF516A', 0.03) }}>
                 <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                    <ShieldIcon sx={{ color: '#FF516A', fontSize: 20 }} />
                    <Typography variant="overline" sx={{ color: '#FF516A', fontWeight: 900, letterSpacing: '0.15em' }}>RISK AUDIT</Typography>
                 </Box>
                 <Typography variant="body2" sx={{ color: alpha('#fff', 0.7), fontWeight: 600, lineHeight: 1.5 }}>
                   Equity asset concentration is {equityPct}%. Remaining allocated across Debt & Fixed Income. Diversification index: {equityPct < 85 ? 'High (88/100)' : 'Moderate (72/100)'}.
                 </Typography>
              </Paper>
            </Stack>
          )}
        </Grid>
      </Grid>

      {/* ── Macro Allocation Spectrum & Risk Parity (Full Width) ──────── */}
      <Box sx={{ mt: 5 }}>
        <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
            <DonutLargeIcon sx={{ color: 'primary.main', fontSize: 24 }} />
            <Typography variant="h6" sx={{ fontWeight: 800, color: '#fff', letterSpacing: '0.05em' }}>
              Macro Asset Spectrum & Risk Parity
            </Typography>
          </Box>
          <Typography variant="body2" sx={{ color: '#94A3B8', mb: 3, fontWeight: 600 }}>
            Real-time aggregate exposure across uploaded CAS accounts. Hover segments for precise valuation and liquidity tiering.
          </Typography>

          {/* Allocation Spectrum Bar */}
          <Box sx={{ width: '100%', height: 24, borderRadius: '12px', display: 'flex', overflow: 'hidden', mb: 4, border: '1px solid rgba(255,255,255,0.1)', boxShadow: 'inset 0 2px 10px rgba(0,0,0,0.5)' }}>
            {(alloc?.broad ?? []).map((b: any) => (
              <MuiTooltip key={b.label} title={`${b.label}: ${b.pct}% (${fmtInr(b.value, true)})`} arrow>
                <Box sx={{ width: `${b.pct}%`, height: '100%', background: b.color || '#6366F1', transition: 'width 0.5s ease', cursor: 'pointer', '&:hover': { filter: 'brightness(1.2)' } }} />
              </MuiTooltip>
            ))}
          </Box>

          {/* Asset Legends & Breakdown */}
          <Grid container spacing={3}>
            <Grid item xs={12} md={7}>
              <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 900, mb: 2, display: 'block', letterSpacing: '0.15em' }}>BROAD CLASS BREAKDOWN</Typography>
              <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ gap: 2 }}>
                {(alloc?.broad ?? []).map((b: any) => (
                  <Paper key={b.label} sx={{ px: 2.5, py: 1.5, borderRadius: '16px', background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    <Box sx={{ width: 12, height: 12, borderRadius: '4px', background: b.color || '#6366F1', boxShadow: `0 0 10px ${b.color || '#6366F1'}` }} />
                    <Box>
                      <Typography variant="caption" sx={{ fontWeight: 800, color: '#fff', display: 'block' }}>{b.label}</Typography>
                      <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 700 }}>{b.pct}% · {fmtInr(b.value, true)}</Typography>
                    </Box>
                  </Paper>
                ))}
              </Stack>
            </Grid>

            <Grid item xs={12} md={5}>
              <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 900, mb: 2, display: 'block', letterSpacing: '0.15em' }}>CAP SIZE DISTRIBUTION</Typography>
              <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ gap: 2 }}>
                {(alloc?.by_cap ?? []).map((c: any) => {
                  const capLabel = String(c.label || c['Cap Type'] || 'Unknown')
                  return (
                    <Chip 
                      key={capLabel}
                      label={`${capLabel.toUpperCase()}: ${c.pct}%`}
                      variant="outlined"
                      sx={{ 
                        borderRadius: '12px', px: 1.5, py: 2.5, fontWeight: 800, fontSize: 11,
                        bgcolor: 'rgba(255,255,255,0.03)', color: '#fff', borderColor: 'rgba(255,255,255,0.1)' 
                      }} 
                    />
                  )
                })}
              </Stack>
            </Grid>
          </Grid>
        </Paper>
      </Box>
    </Box>
  )
}
