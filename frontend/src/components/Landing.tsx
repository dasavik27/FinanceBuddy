import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Box, Typography, Button, TextField, Alert, CircularProgress,
  Paper, Chip, Stack,
} from '@mui/material'
import UploadFileIcon   from '@mui/icons-material/UploadFile'
import LockIcon         from '@mui/icons-material/Lock'
import ShieldIcon       from '@mui/icons-material/Shield'
import SpeedIcon        from '@mui/icons-material/Speed'
import InsightsIcon     from '@mui/icons-material/Insights'
import TrendingUpIcon   from '@mui/icons-material/TrendingUp'
import CheckCircleIcon  from '@mui/icons-material/CheckCircle'
import { apiClient }    from '../api/client'
import { useAppStore }  from '../store/appStore'

const steps = [
  {
    icon: <UploadFileIcon sx={{ fontSize: 28, color: '#1D4ED8' }} />,
    num:  '01',
    title:'CAS PDF Import',
    desc: 'Get a Detailed CAS from cams.com, kfintech.com, or mfcentral.com. Covers all AMCs with full transaction history.',
  },
  {
    icon: <LockIcon sx={{ fontSize: 28, color: '#059669' }} />,
    num:  '02',
    title:'Upload & Unlock',
    desc: 'Enter your PAN as password (uppercase), upload the file and click Analyze. Zero data retention — processed in memory only.',
  },
  {
    icon: <InsightsIcon sx={{ fontSize: 28, color: '#7C3AED' }} />,
    num:  '03',
    title:'Institutional Analytics',
    desc: 'Get XIRR, Alpha, Sharpe ratio, per-fund benchmark comparison, tax estimates and smart nudges — instantly.',
  },
]

const trust = [
  { icon: <ShieldIcon sx={{ fontSize: 16 }} />, label: 'Zero Data Retention' },
  { icon: <LockIcon   sx={{ fontSize: 16 }} />, label: 'In-memory Only' },
  { icon: <SpeedIcon  sx={{ fontSize: 16 }} />, label: 'SEBI CSCRF 2025' },
]

export default function Landing() {
  const [file,     setFile]     = useState<File | null>(null)
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState<string | null>(null)
  const { setSession } = useAppStore()
  const navigate = useNavigate()

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) { setFile(accepted[0]); setError(null) }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  })

  const handleAnalyze = async () => {
    if (!file)     return setError('Please upload a CAS PDF')
    if (!password) return setError('Please enter your PAN password')
    setLoading(true); setError(null)
    try {
      const data = await apiClient.parseFile(file, password)
      setSession(data.session_id, data)
      navigate('/dashboard')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse CAS. Check the file and password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'linear-gradient(160deg, #F0F4FA 0%, #EEF2FF 50%, #F0F4FA 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, md: 4 },
      }}
    >
      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0, 0, 0, 1] }}
      >
        <Box sx={{ textAlign: 'center', mb: 6 }}>
          {/* Logo badge */}
          <Box
            sx={{
              width: 64, height: 64, borderRadius: '18px', mx: 'auto', mb: 3,
              background: 'linear-gradient(135deg, #1D4ED8 0%, #6D28D9 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 10px 30px rgba(29,78,216,0.4)',
            }}
          >
            <TrendingUpIcon sx={{ fontSize: 32, color: '#fff' }} />
          </Box>

          <Typography
            variant="h1"
            sx={{
              background: 'linear-gradient(135deg, #0F172A 0%, #1D4ED8 50%, #6D28D9 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              mb: 2,
            }}
          >
            Know your portfolio.<br />Beat the benchmark.
          </Typography>

          <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 520, mx: 'auto', mb: 3, lineHeight: 1.8 }}>
            Upload your CAMS / KFintech CAS and get institutional-grade analytics —
            XIRR, alpha, Sharpe ratio, tax estimates and AI-powered nudges.
            <strong> Instantly. Privately.</strong>
          </Typography>

          <Stack direction="row" spacing={1} justifyContent="center" flexWrap="wrap" gap={1}>
            {trust.map((t) => (
              <Chip
                key={t.label}
                icon={t.icon as any}
                label={t.label}
                size="small"
                sx={{
                  background: '#fff',
                  border: '1px solid #E2E8F0',
                  fontWeight: 600,
                  fontSize: '0.75rem',
                  color: '#475569',
                }}
              />
            ))}
          </Stack>
        </Box>
      </motion.div>

      {/* Upload card */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 0.1, ease: [0, 0, 0, 1] }}
        style={{ width: '100%', maxWidth: 480 }}
      >
        <Paper
          elevation={3}
          sx={{
            p: 4, borderRadius: 4,
            border: '1px solid #E2E8F0',
            background: '#FFFFFF',
          }}
        >
          <Typography variant="h5" sx={{ mb: 3, fontWeight: 800 }}>
            Analyze your portfolio
          </Typography>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
              >
                <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Dropzone */}
          <Box
            {...getRootProps()}
            sx={{
              border: `2px dashed ${isDragActive ? '#1D4ED8' : file ? '#059669' : '#CBD5E1'}`,
              borderRadius: 3,
              p: 3,
              textAlign: 'center',
              cursor: 'pointer',
              background: isDragActive ? '#EFF6FF' : file ? '#ECFDF5' : '#F8FAFC',
              transition: 'all 200ms ease',
              mb: 2,
              '&:hover': { borderColor: '#1D4ED8', background: '#EFF6FF' },
            }}
          >
            <input {...getInputProps()} />
            {file ? (
              <Box>
                <CheckCircleIcon sx={{ fontSize: 32, color: '#059669', mb: 1 }} />
                <Typography variant="body2" fontWeight={700} color="#059669">
                  {file.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {(file.size / 1024).toFixed(0)} KB · Click to replace
                </Typography>
              </Box>
            ) : (
              <Box>
                <UploadFileIcon sx={{ fontSize: 36, color: '#94A3B8', mb: 1 }} />
                <Typography variant="body2" fontWeight={600} color="text.secondary">
                  {isDragActive ? 'Drop your CAS here…' : 'Drag & drop your CAS PDF'}
                </Typography>
                <Typography variant="caption" color="text.disabled">
                  or click to browse · PDF only
                </Typography>
              </Box>
            )}
          </Box>

          {/* Password */}
          <TextField
            fullWidth
            type="password"
            label="PAN Password"
            placeholder="ABCDE1234F (uppercase)"
            value={password}
            onChange={(e) => setPassword(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
            sx={{ mb: 3 }}
            InputProps={{
              startAdornment: <LockIcon sx={{ mr: 1, color: '#94A3B8', fontSize: 18 }} />,
            }}
          />

          <Button
            fullWidth
            variant="contained"
            size="large"
            onClick={handleAnalyze}
            disabled={loading}
            sx={{
              py: 1.5,
              fontSize: '1rem',
              background: 'linear-gradient(135deg, #1D4ED8 0%, #6D28D9 100%)',
              boxShadow: '0 6px 20px rgba(29,78,216,0.35)',
              '&:hover': {
                background: 'linear-gradient(135deg, #1E40AF 0%, #5B21B6 100%)',
                boxShadow: '0 8px 28px rgba(29,78,216,0.5)',
              },
            }}
          >
            {loading
              ? <><CircularProgress size={18} sx={{ color: '#fff', mr: 1 }} /> Parsing CAS…</>
              : '🔍  Analyze Portfolio'}
          </Button>

          <Typography variant="caption" display="block" textAlign="center" sx={{ mt: 2, color: '#94A3B8' }}>
            Your file is never uploaded to any server. All processing is in-memory.
          </Typography>
        </Paper>
      </motion.div>

      {/* Step cards */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
          gap: 2,
          maxWidth: 860,
          width: '100%',
          mt: 5,
        }}
      >
        {steps.map((s, i) => (
          <motion.div
            key={s.num}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.2 + i * 0.1, ease: [0, 0, 0, 1] }}
          >
            <Paper
              elevation={1}
              sx={{
                p: 3, borderRadius: 3, height: '100%',
                transition: 'all 200ms ease',
                '&:hover': { transform: 'translateY(-4px)', boxShadow: '0 8px 24px rgba(15,23,42,0.10)' },
              }}
            >
              <Box
                sx={{
                  width: 40, height: 40, borderRadius: '10px',
                  background: '#F1F5F9', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', mb: 2,
                }}
              >
                {s.icon}
              </Box>
              <Typography variant="overline" display="block" sx={{ mb: 0.5, color: '#1D4ED8' }}>
                Step {s.num}
              </Typography>
              <Typography variant="subtitle1" sx={{ mb: 1 }}>
                {s.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" lineHeight={1.7}>
                {s.desc}
              </Typography>
            </Paper>
          </motion.div>
        ))}
      </Box>

      {/* Footer */}
      <Typography variant="caption" display="block" textAlign="center" sx={{ mt: 6, color: '#CBD5E1' }}>
        FolioIQ v6.0 · SEBI CSCRF 2025 · Zero Data Retention Architecture · Not financial advice
      </Typography>
    </Box>
  )
}
