import { Alert, Box, Chip, Grid, LinearProgress, Paper, Typography } from '@mui/material'
import AssuredWorkloadIcon from '@mui/icons-material/AssuredWorkload'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import { useClearSessionOnMissing, useEquityInsights } from '../../hooks/useEquityData'
import { EquityTabError, EquityTabSkeleton, IconPanel } from './shared'

export default function InsightsTab() {
  const { data, isPending, isError, error } = useEquityInsights()
  useClearSessionOnMissing(error)

  if (isPending) return <EquityTabSkeleton rows={5} />
  if (isError) return <EquityTabError error={error} label="insights" />

  const score = data?.diversification_score ?? 0
  let scoreColor = '#EF4444'
  if (score >= 80) scoreColor = '#10B981'
  else if (score >= 50) scoreColor = '#F59E0B'

  const concentrated = data?.concentrated_positions ?? []
  const harvest = data?.tax_loss_harvest ?? []

  return (
    <Box>
      <Grid container spacing={4} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <Paper
            className="glass"
            sx={{
              p: 4,
              borderRadius: '24px',
              background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(15,23,42,0.6) 100%)',
              border: '1px solid rgba(16,185,129,0.2)',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Box>
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.2rem', mb: 1 }}>
                  Portfolio Diversification Score
                </Typography>
                <Typography sx={{ color: '#94A3B8' }}>
                  A measure of your portfolio's resilience against sector and concentration risks.
                </Typography>
              </Box>
              <Box sx={{ textAlign: 'center' }}>
                <Typography sx={{ fontWeight: 900, fontSize: '3rem', color: scoreColor, lineHeight: 1 }}>{score}</Typography>
                <Typography sx={{ color: '#64748B', fontWeight: 700 }}>/ 100</Typography>
              </Box>
            </Box>
            <LinearProgress
              variant="determinate"
              value={score}
              sx={{
                mt: 3, height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.1)',
                '& .MuiLinearProgress-bar': { backgroundColor: scoreColor, borderRadius: 4 },
              }}
            />
          </Paper>
        </Grid>
      </Grid>

      <Grid container spacing={4}>
        <Grid item xs={12} md={6}>
          <IconPanel title="Concentration Risk" icon={WarningAmberIcon} color="#F59E0B">
            <Typography sx={{ color: '#94A3B8', mb: 3 }}>
              Positions making up more than 10% of your portfolio.
            </Typography>
            {concentrated.length === 0 ? (
              <Alert
                severity="success"
                sx={{ background: 'rgba(16,185,129,0.1)', color: '#10B981', '& .MuiAlert-icon': { color: '#10B981' } }}
              >
                Your portfolio is well diversified across stocks.
              </Alert>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {concentrated.map((p) => (
                  <Box
                    key={p.symbol}
                    sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, background: 'rgba(255,255,255,0.03)', borderRadius: '12px' }}
                  >
                    <Box>
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{p.symbol}</Typography>
                      <Typography sx={{ fontSize: '0.8rem', color: '#64748B' }}>{p.sector}</Typography>
                    </Box>
                    {/* fmtNum, not p.weight_pct.toFixed(1) — the raw call threw on a null. */}
                    <Chip
                      label={`${fmtNum(p.weight_pct, 1)}% Weight`}
                      size="small"
                      sx={{ background: 'rgba(245,158,11,0.2)', color: '#F59E0B', fontWeight: 700 }}
                    />
                  </Box>
                ))}
              </Box>
            )}
          </IconPanel>
        </Grid>

        <Grid item xs={12} md={6}>
          <IconPanel title="Tax-Loss Harvesting" icon={AssuredWorkloadIcon} color="#3B82F6">
            <Typography sx={{ color: '#94A3B8', mb: 3 }}>
              Positions with significant unrealized losses that could be sold to offset capital gains.
            </Typography>
            {harvest.length === 0 ? (
              <Typography sx={{ color: '#64748B', p: 2, textAlign: 'center' }}>
                No significant losses to harvest right now.
              </Typography>
            ) : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                {harvest.map((p) => (
                  <Box
                    key={p.symbol}
                    sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, background: 'rgba(255,255,255,0.03)', borderRadius: '12px' }}
                  >
                    <Box>
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{p.symbol}</Typography>
                      <Typography sx={{ fontSize: '0.8rem', color: '#EF4444' }}>
                        {fmtNum(p.pnl_pct, 2)}% down
                      </Typography>
                    </Box>
                    <Typography sx={{ fontWeight: 700, color: '#EF4444' }}>
                      {fmtInr(p.unrealized_pnl)} loss
                    </Typography>
                  </Box>
                ))}
              </Box>
            )}
          </IconPanel>
        </Grid>
      </Grid>
    </Box>
  )
}
