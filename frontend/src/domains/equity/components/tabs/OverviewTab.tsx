import { useMemo, useState } from 'react'
import { Box, Button, CircularProgress, Grid, Paper, Typography } from '@mui/material'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import SyncIcon from '@mui/icons-material/Sync'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import { useQueryClient } from '@tanstack/react-query'

import { MetricCard } from '../../../../shared/components/ui'
import { apiClient } from '../../../../shared/api/client'
import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import {
  useClearSessionOnMissing, useEquityAllocation, useEquitySessionId, useEquitySummary,
} from '../../hooks/useEquityData'
import { CHART_COLORS, EquityTabError, GLASS_PAPER } from './shared'

const TOOLTIP_STYLE = {
  borderRadius: '12px',
  background: '#0F172A',
  border: '1px solid rgba(255,255,255,0.1)',
} as const

export default function OverviewTab() {
  const sessionId = useEquitySessionId()
  const queryClient = useQueryClient()
  const [syncing, setSyncing] = useState(false)

  const summaryQuery = useEquitySummary()
  const allocationQuery = useEquityAllocation()
  useClearSessionOnMissing(summaryQuery.error ?? allocationQuery.error)

  const summary = summaryQuery.data
  const loading = summaryQuery.isPending || allocationQuery.isPending

  // Computed once per data change rather than twice per render. `by_sector` was also
  // reached as `allocation?.by_sector.slice(...)` — the `?.` guarded `allocation` but
  // not `by_sector`, so a response missing the key threw inside render.
  const topSectors = useMemo(
    () => (allocationQuery.data?.by_sector ?? []).slice(0, 6),
    [allocationQuery.data],
  )
  const legendSectors = useMemo(() => topSectors.slice(0, 5), [topSectors])

  const handleSync = async () => {
    if (!sessionId) return
    setSyncing(true)
    try {
      await apiClient.syncEquity(sessionId)
      // Invalidate rather than refetching two endpoints by hand: a sync changes prices,
      // so every equity view is stale, not just the two this tab reads.
      await queryClient.invalidateQueries({ queryKey: ['equity'] })
    } catch (e) {
      console.error(e)
    } finally {
      setSyncing(false)
    }
  }

  if (summaryQuery.isError) return <EquityTabError error={summaryQuery.error} label="overview" />

  // Every read is optional-chained and formatted through the null-guarding helpers.
  // `summary ? fmtINR(summary.total_value) : ''` looked safe but the backend returns
  // `{}` for an empty portfolio — truthy — so it rendered "₹NaN", and the P&L subtitle
  // rendered the literal "+undefined% absolute return".
  const pnl = summary?.unrealized_pnl
  const isPositive = (pnl ?? 0) >= 0
  const pnlColor = isPositive ? '#10B981' : '#EF4444'
  const dayChange = summary?.day_change
  const dayPositive = (dayChange ?? 0) >= 0

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 800, color: '#F8FAFC' }}>Executive Summary</Typography>
        <Button
          variant="outlined" size="small"
          startIcon={<SyncIcon sx={{ animation: syncing ? 'spin 1s linear infinite' : 'none' }} />}
          onClick={handleSync}
          disabled={syncing || loading}
          sx={{
            borderColor: 'rgba(255,255,255,0.1)', color: '#CBD5E1', textTransform: 'none', borderRadius: '10px',
            '&:hover': { background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.2)' },
          }}
        >
          {syncing ? 'Syncing...' : 'Live Sync LTP'}
        </Button>
      </Box>

      {/* MetricCard from shared/components/ui, not a local StatCard. The fork differed
          only by having an icon, so the icon became an optional prop there instead. */}
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <MetricCard
            label="Total Market Value"
            value={fmtInr(summary?.total_value)}
            sub={`Invested: ${fmtInr(summary?.total_invested)}`}
            icon={AccountBalanceWalletIcon}
            accent="info"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <MetricCard
            label="Unrealized P&L"
            value={`${isPositive ? '+' : ''}${fmtInr(pnl)}`}
            sub={`${isPositive ? '+' : ''}${fmtNum(summary?.pnl_pct, 2)}% absolute return`}
            icon={TrendingUpIcon}
            accent={isPositive ? 'success' : 'danger'}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <MetricCard
            label="1D Change"
            value={`${dayPositive ? '+' : ''}${fmtInr(dayChange)}`}
            // Says so explicitly when the figure is unavailable. The backend reports 0
            // rather than a meaningless sum of per-share moves when prices could not be
            // refreshed, so "₹0" alone would be ambiguous.
            sub={dayChange ? "Based on today's trading session" : 'Live prices unavailable'}
            icon={ShowChartIcon}
            accent={dayChange ? (dayPositive ? 'success' : 'danger') : 'none'}
            loading={loading}
          />
        </Grid>
      </Grid>

      <Grid container spacing={4}>
        <Grid item xs={12} lg={8}>
          <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4 }}>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Sector Exposure</Typography>
            {loading ? (
              <CircularProgress />
            ) : topSectors.length === 0 ? (
              <Typography sx={{ color: '#64748B' }}>No sector data available.</Typography>
            ) : (
              <Box sx={{ display: 'flex', alignItems: 'center', height: 250 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={topSectors}
                      cx="50%" cy="50%"
                      innerRadius={70} outerRadius={90}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {topSectors.map((s, i) => (
                        <Cell key={s.label ?? `slice-${i}`} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => fmtInr(v)} contentStyle={TOOLTIP_STYLE} />
                  </PieChart>
                </ResponsiveContainer>
                <Box sx={{ flex: 1 }}>
                  {legendSectors.map((s, i) => (
                    <Box key={s.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 12, height: 12, borderRadius: '4px', background: CHART_COLORS[i % CHART_COLORS.length] }} />
                        <Typography sx={{ color: '#CBD5E1', fontSize: '0.9rem' }}>{s.label}</Typography>
                      </Box>
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC', fontSize: '0.9rem' }}>
                        {fmtNum(s.pct, 2)}%
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
