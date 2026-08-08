import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Box, Paper, Typography, TextField, Autocomplete, Grid, Chip, CircularProgress } from '@mui/material'
import ScienceIcon from '@mui/icons-material/Science'
import { apiClient } from '../../../shared/api/client'
import { useWhatIf } from '../hooks/useData'
import { useDebounce } from '../../../shared/hooks/useDebounce'
import { fmtInr } from '../../../shared/utils/fmt'

export default function WhatIfPanel() {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<{ symbol: string; name: string } | null>(null)
  const [monthlyAmount, setMonthlyAmount] = useState(10000)
  const [years, setYears] = useState(5)

  // Debounced before it reaches the key: typing a fund name previously issued one
  // /compare/search per keystroke at a single-worker backend.
  const debouncedQuery = useDebounce(query, 300)

  const { data: searchRes, isFetching: searching } = useQuery({
    queryKey: ['whatIfSearch', debouncedQuery],
    queryFn: () => apiClient.searchTicker(debouncedQuery),
    enabled: debouncedQuery.length >= 3 && !selected,
    // Search results for a given string do not change minute to minute, and this
    // drops the per-keystroke entries out of the cache sooner.
    gcTime: 60 * 1000,
  })
  const options = searchRes?.results ?? []

  const { data, isLoading, isFetching } = useWhatIf(
    { scheme_code: selected?.symbol, monthly_amount: monthlyAmount, years },
    !!selected?.symbol && monthlyAmount > 0 && years > 0
  )

  return (
    <Paper sx={{
      p: 4, borderRadius: '32px', bgcolor: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)', mb: 4,
      boxShadow: '0 8px 32px 0 rgba(0,0,0,0.3)'
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
        <ScienceIcon sx={{ color: '#818CF8', fontSize: 24 }} />
        <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff' }}>What-If Simulator</Typography>
      </Box>
      <Typography variant="body2" sx={{ color: 'text.secondary', mb: 3 }}>
        Evaluating a fund you don't hold yet? Replay its real historical NAVs to see what a SIP into it would have actually returned.
      </Typography>

      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6}>
          <Autocomplete
            options={options}
            getOptionLabel={(o: any) => o.name || ''}
            isOptionEqualToValue={(a: any, b: any) => a?.symbol === b?.symbol}
            filterOptions={(x) => x}
            clearOnBlur={false}
            loading={searching}
            value={selected}
            inputValue={query}
            onChange={(_, val) => {
              setSelected(val)
              if (val) setQuery(val.name || '')
              else setQuery('')
            }}
            onInputChange={(_, val, reason) => {
              if (reason === 'input') {
                setQuery(val)
                if (!val.trim()) setSelected(null)
              } else if (reason === 'clear') {
                setQuery('')
                setSelected(null)
              }
            }}
            renderInput={(params) => (
              <TextField {...params} label="Candidate fund" placeholder="Search by name..." size="small"
                InputProps={{ ...params.InputProps, endAdornment: <>{searching ? <CircularProgress size={16} /> : null}{params.InputProps.endAdornment}</> }}
              />
            )}
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <TextField
            label="Monthly SIP (₹)" type="number" size="small" fullWidth
            value={monthlyAmount} onChange={(e) => setMonthlyAmount(Number(e.target.value))}
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <TextField
            label="Years" type="number" size="small" fullWidth
            value={years} onChange={(e) => setYears(Number(e.target.value))}
          />
        </Grid>
      </Grid>

      {!selected ? (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>Search for a fund above to simulate a hypothetical SIP.</Typography>
      ) : (isLoading || isFetching) ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}><CircularProgress size={24} /></Box>
      ) : data?.error ? (
        <Typography variant="body2" sx={{ color: '#FF516A' }}>{data.error}</Typography>
      ) : data?.final_value ? (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={6} sm={3}>
              <StatBox label="Final Value" value={fmtInr(data.final_value, true)} color="#4EDE93" />
            </Grid>
            <Grid item xs={6} sm={3}>
              <StatBox label="Total Invested" value={fmtInr(data.total_invested, true)} color="#6366F1" />
            </Grid>
            <Grid item xs={6} sm={3}>
              <StatBox label="Wealth Multiple" value={`${data.wealth_multiple}x`} color="#F59E0B" />
            </Grid>
            <Grid item xs={6} sm={3}>
              <StatBox label="CAGR" value={`${data.cagr_pct}%`} color={data.cagr_pct >= 0 ? '#4EDE93' : '#FF516A'} />
            </Grid>
          </Grid>
          <Chip
            label={`Simulated using real NAVs from ${data.actual_start_date} to ${data.actual_end_date} (${data.installments} installments)${data.requested_years > (new Date(data.actual_end_date).getFullYear() - new Date(data.actual_start_date).getFullYear()) ? ' — fund history is shorter than the requested window' : ''}.`}
            size="small"
            sx={{ height: 'auto', py: 1, fontSize: 11, fontWeight: 600, color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.03)', '& .MuiChip-label': { whiteSpace: 'normal', display: 'block' } }}
          />
        </>
      ) : null}
    </Paper>
  )
}

function StatBox({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.05)', textAlign: 'center' }}>
      <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 18, fontWeight: 900, color }}>{value}</Typography>
      <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>{label}</Typography>
    </Box>
  )
}
