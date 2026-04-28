import { useState } from 'react'
import {
  Box, Paper, Typography, TextField, InputAdornment,
  Grid, Skeleton, Alert, Autocomplete, Select,
  MenuItem, FormControl, InputLabel, Chip, CircularProgress,
} from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { useQuery } from '@tanstack/react-query'
import { useHoldings } from '../../hooks/useData'
import { apiClient } from '../../api/client'
import { useSessionId } from '../../store/appStore'
import { SectionHeader, CategoryBadge, PlanBadge } from '../ui'
import { fmtInr, fmtPct, gainColor } from '../../api/fmt'

const PERIODS  = ['1 Month','6 Months','1 Year','3 Years','5 Years']
const P_DAYS   = { '1 Month':30,'6 Months':180,'1 Year':365,'3 Years':1095,'5 Years':1825 } as Record<string,number>
const COLORS   = ['#1D4ED8','#059669','#7C3AED','#D97706','#DC2626','#0E7490']

export default function CompareTab() {
  const sid   = useSessionId()
  const [selectedFunds,  setSelectedFunds]  = useState<string[]>([])
  const [externalSearch, setExternalSearch] = useState('')
  const [externalTicker, setExternalTicker] = useState<{ symbol: string; name: string } | null>(null)
  const [period,         setPeriod]         = useState('1 Year')

  const { data: holdingsData, isLoading: holdL } = useHoldings({ sort_by: 'Market Value' })
  const fundList = (holdingsData?.holdings ?? []).map((h: any) => h.Fund)

  // External ticker search
  const { data: searchResults, isFetching: searching } = useQuery({
    queryKey:  ['tickerSearch', externalSearch],
    queryFn:   () => apiClient.searchTicker(externalSearch),
    enabled:   externalSearch.length >= 3,
    staleTime: 30_000,
  })

  // Benchmark history for external ticker
  const { data: extHistory } = useQuery({
    queryKey: ['benchHistory', externalTicker?.symbol, P_DAYS[period]],
    queryFn:  () => apiClient.getBenchmarkHistory(externalTicker!.symbol, P_DAYS[period]),
    enabled:  !!externalTicker,
  })

  const allSelected = [...selectedFunds, ...(externalTicker ? [externalTicker.symbol] : [])]

  // Holdings data for selected funds
  const selectedHoldingData = (holdingsData?.holdings ?? []).filter((h: any) =>
    selectedFunds.includes(h.Fund)
  )

  return (
    <Box>
      <SectionHeader
        title="Fund Comparison Matrix"
        subtitle="Compare up to 4 portfolio funds + any external ticker"
      />

      {/* ── Selection row ────────────────────────────────────────────── */}
      <Paper elevation={1} sx={{ p: 2.5, mb: 3, borderRadius: 3 }}>
        <Grid container spacing={2} alignItems="flex-start">
          <Grid item xs={12} md={5}>
            <Autocomplete
              multiple
              size="small"
              options={fundList}
              value={selectedFunds}
              onChange={(_, v) => setSelectedFunds(v.slice(0, 4))}
              getOptionLabel={(o) => o}
              renderOption={(props, option) => (
                <Box component="li" {...props} sx={{ fontSize: 12, py: 1 }}>
                  {option.length > 55 ? option.slice(0, 55) + '…' : option}
                </Box>
              )}
              renderTags={(val, getProps) =>
                val.map((option, i) => (
                  <Chip {...getProps({ index: i })} key={option} size="small"
                    label={option.length > 28 ? option.slice(0, 28) + '…' : option}
                    sx={{ fontSize: 10, fontWeight: 600, background: COLORS[i] + '20', color: COLORS[i] }}
                  />
                ))
              }
              renderInput={(params) => (
                <TextField {...params} label="Select portfolio funds (max 4)" placeholder="Type to search…" />
              )}
            />
          </Grid>

          <Grid item xs={12} md={4}>
            <Autocomplete
              size="small"
              options={searchResults?.results ?? []}
              getOptionLabel={(o: any) => `${o.symbol} — ${o.name}`}
              loading={searching}
              value={externalTicker}
              onChange={(_, v) => setExternalTicker(v)}
              inputValue={externalSearch}
              onInputChange={(_, v) => setExternalSearch(v)}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Search external ticker (Yahoo Finance)"
                  placeholder="e.g. Nifty, RELIANCE, Gold…"
                  InputProps={{
                    ...params.InputProps,
                    startAdornment: <><SearchIcon sx={{ fontSize: 18, color: '#94A3B8', mr: 0.5 }} />{params.InputProps.startAdornment}</>,
                    endAdornment: <>{searching && <CircularProgress size={14} />}{params.InputProps.endAdornment}</>,
                  }}
                />
              )}
            />
          </Grid>

          <Grid item xs={12} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>Period</InputLabel>
              <Select value={period} label="Period" onChange={(e) => setPeriod(e.target.value)}>
                {PERIODS.map((p) => <MenuItem key={p} value={p} sx={{ fontSize: 12 }}>{p}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>

      {allSelected.length === 0 ? (
        <Alert severity="info">Select at least one fund to compare.</Alert>
      ) : (
        <>
          {/* ── Metric comparison cards ─────────────────────────────── */}
          <Grid container spacing={2} sx={{ mb: 3 }}>
            {selectedHoldingData.map((h: any, idx: number) => (
              <Grid item xs={12} sm={6} md={3} key={h.Fund}>
                <Paper elevation={1} sx={{
                  p: 2, borderRadius: 3, borderTop: `3px solid ${COLORS[idx]}`,
                  height: '100%',
                }}>
                  <Typography variant="body2" fontWeight={700} sx={{
                    mb: 1.5, pb: 1, borderBottom: '1px solid #F1F5F9',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {h.Fund}
                  </Typography>
                  {[
                    { label: 'Market Value', value: fmtInr(h['Market Value'], true) },
                    { label: 'Invested',     value: fmtInr(h.Invested, true) },
                    { label: 'Return',       value: fmtPct(h['Gain%']),     color: gainColor(h['Gain%']) },
                    { label: 'Weight',       value: `${h['Weight%']?.toFixed(1)}%` },
                    { label: 'AMC',          value: h.AMC },
                  ].map((row) => (
                    <Box key={row.label} sx={{
                      display: 'flex', justifyContent: 'space-between', py: 0.6,
                      borderBottom: '1px solid #F8FAFC',
                    }}>
                      <Typography sx={{ fontSize: 11, color: '#64748B', fontWeight: 500 }}>{row.label}</Typography>
                      <Typography sx={{
                        fontFamily: '"DM Mono",monospace', fontSize: 11, fontWeight: 700,
                        color: (row as any).color ?? '#0F172A',
                      }}>
                        {row.value}
                      </Typography>
                    </Box>
                  ))}
                  <Box sx={{ mt: 1.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                    <CategoryBadge category={h.Category} />
                    <PlanBadge plan={h.Plan} />
                  </Box>
                </Paper>
              </Grid>
            ))}

            {/* External ticker card */}
            {externalTicker && extHistory && (
              <Grid item xs={12} sm={6} md={3}>
                <Paper elevation={1} sx={{
                  p: 2, borderRadius: 3,
                  borderTop: `3px solid ${COLORS[selectedFunds.length]}`,
                  height: '100%',
                }}>
                  <Typography variant="body2" fontWeight={700} sx={{ mb: 1.5, pb: 1, borderBottom: '1px solid #F1F5F9' }}>
                    {externalTicker.symbol}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    {externalTicker.name}
                  </Typography>
                  {extHistory.values?.length > 1 && (() => {
                    const first = extHistory.values[0]
                    const last  = extHistory.values[extHistory.values.length - 1]
                    const ret   = ((last / first) - 1) * 100
                    return (
                      <Box sx={{ py: 0.6, borderBottom: '1px solid #F8FAFC', display: 'flex', justifyContent: 'space-between' }}>
                        <Typography sx={{ fontSize: 11, color: '#64748B' }}>Return ({period})</Typography>
                        <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11, fontWeight: 700, color: gainColor(ret) }}>
                          {fmtPct(ret)}
                        </Typography>
                      </Box>
                    )
                  })()}
                  <Chip size="small" label="External" sx={{ mt: 1.5, fontSize: 10, background: '#F5F3FF', color: '#6D28D9' }} />
                </Paper>
              </Grid>
            )}
          </Grid>

          {/* ── Normalised performance chart ────────────────────────── */}
          {extHistory && (
            <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
              <Typography variant="h6" sx={{ mb: 2 }}>Normalised Returns (Base = 100)</Typography>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart
                  data={extHistory.dates?.map((d: string, i: number) => ({
                    date: d.slice(5),
                    [externalTicker!.symbol]: extHistory.values?.[i],
                  })) ?? []}
                  margin={{ top: 5, right: 10, left: -10, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                  <YAxis tick={{ fontSize: 10, fill: '#94A3B8' }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v.toFixed(0)}`} />
                  <Tooltip contentStyle={{ borderRadius: 10, border: '1px solid #E2E8F0', fontSize: 12 }} formatter={(v: any) => Number(v).toFixed(1)} />
                  <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600 }} />
                  <Line
                    type="monotone"
                    dataKey={externalTicker!.symbol}
                    stroke={COLORS[selectedFunds.length]}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </Paper>
          )}
        </>
      )}
    </Box>
  )
}
