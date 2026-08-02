import { Alert, Box, Chip, Divider, Grid, Paper, Tooltip, Typography } from '@mui/material'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'

import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import { useClearSessionOnMissing, useEquityPnl } from '../../hooks/useEquityData'
import type { GainLossRow } from '../../types'
import { EquityTabError, EquityTabSkeleton, GLASS_PAPER, IconPanel } from './shared'

interface TopMoversProps {
  title: string
  items?: GainLossRow[]
  isPositive: boolean
}

function TopMovers({ title, items, isPositive }: TopMoversProps) {
  const color = isPositive ? '#10B981' : '#EF4444'
  const Icon = isPositive ? TrendingUpIcon : TrendingDownIcon
  const rows = items ?? []

  return (
    <IconPanel title={title} icon={Icon} color={color} dense>
      {rows.length === 0 ? (
        <Typography sx={{ color: '#64748B', fontSize: '0.9rem' }}>No data available.</Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {rows.map((item) => (
            <Box key={item.symbol} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography sx={{ fontWeight: 700, color: '#E2E8F0' }}>{item.symbol}</Typography>
              <Box sx={{ textAlign: 'right' }}>
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '0.95rem' }}>
                  {fmtInr(item.unrealized_pnl)}
                </Typography>
                <Typography sx={{ color, fontSize: '0.8rem', fontWeight: 700 }}>
                  {isPositive ? '+' : ''}{fmtNum(item.pnl_pct, 2)}%
                </Typography>
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </IconPanel>
  )
}

export default function PLTab() {
  const { data, isPending, isError, error } = useEquityPnl()
  useClearSessionOnMissing(error)

  if (isPending) return <EquityTabSkeleton rows={6} />
  if (isError) return <EquityTabError error={error} label="P&L" />

  const netPnl = data?.unrealized_pnl ?? 0
  const hasTradebook = data?.has_tradebook ?? false
  const fy = data?.financial_year
  const byYear = data?.realised_by_year ?? {}
  const priorYears = Object.entries(byYear)
    .filter(([year]) => year !== fy)
    .sort(([a], [b]) => b.localeCompare(a))
  const unmatched = data?.unmatched_sell_qty ?? 0

  return (
    <Box>
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4 }}>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Unrealized P&L Summary</Typography>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography sx={{ color: '#94A3B8' }}>Total Gainers ({data?.total_gainers ?? 0})</Typography>
              <Typography sx={{ color: '#10B981', fontWeight: 700 }}>+{fmtInr(data?.gainers_value)}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography sx={{ color: '#94A3B8' }}>Total Losers ({data?.total_losers ?? 0})</Typography>
              <Typography sx={{ color: '#EF4444', fontWeight: 700 }}>{fmtInr(data?.losers_value)}</Typography>
            </Box>
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)', mb: 2 }} />
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography sx={{ color: '#F8FAFC', fontWeight: 800 }}>Net Unrealized P&L</Typography>
              <Typography sx={{ color: netPnl >= 0 ? '#10B981' : '#EF4444', fontWeight: 800, fontSize: '1.2rem' }}>
                {netPnl >= 0 ? '+' : ''}{fmtInr(netPnl)}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
              <Typography sx={{ fontWeight: 800, color: '#F8FAFC' }}>Estimated Tax Liability</Typography>
              {!hasTradebook && (
                <Chip label="Requires Tradebook" size="small" sx={{ background: 'rgba(245,158,11,0.15)', color: '#F59E0B' }} />
              )}
            </Box>

            {/* The financial year is now stated. These figures are realised gains for
                *one* year, because capital gains are assessed per year and the LTCG
                exemption is an annual allowance. They used to be the sum of every year
                in the tradebook with one exemption applied to the total. */}
            {fy && (
              <Typography sx={{ color: '#64748B', fontSize: '0.8rem', mb: 3 }}>
                Realised in FY {fy}
              </Typography>
            )}

            <Box sx={{ opacity: hasTradebook ? 1 : 0.5 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography sx={{ color: '#94A3B8' }}>STCG (20%)</Typography>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography sx={{ color: '#F8FAFC', fontWeight: 700 }}>{fmtInr(data?.stcg_estimate)}</Typography>
                  <Typography sx={{ color: '#EF4444', fontSize: '0.75rem' }}>
                    Tax: {fmtInr(data?.stcg_tax_estimate)}
                  </Typography>
                </Box>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography sx={{ color: '#94A3B8' }}>LTCG (12.5% over ₹1.25L)</Typography>
                <Box sx={{ textAlign: 'right' }}>
                  <Typography sx={{ color: '#F8FAFC', fontWeight: 700 }}>{fmtInr(data?.ltcg_estimate)}</Typography>
                  <Typography sx={{ color: '#EF4444', fontSize: '0.75rem' }}>
                    Tax: {fmtInr(data?.ltcg_tax_estimate)}
                  </Typography>
                </Box>
              </Box>

              {priorYears.length > 0 && (
                <>
                  <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)', my: 2 }} />
                  <Typography sx={{ color: '#64748B', fontSize: '0.75rem', mb: 1 }}>
                    Earlier years (already assessed)
                  </Typography>
                  {priorYears.map(([year, bucket]) => (
                    <Box key={year} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography sx={{ color: '#94A3B8', fontSize: '0.8rem' }}>FY {year}</Typography>
                      <Typography sx={{ color: '#CBD5E1', fontSize: '0.8rem' }}>
                        STCG {fmtInr(bucket.stcg)} · LTCG {fmtInr(bucket.ltcg)}
                      </Typography>
                    </Box>
                  ))}
                </>
              )}
            </Box>

            {/* Sells with no matching buy lot used to be dropped silently, understating
                gains with no hint that anything was missing. */}
            {unmatched > 0 && (
              <Tooltip title="Your tradebook does not include the original purchase for some shares you sold, so those gains are not counted. Export a tradebook covering the full holding period for an accurate figure.">
                <Alert severity="warning" sx={{ mt: 3, borderRadius: '12px', background: 'rgba(245,158,11,0.1)', color: '#F59E0B' }}>
                  {fmtNum(unmatched, 0)} shares sold without a matching purchase in this tradebook.
                </Alert>
              </Tooltip>
            )}
          </Paper>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <TopMovers title="Top Gainers" items={data?.top_gainers} isPositive />
        </Grid>
        <Grid item xs={12} md={6}>
          <TopMovers title="Top Losers" items={data?.top_losers} isPositive={false} />
        </Grid>
      </Grid>
    </Box>
  )
}
