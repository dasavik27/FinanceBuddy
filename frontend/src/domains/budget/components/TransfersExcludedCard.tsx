import React, { useMemo, useState } from 'react'
import {
  Box, Card, Typography, Chip, Collapse, Button, Table, TableBody, TableCell,
  TableHead, TableRow, Skeleton, Tooltip,
} from '@mui/material'
import SwapHorizIcon from '@mui/icons-material/SwapHoriz'
import CreditCardIcon from '@mui/icons-material/CreditCard'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'

import { budgetErrorDetail, useBudgetTransfers } from '../hooks/useBudget'
import type { BudgetTransferPair } from '../types'

/**
 * Why the totals are lower than the sum of the statements.
 *
 * Moving money between your own accounts used to be counted as income *and* expense,
 * and a credit-card bill payment was counted as spending on top of the purchases it
 * settled. Both are now netted out, which is correct - but it means the dashboard shows
 * smaller numbers than a user adding up their statements by hand would get, sometimes
 * by lakhs. An unexplained correction of that size reads as a bug.
 *
 * So this card exists to be auditable rather than merely informative: it names the
 * amount removed from each side and lists every pair behind it. The pairing is a
 * heuristic, and a heuristic the user cannot inspect is one they cannot trust.
 */

const CARD_SX = {
  p: 2.5, mb: 3, borderRadius: 2,
  backgroundColor: 'rgba(167, 139, 250, 0.07)',
  border: '1px solid rgba(167, 139, 250, 0.25)',
} as const

const HEADER_ROW_SX = {
  display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap',
} as const

const TITLE_SX = { fontWeight: 700, color: '#e2e8f0', fontSize: '1rem' } as const
const MUTED_SX = { color: '#94a3b8', fontSize: '0.85rem' } as const

const FIGURE_STRIP_SX = {
  display: 'flex', gap: 3, flexWrap: 'wrap', mt: 1.5,
} as const

const HEAD_CELL_SX = {
  color: '#94a3b8', fontWeight: 700, fontSize: '0.75rem',
  borderBottom: '1px solid rgba(148, 163, 184, 0.2)',
} as const

const BODY_CELL_SX = {
  color: '#cbd5e1', fontSize: '0.8rem',
  borderBottom: '1px solid rgba(148, 163, 184, 0.08)',
} as const

/** Pairs rendered before the "show all" prompt. Two screens' worth: enough to
 *  see the pattern, small enough to mount instantly. */
const PAIRS_PREVIEW = 50

const CONFIDENCE_COLOURS: Record<string, string> = {
  high: '#34d399',
  medium: '#fbbf24',
  low: '#94a3b8',
}

/** The heuristic's own uncertainty, stated plainly rather than hidden behind a colour. */
const CONFIDENCE_HELP: Record<string, string> = {
  high: 'Same day, and the narration on both sides mentions a transfer.',
  medium: 'Either same day, or the narration corroborates it — not both.',
  low: 'Matched on amount and a few days’ gap alone. Worth checking.',
}

function money(value: number): string {
  return `₹${value.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

function shortAccount(key: string): string {
  // "HDFC:credit_card:1234" -> "HDFC Credit Card ••1234"
  const [bank, kind, last4] = String(key).split(':')
  const pretty = (kind || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
  return `${bank} ${pretty}${last4 && last4 !== '-' ? ` ••${last4}` : ''}`
}

interface TransfersExcludedCardProps {
  sessionId: string
}

function TransfersExcludedCard({ sessionId }: TransfersExcludedCardProps) {
  const [expanded, setExpanded] = useState(false)
  const { data, isPending, isError, error, refetch } = useBudgetTransfers(sessionId)

  const pairs: BudgetTransferPair[] = useMemo(() => data?.pairs ?? [], [data])

  /*
   * The table renders a capped window, not the whole list.
   *
   * GET /transfers deliberately returns every pair - the pairing is a heuristic and a
   * number the user cannot audit is a number they will not trust - but a multi-account
   * year produces thousands, and every one of them was mounted the moment the section
   * expanded: five MUI TableCells plus a Tooltip and two Chips each. Collapse's
   * unmountOnExit meant the cost only landed on expand, which made it a click that
   * visibly froze the tab rather than a slow page load.
   *
   * Auditing is still possible - "show all" is one click - but the default is a window
   * that renders instantly.
   */
  const [showAllPairs, setShowAllPairs] = useState(false)
  const visiblePairs = showAllPairs ? pairs : pairs.slice(0, PAIRS_PREVIEW)
  const hiddenPairCount = pairs.length - visiblePairs.length

  if (isPending) {
    return <Skeleton variant="rounded" height={110} sx={{ mb: 3, bgcolor: 'rgba(148,163,184,0.08)' }} />
  }

  if (isError) {
    return (
      <Card sx={{ ...CARD_SX, backgroundColor: 'rgba(239, 68, 68, 0.08)', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
        <Typography sx={{ color: '#fca5a5', fontSize: '0.9rem' }}>
          {budgetErrorDetail(error, 'Could not load transfer detail.')}
        </Typography>
        <Button size="small" onClick={() => refetch()} sx={{ mt: 1, color: '#fca5a5' }}>
          Retry
        </Button>
      </Card>
    )
  }

  // Nothing was netted out, so there is nothing to explain and no card to show.
  if (!data || data.count === 0) return null

  return (
    <Card sx={CARD_SX}>
      <Box sx={HEADER_ROW_SX}>
        <SwapHorizIcon sx={{ color: '#a78bfa' }} />
        <Typography sx={TITLE_SX}>
          {data.count} transfer{data.count === 1 ? '' : 's'} between your own accounts
        </Typography>
        {data.card_payment_total > 0 && (
          <Chip
            size="small"
            icon={<CreditCardIcon sx={{ fontSize: 14 }} />}
            label={`${money(data.card_payment_total)} card bill payments`}
            sx={{ backgroundColor: 'rgba(167,139,250,0.18)', color: '#c4b5fd', fontWeight: 600 }}
          />
        )}
      </Box>

      <Typography sx={{ ...MUTED_SX, mt: 1 }}>
        Money you moved between your own accounts is not income and not spending, so it is
        excluded from every figure below. Without this, a transfer would be counted twice —
        once leaving one account and once arriving in the other.
      </Typography>

      <Box sx={FIGURE_STRIP_SX}>
        <Box>
          <Typography sx={MUTED_SX}>Excluded from income</Typography>
          <Typography sx={{ color: '#34d399', fontWeight: 800, fontSize: '1.1rem' }}>
            {money(data.excluded_from_income)}
          </Typography>
        </Box>
        <Box>
          <Typography sx={MUTED_SX}>Excluded from spending</Typography>
          <Typography sx={{ color: '#f87171', fontWeight: 800, fontSize: '1.1rem' }}>
            {money(data.excluded_from_expense)}
          </Typography>
        </Box>
      </Box>

      <Button
        size="small"
        onClick={() => setExpanded(v => !v)}
        endIcon={expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
        sx={{ mt: 1.5, color: '#a78bfa', textTransform: 'none', fontWeight: 600 }}
      >
        {expanded ? 'Hide' : 'Show'} the {data.count} matched pair{data.count === 1 ? '' : 's'}
      </Button>

      <Collapse in={expanded} unmountOnExit>
        <Box sx={{ mt: 1.5, overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={HEAD_CELL_SX}>From</TableCell>
                <TableCell sx={HEAD_CELL_SX}>To</TableCell>
                <TableCell sx={HEAD_CELL_SX} align="right">Amount</TableCell>
                <TableCell sx={HEAD_CELL_SX}>Date</TableCell>
                <TableCell sx={HEAD_CELL_SX}>Match</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visiblePairs.map(pair => (
                <TableRow key={`${pair.debit_txn_id}-${pair.credit_txn_id}`}>
                  <TableCell sx={BODY_CELL_SX}>{shortAccount(pair.from_account)}</TableCell>
                  <TableCell sx={BODY_CELL_SX}>
                    {shortAccount(pair.to_account)}
                    {pair.is_card_payment && (
                      <Chip
                        size="small" label="bill payment"
                        sx={{ ml: 1, height: 18, fontSize: '0.65rem', backgroundColor: 'rgba(167,139,250,0.18)', color: '#c4b5fd' }}
                      />
                    )}
                  </TableCell>
                  <TableCell sx={BODY_CELL_SX} align="right">{money(pair.amount)}</TableCell>
                  <TableCell sx={BODY_CELL_SX}>
                    {pair.debit_date}
                    {pair.lag_days !== 0 && (
                      <Typography component="span" sx={{ ...MUTED_SX, ml: 0.5, fontSize: '0.7rem' }}>
                        (+{pair.lag_days}d)
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell sx={BODY_CELL_SX}>
                    <Tooltip title={CONFIDENCE_HELP[pair.confidence] ?? ''}>
                      <Chip
                        size="small"
                        label={pair.confidence}
                        sx={{
                          height: 20, fontSize: '0.68rem', fontWeight: 700,
                          color: CONFIDENCE_COLOURS[pair.confidence] ?? '#94a3b8',
                          backgroundColor: 'rgba(148,163,184,0.12)',
                        }}
                      />
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {hiddenPairCount > 0 && (
            <Button
              size="small"
              onClick={() => setShowAllPairs(true)}
              sx={{ mt: 1, color: '#a78bfa', textTransform: 'none', fontWeight: 600 }}
            >
              Show the remaining {hiddenPairCount.toLocaleString('en-IN')} pair
              {hiddenPairCount === 1 ? '' : 's'}
            </Button>
          )}

          <Typography sx={{ ...MUTED_SX, mt: 1.5, fontSize: '0.78rem' }}>
            Pairs are matched on an exact amount within a few days across two different
            accounts. A payment to someone else is never treated as a transfer, even when
            the narration says &ldquo;transfer&rdquo; — only a matching pair counts.
          </Typography>
        </Box>
      </Collapse>
    </Card>
  )
}

export default React.memo(TransfersExcludedCard)
