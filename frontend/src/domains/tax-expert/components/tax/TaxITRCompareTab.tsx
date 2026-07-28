import React, { useState } from 'react'
import { Box, Typography, Paper, Stack, alpha, Button, CircularProgress, Alert, Divider, ToggleButton, ToggleButtonGroup } from '@mui/material'
import { motion, AnimatePresence } from 'framer-motion'
import { useDropzone } from 'react-dropzone'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import BalanceIcon from '@mui/icons-material/Balance'

import { useITRData, useUploadITR, useTaxExpertSummary } from '../../hooks/useTaxExpert'
import { useTaxRegime, useAppStore } from '../../../../shared/store/appStore'
import { fmtInr } from '../../../../shared/utils/fmt'

// ─── Compute Row ─────────────────────────────────────────────────────────────
const ComputeRow = ({ label, folioVal, itrVal, bold = false, highlight = false, color = '#fff' }: any) => {
  const folioNum = typeof folioVal === 'number' ? folioVal : (typeof folioVal === 'string' && folioVal.includes('₹') ? parseFloat(folioVal.replace(/[^0-9.-]+/g, "")) : 0)
  const itrNum = typeof itrVal === 'number' ? itrVal : 0
  const diff = folioNum - itrNum
  const isMatch = Math.abs(diff) < 10

  const folioDisp = typeof folioVal === 'number' ? fmtInr(folioVal) : (folioVal || '-')
  const itrDisp = typeof itrVal === 'number' ? fmtInr(itrVal) : (itrVal || '-')

  // Don't show if both are exactly 0 and it's not a bold row
  if (folioNum === 0 && itrNum === 0 && !bold && typeof itrVal !== 'number') return null

  return (
    <Box sx={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      px: 2,
      py: highlight ? 1.5 : 1,
      bgcolor: highlight ? 'rgba(255,255,255,0.02)' : 'transparent',
      borderRadius: '8px',
      '&:hover': { bgcolor: 'rgba(255,255,255,0.03)' }
    }}>
      <Box sx={{ flex: 1 }}>
        <Typography variant="body2" sx={{ color: highlight ? '#fff' : 'text.secondary', fontWeight: bold ? 800 : 500, fontSize: bold ? '0.9rem' : '0.85rem' }}>{label}</Typography>
      </Box>

      <Box sx={{ display: 'flex', gap: { xs: 2, sm: 3 }, width: { xs: '240px', sm: '320px' }, justifyContent: 'flex-end', alignItems: 'center' }}>
        <Typography variant="body2" className="num" sx={{ fontWeight: bold ? 900 : 600, color: color, width: { xs: '90px', sm: '100px' }, textAlign: 'right' }}>
          {folioDisp}
        </Typography>
        <Typography variant="body2" className="num" sx={{ fontWeight: bold ? 900 : 600, color: '#94A3B8', width: { xs: '90px', sm: '100px' }, textAlign: 'right' }}>
          {itrDisp}
        </Typography>

        <Box sx={{ width: '40px', display: 'flex', justifyContent: 'flex-end' }}>
          {typeof itrVal === 'number' && typeof folioVal === 'number' ? (
            isMatch ? (
              <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 18 }} />
            ) : (
              <Typography variant="caption" className="num" sx={{ color: '#EF4444', fontWeight: 800, bgcolor: 'rgba(239, 68, 68, 0.1)', px: 0.8, py: 0.3, borderRadius: '4px', whiteSpace: 'nowrap' }}>
                {diff > 0 ? '+' : ''}{Math.round(diff)}
              </Typography>
            )
          ) : null}
        </Box>
      </Box>
    </Box>
  )
}

// ─── Simple Card ───────────────────────────────────────────────────────────────
const SimpleCard = ({ title, color, children }: any) => {
  return (
    <Paper className="glass" sx={{ borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden', mb: 3 }}>
      <Box sx={{ p: 2, bgcolor: alpha(color, 0.05), borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 800, color: '#fff', letterSpacing: '0.02em', flex: 1, pl: 1 }}>{title}</Typography>

        <Box sx={{ display: 'flex', gap: { xs: 2, sm: 3 }, width: { xs: '240px', sm: '320px' }, justifyContent: 'flex-end', alignItems: 'center', pr: { xs: '48px', sm: '56px' } }}>
          <Typography variant="caption" sx={{ color: '#6366F1', fontWeight: 800, width: { xs: '90px', sm: '100px' }, textAlign: 'right' }}>FINANCE BUDDY</Typography>
          <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 800, width: { xs: '90px', sm: '100px' }, textAlign: 'right' }}>YOUR ITR</Typography>
        </Box>
      </Box>

      <Box sx={{ p: 1.5 }}>
        <Stack spacing={0.5}>
          {children}
        </Stack>
      </Box>
    </Paper>
  )
}

// ─── Main Component ──────────────────────────────────────────────────────────
export default function TaxITRCompareTab() {
  const regime = useTaxRegime()
  const setRegime = useAppStore(s => s.setTaxRegime)
  const { data: itrData, isLoading: isLoadingITR } = useITRData()
  const { data: summary, isLoading: isLoadingSummary } = useTaxExpertSummary(regime)
  const uploadMut = useUploadITR()
  const [, setFile] = useState<File | null>(null)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: (accepted) => { if (accepted[0]) { setFile(accepted[0]); uploadMut.mutate(accepted[0]) } },
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  })

  if (isLoadingITR || isLoadingSummary) {
    return <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}><CircularProgress sx={{ color: '#6366F1' }} /></Box>
  }

  // Derived Values
  const taxCg = summary?.tax_on_capital_gains ?? {}
  const refundFb = summary?.refund_or_due ?? 0
  const refundItr = itrData?.tax?.refund_or_due ?? 0
  
  const refundFbDisp = refundFb > 0 ? `REFUND: ${fmtInr(refundFb)}` : `DUE: ${fmtInr(Math.abs(refundFb))}`
  const refundItrDisp = refundItr > 0 ? `REFUND: ${fmtInr(refundItr)}` : (refundItr < 0 ? `DUE: ${fmtInr(Math.abs(refundItr))}` : `₹0`)

  return (
    <Box sx={{ pb: 4, maxWidth: 800, mx: 'auto' }}>
      <AnimatePresence mode="wait">
        {!itrData && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <Paper className="glass" sx={{ p: 4, borderRadius: '24px', textAlign: 'center', mb: 4, border: '1px solid rgba(99,102,241,0.3)' }}>
              <BalanceIcon sx={{ fontSize: 48, color: '#818CF8', mb: 2 }} />
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#fff', mb: 1 }}>Compare ITR vs Finance Buddy</Typography>
              <Typography variant="body2" sx={{ color: '#94A3B8', mb: 4, maxWidth: 400, mx: 'auto' }}>
                Upload your filed ITR PDF to instantly verify the clean 3-part summary of Income, Tax Calculation, and Final Settlement.
              </Typography>
              <Box {...getRootProps()} sx={{ border: `2px dashed ${isDragActive ? '#6366F1' : 'rgba(255,255,255,0.15)'}`, borderRadius: '20px', p: 4, cursor: 'pointer', bgcolor: isDragActive ? 'rgba(99,102,241,0.05)' : 'rgba(255,255,255,0.02)', transition: 'all 0.2s', '&:hover': { borderColor: '#6366F1' } }}>
                <input {...getInputProps()} />
                {uploadMut.isPending ? (
                  <Box><CircularProgress size={32} sx={{ color: '#818CF8', mb: 2 }} /><Typography sx={{ color: '#fff', fontWeight: 600 }}>Parsing ITR Document...</Typography></Box>
                ) : (
                  <Box><UploadFileIcon sx={{ fontSize: 32, color: '#64748B', mb: 1 }} /><Typography sx={{ color: '#fff', fontWeight: 600 }}>Drag & Drop your ITR PDF here</Typography></Box>
                )}
              </Box>
              {uploadMut.isError && <Alert severity="error" sx={{ mt: 3, borderRadius: '12px' }}>Failed to parse ITR PDF.</Alert>}
            </Paper>
          </motion.div>
        )}
      </AnimatePresence>

      {itrData && summary && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3, px: 1 }}>
            <Box>
              <Typography variant="h5" sx={{ fontWeight: 800, color: '#fff' }}>ITR Reconciliation Summary</Typography>
              <Typography variant="caption" sx={{ color: '#94A3B8' }}>{itrData.name} ({itrData.pan}) • {itrData.itr_type} (AY {itrData.assessment_year})</Typography>
            </Box>
            <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
              <ToggleButtonGroup
                value={regime}
                exclusive
                onChange={(e, val) => { if (val) setRegime(val) }}
                size="small"
                sx={{
                  bgcolor: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  '& .MuiToggleButton-root': { color: '#94A3B8', border: 'none', px: 2, textTransform: 'none', py: 0.5, fontSize: '0.8rem' },
                  '& .Mui-selected': { bgcolor: 'rgba(99,102,241,0.2) !important', color: '#818CF8 !important', fontWeight: 700 }
                }}
              >
                <ToggleButton value="old">Old Regime</ToggleButton>
                <ToggleButton value="new">New Regime</ToggleButton>
              </ToggleButtonGroup>
              <Box {...getRootProps()} sx={{ cursor: 'pointer' }}>
                <input {...getInputProps()} />
                <Button size="small" variant="outlined" sx={{ textTransform: 'none', borderRadius: '8px', color: '#94A3B8', borderColor: 'rgba(255,255,255,0.1)' }}>
                  {uploadMut.isPending ? <CircularProgress size={14} sx={{ color: '#94A3B8' }} /> : 'Replace ITR'}
                </Button>
              </Box>
            </Box>
          </Box>

          {/* ── 1. INCOME SUMMARY ─────────────────────────────── */}
          <SimpleCard title="Income Summary" color="#6366F1">
            {/* CMP-5: Salary sub-rows so FB vs ITR comparison is fair */}
            <ComputeRow label="Gross Salary" folioVal={summary.income_heads.salary.gross} itrVal={itrData.income.salary_gross ?? itrData.income.salary} />
            
            {(summary.income_heads.salary.sec10_hra > 0 || summary.income_heads.salary.sec10_lta > 0 || (itrData.income.salary_exemptions && itrData.income.salary_exemptions > 0)) && (
              <ComputeRow 
                label="Less: HRA, LTA & Sec 10 Exemptions" 
                folioVal={-(summary.income_heads.salary.sec10_hra + summary.income_heads.salary.sec10_lta + summary.income_heads.salary.sec10_other)} 
                itrVal={itrData.income.salary_exemptions ? -itrData.income.salary_exemptions : null} 
                color="#38BDF8" 
              />
            )}
            
            <ComputeRow 
              label="Less: Standard Deduction & Sec 16" 
              folioVal={-( (summary.income_heads.salary.std_deduction || 50000) + (summary.income_heads.salary.sec16_ptax || 0) )} 
              itrVal={itrData.income.salary_gross && itrData.income.salary ? -(itrData.income.salary_gross - (itrData.income.salary_exemptions || 0) - itrData.income.salary) : null} 
              color="#38BDF8" 
            />
            
            <ComputeRow label="Net Salary (Chargeable)" folioVal={summary.income_heads.salary.net} itrVal={itrData.income.salary} bold />
            <ComputeRow label="House Property" folioVal={0} itrVal={itrData.income.house_property} />
            <ComputeRow label="Business & Profession" folioVal={summary.income_heads.business?.total_profit || 0} itrVal={itrData.income.business} />
            {/* CMP-3: Use capital_gains.total to match ITR Schedule CG which includes ALL CG buckets */}
            <ComputeRow label="Capital Gains" folioVal={summary.income_heads.capital_gains?.total ?? 0} itrVal={itrData.income.capital_gains} />
            <ComputeRow label="Income from Other Sources" folioVal={summary.income_heads.other_sources?.total || 0} itrVal={itrData.income.other_sources} />
            
            {((summary.income_heads.crypto?.gains || 0) + (summary.income_heads.gaming?.gains || 0)) > 0 && (
              <ComputeRow label="Special Incomes (Crypto, Gaming)" folioVal={(summary.income_heads.crypto?.gains || 0) + (summary.income_heads.gaming?.gains || 0)} itrVal={null} />
            )}

            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            
            <ComputeRow label="Gross Total Income" folioVal={summary.gross_income} itrVal={itrData.income.gross_total} bold />
            {/* CMP-2: Use chapter_via_deductions_total (Chapter VI-A only, excluding Sec 10/16) */}
            <ComputeRow label="Deductions (Chapter VI-A)" folioVal={(summary.chapter_via_deductions_total ?? summary.total_deductions) > 0 ? `- ${fmtInr(summary.chapter_via_deductions_total ?? summary.total_deductions)}` : 0} itrVal={itrData.deductions.total ? `- ${fmtInr(itrData.deductions.total)}` : 0} color="#38BDF8" />
            
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            
            {/* CMP-4: Total Income = taxable_normal (already includes stcg_other) + special rate CG + special rate crypto/gaming */}
            <ComputeRow 
              label="Total Income" 
              folioVal={summary.taxable_normal_income + (summary.income_heads.capital_gains?.total_special_rate ?? ((summary.income_heads.capital_gains?.ltcg_equity || 0) + (summary.income_heads.capital_gains?.stcg_equity || 0) + (summary.income_heads.capital_gains?.ltcg_other || 0))) + (summary.income_heads.crypto?.gains || 0) + (summary.income_heads.gaming?.gains || 0)} 
              itrVal={itrData.tax.taxable_income} 
              bold 
              highlight 
            />
          </SimpleCard>

          {/* ── 2. TAX CALCULATION ─────────────────────────────── */}
          <SimpleCard title="Tax Calculation" color="#F59E0B">
            <ComputeRow label="Tax at normal slab rates" folioVal={summary.tax_on_normal_income} itrVal={itrData.tax.tax_at_slab_rates ?? itrData.tax.tax_on_income} />
            <ComputeRow label="Tax at special rates (CG, Crypto, Lottery)" folioVal={(taxCg.total || 0) + (summary.income_heads.crypto?.tax || 0) + (summary.income_heads.gaming?.tax || 0)} itrVal={itrData.tax.tax_at_special_rate} />
            
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            
            <ComputeRow label="Tax before rebate" folioVal={summary.tax_on_normal_income + (taxCg.total || 0) + (summary.income_heads.crypto?.tax || 0) + (summary.income_heads.gaming?.tax || 0)} itrVal={itrData.tax.tax_before_rebate ?? itrData.tax.tax_on_income} bold />
            
            <ComputeRow label="Less: Rebate u/s 87A" folioVal={summary.rebate_87a > 0 ? `- ${fmtInr(summary.rebate_87a)}` : 0} itrVal={itrData.tax.rebate_87a ? `- ${fmtInr(itrData.tax.rebate_87a)}` : 0} color="#4EDE93" />
            
            {/* Added optional tax after rebate row for clarity */}
            {(summary.rebate_87a > 0 || itrData.tax.rebate_87a > 0) && (
              <ComputeRow label="Tax after rebate" 
                folioVal={summary.tax_on_normal_income + (taxCg.total || 0) + (summary.income_heads.crypto?.tax || 0) + (summary.income_heads.gaming?.tax || 0) - summary.rebate_87a} 
                itrVal={(itrData.tax.tax_before_rebate ?? itrData.tax.tax_on_income) - (itrData.tax.rebate_87a || 0)} 
                bold />
            )}

            <ComputeRow label="Add: Surcharge" folioVal={summary.surcharge} itrVal={itrData.tax.surcharge} />
            <ComputeRow label="Add: Health & Education Cess @4%" folioVal={summary.cess} itrVal={itrData.tax.cess} />
            
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            
            <ComputeRow label="Net Tax Liability" folioVal={summary.total_tax} itrVal={itrData.tax.total_tax_liability} bold highlight />
          </SimpleCard>

          {/* ── 3. TAXES PAID & REFUND ─────────────────────────────── */}
          <SimpleCard title="Taxes Paid & Refund" color="#14B8A6">
            <ComputeRow label="TDS Deducted" folioVal={summary.tds_paid} itrVal={itrData.tax.tds_paid} />
            <ComputeRow label="Advance Tax / Self Assessment" folioVal={summary.advance_tax} itrVal={itrData.tax.advance_tax} />
            {summary.manual_tax_paid > 0 && <ComputeRow label="Manual Taxes Overridden" folioVal={summary.manual_tax_paid} itrVal={null} />}
            
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            
            <ComputeRow label="Total Taxes Paid" folioVal={summary.tds_paid + summary.advance_tax + (summary.manual_tax_paid || 0)} itrVal={itrData.tax.total_taxes_paid} bold />
            <ComputeRow label="Net Tax Liability" folioVal={summary.total_tax} itrVal={itrData.tax.total_tax_liability} bold />
            
            <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', my: 1 }} />
            
            <Box sx={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              px: 2,
              py: 2,
              bgcolor: 'rgba(255,255,255,0.03)',
              borderRadius: '8px'
            }}>
              <Box sx={{ flex: 1 }}>
                <Typography variant="body1" sx={{ color: '#fff', fontWeight: 900 }}>Final Settlement</Typography>
              </Box>
              <Box sx={{ display: 'flex', gap: { xs: 2, sm: 3 }, width: { xs: '240px', sm: '320px' }, justifyContent: 'flex-end', alignItems: 'center' }}>
                <Typography variant="body1" className="num" sx={{ fontWeight: 900, color: refundFb > 0 ? '#4EDE93' : '#F59E0B', width: { xs: '90px', sm: '100px' }, textAlign: 'right' }}>
                  {refundFbDisp}
                </Typography>
                <Typography variant="body1" className="num" sx={{ fontWeight: 900, color: refundItr > 0 ? '#4EDE93' : '#F59E0B', width: { xs: '90px', sm: '100px' }, textAlign: 'right' }}>
                  {refundItrDisp}
                </Typography>
                <Box sx={{ width: '40px', display: 'flex', justifyContent: 'flex-end' }}>
                  {Math.abs(refundFb - refundItr) < 10 ? (
                    <CheckCircleIcon sx={{ color: '#4EDE93', fontSize: 20 }} />
                  ) : (
                    <Typography variant="caption" className="num" sx={{ color: '#EF4444', fontWeight: 900, bgcolor: 'rgba(239, 68, 68, 0.15)', px: 1, py: 0.5, borderRadius: '6px', whiteSpace: 'nowrap' }}>
                      {Math.round(refundFb - refundItr) > 0 ? '+' : ''}{fmtInr(refundFb - refundItr)}
                    </Typography>
                  )}
                </Box>
              </Box>
            </Box>

          </SimpleCard>

        </motion.div>
      )}
    </Box>
  )
}
