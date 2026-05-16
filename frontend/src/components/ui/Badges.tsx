import { Box } from '@mui/material'
import { verdictBg, verdictColor, verdictBorder } from '../../api/fmt'

export function VerdictChip({ verdict }: { verdict: string }) {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-flex', alignItems: 'center',
        px: 1.5, py: 0.4, borderRadius: 999,
        fontSize: '0.6875rem', fontWeight: 700, letterSpacing: '0.04em',
        background: verdictBg(verdict),
        color:      verdictColor(verdict),
        border:     `1px solid ${verdictBorder(verdict)}`,
      }}
    >
      {verdict === 'Strong' ? '🟢' : verdict === 'Average' ? '🟡' : '🔴'} {verdict}
    </Box>
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
