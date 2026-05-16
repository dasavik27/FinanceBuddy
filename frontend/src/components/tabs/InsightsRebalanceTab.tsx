import { useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Box, Grid, Paper, Typography, Alert, Skeleton, Button, Chip } from '@mui/material'
import CheckCircleIcon  from '@mui/icons-material/CheckCircle'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import DangerousIcon    from '@mui/icons-material/Dangerous'
import InfoIcon         from '@mui/icons-material/Info'
import AutoAwesomeIcon  from '@mui/icons-material/AutoAwesome'
import BalanceIcon      from '@mui/icons-material/Balance'
import { useInsights }  from '../../hooks/useData'
import { SectionHeader, ScoreRing, ProgressRow } from '../ui'
import { fmtInr } from '../../api/fmt'
import { motion, AnimatePresence } from 'framer-motion'
import RebalanceTab from './RebalanceTab'

const NUDGE_ICON: Record<string, any> = {
  success: <CheckCircleIcon  sx={{ fontSize: 22, color: '#4EDE93', flexShrink: 0 }} />,
  warn:    <WarningAmberIcon sx={{ fontSize: 22, color: '#F59E0B', flexShrink: 0 }} />,
  danger:  <DangerousIcon    sx={{ fontSize: 22, color: '#FF516A', flexShrink: 0 }} />,
  info:    <InfoIcon         sx={{ fontSize: 22, color: '#6366F1', flexShrink: 0 }} />,
}

const NUDGE_STYLE: Record<string, { bg: string; color: string; border: string; glow: string }> = {
  success: { bg: 'rgba(78, 222, 147, 0.04)', color: '#4EDE93', border: 'rgba(78, 222, 147, 0.2)', glow: 'rgba(78, 222, 147, 0.15)' },
  warn:    { bg: 'rgba(245, 158, 11, 0.04)', color: '#F59E0B', border: 'rgba(245, 158, 11, 0.2)', glow: 'rgba(245, 158, 11, 0.15)' },
  danger:  { bg: 'rgba(255, 81, 106, 0.04)', color: '#FF516A', border: 'rgba(255, 81, 106, 0.2)', glow: 'rgba(255, 81, 106, 0.15)' },
  info:    { bg: 'rgba(99, 102, 241, 0.04)', color: '#6366F1', border: 'rgba(99, 102, 241, 0.2)', glow: 'rgba(99, 102, 241, 0.15)' },
}

export default function InsightsRebalanceTab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeSubTab = searchParams.get('tab') === 'rebalance' ? 'rebalance' : 'diagnostics'
  
  const { data, isLoading, isFetching, error } = useInsights()
  const [filter, setFilter] = useState<'all' | 'warn' | 'danger' | 'info'>('all')

  const scoreBreakdown = data?.score_breakdown || [
    { label: 'Alpha vs Benchmark',   max: 30, score: 0 },
    { label: 'Fund Diversification', max: 25, score: 0 },
    { label: 'Direct Plan Usage',    max: 20, score: 0 },
    { label: 'Concentration Risk',   max: 15, score: 0 },
    { label: 'Category Balance',     max: 10, score: 0 },
  ]

  const filteredNudges = useMemo(() => {
    if (!data?.nudges) return []
    if (filter === 'all') return data.nudges
    return data.nudges.filter((n: any) => n.type === filter)
  }, [data?.nudges, filter])

  return (
    <Box sx={{ pb: 8 }}>
      <SectionHeader 
        title="CIO Intelligence & Rebalancing Lab" 
        subtitle="Real-time institutional diagnostics, fee drag auditing, and proactive portfolio restructuring" 
      />
      {error && <Alert severity="error" sx={{ mb: 2, bgcolor: 'rgba(255, 81, 106, 0.1)', color: '#FF516A', border: '1px solid rgba(255, 81, 106, 0.3)' }}>Failed to load institutional insights.</Alert>}

      {/* ── Top Navigation Bar ──────────────────────────────────────────────────────── */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 6, p: 1, bgcolor: 'rgba(0,0,0,0.4)', borderRadius: '100px', width: 'fit-content', mx: 'auto', border: '1px solid rgba(255,255,255,0.08)', boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)' }}>
        <Button
          onClick={() => setSearchParams({ tab: 'diagnostics' })}
          sx={{
            borderRadius: '100px', px: 3, py: 1, fontSize: 13, fontWeight: 900, display: 'flex', alignItems: 'center', gap: 1,
            color: activeSubTab === 'diagnostics' ? '#000' : 'text.secondary',
            bgcolor: activeSubTab === 'diagnostics' ? '#4EDE93' : 'transparent',
            '&:hover': { bgcolor: activeSubTab === 'diagnostics' ? '#4EDE93' : 'rgba(255,255,255,0.05)' }
          }}
        >
          <AutoAwesomeIcon sx={{ fontSize: 18 }} />
          Neural Diagnostics & Smart Nudges
        </Button>
        <Button
          onClick={() => setSearchParams({ tab: 'rebalance' })}
          sx={{
            borderRadius: '100px', px: 3, py: 1, fontSize: 13, fontWeight: 900, display: 'flex', alignItems: 'center', gap: 1,
            color: activeSubTab === 'rebalance' ? '#fff' : 'text.secondary',
            bgcolor: activeSubTab === 'rebalance' ? '#6366F1' : 'transparent',
            '&:hover': { bgcolor: activeSubTab === 'rebalance' ? '#6366F1' : 'rgba(255,255,255,0.05)' }
          }}
        >
          <BalanceIcon sx={{ fontSize: 18 }} />
          Euclidean Drift & Rebalancing Planner
        </Button>
      </Box>

      {activeSubTab === 'rebalance' ? (
        <RebalanceTab isSubTab={true} />
      ) : (
        <Grid container spacing={4}>
          {/* ── Left Column: Health Scoring & Vitals ─────────────────────────────── */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ 
              p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', 
              border: '1px solid rgba(255,255,255,0.08)', mb: 4, position: 'relative', overflow: 'hidden',
              boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
            }}>
              <Box sx={{ position: 'absolute', top: -50, right: -50, width: 200, height: 200, borderRadius: '50%', background: 'radial-gradient(circle, rgba(78,222,147,0.1) 0%, transparent 70%)', filter: 'blur(30px)' }} />
              
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 4 }}>
                <AutoAwesomeIcon sx={{ color: '#4EDE93', fontSize: 24 }} />
                <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff', letterSpacing: '0.05em' }}>HEALTH AUDIT</Typography>
              </Box>

              {isLoading ? (
                <Skeleton variant="circular" width={160} height={160} sx={{ mx: 'auto', mb: 4, bgcolor: 'rgba(255,255,255,0.05)' }} />
              ) : (
                <Box sx={{ mb: 4, py: 2 }}>
                  <ScoreRing score={data?.score ?? 0} size={160} />
                </Box>
              )}

              <Typography variant="overline" sx={{ fontWeight: 800, color: 'text.secondary', display: 'block', mb: 2, letterSpacing: '0.1em' }}>
                INSTITUTIONAL PILLARS
              </Typography>

              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {scoreBreakdown.map((item: any) => (
                  <ProgressRow key={item.label} label={item.label} actual={item.score} max={item.max} />
                ))}
              </Box>
            </Paper>

            {/* Vitals & Drag Ledger */}
            <Paper sx={{ 
              p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', 
              border: '1px solid rgba(255,255,255,0.08)',
              boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
            }}>
              <Typography variant="h6" sx={{ mb: 3, fontWeight: 900, color: '#fff' }}>Portfolio Ledger</Typography>
              {[
                { label: 'SIP Consistency',  value: `${data?.sip_score ?? 0}/10`, highlight: '#4EDE93' },
                { label: 'Liquid Holdings',  value: `${fmtInr(data?.liquid_val, true)} (${data?.liquid_pct?.toFixed(1)}%)`, highlight: '#fff' },
                { label: 'Expense Drag/yr',  value: fmtInr(data?.expense_drag), highlight: '#FF516A' },
                { label: 'Expense Drag %',   value: `${data?.expense_pct?.toFixed(2)}%`, highlight: '#FF516A' },
                { label: 'ELSS Holdings',    value: fmtInr(data?.elss_val, true), highlight: '#6366F1' },
              ].map((s) => (
                <Box key={s.label} sx={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 2,
                  borderBottom: '1px solid rgba(255,255,255,0.06)', '&:last-child': { borderBottom: 'none' },
                }}>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 700 }}>{s.label}</Typography>
                  {isLoading ? (
                    <Skeleton width={80} sx={{ bgcolor: 'rgba(255,255,255,0.05)' }} />
                  ) : (
                    <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 14, fontWeight: 800, color: s.highlight }}>{s.value}</Typography>
                  )}
                </Box>
              ))}
            </Paper>
          </Grid>

          {/* ── Right Column: Interactive Nudges & Goal Horizon ───────────────────────── */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ 
              p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', 
              border: '1px solid rgba(255,255,255,0.08)', mb: 4,
              boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
            }}>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 2, mb: 4 }}>
                <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>Smart Nudges & CIO Advisories</Typography>
                
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, bgcolor: 'rgba(0,0,0,0.3)', p: 0.5, borderRadius: '100px', border: '1px solid rgba(255,255,255,0.08)' }}>
                  {(['all', 'warn', 'danger', 'info'] as const).map((key) => {
                    const label = key === 'all' ? 'All Insights' : key === 'warn' ? '⚠️ High Priority' : key === 'danger' ? '🚨 Critical' : 'ℹ️ Optimizations';
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

              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={80} sx={{ borderRadius: '20px', mb: 2, bgcolor: 'rgba(255,255,255,0.05)' }} />)
              ) : filteredNudges.length === 0 ? (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, p: 4, background: 'rgba(78, 222, 147, 0.05)', borderRadius: '24px', border: '1px solid rgba(78, 222, 147, 0.2)' }}>
                  <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 28 }} />
                  <Typography variant="body1" fontWeight={800} color="#4EDE93">No issues detected in this category. Your portfolio architecture is exceptionally sound!</Typography>
                </Box>
              ) : (
                <AnimatePresence>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {filteredNudges.map((n: any, i: number) => {
                      const s = NUDGE_STYLE[n.type] ?? NUDGE_STYLE.info
                      return (
                        <motion.div
                          key={i}
                          initial={{ opacity: 0, y: 10 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, scale: 0.95 }}
                          transition={{ duration: 0.2 }}
                        >
                          <Box sx={{
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 3,
                            p: 3, borderRadius: '24px', background: s.bg,
                            border: `1px solid ${s.border}`,
                            borderLeft: `8px solid ${s.color}`,
                            boxShadow: `0 4px 20px ${s.glow}`,
                            transition: 'all 0.2s ease',
                            '&:hover': { transform: 'translateY(-2px)', bgcolor: 'rgba(255,255,255,0.04)' }
                          }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2.5 }}>
                              <Box sx={{ p: 1.5, borderRadius: '16px', bgcolor: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                {NUDGE_ICON[n.type]}
                              </Box>
                              <Typography sx={{ fontSize: 15, fontWeight: 700, lineHeight: 1.5, color: '#fff' }}>
                                {n.message}
                              </Typography>
                            </Box>
                            <Chip 
                              label={n.type === 'danger' ? 'ACTION REQUIRED' : n.type === 'warn' ? 'HIGH PRIORITY' : 'OPTIMIZATION'} 
                              size="small" 
                              sx={{ fontWeight: 900, fontSize: 10, bgcolor: s.color, color: '#000', borderRadius: '8px' }} 
                            />
                          </Box>
                        </motion.div>
                      )
                    })}
                  </Box>
                </AnimatePresence>
              )}
            </Paper>

            {/* ── Goal Horizon Map ────────────────────────────────────────────── */}
            {!isLoading && (data?.goal_timeline?.length ?? 0) > 0 && (
              <Paper sx={{ 
                p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)', 
                border: '1px solid rgba(255,255,255,0.08)',
                boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
              }}>
                <Typography variant="h6" sx={{ mb: 1, fontWeight: 900, color: '#fff' }}>Goal-Based Capital Mapping</Typography>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 4 }}>Dynamic timeline mapping active liquid, debt, and equity holdings to future financial horizons</Typography>
                
                <Box sx={{ display: 'flex', borderRadius: '20px', overflow: 'hidden', height: 48, mb: 4, border: '1px solid rgba(255,255,255,0.1)' }}>
                  {data?.goal_timeline?.map((g: any) => (
                    <Box key={g.category} sx={{
                      width: `${g.pct}%`, background: g.color, minWidth: g.pct > 5 ? 'auto' : 0,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: 12, fontWeight: 900, color: '#000',
                      overflow: 'hidden', whiteSpace: 'nowrap', px: 1,
                      boxShadow: 'inset 0 0 10px rgba(255,255,255,0.3)'
                    }}>
                      {g.pct > 8 ? g.category : ''}
                    </Box>
                  ))}
                </Box>

                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {data?.goal_timeline?.map((g: any) => (
                    <Box key={g.category} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', p: 2.5, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '20px', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                        <Box sx={{ width: 14, height: 14, borderRadius: '50%', background: g.color, flexShrink: 0, boxShadow: `0 0 14px ${g.color}` }} />
                        <Box>
                          <Typography variant="body1" fontWeight={800} sx={{ color: '#fff' }}>{g.category}</Typography>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>{g.goal}</Typography>
                        </Box>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 16, fontWeight: 900, color: '#4EDE93' }}>
                          {fmtInr(g.value, true)}
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800 }}>{g.pct?.toFixed(1)}% of Net Worth</Typography>
                      </Box>
                    </Box>
                  ))}
                </Box>
              </Paper>
            )}
          </Grid>
        </Grid>
      )}
    </Box>
  )
}

