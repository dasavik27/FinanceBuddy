import { useState } from 'react'
import { Box, Typography, Paper, Grid, Stack, Skeleton, ToggleButton, ToggleButtonGroup, Chip, Avatar } from '@mui/material'
import { useJourney } from '../hooks/useData'
import { SectionHeader } from '../../../shared/components/ui'
import { fmtInr, fmtPct } from '../../../shared/utils/fmt'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Cell } from 'recharts'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'

export default function JourneyTab() {
  const { data, isLoading } = useJourney()
  const [flowView, setFlowView] = useState<'monthly' | 'yearly'>('yearly')

  const handleFlowViewChange = (event: React.MouseEvent<HTMLElement>, newView: 'monthly' | 'yearly' | null) => {
    if (newView !== null) setFlowView(newView)
  }

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <Paper sx={{ p: 2, bgcolor: '#0B1326', border: '1px solid rgba(255,255,255,0.1)', minWidth: 200, borderRadius: 2 }}>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, mb: 1, display: 'block' }}>{label}</Typography>
          {payload.map((entry: any, index: number) => (
            <Box key={index} sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
              <Typography variant="caption" sx={{ color: entry.color || '#fff', fontWeight: 600 }}>{entry.name}</Typography>
              <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(entry.value)}</Typography>
            </Box>
          ))}
        </Paper>
      )
    }
    return null
  }

  return (
    <Box sx={{ pb: 8, maxWidth: 1200, mx: 'auto' }}>
      <SectionHeader 
        title="Wealth Journey" 
        subtitle="Track your wealth accumulation and key financial milestones over time." 
      />

      {isLoading ? (
        <Stack spacing={4}>
          <Skeleton variant="rounded" height={400} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} />
          <Grid container spacing={4}>
            <Grid item xs={12} md={6}><Skeleton variant="rounded" height={300} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} /></Grid>
            <Grid item xs={12} md={6}><Skeleton variant="rounded" height={300} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} /></Grid>
          </Grid>
        </Stack>
      ) : (
        <Stack spacing={4}>
          
          {/* Capital Curve */}
          <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, mb: 3, display: 'block', letterSpacing: '0.15em' }}>
              CAPITAL ACCUMULATION CURVE
            </Typography>
            <Box sx={{ height: 350, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data?.capital_curve || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorInvested" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#14B8A6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#14B8A6" stopOpacity={0}/>
                    </linearGradient>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#A855F7" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#A855F7" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis 
                    dataKey="date" 
                    tickFormatter={(val) => val} 
                    stroke="rgba(255,255,255,0.2)" 
                    tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }}
                    minTickGap={30}
                  />
                  <YAxis 
                    stroke="rgba(255,255,255,0.2)" 
                    tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }} 
                    tickFormatter={(val) => '₹' + (val / 100000).toFixed(1) + 'L'}
                  />
                  <RechartsTooltip content={<CustomTooltip />} />
                  <Area 
                    type="monotone" 
                    dataKey="value" 
                    name="Market Value"
                    stroke="#A855F7" 
                    strokeWidth={3}
                    fillOpacity={1} 
                    fill="url(#colorValue)" 
                  />
                  <Area 
                    type="monotone" 
                    dataKey="invested" 
                    name="Capital Invested"
                    stroke="#14B8A6" 
                    strokeWidth={3}
                    fillOpacity={1} 
                    fill="url(#colorInvested)" 
                  />
                </AreaChart>
              </ResponsiveContainer>
            </Box>
          </Paper>

          {/* SIP / Flow Chart */}
          <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
              <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: '0.15em' }}>
                CAPITAL FLOW VELOCITY
              </Typography>
              <ToggleButtonGroup
                value={flowView}
                exclusive
                onChange={handleFlowViewChange}
                size="small"
                sx={{
                  bgcolor: 'rgba(255,255,255,0.03)',
                  p: 0.5,
                  borderRadius: '12px',
                  border: '1px solid rgba(255,255,255,0.05)',
                  '& .MuiToggleButton-root': { color: 'text.secondary', border: 'none', borderRadius: '8px !important', px: 3, py: 0.5, fontWeight: 700, textTransform: 'none' },
                  '& .Mui-selected': { bgcolor: 'primary.main', color: '#fff !important' }
                }}
              >
                <ToggleButton value="yearly">Yearly</ToggleButton>
                <ToggleButton value="monthly">Monthly</ToggleButton>
              </ToggleButtonGroup>
            </Box>
            
            <Box sx={{ height: 300, width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={flowView === 'yearly' ? data?.yearly_flows : data?.monthly_flows} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis 
                    dataKey="period" 
                    stroke="rgba(255,255,255,0.2)" 
                    tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }}
                    minTickGap={20}
                  />
                  <YAxis 
                    stroke="rgba(255,255,255,0.2)" 
                    tick={{ fill: 'rgba(255,255,255,0.5)', fontSize: 12, fontWeight: 600 }} 
                    tickFormatter={(val) => '₹' + (val / 1000).toFixed(0) + 'k'}
                  />
                  <RechartsTooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.02)' }} />
                  <Bar dataKey="invested" name="Deposited" fill="#14B8A6" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="withdrawn" name="Withdrawn" fill="#EF4444" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </Box>
          </Paper>

          {/* Hall of Fame / Shame */}
          <Grid container spacing={4}>
            {/* Best */}
            <Grid item xs={12} md={6}>
              <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)', height: '100%' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
                  <Avatar sx={{ bgcolor: 'rgba(78, 222, 147, 0.1)', color: '#4EDE93' }}>
                    <TrendingUpIcon />
                  </Avatar>
                  <Box>
                    <Typography variant="overline" sx={{ color: '#4EDE93', fontWeight: 900, display: 'block', letterSpacing: '0.15em', lineHeight: 1 }}>HALL OF FAME</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Highest generating assets</Typography>
                  </Box>
                </Box>
                
                <Stack spacing={2}>
                  {(data?.best_funds || []).map((f: any, i: number) => (
                    <Box key={i} sx={{ p: 2, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box sx={{ maxWidth: '65%' }}>
                        <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.fund}</Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Invested: {fmtInr(f.invested)}</Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="subtitle2" className="num" sx={{ color: '#4EDE93', fontWeight: 900 }}>+{f.gain_pct.toFixed(2)}%</Typography>
                        <Typography variant="caption" className="num" sx={{ color: '#4EDE93', fontWeight: 700 }}>+{fmtInr(f.gain_abs)}</Typography>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              </Paper>
            </Grid>

            {/* Worst */}
            <Grid item xs={12} md={6}>
              <Paper className="glass" sx={{ p: 4, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)', height: '100%' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 3 }}>
                  <Avatar sx={{ bgcolor: 'rgba(239, 68, 68, 0.1)', color: '#EF4444' }}>
                    <TrendingDownIcon />
                  </Avatar>
                  <Box>
                    <Typography variant="overline" sx={{ color: '#EF4444', fontWeight: 900, display: 'block', letterSpacing: '0.15em', lineHeight: 1 }}>HALL OF SHAME</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Lowest generating assets</Typography>
                  </Box>
                </Box>
                
                <Stack spacing={2}>
                  {(data?.worst_funds || []).map((f: any, i: number) => (
                    <Box key={i} sx={{ p: 2, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Box sx={{ maxWidth: '65%' }}>
                        <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{f.fund}</Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Invested: {fmtInr(f.invested)}</Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="subtitle2" className="num" sx={{ color: f.gain_pct < 0 ? '#EF4444' : '#EAB308', fontWeight: 900 }}>
                          {f.gain_pct > 0 ? '+' : ''}{f.gain_pct.toFixed(2)}%
                        </Typography>
                        <Typography variant="caption" className="num" sx={{ color: f.gain_pct < 0 ? '#EF4444' : '#EAB308', fontWeight: 700 }}>
                          {f.gain_abs > 0 ? '+' : ''}{fmtInr(f.gain_abs)}
                        </Typography>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </Stack>
      )}
    </Box>
  )
}
