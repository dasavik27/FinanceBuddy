import { useState } from 'react'
import { Box, Typography, Paper, Button, CircularProgress, Snackbar, Alert, alpha } from '@mui/material'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import TimelineIcon from '@mui/icons-material/Timeline'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import ShieldIcon from '@mui/icons-material/Shield'
import LightbulbIcon from '@mui/icons-material/Lightbulb'
import FileDownloadIcon from '@mui/icons-material/FileDownload'
import SecurityIcon from '@mui/icons-material/Security'
import { apiClient } from '../../api/client'

const pillars = [
  {
    icon: <TimelineIcon sx={{ fontSize: 32, color: '#3B82F6' }} />,
    title: 'Indian Stocks',
    desc: 'Connect with Zerodha or upload a CSV to track live equity performance, run fundamental analysis, and simulate portfolio impact.',
    color: '#3B82F6',
    glow: 'rgba(59, 130, 246, 0.15)',
    path: '/dashboard/equity'
  },
  {
    icon: <AccountBalanceIcon sx={{ fontSize: 32, color: '#10B981' }} />,
    title: 'Mutual Funds',
    desc: 'Upload CAS statements to unlock XIRR metrics, detect portfolio overlap, and run automated drift analysis.',
    color: '#10B981',
    glow: 'rgba(16, 185, 129, 0.15)',
    path: '/dashboard/mutual-funds'
  },
  {
    icon: <ShieldIcon sx={{ fontSize: 32, color: '#8B5CF6' }} />,
    title: 'Tax Expert',
    desc: 'Execute institutional FIFO audits, discover tax harvesting opportunities, and track your capital gains liability matrix.',
    color: '#8B5CF6',
    glow: 'rgba(139, 92, 246, 0.15)',
    path: '/dashboard/tax-expert'
  },
  {
    icon: <LightbulbIcon sx={{ fontSize: 32, color: '#F59E0B' }} />,
    title: 'Budget Analyzer',
    desc: 'Parse bank statements, detect cash flows, automate transfers, and monitor your 50/30/20 budget allocations.',
    color: '#F59E0B',
    glow: 'rgba(245, 158, 11, 0.15)',
    path: '/dashboard/budget'
  },
]

export default function DashboardHub() {
  const navigate = useNavigate()
  const [isExporting, setIsExporting] = useState(false)
  const [snack, setSnack] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({
    open: false,
    msg: '',
    severity: 'success',
  })

  const handleExportData = async () => {
    try {
      setIsExporting(true)
      const exportData = await apiClient.exportAccount()
      const jsonStr = JSON.stringify(exportData, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const panTag = exportData?.pan || 'account'
      const dateTag = new Date().toISOString().slice(0, 10)
      a.download = `finance_buddy_export_${panTag}_${dateTag}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      setSnack({ open: true, msg: 'Financial records exported successfully as JSON archive.', severity: 'success' })
    } catch (err: any) {
      console.error('Export failed', err)
      setSnack({
        open: true,
        msg: err?.response?.data?.detail || 'Failed to export account data. Please sign in or upload a statement first.',
        severity: 'error',
      })
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <Box sx={{ width: '100%', maxWidth: 1200, mx: 'auto', mt: 4, pb: 8 }}>
      <Typography variant="h4" sx={{ color: '#F8FAFC', fontWeight: 900, mb: 1, textAlign: 'center' }}>
        Select Your Dashboard
      </Typography>
      <Typography variant="body1" sx={{ color: '#94A3B8', mb: 6, textAlign: 'center', maxWidth: 540, mx: 'auto' }}>
        Choose a module below to begin analyzing your portfolio, budgeting expenses, and tracking your wealth journey.
      </Typography>
      
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 3,
        }}
      >
        {pillars.map((pillar, i) => (
          <motion.div
            key={pillar.title}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 + i * 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            <Paper
              className="glass"
              onClick={() => navigate(pillar.path)}
              sx={{
                p: 3.5, borderRadius: '28px', height: '100%',
                background: 'rgba(15, 23, 42, 0.4)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                position: 'relative',
                overflow: 'hidden',
                cursor: 'pointer',
                transition: 'all 400ms cubic-bezier(0.16, 1, 0.3, 1)',
                display: 'flex',
                flexDirection: 'column',
                '&:hover': {
                  transform: 'translateY(-8px)',
                  borderColor: alpha(pillar.color, 0.3),
                  boxShadow: `0 20px 40px -10px ${pillar.glow}`,
                  '& .icon-wrapper': {
                    transform: 'scale(1.1) rotate(5deg)',
                    background: alpha(pillar.color, 0.2),
                  }
                },
              }}
            >
              <Box sx={{ position: 'absolute', top: 0, right: 0, width: 140, height: 140, background: `radial-gradient(circle at top right, ${pillar.glow} 0%, transparent 70%)`, pointerEvents: 'none' }} />

              <Box
                className="icon-wrapper"
                sx={{
                  width: 56, height: 56, borderRadius: '18px',
                  background: alpha(pillar.color, 0.1), display: 'flex',
                  alignItems: 'center', justifyContent: 'center', mb: 2.5,
                  border: `1px solid ${alpha(pillar.color, 0.2)}`,
                  transition: 'all 400ms cubic-bezier(0.16, 1, 0.3, 1)',
                }}
              >
                {pillar.icon}
              </Box>
              
              <Typography variant="h6" sx={{ mb: 1.2, fontWeight: 800, color: '#F8FAFC' }}>
                {pillar.title}
              </Typography>
              
              <Typography variant="body2" sx={{ color: '#94A3B8', lineHeight: 1.6, fontSize: '0.875rem', flex: 1 }}>
                {pillar.desc}
              </Typography>
            </Paper>
          </motion.div>
        ))}
      </Box>

      {/* Quick Export & Settings Banner */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.5 }}
      >
        <Paper
          className="glass"
          sx={{
            mt: 6,
            p: 3,
            borderRadius: '24px',
            border: '1px solid rgba(255, 255, 255, 0.06)',
            background: 'linear-gradient(180deg, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.6) 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 2.5,
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Box sx={{ p: 1.5, borderRadius: '16px', bgcolor: alpha('#38BDF8', 0.1), color: '#38BDF8' }}>
              <FileDownloadIcon sx={{ fontSize: 28 }} />
            </Box>
            <Box>
              <Typography variant="subtitle1" sx={{ color: '#F8FAFC', fontWeight: 800 }}>
                Data Portability & Export
              </Typography>
              <Typography variant="body2" sx={{ color: '#94A3B8', fontSize: '0.85rem' }}>
                Export your decrypted portfolios, statements, and tax computations in one portable JSON archive.
              </Typography>
            </Box>
          </Box>

          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
            <Button
              variant="outlined"
              onClick={() => navigate('/dashboard/accounts')}
              startIcon={<SecurityIcon />}
              sx={{
                color: '#94A3B8',
                borderColor: 'rgba(255,255,255,0.1)',
                borderRadius: '12px',
                fontWeight: 700,
                px: 2.5,
                '&:hover': { bgcolor: 'rgba(255,255,255,0.05)', borderColor: '#94A3B8' }
              }}
            >
              Account Center
            </Button>
            <Button
              variant="contained"
              startIcon={isExporting ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : <FileDownloadIcon />}
              onClick={handleExportData}
              disabled={isExporting}
              sx={{
                background: 'linear-gradient(135deg, #6366F1 0%, #38BDF8 100%)',
                color: '#fff',
                borderRadius: '12px',
                fontWeight: 800,
                px: 3,
                py: 1,
                boxShadow: '0 8px 24px rgba(99, 102, 241, 0.3)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #4F46E5 0%, #0284C7 100%)',
                }
              }}
            >
              {isExporting ? 'Exporting...' : 'Export Data'}
            </Button>
          </Box>
        </Paper>
      </motion.div>

      <Snackbar 
        open={snack.open} 
        autoHideDuration={4000} 
        onClose={() => setSnack((s) => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snack.severity} sx={{ borderRadius: '12px', fontWeight: 600 }}>
          {snack.msg}
        </Alert>
      </Snackbar>
    </Box>
  )
}
