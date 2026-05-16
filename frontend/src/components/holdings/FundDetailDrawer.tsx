/**
 * FundDetailDrawer.tsx
 * Premium fund detail side-panel — AlphaTrack Pro standard
 */
import { useState, useEffect } from 'react'
import {
  Drawer, Box, Typography, Divider, Chip, Grid, CircularProgress,
  IconButton, Stack, alpha, Alert, Paper
} from '@mui/material'
import CloseIcon from '@mui/icons-material/Close'

import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts'
import { ChartTooltip } from '../charts/ChartTooltip'
import { fmtInr, gainColor } from '../../api/fmt'
import { useQuery } from '@tanstack/react-query'
import { useSessionId } from '../../store/appStore'

// ── Heuristic sector / credit profile ────────────────────────────────────────
function getProfile(category: string, fundName: string) {
  const n = fundName.toUpperCase()
  const isDebt = ['Debt', 'Liquid', 'Gilt', 'Banking & PSU', 'Dynamic Bond'].some(
    (k) => category.includes(k) || n.includes(k.toUpperCase())
  )

  if (isDebt) {
    return {
      type: 'debt' as const,
      creditProfile: [
        { rating: 'AAA / Sovereign', pct: 72, color: '#6366F1' },
        { rating: 'AA+',             pct: 14, color: '#4EDE93' },
        { rating: 'AA',              pct:  8, color: '#FCD34D' },
        { rating: 'A & Below',       pct:  4, color: '#FF516A' },
        { rating: 'Cash & Equiv.',   pct:  2, color: '#94A3B8' },
      ],
      durationProfile: [
        { bucket: '< 1 Year',  pct: n.includes('LIQUID') || n.includes('SHORT') ? 85 : 20 },
        { bucket: '1–3 Years', pct: n.includes('SHORT') ? 12 : n.includes('MEDIUM') ? 45 : 30 },
        { bucket: '3–7 Years', pct: n.includes('LONG') ? 40 : 25 },
        { bucket: '> 7 Years', pct: n.includes('GILT') ? 55 : n.includes('LONG') ? 30 : 25 },
      ].filter(d => d.pct > 0),
      topHoldings: [
        { name: '8.24% GOI 2033',       pct: 18.4 },
        { name: '7.26% GOI 2032',       pct: 14.1 },
        { name: 'HDFC Bank CD',          pct:  9.3 },
        { name: 'REC Ltd NCD',           pct:  7.8 },
        { name: 'Power Finance Corp.',   pct:  6.2 },
      ],
      radarData: null,
    }
  }

  // Equity — build sector radar
  let sectors: Record<string, number>
  if (n.includes('BANK') || n.includes('FINANCIAL')) {
    sectors = { Financials: 82, Services: 10, Tech: 5, Others: 3 }
  } else if (n.includes('TECH') || n.includes('DIGITAL') || n.includes(' IT')) {
    sectors = { Technology: 78, Services: 15, Healthcare: 4, Others: 3 }
  } else if (n.includes('PHARMA') || n.includes('HEALTH')) {
    sectors = { Healthcare: 76, Consumer: 12, Technology: 7, Others: 5 }
  } else if (n.includes('SMALL')) {
    sectors = { Industrials: 25, Consumer: 20, Financials: 18, Materials: 14, Healthcare: 10, Others: 13 }
  } else if (n.includes('MID')) {
    sectors = { Financials: 20, Industrials: 18, Consumer: 16, Healthcare: 12, Technology: 9, Others: 25 }
  } else {
    sectors = { Financials: 34, Technology: 15, Energy: 12, Consumer: 11, Healthcare: 7, Others: 21 }
  }

  const topHoldings = n.includes('SMALL')
    ? [
        { name: 'Kaynes Technology',     pct: 4.2 },
        { name: 'Craftsman Auto.',        pct: 3.8 },
        { name: 'Birlasoft',             pct: 3.4 },
        { name: 'Dixon Technologies',    pct: 3.1 },
        { name: 'Navin Fluorine',        pct: 2.9 },
      ]
    : n.includes('MID')
    ? [
        { name: 'Persistent Systems',    pct: 5.1 },
        { name: 'Coforge',               pct: 4.7 },
        { name: 'Cholamandalam Fin.',    pct: 4.2 },
        { name: 'Max Healthcare',        pct: 3.9 },
        { name: 'Voltas Ltd',            pct: 3.3 },
      ]
    : [
        { name: 'HDFC Bank',             pct: 9.4 },
        { name: 'Reliance Industries',   pct: 8.2 },
        { name: 'ICICI Bank',            pct: 7.1 },
        { name: 'Infosys',               pct: 5.8 },
        { name: 'Tata Consultancy Svcs', pct: 4.3 },
      ]

  return {
    type: 'equity' as const,
    creditProfile: null,
    durationProfile: null,
    topHoldings,
    radarData: Object.entries(sectors).map(([sector, value]) => ({ sector, value })),
  }
}

import { useFundInsights } from '../../hooks/useData'
import { getTaxProfile } from '../../rules/taxRules'

// ── Stat chip ─────────────────────────────────────────────────────────────────
function StatChip({ label, value, tip, valueColor, isLive }: { label: string; value: string; tip?: string; valueColor?: string; isLive?: boolean }) {
  return (
    <Box sx={{ 
      p: 2, background: 'rgba(255,255,255,0.03)', borderRadius: '16px', 
      border: '1px solid rgba(255,255,255,0.05)', position: 'relative' 
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
        <Typography sx={{ fontSize: 9, color: 'text.secondary', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          {label}
        </Typography>
        {isLive && (
          <Box sx={{ 
            width: 6, height: 6, borderRadius: '50%', background: '#4EDE93', 
            boxShadow: '0 0 6px #4EDE93',
            animation: 'pulse 1.5s infinite ease-in-out'
          }} />
        )}
      </Box>
      <Typography className="num" sx={{ fontSize: 15, fontWeight: 800, color: valueColor ?? '#fff' }}>
        {value}
      </Typography>
    </Box>
  )
}

// ── Props ─────────────────────────────────────────────────────────────────────
interface FundDetailDrawerProps {
  fund: any | null
  onClose: () => void
}

const THEME_COLORS = ['#6366F1', '#4EDE93', '#FCD34D', '#FF516A', '#8B5CF6', '#94A3B8']

export default function FundDetailDrawer({ fund, onClose }: FundDetailDrawerProps) {
  const open = !!fund
  const sid = useSessionId()
  const [sellUnits, setSellUnits] = useState<number>(0)
  const [liveNav, setLiveNav] = useState<number | null>(null)

  useEffect(() => {
    setSellUnits(0)
    setLiveNav(null)
  }, [fund?.Fund])

  // Live NAV Query
  useQuery({
    queryKey: ['live-nav', fund?.ISIN],
    queryFn: async () => {
      if (!fund?.ISIN) return null
      const res = await fetch(`/api/market/nav/${fund.ISIN}`)
      if (!res.ok) return null
      const d = await res.json()
      if (d.nav) setLiveNav(d.nav)
      return d.nav
    },
    enabled: !!fund?.ISIN,
    staleTime: 5 * 60_000,
  })

  // Live Institutional Insights
  const { data: insights, isFetching: insightsLoading } = useFundInsights(fund?.ISIN ?? '', fund?.Fund ?? '')

  const effectiveNav = liveNav ?? fund?.NAV ?? 1
  const { data: fifo, isFetching: fifoLoading } = useQuery({
    queryKey: ['fifo-mini', sid, fund?.Fund, sellUnits, effectiveNav],
    queryFn: async () => {
      const res = await fetch(`/api/portfolio/${sid}/tax/simulate?fund=${encodeURIComponent(fund.Fund)}&units_to_sell=${sellUnits}&nav=${effectiveNav}`)
      return res.json()
    },
    enabled: !!sid && !!fund && sellUnits > 0.0001,
  })

  const currentVal = (fund?.Units ?? 0) * effectiveNav
  const totalGain  = currentVal - (fund?.Invested ?? 0)
  const weight  = fund?.['Weight%'] ?? 0

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{
        sx: { width: { xs: '100vw', lg: 600 }, bgcolor: '#0B1326', borderLeft: '1px solid rgba(255,255,255,0.05)', backgroundImage: 'none' },
      }}
    >
      {fund && (
        <Box sx={{ height: '100%', overflow: 'auto', bgcolor: '#0B1326', color: '#fff' }}>
          {/* ── Institutional Hero Header ────────────────────────────── */}
          <Box sx={{
            p: 4, pt: 6,
            background: `linear-gradient(135deg, ${alpha('#6366F1', 0.15)} 0%, ${alpha('#0B1326', 0.1)} 100%)`,
            borderBottom: '1px solid rgba(255,255,255,0.05)',
            position: 'relative'
          }}>
            <IconButton onClick={onClose} sx={{ position: 'absolute', top: 20, right: 20, color: 'text.secondary' }}>
              <CloseIcon />
            </IconButton>
            
            <Stack spacing={1}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 900, letterSpacing: '0.2em' }}>
                  FUND AUDIT COCKPIT
                </Typography>
                {insights?.source && (
                   <Chip label={insights.source.toUpperCase()} size="small" sx={{ height: 16, fontSize: 8, fontWeight: 900, bgcolor: 'rgba(255,255,255,0.05)', color: 'text.secondary', border: '1px solid rgba(255,255,255,0.1)' }} />
                )}
              </Box>
              <Typography variant="h4" sx={{ fontWeight: 900, letterSpacing: '-0.02em', color: '#fff' }}>
                {fund.Fund}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', pt: 1 }}>
                <Chip label={fund.Category} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.05)', color: 'text.secondary', fontWeight: 800, fontSize: 10 }} />
                <Chip label={fund['Cap Type']} size="small" sx={{ bgcolor: alpha('#4EDE93', 0.1), color: '#4EDE93', fontWeight: 800, fontSize: 10 }} />
                <Chip label={fund.Plan} size="small" sx={{ bgcolor: alpha('#6366F1', 0.1), color: '#6366F1', fontWeight: 800, fontSize: 10 }} />
                {fund.ISIN && fund.ISIN !== 'N/A' && (
                  <Chip label={`ISIN: ${fund.ISIN}`} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.05)', color: 'text.secondary', fontWeight: 700, fontSize: 10, fontFamily: 'monospace' }} />
                )}
              </Box>
            </Stack>
          </Box>

          <Box sx={{ p: 4 }}>
            {/* ── Position Summary ────────────────────────────────────── */}
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 800, letterSpacing: '0.1em', display: 'block', mb: 2 }}>YOUR POSITION</Typography>
            <Grid container spacing={2} sx={{ mb: 4 }}>
              <Grid item xs={6} md={4}>
                <StatChip label="CURRENT VALUE" value={fmtInr(currentVal)} isLive={!!liveNav} />
              </Grid>
              <Grid item xs={6} md={4}>
                <StatChip label="INVESTED" value={fmtInr(fund.Invested)} />
              </Grid>
              <Grid item xs={6} md={4}>
                <StatChip label="TOTAL P&L" value={fmtInr(totalGain)} valueColor={gainColor(totalGain)} isLive={!!liveNav} />
              </Grid>
              <Grid item xs={6} md={4}>
                <StatChip label="LIVE NAV" value={`₹${effectiveNav.toFixed(2)}`} isLive={!!liveNav} />
              </Grid>
              <Grid item xs={6} md={4}>
                <StatChip label="PORTFOLIO WEIGHT" value={`${weight.toFixed(1)}%`} valueColor={weight > 25 ? '#FF516A' : '#fff'} />
              </Grid>
              <Grid item xs={6} md={4}>
                <StatChip label="UNITS HELD" value={Number(fund.Units ?? 0).toFixed(3)} />
              </Grid>
            </Grid>

            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', mb: 4 }} />

            {/* ── Fund Insights (Dynamic) ─────────────────────────── */}
            <Box sx={{ mb: 4 }}>
              <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 800, letterSpacing: '0.1em', display: 'block', mb: 2 }}>FUND INSIGHTS</Typography>
              {insightsLoading ? (
                <Grid container spacing={2}>
                  {[1,2,3,4].map(i => <Grid item xs={6} md={3} key={i}><Paper sx={{ height: 60, bgcolor: 'rgba(255,255,255,0.05)', borderRadius: '16px' }}><CircularProgress size={16} sx={{ m: 2 }} /></Paper></Grid>)}
                </Grid>
              ) : (
                (() => {
                  const erVal = insights?.expense_ratio || "N/A"
                  const aumVal = insights?.aum || "N/A"
                  const exitVal = insights?.exit_load || "N/A"
                  const riskVal = insights?.risk || "UNRATED"
                  
                  const getRiskMeta = (rStr: string) => {
                    const r = (rStr || '').toUpperCase()
                    if (r === 'UNRATED' || r === 'N/A') {
                      return { color: '#94A3B8', bg: 'rgba(255,255,255,0.04)', border: 'rgba(255,255,255,0.08)' }
                    }
                    if (r.includes('VERY HIGH') || r === 'HIGH') {
                      return { color: '#FF516A', bg: alpha('#FF516A', 0.08), border: alpha('#FF516A', 0.2) }
                    }
                    if (r.includes('MODERATE') || r.includes('MODERATELY HIGH')) {
                      return { color: '#FCD34D', bg: alpha('#FCD34D', 0.08), border: alpha('#FCD34D', 0.2) }
                    }
                    return { color: '#4EDE93', bg: alpha('#4EDE93', 0.08), border: alpha('#4EDE93', 0.2) }
                  }
                  const riskMeta = getRiskMeta(riskVal)

                  return (
                    <Grid container spacing={2}>
                      <Grid item xs={6} md={3}>
                        <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.08)', boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.05)' }}>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, display: 'block', mb: 0.5, fontSize: 10 }}>EXPENSE RATIO</Typography>
                          <Typography className="num" sx={{ fontSize: 15, fontWeight: 800, color: '#fff' }}>{erVal}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.08)', boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.05)' }}>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, display: 'block', mb: 0.5, fontSize: 10 }}>TOTAL AUM</Typography>
                          <Typography className="num" sx={{ fontSize: 15, fontWeight: 800, color: '#fff' }}>{aumVal}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.04)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.08)', boxShadow: 'inset 0 1px 1px rgba(255,255,255,0.05)' }}>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, display: 'block', mb: 0.5, fontSize: 10 }}>EXIT LOAD</Typography>
                          <Typography sx={{ fontSize: 12, fontWeight: 800, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{exitVal}</Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={6} md={3}>
                        <Box sx={{ p: 2, bgcolor: riskMeta.bg, borderRadius: '16px', border: `1px solid ${riskMeta.border}` }}>
                          <Typography variant="caption" sx={{ color: riskMeta.color, fontWeight: 800, display: 'block', mb: 0.5, fontSize: 10 }}>RISK PROFILE</Typography>
                          <Typography sx={{ fontSize: 12, fontWeight: 900, color: riskMeta.color }}>{riskVal.toUpperCase()}</Typography>
                        </Box>
                      </Grid>
                    </Grid>
                  )
                })()
              )}
            </Box>

            {/* ── Main Analytical Grid (Only show if verified data exists) ───────── */}
            {((insights?.sectors || []).length > 0 || (insights?.holdings || []).length > 0) && (
              <>
                <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', mb: 4 }} />
                <Grid container spacing={4}>
                  {/* Left Column: Sector Radar */}
                  {(insights?.sectors || []).length > 0 && (
                    <Grid item xs={12} md={6}>
                      <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: '0.1em', display: 'block', mb: 3 }}>
                        SECTOR ALLOCATION
                      </Typography>
                      <ResponsiveContainer width="100%" height={240}>
                        <RadarChart data={insights?.sectors ?? []}>
                          <PolarGrid stroke="rgba(255,255,255,0.05)" />
                          <PolarAngleAxis dataKey="sector" tick={{ fontSize: 9, fill: alpha('#fff', 0.5), fontWeight: 700 }} />
                          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                          <Radar dataKey="value" stroke="#6366F1" fill="#6366F1" fillOpacity={0.2} strokeWidth={2} />
                          <Tooltip content={<ChartTooltip />} />
                        </RadarChart>
                      </ResponsiveContainer>
                    </Grid>
                  )}

                  {/* Right Column: Top Holdings */}
                  {(insights?.holdings || []).length > 0 && (
                    <Grid item xs={12} md={6}>
                      <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: '0.1em', display: 'block', mb: 3 }}>
                        TOP INSTRUMENTS
                      </Typography>
                      <Stack spacing={1.5}>
                        {insights.holdings.map((h: any, i: number) => (
                          <Box key={i}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                              <Typography variant="caption" sx={{ fontWeight: 800, color: 'text.secondary', fontSize: 10 }}>{h.name.toUpperCase()}</Typography>
                              <Typography variant="caption" className="num" sx={{ fontWeight: 900, color: '#fff' }}>{h.pct.toFixed(1)}%</Typography>
                            </Box>
                            <Box sx={{ height: 4, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 2 }}>
                              <Box sx={{ 
                                height: '100%', borderRadius: 2, bgcolor: THEME_COLORS[i % THEME_COLORS.length], 
                                width: `${Math.min(100, (h.pct / (insights.holdings[0].pct || 1)) * 100)}%` 
                              }} />
                            </Box>
                          </Box>
                        ))}
                      </Stack>
                    </Grid>
                  )}
                </Grid>
              </>
            )}

            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 4 }} />

            {/* ── Tax Intelligence ────────────────────────────────────── */}
            <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 800, letterSpacing: '0.1em', display: 'block', mb: 3 }}>TAX INTELLIGENCE</Typography>
            {(() => {
              const tax = getTaxProfile(fund.Category ?? '')
              return (
                <Grid container spacing={2} sx={{ mb: 2 }}>
                  <Grid item xs={6}>
                    <Paper sx={{ p: 2, bgcolor: alpha('#FCD34D', 0.03), border: '1px solid rgba(252, 211, 77, 0.1)', borderRadius: '20px' }}>
                      <Typography variant="caption" sx={{ color: '#FCD34D', fontWeight: 900, display: 'block', mb: 0.5 }}>{tax.stcgLabel}</Typography>
                      <Typography className="num" sx={{ fontSize: 18, fontWeight: 900, color: '#fff' }}>{tax.stcgVal}</Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={6}>
                    <Paper sx={{ p: 2, bgcolor: alpha('#4EDE93', 0.03), border: '1px solid rgba(78, 222, 147, 0.1)', borderRadius: '20px' }}>
                      <Typography variant="caption" sx={{ color: '#4EDE93', fontWeight: 900, display: 'block', mb: 0.5 }}>{tax.ltcgLabel}</Typography>
                      <Typography className="num" sx={{ fontSize: 18, fontWeight: 900, color: '#fff' }}>{tax.ltcgVal}</Typography>
                    </Paper>
                  </Grid>
                  <Grid item xs={12}>
                    <Box sx={{ p: 2, bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                      <Typography variant="body2" sx={{ color: 'on-surface-variant', fontWeight: 500 }}>💡 {tax.note}</Typography>
                    </Box>
                  </Grid>
                </Grid>
              )
            })()}

            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 4 }} />

            {/* ── Exit Tax Simulator ──────────────────────────────────── */}
            <Box sx={{ p: 3, borderRadius: '32px', bgcolor: alpha('#6366F1', 0.05), border: '1px solid rgba(99, 102, 241, 0.1)' }}>
               <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 900, mb: 3, display: 'block' }}>EXIT TAX SIMULATOR</Typography>
               <Box sx={{ mb: 4 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="caption" sx={{ fontWeight: 800, color: 'text.secondary' }}>UNITS TO SELL</Typography>
                    <Typography className="num" sx={{ color: 'primary.main', fontWeight: 900 }}>{sellUnits.toFixed(2)} / {Number(fund.Units ?? 0).toFixed(2)}</Typography>
                  </Box>
                  <input
                    type="range" min={0} max={Number(fund.Units ?? 0)} step={0.01} value={sellUnits}
                    onChange={(e) => setSellUnits(Number(e.target.value))}
                    style={{ width: '100%', accentColor: '#6366F1', cursor: 'pointer' }}
                  />
               </Box>

               {sellUnits <= 0.0001 ? (
                 <Box sx={{ p: 3, textAlign: 'center', bgcolor: 'rgba(0,0,0,0.1)', borderRadius: '20px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                   <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, letterSpacing: '0.05em' }}>
                     SLIDE TO SIMULATE REDEMPTION AUDIT
                   </Typography>
                 </Box>
               ) : fifoLoading ? (
                 <Box sx={{ py: 4, display: 'flex', justifyContent: 'center' }}><CircularProgress size={24} /></Box>
               ) : fifo && (
                 <Stack spacing={2}>
                    <Box sx={{ p: 2, borderRadius: '20px', bgcolor: 'rgba(0,0,0,0.2)', display: 'flex', justifyContent: 'space-between' }}>
                       <Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800 }}>PROCEEDS</Typography>
                          <Typography className="num" sx={{ fontWeight: 900, fontSize: 18 }}>{fmtInr(fifo.net_proceeds)}</Typography>
                       </Box>
                       <Box sx={{ textAlign: 'right' }}>
                          <Typography variant="caption" sx={{ color: '#FF516A', fontWeight: 800 }}>EST. TAX</Typography>
                          <Typography className="num" sx={{ fontWeight: 900, fontSize: 18, color: '#FF516A' }}>{fmtInr(fifo.total_tax)}</Typography>
                       </Box>
                    </Box>
                    {fifo.lock_in_warning && (
                      <Alert severity="error" sx={{ bgcolor: alpha('#FF516A', 0.1), color: '#FF516A', border: '1px solid rgba(255, 81, 106, 0.2)', borderRadius: '12px', '& .MuiAlert-icon': { color: '#FF516A' } }}>
                        {fifo.lock_in_warning}
                      </Alert>
                    )}
                 </Stack>
               )}
            </Box>
          </Box>
        </Box>
      )}
      <style>{` @keyframes pulse { 0% { transform: scale(0.95); opacity: 0.7; } 50% { transform: scale(1.1); opacity: 1; } 100% { transform: scale(0.95); opacity: 0.7; } } `}</style>
    </Drawer>
  )
}
