import { useState, useEffect } from 'react'
import { Box, Typography, Grid, Paper, CircularProgress, Alert, LinearProgress, Chip } from '@mui/material'
import EmojiEventsIcon from '@mui/icons-material/EmojiEvents'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import AssuredWorkloadIcon from '@mui/icons-material/AssuredWorkload'
import ShieldIcon from '@mui/icons-material/Shield'
import { apiClient } from '../../../../shared/api/client'
import { useEquitySessionId } from '../../../../shared/store/appStore'

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)
}

function InsightCard({ title, icon: Icon, color, children }: any) {
  return (
    <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)', height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Box sx={{ width: 40, height: 40, borderRadius: '12px', background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon sx={{ color, fontSize: 24 }} />
        </Box>
        <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.2rem' }}>{title}</Typography>
      </Box>
      {children}
    </Paper>
  )
}

export default function InsightsTab() {
  const sessionId = useEquitySessionId()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!sessionId) return
    apiClient.getEquityInsights(sessionId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>
  if (!data) return <Alert severity="error">Failed to load insights</Alert>

  const score = data.diversification_score || 0
  let scoreColor = '#EF4444'
  if (score >= 80) scoreColor = '#10B981'
  else if (score >= 50) scoreColor = '#F59E0B'

  return (
    <Box>
      <Grid container spacing={4} sx={{ mb: 4 }}>
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(15,23,42,0.6) 100%)', border: '1px solid rgba(16,185,129,0.2)' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box>
                    <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.2rem', mb: 1 }}>Portfolio Diversification Score</Typography>
                    <Typography sx={{ color: '#94A3B8' }}>A measure of your portfolio's resilience against sector and concentration risks.</Typography>
                </Box>
                <Box sx={{ textAlign: 'center' }}>
                    <Typography sx={{ fontWeight: 900, fontSize: '3rem', color: scoreColor, lineHeight: 1 }}>{score}</Typography>
                    <Typography sx={{ color: '#64748B', fontWeight: 700 }}>/ 100</Typography>
                </Box>
            </Box>
            <LinearProgress variant="determinate" value={score} sx={{ mt: 3, height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.1)', '& .MuiLinearProgress-bar': { backgroundColor: scoreColor, borderRadius: 4 } }} />
          </Paper>
        </Grid>
      </Grid>

      <Grid container spacing={4}>
        <Grid item xs={12} md={6}>
            <InsightCard title="Concentration Risk" icon={WarningAmberIcon} color="#F59E0B">
                <Typography sx={{ color: '#94A3B8', mb: 3 }}>Positions making up more than 10% of your portfolio.</Typography>
                {data.concentrated_positions?.length === 0 ? (
                    <Alert severity="success" sx={{ background: 'rgba(16,185,129,0.1)', color: '#10B981', '& .MuiAlert-icon': { color: '#10B981' } }}>Your portfolio is well diversified across stocks.</Alert>
                ) : (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {data.concentrated_positions?.map((p: any) => (
                            <Box key={p.symbol} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, background: 'rgba(255,255,255,0.03)', borderRadius: '12px' }}>
                                <Box>
                                    <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{p.symbol}</Typography>
                                    <Typography sx={{ fontSize: '0.8rem', color: '#64748B' }}>{p.sector}</Typography>
                                </Box>
                                <Chip label={`${p.weight_pct.toFixed(1)}% Weight`} size="small" sx={{ background: 'rgba(245,158,11,0.2)', color: '#F59E0B', fontWeight: 700 }} />
                            </Box>
                        ))}
                    </Box>
                )}
            </InsightCard>
        </Grid>

        <Grid item xs={12} md={6}>
            <InsightCard title="Tax-Loss Harvesting" icon={AssuredWorkloadIcon} color="#3B82F6">
                <Typography sx={{ color: '#94A3B8', mb: 3 }}>Positions with significant unrealized losses that could be sold to offset capital gains.</Typography>
                {data.tax_loss_harvest?.length === 0 ? (
                    <Typography sx={{ color: '#64748B', p: 2, textAlign: 'center' }}>No significant losses to harvest right now.</Typography>
                ) : (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {data.tax_loss_harvest?.map((p: any) => (
                            <Box key={p.symbol} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', p: 2, background: 'rgba(255,255,255,0.03)', borderRadius: '12px' }}>
                                <Box>
                                    <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{p.symbol}</Typography>
                                    <Typography sx={{ fontSize: '0.8rem', color: '#EF4444' }}>{p.pnl_pct}% down</Typography>
                                </Box>
                                <Typography sx={{ fontWeight: 700, color: '#EF4444' }}>{fmtINR(p.unrealized_pnl)} loss</Typography>
                            </Box>
                        ))}
                    </Box>
                )}
            </InsightCard>
        </Grid>
      </Grid>
    </Box>
  )
}
