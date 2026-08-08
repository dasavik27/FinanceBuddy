import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Box, Button, Checkbox, Chip, CircularProgress, FormControlLabel,
  MenuItem, Paper, Stack, Table, TableBody, TableCell, TableHead, TableRow,
  TextField, Typography, alpha,
} from '@mui/material'
import TravelExploreIcon from '@mui/icons-material/TravelExplore'

import { apiClient } from '../../../../shared/api/client'

type ScanRow = {
  symbol: string
  score?: number
  stage2?: boolean
  vcp_valid?: boolean
  pivot?: number | null
  last_depth?: number | null
  rs_percentile?: number | null
  close?: number | null
  n_contractions?: number | null
}

export default function ResearchScannerTab() {
  const navigate = useNavigate()
  const [universe, setUniverse] = useState('nifty50')
  const [limit, setLimit] = useState(50)
  const [onlySetups, setOnlySetups] = useState(false)
  const [symbolProbe, setSymbolProbe] = useState('')

  const { data: strategyData } = useQuery({
    queryKey: ['equity-research-strategies'],
    queryFn: () => apiClient.getEquityResearchStrategies(),
  })
  const strategy = strategyData?.strategies?.[0]

  const scan = useMutation({
    mutationFn: () =>
      apiClient.scanEquityResearch({
        strategy: 'minervini_vcp',
        universe,
        limit,
        only_setups: onlySetups,
      }),
  })

  const probe = useMutation({
    mutationFn: (sym: string) => apiClient.evaluateEquityResearchSymbol(sym.trim().toUpperCase()),
  })

  const rows: ScanRow[] = useMemo(() => scan.data?.results ?? [], [scan.data])

  return (
    <Box>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" sx={{ mb: 3 }}>
        <Box>
          <Typography sx={{ color: '#F1F5F9', fontWeight: 800, fontSize: '1.15rem' }}>
            Research Scanner
          </Typography>
          <Typography sx={{ color: '#94A3B8', fontSize: '0.875rem', mt: 0.5, maxWidth: 640 }}>
            {strategy?.description
              || 'Scan liquid NSE names for Stage-2 Trend Template + VCP setups. Research only - no orders.'}
          </Typography>
        </Box>
        <Chip
          icon={<TravelExploreIcon />}
          label="No MarketSmith"
          size="small"
          sx={{ bgcolor: alpha('#10B981', 0.12), color: '#6EE7B7', fontWeight: 700 }}
        />
      </Stack>

      <Paper elevation={0} sx={{
        p: 2.5, mb: 3, borderRadius: '16px',
        bgcolor: alpha('#0F172A', 0.55), border: '1px solid rgba(255,255,255,0.06)',
      }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ md: 'center' }}>
          <TextField
            select
            size="small"
            label="Universe"
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            sx={{ minWidth: 160, '& .MuiInputBase-root': { color: '#E2E8F0' } }}
          >
            <MenuItem value="nifty50">Nifty 50</MenuItem>
            <MenuItem value="liquid">Liquid ~100</MenuItem>
          </TextField>
          <TextField
            select
            size="small"
            label="Limit"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            sx={{ minWidth: 100, '& .MuiInputBase-root': { color: '#E2E8F0' } }}
          >
            {[20, 30, 50, 80].map((n) => (
              <MenuItem key={n} value={n}>{n}</MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={
              <Checkbox
                checked={onlySetups}
                onChange={(e) => setOnlySetups(e.target.checked)}
                sx={{ color: '#64748B' }}
              />
            }
            label={<Typography sx={{ color: '#94A3B8', fontSize: '0.85rem' }}>Only Stage2 + VCP</Typography>}
          />
          <Button
            variant="contained"
            disabled={scan.isPending}
            onClick={() => scan.mutate()}
            sx={{
              textTransform: 'none', fontWeight: 800, bgcolor: '#10B981',
              '&:hover': { bgcolor: '#059669' },
            }}
          >
            {scan.isPending ? 'Scanning...' : 'Run scan'}
          </Button>
        </Stack>
        <Typography sx={{ color: '#64748B', fontSize: '0.75rem', mt: 1.5 }}>
          First run downloads daily OHLC (Yahoo) and caches it. Cap keeps the worker responsive.
        </Typography>
      </Paper>

      {(scan.isError || probe.isError) && (
        <Alert severity="error" sx={{ mb: 2, borderRadius: '12px' }}>
          {(scan.error as any)?.response?.data?.detail
            || (probe.error as any)?.response?.data?.detail
            || 'Scan failed. Sign in and retry.'}
        </Alert>
      )}

      {scan.isPending && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress size={28} sx={{ color: '#10B981' }} />
        </Box>
      )}

      {scan.data && !scan.isPending && (
        <Paper elevation={0} sx={{
          borderRadius: '16px', overflow: 'hidden',
          bgcolor: alpha('#0F172A', 0.45), border: '1px solid rgba(255,255,255,0.06)',
        }}>
          <Box sx={{ px: 2.5, py: 1.5, borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
            <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem' }}>
              Evaluated {scan.data.evaluated}/{scan.data.requested}
              {' · '}
              Setups {scan.data.setups ?? 0}
              {' · '}
              Ranked by MS-free composite score
            </Typography>
          </Box>
          <Table size="small">
            <TableHead>
              <TableRow>
                {['Symbol', 'Score', 'Stage 2', 'VCP', 'Pivot', 'Depth', 'RS %', 'Close', ''].map((h) => (
                  <TableCell key={h || 'actions'} sx={{ color: '#64748B', fontWeight: 700, border: 0 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} sx={{ color: '#94A3B8', py: 4, textAlign: 'center', border: 0 }}>
                    No rows matched. Try disabling Only Stage2 + VCP or another universe.
                  </TableCell>
                </TableRow>
              ) : rows.map((row) => (
                <TableRow key={row.symbol} hover sx={{ '&:hover': { bgcolor: alpha('#10B981', 0.04) } }}>
                  <TableCell sx={{ color: '#F1F5F9', fontWeight: 800, border: 0 }}>{row.symbol}</TableCell>
                  <TableCell sx={{ color: '#6EE7B7', fontWeight: 700, border: 0 }}>{row.score ?? '—'}</TableCell>
                  <TableCell sx={{ border: 0 }}>
                    <Chip
                      size="small"
                      label={row.stage2 ? 'Yes' : 'No'}
                      sx={{
                        height: 22, fontWeight: 700,
                        bgcolor: row.stage2 ? alpha('#10B981', 0.15) : alpha('#64748B', 0.15),
                        color: row.stage2 ? '#6EE7B7' : '#94A3B8',
                      }}
                    />
                  </TableCell>
                  <TableCell sx={{ border: 0 }}>
                    <Chip
                      size="small"
                      label={row.vcp_valid ? 'Yes' : 'No'}
                      sx={{
                        height: 22, fontWeight: 700,
                        bgcolor: row.vcp_valid ? alpha('#38BDF8', 0.15) : alpha('#64748B', 0.15),
                        color: row.vcp_valid ? '#7DD3FC' : '#94A3B8',
                      }}
                    />
                  </TableCell>
                  <TableCell sx={{ color: '#CBD5E1', border: 0 }}>{row.pivot ?? '—'}</TableCell>
                  <TableCell sx={{ color: '#CBD5E1', border: 0 }}>
                    {row.last_depth != null ? `${(row.last_depth * 100).toFixed(1)}%` : '—'}
                  </TableCell>
                  <TableCell sx={{ color: '#CBD5E1', border: 0 }}>{row.rs_percentile ?? '—'}</TableCell>
                  <TableCell sx={{ color: '#CBD5E1', border: 0 }}>{row.close ?? '—'}</TableCell>
                  <TableCell sx={{ border: 0 }}>
                    <Button
                      size="small"
                      onClick={() => navigate(`/equity/analyzer?symbol=${encodeURIComponent(row.symbol)}`)}
                      sx={{ textTransform: 'none', fontWeight: 700, color: '#38BDF8' }}
                    >
                      Analyze
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <Paper elevation={0} sx={{
        p: 2.5, mt: 3, borderRadius: '16px',
        bgcolor: alpha('#0F172A', 0.45), border: '1px solid rgba(255,255,255,0.06)',
      }}>
        <Typography sx={{ color: '#F1F5F9', fontWeight: 800, mb: 1.5 }}>Single-symbol check</Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
          <TextField
            size="small"
            placeholder="e.g. RELIANCE"
            value={symbolProbe}
            onChange={(e) => setSymbolProbe(e.target.value.toUpperCase())}
            sx={{ minWidth: 200, '& .MuiInputBase-root': { color: '#E2E8F0' } }}
          />
          <Button
            variant="outlined"
            disabled={!symbolProbe.trim() || probe.isPending}
            onClick={() => probe.mutate(symbolProbe)}
            sx={{ textTransform: 'none', fontWeight: 700, borderColor: alpha('#10B981', 0.4), color: '#6EE7B7' }}
          >
            {probe.isPending ? 'Checking...' : 'Evaluate'}
          </Button>
        </Stack>
        {probe.data && (
          <Box sx={{ mt: 2 }}>
            <Typography sx={{ color: '#94A3B8', fontSize: '0.85rem' }}>
              {probe.data.symbol}: score {probe.data.score ?? '—'}
              {' · '}Stage2 {probe.data.stage2 ? 'Yes' : 'No'}
              {' · '}VCP {probe.data.vcp_valid ? 'Yes' : 'No'}
              {' · '}Pivot {probe.data.pivot ?? '—'}
              {!probe.data.ok && probe.data.reason ? ` · ${probe.data.reason}` : ''}
            </Typography>
          </Box>
        )}
      </Paper>
    </Box>
  )
}
