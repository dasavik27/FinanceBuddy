import { useState } from 'react'
import {
  Box, Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, TableSortLabel, Typography,
} from '@mui/material'

import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import { useClearSessionOnMissing, useEquityHoldings } from '../../hooks/useEquityData'
import type { EquityHolding, EquitySortColumn } from '../../types'
import { EquityTabError, EquityTabSkeleton, GLASS_PAPER, HEADER_CELL } from './shared'

/**
 * Holdings table.
 *
 * Formatting comes from shared/utils/fmt rather than a local `Intl.NumberFormat`
 * wrapper. There were eight byte-identical copies of that wrapper across the equity
 * tabs, each constructing a fresh formatter *per cell* - six per row here - and none of
 * them null-guarded, so a null from the API rendered as "₹NaN".
 */
export default function HoldingsTab() {
  const [sortCol, setSortCol] = useState<EquitySortColumn>('current_value')
  const [sortAsc, setSortAsc] = useState(false)

  const { data, isPending, isError, error, isPlaceholderData } = useEquityHoldings(sortCol, sortAsc)
  useClearSessionOnMissing(error)

  const handleSort = (col: EquitySortColumn) => {
    if (sortCol === col) setSortAsc((prev) => !prev)
    else {
      setSortCol(col)
      setSortAsc(false)
    }
  }

  if (isPending) return <EquityTabSkeleton rows={8} />
  if (isError) return <EquityTabError error={error} label="holdings" />

  const holdings = data?.holdings ?? []
  if (holdings.length === 0) {
    return (
      <Paper className="glass" sx={{ ...GLASS_PAPER, p: 4, textAlign: 'center' }}>
        <Typography sx={{ color: '#94A3B8' }}>No holdings in this portfolio.</Typography>
      </Paper>
    )
  }

  const total = data?.total ?? 0

  const sortable = (col: EquitySortColumn, label: string) => (
    <TableSortLabel
      active={sortCol === col}
      direction={sortCol === col ? (sortAsc ? 'asc' : 'desc') : 'asc'}
      onClick={() => handleSort(col)}
    >
      {label}
    </TableSortLabel>
  )

  return (
    <Box>
      <Paper className="glass" sx={{ ...GLASS_PAPER, overflow: 'hidden' }}>
        {/* Dimmed while a re-sort is in flight. keepPreviousData holds the old rows on
            screen, so this replaces the full unmount-to-spinner that used to reset
            scroll position on every header click. */}
        <TableContainer sx={{ maxHeight: 600, opacity: isPlaceholderData ? 0.6 : 1, transition: 'opacity 120ms' }}>
          <Table stickyHeader size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={HEADER_CELL}>{sortable('symbol', 'Symbol')}</TableCell>
                <TableCell align="right" sx={HEADER_CELL}>{sortable('quantity', 'Quantity')}</TableCell>
                <TableCell align="right" sx={HEADER_CELL}>{sortable('avg_price', 'Avg Price')}</TableCell>
                <TableCell align="right" sx={HEADER_CELL}>{sortable('ltp', 'LTP')}</TableCell>
                <TableCell align="right" sx={HEADER_CELL}>{sortable('current_value', 'Current Value')}</TableCell>
                <TableCell align="right" sx={HEADER_CELL}>{sortable('unrealized_pnl', 'P&L')}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {holdings.map((h: EquityHolding, i: number) => {
                const isPos = (h.unrealized_pnl ?? 0) >= 0
                const color = isPos ? '#10B981' : '#EF4444'
                // weight_pct is maintained server-side now. Falling back to a division
                // guarded against a zero total, which used to render "∞% weight".
                const weight = h.weight_pct ?? (total > 0 ? (h.current_value / total) * 100 : 0)
                return (
                  <TableRow
                    key={`${h.symbol}-${h.exchange ?? ''}-${i}`}
                    hover
                    sx={{ '&:hover': { background: 'rgba(255,255,255,0.03)' } }}
                  >
                    <TableCell>
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{h.symbol}</Typography>
                      {h.sector && (
                        <Typography sx={{ fontSize: '0.75rem', color: '#64748B' }}>{h.sector}</Typography>
                      )}
                    </TableCell>
                    <TableCell align="right" sx={{ color: '#E2E8F0' }}>{fmtNum(h.quantity)}</TableCell>
                    <TableCell align="right" sx={{ color: '#E2E8F0' }}>{fmtInr(h.avg_price)}</TableCell>
                    <TableCell align="right" sx={{ color: '#E2E8F0', fontWeight: 600 }}>{fmtInr(h.ltp)}</TableCell>
                    <TableCell align="right">
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{fmtInr(h.current_value)}</Typography>
                      <Typography sx={{ fontSize: '0.75rem', color: '#64748B' }}>
                        {fmtNum(weight, 1)}% weight
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Chip
                        label={`${isPos ? '+' : ''}${fmtInr(h.unrealized_pnl)} (${fmtNum(h.pnl_pct, 2)}%)`}
                        size="small"
                        sx={{ background: `${color}15`, color, fontWeight: 700, borderRadius: '8px' }}
                      />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  )
}
