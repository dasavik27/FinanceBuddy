import React, { useCallback, useMemo, useState } from 'react'
import {
  Box, Button, Chip, Divider, IconButton, LinearProgress, Skeleton, Stack,
  TextField, Tooltip, Typography,
} from '@mui/material'
import type { SxProps } from '@mui/material'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import RefreshIcon from '@mui/icons-material/Refresh'

import {
  budgetErrorDetail, useBudgetAnomalies, useBudgetEnvelopes, useBudgetForecast,
  useBudgetRecurring, useSetBudgetEnvelope,
} from '../hooks/useBudget'
import type {
  BudgetAnomaly, BudgetEnvelope, BudgetForecast, BudgetPriceChange, BudgetRecurring,
} from '../types'

interface InsightsTabProps {
  sessionId: string
}

/**
 * Every `sx` that does not depend on props is a module constant.
 *
 * An object literal in JSX has a fresh identity on every render, so emotion
 * re-serialises it each time - in the subscription and envelope lists that would be
 * a dozen cells' worth per row, per render. The prop-dependent ones (status colours)
 * are precomputed lookup tables rather than ternaries over fresh literals, and the
 * genuinely continuous ones (bar widths, tick offsets) go through `style` so they
 * never enter the emotion cache at all.
 */

// ── Palette ──────────────────────────────────────────────────────────────────

const TEXT = '#e2e8f0'
const MUTED = '#94a3b8'
const GREEN = '#34d399'
const RED = '#f87171'
const AMBER = '#fbbf24'
const ORANGE = '#fb923c'
const CARD_BORDER = '1px solid rgba(148, 163, 184, 0.15)'

const SEVERITY_COLOR: Record<BudgetAnomaly['severity'], string> = {
  high: '#f87171',
  medium: '#fbbf24',
  low: '#94a3b8',
}

// ── Shared surfaces ──────────────────────────────────────────────────────────

const ROOT_SX: SxProps = { display: 'flex', flexDirection: 'column', gap: 3 }

const CARD_SX: SxProps = {
  background: 'rgba(30, 41, 59, 0.5)',
  border: CARD_BORDER,
  borderRadius: 2,
  p: 2.5,
  color: TEXT,
}

const CARD_TITLE_SX: SxProps = {
  fontWeight: 700, fontSize: '1rem', color: TEXT, letterSpacing: 0.2,
}
const CARD_SUBTITLE_SX: SxProps = { fontSize: '0.8rem', color: MUTED }
const CARD_HEADER_SX: SxProps = {
  display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
  gap: 2, flexWrap: 'wrap', mb: 2,
}

const MUTED_TEXT_SX: SxProps = { color: MUTED, fontSize: '0.85rem' }
const EMPTY_SX: SxProps = { color: MUTED, fontSize: '0.9rem', py: 3, textAlign: 'center' }
const CAPTION_SX: SxProps = { color: MUTED, fontSize: '0.75rem' }

const SKELETON_SX: SxProps = { bgcolor: 'rgba(148, 163, 184, 0.12)', borderRadius: 1 }
const SKELETON_LINE_SX: SxProps = { ...SKELETON_SX, height: 18, mb: 1 }
const SKELETON_HERO_SX: SxProps = { ...SKELETON_SX, height: 52, mb: 1.5, width: '55%' }

const ERROR_PANEL_SX: SxProps = {
  p: 2,
  borderRadius: 2,
  background: 'rgba(239, 68, 68, 0.10)',
  border: '1px solid rgba(239, 68, 68, 0.30)',
  color: '#fca5a5',
  fontSize: '0.85rem',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 2,
  flexWrap: 'wrap',
}
const RETRY_BTN_SX: SxProps = {
  textTransform: 'none', fontWeight: 600, color: '#fca5a5',
  borderColor: 'rgba(239, 68, 68, 0.4)',
}

const STAT_ROW_SX: SxProps = { display: 'flex', flexWrap: 'wrap', gap: 3, rowGap: 1.5 }
const STAT_LABEL_SX: SxProps = {
  color: MUTED, fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: 0.6,
  fontWeight: 700,
}
const STAT_VALUE_SX: SxProps = { color: TEXT, fontSize: '1.05rem', fontWeight: 700 }

const DIVIDER_SX: SxProps = { borderColor: 'rgba(148, 163, 184, 0.15)', my: 2 }

// ── Forecast ─────────────────────────────────────────────────────────────────

const HERO_SX: SxProps = { display: 'flex', alignItems: 'flex-end', gap: 1.5, flexWrap: 'wrap' }
const HERO_NUMBER_POSITIVE_SX: SxProps = {
  fontSize: '2.6rem', fontWeight: 800, lineHeight: 1.05, color: GREEN,
}
const HERO_NUMBER_NEGATIVE_SX: SxProps = { ...HERO_NUMBER_POSITIVE_SX, color: RED }
const HERO_UNIT_SX: SxProps = { fontSize: '1rem', fontWeight: 600, color: MUTED, pb: 0.6 }
const HERO_CONTEXT_SX: SxProps = { color: TEXT, fontSize: '0.95rem', mt: 0.5 }

const CONFIDENCE_TEXT: Record<BudgetForecast['confidence'], string> = {
  low: 'Based on limited history — upload more statements for a reliable projection',
  medium: 'Based on 2 months of history',
  high: 'Based on 3+ months of history',
}
const CONFIDENCE_LABEL: Record<BudgetForecast['confidence'], string> = {
  low: 'Low confidence',
  medium: 'Medium confidence',
  high: 'High confidence',
}
const CONFIDENCE_CHIP_SX: Record<BudgetForecast['confidence'], SxProps> = {
  low: {
    height: 22, fontSize: '0.7rem', fontWeight: 700,
    backgroundColor: 'rgba(239, 68, 68, 0.12)', color: RED,
    border: '1px solid rgba(239, 68, 68, 0.35)',
  },
  medium: {
    height: 22, fontSize: '0.7rem', fontWeight: 700,
    backgroundColor: 'rgba(245, 158, 11, 0.12)', color: AMBER,
    border: '1px solid rgba(245, 158, 11, 0.35)',
  },
  high: {
    height: 22, fontSize: '0.7rem', fontWeight: 700,
    backgroundColor: 'rgba(16, 185, 129, 0.12)', color: GREEN,
    border: '1px solid rgba(16, 185, 129, 0.35)',
  },
}
const CONFIDENCE_CAPTION_SX: Record<BudgetForecast['confidence'], SxProps> = {
  low: { fontSize: '0.78rem', color: '#fca5a5', mt: 0.75 },
  medium: { fontSize: '0.78rem', color: AMBER, mt: 0.75 },
  high: { fontSize: '0.78rem', color: MUTED, mt: 0.75 },
}

const NOTE_SX: SxProps = {
  mt: 1.5, p: 1.25, borderRadius: 2, fontSize: '0.78rem', color: '#cbd5e1',
  background: 'rgba(148, 163, 184, 0.08)',
  border: '1px solid rgba(148, 163, 184, 0.18)',
}

const SPEND_BAR_SX: SxProps = {
  height: 8,
  borderRadius: 4,
  backgroundColor: 'rgba(148, 163, 184, 0.18)',
  '& .MuiLinearProgress-bar': { borderRadius: 4, backgroundColor: '#818cf8' },
}
const SPEND_BAR_OVER_SX: SxProps = {
  height: 8,
  borderRadius: 4,
  backgroundColor: 'rgba(148, 163, 184, 0.18)',
  '& .MuiLinearProgress-bar': { borderRadius: 4, backgroundColor: RED },
}

const NET_POSITIVE_SX: SxProps = { ...STAT_VALUE_SX, color: GREEN }
const NET_NEGATIVE_SX: SxProps = { ...STAT_VALUE_SX, color: RED }

// ── Subscriptions ────────────────────────────────────────────────────────────

const PRICE_PANEL_SX: SxProps = {
  p: 1.75,
  borderRadius: 2,
  background: 'rgba(245, 158, 11, 0.10)',
  border: '1px solid rgba(245, 158, 11, 0.32)',
  mb: 2,
}
const PRICE_PANEL_TITLE_SX: SxProps = {
  color: '#fcd34d', fontWeight: 700, fontSize: '0.85rem', display: 'flex',
  alignItems: 'center', gap: 0.75, mb: 1,
}
const PRICE_ROW_SX: SxProps = {
  color: '#fde68a', fontSize: '0.85rem', display: 'flex', alignItems: 'baseline',
  gap: 1, flexWrap: 'wrap', py: 0.35,
}
const PRICE_DATE_SX: SxProps = { color: 'rgba(253, 230, 138, 0.65)', fontSize: '0.72rem' }
const TRENDING_ICON_SX: SxProps = { fontSize: 16 }

const SUB_ROW_SX: SxProps = {
  display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap',
  py: 1.1, borderBottom: '1px solid rgba(148, 163, 184, 0.10)',
}
const SUB_MAIN_SX: SxProps = { minWidth: 200, flex: '1 1 200px' }
const SUB_MERCHANT_SX: SxProps = { color: '#f1f5f9', fontWeight: 600, fontSize: '0.9rem' }
const SUB_META_SX: SxProps = { color: MUTED, fontSize: '0.73rem', mt: 0.25 }
const SUB_NUM_SX: SxProps = { minWidth: 110, textAlign: 'right' }
const SUB_NUM_VALUE_SX: SxProps = { color: TEXT, fontWeight: 700, fontSize: '0.88rem' }
const SUB_NUM_LABEL_SX: SxProps = { color: MUTED, fontSize: '0.68rem' }

const STATUS_CHIP_ACTIVE_SX: SxProps = {
  height: 20, fontSize: '0.65rem', fontWeight: 700,
  backgroundColor: 'rgba(16, 185, 129, 0.12)', color: GREEN,
  border: '1px solid rgba(16, 185, 129, 0.32)',
}
const STATUS_CHIP_LAPSED_SX: SxProps = {
  height: 20, fontSize: '0.65rem', fontWeight: 700,
  backgroundColor: 'rgba(148, 163, 184, 0.10)', color: MUTED,
  border: '1px solid rgba(148, 163, 184, 0.25)',
}

const REGULARITY_TRACK_SX: SxProps = {
  width: 46, height: 4, borderRadius: 2,
  backgroundColor: 'rgba(148, 163, 184, 0.20)',
  overflow: 'hidden',
}
const REGULARITY_FILL_SX: SxProps = { height: '100%', backgroundColor: '#64748b', borderRadius: 2 }
const REGULARITY_WRAP_SX: SxProps = { display: 'flex', alignItems: 'center', gap: 0.75 }

const GROUP_LABEL_SX: SxProps = {
  color: MUTED, fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
  letterSpacing: 0.6, mt: 2, mb: 0.5,
}

// ── Anomalies ────────────────────────────────────────────────────────────────

const ANOMALY_ROW_BASE: SxProps = {
  display: 'flex', gap: 1.5, alignItems: 'flex-start',
  p: 1.5, borderRadius: 2, mb: 1,
  background: 'rgba(148, 163, 184, 0.06)',
}
const ANOMALY_ROW_SX: Record<BudgetAnomaly['severity'], SxProps> = {
  high: { ...ANOMALY_ROW_BASE, borderLeft: `3px solid ${SEVERITY_COLOR.high}` },
  medium: { ...ANOMALY_ROW_BASE, borderLeft: `3px solid ${SEVERITY_COLOR.medium}` },
  low: { ...ANOMALY_ROW_BASE, borderLeft: `3px solid ${SEVERITY_COLOR.low}` },
}
const ANOMALY_TITLE_SX: Record<BudgetAnomaly['severity'], SxProps> = {
  high: { fontWeight: 700, fontSize: '0.88rem', color: SEVERITY_COLOR.high },
  medium: { fontWeight: 700, fontSize: '0.88rem', color: SEVERITY_COLOR.medium },
  low: { fontWeight: 700, fontSize: '0.88rem', color: SEVERITY_COLOR.low },
}
const ANOMALY_DETAIL_SX: SxProps = { color: '#cbd5e1', fontSize: '0.82rem', mt: 0.35 }
const ANOMALY_SIDE_SX: SxProps = { textAlign: 'right', minWidth: 96 }
const ANOMALY_AMOUNT_SX: SxProps = { color: TEXT, fontWeight: 700, fontSize: '0.88rem' }
const ANOMALY_BODY_SX: SxProps = { flex: 1, minWidth: 0 }

// ── Envelopes ────────────────────────────────────────────────────────────────

const ENVELOPE_STATUS_COLOR: Record<BudgetEnvelope['status'], string> = {
  on_track: GREEN,
  slightly_ahead: AMBER,
  ahead_of_pace: ORANGE,
  over: RED,
}
const ENVELOPE_STATUS_LABEL: Record<BudgetEnvelope['status'], string> = {
  on_track: 'On track',
  slightly_ahead: 'Slightly ahead',
  ahead_of_pace: 'Ahead of pace',
  over: 'Over budget',
}
const ENVELOPE_CHIP_SX: Record<BudgetEnvelope['status'], SxProps> = {
  on_track: {
    height: 20, fontSize: '0.65rem', fontWeight: 700, color: GREEN,
    backgroundColor: 'rgba(16, 185, 129, 0.12)', border: '1px solid rgba(16, 185, 129, 0.32)',
  },
  slightly_ahead: {
    height: 20, fontSize: '0.65rem', fontWeight: 700, color: AMBER,
    backgroundColor: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.32)',
  },
  ahead_of_pace: {
    height: 20, fontSize: '0.65rem', fontWeight: 700, color: ORANGE,
    backgroundColor: 'rgba(251, 146, 60, 0.12)', border: '1px solid rgba(251, 146, 60, 0.32)',
  },
  over: {
    height: 20, fontSize: '0.65rem', fontWeight: 700, color: RED,
    backgroundColor: 'rgba(239, 68, 68, 0.12)', border: '1px solid rgba(239, 68, 68, 0.32)',
  },
}

const ENVELOPE_ROW_SX: SxProps = {
  py: 1.5, borderBottom: '1px solid rgba(148, 163, 184, 0.10)',
}
const ENVELOPE_HEAD_SX: SxProps = {
  display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1,
}
const ENVELOPE_CATEGORY_SX: SxProps = { color: '#f1f5f9', fontWeight: 600, fontSize: '0.9rem' }
const ENVELOPE_SPEND_SX: SxProps = { color: MUTED, fontSize: '0.8rem' }
const ENVELOPE_SPACER_SX: SxProps = { flex: 1 }
const ENVELOPE_FOOT_SX: SxProps = {
  display: 'flex', gap: 2, flexWrap: 'wrap', mt: 0.85, color: MUTED, fontSize: '0.74rem',
}

/** The bar has to carry two quantities at once: money spent, and time elapsed. */
const BAR_TRACK_SX: SxProps = {
  position: 'relative',
  height: 10,
  borderRadius: 5,
  backgroundColor: 'rgba(148, 163, 184, 0.18)',
  overflow: 'visible',
}
const BAR_FILL_BASE: SxProps = {
  position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 5,
  transition: 'width 0.25s ease',
}
const BAR_FILL_SX: Record<BudgetEnvelope['status'], SxProps> = {
  on_track: { ...BAR_FILL_BASE, backgroundColor: GREEN },
  slightly_ahead: { ...BAR_FILL_BASE, backgroundColor: AMBER },
  ahead_of_pace: { ...BAR_FILL_BASE, backgroundColor: ORANGE },
  over: { ...BAR_FILL_BASE, backgroundColor: RED },
}
/**
 * The pace marker. Spend to the left of the tick is ahead of the calendar; spend to
 * the right of it is behind. Without the tick a half-full bar means nothing - it is
 * either comfortable or alarming depending on the day of the month.
 */
const PACE_TICK_SX: SxProps = {
  position: 'absolute',
  top: -3,
  bottom: -3,
  width: '2px',
  backgroundColor: '#f8fafc',
  borderRadius: '1px',
  transform: 'translateX(-1px)',
  boxShadow: '0 0 0 1px rgba(15, 23, 42, 0.6)',
}
const PACE_LEGEND_SX: SxProps = {
  color: MUTED, fontSize: '0.72rem', mt: 1.5,
  display: 'flex', alignItems: 'center', gap: 0.75,
}
const PACE_LEGEND_MARK_SX: SxProps = {
  display: 'inline-block', width: '2px', height: 12,
  backgroundColor: '#f8fafc', borderRadius: '1px',
}

const ADD_FORM_SX: SxProps = {
  display: 'flex', gap: 1.25, flexWrap: 'wrap', alignItems: 'center', mt: 2,
}
const FIELD_SX: SxProps = {
  minWidth: 170,
  backgroundColor: 'rgba(255,255,255,0.03)',
  borderRadius: 2,
  input: { color: '#fff', py: 0.9, fontSize: '0.85rem' },
  '.MuiOutlinedInput-notchedOutline': { borderColor: 'rgba(148, 163, 184, 0.25)' },
}
const AMOUNT_FIELD_SX: SxProps = { ...FIELD_SX, minWidth: 130 }
const ADD_BTN_SX: SxProps = { textTransform: 'none', fontWeight: 600, background: '#6366f1' }
const DELETE_BTN_SX: SxProps = { color: '#64748b', '&:hover': { color: RED } }
const DELETE_ICON_SX: SxProps = { fontSize: 18 }
const MUTATION_ERROR_SX: SxProps = { color: '#fca5a5', fontSize: '0.78rem', mt: 1 }

const REFRESH_ICON_SX: SxProps = { fontSize: 16 }

// ── Formatting ───────────────────────────────────────────────────────────────

/**
 * Money as whole rupees.
 *
 * The sign goes outside the symbol - `-₹1,200` rather than `₹-1,200` - because a
 * projected negative net is the one number on this tab a user must not misread.
 */
function money(value: number | null | undefined): string {
  const n = Math.round(value ?? 0)
  const body = Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })
  return n < 0 ? `-₹${body}` : `₹${body}`
}

const MONTH_DAY_FORMAT: Intl.DateTimeFormatOptions = {
  day: 'numeric', month: 'short', year: 'numeric',
}

/** Dates arrive as ISO strings; an unparseable one is shown verbatim rather than "Invalid Date". */
function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('en-IN', MONTH_DAY_FORMAT)
}

function pct(value: number | null | undefined): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}

// ── Shared state components ──────────────────────────────────────────────────

interface SectionCardProps {
  title: string
  subtitle?: string
  children: React.ReactNode
}

const SectionCard = React.memo(function SectionCard({
  title, subtitle, children,
}: SectionCardProps) {
  return (
    <Box sx={CARD_SX}>
      <Box sx={CARD_HEADER_SX}>
        <Typography sx={CARD_TITLE_SX}>{title}</Typography>
        {subtitle ? <Typography sx={CARD_SUBTITLE_SX}>{subtitle}</Typography> : null}
      </Box>
      {children}
    </Box>
  )
})

const SectionSkeleton = React.memo(function SectionSkeleton({ hero = false }: { hero?: boolean }) {
  return (
    <Box>
      {hero ? <Skeleton variant="rectangular" sx={SKELETON_HERO_SX} /> : null}
      <Skeleton variant="rectangular" sx={SKELETON_LINE_SX} />
      <Skeleton variant="rectangular" sx={SKELETON_LINE_SX} />
      <Skeleton variant="rectangular" sx={SKELETON_LINE_SX} />
    </Box>
  )
})

interface SectionErrorProps {
  error: unknown
  fallback: string
  onRetry: () => void
}

/**
 * A per-section failure panel.
 *
 * Each section owns its own query, so one endpoint failing leaves the other three
 * rendered - the alternative, a single guard at the top, blanks the whole tab because
 * anomalies came back 500.
 */
const SectionError = React.memo(function SectionError({
  error, fallback, onRetry,
}: SectionErrorProps) {
  return (
    <Box sx={ERROR_PANEL_SX}>
      <span>{budgetErrorDetail(error, fallback)}</span>
      <Button
        size="small"
        variant="outlined"
        onClick={onRetry}
        startIcon={<RefreshIcon sx={REFRESH_ICON_SX} />}
        sx={RETRY_BTN_SX}
      >
        Retry
      </Button>
    </Box>
  )
})

const Stat = React.memo(function Stat({
  label, value, valueSx,
}: { label: string; value: string; valueSx?: SxProps }) {
  return (
    <Box>
      <Typography sx={STAT_LABEL_SX}>{label}</Typography>
      <Typography sx={valueSx ?? STAT_VALUE_SX}>{value}</Typography>
    </Box>
  )
})

// ── 1. Safe to spend ─────────────────────────────────────────────────────────

const ForecastBody = React.memo(function ForecastBody({ data }: { data: BudgetForecast }) {
  // A forecast with no `as_of` is the server saying it had nothing to work with. The
  // scalars are all zero in that case, and rendering "₹0 /day" would read as a real
  // (and alarming) answer rather than an absence of data.
  if (!data.as_of) {
    return <Typography sx={EMPTY_SX}>Not enough data yet.</Typography>
  }

  const daily = data.safe_to_spend_daily
  const spendPct = data.typical_monthly_spend > 0
    ? pct((data.spent_this_month / data.typical_monthly_spend) * 100)
    : 0
  const overTypical = data.spent_this_month > data.typical_monthly_spend
  const netPositive = data.projected_month_end_net >= 0

  return (
    <Box>
      <Box sx={HERO_SX}>
        <Typography sx={daily >= 0 ? HERO_NUMBER_POSITIVE_SX : HERO_NUMBER_NEGATIVE_SX}>
          {money(daily)}
        </Typography>
        <Typography sx={HERO_UNIT_SX}>/day</Typography>
        <Chip
          size="small"
          label={CONFIDENCE_LABEL[data.confidence]}
          sx={CONFIDENCE_CHIP_SX[data.confidence]}
        />
      </Box>

      <Typography sx={HERO_CONTEXT_SX}>
        {money(data.safe_to_spend_total)} left for {data.days_remaining}{' '}
        {data.days_remaining === 1 ? 'day' : 'days'}
        {data.month ? ` in ${data.month}` : ''}
      </Typography>

      {/*
        Confidence is stated in words, not just as a chip. "low" means one month of
        history or less, and a daily allowance derived from a single month is a guess -
        presenting it without that sentence would present a guess as a projection.
      */}
      <Typography sx={CONFIDENCE_CAPTION_SX[data.confidence]}>
        {CONFIDENCE_TEXT[data.confidence]}
      </Typography>

      {data.available_balance === null ? (
        <Box sx={NOTE_SX}>
          Your statements carry no running balance, so this is projected from your typical
          income rather than a real account balance.
        </Box>
      ) : null}

      <Divider sx={DIVIDER_SX} />

      <Box>
        <Box sx={CARD_HEADER_SX}>
          <Typography sx={MUTED_TEXT_SX}>Spent this month</Typography>
          <Typography sx={MUTED_TEXT_SX}>
            {money(data.spent_this_month)} of {money(data.typical_monthly_spend)} typical
          </Typography>
        </Box>
        <LinearProgress
          variant="determinate"
          value={spendPct}
          sx={overTypical ? SPEND_BAR_OVER_SX : SPEND_BAR_SX}
        />
      </Box>

      <Divider sx={DIVIDER_SX} />

      <Box sx={STAT_ROW_SX}>
        <Stat
          label="Projected month end"
          value={money(data.projected_month_end_net)}
          valueSx={netPositive ? NET_POSITIVE_SX : NET_NEGATIVE_SX}
        />
        <Stat
          label="Available balance"
          value={data.available_balance === null ? 'Not in statements' : money(data.available_balance)}
        />
        <Stat label="Income still expected" value={money(data.income_still_expected)} />
        <Stat label="Committed upcoming" value={money(data.committed_upcoming_total)} />
        <Stat label="Days elapsed" value={`${data.days_elapsed}`} />
      </Box>
    </Box>
  )
})

const ForecastSection = React.memo(function ForecastSection({ sessionId }: InsightsTabProps) {
  const { data, isPending, isError, error, refetch } = useBudgetForecast(sessionId)
  const retry = useCallback(() => { void refetch() }, [refetch])

  return (
    <SectionCard title="Safe to spend" subtitle="What is left after committed spend">
      {isPending ? <SectionSkeleton hero /> : null}
      {isError ? (
        <SectionError error={error} fallback="Could not load the forecast." onRetry={retry} />
      ) : null}
      {!isPending && !isError && data ? <ForecastBody data={data} /> : null}
    </SectionCard>
  )
})

// ── 2. Subscriptions ─────────────────────────────────────────────────────────

const PriceIncreaseRow = React.memo(function PriceIncreaseRow({
  change,
}: { change: BudgetPriceChange & { merchant: string } }) {
  return (
    <Box sx={PRICE_ROW_SX}>
      <strong>{change.merchant}</strong>
      <span>
        went from {money(change.from)} to {money(change.to)} (
        {change.change_pct >= 0 ? '+' : ''}{Math.round(change.change_pct)}%)
      </span>
      <Typography component="span" sx={PRICE_DATE_SX}>{formatDate(change.date)}</Typography>
    </Box>
  )
})

const SubscriptionRow = React.memo(function SubscriptionRow({
  sub,
}: { sub: BudgetRecurring }) {
  const isActive = sub.status === 'active'
  const regularityPct = pct(sub.regularity * 100)

  return (
    <Box sx={SUB_ROW_SX}>
      <Box sx={SUB_MAIN_SX}>
        <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap">
          <Typography component="span" sx={SUB_MERCHANT_SX}>{sub.merchant}</Typography>
          <Chip
            size="small"
            label={isActive ? 'active' : `lapsed · last seen ${formatDate(sub.last_seen)}`}
            sx={isActive ? STATUS_CHIP_ACTIVE_SX : STATUS_CHIP_LAPSED_SX}
          />
        </Stack>
        <Typography sx={SUB_META_SX}>
          {sub.cadence} · {sub.occurrences} charge{sub.occurrences === 1 ? '' : 's'}
          {isActive && sub.next_expected ? ` · next ${formatDate(sub.next_expected)}` : ''}
        </Typography>
      </Box>

      {/*
        Regularity is how evenly spaced the charges are, 0-1. It is the reason to trust
        or discount `next_expected`, so it sits next to it rather than being dropped.
      */}
      <Tooltip title={`Regularity ${regularityPct.toFixed(0)}% — how evenly spaced these charges are`}>
        <Box sx={REGULARITY_WRAP_SX}>
          <Box sx={REGULARITY_TRACK_SX}>
            <Box sx={REGULARITY_FILL_SX} style={{ width: `${regularityPct}%` }} />
          </Box>
          <Typography component="span" sx={SUB_NUM_LABEL_SX}>
            {regularityPct.toFixed(0)}%
          </Typography>
        </Box>
      </Tooltip>

      <Box sx={SUB_NUM_SX}>
        <Typography sx={SUB_NUM_VALUE_SX}>{money(sub.typical_amount)}</Typography>
        <Typography sx={SUB_NUM_LABEL_SX}>typical</Typography>
      </Box>
      <Box sx={SUB_NUM_SX}>
        <Typography sx={SUB_NUM_VALUE_SX}>{money(sub.annualised_cost)}</Typography>
        <Typography sx={SUB_NUM_LABEL_SX}>per year</Typography>
      </Box>
    </Box>
  )
})

const RecurringSection = React.memo(function RecurringSection({ sessionId }: InsightsTabProps) {
  const { data, isPending, isError, error, refetch } = useBudgetRecurring(sessionId)
  const retry = useCallback(() => { void refetch() }, [refetch])

  // Active before lapsed, order preserved inside each group: the API already sorts by
  // annualised cost, and re-sorting here would throw that away.
  const grouped = useMemo(() => {
    const subs = data?.subscriptions ?? []
    return {
      active: subs.filter(s => s.status === 'active'),
      lapsed: subs.filter(s => s.status !== 'active'),
    }
  }, [data])

  const subtitle = data
    ? `${money(data.monthly_commitment)}/month committed · ${money(data.annual_commitment)}/year`
    : undefined

  return (
    <SectionCard title="Subscriptions" subtitle={subtitle}>
      {isPending ? <SectionSkeleton /> : null}
      {isError ? (
        <SectionError error={error} fallback="Could not load subscriptions." onRetry={retry} />
      ) : null}

      {!isPending && !isError && data ? (
        <Box>
          <Box sx={STAT_ROW_SX}>
            <Stat label="Active" value={`${data.active_count}`} />
            <Stat label="Lapsed" value={`${data.lapsed_count}`} />
            <Stat label="Monthly commitment" value={money(data.monthly_commitment)} />
            <Stat label="Annual commitment" value={money(data.annual_commitment)} />
          </Box>

          <Divider sx={DIVIDER_SX} />

          {/*
            Price increases lead. Everything else in this section is a statement of what
            the user already agreed to; this is the part they did not agree to and can
            still act on.
          */}
          {data.price_increases.length > 0 ? (
            <Box sx={PRICE_PANEL_SX}>
              <Typography sx={PRICE_PANEL_TITLE_SX}>
                <TrendingUpIcon sx={TRENDING_ICON_SX} />
                {data.price_increases.length} price increase
                {data.price_increases.length === 1 ? '' : 's'} detected
              </Typography>
              {data.price_increases.map((change, i) => (
                <PriceIncreaseRow key={`${change.merchant}-${change.date}-${i}`} change={change} />
              ))}
            </Box>
          ) : null}

          {data.subscriptions.length === 0 ? (
            <Typography sx={EMPTY_SX}>No recurring charges found.</Typography>
          ) : (
            <Box>
              {grouped.active.length > 0 ? (
                <>
                  <Typography sx={GROUP_LABEL_SX}>Active</Typography>
                  {grouped.active.map(sub => (
                    <SubscriptionRow key={`${sub.account_key}-${sub.merchant}`} sub={sub} />
                  ))}
                </>
              ) : null}
              {grouped.lapsed.length > 0 ? (
                <>
                  <Typography sx={GROUP_LABEL_SX}>Lapsed</Typography>
                  {grouped.lapsed.map(sub => (
                    <SubscriptionRow key={`${sub.account_key}-${sub.merchant}`} sub={sub} />
                  ))}
                </>
              ) : null}
            </Box>
          )}
        </Box>
      ) : null}
    </SectionCard>
  )
})

// ── 3. Anomalies ─────────────────────────────────────────────────────────────

const AnomalyRow = React.memo(function AnomalyRow({ anomaly }: { anomaly: BudgetAnomaly }) {
  return (
    <Box sx={ANOMALY_ROW_SX[anomaly.severity]}>
      <Box sx={ANOMALY_BODY_SX}>
        <Typography sx={ANOMALY_TITLE_SX[anomaly.severity]}>{anomaly.title}</Typography>
        {/*
          `detail` is user-facing prose written by the backend, which is the only place
          that knows the baseline it compared against. Rendered verbatim.
        */}
        <Typography sx={ANOMALY_DETAIL_SX}>{anomaly.detail}</Typography>
      </Box>
      <Box sx={ANOMALY_SIDE_SX}>
        <Typography sx={ANOMALY_AMOUNT_SX}>{money(anomaly.amount)}</Typography>
        <Typography sx={CAPTION_SX}>{formatDate(anomaly.date)}</Typography>
      </Box>
    </Box>
  )
})

const AnomaliesSection = React.memo(function AnomaliesSection({ sessionId }: InsightsTabProps) {
  const { data, isPending, isError, error, refetch } = useBudgetAnomalies(sessionId)
  const retry = useCallback(() => { void refetch() }, [refetch])

  const subtitle = data && data.count > 0
    ? `${data.count} flagged · ${data.high_severity_count} high severity`
    : undefined

  return (
    <SectionCard title="Anomalies" subtitle={subtitle}>
      {isPending ? <SectionSkeleton /> : null}
      {isError ? (
        <SectionError error={error} fallback="Could not load anomalies." onRetry={retry} />
      ) : null}
      {!isPending && !isError && data ? (
        data.anomalies.length === 0 ? (
          <Typography sx={EMPTY_SX}>Nothing unusual found.</Typography>
        ) : (
          <Box>
            {data.anomalies.map((anomaly, i) => (
              <AnomalyRow key={`${anomaly.type}-${anomaly.date}-${i}`} anomaly={anomaly} />
            ))}
          </Box>
        )
      ) : null}
    </SectionCard>
  )
})

// ── 4. Envelopes ─────────────────────────────────────────────────────────────

interface EnvelopeRowProps {
  envelope: BudgetEnvelope
  onDelete: (category: string) => void
  busy: boolean
}

const EnvelopeRow = React.memo(function EnvelopeRow({
  envelope, onDelete, busy,
}: EnvelopeRowProps) {
  const handleDelete = useCallback(() => onDelete(envelope.category), [onDelete, envelope.category])
  const usedWidth = pct(envelope.used_pct)
  const paceLeft = pct(envelope.month_progress_pct)

  return (
    <Box sx={ENVELOPE_ROW_SX}>
      <Box sx={ENVELOPE_HEAD_SX}>
        <Typography component="span" sx={ENVELOPE_CATEGORY_SX}>{envelope.category}</Typography>
        <Chip
          size="small"
          label={ENVELOPE_STATUS_LABEL[envelope.status]}
          sx={ENVELOPE_CHIP_SX[envelope.status]}
        />
        <Box sx={ENVELOPE_SPACER_SX} />
        <Typography component="span" sx={ENVELOPE_SPEND_SX}>
          {money(envelope.spent)} of {money(envelope.monthly_cap)}
        </Typography>
        <Tooltip title="Remove this budget">
          <span>
            <IconButton size="small" onClick={handleDelete} disabled={busy} sx={DELETE_BTN_SX}>
              <DeleteOutlineIcon sx={DELETE_ICON_SX} />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      <Tooltip
        title={`${usedWidth.toFixed(0)}% of budget used · ${paceLeft.toFixed(0)}% through the month`}
      >
        <Box sx={BAR_TRACK_SX}>
          <Box sx={BAR_FILL_SX[envelope.status]} style={{ width: `${usedWidth}%` }} />
          <Box sx={PACE_TICK_SX} style={{ left: `${paceLeft}%` }} />
        </Box>
      </Tooltip>

      <Box sx={ENVELOPE_FOOT_SX}>
        <span>Daily allowance {money(envelope.daily_allowance)}</span>
        <span>Projected month end {money(envelope.projected_month_end)}</span>
        <span>Remaining {money(envelope.remaining)}</span>
      </Box>
    </Box>
  )
})

const EnvelopesSection = React.memo(function EnvelopesSection({ sessionId }: InsightsTabProps) {
  const { data, isPending, isError, error, refetch } = useBudgetEnvelopes(sessionId)
  const setEnvelope = useSetBudgetEnvelope()
  const retry = useCallback(() => { void refetch() }, [refetch])

  const [category, setCategory] = useState('')
  const [amount, setAmount] = useState('')

  const parsedAmount = Number(amount)
  const canAdd = category.trim().length > 0
    && amount.trim().length > 0
    && Number.isFinite(parsedAmount)
    && parsedAmount >= 0

  const { mutate } = setEnvelope

  const handleAdd = useCallback(() => {
    const trimmed = category.trim()
    const value = Number(amount)
    if (!trimmed || !amount.trim() || !Number.isFinite(value) || value < 0) return
    mutate({ category: trimmed, monthlyCap: value })
    setCategory('')
    setAmount('')
  }, [category, amount, mutate])

  /**
   * Clearing an envelope sends `null`, not `0`.
   *
   * They are different instructions: `null` removes the budget so the category stops
   * being tracked, `0` sets a budget of zero rupees, which makes every category
   * permanently "over". Sending 0 here would look like a delete and behave like an
   * alarm that never turns off.
   */
  const handleDelete = useCallback((cat: string) => {
    mutate({ category: cat, monthlyCap: null })
  }, [mutate])

  const handleCategoryChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setCategory(e.target.value), [],
  )
  const handleAmountChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => setAmount(e.target.value), [],
  )

  const envelopes = data ?? []

  return (
    <SectionCard title="Budget envelopes" subtitle="Spend against a monthly cap, paced by the calendar">
      {isPending ? <SectionSkeleton /> : null}
      {isError ? (
        <SectionError error={error} fallback="Could not load budget envelopes." onRetry={retry} />
      ) : null}

      {!isPending && !isError ? (
        <Box>
          {envelopes.length === 0 ? (
            <Typography sx={EMPTY_SX}>
              No budgets set. An envelope caps a category for the month and tracks your spend
              against how far through the month you are — so you can see whether you are
              overspending, not just how much you have spent.
            </Typography>
          ) : (
            <Box>
              {envelopes.map(env => (
                <EnvelopeRow
                  key={env.category}
                  envelope={env}
                  onDelete={handleDelete}
                  busy={setEnvelope.isPending}
                />
              ))}
              <Box sx={PACE_LEGEND_SX}>
                <Box component="span" sx={PACE_LEGEND_MARK_SX} />
                <span>marks how far through the month you are — fill past it means overspending</span>
              </Box>
            </Box>
          )}

          <Box sx={ADD_FORM_SX}>
            <TextField
              size="small"
              placeholder="Category"
              value={category}
              onChange={handleCategoryChange}
              sx={FIELD_SX}
            />
            <TextField
              size="small"
              type="number"
              placeholder="Monthly cap ₹"
              value={amount}
              onChange={handleAmountChange}
              sx={AMOUNT_FIELD_SX}
            />
            <Button
              variant="contained"
              size="small"
              onClick={handleAdd}
              disabled={!canAdd || setEnvelope.isPending}
              sx={ADD_BTN_SX}
            >
              Add budget
            </Button>
          </Box>

          {setEnvelope.isError ? (
            <Typography sx={MUTATION_ERROR_SX}>
              {budgetErrorDetail(setEnvelope.error, 'Could not save that budget.')}
            </Typography>
          ) : null}
        </Box>
      ) : null}
    </SectionCard>
  )
})

// ── Tab ──────────────────────────────────────────────────────────────────────

/**
 * The four derived views over the uploaded statements.
 *
 * Each section owns its own query and its own pending/error state, so a 500 from one
 * endpoint costs the user that panel and nothing else.
 */
function InsightsTab({ sessionId }: InsightsTabProps) {
  return (
    <Box sx={ROOT_SX}>
      <ForecastSection sessionId={sessionId} />
      <RecurringSection sessionId={sessionId} />
      <AnomaliesSection sessionId={sessionId} />
      <EnvelopesSection sessionId={sessionId} />
    </Box>
  )
}

export default React.memo(InsightsTab)
