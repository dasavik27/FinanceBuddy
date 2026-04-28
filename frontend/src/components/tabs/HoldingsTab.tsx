import { useState } from 'react'
import {
  Box, Paper, Typography, TextField, InputAdornment,
  Table, TableHead, TableRow, TableCell, TableBody,
  TableSortLabel, Skeleton, Alert, Chip, Select,
  MenuItem, FormControl, InputLabel, TableContainer,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useHoldings } from '../../hooks/useData'
import { CategoryBadge, PlanBadge, SectionHeader } from '../ui'
import { fmtInr, fmtPct, gainColor } from '../../api/fmt'
import type { Holding } from '../../api/client'

type SortKey = 'Market Value' | 'Gain%' | 'Weight%' | 'Gain' | 'Invested' | 'Fund'

export default function HoldingsTab() {
  const [search,    setSearch]    = useState('')
  const [sortBy,    setSortBy]    = useState<SortKey>('Market Value')
  const [ascending, setAscending] = useState(false)
  const [capFilter, setCapFilter] = useState('All')

  const { data, isLoading, error } = useHoldings({
    sort_by:   sortBy,
    ascending: String(ascending),
    search,
    cap_filter: capFilter,
  })

  const holdings  = data?.holdings  ?? []
  const capTypes  = ['All', ...(data?.cap_types ?? [])]

  function handleSort(col: SortKey) {
    if (col === sortBy) setAscending(!ascending)
    else { setSortBy(col); setAscending(false) }
  }

  const cols: { id: SortKey; label: string; align?: 'right' | 'left' }[] = [
    { id: 'Fund',         label: 'Fund',          align: 'left' },
    { id: 'Market Value', label: 'Market Value',  align: 'right' },
    { id: 'Invested',     label: 'Invested',      align: 'right' },
    { id: 'Gain',         label: 'Gain / Loss',   align: 'right' },
    { id: 'Gain%',        label: 'Return %',      align: 'right' },
    { id: 'Weight%',      label: 'Weight',        align: 'right' },
  ]

  return (
    <Box>
      <SectionHeader title="Holdings" subtitle="All mutual fund positions in your filtered portfolio" />

      {/* ── Filter bar ──────────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ p: 2, mb: 2, borderRadius: 3 }}>
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            size="small"
            placeholder="Search fund name…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ minWidth: 240 }}
            InputProps={{
              startAdornment: <InputAdornment position="start"><SearchIcon sx={{ fontSize: 18, color: '#94A3B8' }} /></InputAdornment>,
            }}
          />
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel sx={{ fontSize: 12 }}>Cap Type</InputLabel>
            <Select value={capFilter} label="Cap Type" onChange={(e) => setCapFilter(e.target.value)} sx={{ fontSize: 12 }}>
              {capTypes.map((c) => <MenuItem key={c} value={c} sx={{ fontSize: 12 }}>{c}</MenuItem>)}
            </Select>
          </FormControl>
          <Box sx={{ ml: 'auto' }}>
            <Typography variant="caption" color="text.secondary">
              {holdings.length} fund{holdings.length !== 1 ? 's' : ''}
            </Typography>
          </Box>
        </Box>
      </Paper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>Failed to load holdings.</Alert>}

      {/* ── Table ───────────────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ borderRadius: 3, overflow: 'hidden' }}>
        <TableContainer>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {cols.map((col) => (
                  <TableCell key={col.id} align={col.align ?? 'left'} sx={{ background: '#F8FAFC' }}>
                    <TableSortLabel
                      active={sortBy === col.id}
                      direction={sortBy === col.id ? (ascending ? 'asc' : 'desc') : 'desc'}
                      onClick={() => handleSort(col.id)}
                    >
                      {col.label}
                    </TableSortLabel>
                  </TableCell>
                ))}
                <TableCell sx={{ background: '#F8FAFC' }}>Category</TableCell>
                <TableCell sx={{ background: '#F8FAFC' }}>Plan</TableCell>
                <TableCell sx={{ background: '#F8FAFC' }}>Cap Type</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {isLoading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      {Array.from({ length: 9 }).map((__, j) => (
                        <TableCell key={j}><Skeleton /></TableCell>
                      ))}
                    </TableRow>
                  ))
                : holdings.map((h: Holding) => {
                    const gain = h.Gain ?? 0
                    const gainPct = h['Gain%'] ?? 0
                    const weight = h['Weight%'] ?? 0
                    return (
                      <TableRow key={h.Fund} hover>
                        {/* Fund name */}
                        <TableCell sx={{ maxWidth: 300 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Box sx={{ width: 8, height: 8, borderRadius: '50%', background: h.color, flexShrink: 0 }} />
                            <Typography variant="body2" fontWeight={600} sx={{
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}>
                              {h.Fund}
                            </Typography>
                          </Box>
                        </TableCell>

                        <TableCell align="right">
                          <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 600, color: '#0F172A' }}>
                            {fmtInr(h['Market Value'], true)}
                          </Typography>
                        </TableCell>

                        <TableCell align="right">
                          <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#64748B' }}>
                            {fmtInr(h.Invested, true)}
                          </Typography>
                        </TableCell>

                        <TableCell align="right">
                          <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, fontWeight: 600, color: gainColor(gain) }}>
                            {fmtInr(gain, true)}
                          </Typography>
                        </TableCell>

                        <TableCell align="right">
                          <Box sx={{
                            display: 'inline-block', px: 1.25, py: 0.25, borderRadius: 999,
                            fontFamily: '"DM Mono",monospace', fontSize: 11, fontWeight: 700,
                            background: gain >= 0 ? '#ECFDF5' : '#FEF2F2',
                            color: gainColor(gain),
                          }}>
                            {fmtPct(gainPct)}
                          </Box>
                        </TableCell>

                        <TableCell align="right">
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, justifyContent: 'flex-end' }}>
                            <Box sx={{ width: 40, background: '#F1F5F9', borderRadius: 999, height: 5 }}>
                              <Box sx={{
                                height: '100%', borderRadius: 999,
                                background: '#1D4ED8',
                                width: `${Math.min(100, weight * 4)}%`,
                              }} />
                            </Box>
                            <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11, color: '#64748B', minWidth: 36 }}>
                              {weight.toFixed(1)}%
                            </Typography>
                          </Box>
                        </TableCell>

                        <TableCell><CategoryBadge category={h.Category} /></TableCell>
                        <TableCell><PlanBadge plan={h.Plan} /></TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary" fontWeight={600}>
                            {h['Cap Type']}
                          </Typography>
                        </TableCell>
                      </TableRow>
                    )
                  })
              }
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  )
}
