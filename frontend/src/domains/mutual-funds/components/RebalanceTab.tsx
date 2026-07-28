import { useState, useMemo } from 'react'
import { Box, Typography, Paper, Grid, Button, Chip, Skeleton, Tooltip } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { useRebalancePlan } from '../hooks/useData'
import { fmtInr } from '../../../shared/utils/fmt'
import { SectionHeader, InfoTooltip } from '../../../shared/components/ui'
import AutoAwesomeIcon from '@mui/icons-material/AutoAwesome'
import BalanceIcon from '@mui/icons-material/Balance'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { motion, AnimatePresence } from 'framer-motion'

const PROFILES = [
  { id: 'Auto',         label: 'Auto (Detected)',      desc: 'Dynamically targets your actual revealed risk profile' },
  { id: 'Balanced',     label: 'Balanced Profile',     desc: '50% Equity / 30% Debt / 10% Hybrid / 10% Gold' },
  { id: 'Aggressive',   label: 'Aggressive Profile',   desc: '80% Equity / 10% Debt / 5% Hybrid / 5% Gold' },
  { id: 'Conservative', label: 'Conservative Profile', desc: '20% Equity / 60% Debt / 10% Hybrid / 10% Gold' },
]

export default function RebalanceTab({ isSubTab = false }: { isSubTab?: boolean }) {
  const [profile, setProfile] = useState('Auto')
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell' | 'switch'>('all')
  const { data, isLoading, isFetching } = useRebalancePlan(profile)

  const filteredOrders = useMemo(() => {
    if (!data?.orders) return []
    if (filter === 'all') return data.orders
    return data.orders.filter((o: any) => {
      const act = o.action.toLowerCase()
      if (filter === 'buy') return act.includes('buy')
      if (filter === 'sell') return act.includes('sell')
      if (filter === 'switch') return act.includes('switch')
      return true
    })
  }, [data?.orders, filter])

  return (
    <Box sx={{ pb: isSubTab ? 0 : 8 }}>
      {!isSubTab && (
        <SectionHeader 
          title="Strategic Rebalancing" 
          subtitle="Realign your asset allocation to match your target risk profile."
        />
      )}

      {/* ── Architecture Selection Card ────────────────────────────────────────── */}
      <Paper sx={{ 
        p: 4, mb: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', 
        border: '1px solid rgba(255,255,255,0.08)', position: 'relative', overflow: 'hidden',
        boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
      }}>
        <Box sx={{ position: 'absolute', top: -50, right: -50, width: 250, height: 250, borderRadius: '50%', background: 'radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)', filter: 'blur(40px)' }} />
        
        <Grid container spacing={4} alignItems="center">
          <Grid item xs={12} md={7}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
              <AutoAwesomeIcon sx={{ color: '#6366F1', fontSize: 24 }} />
              <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff', letterSpacing: '0.05em' }}>TARGET ARCHITECTURE</Typography>
            </Box>
            <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
              Select your targeted asset allocation. The institutional engine dynamically recalibrates your asset weights to minimize Euclidean/RMSD drift.
            </Typography>

            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5 }}>
              {PROFILES.map((p) => {
                const active = profile === p.id
                return (
                  <Tooltip key={p.id} title={p.desc} arrow placement="top">
                    <Button
                      onClick={() => setProfile(p.id)}
                      sx={{
                        p: 2, borderRadius: '20px', display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                        border: `1px solid ${active ? '#6366F1' : 'rgba(255,255,255,0.08)'}`,
                        bgcolor: active ? alpha('#6366F1', 0.1) : 'rgba(0,0,0,0.3)',
                        color: active ? '#fff' : 'text.secondary',
                        minWidth: 180, flex: '1 1 auto',
                        transition: 'all 0.2s ease',
                        '&:hover': { bgcolor: active ? alpha('#6366F1', 0.15) : 'rgba(255,255,255,0.05)', borderColor: active ? '#6366F1' : 'rgba(255,255,255,0.2)' }
                      }}
                    >
                      <Typography sx={{ fontSize: 14, fontWeight: 900, color: active ? '#6366F1' : '#fff', mb: 0.5 }}>
                        {p.label}
                      </Typography>
                      <Typography sx={{ fontSize: 11, fontWeight: 600, color: 'text.secondary' }}>
                        {p.desc.split('/')[0].trim()}
                      </Typography>
                    </Button>
                  </Tooltip>
                )
              })}
            </Box>
          </Grid>
          
          <Grid item xs={12} md={5}>
            <Box sx={{ 
              background: 'rgba(0,0,0,0.4)', p: 4, borderRadius: '28px', 
              border: '1px solid rgba(255,255,255,0.08)', position: 'relative', overflow: 'hidden',
              boxShadow: 'inset 0 0 20px rgba(99,102,241,0.1)'
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="overline" sx={{ fontWeight: 900, color: '#6366F1', letterSpacing: '0.15em' }}>
                  RMSD DRIFT SCORE
                </Typography>
                <InfoTooltip title="Root Mean Square Deviation measuring divergence from target risk architecture across all asset classes. A higher score means rebalancing is urgently needed." size={18} />
              </Box>
              
              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 48, fontWeight: 900, my: 1, color: '#fff', lineHeight: 1.1 }}>
                {isLoading ? <Skeleton width={140} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} /> : `${data?.drift_score ?? 0}%`}
              </Typography>
              
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 3 }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>
                  Optimal threshold &lt; 5.0%
                </Typography>
                <Chip
                  label={isLoading ? 'Optimizing Vectors...' : (data?.status || 'Balanced')}
                  size="small"
                  sx={{
                    fontWeight: 900, fontSize: 11, px: 1.5, py: 0.5, borderRadius: '10px',
                    bgcolor: (data?.drift_score ?? 0) > 8 ? alpha('#FF516A', 0.2) : (data?.drift_score ?? 0) > 4 ? alpha('#F59E0B', 0.2) : alpha('#4EDE93', 0.2),
                    color: (data?.drift_score ?? 0) > 8 ? '#FF516A' : (data?.drift_score ?? 0) > 4 ? '#F59E0B' : '#4EDE93',
                    border: `1px solid ${(data?.drift_score ?? 0) > 8 ? '#FF516A' : (data?.drift_score ?? 0) > 4 ? '#F59E0B' : '#4EDE93'}`
                  }}
                />
              </Box>
            </Box>
          </Grid>
        </Grid>
      </Paper>

      {/* ── Main Cockpit Area: Vectors & Action Directives ────────────────────────────────────────── */}
      {isLoading ? (
        <Grid container spacing={4}>
          <Grid item xs={12} md={4}>
            <Skeleton variant="rounded" height={360} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} />
          </Grid>
          <Grid item xs={12} md={8}>
            <Skeleton variant="rounded" height={420} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} />
          </Grid>
        </Grid>
      ) : (
        <Grid container spacing={4}>
          {/* Allocation Drift Vectors */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', height: '100%', boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)' }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 4 }}>
                <BalanceIcon sx={{ color: '#6366F1', fontSize: 24 }} />
                <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Asset Drift Vectors</Typography>
              </Box>
              
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
                {data?.drifts && Object.entries(data.drifts).map(([cat, val]: any) => {
                  const isPos = val >= 0
                  return (
                    <Box key={cat} sx={{ p: 2, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                        <Typography variant="body2" sx={{ fontWeight: 800, color: '#fff' }}>{cat}</Typography>
                        <Chip
                          label={isPos ? `+${val.toFixed(1)}% OVER` : `${val.toFixed(1)}% UNDER`}
                          size="small"
                          sx={{
                            fontWeight: 900, fontSize: 10,
                            bgcolor: isPos ? alpha('#FF516A', 0.15) : alpha('#4EDE93', 0.15),
                            color: isPos ? '#FF516A' : '#4EDE93',
                            border: `1px solid ${isPos ? alpha('#FF516A', 0.3) : alpha('#4EDE93', 0.3)}`
                          }}
                        />
                      </Box>
                      <Box sx={{ width: '100%', height: 6, bgcolor: 'rgba(255,255,255,0.08)', borderRadius: 999, overflow: 'hidden' }}>
                        <Box sx={{
                          width: `${Math.min(100, Math.abs(val) * 4)}%`,
                          height: '100%',
                          bgcolor: isPos ? '#FF516A' : '#4EDE93',
                          borderRadius: 999,
                          transition: 'width 0.5s ease'
                        }} />
                      </Box>
                    </Box>
                  )
                })}
              </Box>
            </Paper>
          </Grid>

          {/* Action Directives Card */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', height: '100%', boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)' }}>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 2, mb: 4 }}>
                <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Action Directives (Tax & Yield Aware)</Typography>
                
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, bgcolor: 'rgba(0,0,0,0.3)', p: 0.5, borderRadius: '100px', border: '1px solid rgba(255,255,255,0.08)' }}>
                  {(['all', 'buy', 'sell', 'switch'] as const).map((key) => {
                    const label = key === 'all' ? 'All Directives' : key === 'buy' ? '🟢 Buys' : key === 'sell' ? '🔴 Trims' : '🔄 Switches';
                    return (
                      <Button
                        key={key}
                        size="small"
                        onClick={() => setFilter(key)}
                        sx={{
                          borderRadius: '100px', px: 2, py: 0.5, fontSize: 12, fontWeight: 800,
                          color: filter === key ? '#000' : 'text.secondary',
                          bgcolor: filter === key ? 'primary.main' : 'transparent',
                          '&:hover': { bgcolor: filter === key ? 'primary.main' : 'rgba(255,255,255,0.05)' }
                        }}
                      >
                        {label}
                      </Button>
                    )
                  })}
                </Box>
              </Box>

              {filteredOrders && filteredOrders.length > 0 ? (
                <AnimatePresence>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {filteredOrders.map((order: any, i: number) => {
                      const isSell = order.action.toLowerCase().includes('sell') || order.action.toLowerCase().includes('reduce')
                      const isSwitch = order.action.toLowerCase().includes('switch')
                      const color = isSwitch ? '#6366F1' : isSell ? '#FF516A' : '#4EDE93'
                      const bgGlow = isSwitch ? alpha('#6366F1', 0.15) : isSell ? alpha('#FF516A', 0.15) : alpha('#4EDE93', 0.15)
                      
                      return (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, scale: 0.95 }}
                          transition={{ duration: 0.2 }}
                        >
                          <Box sx={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 3, p: 3,
                            borderRadius: '24px', bgcolor: 'rgba(0,0,0,0.3)',
                            border: '1px solid rgba(255,255,255,0.05)',
                            borderLeft: `8px solid ${color}`,
                            boxShadow: `0 4px 20px ${bgGlow}`,
                            transition: 'all 0.2s ease',
                            '&:hover': { transform: 'translateY(-2px)', bgcolor: 'rgba(255,255,255,0.04)' }
                          }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2.5 }}>
                              <Box sx={{ p: 1.5, borderRadius: '16px', bgcolor: alpha(color, 0.15), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                {isSwitch ? <SwapHorizIcon sx={{ color, fontSize: 24 }} /> : isSell ? <TrendingDownIcon sx={{ color, fontSize: 24 }} /> : <TrendingUpIcon sx={{ color, fontSize: 24 }} />}
                              </Box>
                              <Box>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
                                  <Typography sx={{ fontSize: 16, fontWeight: 900, color: '#fff' }}>
                                    {order.fund || order.category}
                                  </Typography>
                                  <Chip
                                    label={order.action.toUpperCase()}
                                    size="small"
                                    sx={{
                                      fontWeight: 900, fontSize: 9, height: 20,
                                      bgcolor: alpha(color, 0.2), color, border: `1px solid ${color}`
                                    }}
                                  />
                                </Box>
                                <Typography sx={{ fontSize: 13, fontWeight: 600, color: 'text.secondary' }}>
                                  {order.note}
                                </Typography>
                              </Box>
                            </Box>
                            
                            <Box sx={{ textAlign: 'right', flexShrink: 0 }}>
                              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 20, fontWeight: 900, color }}>
                                {fmtInr(order.amount)}
                              </Typography>
                              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800 }}>
                                EXECUTION TARGET
                              </Typography>
                            </Box>
                          </Box>
                        </motion.div>
                      )
                    })}
                  </Box>
                </AnimatePresence>
              ) : (
                <Box sx={{ p: 6, textAlign: 'center', bgcolor: 'rgba(0,0,0,0.2)', borderRadius: '24px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                  <Typography variant="h6" sx={{ color: '#4EDE93', fontWeight: 800, mb: 1 }}>
                    Euclidean/RMSD Equilibrium Achieved
                  </Typography>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                    Your active asset allocation perfectly conforms to the target risk profile. No rebalancing directives required at this time.
                  </Typography>
                </Box>
              )}
            </Paper>
          </Grid>
        </Grid>
      )}
    </Box>
  )
}

