import { Box, Tooltip as MuiTooltip } from '@mui/material'
import { verdictBg, verdictColor, verdictBorder } from '../../utils/fmt'

export function VerdictChip({ verdict, reason, score }: { verdict: string; reason?: string; score?: number }) {
  const chip = (
    <Box
      component="span"
      sx={{
        display: 'inline-flex', alignItems: 'center', gap: 0.5,
        px: 1.5, py: 0.4, borderRadius: 999,
        fontSize: '0.6875rem', fontWeight: 700, letterSpacing: '0.04em',
        background: verdictBg(verdict),
        color:      verdictColor(verdict),
        border:     `1px solid ${verdictBorder(verdict)}`,
        cursor: reason ? 'help' : 'default',
        transition: 'all 0.2s',
        '&:hover': reason ? { filter: 'brightness(1.1)', transform: 'scale(1.03)' } : {},
      }}
    >
      {verdict === 'Strong' ? '🟢' : verdict === 'Average' ? '🟡' : '🔴'} {verdict}
      {score != null && (
        <Box component="span" sx={{ 
          ml: 0.5, fontSize: '0.6rem', fontWeight: 800, opacity: 0.8,
          bgcolor: 'rgba(0,0,0,0.1)', px: 0.75, py: 0.15, borderRadius: 999,
        }}>
          {score.toFixed(1)}
        </Box>
      )}
    </Box>
  )

  if (!reason) return chip

  return (
    <MuiTooltip
      title={reason}
      placement="top"
      arrow
      slotProps={{
        tooltip: {
          sx: {
            bgcolor: '#0F172A', color: '#E2E8F0', fontSize: 12,
            p: 1.5, borderRadius: '10px', maxWidth: 320,
            border: '1px solid rgba(255,255,255,0.1)',
            lineHeight: 1.5, fontWeight: 500,
            boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
          }
        }
      }}
    >
      {chip}
    </MuiTooltip>
  )
}

const CAT_STYLE: Record<string, { bg: string; color: string; border: string }> = {
  Equity: { bg: '#EFF6FF', color: '#1D4ED8',   border: '#BFDBFE' },
  Debt:   { bg: '#ECFDF5', color: '#059669',   border: '#A7F3D0' },
  ELSS:   { bg: '#F5F3FF', color: '#6D28D9',   border: '#DDD6FE' },
  Hybrid: { bg: '#FFFBEB', color: '#B45309',   border: '#FDE68A' },
  Index:  { bg: '#EFF6FF', color: '#2563EB',   border: '#BFDBFE' },
  Liquid: { bg: '#ECFEFF', color: '#0E7490',   border: '#A5F3FC' },
  FOF:    { bg: '#FFF1F2', color: '#BE123C',   border: '#FECDD3' },
  Other:  { bg: '#F8FAFC', color: '#64748B',   border: '#E2E8F0' },
}

export function CategoryBadge({ category }: { category: string }) {
  const s = CAT_STYLE[category] ?? CAT_STYLE.Other
  return (
    <Box component="span" sx={{
      display: 'inline-flex', alignItems: 'center',
      px: 1.25, py: 0.3, borderRadius: 999,
      fontSize: '0.625rem', fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.06em', ...s, border: `1px solid ${s.border}`,
    }}>
      {category}
    </Box>
  )
}

export function PlanBadge({ plan }: { plan: string }) {
  const isDirect = plan === 'Direct'
  return (
    <Box component="span" sx={{
      display: 'inline-flex', alignItems: 'center',
      px: 1.25, py: 0.3, borderRadius: 999,
      fontSize: '0.625rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
      background: isDirect ? '#ECFDF5' : '#FFF7ED',
      color:      isDirect ? '#059669' : '#C2410C',
      border:     `1px solid ${isDirect ? '#A7F3D0' : '#FED7AA'}`,
    }}>
      {plan}
    </Box>
  )
}

export function RiskPill({ label }: { label: string }) {
  const low = ['Very Low','Low','Low to Moderate'].includes(label)
  const high = ['High','Moderate-High','Moderately High','Very High'].includes(label)
  return (
    <Box component="span" sx={{
      px: 1.25, py: 0.3, borderRadius: 999, fontSize: '0.625rem',
      fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em',
      background: low ? '#D1FAE5' : high ? '#FEE2E2' : '#FEF3C7',
      color:      low ? '#065F46'  : high ? '#991B1B' : '#92400E',
    }}>
      Risk: {label}
    </Box>
  )
}
