import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box, Typography, Paper, CircularProgress, Button, alpha } from '@mui/material'
import { motion } from 'framer-motion'
import DescriptionIcon from '@mui/icons-material/Description'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import { useTaxSessionId, useAppStore } from '../../../shared/store/appStore'
import { useTaxExpertSummary } from '../hooks/useTaxExpert'
import { apiClient } from '../../../shared/api/client'
import TaxStrategyTab from './TaxStrategyTab'
import TaxUploadPanel, { SwitchTaxSessionButton } from './TaxUploadPanel'
import { ErrorBoundary } from '../../../shared/components/ui'

export default function TaxExpertDashboard() {
  const sid = useTaxSessionId()
  const setActiveModule = useAppStore((s) => s.setActiveModule)
  const setSession = useAppStore((s) => s.setSession)
  const clearSession = useAppStore((s) => s.clearSession)
  const [sessionExpired, setSessionExpired] = useState(false)
  const [isExporting, setIsExporting] = useState(false)

  useEffect(() => {
    setActiveModule('tax_expert')
  }, [setActiveModule])

  // Session validation piggybacks on the cached summary query instead of firing
  // its own raw axios call.
  const { data: summaryData, isLoading, error } = useTaxExpertSummary('new')
  const validating = !!sid && isLoading

  useEffect(() => {
    if ((error as any)?.response?.status === 404) {
      clearSession('tax_expert')
      setSessionExpired(true)
    }
  }, [error, clearSession])

  const handleExportTaxReport = async () => {
    if (!sid) return
    try {
      setIsExporting(true)
      const [newReg, oldReg, comp, inc, cg] = await Promise.allSettled([
        apiClient.getTaxExpertSummary(sid, 'new'),
        apiClient.getTaxExpertSummary(sid, 'old'),
        apiClient.compareTaxRegimes(sid),
        apiClient.getTaxExpertIncome(sid),
        apiClient.getTaxExpertCapitalGains(sid),
      ])

      const report = {
        session_id: sid,
        ay: summaryData?.ay || 'Unknown',
        fy: summaryData?.fy || 'Unknown',
        itr_type: summaryData?.itr_type || 'ITR-2',
        exported_at: new Date().toISOString(),
        summary_new_regime: newReg.status === 'fulfilled' ? newReg.value : null,
        summary_old_regime: oldReg.status === 'fulfilled' ? oldReg.value : null,
        regime_comparison: comp.status === 'fulfilled' ? comp.value : null,
        income_breakdown: inc.status === 'fulfilled' ? inc.value : null,
        capital_gains_breakdown: cg.status === 'fulfilled' ? cg.value : null,
      }

      const jsonStr = JSON.stringify(report, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tax_expert_report_AY_${report.ay}_${sid.slice(0, 8)}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Failed to export tax report', e)
    } finally {
      setIsExporting(false)
    }
  }

  if (validating) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress sx={{ color: '#6366F1' }} />
        <Typography sx={{ ml: 2, color: '#94A3B8', fontWeight: 600 }}>Restoring your session...</Typography>
      </Box>
    )
  }

  if (!sid) {
    return (
      <TaxUploadPanel
        onSessionCreated={(sessionId, data) => {
          setSessionExpired(false)
          setSession(sessionId, 'tax_expert', data)
        }}
        sessionExpired={sessionExpired}
      />
    )
  }

  return (
    <Box>
      {/* ── Module header bar (mirrors Mutual Funds dashboard bar) ── */}
      <Paper
        className="glass"
        sx={{
          mb: 4, borderRadius: '16px',
          border: '1px solid rgba(255,255,255,0.05)',
          background: 'rgba(255,255,255,0.02)',
        }}
      >
        <Box display="flex" alignItems="center" justifyContent="space-between" sx={{ px: 2, py: 1 }}>
          {/* Module identity badge */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
            <DescriptionIcon sx={{ color: '#6366F1', fontSize: 20 }} />
            <Typography sx={{ fontWeight: 800, fontSize: '0.82rem', color: '#475569', letterSpacing: '0.06em', display: { xs: 'none', md: 'block' } }}>
              TAX EXPERT
            </Typography>
          </Box>

          {/* Action buttons: Export Tax Report + Switch Statement */}
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Button
              size="small"
              variant="outlined"
              startIcon={isExporting ? <CircularProgress size={14} sx={{ color: '#818CF8' }} /> : <FileDownloadIcon sx={{ fontSize: 16 }} />}
              onClick={handleExportTaxReport}
              disabled={isExporting}
              sx={{
                color: '#94A3B8',
                borderColor: 'rgba(255,255,255,0.1)',
                borderRadius: '10px',
                fontWeight: 700,
                fontSize: '0.78rem',
                textTransform: 'none',
                px: 1.8,
                py: 0.6,
                '&:hover': {
                  bgcolor: alpha('#6366F1', 0.1),
                  borderColor: '#818CF8',
                  color: '#F8FAFC',
                },
              }}
            >
              {isExporting ? 'Exporting...' : 'Export Report'}
            </Button>

            <motion.div initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 }}>
              <SwitchTaxSessionButton sessionId={sid} />
            </motion.div>
          </Box>
        </Box>
      </Paper>

      <Routes>
        <Route index element={<ErrorBoundary fallbackMessage="Tax Expert encountered an error."><TaxStrategyTab /></ErrorBoundary>} />
        <Route path="*" element={<Navigate to="/dashboard/tax-expert" replace />} />
      </Routes>
    </Box>
  )
}
