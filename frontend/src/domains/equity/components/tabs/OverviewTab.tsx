import { useEffect, useState } from 'react'
import { Box, Typography, Grid, Paper, CircularProgress, Alert, Button, Chip } from '@mui/material'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import SyncIcon from '@mui/icons-material/Sync'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import { apiClient } from '../../../../shared/api/client'
import { useEquitySessionId } from '../../../../shared/store/appStore'

function StatCard({ title, value, sub, icon: Icon, color, loading }: any) {
  return (
    <Paper className="glass" sx={{ p: 3, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
        <Box sx={{ width: 40, height: 40, borderRadius: '12px', background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon sx={{ color, fontSize: 20 }} />
        </Box>
        <Typography sx={{ color: '#94A3B8', fontWeight: 600, fontSize: '0.9rem' }}>{title}</Typography>
      </Box>
      {loading ? (
        <CircularProgress size={24} sx={{ color }} />
      ) : (
        <>
          <Typography sx={{ fontWeight: 800, fontSize: '1.8rem', color: '#F8FAFC', mb: 0.5 }}>{value}</Typography>
          {sub && <Typography sx={{ color: sub.color || '#64748B', fontSize: '0.85rem', fontWeight: 600 }}>{sub.text}</Typography>}
        </>
      )}
    </Paper>
  )
}

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)
}

const COLORS = ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899', '#06B6D4']

export default function OverviewTab() {
  const sessionId = useEquitySessionId()
  const [summary, setSummary] = useState<any>(null)
  const [allocation, setAllocation] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const [sumRes, allocRes] = await Promise.all([
        apiClient.getEquitySummary(sessionId),
        apiClient.getEquityAllocation(sessionId)
      ])
      setSummary(sumRes)
      setAllocation(allocRes)
    } catch (e) {
      console.error(e)
      setError('Could not load overview data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [sessionId])

  const handleSync = async () => {
    if (!sessionId) return
    setSyncing(true)
    try {
      await apiClient.syncEquity(sessionId)
      await fetchData()
    } catch (e) {
      console.error(e)
    } finally {
      setSyncing(false)
    }
  }

  if (error) return <Alert severity="error">{error}</Alert>

  const isPositive = summary?.unrealized_pnl >= 0
  const pnlColor = isPositive ? '#10B981' : '#EF4444'

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
            '&:hover': { background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.2)' }
          }}
        >
          {syncing ? 'Syncing...' : 'Live Sync LTP'}
        </Button>
      </Box>

      <Grid container spacing={3} sx={{ mb: 4 }}>
        <Grid item xs={12} md={4}>
          <StatCard
            title="Total Market Value"
            value={summary ? fmtINR(summary.total_value) : ''}
            sub={{ text: `Invested: ${summary ? fmtINR(summary.total_invested) : ''}` }}
            icon={AccountBalanceWalletIcon}
            color="#3B82F6"
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <StatCard
            title="Unrealized P&L"
            value={summary ? `${isPositive ? '+' : ''}${fmtINR(summary.unrealized_pnl)}` : ''}
            sub={{ text: `${isPositive ? '+' : ''}${summary?.pnl_pct}% absolute return`, color: pnlColor }}
            icon={TrendingUpIcon}
            color={pnlColor}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} md={4}>
          <StatCard
            title="1D Change"
            value={summary ? `${summary.day_change >= 0 ? '+' : ''}${fmtINR(summary.day_change)}` : ''}
            sub={{ text: 'Based on today\'s trading session', color: summary?.day_change >= 0 ? '#10B981' : '#EF4444' }}
            icon={ShowChartIcon}
            color="#8B5CF6"
            loading={loading}
          />
        </Grid>
      </Grid>

      {/* Mini Allocation View */}
      <Grid container spacing={4}>
        <Grid item xs={12} lg={8}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
             <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Sector Exposure</Typography>
             {loading ? <CircularProgress /> : (
                 <Box sx={{ display: 'flex', alignItems: 'center', height: 250 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie
                                data={allocation?.by_sector.slice(0,6) || []}
                                cx="50%" cy="50%"
                                innerRadius={70} outerRadius={90}
                                paddingAngle={5}
                                dataKey="value"
                            >
                                {(allocation?.by_sector || []).slice(0,6).map((e: any, i: number) => (
                                    <Cell key={`cell-${i}`} fill={COLORS[i % COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip formatter={(v: number) => fmtINR(v)} contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }} />
                        </PieChart>
                    </ResponsiveContainer>
                    <Box sx={{ flex: 1 }}>
                        {(allocation?.by_sector || []).slice(0,5).map((s: any, i: number) => (
                            <Box key={s.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    <Box sx={{ width: 12, height: 12, borderRadius: '4px', background: COLORS[i] }} />
                                    <Typography sx={{ color: '#CBD5E1', fontSize: '0.9rem' }}>{s.label}</Typography>
                                </Box>
                                <Typography sx={{ fontWeight: 700, color: '#F8FAFC', fontSize: '0.9rem' }}>{s.pct}%</Typography>
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
