import { useState, useEffect } from 'react'
import { Box, Typography, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TableSortLabel, CircularProgress, Chip } from '@mui/material'
import { apiClient } from '../../../../shared/api/client'
import { useEquitySessionId } from '../../../../shared/store/appStore'

function fmtINR(v: number) {
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v)
}

function fmtNum(v: number) {
    return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 }).format(v)
}

export default function HoldingsTab() {
  const sessionId = useEquitySessionId()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [sortCol, setSortCol] = useState('current_value')
  const [sortAsc, setSortAsc] = useState(false)

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    apiClient.getEquityHoldings(sessionId, { sort_by: sortCol, ascending: sortAsc })
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [sessionId, sortCol, sortAsc])

  if (loading) return <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>
  if (!data?.holdings) return null

  const handleSort = (col: string) => {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(false) }
  }

  return (
    <Box>
      <Paper className="glass" sx={{ borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)', overflow: 'hidden' }}>
        <TableContainer sx={{ maxHeight: 600 }}>
          <Table stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell sx={{ background: 'rgba(15,23,42,0.9)', color: '#94A3B8', fontWeight: 700 }}>
                  <TableSortLabel active={sortCol === 'symbol'} direction={sortCol === 'symbol' ? (sortAsc ? 'asc' : 'desc') : 'asc'} onClick={() => handleSort('symbol')}>
                    Symbol
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right" sx={{ background: 'rgba(15,23,42,0.9)', color: '#94A3B8', fontWeight: 700 }}>Quantity</TableCell>
                <TableCell align="right" sx={{ background: 'rgba(15,23,42,0.9)', color: '#94A3B8', fontWeight: 700 }}>Avg Price</TableCell>
                <TableCell align="right" sx={{ background: 'rgba(15,23,42,0.9)', color: '#94A3B8', fontWeight: 700 }}>LTP</TableCell>
                <TableCell align="right" sx={{ background: 'rgba(15,23,42,0.9)', color: '#94A3B8', fontWeight: 700 }}>
                  <TableSortLabel active={sortCol === 'current_value'} direction={sortCol === 'current_value' ? (sortAsc ? 'asc' : 'desc') : 'asc'} onClick={() => handleSort('current_value')}>
                    Current Value
                  </TableSortLabel>
                </TableCell>
                <TableCell align="right" sx={{ background: 'rgba(15,23,42,0.9)', color: '#94A3B8', fontWeight: 700 }}>
                  <TableSortLabel active={sortCol === 'unrealized_pnl'} direction={sortCol === 'unrealized_pnl' ? (sortAsc ? 'asc' : 'desc') : 'asc'} onClick={() => handleSort('unrealized_pnl')}>
                    P&L
                  </TableSortLabel>
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.holdings.map((h: any, i: number) => {
                const isPos = h.unrealized_pnl >= 0
                const color = isPos ? '#10B981' : '#EF4444'
                return (
                  <TableRow key={h.symbol || i} hover sx={{ '&:hover': { background: 'rgba(255,255,255,0.03)' } }}>
                    <TableCell>
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{h.symbol}</Typography>
                      {h.sector && <Typography sx={{ fontSize: '0.75rem', color: '#64748B' }}>{h.sector}</Typography>}
                    </TableCell>
                    <TableCell align="right" sx={{ color: '#E2E8F0' }}>{fmtNum(h.quantity)}</TableCell>
                    <TableCell align="right" sx={{ color: '#E2E8F0' }}>{fmtINR(h.avg_price)}</TableCell>
                    <TableCell align="right" sx={{ color: '#E2E8F0', fontWeight: 600 }}>{fmtINR(h.ltp)}</TableCell>
                    <TableCell align="right">
                      <Typography sx={{ fontWeight: 700, color: '#F8FAFC' }}>{fmtINR(h.current_value)}</Typography>
                      <Typography sx={{ fontSize: '0.75rem', color: '#64748B' }}>
                        {fmtNum((h.current_value / data.total) * 100)}% weight
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Chip 
                        label={`${isPos ? '+' : ''}${fmtINR(h.unrealized_pnl)} (${h.pnl_pct}%)`} 
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
