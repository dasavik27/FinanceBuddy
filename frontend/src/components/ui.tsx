import { ReactNode } from 'react'
import { Box, Typography, Skeleton, LinearProgress, Chip } from '@mui/material'
import { motion } from 'framer-motion'
import { fmtPct, gainColor, verdictColor, verdictBg, verdictBorder } from '../api/fmt'

// ── KPI Metric Card ──────────────────────────────────────────────────────────
interface MetricCardProps {
  label:    string
  value:    string | number
  sub?:     string
  accent?:  'success' | 'danger' | 'info' | 'warn' | 'none'
  loading?: boolean
  mono?:    boolean
}

export function MetricCard({ label, value, sub, accent, loading, mono }: MetricCardProps) {
  const accentColor = {
    success: '#059669', danger: '#DC2626', info: '#1D4ED8', warn: '#D97706', none: 'transparent',
  }[accent ?? 'none']

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: [0, 0, 0, 1] }}
    >
      <Box
        sx={{
          background: '#FFFFFF',
          border: `1px solid #E2E8F0`,
          borderLeft: accent && accent !== 'none' ? `3px solid ${accentColor}` : '1px solid #E2E8F0',
          borderRadius: '14px',
          p: '18px 20px',
          boxShadow: '0 1px 2px rgba(15,23,42,0.04), 0 1px 6px rgba(15,23,42,0.06)',
          transition: 'all 200ms cubic-bezier(0.2,0,0,1)',
          position: 'relative', overflow: 'hidden',
          '&::before': accent && accent !== 'none' ? {
            content: '""', position: 'absolute', top: 0, left: 0, right: 0,
            height: '2px',
            background: `linear-gradient(90deg, ${accentColor}40, ${accentColor}, ${accentColor}40)`,
            opacity: 0, transition: 'opacity 200ms ease',
          } : {},
          '&:hover': {
            boxShadow: '0 2px 6px rgba(15,23,42,0.06), 0 8px 24px rgba(15,23,42,0.11)',
            transform: 'translateY(-2px)',
            borderColor: '#BFDBFE',
            '&::before': { opacity: 1 },
          },
        }}
      >
        <Typography variant="overline" display="block" sx={{ mb: 1 }}>
          {label}
        </Typography>
        {loading ? (
          <Skeleton width="60%" height={36} />
        ) : (
          <Typography
            sx={{
              fontSize: '1.5rem',
              fontWeight: 500,
              color: '#0F172A',
              fontFamily: mono !== false ? '"DM Mono", monospace' : 'inherit',
              letterSpacing: '-0.5px',
              lineHeight: 1.2,
              mb: sub ? 0.5 : 0,
            }}
          >
            {value}
          </Typography>
        )}
        {sub && !loading && (
          <Typography variant="caption" color="text.secondary" display="block">
            {sub}
          </Typography>
        )}
      </Box>
    </motion.div>
  )
}

// ── Section Header ───────────────────────────────────────────────────────────
export function SectionHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography variant="h5" sx={{ mb: subtitle ? 0.5 : 0 }}>{title}</Typography>
      {subtitle && <Typography variant="body2" color="text.secondary">{subtitle}</Typography>}
    </Box>
  )
}

// ── Verdict Chip ─────────────────────────────────────────────────────────────
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

// ── Category Badge ────────────────────────────────────────────────────────────
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

// ── Plan Badge ────────────────────────────────────────────────────────────────
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

// ── Risk Pill ────────────────────────────────────────────────────────────────
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

// ── Score Ring ───────────────────────────────────────────────────────────────
export function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const pct  = Math.min(100, Math.max(0, score))
  const color = pct >= 70 ? '#059669' : pct >= 40 ? '#D97706' : '#DC2626'
  const r = (size / 2) - 8
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - pct / 100)
  return (
    <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#F1F5F9" strokeWidth={8} />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={8}
          strokeDasharray={circ} strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 600ms cubic-bezier(0,0,0,1)' }}
        />
      </svg>
      <Box sx={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: size * 0.28, fontWeight: 500, color: '#0F172A', lineHeight: 1 }}>
          {score}
        </Typography>
        <Typography sx={{ fontSize: 9, color: '#94A3B8', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          /100
        </Typography>
      </Box>
    </Box>
  )
}

// ── Progress Row ─────────────────────────────────────────────────────────────
export function ProgressRow({ label, actual, max }: { label: string; actual: number; max: number }) {
  const pct   = max > 0 ? (actual / max) * 100 : 0
  const color = pct >= 70 ? 'success' : pct >= 40 ? 'warning' : 'error'
  return (
    <Box sx={{ mb: 1.5 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.75 }}>
        <Typography variant="body2" fontWeight={600} color="text.primary">{label}</Typography>
        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '0.75rem', color: '#94A3B8' }}>
          {actual}/{max}
        </Typography>
      </Box>
      <LinearProgress variant="determinate" value={pct} color={color as any}
        sx={{ height: 7, borderRadius: 999, background: '#F1F5F9' }} />
    </Box>
  )
}

// ── Period Selector ───────────────────────────────────────────────────────────
interface PeriodSelectorProps {
  options:   string[]
  value:     string
  onChange:  (v: string) => void
}
export function PeriodSelector({ options, value, onChange }: PeriodSelectorProps) {
  return (
    <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
      {options.map((o) => (
        <Box
          key={o}
          onClick={() => onChange(o)}
          sx={{
            px: 1.75, py: 0.6,
            borderRadius: 999,
            fontSize: '0.75rem', fontWeight: 600,
            cursor: 'pointer',
            border: `1.5px solid ${o === value ? '#0F172A' : '#E2E8F0'}`,
            background: o === value ? '#0F172A' : '#FFFFFF',
            color: o === value ? '#FFFFFF' : '#64748B',
            transition: 'all 120ms ease',
            '&:hover': o !== value ? { borderColor: '#BFDBFE', background: '#EFF6FF', color: '#1D4ED8' } : {},
          }}
        >
          {o}
        </Box>
      ))}
    </Box>
  )
}

// ── Loading Grid ─────────────────────────────────────────────────────────────
export function LoadingGrid({ cols = 4, rows = 1 }: { cols?: number; rows?: number }) {
  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 2, mb: 3 }}>
      {Array.from({ length: cols * rows }).map((_, i) => (
        <Skeleton key={i} variant="rectangular" height={100} sx={{ borderRadius: 2 }} />
      ))}
    </Box>
  )
}

// ── Empty State ───────────────────────────────────────────────────────────────
export function EmptyState({ message }: { message: string }) {
  return (
    <Box sx={{ textAlign: 'center', py: 8 }}>
      <Typography variant="body1" color="text.secondary">{message}</Typography>
    </Box>
  )
}
