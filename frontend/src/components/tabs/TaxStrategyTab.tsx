
import { useState, useEffect, useMemo } from 'react'
import {
  Box, Grid, Paper, Typography, Tooltip as MuiTooltip,
  Chip, Select, MenuItem, Skeleton,
  IconButton, Dialog, DialogTitle,
  DialogContent, DialogActions, Button, Stack,
  List, ListItem, ListItemText, ListItemAvatar, Avatar, alpha
} from '@mui/material'
import ArrowForwardIosIcon from '@mui/icons-material/ArrowForwardIos'
import KeyboardArrowDownIcon from '@mui/icons-material/KeyboardArrowDown'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import ShieldIcon from '@mui/icons-material/Shield'

import { useTax, useTaxYears } from '../../hooks/useData'
import { TabLoader, SectionHeader } from '../ui'
import { fmtInr } from '../../api/fmt'

// ── Sub-components & Metric Containers ────────────────────────────────────

/**
 * Metric display container for top-level financial summaries (Gains, Tax, Assets audited).
 */
const TaxMetric = ({ label, value, color, icon: Icon }: any) => (
  <Paper className="glass" sx={{ p: 3, borderRadius: '24px', flex: 1, border: '1px solid rgba(255,255,255,0.05)' }}>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
      <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha(color, 0.1), color }}>
        <Icon sx={{ fontSize: 24 }} />
      </Box>
      <Box>
        <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 800, letterSpacing: '0.1em' }}>{label}</Typography>
        <Typography variant="h5" className="num" sx={{ fontWeight: 900, color: '#fff' }}>{value}</Typography>
      </Box>
    </Box>
  </Paper>
)

const SummaryBox = ({ title, gain, tax, onGainClick, onTaxClick, type }: any) => {
  const tooltipText = type === 'LTCG'
    ? 'Long-Term Capital Gains (held > 1 year for equity or > 3 years for debt). Exempt up to ₹1.25 Lakhs per FY for equities.'
    : 'Short-Term Capital Gains (held <= 1 year for equity or <= 3 years for debt). Taxed at 20% for equities or slab rate for debt.'
  return (
    <Paper className="glass" sx={{ p: 4, borderRadius: '32px', height: '100%', border: '1px solid rgba(255,255,255,0.05)' }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: '0.15em' }}>{title}</Typography>
        <MuiTooltip title={tooltipText}>
          <span>
            <IconButton size="small" sx={{ p: 0 }}><InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary' }} /></IconButton>
          </span>
        </MuiTooltip>
      </Box>
      
      <Stack spacing={3}>
        <Box 
          onClick={onGainClick}
          sx={{ 
            p: 3, borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.02)', cursor: 'pointer',
            transition: 'all 0.2s', '&:hover': { bgcolor: 'rgba(255,255,255,0.05)', transform: 'translateX(4px)' }
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>NET {type} GAINS</Typography>
              <Typography variant="h5" className="num" sx={{ fontWeight: 800, color: '#fff', mt: 0.5 }}>{fmtInr(gain)}</Typography>
            </Box>
            <ArrowForwardIosIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
          </Box>
        </Box>

        <Box 
          onClick={onTaxClick}
          sx={{ 
            p: 3, borderRadius: '20px', bgcolor: alpha('#FF516A', 0.03), cursor: 'pointer',
            border: '1px solid rgba(255, 81, 106, 0.1)',
            transition: 'all 0.2s', '&:hover': { bgcolor: alpha('#FF516A', 0.06), transform: 'translateX(4px)' }
          }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Box>
              <Typography variant="caption" sx={{ color: '#FF516A', fontWeight: 800 }}>ESTIMATED LIABILITY</Typography>
              <Typography variant="h5" className="num" sx={{ fontWeight: 800, color: '#FF516A', mt: 0.5 }}>{fmtInr(tax)}</Typography>
            </Box>
            <ArrowForwardIosIcon sx={{ fontSize: 14, color: '#FF516A' }} />
          </Box>
        </Box>
      </Stack>
    </Paper>
  )
}

const SummaryModal = ({ open, onClose, title, subtitle, data, contributions = [], type }: any) => (
  <Dialog 
    open={open} 
    onClose={onClose} 
    fullWidth 
    maxWidth="xs" 
    PaperProps={{ className: "glass", sx: { borderRadius: '32px', bgcolor: '#0B1326', border: '1px solid rgba(255,255,255,0.1)', p: 2 } }}
  >
    <DialogTitle sx={{ fontWeight: 900, fontSize: 24, color: '#fff', pb: 1 }}>
      {title}
      <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600, mt: 1 }}>{subtitle}</Typography>
    </DialogTitle>
    <DialogContent sx={{ pb: 3 }}>
      <Stack spacing={2} sx={{ mt: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', p: 2, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '16px' }}>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>EQUITY {type}</Typography>
          <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(data?.equity)}</Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', p: 2, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '16px' }}>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>NON-EQUITY {type}</Typography>
          <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(data?.debt)}</Typography>
        </Box>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', p: 2, bgcolor: alpha('#FF516A', 0.05), borderRadius: '16px', border: `1px solid ${alpha('#FF516A', 0.1)}` }}>
          <Typography variant="body2" sx={{ color: '#FF516A', fontWeight: 700 }}>REALIZED LOSSES</Typography>
          <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#FF516A' }}>-{fmtInr(data?.loss)}</Typography>
        </Box>
      </Stack>

      <Box sx={{ mt: 4, p: 3, borderRadius: '24px', background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(78, 222, 147, 0.1) 100%)', border: '1px solid rgba(255,255,255,0.05)' }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 900, color: '#fff' }}>NET {type} GAINS</Typography>
          <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#4EDE93' }}>{fmtInr(data?.net)}</Typography>
        </Box>
      </Box>

      <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 800, display: 'block', mt: 4, mb: 2, letterSpacing: '0.1em' }}>CONTRIBUTORS</Typography>
      <List sx={{ bgcolor: 'rgba(255,255,255,0.02)', borderRadius: '20px', overflow: 'hidden' }}>
        {contributions.map((c: any, i: number) => (
          <ListItem key={i} divider={i !== contributions.length - 1} sx={{ py: 2, borderColor: 'rgba(255,255,255,0.05)' }}>
            <ListItemText 
              primary={<Typography variant="body2" sx={{ fontWeight: 800, color: '#fff' }}>{c?.fund || 'Instrument'}</Typography>}
              secondary={<Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>{String(c?.category || 'Equity').toUpperCase()}</Typography>}
            />
            <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: (c?.gain ?? 0) >= 0 ? '#4EDE93' : '#FF516A' }}>
              {(c?.gain ?? 0) >= 0 ? '+' : ''}{fmtInr(c?.gain ?? 0)}
            </Typography>
          </ListItem>
        ))}
      </List>
    </DialogContent>
    <DialogActions sx={{ p: 4 }}>
      <Button fullWidth variant="contained" onClick={onClose} sx={{ borderRadius: '16px', py: 2, fontWeight: 800 }}>CLOSE AUDIT</Button>
    </DialogActions>
  </Dialog>
)

const TaxLiabilityModal = ({ open, onClose, title, data, type }: any) => (
  <Dialog 
    open={open} 
    onClose={onClose} 
    fullWidth 
    maxWidth="xs" 
    PaperProps={{ className: "glass", sx: { borderRadius: '32px', bgcolor: '#0B1326', border: '1px solid rgba(255,255,255,0.1)', p: 2 } }}
  >
    <DialogTitle sx={{ fontWeight: 900, fontSize: 24, color: '#fff', pb: 2 }}>{title}</DialogTitle>
    <DialogContent sx={{ pb: 3 }}>
      <Stack spacing={2}>
        <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800 }}>EQUITY {type}</Typography>
            <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(data?.equity)}</Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="caption" sx={{ color: 'primary.main', fontWeight: 800 }}>{type === 'LTCG' ? 'EXEMPTION APPLIED' : 'TAX @ 20%'}</Typography>
            <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: 'primary.main' }}>{type === 'LTCG' ? 'MAX' : fmtInr(data?.equity_tax)}</Typography>
          </Box>
        </Box>

        <Box sx={{ p: 2.5, borderRadius: '20px', bgcolor: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.05)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800 }}>NON-EQUITY {type}</Typography>
            <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(data?.debt)}</Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="caption" sx={{ color: 'primary.main', fontWeight: 800 }}>{type === 'LTCG' ? 'TAX @ 12.5%' : 'SLAB TAX (20%)'}</Typography>
            <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: 'primary.main' }}>{fmtInr(data?.debt_tax)}</Typography>
          </Box>
        </Box>

        <Box sx={{ mt: 2, p: 3, borderRadius: '24px', background: 'rgba(255, 81, 106, 0.1)', border: '1px solid rgba(255, 81, 106, 0.2)' }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 900, color: '#fff' }}>TOTAL LIABILITY</Typography>
            <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#FF516A' }}>{fmtInr(data?.total_tax)}</Typography>
          </Box>
        </Box>
      </Stack>
    </DialogContent>
    <DialogActions sx={{ p: 4 }}>
      <Button fullWidth variant="contained" onClick={onClose} sx={{ borderRadius: '16px', py: 2, fontWeight: 800 }}>CLOSE</Button>
    </DialogActions>
  </Dialog>
)

/**
 * TaxStrategyTab: Institutional Strategy Lab
 * 
 * Conducts a deep-ledger FIFO audit to calculate realized and unrealized 
 * capital gains (LTCG/STCG) across multiple financial years.
 * Includes liability tracking and simulated tax harvesting opportunities.
 */
export default function TaxStrategyTab() {
  const { data: yearsData, isLoading: yearsL } = useTaxYears()
  const years = yearsData?.years || []
  
  const [fy, setFy] = useState('')
  
  // Fiscal Year Initialization
  useEffect(() => {
    if (years.length > 0 && !fy) {
      setFy(years[0])
    }
  }, [years, fy])

  const activeFy = fy || (years.length > 0 ? years[0] : 'Current Portfolio')

  // Data Acquisition: Tax Audit Ledger
  const { data: tax, isLoading: taxL } = useTax(activeFy)
  
  // Modal State Management
  const [showLtcg, setShowLtcg] = useState(false)
  const [showStcg, setShowStcg] = useState(false)
  const [showLtcgTax, setShowLtcgTax] = useState(false)
  const [showStcgTax, setShowStcgTax] = useState(false)

  const isCurrent = activeFy === 'Current Portfolio'

  const filteredFunds = useMemo(() => {
    if (!tax?.fund_breakdown) return []
    return tax.fund_breakdown.filter((f: any) => isCurrent || (f?.withdrawal ?? 0) > 0)
  }, [tax?.fund_breakdown, isCurrent])

  if (yearsL) return <TabLoader message="Analyzing institutional tax audit..." />

  return (
    <Box sx={{ pb: 8 }}>
      <SectionHeader 
        title="Tax Strategy Lab" 
        subtitle="Institutional-grade FIFO audit and real-time liability tracking"
        action={
          <Paper className="glass" sx={{ px: 3, py: 1.5, borderRadius: '40px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, letterSpacing: '0.1em' }}>AUDIT PERIOD</Typography>
              <Select 
                value={activeFy} 
                variant="standard"
                disableUnderline
                onChange={(e) => setFy(e.target.value)}
                sx={{ fontWeight: 900, fontSize: 15, color: 'primary.main', textTransform: 'uppercase' }}
                IconComponent={KeyboardArrowDownIcon}
              >
                {years.map(y => <MenuItem key={y} value={y}>{y}</MenuItem>)}
              </Select>
            </Box>
          </Paper>
        }
      />

      {/* ── Global Health Metrics ─────────────────────────────────────────── */}
      <Grid container spacing={3} sx={{ mb: 6 }}>
        <Grid item xs={12} md={4}>
          {taxL ? <Skeleton variant="rounded" height={90} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} /> : <TaxMetric label="TOTAL NET GAINS" value={fmtInr((tax?.ltcg_gain ?? 0) + (tax?.stcg_gain ?? 0))} color="#4EDE93" icon={TrendingUpIcon} />}
        </Grid>
        <Grid item xs={12} md={4}>
          {taxL ? <Skeleton variant="rounded" height={90} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} /> : <TaxMetric label="ESTIMATED LIABILITY" value={fmtInr(tax?.total_tax ?? 0)} color="#FF516A" icon={ShieldIcon} />}
        </Grid>
        <Grid item xs={12} md={4}>
          {taxL ? <Skeleton variant="rounded" height={90} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} /> : <TaxMetric label="AUDITED ASSETS" value={fmtInr(isCurrent ? (tax?.equity_gain ?? 0) + (tax?.debt_gain ?? 0) : (tax?.total_withdrawals ?? 0))} color="#6366F1" icon={ReceiptLongIcon} />}
        </Grid>
      </Grid>

      {/* ── Main Analytical Grid ─────────────────────────────────────────── */}
      <Grid container spacing={4}>
        <Grid item xs={12} lg={7}>
          <Stack spacing={4}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                {taxL ? <Skeleton variant="rounded" height={260} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} /> : (
                  <SummaryBox 
                    title="LONG-TERM CAPITAL GAINS" 
                    gain={tax?.ltcg_gain ?? 0} 
                    tax={(tax?.ltcg_equity_tax ?? 0) + (tax?.ltcg_debt_tax ?? 0)}
                    type="LTCG"
                    onGainClick={() => setShowLtcg(true)}
                    onTaxClick={() => setShowLtcgTax(true)}
                  />
                )}
              </Grid>
              <Grid item xs={12} md={6}>
                {taxL ? <Skeleton variant="rounded" height={260} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '32px' }} /> : (
                  <SummaryBox 
                    title="SHORT-TERM CAPITAL GAINS" 
                    gain={tax?.stcg_gain ?? 0} 
                    tax={(tax?.stcg_equity_tax ?? 0) + (tax?.stcg_debt_tax ?? 0)}
                    type="STCG"
                    onGainClick={() => setShowStcg(true)}
                    onTaxClick={() => setShowStcgTax(true)}
                  />
                )}
              </Grid>
            </Grid>

            {/* Tax Optimizer Promo (Web-friendly) */}
            <Paper className="glass" sx={{ 
              p: 4, borderRadius: '32px', 
              background: 'linear-gradient(90deg, rgba(99, 102, 241, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%)',
              border: '1px solid rgba(99, 102, 241, 0.2)',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center'
            }}>
              <Box sx={{ maxWidth: '70%' }}>
                <Typography variant="h6" sx={{ fontWeight: 900, color: '#fff', mb: 1 }}>
                  Optimize Your Tax Liability 🎯
                </Typography>
                <Typography variant="body2" sx={{ color: 'on-surface-variant', fontWeight: 500 }}>
                  Our algorithm identifies tax-harvesting opportunities across your portfolio to save up to ₹1,25,000 in LTCG annually.
                </Typography>
              </Box>
              <Button variant="contained" sx={{ borderRadius: '12px', px: 4, py: 1.5, fontWeight: 800 }}>
                RUN OPTIMIZER
              </Button>
            </Paper>
          </Stack>
        </Grid>

        <Grid item xs={12} lg={5}>
          <Paper className="glass" sx={{ 
            p: 4, borderRadius: '32px', height: '100%', 
            maxHeight: '700px', display: 'flex', flexDirection: 'column',
            border: '1px solid rgba(255,255,255,0.05)'
          }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 4 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="overline" sx={{ color: 'primary.main', fontWeight: 800, letterSpacing: '0.15em' }}>
                  AUDIT LEDGER
                </Typography>
                <MuiTooltip title="Realized and unrealized capital gain distribution across individual portfolio holdings audited using First-In-First-Out (FIFO) methodology.">
                  <span style={{ display: 'inline-flex' }}>
                    <IconButton size="small" sx={{ p: 0 }}><InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary' }} /></IconButton>
                  </span>
                </MuiTooltip>
              </Box>
              <Chip label={isCurrent ? "PORTFOLIO" : "SETTLED"} size="small" sx={{ fontWeight: 900, fontSize: 10, bgcolor: 'rgba(255,255,255,0.05)' }} />
            </Box>

            <Box sx={{ flex: 1, overflow: 'auto', pr: 1, '&::-webkit-scrollbar': { width: 4 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 2 } }}>
              {taxL ? (
                <Stack spacing={2} sx={{ py: 2 }}>
                  {[1, 2, 3, 4].map(n => <Skeleton key={n} variant="rounded" height={60} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 3 }} />)}
                </Stack>
              ) : (
                <List sx={{ p: 0 }}>
                  {filteredFunds.map((f: any, i: number) => (
                    <ListItem key={i} sx={{ px: 0, py: 2.5, borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <ListItemAvatar>
                        <Avatar sx={{ background: 'rgba(255,255,255,0.03)', color: 'primary.main', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                          <AccountBalanceWalletIcon fontSize="small" />
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText 
                        primaryTypographyProps={{ component: 'div' }}
                        secondaryTypographyProps={{ component: 'div' }}
                        primary={<Typography component="div" variant="body2" sx={{ fontWeight: 800, color: '#fff', mb: 0.5 }}>{f?.fund || 'Instrument'}</Typography>}
                        secondary={
                          <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
                            <Typography component="span" variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>{String(f?.category || 'Equity').toUpperCase()}</Typography>
                            <Box component="span" sx={{ width: 4, height: 4, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.2)' }} />
                            <Typography component="span" variant="caption" className="num" sx={{ color: 'primary.main', fontWeight: 700 }}>{fmtInr(isCurrent ? ((f?.ltcg_gain ?? 0) + (f?.stcg_gain ?? 0)) : (f?.withdrawal ?? 0))}</Typography>
                          </Box>
                        }
                      />
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: ((f?.ltcg_gain ?? 0) + (f?.stcg_gain ?? 0)) >= 0 ? '#4EDE93' : '#FF516A' }}>
                          {((f?.ltcg_gain ?? 0) + (f?.stcg_gain ?? 0)) >= 0 ? '+' : ''}{fmtInr((f?.ltcg_gain ?? 0) + (f?.stcg_gain ?? 0))}
                        </Typography>
                        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700, fontSize: 9 }}>FIFO AUDITED</Typography>
                      </Box>
                    </ListItem>
                  ))}
                </List>
              )}
            </Box>
          </Paper>
        </Grid>
      </Grid>

      {/* Breakdown Modals */}
      <SummaryModal 
        open={showLtcg} onClose={() => setShowLtcg(false)} 
        title="LTCG Audit" type="LTCG"
        subtitle={isCurrent ? 'FIFO Audit of unrealized long-term holdings' : 'Institutional audit of realized LT sales'}
        data={{ equity: tax?.equity_ltcg, debt: tax?.debt_ltcg, loss: tax?.ltcl, net: tax?.ltcg_gain }}
        contributions={(tax?.fund_breakdown || []).filter((f: any) => Math.abs(f?.ltcg_gain ?? 0) > 0).map((f: any) => ({ fund: f?.fund, gain: f?.ltcg_gain ?? 0, category: f?.category }))}
      />
      <SummaryModal 
        open={showStcg} onClose={() => setShowStcg(false)} 
        title="STCG Audit" type="STCG"
        subtitle={isCurrent ? 'FIFO Audit of unrealized short-term holdings' : 'Institutional audit of realized ST sales'}
        data={{ equity: tax?.equity_stcg, debt: tax?.debt_stcg, loss: tax?.stcl, net: tax?.stcg_gain }}
        contributions={(tax?.fund_breakdown || []).filter((f: any) => Math.abs(f?.stcg_gain ?? 0) > 0).map((f: any) => ({ fund: f?.fund, gain: f?.stcg_gain ?? 0, category: f?.category }))}
      />

      <TaxLiabilityModal 
        open={showLtcgTax} onClose={() => setShowLtcgTax(false)} title="Liability Matrix (LTCG)" type="LTCG"
        data={{ equity: tax?.equity_ltcg, debt: tax?.debt_ltcg, debt_tax: tax?.ltcg_debt_tax, total_tax: (tax?.ltcg_equity_tax ?? 0) + (tax?.ltcg_debt_tax ?? 0) }}
      />
      <TaxLiabilityModal 
        open={showStcgTax} onClose={() => setShowStcgTax(false)} title="Liability Matrix (STCG)" type="STCG"
        data={{ equity: tax?.equity_stcg, equity_tax: tax?.stcg_equity_tax, debt: tax?.debt_stcg, debt_tax: tax?.stcg_debt_tax, total_tax: (tax?.stcg_equity_tax ?? 0) + (tax?.stcg_debt_tax ?? 0) }}
      />
    </Box>
  )
}
