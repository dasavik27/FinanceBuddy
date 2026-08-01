import { useState, useEffect } from 'react'
import { Box, Typography, Grid, Paper, CircularProgress, Alert } from '@mui/material'
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts'
import { apiClient } from '../../../../shared/api/client'
import { useEquitySessionId } from '../../../../shared/store/appStore'

const COLORS = ['#10B981', '#3B82F6', '#8B5CF6', '#F59E0B', '#EC4899', '#06B6D4', '#EAB308', '#14B8A6', '#6366F1', '#F43F5E']

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)
}

export default function SectorTab() {
  const sessionId = useEquitySessionId()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!sessionId) return
    apiClient.getEquityAllocation(sessionId)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>
  if (!data) return <Alert severity="error">Failed to load allocation data</Alert>

  return (
    <Box>
      <Grid container spacing={4}>
        <Grid item xs={12} lg={6}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
             <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Sector Allocation</Typography>
             <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', height: 400 }}>
                <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                        <Pie
                            data={data.by_sector}
                            cx="50%" cy="50%"
                            innerRadius={90} outerRadius={120}
                            paddingAngle={2}
                            dataKey="value"
                        >
                            {data.by_sector.map((e: any, i: number) => (
                                <Cell key={`cell-${i}`} fill={COLORS[i % COLORS.length]} />
                            ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => fmtINR(v)} contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }} />
                    </PieChart>
                </ResponsiveContainer>
             </Box>
             <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mt: 2 }}>
                  {data.by_sector.slice(0, 10).map((s: any, i: number) => (
                      <Box key={s.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Box sx={{ width: 12, height: 12, borderRadius: '4px', background: COLORS[i % COLORS.length] }} />
                              <Typography sx={{ color: '#CBD5E1', fontSize: '0.85rem' }}>{s.label}</Typography>
                          </Box>
                          <Typography sx={{ fontWeight: 700, color: '#F8FAFC', fontSize: '0.85rem' }}>{s.pct}%</Typography>
                      </Box>
                  ))}
             </Box>
          </Paper>
        </Grid>

        <Grid item xs={12} lg={6}>
          <Paper className="glass" sx={{ p: 4, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)', height: '100%' }}>
             <Typography sx={{ fontWeight: 800, color: '#F8FAFC', mb: 3 }}>Top Industries</Typography>
             <Box sx={{ height: 400 }}>
                 <ResponsiveContainer width="100%" height="100%">
                     <BarChart data={data.by_industry.slice(0, 8)} layout="vertical" margin={{ left: 50, right: 20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" horizontal={false} />
                        <XAxis type="number" tickFormatter={(v) => `₹${(v/1000).toFixed(0)}k`} stroke="#64748B" fontSize={12} />
                        <YAxis type="category" dataKey="industry" stroke="#64748B" fontSize={12} width={120} />
                        <Tooltip cursor={{ fill: 'rgba(255,255,255,0.05)' }} formatter={(v: number) => fmtINR(v)} contentStyle={{ borderRadius: '12px', background: '#0F172A', border: '1px solid rgba(255,255,255,0.1)' }} />
                        <Bar dataKey="value" fill="#8B5CF6" radius={[0, 4, 4, 0]} barSize={24} />
                     </BarChart>
                 </ResponsiveContainer>
             </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  )
}
