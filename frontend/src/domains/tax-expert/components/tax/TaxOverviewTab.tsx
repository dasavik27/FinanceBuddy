import React from 'react'
import { Box, Typography, Paper, Grid, Chip, Stack, Skeleton, alpha, Divider } from '@mui/material'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import { useTaxExpertSummary, useTaxRegimeComparison } from '../../hooks/useTaxExpert'
import { fmtInr } from '../../../../shared/utils/fmt'
import TaxAuditorFindings from './TaxAuditorFindings'

const ComputeRow = ({ label, valueOld, valueNew, indent = false, bold = false, color = '#fff', highlight = false, hideIfZero = true }: any) => {
  const isZero = (v: any) => v === '₹0' || v === '- ₹0' || v === '₹ 0' || v === '- ₹ 0';
  if (hideIfZero && isZero(valueOld) && isZero(valueNew)) return null;

  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pl: indent ? 4 : 2, pr: 2, py: highlight ? 1.5 : 0.5, bgcolor: highlight ? 'rgba(255,255,255,0.02)' : 'transparent', borderRadius: '12px' }}>
      <Typography component="div" variant="body2" sx={{ color: highlight ? '#fff' : 'text.secondary', fontWeight: bold ? 800 : 600, flex: 1 }}>{label}</Typography>
      <Box sx={{ display: 'flex', gap: 4, width: { xs: '180px', sm: '250px' }, justifyContent: 'flex-end' }}>
        <Typography variant="body1" className="num" sx={{ fontWeight: bold ? 900 : 700, color, width: { xs: '80px', sm: '100px' }, textAlign: 'right' }}>{valueOld}</Typography>
        <Typography variant="body1" className="num" sx={{ fontWeight: bold ? 900 : 700, color, width: { xs: '80px', sm: '100px' }, textAlign: 'right' }}>{valueNew}</Typography>
      </Box>
    </Box>
  )
}

const StepCard = ({ step, title, color, children, totalLabel, totalOld, totalNew }: any) => (
  <Paper className="glass" sx={{ borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden', mb: 4 }}>
    <Box sx={{ p: 2.5, bgcolor: alpha(color, 0.05), borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 2 }}>
      <Box sx={{ p: 1, borderRadius: '12px', bgcolor: alpha(color, 0.1), color, display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 40, height: 40 }}>
        <Typography variant="h6" sx={{ fontWeight: 900 }}>{step}</Typography>
      </Box>
      <Typography variant="subtitle1" sx={{ fontWeight: 900, color: '#fff', letterSpacing: '0.05em', flex: 1 }}>{title}</Typography>
      
      {/* Column Headers */}
      <Box sx={{ display: 'flex', gap: 4, width: { xs: '180px', sm: '250px' }, justifyContent: 'flex-end', pr: 1 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, width: { xs: '80px', sm: '100px' }, textAlign: 'right', letterSpacing: '0.05em' }}>OLD REGIME</Typography>
        <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, width: { xs: '80px', sm: '100px' }, textAlign: 'right', letterSpacing: '0.05em' }}>NEW REGIME</Typography>
      </Box>
    </Box>
    <Box sx={{ p: 3 }}>
      <Stack spacing={1.5}>
        {children}
        {(totalLabel) && (
          <>
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', px: 2, py: 1.5, bgcolor: alpha(color, 0.08), borderRadius: '12px', border: `1px solid ${alpha(color, 0.1)}` }}>
              <Typography variant="body1" sx={{ color: color, fontWeight: 900, flex: 1 }}>{totalLabel}</Typography>
              <Box sx={{ display: 'flex', gap: 4, width: { xs: '180px', sm: '250px' }, justifyContent: 'flex-end' }}>
                <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: color, width: { xs: '80px', sm: '100px' }, textAlign: 'right' }}>{totalOld}</Typography>
                <Typography variant="h6" className="num" sx={{ fontWeight: 900, color: color, width: { xs: '80px', sm: '100px' }, textAlign: 'right' }}>{totalNew}</Typography>
              </Box>
            </Box>
          </>
        )}
      </Stack>
    </Box>
  </Paper>
)

export default function TaxOverviewTab() {
  const { data: newRegime, isLoading: loadNew } = useTaxExpertSummary('new')
  const { data: oldRegime, isLoading: loadOld } = useTaxExpertSummary('old')
  const { data: comparison } = useTaxRegimeComparison()

  if (loadNew || loadOld || !newRegime || !oldRegime) {
    return (
      <Box sx={{ pb: 8 }}>
        <Stack spacing={3}>
          {[1, 2, 3].map(n => <Skeleton key={n} variant="rounded" height={120} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} />)}
        </Stack>
      </Box>
    )
  }

  // Determine recommendations and colors
  const recommended = comparison?.recommended === 'new' ? 'New Regime' : 'Old Regime'
  const savings = Math.abs((comparison?.new_regime.total_tax || 0) - (comparison?.old_regime.total_tax || 0))
  const recomColor = '#A855F7'

  return (
    <Box sx={{ pb: 8 }}>
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
          <Chip label={newRegime.itr_type} size="small" sx={{ fontWeight: 900, bgcolor: alpha('#6366F1', 0.15), color: '#818CF8', fontSize: '0.75rem' }} />
          <Chip label={`AY ${newRegime.ay}`} size="small" sx={{ fontWeight: 800, bgcolor: 'rgba(255,255,255,0.05)', color: '#94A3B8', fontSize: '0.7rem' }} />
          <Chip label={`FY ${newRegime.fy}`} size="small" sx={{ fontWeight: 800, bgcolor: 'rgba(255,255,255,0.05)', color: '#94A3B8', fontSize: '0.7rem' }} />
        </Box>
        <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff' }}>Tax Summary</Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Side-by-side comparison of your exact tax liability</Typography>
      </Box>

      {/* Tax Auditor Findings */}
      <TaxAuditorFindings flags={newRegime.reconciliation_flags} />

      <Grid container spacing={4}>
        {/* Left Column: Detailed Steps */}
        <Grid item xs={12} md={8}>
          
          <StepCard step="1" title="Gross Total Income (GTI)" color="#6366F1" totalLabel="Total Gross Income" totalOld={fmtInr(oldRegime.gross_income)} totalNew={fmtInr(newRegime.gross_income)}>
            <ComputeRow label="Income from Salary (Gross)" valueOld={fmtInr(oldRegime.income_heads.salary.gross)} valueNew={fmtInr(newRegime.income_heads.salary.gross)} />
            <ComputeRow label="Less: Standard Deduction u/s 16(ia)" valueOld={`- ${fmtInr(oldRegime.income_heads.salary.std_deduction || 0)}`} valueNew={`- ${fmtInr(newRegime.income_heads.salary.std_deduction || 0)}`} color="#38BDF8" indent />
            <ComputeRow label="Less: Sec 10(13A) HRA Exemption" valueOld={oldRegime.income_heads.salary.sec10_hra > 0 ? `- ${fmtInr(oldRegime.income_heads.salary.sec10_hra)}` : '₹0'} valueNew="₹0" color="#38BDF8" indent />
            <ComputeRow label="Less: Sec 10(5) LTA Exemption" valueOld={oldRegime.income_heads.salary.sec10_lta > 0 ? `- ${fmtInr(oldRegime.income_heads.salary.sec10_lta)}` : '₹0'} valueNew="₹0" color="#38BDF8" indent />
            <ComputeRow label="Less: Other Sec 10 Exemptions" valueOld={oldRegime.income_heads.salary.sec10_other > 0 ? `- ${fmtInr(oldRegime.income_heads.salary.sec10_other)}` : '₹0'} valueNew="₹0" color="#38BDF8" indent />
            <ComputeRow label="Less: Professional Tax u/s 16(iii)" valueOld={oldRegime.income_heads.salary.sec16_ptax > 0 ? `- ${fmtInr(oldRegime.income_heads.salary.sec16_ptax)}` : '₹0'} valueNew="₹0" color="#38BDF8" indent />
            <ComputeRow label="Profits & Gains of Business or Profession" valueOld={fmtInr(oldRegime.income_heads.business?.total_profit || 0)} valueNew={fmtInr(newRegime.income_heads.business?.total_profit || 0)} />
            {/* CG: display total capital gains so it mathematically sums to gross total income */}
            <ComputeRow label="Capital Gains" valueOld={fmtInr(oldRegime.income_heads.capital_gains?.total ?? 0)} valueNew={fmtInr(newRegime.income_heads.capital_gains?.total ?? 0)} />
            {((oldRegime.income_heads.capital_gains?.grandfather_benefit || 0) > 0 || (newRegime.income_heads.capital_gains?.grandfather_benefit || 0) > 0) && (
              <Typography variant="caption" sx={{ color: 'text.secondary', pl: 4, pr: 2, display: 'block', opacity: 0.8 }}>
                Incl. Sec 112A grandfathering benefit of {fmtInr(newRegime.income_heads.capital_gains?.grandfather_benefit || 0)} (31-Jan-2018 FMV)
              </Typography>
            )}
            {((oldRegime.income_heads.capital_gains?.slab_taxed_cg || 0) > 0 || (newRegime.income_heads.capital_gains?.slab_taxed_cg || 0) > 0) && (
              <Typography variant="caption" sx={{ color: 'text.secondary', pl: 4, pr: 2, display: 'block', opacity: 0.8 }}>
                Incl. {fmtInr(newRegime.income_heads.capital_gains?.slab_taxed_cg || 0)} debt/specified-fund gains taxed at slab (Sec 50AA)
              </Typography>
            )}
            <ComputeRow label="Income from Other Sources" valueOld={fmtInr(oldRegime.income_heads.other_sources?.total || 0)} valueNew={fmtInr(newRegime.income_heads.other_sources?.total || 0)} />
            <ComputeRow label="Special Incomes (Crypto, Gaming, Misc)" valueOld={fmtInr((oldRegime.income_heads.crypto?.gains || 0) + (oldRegime.income_heads.gaming?.gains || 0) + (oldRegime.income_heads.misc_income?.total || 0))} valueNew={fmtInr((newRegime.income_heads.crypto?.gains || 0) + (newRegime.income_heads.gaming?.gains || 0) + (newRegime.income_heads.misc_income?.total || 0))} />
          </StepCard>

          <StepCard step="2" title="Chapter VI-A Deductions" color="#38BDF8" totalLabel="Total Deductions" totalOld={`- ${fmtInr(oldRegime.chapter_via_deductions_total ?? oldRegime.total_deductions)}`} totalNew={`- ${fmtInr(newRegime.chapter_via_deductions_total ?? newRegime.total_deductions)}`}>
            {/* Chapter VI-A items only. Sec 10/16 items now in Step 1 under Salary. */}
            <ComputeRow label="Sec 80C, 80CCC, 80CCD(1)" valueOld={fmtInr((oldRegime.deductions?.['80c'] || 0) + (oldRegime.deductions?.['80ccc'] || 0) + (oldRegime.deductions?.['80ccd1'] || 0))} valueNew={fmtInr((newRegime.deductions?.['80c'] || 0) + (newRegime.deductions?.['80ccc'] || 0) + (newRegime.deductions?.['80ccd1'] || 0))} />
            <ComputeRow label="Sec 80CCD(1B) (NPS)" valueOld={fmtInr(oldRegime.deductions?.['80ccd1b'] || 0)} valueNew={fmtInr(newRegime.deductions?.['80ccd1b'] || 0)} />
            <ComputeRow label="Sec 80CCD(2) (Employer NPS)" valueOld={fmtInr(oldRegime.deductions?.['80ccd2'] || 0)} valueNew={fmtInr(newRegime.deductions?.['80ccd2'] || 0)} />
            <ComputeRow label="Sec 80D, 80DD, 80U (Medical & Disability)" valueOld={fmtInr((oldRegime.deductions?.['80d'] || 0) + (oldRegime.deductions?.['80dd'] || 0) + (oldRegime.deductions?.['80u'] || 0))} valueNew={fmtInr((newRegime.deductions?.['80d'] || 0) + (newRegime.deductions?.['80dd'] || 0) + (newRegime.deductions?.['80u'] || 0))} />
            <ComputeRow label="Sec 24(b) & 80E (Loans)" valueOld={fmtInr((oldRegime.deductions?.['24b'] || 0) + (oldRegime.deductions?.['80e'] || 0))} valueNew={fmtInr((newRegime.deductions?.['24b'] || 0) + (newRegime.deductions?.['80e'] || 0))} />
            {oldRegime.deductions?.['80ttb'] ? (
              <ComputeRow label="Sec 80TTB (Savings & FD Interest - Senior Citizen)" valueOld={fmtInr(oldRegime.deductions?.['80ttb'] || 0)} valueNew={fmtInr(newRegime.deductions?.['80ttb'] || 0)} />
            ) : (
              <ComputeRow label="Sec 80TTA (Savings Interest)" valueOld={fmtInr(oldRegime.deductions?.['80tta'] || 0)} valueNew={fmtInr(newRegime.deductions?.['80tta'] || 0)} />
            )}
            <ComputeRow label="Sec 80G, 80GGA, 80GGC & Others" valueOld={fmtInr((oldRegime.deductions?.['80g'] || 0) + (oldRegime.deductions?.['80gga'] || 0) + (oldRegime.deductions?.['80ggc'] || 0) + (oldRegime.deductions?.['other'] || 0))} valueNew={fmtInr((newRegime.deductions?.['80g'] || 0) + (newRegime.deductions?.['80gga'] || 0) + (newRegime.deductions?.['80ggc'] || 0) + (newRegime.deductions?.['other'] || 0))} />
          </StepCard>

          <StepCard step="3" title="Net Taxable Income" color="#EC4899" totalLabel="Taxable Normal Income" totalOld={fmtInr(oldRegime.taxable_normal_income)} totalNew={fmtInr(newRegime.taxable_normal_income)}>
            <ComputeRow label="Gross Total Income (Step 1)" valueOld={fmtInr(oldRegime.gross_income)} valueNew={fmtInr(newRegime.gross_income)} />
            <ComputeRow label="Less: Total Deductions (Step 2)" valueOld={`- ${fmtInr(oldRegime.chapter_via_deductions_total ?? oldRegime.total_deductions)}`} valueNew={`- ${fmtInr(newRegime.chapter_via_deductions_total ?? newRegime.total_deductions)}`} color="#38BDF8" />
            {/* Special rate incomes: use direct sum of LTCG equity + STCG equity + LTCG other + Crypto + Gaming */}
            <ComputeRow 
              label="Less: Special Rate Incomes (CG, Crypto, Lottery)" 
              valueOld={`- ${fmtInr((oldRegime.income_heads.capital_gains?.total_special_rate ?? 0) + (oldRegime.income_heads.crypto?.gains || 0) + (oldRegime.income_heads.gaming?.gains || 0))}`} 
              valueNew={`- ${fmtInr((newRegime.income_heads.capital_gains?.total_special_rate ?? 0) + (newRegime.income_heads.crypto?.gains || 0) + (newRegime.income_heads.gaming?.gains || 0))}`} 
              color="#A855F7" 
            />
          </StepCard>

          <StepCard step="4" title="Tax Calculation" color="#F59E0B" totalLabel="Total Tax Liability" totalOld={fmtInr(oldRegime.total_tax)} totalNew={fmtInr(newRegime.total_tax)}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, px: 2, display: 'block', mb: 1 }}>TAX ON NORMAL SLAB</Typography>
            <ComputeRow label={
              <Box>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Tax on Normal Income</Typography>
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5, lineHeight: 1.2, opacity: 0.7 }}>
                  Tax calculated on your salary, interest, and other standard income. Excludes capital gains.
                </Typography>
              </Box>
            } valueOld={fmtInr(oldRegime.tax_on_normal_income)} valueNew={fmtInr(newRegime.tax_on_normal_income)} />
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />

            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, px: 2, display: 'block', mb: 1, mt: 1 }}>TAX ON SPECIAL RATES (BEFORE REBATE)</Typography>
            <ComputeRow label="LTCG Equity Tax (12.5%)" valueOld={fmtInr(oldRegime.tax_on_capital_gains.ltcg_equity)} valueNew={fmtInr(newRegime.tax_on_capital_gains.ltcg_equity)} />
            <ComputeRow label="STCG Equity Tax (20%)" valueOld={fmtInr(oldRegime.tax_on_capital_gains.stcg_equity)} valueNew={fmtInr(newRegime.tax_on_capital_gains.stcg_equity)} />
            <ComputeRow label="LTCG Debt/Other Tax (12.5%)" valueOld={fmtInr(oldRegime.tax_on_capital_gains.ltcg_other || 0)} valueNew={fmtInr(newRegime.tax_on_capital_gains.ltcg_other || 0)} />
            <ComputeRow label="STCG at Applicable Rate (Slab)" valueOld={fmtInr(oldRegime.income_heads.capital_gains?.stcg_other || 0)} valueNew={fmtInr(newRegime.income_heads.capital_gains?.stcg_other || 0)} />
            <ComputeRow label="Crypto & Gaming Tax (30%)" valueOld={fmtInr((oldRegime.income_heads.crypto?.tax || 0) + (oldRegime.income_heads.gaming?.tax || 0))} valueNew={fmtInr((newRegime.income_heads.crypto?.tax || 0) + (newRegime.income_heads.gaming?.tax || 0))} />
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />

            <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 800, px: 2, display: 'block', mb: 1, mt: 1 }}>REBATE, SURCHARGE & CESS</Typography>
            <ComputeRow
              label={
                <Box>
                  <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Less: Rebate u/s 87A</Typography>
                  {(newRegime.rebate_87a_on_cg > 0 || oldRegime.rebate_87a_on_cg > 0) && (
                    <Typography variant="caption" sx={{ color: '#4EDE93', display: 'block', mt: 0.5, lineHeight: 1.2, opacity: 0.8 }}>
                      Cascades to Capital Gains tax after wiping normal income tax
                    </Typography>
                  )}
                </Box>
              }
              valueOld={`- ${fmtInr(oldRegime.rebate_87a)}`}
              valueNew={`- ${fmtInr(newRegime.rebate_87a)}`}
              color="#4EDE93"
            />
            
            {(oldRegime.rebate_87a > 0 || newRegime.rebate_87a > 0) && (
              <ComputeRow 
                label="Tax after rebate" 
                valueOld={fmtInr(oldRegime.tax_on_normal_income + (oldRegime.tax_on_capital_gains.total || 0) + (oldRegime.income_heads.crypto?.tax || 0) + (oldRegime.income_heads.gaming?.tax || 0) - oldRegime.rebate_87a)}
                valueNew={fmtInr(newRegime.tax_on_normal_income + (newRegime.tax_on_capital_gains.total || 0) + (newRegime.income_heads.crypto?.tax || 0) + (newRegime.income_heads.gaming?.tax || 0) - newRegime.rebate_87a)}
                bold
              />
            )}
            <ComputeRow label="Add: Surcharge" valueOld={fmtInr(oldRegime.surcharge)} valueNew={fmtInr(newRegime.surcharge)} hideIfZero={false} />
            {(oldRegime.surcharge > 0 || newRegime.surcharge > 0) && (
              <Typography variant="caption" sx={{ color: 'text.secondary', pl: 2, pr: 2, display: 'block', opacity: 0.8 }}>
                Surcharge on capital gains is capped at 15%{newRegime.surcharge_detail?.rate === 0.25 ? '; New Regime surcharge capped at 25%' : ''}
                {(newRegime.surcharge_detail?.marginal_relief || 0) > 0 || (oldRegime.surcharge_detail?.marginal_relief || 0) > 0 ? '; marginal relief applied' : ''}
              </Typography>
            )}
            <ComputeRow label="Add: Health & Education Cess (4%)" valueOld={fmtInr(oldRegime.cess)} valueNew={fmtInr(newRegime.cess)} />
          </StepCard>


          <StepCard step="5" title="Final Settlement" color="#14B8A6" totalLabel="FINAL SETTLEMENT" totalOld={oldRegime.refund_or_due > 0 ? `REFUND: ${fmtInr(oldRegime.refund_or_due)}` : `DUE: ${fmtInr(Math.abs(oldRegime.refund_or_due))}`} totalNew={newRegime.refund_or_due > 0 ? `REFUND: ${fmtInr(newRegime.refund_or_due)}` : `DUE: ${fmtInr(Math.abs(newRegime.refund_or_due))}`}>
            <ComputeRow label="Total Tax Liability (Step 4)" valueOld={fmtInr(oldRegime.total_tax)} valueNew={fmtInr(newRegime.total_tax)} />
            <ComputeRow label="Add: Interest u/s 234A/B/C" valueOld={fmtInr(oldRegime.interest_234_total || 0)} valueNew={fmtInr(newRegime.interest_234_total || 0)} color="#F59E0B" />
            {((oldRegime.interest_234_total || 0) > 0 || (newRegime.interest_234_total || 0) > 0) && (
              <ComputeRow label="Aggregate Liability (Tax + Interest)" valueOld={fmtInr(oldRegime.aggregate_liability ?? oldRegime.total_tax)} valueNew={fmtInr(newRegime.aggregate_liability ?? newRegime.total_tax)} bold />
            )}
            <ComputeRow label="Less: TDS Deducted" valueOld={`- ${fmtInr(oldRegime.tds_paid)}`} valueNew={`- ${fmtInr(newRegime.tds_paid)}`} color="#4EDE93" />
            <ComputeRow label="Less: Advance / Self-Assessment Tax Paid" valueOld={`- ${fmtInr(oldRegime.advance_tax)}`} valueNew={`- ${fmtInr(newRegime.advance_tax)}`} color="#4EDE93" />
            <ComputeRow label="Less: Manual Taxes Overridden" valueOld={`- ${fmtInr(oldRegime.manual_tax_paid || 0)}`} valueNew={`- ${fmtInr(newRegime.manual_tax_paid || 0)}`} color="#4EDE93" />
          </StepCard>

        </Grid>

        {/* Right Column: Sticky Summary */}
        <Grid item xs={12} md={4}>
          <Box sx={{ position: 'sticky', top: 24 }}>
            {/* Hero Recommendation Card */}
            <Paper className="glass" sx={{ 
              p: 5, 
              borderRadius: '32px', 
              border: `1px solid ${alpha(recomColor, 0.2)}`,
              boxShadow: `0 8px 32px ${alpha(recomColor, 0.15)}`,
              mb: 4,
              background: `linear-gradient(145deg, ${alpha(recomColor, 0.1)} 0%, rgba(20,20,20,0.8) 100%)`,
              position: 'relative',
              overflow: 'hidden'
            }}>
              {/* Ambient Glow */}
              <Box sx={{
                position: 'absolute',
                top: '-50%',
                left: '50%',
                transform: 'translateX(-50%)',
                width: '600px',
                height: '600px',
                background: `radial-gradient(circle, ${alpha(recomColor, 0.15)} 0%, transparent 60%)`,
                pointerEvents: 'none',
              }} />

              <Box sx={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
                <Chip 
                  icon={<CompareArrowsIcon sx={{ fontSize: '18px !important' }} />} 
                  label="RECOMMENDED ACTION"
                  sx={{ 
                    bgcolor: alpha(recomColor, 0.15), 
                    color: recomColor, 
                    fontWeight: 900, 
                    letterSpacing: '0.1em',
                    mb: 3,
                    border: `1px solid ${alpha(recomColor, 0.3)}`,
                    backdropFilter: 'blur(10px)',
                  }} 
                />
                
                <Typography variant="h3" sx={{ fontWeight: 900, color: '#fff', mb: 2, letterSpacing: '-0.02em' }}>
                  Choose the <Box component="span" sx={{ 
                    color: recomColor,
                    display: 'block',
                    mt: 1,
                    textShadow: `0 0 20px ${alpha(recomColor, 0.5)}`
                  }}>
                    {recommended}
                  </Box>
                </Typography>
                
                <Typography variant="body1" sx={{ color: 'rgba(255,255,255,0.8)', fontWeight: 500, mx: 'auto', lineHeight: 1.6 }}>
                  Filing under the {recommended} legally minimizes your liability. You save <Box component="span" className="num" sx={{ color: recomColor, fontWeight: 800, fontSize: '1.1em', bgcolor: alpha(recomColor, 0.1), px: 1, py: 0.5, borderRadius: '8px', mx: 0.5 }}>{fmtInr(savings)}</Box>.
                </Typography>
                
                <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 500, display: 'block', mt: 3, opacity: 0.6, fontFamily: 'monospace' }}>
                  [ {fmtInr(Math.max(oldRegime.total_tax, newRegime.total_tax))} ({recommended === 'New Regime' ? 'Old Regime' : 'New Regime'}) - {fmtInr(Math.min(oldRegime.total_tax, newRegime.total_tax))} ({recommended}) = {fmtInr(savings)} saved ]
                </Typography>
              </Box>
            </Paper>
          </Box>
        </Grid>
      </Grid>
    </Box>
  )
}
