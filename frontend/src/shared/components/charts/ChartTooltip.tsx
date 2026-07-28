import { Box, Typography, Paper } from '@mui/material'
import { fmtInr, fmtPct } from '../../utils/fmt'

export function ChartTooltip({ active, payload, label, isPct = false }: any) {
  if (!active || !payload?.length) return null
  return (
    <Paper
      elevation={3}
      sx={{
        p: 1.5,
        border: '1px solid #E2E8F0',
        borderRadius: 2,
        background: 'rgba(255, 255, 255, 0.96)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <Typography variant="caption" fontWeight={700} sx={{ mb: 1, display: 'block', color: '#64748B' }}>
        {label}
      </Typography>
      {payload.map((p: any, i: number) => (
        <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5, '&:last-child': { mb: 0 } }}>
          <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: p.color }} />
          <Typography variant="body2" fontWeight={600} color="#0F172A">
            {p.name}:
          </Typography>
          <Typography variant="body2" sx={{ fontFamily: '"DM Mono",monospace', ml: 'auto', fontWeight: 700, color: '#0F172A' }}>
            {isPct ? fmtPct(p.value) : fmtInr(p.value)}
          </Typography>
        </Box>
      ))}
    </Paper>
  )
}
