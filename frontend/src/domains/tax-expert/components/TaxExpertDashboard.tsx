import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box, Typography, Paper, CircularProgress } from '@mui/material'
import { motion } from 'framer-motion'
import DescriptionIcon from '@mui/icons-material/Description'
import { useTaxSessionId, useAppStore } from '../../../shared/store/appStore'
import { useTaxExpertSummary } from '../hooks/useTaxExpert'
import TaxStrategyTab from './TaxStrategyTab'
import TaxUploadPanel, { SwitchTaxSessionButton } from './TaxUploadPanel'
import { ErrorBoundary } from '../../../shared/components/ui'

export default function TaxExpertDashboard() {
  const sid = useTaxSessionId()
  const setActiveModule = useAppStore((s) => s.setActiveModule)
  const setSession = useAppStore((s) => s.setSession)
  const clearSession = useAppStore((s) => s.clearSession)
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    setActiveModule('tax_expert')
  }, [setActiveModule])

  // Session validation piggybacks on the cached summary query instead of firing
  // its own raw axios call. The previous version requested the identical URL
  // (/tax/summary?regime=new) outside react-query, so it neither deduped against
  // nor populated the cache — TaxOverviewTab then re-requested the same data
  // moments later. On Render's free tier that doubled an already slow round trip
  // and gated first paint behind it. Sharing this query key means the request
  // TaxOverviewTab needs is the same one that validates the session: one fetch.
  const { isLoading, error } = useTaxExpertSummary('new')
  const validating = !!sid && isLoading

  // A 404 means the backend no longer knows this session (Render's free tier has
  // an ephemeral disk, so sessions do not survive a redeploy or spin-down).
  useEffect(() => {
    if ((error as any)?.response?.status === 404) {
      clearSession('tax_expert')
      setSessionExpired(true)
    }
  }, [error, clearSession])

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

          {/* Switch session button — mirrors Mutual Funds "Switch Statement" */}
          <motion.div initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 }}>
            <SwitchTaxSessionButton sessionId={sid} />
          </motion.div>
        </Box>
      </Paper>

      <Routes>
        <Route index element={<ErrorBoundary fallbackMessage="Tax Expert encountered an error."><TaxStrategyTab /></ErrorBoundary>} />
        <Route path="*" element={<Navigate to="/dashboard/tax-expert" replace />} />
      </Routes>
    </Box>
  )
}
