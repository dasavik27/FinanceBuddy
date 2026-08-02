import React, { useMemo } from 'react'
import { Box, Button, Card, Chip, Skeleton, Typography } from '@mui/material'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'

import { budgetErrorDetail, useBudgetNetWorth } from '../hooks/useBudget'
import type { BudgetNetWorth } from '../types'

/**
 * Net worth across every domain, as a single strip.
 *
 * The one thing this component must never do is print a confident number that is missing
 * a piece. Net worth is assembled from several domains, any of which can fail to read
 * independently, and a failure there does not fail the request - it comes back in
 * `unavailable_domains` with the total silently short by whatever that domain holds. A
 * user seeing "₹4,20,000" has no way to know their mutual funds are not in it.
 *
 * So `unavailable_domains` is rendered as prominently as the shortfall warrants, and a
 * query that errored outright renders no figure at all rather than a zero.
 */

const CARD_SX = {
  px: 2.5, py: 2, mb: 3, borderRadius: 2,
  backgroundColor: 'rgba(30, 41, 59, 0.5)',
  border: '1px solid rgba(148, 163, 184, 0.15)',
  color: '#e2e8f0',
} as const

const ERROR_CARD_SX = {
  ...CARD_SX,
  py: 1.25,
  display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap',
  backgroundColor: 'rgba(239, 68, 68, 0.08)',
  border: '1px solid rgba(239, 68, 68, 0.3)',
} as const

const TOP_ROW_SX = {
  display: 'flex', alignItems: 'flex-end', gap: 4, flexWrap: 'wrap',
} as const

const LABEL_SX = {
  color: '#94a3b8', fontSize: '0.72rem', fontWeight: 700,
  textTransform: 'uppercase', letterSpacing: 0.6,
} as const

const MUTED_SX = { color: '#94a3b8', fontSize: '0.8rem' } as const

const HEADLINE_SX = { fontWeight: 800, fontSize: '2rem', lineHeight: 1.1 } as const
const HEADLINE_POSITIVE_SX = { ...HEADLINE_SX, color: '#34d399' } as const
const HEADLINE_NEGATIVE_SX = { ...HEADLINE_SX, color: '#f87171' } as const

const SUB_FIGURES_SX = {
  display: 'flex', gap: 3.5, flexWrap: 'wrap',
} as const

const SUB_VALUE_SX = { fontWeight: 700, fontSize: '1.05rem', color: '#e2e8f0' } as const
const SUB_VALUE_DEBT_SX = { ...SUB_VALUE_SX, color: '#f87171' } as const

const BAR_TRACK_SX = {
  display: 'flex', height: 8, mt: 2, borderRadius: 4, overflow: 'hidden',
  backgroundColor: 'rgba(148, 163, 184, 0.12)',
} as const

const BAR_LEGEND_SX = {
  display: 'flex', justifyContent: 'space-between', mt: 0.6, gap: 2, flexWrap: 'wrap',
} as const

const BREAKDOWN_ROW_SX = {
  display: 'flex', gap: 4, flexWrap: 'wrap', mt: 2,
  pt: 1.75, borderTop: '1px solid rgba(148, 163, 184, 0.12)',
} as const

const BREAKDOWN_COLUMN_SX = { minWidth: 220, flex: '1 1 240px' } as const

const BREAKDOWN_ITEM_SX = {
  display: 'flex', alignItems: 'center', gap: 1,
  justifyContent: 'space-between', py: 0.4,
} as const

const DOMAIN_CHIP_SX = {
  height: 18, fontSize: '0.62rem', fontWeight: 700,
  backgroundColor: 'rgba(148, 163, 184, 0.12)',
  color: '#94a3b8',
  border: '1px solid rgba(148, 163, 184, 0.2)',
} as const

const UNAVAILABLE_SX = {
  display: 'flex', alignItems: 'flex-start', gap: 1,
  mt: 2, px: 1.5, py: 1, borderRadius: 1.5,
  fontSize: '0.8rem', color: '#fcd34d',
  backgroundColor: 'rgba(245, 158, 11, 0.10)',
  border: '1px solid rgba(245, 158, 11, 0.30)',
} as const

const ASSET_BAR_SX = { backgroundColor: '#34d399' } as const
const LIABILITY_BAR_SX = { backgroundColor: '#f87171' } as const

/** Domain keys as the backend sends them, in human words. */
const DOMAIN_LABELS: Record<string, string> = {
  budget: 'bank accounts',
  mutual_funds: 'mutual funds',
  equity: 'equity',
}

function money(value: number): string {
  const magnitude = Math.abs(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })
  return `${value < 0 ? '-' : ''}₹${magnitude}`
}

function domainWords(domain: string): string {
  return DOMAIN_LABELS[domain] ?? domain.replace(/_/g, ' ')
}

/** "mutual funds", "mutual funds and equity", "a, b and c". */
function joinWords(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

interface BreakdownListProps {
  title: string
  items: BudgetNetWorth['breakdown']
  negative: boolean
}

function BreakdownList({ title, items, negative }: BreakdownListProps) {
  if (items.length === 0) return null

  return (
    <Box sx={BREAKDOWN_COLUMN_SX}>
      <Typography sx={LABEL_SX}>{title}</Typography>
      {items.map(item => (
        <Box key={`${item.domain}-${item.label}`} sx={BREAKDOWN_ITEM_SX}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, minWidth: 0 }}>
            <Chip size="small" label={item.domain} sx={DOMAIN_CHIP_SX} />
            <Typography
              sx={{
                color: '#cbd5e1', fontSize: '0.82rem',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
              title={item.label}
            >
              {item.label}
            </Typography>
          </Box>
          <Typography
            sx={{
              fontSize: '0.82rem', fontWeight: 700, whiteSpace: 'nowrap',
              color: negative ? '#f87171' : '#e2e8f0',
            }}
          >
            {money(negative ? -Math.abs(item.value) : item.value)}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}

const MemoBreakdownList = React.memo(BreakdownList)

interface NetWorthRibbonProps {
  sessionId: string
}

function NetWorthRibbon({ sessionId }: NetWorthRibbonProps) {
  const { data, isPending, isError, error, refetch } = useBudgetNetWorth(sessionId)

  const breakdown = data?.breakdown
  const { assets: assetItems, liabilities: liabilityItems } = useMemo(() => {
    const grouped: { assets: BudgetNetWorth['breakdown']; liabilities: BudgetNetWorth['breakdown'] } =
      { assets: [], liabilities: [] }
    for (const item of breakdown ?? []) {
      if (item.kind === 'liability') grouped.liabilities.push(item)
      else grouped.assets.push(item)
    }
    return grouped
  }, [breakdown])

  if (isPending) {
    return (
      <Skeleton
        variant="rounded"
        height={150}
        sx={{ mb: 3, bgcolor: 'rgba(148,163,184,0.08)' }}
      />
    )
  }

  // No figure is shown here on purpose. A ribbon that failed to load has to read as
  // "unknown", never as a number - and it stays one line, because it is a strip on top
  // of a page rather than the page itself.
  if (isError || !data) {
    return (
      <Card sx={ERROR_CARD_SX}>
        <Typography sx={{ color: '#fca5a5', fontSize: '0.85rem' }}>
          Net worth unavailable — {budgetErrorDetail(error, 'could not be calculated.')}
        </Typography>
        <Button
          size="small"
          onClick={() => refetch()}
          sx={{ color: '#fca5a5', textTransform: 'none', py: 0, minWidth: 0 }}
        >
          Retry
        </Button>
      </Card>
    )
  }

  const assetTotal = Math.abs(data.assets)
  const liabilityTotal = Math.abs(data.liabilities)
  const barTotal = assetTotal + liabilityTotal
  const assetPct = barTotal > 0 ? (assetTotal / barTotal) * 100 : 0

  const missing = data.unavailable_domains ?? []

  return (
    <Card sx={CARD_SX}>
      <Box sx={TOP_ROW_SX}>
        <Box>
          <Typography sx={LABEL_SX}>Net worth</Typography>
          <Typography sx={data.net_worth < 0 ? HEADLINE_NEGATIVE_SX : HEADLINE_POSITIVE_SX}>
            {money(data.net_worth)}
          </Typography>
        </Box>

        <Box sx={SUB_FIGURES_SX}>
          <Box>
            <Typography sx={LABEL_SX}>Cash</Typography>
            <Typography sx={SUB_VALUE_SX}>{money(data.cash)}</Typography>
          </Box>
          <Box>
            <Typography sx={LABEL_SX}>Investments</Typography>
            <Typography sx={SUB_VALUE_SX}>{money(data.investments)}</Typography>
          </Box>
          <Box>
            <Typography sx={LABEL_SX}>Card debt</Typography>
            <Typography sx={SUB_VALUE_DEBT_SX}>
              {money(-Math.abs(data.card_debt))}
            </Typography>
          </Box>
        </Box>
      </Box>

      {barTotal > 0 && (
        <>
          <Box sx={BAR_TRACK_SX}>
            <Box
              sx={{ ...ASSET_BAR_SX, width: `${assetPct}%` }}
              title={`Assets ${money(assetTotal)}`}
            />
            <Box
              sx={{ ...LIABILITY_BAR_SX, width: `${100 - assetPct}%` }}
              title={`Liabilities ${money(liabilityTotal)}`}
            />
          </Box>
          <Box sx={BAR_LEGEND_SX}>
            <Typography sx={{ ...MUTED_SX, color: '#34d399' }}>
              Assets {money(assetTotal)}
            </Typography>
            <Typography sx={{ ...MUTED_SX, color: '#f87171' }}>
              Liabilities {money(liabilityTotal)}
            </Typography>
          </Box>
        </>
      )}

      {(assetItems.length > 0 || liabilityItems.length > 0) && (
        <Box sx={BREAKDOWN_ROW_SX}>
          <MemoBreakdownList title="Assets" items={assetItems} negative={false} />
          <MemoBreakdownList title="Liabilities" items={liabilityItems} negative />
        </Box>
      )}

      {missing.length > 0 && (
        <Box sx={UNAVAILABLE_SX}>
          <WarningAmberIcon sx={{ fontSize: 16, mt: '1px', flexShrink: 0 }} />
          <span>
            Excludes {joinWords(missing.map(domainWords))} — could not be loaded. The
            figure above is missing whatever{' '}
            {missing.length === 1 ? 'it holds' : 'they hold'}.
          </span>
        </Box>
      )}
    </Card>
  )
}

export default React.memo(NetWorthRibbon)
