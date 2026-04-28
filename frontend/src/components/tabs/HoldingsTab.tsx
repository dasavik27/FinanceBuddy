import { useState } from 'react'
import {
  Box, Paper, Typography, TextField, InputAdornment,
  Table, TableHead, TableRow, TableCell, TableBody,
  TableSortLabel, Skeleton, Alert, Chip, Select,
  MenuItem, FormControl, InputLabel, TableContainer, Grid,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import { useHoldings, useAllocation } from '../../hooks/useData'
import { CategoryBadge, PlanBadge, SectionHeader, TabLoader } from '../ui'
import { fmtInr, fmtPct, gainColor } from '../../api/fmt'
import type { Holding } from '../../api/client'

// ── Donut chart (SVG, no dep) ─────────────────────────────────────────────────
function DonutChart({ data, size = 160 }: { data: { label: string; value: number; pct: number; color: string }[]; size?: number }) {
  const total  = data.reduce((a, b) => a + b.value, 0)
  const cx = size / 2; const cy = size / 2; const r = size * 0.36; const ir = size * 0.22
  let startAngle = -90
  const slices = data.filter(d => d.value > 0).map(d => {
    const angle = (d.value / total) * 360
    const s = startAngle; startAngle += angle
    return { ...d, startAngle: s, angle }
  })

  function polarToXY(cx: number, cy: number, r: number, angleDeg: number) {
    const rad = (angleDeg * Math.PI) / 180
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
  }
  function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
    const s = polarToXY(cx, cy, r, startDeg)
    const e = polarToXY(cx, cy, r, endDeg)
    const large = endDeg - startDeg > 180 ? 1 : 0
    return `M ${s.x} ${s.y} A ${r} ${r} 0 ${large} 1 ${e.x} ${e.y}`
  }

  return (
    <svg width={size} height={size}>
      {slices.map((s, i) => {
        const outerPath = arcPath(cx, cy, r, s.startAngle, s.startAngle + s.angle - 0.5)
        const innerStart = polarToXY(cx, cy, ir, s.startAngle + s.angle - 0.5)
        const innerEnd   = polarToXY(cx, cy, ir, s.startAngle)
        const large = s.angle > 180 ? 1 : 0
        const d = `${outerPath} L ${innerStart.x} ${innerStart.y} A ${ir} ${ir} 0 ${large} 0 ${innerEnd.x} ${innerEnd.y} Z`
        return <path key={i} d={d} fill={s.color} opacity={0.9}>
          <title>{s.label}: {s.pct?.toFixed(1)}%</title>
        </path>
      })}
      <circle cx={cx} cy={cy} r={ir - 2} fill="#FFFFFF" />
    </svg>
  )
}


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

  const { data: alloc, isLoading: allocL } = useAllocation()

  if (isLoading || allocL) {
    return <TabLoader message="Loading absolute holdings allocations..." />
  }

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

      {/* ── Allocation row ───────────────────────────────────────────── */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {/* Broad asset class donut */}
        <Grid item xs={12} md={6}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, height: '100%' }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Asset Mix</Typography>
            {allocL ? <Skeleton variant="circular" width={160} height={160} sx={{ mx: 'auto' }} /> : (
              <>
                <Box sx={{ display: 'flex', justifyContent: 'center', mb: 2 }}>
                  <DonutChart data={(alloc?.broad ?? []).filter((d: any) => d.value > 0)} />
                </Box>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75 }}>
                  {(alloc?.broad ?? []).filter((d: any) => d.value > 0).map((d: any) => (
                    <Box key={d.label} sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: '50%', background: d.color, flexShrink: 0 }} />
                        <Typography variant="body2" fontWeight={600}>{d.label}</Typography>
                      </Box>
                      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#64748B' }}>
                        {d.pct?.toFixed(1)}%
                      </Typography>
                    </Box>
                  ))}
                </Box>
              </>
            )}
          </Paper>
        </Grid>

        {/* Cap size */}
        <Grid item xs={12} md={6}>
          <Paper elevation={1} sx={{ p: 3, borderRadius: 3, height: '100%' }}>
            <Typography variant="h6" sx={{ mb: 2 }}>Cap Breakdown</Typography>
            {allocL ? <Skeleton variant="rectangular" height={180} sx={{ borderRadius: 2 }} /> : (
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                {(alloc?.by_cap ?? []).map((d: any) => {
                  const pct = d.pct ?? 0
                  return (
                    <Box key={d['Cap Type']}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                        <Typography variant="body2" fontWeight={600}>{d['Cap Type']}</Typography>
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#64748B' }}>
                          {pct.toFixed(1)}% · {fmtInr(d['Market Value'], true)}
                        </Typography>
                      </Box>
                      <Box sx={{ background: '#F1F5F9', borderRadius: 999, height: 7, overflow: 'hidden' }}>
                        <Box sx={{
                          height: '100%', borderRadius: 999,
                          background: 'linear-gradient(90deg, #1D4ED8, #60A5FA)',
                          width: `${pct}%`, transition: 'width 600ms cubic-bezier(0,0,0,1)',
                        }} />
                      </Box>
                    </Box>
                  )
                })}
              </Box>
            )}
          </Paper>
        </Grid>
      </Grid>


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
