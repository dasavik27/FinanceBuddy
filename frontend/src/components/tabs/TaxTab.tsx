import { useState } from 'react'
import {
  Box, Grid, Paper, Typography, Alert, Skeleton,
  Table, TableHead, TableRow, TableCell, TableBody,
  TableContainer, Select, MenuItem, FormControl, InputLabel,
  ToggleButtonGroup, ToggleButton, Chip, Divider, CircularProgress,
} from '@mui/material'
import { useQuery }      from '@tanstack/react-query'
import { useTax }        from '../../hooks/useData'
import { useSessionId }  from '../../store/appStore'
import { SectionHeader, MetricCard } from '../ui'
import { fmtInr, gainColor } from '../../api/fmt'
import { apiClient }     from '../../api/client'

// ─────────────────────────────────────────────────────────
// FIFO Simulator component
// ─────────────────────────────────────────────────────────
interface FifoDetail {
  'Acquisition Date': string
  'Units Sold':       number
  'Buy NAV':          number
  Cost:               number
  Value:              number
  Gain:               number
  Type:               'LTCG' | 'STCG'
}
interface FifoResult {
  total_units:  number
  total_value:  number
  total_cost:   number
  total_gain:   number
  stcg_gain:    number
  ltcg_gain:    number
  stcg_tax:     number
  ltcg_tax:     number
  total_tax:    number
  net_proceeds: number
  details:      FifoDetail[]
}

function FifoSimulator({ holdings }: { holdings: any[] }) {
  const sid                          = useSessionId()
  const [selectedFund, setSelectedFund] = useState<string>(holdings[0]?.Fund ?? '')
  const [simMode,      setSimMode]      = useState<'Units' | 'Amount'>('Amount')
  const [sliderVal,    setSliderVal]    = useState<number>(0)

  const fund      = holdings.find((h) => h.Fund === selectedFund)
  const maxUnits  = fund ? Number(fund.Units)            : 0
  const maxAmount = fund ? Number(fund['Market Value'])  : 0
  const nav       = fund ? Number(fund.NAV)              : 1

  const unitsToSell = simMode === 'Units'
    ? Math.min(sliderVal, maxUnits)
    : nav > 0 ? Math.min(sliderVal / nav, maxUnits) : 0

  const { data: fifo, isFetching } = useQuery<FifoResult>({
    queryKey: ['fifo', sid, selectedFund, unitsToSell.toFixed(4)],
    queryFn:  async () => {
      const res = await fetch(
        `/api/portfolio/${sid}/fifo?fund=${encodeURIComponent(selectedFund)}&units=${unitsToSell}&nav=${nav}`
      )
      if (!res.ok) throw new Error('FIFO failed')
      return res.json()
    },
    enabled:   !!sid && !!selectedFund && unitsToSell > 0.001,
    staleTime: 30_000,
  })

  return (
    <Paper elevation={1} sx={{ p: 3, borderRadius: 3 }}>
      <SectionHeader
        title="FIFO Redemption Tax Simulator"
        subtitle="Select a fund and simulate a sell-off to see exact FIFO tax impact"
      />

      <Grid container spacing={3}>
        {/* ── LEFT: Inputs ───────────────────────────────────────── */}
        <Grid item xs={12} md={5}>
          <FormControl fullWidth size="small" sx={{ mb: 2.5 }}>
            <InputLabel>Select Fund to Simulate Sale</InputLabel>
            <Select
              value={selectedFund}
              label="Select Fund to Simulate Sale"
              onChange={(e) => { setSelectedFund(e.target.value); setSliderVal(0) }}
            >
              {holdings.map((h) => (
                <MenuItem key={h.Fund} value={h.Fund} sx={{ fontSize: 12 }}>
                  <Box sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 340 }}>
                    {h.Fund}
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <Typography variant="overline" display="block" sx={{ mb: 1 }}>Simulation Input</Typography>
          <ToggleButtonGroup
            exclusive size="small"
            value={simMode}
            onChange={(_, v) => v && setSimMode(v)}
            sx={{ mb: 2.5 }}
          >
            <ToggleButton value="Units"  sx={{ fontSize: 12, fontWeight: 600, px: 2.5 }}>Units</ToggleButton>
            <ToggleButton value="Amount" sx={{ fontSize: 12, fontWeight: 600, px: 2.5 }}>Amount (₹)</ToggleButton>
          </ToggleButtonGroup>

          {/* Slider */}
          <Box sx={{ mb: 2.5 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
              <Typography variant="body2" fontWeight={600}>
                {simMode === 'Units' ? 'Units to sell' : 'Amount to sell'}
              </Typography>
              <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 12, color: '#1D4ED8', fontWeight: 700 }}>
                {simMode === 'Units'
                  ? `${sliderVal.toFixed(2)} / ${maxUnits.toFixed(2)}`
                  : `${fmtInr(sliderVal)} / ${fmtInr(maxAmount)}`}
              </Typography>
            </Box>
            <input
              type="range"
              min={0}
              max={simMode === 'Units' ? maxUnits : maxAmount}
              step={simMode === 'Units' ? Math.max(0.01, maxUnits / 200) : Math.max(100, maxAmount / 200)}
              value={sliderVal}
              onChange={(e) => setSliderVal(Number(e.target.value))}
              style={{ width: '100%', accentColor: '#1D4ED8', cursor: 'pointer' }}
            />
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              <Typography variant="caption" color="text.secondary">0</Typography>
              <Typography variant="caption" color="text.secondary">
                {simMode === 'Units' ? `${maxUnits.toFixed(2)} units` : fmtInr(maxAmount)}
              </Typography>
            </Box>
          </Box>

          {/* Info pill */}
          <Box sx={{
            p: 1.5, background: '#EFF6FF', borderRadius: 2,
            border: '1px solid #BFDBFE',
          }}>
            <Typography sx={{ fontSize: 12, color: '#1E3A8A', lineHeight: 1.6 }}>
              Selling <strong>{unitsToSell.toFixed(4)} units</strong> out of{' '}
              <strong>{maxUnits.toFixed(4)}</strong> total
              {nav > 0 && <> · NAV ₹{nav.toFixed(4)}</>}
            </Typography>
          </Box>

          {/* Fund summary */}
          {fund && (
            <Box sx={{ mt: 2, p: 1.5, background: '#F8FAFC', borderRadius: 2, border: '1px solid #E2E8F0' }}>
              {[
                { label: 'Current Value', value: fmtInr(fund['Market Value'], true) },
                { label: 'Invested',      value: fmtInr(fund.Invested, true) },
                { label: 'Unrealised Gain', value: fmtInr(fund.Gain, true) },
                { label: 'Return',        value: `${fund['Gain%']?.toFixed(2)}%` },
              ].map((s) => (
                <Box key={s.label} sx={{ display: 'flex', justifyContent: 'space-between', py: 0.5, borderBottom: '1px solid #F1F5F9', '&:last-child': { borderBottom: 'none' } }}>
                  <Typography sx={{ fontSize: 11, color: '#64748B', fontWeight: 500 }}>{s.label}</Typography>
                  <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11, fontWeight: 700, color: '#0F172A' }}>{s.value}</Typography>
                </Box>
              ))}
            </Box>
          )}
        </Grid>

        {/* ── RIGHT: Results ──────────────────────────────────────── */}
        <Grid item xs={12} md={7}>
          {isFetching && (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
              <CircularProgress size={28} />
            </Box>
          )}

          {fifo && !isFetching && (
            <>
              {/* Net proceeds card */}
              <Box sx={{
                p: 2.5, borderRadius: 3, mb: 2,
                border: '2px solid #6366F1',
                background: 'linear-gradient(135deg, #F5F3FF 0%, #EFF6FF 100%)',
              }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Box>
                    <Typography variant="overline" sx={{ color: '#6366F1' }}>Net Proceeds (Post Tax)</Typography>
                    <Typography sx={{
                      fontFamily: '"DM Mono",monospace', fontSize: '1.6rem',
                      fontWeight: 500, color: '#6366F1', letterSpacing: '-0.5px',
                    }}>
                      {fmtInr(fifo.net_proceeds)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Gross: {fmtInr(fifo.total_value)}
                    </Typography>
                  </Box>
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography sx={{ fontSize: 10, fontWeight: 800, color: '#DC2626', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                      Est. Tax
                    </Typography>
                    <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '1.3rem', fontWeight: 700, color: '#DC2626' }}>
                      {fmtInr(fifo.total_tax)}
                    </Typography>
                  </Box>
                </Box>
              </Box>

              {/* LTCG / STCG breakdown */}
              <Grid container spacing={1.5} sx={{ mb: 2 }}>
                <Grid item xs={6}>
                  <Box sx={{ p: 1.75, background: '#ECFDF5', borderRadius: 2, border: '1px solid #A7F3D0' }}>
                    <Typography sx={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em', mb: 0.5 }}>
                      LTCG (&gt;1Y)
                    </Typography>
                    <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '1rem', fontWeight: 700, color: '#059669' }}>
                      {fmtInr(fifo.ltcg_gain)}
                    </Typography>
                    <Typography sx={{ fontSize: 10, color: '#64748B', mt: 0.25 }}>
                      Tax: {fmtInr(fifo.ltcg_tax)} @ 12.5%
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={6}>
                  <Box sx={{ p: 1.75, background: '#FFFBEB', borderRadius: 2, border: '1px solid #FDE68A' }}>
                    <Typography sx={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase', letterSpacing: '0.06em', mb: 0.5 }}>
                      STCG (≤1Y)
                    </Typography>
                    <Typography sx={{ fontFamily: '"DM Mono",monospace', fontSize: '1rem', fontWeight: 700, color: '#D97706' }}>
                      {fmtInr(fifo.stcg_gain)}
                    </Typography>
                    <Typography sx={{ fontSize: 10, color: '#64748B', mt: 0.25 }}>
                      Tax: {fmtInr(fifo.stcg_tax)} @ 20.0%
                    </Typography>
                  </Box>
                </Grid>
              </Grid>

              {/* FIFO Ledger */}
              {fifo.details?.length > 0 && (
                <>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Detailed FIFO Acquisition Matching
                  </Typography>
                  <Paper elevation={0} sx={{ border: '1px solid #E2E8F0', borderRadius: 2, overflow: 'hidden' }}>
                    <TableContainer sx={{ maxHeight: 260 }}>
                      <Table size="small" stickyHeader>
                        <TableHead>
                          <TableRow>
                            {['Date','Units','Buy NAV','Cost','Value','Gain','Type'].map((h) => (
                              <TableCell key={h} sx={{ background: '#F8FAFC', fontSize: 10, fontWeight: 700, py: 1 }}>{h}</TableCell>
                            ))}
                          </TableRow>
                        </TableHead>
                        <TableBody>
                          {fifo.details.map((row, i) => (
                            <TableRow key={i} hover>
                              <TableCell sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11 }}>
                                {row['Acquisition Date']}
                              </TableCell>
                              <TableCell sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11 }}>
                                {Number(row['Units Sold']).toFixed(3)}
                              </TableCell>
                              <TableCell sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11 }}>
                                ₹{Number(row['Buy NAV']).toFixed(2)}
                              </TableCell>
                              <TableCell sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11 }}>
                                {fmtInr(row.Cost)}
                              </TableCell>
                              <TableCell sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11 }}>
                                {fmtInr(row.Value)}
                              </TableCell>
                              <TableCell sx={{ fontFamily: '"DM Mono",monospace', fontSize: 11, color: gainColor(row.Gain) }}>
                                {fmtInr(row.Gain)}
                              </TableCell>
                              <TableCell>
                                <Chip size="small" label={row.Type} sx={{
                                  fontSize: 10, fontWeight: 700, height: 20,
                                  background: row.Type === 'LTCG' ? '#ECFDF5' : '#FFFBEB',
                                  color:      row.Type === 'LTCG' ? '#059669' : '#D97706',
                                }} />
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableContainer>
                  </Paper>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                    Matched against purchase batches in chronological FIFO order.
                  </Typography>
                </>
              )}
            </>
          )}

          {!fifo && !isFetching && (
            <Box sx={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              height: 200, border: '2px dashed #E2E8F0', borderRadius: 3,
            }}>
              <Typography variant="body2" color="text.secondary" textAlign="center">
                Move the slider to simulate a redemption
              </Typography>
            </Box>
          )}
        </Grid>
      </Grid>
    </Paper>
  )
}

// ─────────────────────────────────────────────────────────
// Wrapper: loads holdings list then renders FifoSimulator
// ─────────────────────────────────────────────────────────
function FifoSimulatorWrapper() {
  const sid = useSessionId()
  const { data, isLoading } = useQuery({
    queryKey: ['holdingsForFifo', sid],
    queryFn:  () => apiClient.getHoldings(sid!, { sort_by: 'Market Value' }),
    enabled:  !!sid,
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <Skeleton variant="rectangular" height={400} sx={{ borderRadius: 3 }} />
  const holdings = data?.holdings ?? []
  if (!holdings.length) return null
  return <FifoSimulator holdings={holdings} />
}

// ─────────────────────────────────────────────────────────
// MAIN TAX TAB
// ─────────────────────────────────────────────────────────
export default function TaxTab() {
  const { data, isLoading, error } = useTax()

  return (
    <Box>
      <SectionHeader
        title="Tax Liability Estimator"
        subtitle="Estimates based on current holdings. Not financial/tax advice — consult a CA."
      />
      {error && <Alert severity="error" sx={{ mb: 2 }}>Failed to load tax data.</Alert>}

      {/* ── KPI Cards ─────────────────────────────────────────────── */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {[
          {
            label:  'ELSS Holdings',
            value:  fmtInr(data?.elss_value),
            sub:    `${data?.elss_count ?? 0} ELSS funds · ${fmtInr(data?.elss_invested)} invested`,
            accent: 'info' as const,
          },
          {
            label:  'Equity Gains',
            value:  fmtInr(data?.equity_gain),
            sub:    'Total unrealised equity gains',
            accent: (data?.equity_gain ?? 0) >= 0 ? 'success' as const : 'danger' as const,
          },
          {
            label:  'Est. Equity LTCG Tax',
            value:  fmtInr(data?.ltcg_equity),
            sub:    '12.5% on gains above ₹1.25L · if redeemed today',
            accent: 'warn' as const,
          },
          {
            label:  'Est. Debt STCG Tax',
            value:  fmtInr(data?.stcg_debt),
            sub:    'At 30% slab rate · debt/hybrid gains',
            accent: 'danger' as const,
          },
        ].map((card) => (
          <Grid item xs={12} sm={6} md={3} key={card.label}>
            <MetricCard {...card} loading={isLoading} />
          </Grid>
        ))}
      </Grid>



      <Alert severity="warning" sx={{ borderRadius: 2, mb: 4 }}>
        ⚠ Tax figures are <strong>illustrative estimates</strong>. Holding periods, grandfathering clauses,
        and debt taxation post-April 2023 may differ. Consult a SEBI-registered financial advisor and CA.
      </Alert>

      <Divider sx={{ mb: 4 }} />

      {/* ── FIFO Redemption Tax Simulator ────────────────────────── */}
      <FifoSimulatorWrapper />
    </Box>
  )
}
