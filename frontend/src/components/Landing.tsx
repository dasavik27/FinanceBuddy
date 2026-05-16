import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Box, Typography, Button, TextField, Alert, CircularProgress,
  Paper, Chip, Stack, Tabs, Tab, Dialog, DialogTitle, DialogContent, DialogActions, alpha
} from '@mui/material'
import UploadFileIcon   from '@mui/icons-material/UploadFile'
import LockIcon         from '@mui/icons-material/Lock'
import ShieldIcon       from '@mui/icons-material/Shield'
import SpeedIcon        from '@mui/icons-material/Speed'
import InsightsIcon     from '@mui/icons-material/Insights'
import TrendingUpIcon   from '@mui/icons-material/TrendingUp'
import CheckCircleIcon  from '@mui/icons-material/CheckCircle'
import PhoneAndroidIcon from '@mui/icons-material/PhoneAndroid'
import SecurityIcon     from '@mui/icons-material/Security'
import { apiClient }    from '../api/client'
import { useAppStore }  from '../store/appStore'

const steps = [
  {
    icon: <SpeedIcon sx={{ fontSize: 28, color: '#6366F1' }} />,
    num:  '01',
    title:'1-Click AA Sync or CAS Upload',
    desc: 'Connect instantly via Account Aggregator (Setu / Onemoney) with OTP, or upload your detailed CAS PDF.',
  },
  {
    icon: <LockIcon sx={{ fontSize: 28, color: '#4EDE93' }} />,
    num:  '02',
    title:'Institutional Memory Lock',
    desc: 'Processed securely in memory. Zero disk persistence ensures your financial privacy is fully compliant with SEBI regulations.',
  },
  {
    icon: <InsightsIcon sx={{ fontSize: 28, color: '#A855F7' }} />,
    num:  '03',
    title:'Real-time Analytics & Audit',
    desc: 'Get live NAV updates, XIRR, Alpha, rolling returns, and automated drift rebalancing strategies instantly.',
  },
]

const trust = [
  { icon: <ShieldIcon sx={{ fontSize: 16 }} />, label: 'Zero Data Retention' },
  { icon: <LockIcon   sx={{ fontSize: 16 }} />, label: 'In-memory Only' },
  { icon: <SpeedIcon  sx={{ fontSize: 16 }} />, label: 'SEBI CSCRF 2025' },
]

export default function Landing() {
  const [activeTab, setActiveTab] = useState(0) // 0: AA Sync, 1: PDF Upload
  const [phone,     setPhone]     = useState('+91 9876543210')
  const [pan,       setPan]       = useState('ABCDE1234F')
  const [showOtp,   setShowOtp]   = useState(false)
  const [otp,       setOtp]       = useState('123456')

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

  const handleConnectAA = () => {
    if (!phone || !pan) return setError('Please enter mobile number and PAN')
    setError(null)
    setShowOtp(true)
  }

  const handleVerifyOtp = async () => {
    setLoading(true); setError(null)
    try {
      const data = await apiClient.connectAA(phone, pan)
      setSession(data.session_id, data)
      setShowOtp(false)
      navigate('/dashboard')
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to connect via Account Aggregator.')
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyze = async () => {
    if (!file) return setError('Please upload a CAS PDF')
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
        background: 'radial-gradient(circle at 50% 0%, #1D2845 0%, #0B1326 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: { xs: 2, md: 4 },
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Background glow effects */}
      <Box sx={{ position: 'absolute', top: '-10%', left: '20%', width: 500, height: 500, background: 'radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%)', filter: 'blur(60px)', pointerEvents: 'none' }} />
      <Box sx={{ position: 'absolute', bottom: '-10%', right: '10%', width: 600, height: 600, background: 'radial-gradient(circle, rgba(78,222,147,0.1) 0%, transparent 70%)', filter: 'blur(60px)', pointerEvents: 'none' }} />

      {/* Hero */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0, 0, 0, 1] }}
        style={{ zIndex: 1 }}
      >
        <Box sx={{ textAlign: 'center', mb: 5 }}>
          {/* Logo badge */}
          <Box
            sx={{
              width: 68, height: 68, borderRadius: '22px', mx: 'auto', mb: 3,
              background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 12px 35px rgba(99,102,241,0.45)',
              border: '1px solid rgba(255,255,255,0.2)',
            }}
          >
            <TrendingUpIcon sx={{ fontSize: 36, color: '#fff' }} />
          </Box>

          <Typography
            variant="h1"
            sx={{
              background: 'linear-gradient(135deg, #FFFFFF 0%, #E2E8F0 40%, #6366F1 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              mb: 2,
              lineHeight: 1.15,
            }}
          >
            Know your portfolio.<br />Beat the benchmark.
          </Typography>

          <Typography variant="body1" sx={{ color: '#94A3B8', maxWidth: 540, mx: 'auto', mb: 3.5, lineHeight: 1.7, fontSize: '1.05rem' }}>
            Upload your CAMS / KFintech CAS or connect securely via Account Aggregator to get institutional-grade analytics.
            <strong style={{ color: '#F8FAFC' }}> Instantly. Privately.</strong>
          </Typography>

          <Stack direction="row" spacing={1.5} justifyContent="center" flexWrap="wrap" gap={1.5}>
            {trust.map((t) => (
              <Chip
                key={t.label}
                icon={t.icon as any}
                label={t.label}
                size="small"
                sx={{
                  background: 'rgba(99, 102, 241, 0.1)',
                  border: '1px solid rgba(99, 102, 241, 0.25)',
                  fontWeight: 700,
                  fontSize: '0.75rem',
                  color: '#818CF8',
                  px: 1, py: 1.5,
                  borderRadius: '10px',
                  '& .MuiChip-icon': { color: '#818CF8' },
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
        style={{ width: '100%', maxWidth: 500, zIndex: 1 }}
      >
        <Paper
          className="glass"
          sx={{
            p: 4.5, borderRadius: '32px',
            border: '1px solid rgba(99, 102, 241, 0.3)',
            background: 'rgba(19, 27, 46, 0.75)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), 0 0 40px rgba(99, 102, 241, 0.15)',
          }}
        >
          <Typography variant="h5" sx={{ mb: 1, fontWeight: 800, textAlign: 'center', color: '#F8FAFC' }}>
            Import Your Mutual Funds
          </Typography>
          <Typography variant="body2" sx={{ mb: 3.5, color: '#94A3B8', textAlign: 'center', fontSize: '0.9rem' }}>
            Connect instantly via open banking or upload a CAS statement.
          </Typography>

          <Tabs
            value={activeTab}
            onChange={(_, val) => setActiveTab(val)}
            centered
            sx={{
              mb: 3.5,
              background: 'rgba(255, 255, 255, 0.04)',
              borderRadius: '20px',
              p: 0.75,
              '& .MuiTab-root': { fontWeight: 700, textTransform: 'none', fontSize: '0.9rem', color: '#94A3B8', borderRadius: '16px', py: 1.25, minHeight: 42 },
              '& .Mui-selected': { color: '#FFFFFF !important', background: 'linear-gradient(135deg, #6366F1, #4F46E5)', boxShadow: '0 4px 15px rgba(99,102,241,0.4)' },
            }}
          >
            <Tab icon={<SpeedIcon sx={{ mb: 0.5, fontSize: 18 }} />} label="⚡ 1-Click AA Sync" sx={{ flex: 1 }} />
            <Tab icon={<UploadFileIcon sx={{ mb: 0.5, fontSize: 18 }} />} label="📁 CAS PDF Upload" sx={{ flex: 1 }} />
          </Tabs>

          <AnimatePresence mode="wait">
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
              >
                <Alert severity="error" sx={{ mb: 3, borderRadius: '16px' }}>{error}</Alert>
              </motion.div>
            )}
          </AnimatePresence>

          {activeTab === 0 ? (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              <TextField
                fullWidth
                label="Registered Phone Number"
                placeholder="+91 9876543210"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                sx={{
                  mb: 2.5,
                  '& .MuiOutlinedInput-root': { borderRadius: '16px', background: 'rgba(255,255,255,0.03)' },
                }}
                InputProps={{
                  startAdornment: <PhoneAndroidIcon sx={{ mr: 1.5, color: '#6366F1' }} />,
                }}
              />
              <TextField
                fullWidth
                label="PAN Number"
                placeholder="ABCDE1234F"
                value={pan}
                onChange={(e) => setPan(e.target.value.toUpperCase())}
                sx={{
                  mb: 3.5,
                  '& .MuiOutlinedInput-root': { borderRadius: '16px', background: 'rgba(255,255,255,0.03)' },
                }}
                InputProps={{
                  startAdornment: <SecurityIcon sx={{ mr: 1.5, color: '#6366F1' }} />,
                }}
              />
              <Button
                fullWidth
                variant="contained"
                size="large"
                onClick={handleConnectAA}
                disabled={loading}
                sx={{
                  py: 1.75,
                  borderRadius: '16px',
                  fontSize: '1.05rem', fontWeight: 800,
                  background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
                  boxShadow: '0 8px 25px rgba(16,185,129,0.45)',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #059669 0%, #047857 100%)',
                    boxShadow: '0 10px 30px rgba(16,185,129,0.6)',
                  },
                }}
              >
                {loading ? <><CircularProgress size={20} sx={{ color: '#fff', mr: 1.5 }} /> Connecting AA…</> : '⚡ Connect via Account Aggregator'}
              </Button>
              <Typography variant="caption" display="block" textAlign="center" sx={{ mt: 2.5, color: '#64748B', fontWeight: 600 }}>
                Secure OTP verification powered by Setu / Onemoney AA Framework.
              </Typography>
            </motion.div>
          ) : (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              {/* Dropzone */}
              <Box
                {...getRootProps()}
                sx={{
                  border: `2px dashed ${isDragActive ? '#6366F1' : file ? '#4EDE93' : 'rgba(255, 255, 255, 0.2)'}`,
                  borderRadius: '20px',
                  p: 3.5,
                  textAlign: 'center',
                  cursor: 'pointer',
                  background: isDragActive ? 'rgba(99, 102, 241, 0.1)' : file ? 'rgba(78, 222, 147, 0.08)' : 'rgba(255, 255, 255, 0.02)',
                  transition: 'all 200ms ease',
                  mb: 2.5,
                  '&:hover': { borderColor: '#6366F1', background: 'rgba(99, 102, 241, 0.05)' },
                }}
              >
                <input {...getInputProps()} />
                {file ? (
                  <Box>
                    <CheckCircleIcon sx={{ fontSize: 36, color: '#4EDE93', mb: 1.5 }} />
                    <Typography variant="body1" fontWeight={700} sx={{ color: '#4EDE93', mb: 0.5 }}>
                      {file.name}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#94A3B8' }}>
                      {(file.size / 1024).toFixed(0)} KB · Click to replace file
                    </Typography>
                  </Box>
                ) : (
                  <Box>
                    <UploadFileIcon sx={{ fontSize: 40, color: '#6366F1', mb: 1.5 }} />
                    <Typography variant="body1" fontWeight={700} sx={{ color: '#F8FAFC', mb: 0.5 }}>
                      {isDragActive ? 'Drop your CAS here…' : 'Drag & drop your CAS PDF'}
                    </Typography>
                    <Typography variant="caption" sx={{ color: '#64748B' }}>
                      or click to browse from your device · PDF statement only
                    </Typography>
                  </Box>
                )}
              </Box>

              {/* Password */}
              <TextField
                fullWidth
                type="password"
                label="PAN Password (Optional for Testing)"
                placeholder="ABCDE1234F (Default: Test Password)"
                value={password}
                onChange={(e) => setPassword(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                sx={{
                  mb: 3.5,
                  '& .MuiOutlinedInput-root': { borderRadius: '16px', background: 'rgba(255,255,255,0.03)' },
                }}
                InputProps={{
                  startAdornment: <LockIcon sx={{ mr: 1.5, color: '#6366F1' }} />,
                }}
              />

              <Button
                fullWidth
                variant="contained"
                size="large"
                onClick={handleAnalyze}
                disabled={loading}
                sx={{
                  py: 1.75,
                  borderRadius: '16px',
                  fontSize: '1.05rem', fontWeight: 800,
                  background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
                  boxShadow: '0 8px 25px rgba(99,102,241,0.45)',
                  '&:hover': {
                    background: 'linear-gradient(135deg, #4F46E5 0%, #6366F1 100%)',
                    boxShadow: '0 10px 30px rgba(99,102,241,0.6)',
                  },
                }}
              >
                {loading
                  ? <><CircularProgress size={20} sx={{ color: '#fff', mr: 1.5 }} /> Analyzing Portfolio…</>
                  : '🔍  Analyze Portfolio'}
              </Button>

              <Typography variant="caption" display="block" textAlign="center" sx={{ mt: 2.5, color: '#64748B', fontWeight: 600 }}>
                Your file is never uploaded to any server. All processing is in-memory.
              </Typography>
            </motion.div>
          )}

          {/* OTP Modal */}
          <Dialog
            open={showOtp}
            onClose={() => !loading && setShowOtp(false)}
            PaperProps={{
              className: 'glass',
              sx: {
                borderRadius: '28px',
                p: 3,
                maxWidth: 420,
                background: '#131B2E',
                border: '1px solid rgba(99, 102, 241, 0.4)',
                boxShadow: '0 25px 50px -12px rgba(0,0,0,0.8)',
              },
            }}
          >
            <DialogTitle sx={{ fontWeight: 800, color: '#F8FAFC', textAlign: 'center', pb: 1, fontSize: '1.35rem' }}>
              🔐 Account Aggregator OTP
            </DialogTitle>
            <DialogContent sx={{ textAlign: 'center', pt: 1 }}>
              <Alert severity="info" sx={{ mb: 3, borderRadius: '18px', textAlign: 'left', bgcolor: 'rgba(99, 102, 241, 0.15)', border: '1px solid rgba(99, 102, 241, 0.3)' }}>
                <Typography variant="body2" fontWeight={800} sx={{ color: '#818CF8', mb: 0.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                  <span>ℹ️</span> Local Sandbox Simulation Active
                </Typography>
                <Typography variant="body2" sx={{ color: '#F8FAFC', lineHeight: 1.5, mb: 1.5, fontSize: '0.85rem' }}>
                  No physical SMS will be delivered to <strong style={{ color: '#4EDE93' }}>{phone}</strong> while running in local developer mode.
                </Typography>
                <Box sx={{ p: 1.5, borderRadius: '12px', background: 'rgba(16, 185, 129, 0.2)', border: '1px dashed rgba(16, 185, 129, 0.4)' }}>
                  <Typography variant="caption" sx={{ color: '#4EDE93', fontWeight: 800, fontSize: '0.85rem', display: 'block', textAlign: 'center' }}>
                    💡 Click "Authorize & Import" below using universal sandbox code <strong style={{ color: '#FFFFFF', fontSize: '1rem', padding: '2px 6px', background: '#10B981', borderRadius: '6px' }}>123456</strong>
                  </Typography>
                </Box>
              </Alert>
              <TextField
                fullWidth
                autoFocus
                label="6-Digit Verification Code"
                placeholder="123456"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                inputProps={{ maxLength: 6, style: { textAlign: 'center', fontSize: '1.5rem', letterSpacing: '0.35em', fontWeight: 800, color: '#F8FAFC' } }}
                sx={{
                  mb: 1,
                  '& .MuiOutlinedInput-root': { borderRadius: '16px', background: 'rgba(255,255,255,0.05)' },
                }}
              />
            </DialogContent>
            <DialogActions sx={{ justifyContent: 'center', pb: 1, pt: 2, gap: 1.5 }}>
              <Button variant="outlined" onClick={() => setShowOtp(false)} disabled={loading} sx={{ borderRadius: '14px', px: 3.5, py: 1.25, color: '#94A3B8', borderColor: 'rgba(255,255,255,0.2)' }}>
                Cancel
              </Button>
              <Button variant="contained" onClick={handleVerifyOtp} disabled={loading || otp.length < 6} sx={{ borderRadius: '14px', px: 4, py: 1.25, bgcolor: '#10B981', '&:hover': { bgcolor: '#059669' }, boxShadow: '0 6px 20px rgba(16,185,129,0.4)' }}>
                {loading ? <CircularProgress size={20} sx={{ color: '#fff' }} /> : 'Authorize & Import'}
              </Button>
            </DialogActions>
          </Dialog>
        </Paper>
      </motion.div>

      {/* Step cards */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
          gap: 2.5,
          maxWidth: 960,
          width: '100%',
          mt: 7,
          zIndex: 1,
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
              className="glass"
              sx={{
                p: 3.5, borderRadius: '24px', height: '100%',
                background: 'rgba(19, 27, 46, 0.4)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                transition: 'all 300ms ease',
                '&:hover': {
                  transform: 'translateY(-6px)',
                  borderColor: alpha('#6366F1', 0.4),
                  boxShadow: '0 12px 30px rgba(99,102,241,0.2)',
                },
              }}
            >
              <Box
                sx={{
                  width: 48, height: 48, borderRadius: '14px',
                  background: 'rgba(99, 102, 241, 0.15)', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', mb: 2.5,
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                }}
              >
                {s.icon}
              </Box>
              <Typography variant="overline" display="block" sx={{ mb: 0.75, color: '#818CF8', fontWeight: 800, fontSize: '0.75rem' }}>
                Step {s.num}
              </Typography>
              <Typography variant="subtitle1" sx={{ mb: 1.25, fontWeight: 700, color: '#F8FAFC', fontSize: '1.1rem' }}>
                {s.title}
              </Typography>
              <Typography variant="body2" sx={{ color: '#94A3B8', lineHeight: 1.7, fontSize: '0.9rem' }}>
                {s.desc}
              </Typography>
            </Paper>
          </motion.div>
        ))}
      </Box>

      {/* Footer */}
      <Typography variant="caption" display="block" textAlign="center" sx={{ mt: 7, color: '#64748B', zIndex: 1, fontWeight: 600 }}>
        FolioPulse v8.0 · SEBI CSCRF 2025 · Zero Data Retention Architecture · Not financial advice
      </Typography>
    </Box>
  )
}
