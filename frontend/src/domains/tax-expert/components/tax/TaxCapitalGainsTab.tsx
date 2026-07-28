import { Box, Typography, Paper, Grid, Stack, Skeleton, alpha, Chip, LinearProgress, Divider, IconButton, Collapse, CircularProgress } from '@mui/material'
import React, { useState, useEffect } from 'react'
import EditIcon from '@mui/icons-material/Edit'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import HomeWorkIcon from '@mui/icons-material/HomeWork'
import ExpandMoreIcon from '@mui/icons-material/ExpandMore'
import ExpandLessIcon from '@mui/icons-material/ExpandLess'
import HistoryIcon from '@mui/icons-material/History'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import CloudUploadIcon from '@mui/icons-material/CloudUpload'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import GavelIcon from '@mui/icons-material/Gavel'
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import InfoIcon from '@mui/icons-material/Info'
import { useDropzone } from 'react-dropzone'
import { useQueryClient } from '@tanstack/react-query'
import { useTaxExpertCapitalGains, useTaxExpertOverrides, useTaxExpertSummary, useTaxExpertTransactionCost } from '../../../hooks/useTaxExpert'
import { useTaxRegime, useAppStore } from '../../../store/appStore'
import { apiClient } from '../../../api/client'
import { fmtInr } from '../../../api/fmt'
import { InlineEdit } from '../../ui/InlineEdit'

const TransactionTable = ({ title, data, count, color, onSaveCost, category }: any) => {
  let grandTotalSale = 0;
  let grandTotalCost = 0;
  let grandTotalGain = 0;

  const stcgData = data.filter((tx: any) => tx.type === 'STCG');
  const ltcgData = data.filter((tx: any) => tx.type === 'LTCG');
  
  data.forEach((tx: any) => {
     const gain = tx.gain || (tx.consideration - tx.cost)
     grandTotalSale += (tx.consideration || 0)
     grandTotalCost += (tx.cost || 0)
     grandTotalGain += gain
  });

  const renderSubCategory = (termData: any[], termTitle: string, termColor: string) => {
    if (termData.length === 0) return null;
    let termSale = 0, termCost = 0, termGain = 0;
    const grouped = termData.reduce((acc: any, tx: any) => {
      const name = tx.security || tx.fund || 'Unknown'
      const gain = tx.gain || (tx.consideration - tx.cost)
      
      termSale += (tx.consideration || 0)
      termCost += (tx.cost || 0)
      termGain += gain

      if (!acc[name]) acc[name] = { transactions: [], totalSale: 0, totalCost: 0, totalGain: 0 }
      acc[name].transactions.push(tx)
      acc[name].totalSale += (tx.consideration || 0)
      acc[name].totalCost += (tx.cost || 0)
      acc[name].totalGain += gain
      return acc
    }, {})

    return (
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, borderBottom: `2px solid ${termColor}40`, pb: 1 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 800, color: termColor }}>{termTitle}</Typography>
          <Box sx={{ display: 'flex', gap: 3, textAlign: 'right' }}>
            <Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Total Sale</Typography>
              <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(termSale)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Total Cost</Typography>
              <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(termCost)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Total Gain</Typography>
              <Typography variant="caption" className="num" sx={{ color: termGain >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>
                {termGain >= 0 ? '+' : ''}{fmtInr(termGain)}
              </Typography>
            </Box>
          </Box>
        </Box>
        <Stack spacing={2.5}>
          {Object.entries(grouped).map(([name, group]: [string, any], groupIdx) => (
            <Box key={groupIdx} sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
              {/* Group Summary Header */}
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', bgcolor: 'rgba(255,255,255,0.03)', px: 2, py: 1.5, borderRadius: '8px' }}>
                <Typography variant="body2" sx={{ fontWeight: 800, color: '#fff', fontSize: '0.85rem' }}>{name}</Typography>
                <Box sx={{ display: 'flex', gap: 3, textAlign: 'right' }}>
                  <Box>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Sale</Typography>
                    <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(group.totalSale)}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Cost</Typography>
                    <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(group.totalCost)}</Typography>
                  </Box>
                  <Box>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Gain</Typography>
                    <Typography variant="caption" className="num" sx={{ color: group.totalGain >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>
                      {group.totalGain >= 0 ? '+' : ''}{fmtInr(group.totalGain)}
                    </Typography>
                  </Box>
                </Box>
              </Box>

              {/* Individual Transactions */}
              <Stack spacing={1}>
                {group.transactions.map((tx: any, i: number) => {
                  const gain = tx.gain || (tx.consideration - tx.cost)
                  const isGain = gain >= 0
                  return (
                    <Box key={i} sx={{
                      p: 1.5, px: 2, borderRadius: '8px', bgcolor: 'rgba(255,255,255,0.015)',
                      borderLeft: `2px solid ${tx.type === 'LTCG' ? '#4EDE93' : '#38BDF8'}`,
                      transition: 'all 0.2s', '&:hover': { bgcolor: 'rgba(255,255,255,0.04)', transform: 'translateX(3px)' }
                    }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1, alignItems: 'center' }}>
                        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                          {tx.cost === 0 && <WarningAmberIcon sx={{ color: '#EAB308', fontSize: 16 }} />}
                          <Chip label={tx.type} size="small" sx={{
                            fontWeight: 900, fontSize: '0.55rem', height: 18,
                            bgcolor: alpha(tx.type === 'LTCG' ? '#4EDE93' : '#38BDF8', 0.1),
                            color: tx.type === 'LTCG' ? '#4EDE93' : '#38BDF8',
                          }} />
                        </Box>
                        {tx.patched && (
                          <Chip icon={<CheckCircleIcon sx={{ fontSize: '12px !important' }} />} label="Auto-Fixed" size="small" sx={{
                            fontWeight: 800, fontSize: '0.55rem', height: 18,
                            bgcolor: alpha('#3B82F6', 0.1), color: '#3B82F6',
                            '& .MuiChip-icon': { color: '#3B82F6', ml: '4px' }
                          }} />
                        )}
                      </Box>
                      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                        <Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>Date</Typography>
                          <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 700 }}>{tx.date}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>Qty</Typography>
                          <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 700 }}>{tx.quantity || '-'}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>Sale</Typography>
                          <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 700 }}>{fmtInr(tx.consideration)}</Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>Cost</Typography>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <InlineEdit 
                              value={tx.cost}
                              onSave={(val: any) => onSaveCost(tx, category, Number(val))}
                              type="number"
                              placeholder="Cost"
                              formatDisplay={(val: any) => val > 0 ? fmtInr(val) : (
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                  <ErrorOutlineIcon sx={{ fontSize: 14 }} /> Add
                                </Box>
                              )}
                              textProps={{ variant: "caption", className: "num", sx: { fontSize: '0.75rem', color: tx.cost === 0 ? '#EAB308' : '#fff', fontWeight: 700 } }}
                              inputProps={{ textAlign: 'left', fontWeight: 700, fontSize: '0.75rem' }}
                              sx={{ 
                                width: tx.cost === 0 ? 80 : 'auto', 
                                justifyContent: tx.cost === 0 ? 'center' : 'flex-start',
                                border: tx.cost === 0 ? '1px dashed rgba(234, 179, 8, 0.4)' : 'none',
                                bgcolor: tx.cost === 0 ? 'rgba(234, 179, 8, 0.05)' : 'transparent',
                                px: tx.cost === 0 ? 1 : 0,
                                py: tx.cost === 0 ? 0.2 : 0,
                                borderRadius: 1,
                                '&:hover': tx.cost === 0 ? { borderColor: '#EAB308', bgcolor: 'rgba(234, 179, 8, 0.1)' } : undefined
                              }}
                            />
                          </Box>
                        </Box>
                        <Box>
                          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.65rem' }}>Gain</Typography>
                          <Typography variant="caption" className="num" sx={{ color: isGain ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>
                            {isGain ? '+' : ''}{fmtInr(gain)}
                          </Typography>
                        </Box>
                      </Box>
                    </Box>
                  )
                })}
              </Stack>
            </Box>
          ))}
        </Stack>
      </Box>
    )
  }

  return (
  <Box sx={{ mt: 3, pt: 3, borderTop: '1px solid rgba(255,255,255,0.05)' }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2, flexWrap: 'wrap', gap: 2 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 800, color: '#fff' }}>{title}</Typography>
        <Chip label={`${count} Transactions`} size="small" sx={{ fontWeight: 800, fontSize: '0.65rem', bgcolor: 'rgba(255,255,255,0.05)', color: '#94A3B8' }} />
      </Box>
      <Box sx={{ display: 'flex', gap: 3, textAlign: 'right', bgcolor: 'rgba(255,255,255,0.02)', px: 2, py: 1, borderRadius: '8px', border: '1px solid rgba(255,255,255,0.05)' }}>
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Grand Total Sale</Typography>
          <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(grandTotalSale)}</Typography>
        </Box>
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Grand Total Cost</Typography>
          <Typography variant="caption" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(grandTotalCost)}</Typography>
        </Box>
        <Box>
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600, display: 'block', fontSize: '0.6rem' }}>Grand Total Gain</Typography>
          <Typography variant="caption" className="num" sx={{ color: grandTotalGain >= 0 ? '#4EDE93' : '#FF516A', fontWeight: 800 }}>
            {grandTotalGain >= 0 ? '+' : ''}{fmtInr(grandTotalGain)}
          </Typography>
        </Box>
      </Box>
    </Box>
    <Box sx={{ maxHeight: 600, overflowY: 'auto', pr: 1, '&::-webkit-scrollbar': { width: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(255,255,255,0.1)', borderRadius: 2 } }}>
      <Stack spacing={2.5}>
        {renderSubCategory(ltcgData, 'Long Term Capital Gains (LTCG)', '#4EDE93')}
        {renderSubCategory(stcgData, 'Short Term Capital Gains (STCG)', '#38BDF8')}
        
        {data.length === 0 && (
          <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center', py: 4, fontWeight: 600 }}>
            No transactions found
          </Typography>
        )}
      </Stack>
    </Box>
  </Box>
)
}

export default function TaxCapitalGainsTab() {
  const regime = useTaxRegime()
  const { data, isLoading } = useTaxExpertCapitalGains()
  const { data: summaryData, isLoading: isSummaryLoading } = useTaxExpertSummary(regime)
  const mutation = useTaxExpertOverrides()
  const costMutation = useTaxExpertTransactionCost()
  const [bfLosses, setBfLosses] = useState({ stcl: 0, ltcl: 0 })
  const [expandedCat, setExpandedCat] = useState<string | null>('equity_shares')
  const [uploadingBroker, setUploadingBroker] = useState(false)
  const sid = useAppStore((s: any) => s.taxSessionId)

  const queryClient = useQueryClient()
  const onDrop = async (accepted: File[]) => {
    if (!accepted[0] || !sid) return
    setUploadingBroker(true)
    try {
      await apiClient.reconcileBrokerFile(sid, accepted[0])
      // Trigger a re-fetch of the data
      queryClient.invalidateQueries({ queryKey: ['tax-expert-capital-gains'] })
      queryClient.invalidateQueries({ queryKey: ['tax-expert-summary'] })
    } catch (e) {
      console.error(e)
      alert("Failed to process broker file.")
    } finally {
      setUploadingBroker(false)
    }
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'], 'application/vnd.ms-excel': ['.xls'] },
    maxFiles: 1,
  })

  
  useEffect(() => {
    if (data?.bf_losses) {
      setBfLosses({ stcl: data.bf_losses.stcl || 0, ltcl: data.bf_losses.ltcl || 0 })
    }
  }, [data?.bf_losses])
  
  const handleSaveLosses = (field: string, val: number) => {
    const newLosses = { ...bfLosses, [field]: val }
    setBfLosses(newLosses)
    mutation.mutate({ bf_losses: newLosses })
  }
  
  const handleSaveCost = (tx: any, category: string, newCost: number) => {
    costMutation.mutate({ category, sr: tx.sr, new_cost: newCost })
  }

  const toggleCat = (cat: string) => {
    setExpandedCat(prev => prev === cat ? null : cat)
  }

  if (isLoading || isSummaryLoading || !data || !summaryData) {
    return (
      <Box sx={{ pb: 8 }}>
        <Grid container spacing={3}>
          {[1, 2, 3, 4].map(n => (
            <Grid item xs={12} key={n}>
              <Skeleton variant="rounded" height={100} sx={{ bgcolor: 'rgba(255,255,255,0.03)', borderRadius: '24px' }} />
            </Grid>
          ))}
        </Grid>
      </Box>
    )
  }

  const exemptionUsed = Math.min(Math.max(0, summaryData.income_heads.capital_gains.ltcg_equity), 125000)
  const exemptionPct = (exemptionUsed / 125000) * 100
  
  const equityTotal = summaryData.tax_on_capital_gains.ltcg_equity + summaryData.tax_on_capital_gains.stcg_equity
  
  const equityCost = (data?.equity_shares || []).reduce((acc: any, tx: any) => acc + tx.cost, 0) + (data?.equity_mf || []).reduce((acc: any, tx: any) => acc + tx.cost, 0)
  const equitySale = (data?.equity_shares || []).reduce((acc: any, tx: any) => acc + tx.consideration, 0) + (data?.equity_mf || []).reduce((acc: any, tx: any) => acc + tx.consideration, 0)
  const otherTotal = summaryData.tax_on_capital_gains.ltcg_other || 0
  
  const otherCost = (data?.real_estate || []).reduce((acc: any, tx: any) => acc + tx.cost, 0) + (data?.bonds_gold || []).reduce((acc: any, tx: any) => acc + tx.cost, 0) + (data?.unlisted || []).reduce((acc: any, tx: any) => acc + tx.cost, 0) + (data?.other_mf || []).reduce((acc: any, tx: any) => acc + tx.cost, 0)
  const otherSale = (data?.real_estate || []).reduce((acc: any, tx: any) => acc + tx.consideration, 0) + (data?.bonds_gold || []).reduce((acc: any, tx: any) => acc + tx.consideration, 0) + (data?.unlisted || []).reduce((acc: any, tx: any) => acc + tx.consideration, 0) + (data?.other_mf || []).reduce((acc: any, tx: any) => acc + tx.consideration, 0)
  
  const allTrades = [
    ...(data?.equity_shares || []), 
    ...(data?.equity_mf || []), 
    ...(data?.other_mf || []), 
    ...(data?.real_estate || []), 
    ...(data?.unlisted || []), 
    ...(data?.bonds_gold || [])
  ]
  
  const zeroCostCount = allTrades.filter((tx: any) => tx.cost === 0 && tx.consideration > 0).length
  const patchedCount = allTrades.filter((tx: any) => tx.patched).length
  
  // Note: we can't reliably detect cost mismatches on the frontend BEFORE the broker file is uploaded, 
  // because we don't have the broker's FMV data to compare against. 
  // However, the user is already warned about potential issues if they have 0-cost trades.
  // We can just rely on the zeroCostCount to trigger the banner.
  const duplicatesRemoved = summaryData.reconciliation_flags?.duplicates_removed || 0

  return (
    <Box sx={{ pb: 8 }}>
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" sx={{ fontWeight: 900, color: '#fff', mb: 0.5 }}>Capital Gains</Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>
          Per-transaction breakdown of assets sold during FY 2025-26.
        </Typography>
      </Box>

      {(patchedCount > 0 || duplicatesRemoved > 0) && (
        <Paper className="glass" sx={{ p: 2, mb: 4, borderRadius: '16px', border: '1px solid rgba(78, 222, 147, 0.3)', background: 'rgba(78, 222, 147, 0.05)', display: 'flex', alignItems: 'center', gap: 2 }}>
          <CheckCircleIcon sx={{ color: '#4EDE93' }} />
          <Box>
            <Typography variant="subtitle2" sx={{ color: '#4EDE93', fontWeight: 800 }}>Reconciliation Successful</Typography>
            <Typography variant="caption" sx={{ color: 'rgba(78, 222, 147, 0.8)' }}>
              {patchedCount > 0 && `Auto-fixed ${patchedCount} transactions (Zero-cost & FMV mismatches). `}
              {duplicatesRemoved > 0 && `Removed ${duplicatesRemoved} duplicate reporting entries.`}
            </Typography>
          </Box>
        </Paper>
      )}

      {zeroCostCount > 0 && patchedCount === 0 && (
        <Paper className="glass" sx={{ p: 3, mb: 4, borderRadius: '24px', border: '1px solid rgba(234, 179, 8, 0.3)', background: 'rgba(234, 179, 8, 0.05)' }}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
            <WarningAmberIcon sx={{ color: '#EAB308', mt: 0.5 }} />
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle1" sx={{ color: '#FDE047', fontWeight: 800, mb: 1 }}>
                Missing Cost Basis Detected
              </Typography>
              <Typography variant="body2" sx={{ color: '#FEF08A', mb: 2 }}>
                We found {zeroCostCount} transactions where the Income Tax Dept (AIS) reported a purchase cost of ₹0. Upload your broker P&L statement to auto-correct these records, fix FMV grandfathering errors, and remove duplicate entries!
              </Typography>
              
              <Box
                {...getRootProps()}
                sx={{
                  border: `2px dashed ${isDragActive ? '#EAB308' : 'rgba(234, 179, 8, 0.3)'}`,
                  borderRadius: '16px', p: 3, textAlign: 'center', cursor: 'pointer',
                  background: isDragActive ? 'rgba(234, 179, 8, 0.1)' : 'rgba(0,0,0,0.1)',
                  transition: 'all 0.2s',
                  '&:hover': { borderColor: '#EAB308', background: 'rgba(234, 179, 8, 0.1)' }
                }}
              >
                <input {...getInputProps()} />
                {uploadingBroker ? (
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
                    <CircularProgress size={20} sx={{ color: '#EAB308' }} />
                    <Typography variant="body2" sx={{ color: '#FDE047', fontWeight: 700 }}>Processing Broker File...</Typography>
                  </Box>
                ) : (
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                    <CloudUploadIcon sx={{ color: '#EAB308', fontSize: 32 }} />
                    <Typography variant="body2" sx={{ color: '#FDE047', fontWeight: 700 }}>
                      Drop Zerodha/Groww Tax P&L Excel Here
                    </Typography>
                    <Typography variant="caption" sx={{ color: 'rgba(254, 240, 138, 0.7)' }}>
                      Click or drag and drop to auto-fix missing costs
                    </Typography>
                  </Box>
                )}
              </Box>
            </Box>
          </Box>
        </Paper>
      )}

      <Grid container spacing={4}>
        
        {/* Equity & Mutual Funds */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('equity')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'equity' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#6366F1', 0.1), display: 'flex' }}>
                <TrendingUpIcon sx={{ color: '#6366F1', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Equity & Equity Mutual Funds</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Shares and mutual funds with &gt;65% domestic equity exposure</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Box sx={{ textAlign: 'right', display: { xs: 'none', md: 'block' } }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Cost</Typography>
                  <Typography variant="body2" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(equityCost)}</Typography>
                </Box>
                <Box sx={{ textAlign: 'right', display: { xs: 'none', md: 'block' } }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Value</Typography>
                  <Typography variant="body2" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(equitySale)}</Typography>
                </Box>
                {equityTotal >= 0 && (
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Tax</Typography>
                    <Typography variant="body2" className="num" sx={{ fontWeight: 900, color: '#6366F1' }}>{fmtInr(equityTotal)}</Typography>
                  </Box>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'equity' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            
            <Collapse in={expandedCat === 'equity'}>
              <Grid container spacing={3}>
                <Grid item xs={12} md={6}>
                  <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <Typography variant="subtitle2" sx={{ color: '#4EDE93', fontWeight: 800, mb: 2 }}>Long Term (LTCG)</Typography>
                    <Stack spacing={1.5}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Realized Gain</Typography>
                        <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(summaryData.income_heads.capital_gains.ltcg_equity)}</Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" sx={{ color: '#EAB308', fontWeight: 600 }}>Less: Sec 112A Exemption</Typography>
                        <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#EAB308' }}>- {fmtInr(Math.min(summaryData.income_heads.capital_gains.ltcg_equity, 125000))}</Typography>
                      </Box>
                      <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', borderStyle: 'dashed' }} />
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" sx={{ color: '#38BDF8', fontWeight: 700 }}>Taxable Base</Typography>
                        <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#38BDF8' }}>{fmtInr(summaryData.income_heads.capital_gains.ltcg_equity_taxable)}</Typography>
                      </Box>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1, p: 1.5, bgcolor: alpha('#FF516A', 0.1), borderRadius: '8px' }}>
                        <Typography variant="body2" sx={{ color: '#FF516A', fontWeight: 800 }}>Computed Tax (@ 12.5%)</Typography>
                        <Typography variant="subtitle2" className="num" sx={{ fontWeight: 900, color: '#FF516A' }}>{fmtInr(summaryData.tax_on_capital_gains.ltcg_equity)}</Typography>
                      </Box>
                    </Stack>
                  </Box>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', height: '100%' }}>
                    <Typography variant="subtitle2" sx={{ color: '#38BDF8', fontWeight: 800, mb: 2 }}>Short Term (STCG)</Typography>
                    <Stack spacing={1.5}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                        <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Realized Gain</Typography>
                        <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(summaryData.income_heads.capital_gains.stcg_equity)}</Typography>
                      </Box>
                      <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', borderStyle: 'dashed' }} />
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1, p: 1.5, bgcolor: alpha('#FF516A', 0.1), borderRadius: '8px' }}>
                        <Typography variant="body2" sx={{ color: '#FF516A', fontWeight: 800 }}>Computed Tax (@ 20%)</Typography>
                        <Typography variant="subtitle2" className="num" sx={{ fontWeight: 900, color: '#FF516A' }}>{fmtInr(summaryData.tax_on_capital_gains.stcg_equity)}</Typography>
                      </Box>
                    </Stack>
                  </Box>
                </Grid>
              </Grid>

              {data.equity_shares_count > 0 && <TransactionTable onSaveCost={handleSaveCost} category="capital_gains_equity" title="Equity Shares" data={data.equity_shares} count={data.equity_shares_count} />}
              {data.equity_mf_count > 0 && <TransactionTable onSaveCost={handleSaveCost} category="capital_gains_mf_equity" title="Equity Mutual Funds" data={data.equity_mf} count={data.equity_mf_count} />}
            </Collapse>
          </Paper>
        </Grid>

        {/* Other Assets */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('other')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'other' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#EC4899', 0.1), display: 'flex' }}>
                <HomeWorkIcon sx={{ color: '#EC4899', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Other Capital Assets</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Real Estate, Gold, Bonds, Debt Funds & Foreign Equity</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Box sx={{ textAlign: 'right', display: { xs: 'none', md: 'block' } }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Cost</Typography>
                  <Typography variant="body2" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(otherCost)}</Typography>
                </Box>
                <Box sx={{ textAlign: 'right', display: { xs: 'none', md: 'block' } }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Value</Typography>
                  <Typography variant="body2" className="num" sx={{ color: '#fff', fontWeight: 800 }}>{fmtInr(otherSale)}</Typography>
                </Box>
                {otherTotal >= 0 && (
                  <Box sx={{ textAlign: 'right' }}>
                    <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total Tax</Typography>
                    <Typography variant="body2" className="num" sx={{ fontWeight: 900, color: '#EC4899' }}>{fmtInr(otherTotal)}</Typography>
                  </Box>
                )}
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'other' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            
            <Collapse in={expandedCat === 'other'}>
              <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', mb: 3 }}>
                <Stack spacing={1.5}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>LTCG (Taxed @ 12.5% without indexation)</Typography>
                    <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(summaryData.income_heads.capital_gains.ltcg_other)}</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>STCG (Added to normal income slab)</Typography>
                    <Typography variant="body2" className="num" sx={{ fontWeight: 800, color: '#fff' }}>{fmtInr(summaryData.income_heads.capital_gains.stcg_other)}</Typography>
                  </Box>
                  <Divider sx={{ borderColor: 'rgba(255,255,255,0.05)', borderStyle: 'dashed' }} />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 1, p: 1.5, bgcolor: alpha('#FF516A', 0.1), borderRadius: '8px' }}>
                    <Typography variant="body2" sx={{ color: '#FF516A', fontWeight: 800 }}>Computed Tax</Typography>
                    <Typography variant="subtitle2" className="num" sx={{ fontWeight: 900, color: '#FF516A' }}>{fmtInr(summaryData.tax_on_capital_gains.ltcg_other || 0)}</Typography>
                  </Box>
                </Stack>
              </Box>

              {data.real_estate_count > 0 && <TransactionTable onSaveCost={handleSaveCost} category="cg_real_estate" title="Real Estate (Land & Building)" data={data.real_estate} count={data.real_estate_count} />}
              {data.bonds_gold_count > 0 && <TransactionTable onSaveCost={handleSaveCost} category="cg_bonds_gold" title="Gold & Bonds" data={data.bonds_gold} count={data.bonds_gold_count} />}
              {data.unlisted_count > 0 && <TransactionTable onSaveCost={handleSaveCost} category="cg_unlisted" title="Foreign Assets & Unlisted Equity" data={data.unlisted} count={data.unlisted_count} />}
              {data.other_mf_count > 0 && <TransactionTable onSaveCost={handleSaveCost} category="capital_gains_mf_other" title="Debt / Other Funds" data={data.other_mf} count={data.other_mf_count} />}
            </Collapse>
          </Paper>
        </Grid>

        {/* Other Section Header */}
        <Grid item xs={12}>
          <Box sx={{ mt: 2, mb: 1 }}>
            <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Other</Typography>
          </Box>
        </Grid>
        
        {/* Brought Forward Losses */}
        <Grid item xs={12}>
          <Paper className="glass" sx={{ p: 3, borderRadius: '32px', border: '1px solid rgba(255,255,255,0.05)' }}>
            <Box onClick={() => toggleCat('bflosses')} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: expandedCat === 'bflosses' ? 4 : 0, cursor: 'pointer' }}>
              <Box sx={{ p: 1.5, borderRadius: '14px', bgcolor: alpha('#F59E0B', 0.1), display: 'flex' }}>
                <HistoryIcon sx={{ color: '#F59E0B', fontSize: 24 }} />
              </Box>
              <Box sx={{ flexGrow: 1 }}>
                <Typography variant="h5" sx={{ fontWeight: 900, color: '#fff' }}>Brought Forward Losses</Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary', fontWeight: 600 }}>Offset current gains with past unadjusted losses</Typography>
              </Box>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Box sx={{ textAlign: 'right', display: { xs: 'none', md: 'block' } }}>
                  <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 600 }}>Total B/F Loss</Typography>
                  <Typography variant="body2" className="num" sx={{ color: '#F59E0B', fontWeight: 800 }}>{fmtInr((bfLosses.stcl || 0) + (bfLosses.ltcl || 0))}</Typography>
                </Box>
                <IconButton size="small" sx={{ color: 'rgba(255,255,255,0.5)' }}>
                  {expandedCat === 'bflosses' ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                </IconButton>
              </Box>
            </Box>
            <Collapse in={expandedCat === 'bflosses'}>
              <Stack spacing={2}>
                <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700 }}>B/F Short-Term Capital Loss (STCL)</Typography>
                  <InlineEdit 
                    value={bfLosses.stcl || 0}
                    onSave={(val: any) => handleSaveLosses('stcl', Number(val))}
                    type="number"
                    placeholder="0"
                    formatDisplay={(val: any) => val > 0 ? fmtInr(val) : '₹ 0'}
                    textProps={{ className: "num", sx: { fontWeight: 800, color: bfLosses.stcl > 0 ? '#fff' : 'text.disabled' } }}
                    inputProps={{ textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}
                    sx={{ width: 140, justifyContent: 'flex-end' }}
                  />
                </Box>
                <Box sx={{ p: 2.5, borderRadius: '16px', bgcolor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Typography variant="body2" sx={{ color: '#fff', fontWeight: 700 }}>B/F Long-Term Capital Loss (LTCL)</Typography>
                  <InlineEdit 
                    value={bfLosses.ltcl || 0}
                    onSave={(val: any) => handleSaveLosses('ltcl', Number(val))}
                    type="number"
                    placeholder="0"
                    formatDisplay={(val: any) => val > 0 ? fmtInr(val) : '₹ 0'}
                    textProps={{ className: "num", sx: { fontWeight: 800, color: bfLosses.ltcl > 0 ? '#fff' : 'text.disabled' } }}
                    inputProps={{ textAlign: 'right', fontWeight: 800, fontFamily: 'monospace' }}
                    sx={{ width: 140, justifyContent: 'flex-end' }}
                  />
                </Box>
              </Stack>
            </Collapse>
          </Paper>
        </Grid>

              </Grid>
    </Box>
  )
}
