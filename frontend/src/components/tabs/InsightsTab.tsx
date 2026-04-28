import { Box, Grid, Paper, Typography, Alert, Skeleton } from '@mui/material'
import CheckCircleIcon  from '@mui/icons-material/CheckCircle'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import DangerousIcon    from '@mui/icons-material/Dangerous'
import InfoIcon         from '@mui/icons-material/Info'
import { useInsights }  from '../../hooks/useData'
import { SectionHeader, ScoreRing, ProgressRow, TabLoader } from '../ui'
import { fmtInr, fmtPct } from '../../api/fmt'

const NUDGE_ICON: Record<string, any> = {
  success: <CheckCircleIcon  sx={{ fontSize: 18, color: '#059669', flexShrink: 0 }} />,
  warn:    <WarningAmberIcon sx={{ fontSize: 18, color: '#D97706', flexShrink: 0 }} />,
  danger:  <DangerousIcon    sx={{ fontSize: 18, color: '#DC2626', flexShrink: 0 }} />,
  info:    <InfoIcon         sx={{ fontSize: 18, color: '#1D4ED8', flexShrink: 0 }} />,
}
const NUDGE_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  success: { bg: '#F0FDF4', color: '#14532D', border: '#A7F3D0' },
  warn:    { bg: '#FFFBEB', color: '#78350F', border: '#FDE68A' },
  danger:  { bg: '#FEF2F2', color: '#7F1D1D', border: '#FECACA' },
  info:    { bg: '#EFF6FF', color: '#1E3A8A', border: '#BFDBFE' },
}

export default function InsightsTab() {
  const { data, isLoading, error } = useInsights()

  if (isLoading) {
    return <TabLoader message="Executing heuristics and risk allocation models..." />
  }

  const scoreBreakdown = [
    { label: 'Alpha vs Benchmark',   max: 30, pct: 0.7 },
    { label: 'Fund Diversification', max: 25, pct: 0.5 },
    { label: 'Direct Plan Usage',    max: 20, pct: 0.8 },
    { label: 'Concentration Risk',   max: 15, pct: 0.6 },
    { label: 'Category Balance',     max: 10, pct: 0.5 },
  ]

  return (
    <Box>
      <SectionHeader title="Smart Insights" subtitle="AI-powered portfolio diagnostics and actionable recommendations" />
      {error && <Alert severity="error" sx={{ mb: 2 }}>Failed to load insights.</Alert>}

      <Grid container spacing={3}>
        {/* ── Left: Score + breakdown ─────────────────────────────── */}
        <Grid item xs={12} md={4}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Portfolio Health Score</Typography>
            {isLoading
              ? <Skeleton variant="circular" width={120} height={120} sx={{ mx: 'auto', mb: 2 }} />
              : <ScoreRing score={data?.score ?? 0} size={120} />
            }
            <Box sx={{ mt: 3 }}>
              {scoreBreakdown.map((item) => {
                const actual = Math.round(item.pct * item.max)
                return <ProgressRow key={item.label} label={item.label} actual={actual} max={item.max} />
              })}
            </Box>
          </Paper>

          {/* Quick stats */}
          <Paper elevation={1} sx={{ p: 2.5, borderRadius: 3 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Portfolio Stats</Typography>
            {[
              { label: 'SIP Consistency',  value: `${data?.sip_score ?? 0}/10` },
              { label: 'Liquid Holdings',  value: `${fmtInr(data?.liquid_val, true)} (${data?.liquid_pct?.toFixed(1)}%)` },
              { label: 'Expense Drag/yr',  value: fmtInr(data?.expense_drag) },
              { label: 'Expense Drag %',   value: `${data?.expense_pct?.toFixed(2)}%` },
              { label: 'ELSS Holdings',    value: fmtInr(data?.elss_val, true) },
            ].map((s) => (
              <Box key={s.label} sx={{
                display: 'flex', justifyContent: 'space-between', py: 1,
                borderBottom: '1px solid #F1F5F9', '&:last-child': { borderBottom: 'none' },
              }}>
                <Typography variant="body2" color="text.secondary" fontWeight={500}>{s.label}</Typography>
                {isLoading
                  ? <Skeleton width={80} />
                  : <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 600, color: '#0F172A' }}>{s.value}</Typography>
                }
              </Box>
            ))}
          </Paper>
        </Grid>

        {/* ── Right: Nudges + Goal timeline ───────────────────────── */}
        <Grid item xs={12} md={8}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Smart Nudges</Typography>
            {isLoading
              ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} height={56} sx={{ borderRadius: 2, mb: 1 }} />)
              : (data?.nudges?.length ?? 0) === 0
                ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, p: 2, background: '#F0FDF4', borderRadius: 2, border: '1px solid #A7F3D0' }}>
                    <CheckCircleIcon sx={{ color: '#059669', fontSize: 20 }} />
                    <Typography variant="body2" fontWeight={600} color="#14532D">No issues detected. Your portfolio looks healthy!</Typography>
                  </Box>
                )
                : data?.nudges?.map((n, i) => {
                  const s = NUDGE_STYLE[n.type] ?? NUDGE_STYLE.info
                  return (
                    <Box key={i} sx={{
                      display: 'flex', alignItems: 'flex-start', gap: 1.5,
                      p: 1.75, borderRadius: 2, mb: 1,
                      background: s.bg, color: s.color,
                      border: `1px solid ${s.border}`,
                      borderLeft: `4px solid ${s.border}`,
                    }}>
                      {NUDGE_ICON[n.type]}
                      <Typography sx={{ fontSize: 13, fontWeight: 500, lineHeight: 1.55 }}>
                        {n.message}
                      </Typography>
                    </Box>
                  )
                })
            }
          </Paper>

          {/* Goal timeline */}
          {!isLoading && (data?.goal_timeline?.length ?? 0) > 0 && (
            <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
              <Typography variant="h6" sx={{ mb: 1 }}>Goal-Based Timeline</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>How your holdings map to financial goals</Typography>
              {/* Timeline bar */}
              <Box sx={{ display: 'flex', borderRadius: 2, overflow: 'hidden', height: 42, mb: 2 }}>
                {data?.goal_timeline?.map((g: any) => (
                  <Box key={g.category} sx={{
                    width: `${g.pct}%`, background: g.color, minWidth: g.pct > 5 ? 'auto' : 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 10, fontWeight: 700, color: 'rgba(255,255,255,0.92)',
                    overflow: 'hidden', whiteSpace: 'nowrap', px: 1,
                  }}>
                    {g.pct > 8 ? g.category : ''}
                  </Box>
                ))}
              </Box>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {data?.goal_timeline?.map((g: any) => (
                  <Box key={g.category} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: g.color, flexShrink: 0 }} />
                      <Typography variant="body2" fontWeight={600}>{g.category}</Typography>
                      <Typography variant="caption" color="text.secondary">· {g.goal}</Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right' }}>
                      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 600, color: '#0F172A' }}>
                        {fmtInr(g.value, true)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">{g.pct?.toFixed(1)}%</Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </Paper>
          )}
        </Grid>
      </Grid>
    </Box>
  )
}
