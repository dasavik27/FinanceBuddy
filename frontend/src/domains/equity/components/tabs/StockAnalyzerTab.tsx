import { useMemo, useState } from 'react'
import { Box, Typography, Paper, TextField, Button, CircularProgress, Alert, Grid, Chip, InputAdornment, Autocomplete } from '@mui/material'
import SearchIcon from '@mui/icons-material/Search'
import AutoGraphIcon from '@mui/icons-material/AutoGraph'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { apiClient } from '../../../../shared/api/client'
import { useDebounce } from '../../../../shared/hooks/useDebounce'
import { fmtInr, fmtNum } from '../../../../shared/utils/fmt'
import { useEquitySessionId, useStockSearch } from '../../hooks/useEquityData'
import type { StockAnalysis, StockSearchResult } from '../../types'

/** Alias kept so the existing render code below needs no edits. */
const fmtINR = fmtInr

function StatBox({ label, value }: { label: string, value: string | number }) {
    return (
        <Box sx={{ p: 2, background: 'rgba(255,255,255,0.03)', borderRadius: '12px' }}>
            <Typography sx={{ color: '#94A3B8', fontSize: '0.8rem', mb: 0.5 }}>{label}</Typography>
            <Typography sx={{ color: '#F8FAFC', fontWeight: 700, fontSize: '1rem' }}>{value}</Typography>
        </Box>
    )
}

export default function StockAnalyzerTab() {
  const sessionId = useEquitySessionId()
  const [query, setQuery] = useState('')

  // Debounced, then keyed into react-query. This was wired straight to onInputChange
  // with no debounce and no abort, so typing "RELIANCE" issued seven sequential GETs
  // and applied the results in arrival order — which for a search box means the
  // dropdown could settle on the results for a prefix the user had already moved past.
  const debouncedQuery = useDebounce(query, 300)
  const { data: searchData, isFetching: searching } = useStockSearch(debouncedQuery)
  const options: StockSearchResult[] = searchData?.results ?? []

  const [stock, setStock] = useState<StockAnalysis | null>(null)
  const [loadingAnalysis, setLoadingAnalysis] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)

  const [impactAmount, setImpactAmount] = useState('100000')
  const [impact, setImpact] = useState<any>(null)
  const [loadingImpact, setLoadingImpact] = useState(false)

  const handleImpact = async (symbol: string, amt: number) => {
      if (!sessionId || !amt || Number.isNaN(amt) || amt <= 0) return
      setLoadingImpact(true)
      try {
          const data = await apiClient.stockPortfolioImpact(symbol, amt, sessionId)
          setImpact(data)
      } catch (e) {
          console.error(e)
      } finally {
          setLoadingImpact(false)
      }
  }

  const handleSelect = async (val: StockSearchResult | null) => {
      if (!val) {
          setStock(null); setImpact(null); setAnalysisError(null); return
      }
      setLoadingAnalysis(true)
      setAnalysisError(null)
      try {
          const data = await apiClient.analyzeStock(val.symbol)
          setStock(data)
          if (sessionId) {
              void handleImpact(data.symbol, parseFloat(impactAmount))
          }
      } catch (e) {
          const status = (e as { response?: { status?: number } })?.response?.status
          setAnalysisError(
              status === 404
                  ? 'That symbol was not recognised.'
                  : 'Could not load analysis for that stock. Please try again.',
          )
      } finally {
          setLoadingAnalysis(false)
      }
  }

  // Memoized: this zip previously ran on every render and handed recharts a new array.
  const chartData = useMemo(() => {
      const dates = stock?.chart?.dates ?? []
      const prices = stock?.chart?.prices ?? []
      return dates.map((d, i) => ({ date: d, price: prices[i] ?? null }))
  }, [stock])

  // Derived once and null-guarded. This was read as `stock.year_return >= 0` in five
  // places; on a stock the provider has no 1Y history for, the field is absent and
  // `undefined >= 0` is false, so a missing return silently rendered as a red loss.
  const yearReturn = stock?.year_return ?? 0
  const returnColor = yearReturn >= 0 ? '#10B981' : '#EF4444'

  return (
    <Box>
      <Box sx={{ maxWidth: 800, mx: 'auto', mb: 6 }}>
          <Typography sx={{ textAlign: 'center', color: '#94A3B8', mb: 3 }}>
              Search for an NSE stock to view fundamentals and simulate its impact on your portfolio.
          </Typography>
          <Autocomplete
              options={options}
              getOptionLabel={(opt) => `${opt.symbol} - ${opt.name}`}
              isOptionEqualToValue={(a, b) => a.symbol === b.symbol}
              filterOptions={(x) => x}   // the server already filtered
              inputValue={query}
              onInputChange={(_, v) => setQuery(v)}
              onChange={(_, v) => handleSelect(v)}
              loading={searching}
              renderInput={(params) => (
                  <TextField
                      {...params}
                      placeholder="Search stocks (e.g. RELIANCE, TCS)..."
                      variant="outlined"
                      fullWidth
                      InputProps={{
                          ...params.InputProps,
                          startAdornment: <SearchIcon sx={{ color: '#64748B', ml: 1, mr: 1 }} />,
                          sx: { 
                              borderRadius: '16px', background: 'rgba(15,23,42,0.8)',
                              '& fieldset': { borderColor: 'rgba(16,185,129,0.3)' },
                              '&:hover fieldset': { borderColor: 'rgba(16,185,129,0.5)' },
                              '&.Mui-focused fieldset': { borderColor: '#10B981' },
                              color: '#fff'
                          }
                      }}
                  />
              )}
          />
      </Box>

      {loadingAnalysis && <Box sx={{ display: 'flex', justifyContent: 'center', p: 5 }}><CircularProgress /></Box>}

      {analysisError && !loadingAnalysis && (
          <Alert severity="error" sx={{ borderRadius: '16px', mb: 3 }}>{analysisError}</Alert>
      )}

      {stock && !loadingAnalysis && (
          <Grid container spacing={4}>
              <Grid item xs={12} lg={8}>
                  {/* Fundamental Analysis Card */}
                  <Paper className="glass" sx={{ p: { xs: 3, md: 4 }, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 4 }}>
                          <Box>
                              <Typography sx={{ fontWeight: 900, color: '#F8FAFC', fontSize: '1.8rem' }}>{stock.name}</Typography>
                              <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
                                  <Chip label={stock.symbol} size="small" sx={{ background: 'rgba(16,185,129,0.1)', color: '#10B981', fontWeight: 700 }} />
                                  <Chip label={stock.sector} size="small" sx={{ background: 'rgba(59,130,246,0.1)', color: '#3B82F6', fontWeight: 700 }} />
                              </Box>
                          </Box>
                          <Box sx={{ textAlign: 'right' }}>
                              <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.8rem' }}>{fmtINR(stock.current_price)}</Typography>
                              <Typography sx={{ color: returnColor, fontWeight: 700 }}>
                                  {yearReturn >= 0 ? '+' : ''}{fmtNum(yearReturn, 2)}% (1Y)
                              </Typography>
                          </Box>
                      </Box>

                      {/* Mini Chart */}
                      {chartData.length > 0 && (
                          <Box sx={{ height: 200, mb: 4 }}>
                               <ResponsiveContainer width="100%" height="100%">
                                   <AreaChart data={chartData}>
                                        <defs>
                                            <linearGradient id="colorPrice" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor={returnColor} stopOpacity={0.3}/>
                                                <stop offset="95%" stopColor={returnColor} stopOpacity={0}/>
                                            </linearGradient>
                                        </defs>
                                       <Tooltip contentStyle={{ borderRadius: '12px', background: '#0F172A', border: 'none' }} labelStyle={{ display: 'none' }} formatter={(v: number) => [fmtINR(v), 'Price']} />
                                       <Area type="monotone" dataKey="price" stroke={returnColor} fill="url(#colorPrice)" strokeWidth={2} />
                                   </AreaChart>
                               </ResponsiveContainer>
                          </Box>
                      )}

                      <Grid container spacing={2}>
                          <Grid item xs={6} sm={4}><StatBox label="Market Cap" value={stock.market_cap_cr ? `₹${stock.market_cap_cr.toLocaleString()} Cr` : '-'} /></Grid>
                          <Grid item xs={6} sm={4}><StatBox label="P/E Ratio" value={stock.pe_ratio?.toFixed(2) || '-'} /></Grid>
                          <Grid item xs={6} sm={4}><StatBox label="P/B Ratio" value={stock.pb_ratio?.toFixed(2) || '-'} /></Grid>
                          <Grid item xs={6} sm={4}><StatBox label="Dividend Yield" value={stock.dividend_yield ? `${stock.dividend_yield}%` : '-'} /></Grid>
                          <Grid item xs={6} sm={4}><StatBox label="ROE" value={stock.roe ? `${stock.roe}%` : '-'} /></Grid>
                          <Grid item xs={6} sm={4}><StatBox label="Beta (Volatility)" value={stock.beta?.toFixed(2) || '-'} /></Grid>
                      </Grid>
                  </Paper>
              </Grid>

              <Grid item xs={12} lg={4}>
                  {/* Portfolio Impact Simulator */}
                  <Paper className="glass" sx={{ p: { xs: 3, md: 4 }, borderRadius: '24px', background: 'rgba(15,23,42,0.6)', border: '1px solid rgba(255,255,255,0.06)', height: '100%' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 3 }}>
                          <AutoGraphIcon sx={{ color: '#8B5CF6' }} />
                          <Typography sx={{ fontWeight: 800, color: '#F8FAFC', fontSize: '1.1rem' }}>Portfolio Impact</Typography>
                      </Box>
                      
                      {!sessionId ? (
                          <Alert severity="info" sx={{ background: 'rgba(59,130,246,0.1)' }}>Connect your portfolio to simulate the impact of buying this stock.</Alert>
                      ) : (
                          <Box>
                              <Typography sx={{ color: '#94A3B8', fontSize: '0.9rem', mb: 1 }}>Simulate Investment Amount</Typography>
                              <Box sx={{ display: 'flex', gap: 2, mb: 4 }}>
                                  <TextField 
                                      value={impactAmount}
                                      onChange={(e) => setImpactAmount(e.target.value)}
                                      type="number"
                                      size="small"
                                      fullWidth
                                      InputProps={{
                                          startAdornment: <InputAdornment position="start" sx={{ color: '#94A3B8' }}>₹</InputAdornment>,
                                          sx: { color: '#fff', background: 'rgba(255,255,255,0.05)' }
                                      }}
                                  />
                                  <Button 
                                      variant="contained" 
                                      onClick={() => handleImpact(stock.symbol, parseFloat(impactAmount))}
                                      disabled={loadingImpact}
                                      sx={{ background: '#8B5CF6', '&:hover': { background: '#7C3AED' } }}
                                  >
                                      Simulate
                                  </Button>
                              </Box>

                              {loadingImpact ? <CircularProgress size={24} /> : impact ? (
                                  <Box>
                                      {impact.already_owned && (
                                          <Alert severity="info" sx={{ mb: 3, background: 'rgba(59,130,246,0.1)' }}>
                                              You already own {impact.existing_position.quantity} shares of {stock.symbol}.
                                          </Alert>
                                      )}
                                      
                                      <Typography sx={{ color: '#F8FAFC', fontWeight: 700, mb: 2 }}>{stock.sector} Exposure Shift</Typography>
                                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                                          <Typography sx={{ color: '#94A3B8' }}>Before</Typography>
                                          <Typography sx={{ color: '#F8FAFC', fontWeight: 700 }}>{impact.sector_weight_before}%</Typography>
                                      </Box>
                                      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
                                          <Typography sx={{ color: '#94A3B8' }}>After</Typography>
                                          <Typography sx={{ color: '#10B981', fontWeight: 700 }}>{impact.sector_weight_after}%</Typography>
                                      </Box>

                                      <Box sx={{ p: 2, background: 'rgba(16,185,129,0.1)', borderRadius: '12px', border: '1px solid rgba(16,185,129,0.2)' }}>
                                          <Typography sx={{ color: '#10B981', fontWeight: 700, textAlign: 'center' }}>
                                              {impact.sector_delta > 0 ? '+' : ''}{impact.sector_delta}% increase in {stock.sector}
                                          </Typography>
                                      </Box>

                                      {impact.concentration_warning && (
                                          <Alert severity="warning" sx={{ mt: 3, background: 'rgba(245,158,11,0.1)' }}>
                                              Warning: This trade would make {stock.symbol} more than 15% of your total equity portfolio.
                                          </Alert>
                                      )}
                                  </Box>
                              ) : null}
                          </Box>
                      )}
                  </Paper>
              </Grid>
          </Grid>
      )}
    </Box>
  )
}
