import { useState, useEffect } from 'react'
import { Box, Typography, Grid, Paper, CircularProgress, Alert, Chip, Divider } from '@mui/material'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import { apiClient } from '../../../../shared/api/client'
import { useEquitySessionId } from '../../../../shared/store/appStore'

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)
}

function TopMovers({ title, items, isPositive }: any) {
  const color = isPositive ? '#10B981' : '#EF4444'
  const Icon = isPositive ? TrendingUpIcon : TrendingDownIcon

  return (
    <Paper className="glass" sx={{ p: 3, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)', height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
        <Box sx={{ width: 36, height: 36, borderRadius: '10px', background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon sx={{ color, fontSize: 20 }} />
        </Box>
        <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1.1rem' }}>{title}</Typography>
      </Box>
      
      {items?.length === 0 ? (
        <Typography sx={{ color: '#64748B', fontSize: '0.9rem' }}>No data available.</Typography>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {items?.map((item: any) => (
            <Box key={item.symbol} sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography sx={{ fontWeight: 700, color: '#E2E8F0' }}>{item.symbol}</Typography>
              <Box sx={{ textAlign: 'right' }}>
                <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '0.95rem' }}>{fmtINR(item.unrealized_pnl)}</Typography>
                <Typography sx={{ color, fontSize: '0.8rem', fontWeight: 700 }}>{isPositive ? '+' : ''}{item.pnl_pct}%</Typography>
              </Box>
            </Box>
          ))}
        </Box>
      )}
    </Paper>
  )
}

export default function PLTab() {
  const sessionId = useEquitySessionId()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!sessionId) return
    apiClient.getEquityPnl(sessionId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>
  if (!data) return <Alert severity="error">Failed to load P&L data</Alert>

  return (
    <Box>
      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={6}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Unrealized P&L Summary</Typography>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography sx={{ color: '#94A3B8' }}>Total Gainers ({data.total_gainers})</Typography>
              <Typography sx={{ color: '#10B981', fontWeight: 700 }}>+{fmtINR(data.gainers_value)}</Typography>
            </Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography sx={{ color: '#94A3B8' }}>Total Losers ({data.total_losers})</Typography>
              <Typography sx={{ color: '#EF4444', fontWeight: 700 }}>{fmtINR(data.losers_value)}</Typography>
            </Box>
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.1)', mb: 2 }} />
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Typography sx={{ color: '#F8FAFC', fontWeight: 800 }}>Net Unrealized P&L</Typography>
              <Typography sx={{ color: data.unrealized_pnl >= 0 ? '#10B981' : '#EF4444', fontWeight: 800, fontSize: '1.2rem' }}>
                {data.unrealized_pnl >= 0 ? '+' : ''}{fmtINR(data.unrealized_pnl)}
              </Typography>
            </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} md={6}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography sx={{ fontWeight: 800, color: '#F8FAFC' }}>Estimated Tax Liability</Typography>
              {!data.has_tradebook && (
                <Chip label="Requires Tradebook CSV" size="small" sx={{ background: 'rgba(245,158,11,0.15)', color: '#F59E0B' }} />
              )}
            </Box>
            
            <Box sx={{ opacity: data.has_tradebook ? 1 : 0.5 }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                  <Typography sx={{ color: '#94A3B8' }}>STCG (20%)</Typography>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography sx={{ color: '#F8FAFC', fontWeight: 700 }}>{fmtINR(data.stcg_estimate)}</Typography>
                    <Typography sx={{ color: '#EF4444', fontSize: '0.75rem' }}>Tax: {fmtINR(data.stcg_tax_estimate)}</Typography>
                  </Box>
                </Box>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography sx={{ color: '#94A3B8' }}>LTCG (12.5% over ₹1.25L)</Typography>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography sx={{ color: '#F8FAFC', fontWeight: 700 }}>{fmtINR(data.ltcg_estimate)}</Typography>
                    <Typography sx={{ color: '#EF4444', fontSize: '0.75rem' }}>Tax: {fmtINR(data.ltcg_tax_estimate)}</Typography>
                  </Box>
                </Box>
            </Box>
          </Paper>
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        <Grid item xs={12} md={6}>
          <TopMovers title="Top Gainers" items={data.top_gainers} isPositive={true} />
        </Grid>
        <Grid item xs={12} md={6}>
          <TopMovers title="Top Losers" items={data.top_losers} isPositive={false} />
        </Grid>
      </Grid>
    </Box>
  )
}
