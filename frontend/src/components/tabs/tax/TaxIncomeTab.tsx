import { Box, Typography, Paper, Grid, Stack, Skeleton, alpha, Chip, Divider, TextField, IconButton, Collapse, Tooltip } from '@mui/material'
import React, { useState, useEffect } from 'react'
import SaveIcon from '@mui/icons-material/Save'
import LanguageIcon from '@mui/icons-material/Language'
import WorkIcon from '@mui/icons-material/Work'
import StorefrontIcon from '@mui/icons-material/Storefront'
import SavingsIcon from '@mui/icons-material/Savings'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import CurrencyRupeeIcon from '@mui/icons-material/CurrencyRupee'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import MoreHorizIcon from '@mui/icons-material/MoreHoriz'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import { useTaxExpertIncome, useTaxExpertSummary, useTaxExpertOverrides } from '../../../hooks/useTaxExpert'
import { useTaxRegime } from '../../../store/appStore'
import { fmtInr } from '../../../api/fmt'
import taxRulesData from '../../../../../backend/config/tax_rules.json'

const IncomeCard = ({ id, expanded, onToggle, title, infoText, icon: Icon, color, amount, autoFilled, children }: any) => {
  return (
    <Paper className="glass" sx={{ p: 3.5, borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', height: '100%', transition: 'all 0.3s ease' }}>
      <Box 
        sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', userSelect: 'none' }}
        onClick={onToggle}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha(color, 0.1), color, display: 'flex' }}>
            <Icon sx={{ fontSize: 22 }} />
          </Box>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 900, color: '#fff' }}>{title}</Typography>
              {infoText && (
                <Tooltip 
                  title={
                    infoText ? infoText.split('\n').map((line: string, i: number) => (
                      <div key={i} style={{ marginBottom: i < infoText.split('\n').length - 1 ? '4px' : 0 }}>{line}</div>
                    )) : ''
                  } 
                  arrow 
                  placement="top"
                >
                  <InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                </Tooltip>
              )}
            </Box>
            <Typography variant="h5" className="num" sx={{ fontWeight: 900, color }}>{fmtInr(amount)}</Typography>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {autoFilled && (
            <Chip
              icon={<CheckCircleIcon sx={{ fontSize: 14 }} />}
              label="AIS Auto-filled"
              size="small"
              sx={{ fontWeight: 800, fontSize: '0.6rem', bgcolor: alpha('#4EDE93', 0.1), color: '#4EDE93', '& .MuiChip-icon': { color: '#4EDE93' } }}
            />
          )}
          <IconButton size="small" sx={{ color: 'text.secondary', bgcolor: 'rgba(255,255,255,0.05)', pointerEvents: 'none' }}>
            {expanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>
      </Box>

      <Collapse in={expanded}>
        <Box sx={{ mt: 2.5, pt: 2.5, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
          {children}
        </Box>
      </Collapse>
    </Paper>
  )
}

export default function TaxIncomeTab() {
  const regime = useTaxRegime()
  const { data, isLoading } = useTaxExpertIncome()
  
  const [expandedCat, setExpandedCat] = useState<string | null>('core')
  const [expandedCard, setExpandedCard] = useState<string | null>('salary_income')

  const toggleCat = (cat: string) => {
    if (expandedCat === cat) {
      setExpandedCat(null)
    } else {
      setExpandedCat(cat)
      setExpandedCard(null)
    }
  }

  const { data: summaryData } = useTaxExpertSummary(regime)
  const mutation = useTaxExpertOverrides()
  const [foreignInterest, setForeignInterest] = useState(0)
  const [businessIncome, setBusinessIncome] = useState({ revenue_44ada: 0, revenue_44ad: 0 })
  const [cryptoIncome, setCryptoIncome] = useState(0)
  const [gamingIncome, setGamingIncome] = useState(0)
  
  useEffect(() => {
    if (summaryData?.overrides?.foreign_interest) {
      setForeignInterest(summaryData.overrides.foreign_interest)
    }
    if (summaryData?.overrides?.business_income) {
      setBusinessIncome({
        revenue_44ada: summaryData.overrides.business_income.revenue_44ada || 0,
        revenue_44ad: summaryData.overrides.business_income.revenue_44ad || 0
      })
    }
    if (summaryData?.overrides?.crypto_income) {
      setCryptoIncome(summaryData.overrides.crypto_income)
    }
    if (summaryData?.overrides?.gaming_income) {
      setGamingIncome(summaryData.overrides.gaming_income)
    }
  }, [summaryData?.overrides])
  


  const isSenior = (data?.personal?.dob) ? (new Date().getFullYear() - parseInt(data.personal.dob.split('/')[2])) >= 60 : false;
  const savingsExempt = regime === 'new' ? 0 : isSenior ? Math.min((data?.total_savings_interest || 0) + (data?.total_fd_interest || 0), 50000) : Math.min(data?.total_savings_interest || 0, taxRulesData.deductions.limit_80tta);
  const netSavings = Math.max(0, (data?.total_savings_interest || 0) - savingsExempt);

  const handleSaveForeignInterest = () => {
    mutation.mutate({ foreign_interest: foreignInterest })
  }
  const handleSaveBusiness = () => {
    mutation.mutate({ business_income: businessIncome })
  }
  const handleSaveCrypto = () => {
    mutation.mutate({ crypto_income: cryptoIncome })
  }
  const handleSaveGaming = () => {
    mutation.mutate({ gaming_income: gamingIncome })
  }

  if (isLoading || !data) {
    return (
      <Box sx={{ pb: 8 }}>
        <Grid container spacing={3}>
          {[1, 2, 3, 4].map(n => (
            <Grid item xs={12} md={6} key={n}>
              <Skeleton variant="rounded" height={220} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} />
            </Grid>
          ))}
        </Grid>
      </Box>
    )
  }

  return (
    <Box sx={{ pb: 8 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff', mb: 0.5 }}>Income Sources</Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
          All income data auto-populated from your AIS. Review and verify each source below.
        </Typography>
      </Box>

      <Grid container spacing={3}>
        
        {/* Core Income */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('core')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'core' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#6366F1', 0.1), display: 'flex' }}>
                <WorkIcon sx={{ color: '#6366F1', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Core Income</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Salary, Business, Professional & Misc Income</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {((data.salary?.gross || 0) + (businessIncome?.revenue_44ad || 0) + (businessIncome?.revenue_44ada || 0) + (data.total_misc_income || 0)) >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#6366F1' }}>{fmtInr((data.salary?.gross || 0) + (businessIncome?.revenue_44ad || 0) + (businessIncome?.revenue_44ada || 0) + (data.total_misc_income || 0))}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'core' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'core'}>
            <Grid container spacing={3}>

        <Grid item xs={12}>
          <IncomeCard id="salary_income" expanded={expandedCard === "salary_income"} onToggle={() => setExpandedCard(prev => prev === "salary_income" ? null : "salary_income")} title="Salary Income" infoText={taxRulesData.ui_tooltips.section_16_ia.text}  icon={WorkIcon} color="#6366F1" amount={data.salary.gross} autoFilled>
            <Stack spacing={1.5} sx={{ mt: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>Employer</Typography>
                <Typography variant="caption" sx={{ color: '#fff', fontWeight: 800, maxWidth: '60%', textAlign: 'right' }}>
                  {data.salary.employer?.replace('Section 192) ', '').split('(')[0]?.trim() || 'N/A'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>TDS Deducted by Employer</Typography>
                <Typography variant="caption" className="num" sx={{ color: '#4EDE93', fontWeight: 800 }}>{fmtInr(data.salary.tds_deducted)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '12px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 700 }}>Salary Payments</Typography>
                <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>
                  {data.salary.quarterly?.filter((q: any) => q.amount_paid > 100)?.length || 0} months
                </Typography>
              </Box>
            </Stack>


          </IncomeCard>
        </Grid>
        
        <Grid item xs={12}>
          <IncomeCard id="professional_income_44ada" expanded={expandedCard === "professional_income_44ada"} onToggle={() => setExpandedCard(prev => prev === "professional_income_44ada" ? null : "professional_income_44ada")} title="Professional Income (44ADA)" infoText={taxRulesData.ui_tooltips.section_44ada.text} icon={WorkIcon} color="#3B82F6" amount={businessIncome.revenue_44ada || 0} autoFilled={false}>
            <Box sx={{ mt: 2, p: 2, borderRadius: '14px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, mb: 0.5 }}>Presumptive Income</Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField 
                  fullWidth variant="outlined" size="small" placeholder="Gross Receipts (₹)" 
                  value={businessIncome.revenue_44ada || ''}
                  onChange={e => setBusinessIncome(p => ({...p, revenue_44ada: Number(e.target.value)}))}
                  onBlur={handleSaveBusiness}
                  sx={{ input: { color: '#fff', fontWeight: 800, p: 1.5, fontFamily: 'monospace' }, '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' } }} 
                />
              </Box>
            </Box>
          </IncomeCard>
        </Grid>

        <Grid item xs={12}>
          <IncomeCard id="business_income_44ad" expanded={expandedCard === "business_income_44ad"} onToggle={() => setExpandedCard(prev => prev === "business_income_44ad" ? null : "business_income_44ad")} title="Business Income (44AD)" infoText={taxRulesData.ui_tooltips.section_44ad.text} icon={StorefrontIcon} color="#06B6D4" amount={businessIncome.revenue_44ad || 0} autoFilled={false}>
            <Box sx={{ mt: 2, p: 2, borderRadius: '14px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, mb: 0.5 }}>Presumptive Income</Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField 
                  fullWidth variant="outlined" size="small" placeholder="Gross Turnover (₹)" 
                  value={businessIncome.revenue_44ad || ''}
                  onChange={e => setBusinessIncome(p => ({...p, revenue_44ad: Number(e.target.value)}))}
                  onBlur={handleSaveBusiness}
                  sx={{ input: { color: '#fff', fontWeight: 800, p: 1.5, fontFamily: 'monospace' }, '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' } }} 
                />
              </Box>
            </Box>
          </IncomeCard>
        </Grid>
        
        <Grid item xs={12}>
          <IncomeCard id="misc_income_freelance_rent_etc" expanded={expandedCard === "misc_income_freelance_rent_etc"} onToggle={() => setExpandedCard(prev => prev === "misc_income_freelance_rent_etc" ? null : "misc_income_freelance_rent_etc")} title="Misc. Income (Freelance, Rent, etc.)" infoText={taxRulesData.ui_tooltips.misc_income.text} icon={MoreHorizIcon} color="#EC4899" amount={data.total_misc_income || 0} autoFilled>
            <Stack spacing={1} sx={{ mt: 2, maxHeight: 180, overflowY: 'auto' }}>
              {data.misc_income?.map((m: any, idx: number) => (
                <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                  <Box>
                    <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700, display: 'block' }}>{m.source?.replace(/ LIMITED| LTD| PVT| PRIVATE/gi, '')}</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: '0.6rem' }}>{m.type} ({m.code})</Typography>
                  </Box>
                  <Typography variant="caption" className="num" sx={{ color: '#EC4899', fontWeight: 800 }}>{fmtInr(m.amount)}</Typography>
                </Box>
              ))}
              {(!data.misc_income || data.misc_income.length === 0) && (
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textAlign: 'center', py: 3 }}>
                  No freelance, rent, or commission reported
                </Typography>
              )}
            </Stack>
          </IncomeCard>
        </Grid>
        
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

        {/* Interest & Dividends */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('interest')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'interest' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#A855F7', 0.1), display: 'flex' }}>
                <AccountBalanceIcon sx={{ color: '#A855F7', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Interest & Dividends</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Savings, FD, Bonds, Foreign & Domestic Dividends</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {((data.total_savings_interest || 0) + (data.total_fd_interest || 0) + (data.total_other_interest || 0) + (data.total_dividends || 0) + (foreignInterest || 0)) >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#A855F7' }}>{fmtInr((data.total_savings_interest || 0) + (data.total_fd_interest || 0) + (data.total_other_interest || 0) + (data.total_dividends || 0) + (foreignInterest || 0))}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'interest' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'interest'}>
            <Grid container spacing={3}>
            
        <Grid item xs={12}>
          <IncomeCard id="savings_bank_interest" expanded={expandedCard === "savings_bank_interest"} onToggle={() => setExpandedCard(prev => prev === "savings_bank_interest" ? null : "savings_bank_interest")} title="Savings Bank Interest" infoText={taxRulesData.ui_tooltips.section_80tta.text}  icon={SavingsIcon} color="#38BDF8" amount={data.total_savings_interest} autoFilled>
            <Stack spacing={1}>
              {data.interest_savings.map((i: any, idx: number) => (
                <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                  <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700 }}>{i.bank?.replace(/ LIMITED| LTD/gi, '')}</Typography>
                  <Typography variant="caption" className="num" sx={{ color: '#38BDF8', fontWeight: 800 }}>{fmtInr(i.amount)}</Typography>
                </Box>
              ))}
              {data.interest_savings.length === 0 && (
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textAlign: 'center', py: 3 }}>No savings interest reported in AIS</Typography>
              )}
            </Stack>
            <Box sx={{ mt: 2, p: 2, borderRadius: '12px', bgcolor: 'rgba(0,0,0,0.2)', border: '1px dashed rgba(255,255,255,0.1)' }}>
              <Typography variant="overline" sx={{ color: 'text.secondary', fontWeight: 800, display: 'block', mb: 1, lineHeight: 1 }}>Tax Computation ({regime === 'new' ? 'New' : 'Old'} Regime)</Typography>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Gross Interest</Typography>
                <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700 }} className="num">{fmtInr(data.total_savings_interest)}</Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>{isSenior ? "Exempt u/s 80TTB" : "Exempt u/s 80TTA"}</Typography>
                <Typography variant="caption" sx={{ color: '#F43F5E', fontWeight: 700 }} className="num">-{fmtInr(savingsExempt)}</Typography>
              </Box>
              <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: '#fff', fontWeight: 800 }}>Net Taxable Interest</Typography>
                <Typography variant="caption" sx={{ color: regime === 'new' ? '#F59E0B' : '#4EDE93', fontWeight: 900 }} className="num">{fmtInr(netSavings)}</Typography>
              </Box>
            </Box>

          </IncomeCard>
        </Grid>

        <Grid item xs={12}>
          <IncomeCard id="term_deposit_interest" expanded={expandedCard === "term_deposit_interest"} onToggle={() => setExpandedCard(prev => prev === "term_deposit_interest" ? null : "term_deposit_interest")} title="Term Deposit Interest" infoText={taxRulesData.ui_tooltips.section_80ttb.text}  icon={AccountBalanceIcon} color="#A855F7" amount={data.total_fd_interest} autoFilled>
            <Stack spacing={1}>
              {data.interest_deposits?.map((i: any, idx: number) => (
                <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                  <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700 }}>{i.bank?.replace(/ LIMITED| LTD/gi, '')}</Typography>
                  <Typography variant="caption" className="num" sx={{ color: '#A855F7', fontWeight: 800 }}>{fmtInr(i.amount)}</Typography>
                </Box>
              ))}
              {data.interest_deposits.length === 0 && (
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textAlign: 'center', py: 3 }}>No deposit interest reported in AIS</Typography>
              )}
            </Stack>
            <Box sx={{ mt: 2, p: 2, bgcolor: 'rgba(0,0,0,0.2)', borderRadius: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Interest</Typography>
                <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700 }} className="num">{fmtInr(data.total_fd_interest)}</Typography>
              </Box>
              {isSenior && regime === 'old' && (
                <>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Exempt u/s 80TTB (Shared with Savings)</Typography>
                    <Typography variant="caption" sx={{ color: '#F43F5E', fontWeight: 700 }} className="num">Included</Typography>
                  </Box>
                </>
              )}
              <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700 }}>Taxable Amount</Typography>
                <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700 }} className="num">{isSenior && regime === 'old' ? "See Net" : fmtInr(data.total_fd_interest)}</Typography>
              </Box>
            </Box>
          </IncomeCard>
        </Grid>

        <Grid item xs={12}>
          <IncomeCard id="other_interest_income" expanded={expandedCard === "other_interest_income"} onToggle={() => setExpandedCard(prev => prev === "other_interest_income" ? null : "other_interest_income")} title="Other Interest Income" infoText={taxRulesData.ui_tooltips.other_interest.text} icon={MoreHorizIcon} color="#F43F5E" amount={data.total_other_interest || 0} autoFilled>
            <Stack spacing={1}>
              {data.interest_others?.map((i: any, idx: number) => (
                <Box key={idx} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                  <Box>
                    <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700, display: 'block' }}>{i.source?.replace(/ LIMITED| LTD/gi, '')}</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, fontSize: '0.6rem' }}>{i.type}</Typography>
                  </Box>
                  <Typography variant="caption" className="num" sx={{ color: '#F43F5E', fontWeight: 800 }}>{fmtInr(i.amount)}</Typography>
                </Box>
              ))}
              {(!data.interest_others || data.interest_others.length === 0) && (
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textAlign: 'center', py: 3 }}>
                  No P2P, Bond, or other interest reported in AIS
                </Typography>
              )}
            </Stack>
          </IncomeCard>
        </Grid>

        <Grid item xs={12}>
          <IncomeCard id="dividend_income" expanded={expandedCard === "dividend_income"} onToggle={() => setExpandedCard(prev => prev === "dividend_income" ? null : "dividend_income")} title="Dividend Income" infoText={taxRulesData.ui_tooltips.dividend.text} icon={CurrencyRupeeIcon} color="#EAB308" amount={data.total_dividends} autoFilled>
            <Stack spacing={1} sx={{ mt: 2, maxHeight: 180, overflowY: 'auto', pr: 0.5, '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 2 } }}>
              {data.dividends.map((d: any, i: number) => (
                <Box key={i} sx={{ display: 'flex', justifyContent: 'space-between', p: 1.5, borderRadius: '10px', bgcolor: 'rgba(255,255,255,0.02)' }}>
                  <Typography variant="caption" sx={{ color: '#fff', fontWeight: 700, maxWidth: '70%' }}>
                    {d.source?.replace(/ LIMITED| LTD/gi, '')}
                  </Typography>
                  <Typography variant="caption" className="num" sx={{ color: '#EAB308', fontWeight: 800 }}>{fmtInr(d.amount)}</Typography>
                </Box>
              ))}
              {data.dividends.length === 0 && (
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, textAlign: 'center', py: 3 }}>No dividend income reported in AIS</Typography>
              )}
            </Stack>
          </IncomeCard>
        </Grid>

        <Grid item xs={12}>
          <IncomeCard id="foreign_interest__dividends" expanded={expandedCard === "foreign_interest__dividends"} onToggle={() => setExpandedCard(prev => prev === "foreign_interest__dividends" ? null : "foreign_interest__dividends")} title="Foreign Interest / Dividends" infoText={taxRulesData.ui_tooltips.foreign_interest.text} icon={LanguageIcon} color="#10B981" amount={foreignInterest} autoFilled={false}>
            <Box sx={{ mt: 2, p: 2, borderRadius: '14px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, mb: 1.5 }}>RSUs / ESOPs / ESPPs (Fidelity, Schwab, E*Trade)</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField 
                  fullWidth variant="outlined" size="small" placeholder="Enter amount (₹)" 
                  value={foreignInterest || ''}
                  onChange={e => setForeignInterest(Number(e.target.value))}
                  onBlur={handleSaveForeignInterest}
                  sx={{ input: { color: '#fff', fontWeight: 800, p: 1.5, fontFamily: 'monospace' }, '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' } }} 
                />
              </Box>
            </Box>
          </IncomeCard>
        </Grid>
        
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

        {/* Special Rates */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('special')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'special' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#F59E0B', 0.1), display: 'flex' }}>
                <CurrencyRupeeIcon sx={{ color: '#F59E0B', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Special Rates</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Crypto (VDA) and Online Gaming/Lottery</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {((cryptoIncome || 0) + (gamingIncome || 0)) >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#F59E0B' }}>{fmtInr((cryptoIncome || 0) + (gamingIncome || 0))}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'special' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'special'}>
            <Grid container spacing={3}>
            
        <Grid item xs={12}>
          <IncomeCard id="crypto_income_vda" expanded={expandedCard === "crypto_income_vda"} onToggle={() => setExpandedCard(prev => prev === "crypto_income_vda" ? null : "crypto_income_vda")} title="Crypto Income (VDA)" infoText={taxRulesData.ui_tooltips.crypto_vda.text} icon={CurrencyRupeeIcon} color="#F59E0B" amount={cryptoIncome} autoFilled={false}>
            <Box sx={{ mt: 2, p: 2, borderRadius: '14px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, mb: 0.5 }}>Import from Crypto Exchanges</Typography>

              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField 
                  fullWidth variant="outlined" size="small" placeholder="Total Crypto Gains (₹)" 
                  value={cryptoIncome || ''}
                  onChange={e => setCryptoIncome(Number(e.target.value))}
                  onBlur={handleSaveCrypto}
                  sx={{ input: { color: '#fff', fontWeight: 800, p: 1.5, fontFamily: 'monospace' }, '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' } }} 
                />
              </Box>
            </Box>
          </IncomeCard>
        </Grid>

        <Grid item xs={12}>
          <IncomeCard id="gaming__lottery_115bb" expanded={expandedCard === "gaming__lottery_115bb"} onToggle={() => setExpandedCard(prev => prev === "gaming__lottery_115bb" ? null : "gaming__lottery_115bb")} title="Gaming & Lottery (115BB)" infoText={taxRulesData.ui_tooltips.gaming_lottery.text} icon={CurrencyRupeeIcon} color="#EAB308" amount={gamingIncome} autoFilled={false}>
            <Box sx={{ mt: 2, p: 2, borderRadius: '14px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
              <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700, mb: 1.5 }}>Dream11, MPL, Lottery Winnings</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <TextField 
                  fullWidth variant="outlined" size="small" placeholder="Net Winnings (₹)" 
                  value={gamingIncome || ''}
                  onChange={e => setGamingIncome(Number(e.target.value))}
                  onBlur={handleSaveGaming}
                  sx={{ input: { color: '#fff', fontWeight: 800, p: 1.5, fontFamily: 'monospace' }, '& fieldset': { borderColor: 'rgba(255,255,255,0.1)' } }} 
                />
              </Box>
            </Box>
          </IncomeCard>
        </Grid>
        
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

      </Grid>
    </Box>
  )
}
