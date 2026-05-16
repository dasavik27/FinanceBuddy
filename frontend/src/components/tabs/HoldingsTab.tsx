import { useState } from 'react'
import {
  Box, Grid, Paper, Typography, Alert, Chip, Skeleton,
  TextField, InputAdornment, FormControl, Select, MenuItem,
  Avatar, IconButton, Divider, Stack, alpha
} from '@mui/material'

import SearchIcon from '@mui/icons-material/Search'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import FilterListIcon from '@mui/icons-material/FilterList'

import { useHoldings } from '../../hooks/useData'
import { SectionHeader } from '../ui'
import { fmtInr, gainColor } from '../../api/fmt'
import FundDetailDrawer from '../holdings/FundDetailDrawer'

/**
 * Institutional Health Signaling Engine
 * Categorizes portfolio instruments into performance health brackets:
 * - STRONG (>= 15% gain): High alpha performers
 * - WATCH (5% - 15% gain): Stable compounding assets
 * - NEUTRAL (0% - 5% gain): Modest or recent allocations
 * - REVIEW (< 0% gain): Capital erosion requiring attention
 */
function getHealthSignal(gainPct: number): { label: string; color: string; bg: string } {
  if (gainPct >= 15) return { label: 'STRONG', color: '#4EDE93', bg: 'rgba(78, 222, 147, 0.1)' }
  if (gainPct >= 5)  return { label: 'WATCH',  color: '#6366F1', bg: 'rgba(99, 102, 241, 0.1)' }
  if (gainPct >= 0)  return { label: 'NEUTRAL', color: '#94A3B8', bg: 'rgba(255, 255, 255, 0.05)' }
  return { label: 'REVIEW', color: '#FF516A', bg: 'rgba(255, 81, 106, 0.1)' }
}

/**
 * HoldingsTab: Institutional Asset Explorer
 * 
 * Provides an interactive ledger of all portfolio instruments with full-width master grid,
 * dynamic drawer inspection, real-time concentration warnings, and health indicators.
 */
export default function HoldingsTab() {
  const [search, setSearch] = useState('')
  const [capFilter, setCapFilter] = useState('All')
  const [selectedFund, setSelectedFund] = useState<any | null>(null)

  // Data Acquisition: Holdings Audit
  const { data: hold, isLoading: holdL } = useHoldings({
    sort_by: 'Market Value',
    ascending: 'false',
    search,
    cap_filter: capFilter,
  })

  // Derived Analytics
  const holdings = hold?.holdings ?? []
  const capTypes = ['All', ...(hold?.cap_types ?? [])]
  
  // Concentration Risk Assessment: Identify if any single fund exceeds institutional limits (25%)
  const maxWeightFund = holdings.length > 0
    ? holdings.reduce((a: any, b: any) => (a['Weight%'] ?? 0) > (b['Weight%'] ?? 0) ? a : b, holdings[0])
    : null
  const hasConcentration = maxWeightFund && (maxWeightFund['Weight%'] ?? 0) > 25

  return (
    <Box sx={{ pb: 6 }}>
      <SectionHeader 
        title="Holdings Explorer" 
        subtitle="Full-width institutional instrument inventory, search, and dynamic factsheet inspection" 
      />

      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', gap: 2, mb: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField
            size="small"
            placeholder="Search Asset Ledger by Instrument Name or AMC…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            sx={{ 
              flex: 1, minWidth: 320,
              '& .MuiOutlinedInput-root': { 
                borderRadius: '16px', 
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.08)',
                '&:hover': { borderColor: 'rgba(255,255,255,0.15)' }
              },
              '& fieldset': { border: 'none' }
            }}
            InputProps={{
              startAdornment: <InputAdornment position="start"><SearchIcon sx={{ color: 'primary.main' }} /></InputAdornment>
            }}
          />
          <FormControl size="small" sx={{ minWidth: 220 }}>
             <Select 
               value={capFilter} 
               onChange={(e) => setCapFilter(e.target.value)}
               sx={{ 
                 borderRadius: '16px', 
                 fontWeight: 700, 
                 fontSize: 14, 
                 background: 'rgba(255,255,255,0.03)',
                 '.MuiOutlinedInput-notchedOutline': { border: '1px solid rgba(255,255,255,0.08)' } 
               }}
               IconComponent={FilterListIcon}
             >
               {capTypes.map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
             </Select>
          </FormControl>
        </Box>

        {hasConcentration && (
          <Alert 
            severity="warning" 
            icon={<WarningAmberIcon sx={{ color: '#EAB308' }} />} 
            sx={{ 
              mb: 4, 
              borderRadius: '24px', 
              bgcolor: alpha('#EAB308', 0.05),
              color: '#FCD34D',
              border: '1px solid rgba(234, 179, 8, 0.2)',
              p: 2
            }}
          >
            <Typography variant="body2" sx={{ fontWeight: 800 }}>
              CONCENTRATION RISK AUDIT: {maxWeightFund.Fund} accounts for {maxWeightFund['Weight%']?.toFixed(1)}% of total portfolio exposure.
            </Typography>
          </Alert>
        )}

        <Typography variant="overline" sx={{ mb: 3, ml: 1, color: 'text.secondary', fontWeight: 800, display: 'block', letterSpacing: '0.15em' }}>
          ACTIVE ASSETS ({holdings.length} INSTRUMENTS)
        </Typography>

        {holdL ? (
          <Grid container spacing={4}>
            {[1, 2, 3, 4, 5, 6].map(n => (
              <Grid item xs={12} md={6} lg={4} key={n}>
                <Skeleton variant="rounded" height={200} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '28px' }} />
              </Grid>
            ))}
          </Grid>
        ) : (
          <Grid container spacing={4}>
            {holdings.map((h: any) => {
              const gainPct = h['Gain%'] ?? 0
              const weight = h['Weight%'] ?? 0
              const signal = getHealthSignal(gainPct)
              return (
                <Grid item xs={12} md={6} lg={4} key={h.Fund}>
                  <Paper 
                    className="glass"
                    onClick={() => setSelectedFund(h)}
                    sx={{ 
                      p: 3.5, borderRadius: '28px', cursor: 'pointer', height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
                      transition: 'all 0.4s cubic-bezier(0.23, 1, 0.32, 1)',
                      border: '1px solid rgba(255,255,255,0.05)',
                      '&:hover': { transform: 'translateY(-8px)', borderColor: 'primary.main', boxShadow: '0 20px 40px rgba(0,0,0,0.3)' }
                    }}
                  >
                    <Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 3 }}>
                        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', maxWidth: '75%' }}>
                          <Avatar sx={{ background: alpha('#6366F1', 0.1), borderRadius: '12px', width: 40, height: 40, border: '1px solid rgba(99, 102, 241, 0.1)' }}>
                            <AccountBalanceWalletIcon sx={{ fontSize: 20, color: 'primary.main' }} />
                          </Avatar>
                          <Box sx={{ overflow: 'hidden' }}>
                            <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#fff', fontSize: '1rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {h.Fund}
                            </Typography>
                            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, letterSpacing: '0.02em', display: 'flex', alignItems: 'center', gap: 0.75 }}>
                              {h.Category.toUpperCase()} <Box sx={{ width: 3, height: 3, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.2)' }} /> {h['Cap Type'].toUpperCase()}
                            </Typography>
                          </Box>
                        </Box>
                        <Chip 
                          label={signal.label} 
                          size="small" 
                          sx={{ height: 20, fontSize: 10, px: 0.5, fontWeight: 900, background: signal.bg, color: signal.color, borderRadius: '8px' }} 
                        />
                      </Box>

                      <Grid container spacing={2}>
                        <Grid item xs={6}>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, display: 'block', mb: 0.5 }}>MARKET VALUE</Typography>
                          <Typography variant="body1" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(h['Market Value'])}</Typography>
                        </Grid>
                        <Grid item xs={6} sx={{ textAlign: 'right' }}>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, display: 'block', mb: 0.5 }}>NET GAINS</Typography>
                          <Typography variant="body1" className="num" sx={{ fontWeight: 800, color: gainColor(h.Gain) }}>
                            {h.Gain >= 0 ? '+' : ''}{fmtInr(h.Gain)}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>

                    <Box sx={{ mt: 3 }}>
                      <Divider sx={{ mb: 2.5, borderColor: 'rgba(255,255,255,0.03)' }} />
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flex: 1 }}>
                          <Box sx={{ flex: 1, maxWidth: 100, height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3 }}>
                            <Box sx={{ 
                              height: '100%', 
                              background: 'primary.main', 
                              borderRadius: 3, 
                              width: `${Math.min(100, weight * 4)}%`,
                              boxShadow: '0 0 10px rgba(99, 102, 241, 0.4)' 
                            }} />
                          </Box>
                          <Typography variant="caption" className="num" sx={{ fontWeight: 800, color: 'text.secondary', fontSize: 11 }}>{weight.toFixed(1)}% WT</Typography>
                        </Box>
                        <Box sx={{ px: 1.25, py: 0.5, borderRadius: '8px', bgcolor: signal.bg }}>
                          <Typography variant="caption" className="num" sx={{ fontWeight: 800, color: signal.color, fontSize: 11 }}>
                            {gainPct >= 0 ? '▲' : '▼'} {Math.abs(gainPct).toFixed(2)}%
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  </Paper>
                </Grid>
              )
            })}
          </Grid>
        )}
      </Box>

      <FundDetailDrawer fund={selectedFund} onClose={() => setSelectedFund(null)} />
    </Box>
  )
}
