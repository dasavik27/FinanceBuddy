import { useState, useEffect } from 'react'
import { Box, Typography, Paper, CircularProgress, Alert, ToggleButton, ToggleButtonGroup } from '@mui/material'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { apiClient } from '../../../../shared/api/client'
import { useEquitySessionId } from '../../../../shared/store/appStore'

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)
}

export default function PerformanceTab() {
  const sessionId = useEquitySessionId()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [period, setPeriod] = useState('1Y')
  const [benchmark, setBenchmark] = useState('Nifty 50')

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    apiClient.getEquityPerformance(sessionId, { period, benchmark })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionId, period, benchmark])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>
  if (!data) return <Alert severity="error">Failed to load performance data</Alert>

  const chartData = data.dates?.map((d: string, i: number) => ({
    date: d,
    portfolio: data.portfolio[i],
    benchmark: data.benchmark[i],
  })) || []

  return (
    <Box>
      <Paper className="glass" sx={{ p: { xs: 2, md: 4 }, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <Box sx={{ display: 'flex', flexDirection: { xs: 'column', md: 'row' }, justifyContent: 'space-between', alignItems: { xs: 'flex-start', md: 'center' }, mb: 4, gap: 2 }}>
          <Box>
            <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 0.5 }}>Portfolio Performance</Typography>
            <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem' }}>Mark-to-market comparison against {benchmark}</Typography>
          </Box>
          <ToggleButtonGroup
            value={period}
            exclusive
            onChange={(_, v) => v && setPeriod(v)}
            size="small"
            sx={{
              background: 'rgba(255,255,255,0.03)', p: 0.5, borderRadius: '12px',
              '& .MuiToggleButton-root': {
                border: 'none', borderRadius: '8px !important', color: '#64748B', fontWeight: 600, px: 2, textTransform: 'none',
                '&.Mui-selected': { background: 'rgba(16,185,129,0.15)', color: '#10B981' }
              }
            }}
          >
            {['1M', '3M', '6M', '1Y', '3Y'].map(p => (
              <ToggleButton key={p} value={p}>{p}</ToggleButton>
            ))}
          </ToggleButtonGroup>
        </Box>

        <Box sx={{ height: 400, width: '100%' }}>
            {chartData.length === 0 ? (
                <Box sx={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Typography sx={{ color: '#64748B' }}>Not enough historical data.</Typography>
                </Box>
            ) : (
                <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                            <linearGradient id="colorPort" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#10B981" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="#10B981" stopOpacity={0}/>
                            </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                        <XAxis 
                            dataKey="date" 
                            stroke="#64748B" 
                            fontSize={12} 
                            tickFormatter={(v) => {
                                const d = new Date(v);
                                return `${d.getDate()} ${d.toLocaleString('default', { month: 'short' })}`;
                            }}
                            minTickGap={30}
                        />
                        <YAxis 
                            stroke="#64748B" 
                            fontSize={12}
                            tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`}
                            domain={['auto', 'auto']}
                        />
                        <Tooltip 
                            contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }}
                            labelStyle={{ color: '#94A3B8', marginBottom: 4 }}
                            formatter={(value: number, name: string) => [fmtINR(value), name === 'portfolio' ? 'Your Portfolio' : benchmark]}
                        />
                        <Area type="monotone" dataKey="benchmark" stroke="#64748B" fill="none" strokeWidth={2} strokeDasharray="5 5" />
                        <Area type="monotone" dataKey="portfolio" stroke="#10B981" fillOpacity={1} fill="url(#colorPort)" strokeWidth={3} />
                    </AreaChart>
                </ResponsiveContainer>
            )}
        </Box>
      </Paper>
    </Box>
  )
}
