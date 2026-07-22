import { useEffect, useState, useCallback } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box, Typography, Paper, Button, CircularProgress, Alert, Chip, Stack } from '@mui/material'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ShieldIcon from '@mui/icons-material/Shield'
import DescriptionIcon from '@mui/icons-material/Description'
import { useTaxSessionId, useAppStore } from '../../store/appStore'
import { apiClient } from '../../api/client'
import TaxStrategyTab from '../tabs/TaxStrategyTab'
import { ErrorBoundary } from '../ui'

export default function TaxExpertDashboard() {
  const sid = useTaxSessionId()
  const setActiveModule = useAppStore((s) => s.setActiveModule)
  const { setSession, clearSession } = useAppStore()
  const [sessionExpired, setSessionExpired] = useState(false)
  const [validating, setValidating] = useState(!!sid)

  useEffect(() => {
    setActiveModule('tax_expert')
  }, [setActiveModule])

  // Validate that the stored session ID still exists on the backend
  useEffect(() => {
    if (!sid) {
      setValidating(false)
      return
    }
    setValidating(true)
    apiClient.getTaxExpertSummary(sid, 'new')
      .then(() => setValidating(false))
      .catch((err: any) => {
        if (err?.response?.status === 404) {
          // Session is gone from backend — clear the stale session ID
          clearSession('tax_expert')
          setSessionExpired(true)
        }
        setValidating(false)
      })
  }, [sid]) // eslint-disable-line react-hooks/exhaustive-deps

  if (validating) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
        <CircularProgress sx={{ color: '#6366F1' }} />
        <Typography sx={{ ml: 2, color: '#94A3B8', fontWeight: 600 }}>Restoring your session...</Typography>
      </Box>
    )
  }

  if (!sid) {
    return <AISUpload
      onSessionCreated={(sessionId, data) => { setSessionExpired(false); setSession(sessionId, 'tax_expert', data) }}
      sessionExpired={sessionExpired}
    />
  }

  return (
    <Box>
      <Routes>
        <Route index element={<ErrorBoundary fallbackMessage="Tax Expert encountered an error."><TaxStrategyTab /></ErrorBoundary>} />
        <Route path="*" element={<Navigate to="" replace />} />
      </Routes>
    </Box>
  )
}


function AISUpload({ onSessionCreated, sessionExpired = false }: { onSessionCreated: (sid: string, data: any) => void, sessionExpired?: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)


  const onDropAIS = useCallback((accepted: File[]) => {
    if (accepted[0]) {
      setFile(accepted[0])
      setError(null)
    }
  }, [])
  
  const { getRootProps: getAisRootProps, getInputProps: getAisInputProps, isDragActive: isAisDragActive } = useDropzone({
    onDrop: onDropAIS,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  })

  const handleAnalyze = async () => {
    if (!file) return setError('Please upload a valid AIS PDF.')
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.parseAIS(file)
      onSessionCreated(data.session_id, data)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse AIS. Ensure this is a valid Annual Information Statement PDF.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '70vh', py: 8 }}>
      <Paper
        className="glass"
        sx={{
          p: { xs: 4, md: 6 }, borderRadius: '32px',
          border: '1px solid rgba(99, 102, 241, 0.3)',
          background: 'rgba(19, 27, 46, 0.75)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), 0 0 40px rgba(99, 102, 241, 0.15)',
          maxWidth: 520, width: '100%',
        }}
      >
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <Box sx={{
            width: 64, height: 64, mx: 'auto', mb: 2, borderRadius: '20px',
            background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(56,189,248,0.2))',
            border: '1px solid rgba(99,102,241,0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <DescriptionIcon sx={{ fontSize: 32, color: '#818CF8' }} />
          </Box>
          <Typography variant="h5" sx={{ fontWeight: 900, color: '#F8FAFC', mb: 1 }}>
            Import Your AIS
          </Typography>
          <Typography variant="body2" sx={{ color: '#94A3B8', fontSize: '0.9rem', maxWidth: 380, mx: 'auto' }}>
            Download your Annual Information Statement from the{' '}
            <Typography component="span" sx={{ color: '#818CF8', fontWeight: 700 }}>Income Tax Portal</Typography>
            {' '}and upload it here for instant tax computation.
          </Typography>
        </Box>

        {/* Steps */}
        <Stack direction="row" spacing={1} sx={{ mb: 3, justifyContent: 'center' }}>
          <Chip label="1. Login to incometax.gov.in" size="small" sx={{ fontWeight: 700, fontSize: '0.65rem', bgcolor: 'rgba(255,255,255,0.05)', color: '#94A3B8' }} />
          <Chip label="2. AIS → Download" size="small" sx={{ fontWeight: 700, fontSize: '0.65rem', bgcolor: 'rgba(255,255,255,0.05)', color: '#94A3B8' }} />
          <Chip label="3. Upload here" size="small" sx={{ fontWeight: 700, fontSize: '0.65rem', bgcolor: 'rgba(99,102,241,0.15)', color: '#818CF8' }} />
        </Stack>

        <AnimatePresence mode="wait">
          {sessionExpired && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              <Alert severity="warning" sx={{ mb: 3, borderRadius: '16px', fontWeight: 600 }}>
                ⚡ Your previous session was lost (server restarted). Please re-upload your AIS to continue.
              </Alert>
            </motion.div>
          )}
          {error && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
              <Alert severity="error" sx={{ mb: 3, borderRadius: '16px' }}>{error}</Alert>
            </motion.div>
          )}
        </AnimatePresence>


        <Box sx={{ mb: 3 }}>
        <Box
          {...getAisRootProps()}
          component={motion.div as any}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.98 }}
          sx={{
            flex: 1,
            border: `2px dashed ${isAisDragActive ? '#6366F1' : file ? '#4EDE93' : 'rgba(255, 255, 255, 0.15)'}`,
            borderRadius: '24px',
            p: { xs: 2, md: 3 },
            textAlign: 'center',
            cursor: 'pointer',
            background: isAisDragActive ? 'rgba(99, 102, 241, 0.1)' : file ? 'rgba(78, 222, 147, 0.05)' : 'rgba(255, 255, 255, 0.02)',
            transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
            '&:hover': { borderColor: file ? '#4EDE93' : '#6366F1' },
          }}
        >
          <input {...getAisInputProps()} />
          <AnimatePresence mode="wait">
            {file ? (
              <motion.div key="file" initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }} style={{ width: '100%', overflow: 'hidden' }}>
                <Box sx={{ width: 40, height: 40, mx: 'auto', mb: 1.5, borderRadius: '50%', background: 'rgba(78, 222, 147, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CheckCircleIcon sx={{ fontSize: 20, color: '#4EDE93' }} />
                </Box>
                <Typography variant="body2" fontWeight={800} sx={{ color: '#4EDE93', mb: 0.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', px: 1 }}>
                  {file.name}
                </Typography>
                <Typography variant="caption" sx={{ color: '#94A3B8' }}>Click to replace</Typography>
              </motion.div>
            ) : (
              <motion.div key="empty" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}>
                <Box sx={{ width: 48, height: 48, mx: 'auto', mb: 1.5, borderRadius: '16px', background: 'linear-gradient(135deg, rgba(99,102,241,0.2), rgba(56,189,248,0.2))', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <UploadFileIcon sx={{ fontSize: 24, color: '#818CF8' }} />
                </Box>
                <Typography variant="body2" fontWeight={800} sx={{ color: '#F8FAFC', mb: 0.5 }}>1. Upload AIS</Typography>
                <Typography variant="caption" sx={{ color: '#94A3B8' }}>(Required) PDF format</Typography>
              </motion.div>
            )}
          </AnimatePresence>
        </Box>

        </Box>

        <AnimatePresence>
          {file && (
            <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.3 }}>
              <Button
                fullWidth
                variant="contained"
                size="large"
                onClick={handleAnalyze}
                disabled={loading}
                sx={{
                  py: 1.8, mb: 2, borderRadius: '16px', fontSize: '1.1rem', fontWeight: 800,
                  background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
                  boxShadow: '0 8px 25px rgba(99,102,241,0.45)',
                  textTransform: 'none',
                  '&:hover': { background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)', boxShadow: '0 12px 35px rgba(99,102,241,0.6)' },
                }}
              >
                {loading
                  ? <><CircularProgress size={22} sx={{ color: '#fff', mr: 1.5 }} /> Computing Taxes...</>
                  : '🧮 Compute My Taxes'}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>

        <Typography variant="caption" display="block" textAlign="center" sx={{ color: '#64748B', fontWeight: 600 }}>
          <ShieldIcon sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.5, color: '#4EDE93' }} />
          Your AIS is processed locally on your machine. No data is sent to any external server.
        </Typography>
      </Paper>
    </Box>
  )
}
