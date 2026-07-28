import { Box, Typography, Paper, Grid, Stack, alpha, Chip, LinearProgress, TextField, Button, IconButton, Collapse, Tooltip } from '@mui/material'
import React, { useState, useEffect } from 'react'
import ShieldIcon from '@mui/icons-material/Shield'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ReceiptLongIcon from '@mui/icons-material/ReceiptLong'
import CloseIcon from '@mui/icons-material/Close'
import AddIcon from '@mui/icons-material/Add'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import MedicalServicesIcon from '@mui/icons-material/MedicalServices'
import VolunteerActivismIcon from '@mui/icons-material/VolunteerActivism'
import RequestQuoteIcon from '@mui/icons-material/RequestQuote'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { useTaxExpertSummary, useTaxExpertOverrides, useParseForm16 } from '../../../hooks/useTaxExpert'
import { fmtInr } from '../../../api/fmt'
import { InlineEdit } from '../../ui/InlineEdit'

export default function TaxSavingsTab() {
  const { data: newData } = useTaxExpertSummary('new')
  const { data: oldData } = useTaxExpertSummary('old')
  const mutation = useTaxExpertOverrides()
  const form16Mutation = useParseForm16()

  const tdsData = newData // TDS is same for both regimes

  const [deductions, setDeductions] = useState({
    c80c: 0,
    c80ccc: 0,
    c80ccd1: 0,
    c80ccd1b: 0,
    c80ccd2: 0,
    c80d: 0,
    c80dd: 0,
    c80u: 0,
    c80e: 0,
    c80g: 0,
    c80gga: 0,
    c80ggc: 0,
    hra: 0,
    lta: 0,
    sec10_other: 0,
    ptax: 0,
    c24b: 0
  })
  
  const [manualTax, setManualTax] = useState(0)

  
  const [expandedCat, setExpandedCat] = useState<string | null>('popular')

  const toggleCat = (cat: string) => {
    setExpandedCat(prev => prev === cat ? null : cat)
  }

  const popularTotal = (deductions.c80c || 0) + (deductions.c80ccc || 0) + (deductions.c80ccd1 || 0) + (deductions.c80ccd1b || 0) + (deductions.c80ccd2 || 0)
  const medicalTotal = (deductions.c80d || 0) + (deductions.c80dd || 0) + (deductions.c80u || 0)
  const donationsTotal = (deductions.c80g || 0) + (deductions.c80gga || 0) + (deductions.c80ggc || 0)
  const loansTotal = (deductions.c24b || 0) + (deductions.c80e || 0)
  const exemptionsTotal = (deductions.hra || 0) + (deductions.lta || 0) + (deductions.sec10_other || 0) + (deductions.ptax || 0)


  useEffect(() => {
    if (oldData?.overrides?.deductions) {
      setDeductions({
        c80c: oldData.overrides.deductions['80c'] || 0,
        c80ccd1: oldData.overrides.deductions['80ccd1'] || 0,
        c80ccd1b: oldData.overrides.deductions['80ccd1b'] || 0,
        c80ccc: oldData.overrides.deductions['80ccc'] || 0,
        c80ccd2: oldData.overrides.deductions['80ccd2'] || 0,
        c80d: oldData.overrides.deductions['80d'] || 0,
        c80dd: oldData.overrides.deductions['80dd'] || 0,
        c80u: oldData.overrides.deductions['80u'] || 0,
        c80e: oldData.overrides.deductions['80e'] || 0,
        c80g: oldData.overrides.deductions['80g'] || 0,
        c80gga: oldData.overrides.deductions['80gga'] || 0,
        c80ggc: oldData.overrides.deductions['80ggc'] || 0,
        hra: oldData.overrides.deductions['hra'] || 0,
        lta: oldData.overrides.deductions['lta'] || 0,
        sec10_other: oldData.overrides.deductions['sec10_other'] || 0,
        ptax: oldData.overrides.deductions['ptax'] || 0,
        c24b: oldData.overrides.deductions['24b'] || 0
      })
    }

    if (oldData?.overrides?.manual_taxes) {
      setManualTax(oldData.overrides.manual_taxes)
    }
  }, [oldData?.overrides])

  const handleSave = (latestItems?: any, latestDeductions?: any, latestManualTax?: number) => {
    const d = latestDeductions || deductions;
    const tax = latestManualTax !== undefined ? latestManualTax : manualTax;
    
    mutation.mutate({ 
      deductions: { 
        '80c': d.c80c, 
        '80ccc': d.c80ccc,
        '80ccd1': d.c80ccd1, 
        '80ccd1b': d.c80ccd1b, 
        '80ccd2': d.c80ccd2,
        '80d': d.c80d, 
        '80dd': d.c80dd,
        '80u': d.c80u,
        '80e': d.c80e,
        '80g': d.c80g, 
        '80gga': d.c80gga,
        '80ggc': d.c80ggc,
        'hra': d.hra, 
        'lta': d.lta, 
        'sec10_other': d.sec10_other, 
        'ptax': d.ptax, 
        '24b': d.c24b
      },
      itemized_deductions: {},
      manual_taxes: tax
    })
  }

  const handleUpdateDeduction = (key: string, val: number) => {
    const newDeductions = { ...deductions, [key]: val }
    setDeductions(newDeductions)
    handleSave({}, newDeductions)
  }



  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      form16Mutation.mutate(e.target.files[0])
    }
  }

  return (
    <Box sx={{ pb: 8 }}>
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff', mb: 0.5 }}>Tax Savings & TDS</Typography>
          <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
            Review your TDS payments and explore deduction opportunities under the Old Tax Regime.
          </Typography>
        </Box>
      </Box>

      <Grid container spacing={4}>
        {/* TDS & Taxes Paid */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('tds')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'tds' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#4EDE93', 0.1), display: 'flex' }}>
                <ShieldIcon sx={{ color: '#4EDE93', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>TDS & Taxes Paid</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Auto-fetched from AIS</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {((tdsData?.total_tax_paid || 0)) >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#4EDE93' }}>{fmtInr(tdsData?.total_tax_paid || 0)}</Typography>
                )}

                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'tds' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            
            <Collapse in={expandedCat === 'tds'}>
            <Stack spacing={2}>
              <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 700 }}>TDS on Salary (Sec 192)</Typography>
                    <Chip label="AIS Auto-filled" size="small" sx={{ ml: 1.5, fontWeight: 800, fontSize: '0.6rem', height: 20, bgcolor: alpha('#4EDE93', 0.1), color: '#4EDE93' }} />
                  </Box>
                  <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>
                    {fmtInr(tdsData?.tds_paid || 0)}
                  </Typography>
                </Box>
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                  Deducted by {tdsData?.income_heads?.salary?.employer?.replace('Section 192) ', '')?.split('(')[0]?.trim() || 'employer'}
                </Typography>
              </Box>

              <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 700 }}>Advance Tax Paid</Typography>
                    <Chip label="AIS Auto-filled" size="small" sx={{ ml: 1.5, fontWeight: 800, fontSize: '0.6rem', height: 20, bgcolor: alpha('#4EDE93', 0.1), color: '#4EDE93' }} />
                  </Box>
                  <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>
                    {fmtInr(tdsData?.advance_tax || 0)}
                  </Typography>
                </Box>
              </Box>

              <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Box>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 700 }}>Self Tax Payments / Challans</Typography>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Manual entry if not in AIS</Typography>
                  </Box>
                  <InlineEdit 
                    value={manualTax || ''}
                    onSave={(val: any) => { const newTax = Number(val); setManualTax(newTax); handleSave({}, deductions, newTax); }}
                    type="number"
                    placeholder="0"
                    formatDisplay={(val: any) => val > 0 ? fmtInr(val) : '₹ 0'}
                    textProps={{ className: "num", sx: { fontWeight: 800, color: manualTax > 0 ? '#fff' : 'text.disabled' } }}
                    inputProps={{ textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}
                    sx={{ width: 120, justifyContent: 'flex-end' }}
                  />
                </Box>
              </Box>

              <Box sx={{
                p: 2.5, borderRadius: '16px',
                bgcolor: alpha('#4EDE93', 0.05), border: `1px solid ${alpha('#4EDE93', 0.2)}`
              }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" sx={{ color: '#4EDE93', fontWeight: 800 }}>Total Tax Already Paid</Typography>
                  <Typography variant="body2" className="num" sx={{ fontWeight: 900, color: '#4EDE93' }}>
                    {fmtInr(tdsData?.total_tax_paid || 0)}
                  </Typography>
                </Box>
              </Box>
            </Stack>

            {/* Previous Refund */}
            {tdsData?.refunds?.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="overline" sx={{ color: '#38BDF8', fontWeight: 900, letterSpacing: '0.1em', mb: 1.5, display: 'block' }}>
                  PREVIOUS REFUNDS
                </Typography>
                {tdsData.refunds.map((r: any, i: number) => (
                  <Box key={i} sx={{ p: 2, borderRadius: '12px', bgcolor: alpha('#38BDF8', 0.05), border: `1px solid ${alpha('#38BDF8', 0.15)}` }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700 }}>FY {r.fy}</Typography>
                        <Chip label="AIS Auto-filled" size="small" sx={{ ml: 1.5, fontWeight: 800, fontSize: '0.6rem', height: 20, bgcolor: alpha('#4EDE93', 0.1), color: '#4EDE93' }} />
                      </Box>
                      <Typography variant="body2" className="num" sx={{ color: '#38BDF8', fontWeight: 800 }}>{fmtInr(r.amount)}</Typography>
                    </Box>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>
                      Received on {r.date}
                    </Typography>
                  </Box>
                ))}
              </Box>
            )}
            </Collapse>
          </Paper>
        </Grid>

        {/* 1. Popular Tax Saving Investments */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('popular')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'popular' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#EAB308', 0.1), display: 'flex' }}>
                <TrendingUpIcon sx={{ color: '#EAB308', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Popular Tax Saving Investments</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>80C, PPF, ELSS, NPS, Savings Bank Interest, Pension, and more</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {popularTotal >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#EAB308' }}>{fmtInr(popularTotal)}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'popular' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'popular'}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <DeductionItem label="80C - PPF, ELSS, Life Insurance, etc." sub="Limit: 1,50,000" infoText="Section 80C: Combined maximum limit of ₹1,50,000 under Section 80CCE. Includes PPF, EPF, ELSS, Life Insurance premiums, Principal home loan repayment, Tuition fees, etc." used={deductions.c80c} onChange={(val: any) => handleUpdateDeduction('c80c', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80TTA / 80TTB - Savings Account and FD Interest Deduction" sub="This amount is auto-filled from interest income (max ₹10,000 for 80TTA, ₹50,000 for 80TTB)." infoText="Section 80TTA: Max ₹10,000 exemption on Savings Bank Interest for age < 60. Section 80TTB: Max ₹50,000 on Savings+FD Interest for age >= 60." used={oldData?.deductions?.['80ttb'] || oldData?.deductions?.['80tta'] || 0} autoFilled={true} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80CCC - Pension/Annuity fund contribution" sub="Limit: 1,50,000. Applicable for new pension plan or existing." infoText="Section 80CCC: Deduction for annuity plan of LIC or other insurers. Included in the overall ₹1,50,000 limit of Section 80CCE." used={deductions.c80ccc} onChange={(val: any) => handleUpdateDeduction('c80ccc', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80CCD (1) - Employee's (Your) contribution to NPS" sub="Enter amount invested by you in NPS" infoText="Section 80CCD(1): Employee contribution to NPS. Max 10% of Salary (Basic+DA) or 20% of Gross Total Income. Included in ₹1.5L limit of 80CCE." used={deductions.c80ccd1} onChange={(val: any) => handleUpdateDeduction('c80ccd1', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80CCD (1B) - Additional Employee NPS" sub="Additional NPS Contribution (up to ₹50k)" infoText="Section 80CCD(1B): Additional NPS deduction up to ₹50,000. This is over and above the ₹1.5L limit of 80CCE." used={deductions.c80ccd1b} onChange={(val: any) => handleUpdateDeduction('c80ccd1b', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80CCD(2) - Employer's (Company's) contribution for your NPS" sub="This is applicable only for salaried individuals." infoText="Section 80CCD(2): Employer's NPS contribution. Max 10% of salary (14% for Govt employees). Excluded from the ₹1.5L limit." used={deductions.c80ccd2} onChange={(val: any) => handleUpdateDeduction('c80ccd2', val)} />
              </Grid>
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

        {/* 2. Medical Insurance, Health Check-ups, Disabilities */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('medical')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'medical' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#38BDF8', 0.1), display: 'flex' }}>
                <MedicalServicesIcon sx={{ color: '#38BDF8', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Medical Insurance, Health Check-ups, Disabilities</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Deductions related to 80D - Insurance, Disabilities, Health Checkups, etc.</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {medicalTotal >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#38BDF8' }}>{fmtInr(medicalTotal)}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'medical' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'medical'}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <DeductionItem label="80D - Medical Insurance" sub="Applicable for you (self), family (spouse & children) and parents." infoText="Section 80D: Medical Insurance Premium. Max ₹25,000 (Self+Family) + ₹25,000 (Parents). If parents are seniors, limit is ₹50,000. Includes ₹5,000 for preventive health checkups." used={deductions.c80d} onChange={(val: any) => handleUpdateDeduction('c80d', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80DD - Deduction for Disabled Dependent" sub="For a dependent, who is differently-abled & is wholly dependent on you" infoText="Section 80DD: Maintenance/medical treatment of disabled dependent. Flat ₹75,000 deduction (₹1,25,000 for severe disability)." used={deductions.c80dd} onChange={(val: any) => handleUpdateDeduction('c80dd', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80U - Deduction for Self Disability" sub="Do you have any form of self disability?" infoText="Section 80U: Self disability deduction. Flat ₹75,000 deduction (₹1,25,000 for severe disability)." used={deductions.c80u} onChange={(val: any) => handleUpdateDeduction('c80u', val)} />
              </Grid>
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

        {/* 3. Donations / Contributions */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('donations')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'donations' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#EC4899', 0.1), display: 'flex' }}>
                <VolunteerActivismIcon sx={{ color: '#EC4899', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Donations / Contributions</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Deductions for donations to charitable orgs., political parties, R&D, etc.</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {donationsTotal >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#EC4899' }}>{fmtInr(donationsTotal)}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'donations' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'donations'}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <DeductionItem label="80G - Donations to charitable organizations" sub="Govt requires itemized details of donations for this." infoText="Section 80G: Donations to approved charitable funds. Deduction can be 100% or 50% of the donated amount, with or without qualifying limits." used={deductions.c80g} onChange={(val: any) => handleUpdateDeduction('c80g', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80GGA - Donations for Research/Rural Development" sub="Govt requires itemized details of donations for this." infoText="Section 80GGA: Donations for scientific research or rural development. 100% deduction allowed. Cannot be claimed by those having business/professional income." used={deductions.c80gga} onChange={(val: any) => handleUpdateDeduction('c80gga', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="80GGC - Contribution to political party" sub="Enter the contribution or donation made to a political party" infoText="Section 80GGC: Contributions to political parties. 100% deduction. Must be made via non-cash modes." used={deductions.c80ggc} onChange={(val: any) => handleUpdateDeduction('c80ggc', val)} />
              </Grid>
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

        {/* 4. Loans */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('loans')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'loans' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#8B5CF6', 0.1), display: 'flex' }}>
                <RequestQuoteIcon sx={{ color: '#8B5CF6', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Loans</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Deduction for Educational, Home or Electric Vehicle Loans</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {loansTotal >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#8B5CF6' }}>{fmtInr(loansTotal)}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'loans' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'loans'}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <DeductionItem label="Section 24(b) - Home Loan Interest" sub="Deduction on interest paid for a housing loan" infoText="Section 24(b): Interest on Home Loan. Max deduction of ₹2,00,000 for a self-occupied property. No limit for let-out property." used={deductions.c24b} onChange={(val: any) => handleUpdateDeduction('c24b', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="Section 80E - Education Loan" sub="Interest paid on loan taken for higher education" infoText="Section 80E: Interest on Education Loan for higher studies. 100% of interest paid can be deducted for up to 8 years." used={deductions.c80e} onChange={(val: any) => handleUpdateDeduction('c80e', val)} />
              </Grid>
            </Grid>
            </Collapse>
          </Paper>
        </Grid>

        {/* 5. Salary Exemptions */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('exemptions')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'exemptions' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#4EDE93', 0.1), display: 'flex' }}>
                <ReceiptLongIcon sx={{ color: '#4EDE93', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Salary Exemptions (Section 10)</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>HRA, LTA, and other allowances</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                {exemptionsTotal >= 0 && (
                   <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: '#4EDE93' }}>{fmtInr(exemptionsTotal)}</Typography>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'exemptions' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'exemptions'}>
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <DeductionItem label="House Rent Allowance (HRA)" sub="Exemption u/s 10(13A)" infoText="Section 10(13A): HRA exemption is the minimum of: 1) Actual HRA received, 2) 50% of salary (Metro) or 40% (Non-Metro), 3) Rent paid minus 10% of salary." used={deductions.hra} onChange={(val: any) => handleUpdateDeduction('hra', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="Leave Travel Allowance (LTA)" sub="Exemption u/s 10(5)" infoText="Section 10(5): Leave Travel Allowance exemption. Covers domestic travel fare for self and family, allowed twice in a block of 4 calendar years." used={deductions.lta} onChange={(val: any) => handleUpdateDeduction('lta', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="Other Allowances" sub="Exemptions u/s 10(14) (e.g. Children Education)" infoText="Section 10(14): Covers Children Education Allowance (₹100/child/month, max 2 children), Hostel Expenditure (₹300/child/month), Transport allowance, etc." used={deductions.sec10_other} onChange={(val: any) => handleUpdateDeduction('sec10_other', val)} />
              </Grid>
              <Grid item xs={12}>
                <DeductionItem label="Professional Tax" sub="Deduction u/s 16(iii)" infoText="Section 16(iii): Deduction for Professional Tax (Tax on Employment) actually paid during the year. Maximum limit is ₹2,500." used={deductions.ptax} onChange={(val: any) => handleUpdateDeduction('ptax', val)} />
              </Grid>
            </Grid>
            </Collapse>
          </Paper>
        </Grid>


      </Grid>
    </Box>
  )
}

const DeductionItem = ({ label, sub, infoText, used, autoFilled = false, onChange }: any) => {
  const Icon = autoFilled ? CheckCircleIcon : ReceiptLongIcon

  return (
    <Paper className="glass" sx={{ 
      p: 2.5,
      borderRadius: '24px', 
      border: '1px solid rgba(255,255,255,0.05)',
      height: '100%', 
      transition: 'all 0.3s ease',
      bgcolor: 'transparent',
      '&:hover': {
        bgcolor: 'rgba(255,255,255,0.04)'
      }
    }}>
      <Box 
        sx={{ 
          p: 2, 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center'
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ p: 1, borderRadius: '12px', bgcolor: alpha('#38BDF8', 0.1), display: 'flex' }}>
            <Icon sx={{ color: '#38BDF8', fontSize: 20 }} />
          </Box>
          <Box>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="body1" sx={{ color: '#fff', fontWeight: 800 }}>{label}</Typography>
              {sub && (
                <Tooltip title={sub} arrow placement="top">
                  <InfoOutlinedIcon sx={{ fontSize: 16, color: 'text.secondary' }} />
                </Tooltip>
              )}
            </Box>
          </Box>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{ textAlign: 'right' }}>
            {autoFilled ? (
              <Chip label="Auto" size="small" sx={{ mb: 0.5, fontWeight: 800, fontSize: '0.6rem', height: 20, bgcolor: alpha('#4EDE93', 0.1), color: '#4EDE93' }} />
            ) : null}
            
            {(!autoFilled) ? (
              <InlineEdit 
                value={used || ''}
                onSave={(val: any) => { if(onChange) onChange(Number(val)); }}
                type="number"
                placeholder="0"
                formatDisplay={(val: any) => val > 0 ? fmtInr(val) : '₹ 0'}
                textProps={{ className: "num", sx: { fontWeight: 800, fontSize: '1rem', color: used > 0 ? '#fff' : 'text.disabled' } }}
                inputProps={{ textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}
                sx={{ width: 140, justifyContent: 'flex-end' }}
              />
            ) : (
              <Typography variant="body1" className="num" sx={{ fontWeight: 800, color: used > 0 ? '#fff' : 'text.disabled' }}>
                {fmtInr(used || 0)}
              </Typography>
            )}
          </Box>
        </Box>
      </Box>
    </Paper>
  )
}
