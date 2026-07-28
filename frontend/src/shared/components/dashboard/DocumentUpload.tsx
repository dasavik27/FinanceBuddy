import { useState, useCallback, useEffect } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import { Box, Typography, Button, TextField, Alert, CircularProgress, Paper, Chip, Stack } from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import LockIcon from '@mui/icons-material/Lock'
import CheckCircleIcon from '@mui/icons-material/CheckCircle'
import ShieldIcon from '@mui/icons-material/Shield'
import HistoryIcon from '@mui/icons-material/History'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import { apiClient } from '../../api/client'
import api from '../../api/client'
import { useAppStore } from '../../store/appStore'

interface DocumentUploadProps {
  title: string
  subtitle: string
  dropText: string
  dropSubText: string
  uploadType: 'mutual_funds' | 'tax_expert'
}

export default function DocumentUpload({ title, subtitle, dropText, dropSubText, uploadType }: DocumentUploadProps) {
  const [file, setFile] = useState<File | null>(null)
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [history, setHistory] = useState<any[]>([])
  const { setSession, setSessionById, pan } = useAppStore()

  const fetchHistory = useCallback(() => {
    if (!pan) return
    apiClient.getHistory(uploadType)
      .then((res) => {
        if (res?.history) setHistory(res.history)
      })
      .catch(console.error)
  }, [pan, uploadType])

  useEffect(() => {
    fetchHistory()
  }, [fetchHistory])

  const onDrop = useCallback((accepted: File[]) => {
    if (accepted[0]) {
      setFile(accepted[0])
      setError(null)
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  })

  const handleAnalyze = async () => {
    if (!file) return setError('Please upload a valid statement PDF.')
    setLoading(true)
    setError(null)
    try {
      const data = await apiClient.parseFile(file, password, uploadType)
      setSession(data.session_id, uploadType, data)
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? 'Failed to parse document. Check the file and password.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: { xs: 'minmax(0, 1fr)', lg: history.length > 0 ? 'minmax(0, 1fr) minmax(0, 1fr)' : 'minmax(0, 1fr)' }, gap: 4, width: '100%', maxWidth: history.length > 0 ? 1000 : 500, mx: 'auto', py: 8 }}>
      <Paper
        className="glass"
        sx={{
          p: { xs: 3, md: 5 }, borderRadius: '32px',
          border: '1px solid rgba(99, 102, 241, 0.3)',
          background: 'rgba(19, 27, 46, 0.75)',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.75), 0 0 40px rgba(99, 102, 241, 0.15)',
          width: '100%',
          display: 'flex', flexDirection: 'column', justifyContent: 'center'
        }}
      >
        <Typography variant="h5" sx={{ mb: 1, fontWeight: 800, textAlign: 'center', color: '#F8FAFC' }}>
          {title}
        </Typography>
        <Typography variant="body2" sx={{ mb: 3.5, color: '#94A3B8', textAlign: 'center', fontSize: '0.9rem' }}>
          {subtitle}
        </Typography>

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

        <Box
          {...getRootProps()}
          component={motion.div as any}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.98 }}
          sx={{
            border: `2px dashed ${isDragActive ? '#6366F1' : file ? '#4EDE93' : 'rgba(255, 255, 255, 0.15)'}`,
            borderRadius: '24px',
            p: { xs: 3, md: 5 },
            textAlign: 'center',
            cursor: 'pointer',
            background: isDragActive ? 'rgba(99, 102, 241, 0.1)' : file ? 'rgba(78, 222, 147, 0.05)' : 'rgba(255, 255, 255, 0.02)',
            transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
            mb: 3,
            position: 'relative',
            overflow: 'hidden',
            '&:hover': { borderColor: file ? '#4EDE93' : '#6366F1', background: file ? 'rgba(78, 222, 147, 0.08)' : 'rgba(99, 102, 241, 0.05)' },
          }}
        >
          <input {...getInputProps()} />
          <AnimatePresence mode="wait">
            {file ? (
              <motion.div
                key="file"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                style={{ width: '100%', overflow: 'hidden' }}
              >
                <Box sx={{ width: 64, height: 64, mx: 'auto', mb: 2, borderRadius: '50%', background: 'rgba(78, 222, 147, 0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <CheckCircleIcon sx={{ fontSize: 32, color: '#4EDE93' }} />
                </Box>
                <Typography variant="body1" fontWeight={800} sx={{ color: '#4EDE93', mb: 0.5, fontSize: '1.1rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', width: '100%', display: 'block', px: 2, boxSizing: 'border-box' }}>
                  {file.name}
                </Typography>
                <Typography variant="caption" sx={{ color: '#94A3B8', fontWeight: 600 }}>
                  {(file.size / 1024).toFixed(0)} KB · Click to replace file
                </Typography>
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
              >
                <motion.div
                  animate={{ y: [0, -8, 0] }}
                  transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}
                >
                  <Box sx={{ width: 72, height: 72, mx: 'auto', mb: 2.5, borderRadius: '20px', background: 'linear-gradient(135deg, rgba(99,102,241,0.2) 0%, rgba(79,70,229,0.2) 100%)', border: '1px solid rgba(99,102,241,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 8px 32px rgba(99,102,241,0.2)' }}>
                    <UploadFileIcon sx={{ fontSize: 36, color: '#818CF8' }} />
                  </Box>
                </motion.div>
                <Typography variant="body1" fontWeight={800} sx={{ color: '#F8FAFC', mb: 1, fontSize: '1.1rem' }}>
                  {isDragActive ? 'Drop file to parse' : dropText}
                </Typography>
                <Typography variant="body2" sx={{ color: '#94A3B8', fontWeight: 500, maxWidth: 280, mx: 'auto' }}>
                  {dropSubText}
                </Typography>
              </motion.div>
            )}
          </AnimatePresence>
        </Box>

        <AnimatePresence>
          {file && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.3 }}
            >
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5, mb: 3 }}>
                <TextField
                  fullWidth
                  type="password"
                  label="Document Password (Optional)"
                  placeholder="ABCDE1234F"
                  value={password}
                  onChange={(e) => setPassword(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                  sx={{
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
                    py: 1.8,
                    borderRadius: '16px',
                    fontSize: '1.1rem', fontWeight: 800,
                    background: 'linear-gradient(135deg, #6366F1 0%, #4F46E5 100%)',
                    boxShadow: '0 8px 25px rgba(99,102,241,0.45)',
                    textTransform: 'none',
                    position: 'relative',
                    overflow: 'hidden',
                    '&:hover': {
                      background: 'linear-gradient(135deg, #4F46E5 0%, #4338CA 100%)',
                      boxShadow: '0 12px 35px rgba(99,102,241,0.6)',
                    },
                  }}
                >
                  {loading
                    ? <><CircularProgress size={22} sx={{ color: '#fff', mr: 1.5 }} /> Processing...</>
                    : 'Initialize Analytics Engine'}
                </Button>
              </Box>
            </motion.div>
          )}
        </AnimatePresence>

        <Typography variant="caption" display="block" textAlign="center" sx={{ color: '#64748B', fontWeight: 600 }}>
          <ShieldIcon sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.5, color: '#4EDE93' }} />
          Your file is never uploaded to any server. 100% in-memory processing.
        </Typography>
      </Paper>

      {history.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          style={{ height: '100%' }}
        >
          <Paper
            className="glass"
            sx={{
              p: { xs: 3, md: 4.5 }, borderRadius: '32px',
              border: '1px solid rgba(99, 102, 241, 0.2)',
              background: 'rgba(19, 27, 46, 0.5)',
              height: '100%',
              minWidth: 0,
              display: 'flex', flexDirection: 'column'
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
              <Typography variant="subtitle2" sx={{ color: '#94A3B8', display: 'flex', alignItems: 'center', gap: 1, fontWeight: 700, letterSpacing: 1 }}>
                <HistoryIcon fontSize="small" sx={{ color: '#6366F1' }} /> PORTFOLIO HISTORY
              </Typography>
              <Chip label={`${history.length} Saved`} size="small" sx={{ background: 'rgba(255,255,255,0.05)', color: '#94A3B8', fontSize: '0.7rem', fontWeight: 700 }} />
            </Box>

            <Stack spacing={2} sx={{ flex: 1, justifyContent: 'center' }}>
              {history.slice(0, 3).map((h, i) => (
                <motion.div
                  key={h.session_id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.2 + i * 0.1 }}
                >
                  <Box
                    onClick={() => {
                      setSessionById(h.session_id, uploadType)
                    }}
                    sx={{
                      display: 'flex', alignItems: 'center', p: 2.5,
                      background: 'linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '20px',
                      cursor: 'pointer',
                      transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                      '&:hover': {
                        background: 'linear-gradient(180deg, rgba(99, 102, 241, 0.1) 0%, rgba(79, 70, 229, 0.05) 100%)',
                        borderColor: 'rgba(99, 102, 241, 0.4)',
                        transform: 'translateY(-2px)',
                        boxShadow: '0 8px 24px rgba(99,102,241,0.15)',
                        '& .chevron': { color: '#818CF8', transform: 'translateX(4px)' }
                      }
                    }}
                  >
                    <Box sx={{ flex: 1 }}>
                      <Typography sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '1rem', mb: 1 }}>
                        {new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(h.created_at + 'Z'))}
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap' }}>
                        <Typography variant="caption" sx={{ color: '#E2E8F0', fontWeight: 700, background: 'rgba(255,255,255,0.1)', px: 1, py: 0.5, borderRadius: '6px' }}>
                          {h.num_funds} Funds
                        </Typography>
                        <Typography variant="caption" sx={{ color: '#4EDE93', fontWeight: 800, background: 'rgba(78, 222, 147, 0.1)', px: 1, py: 0.5, borderRadius: '6px', letterSpacing: 0.5 }}>
                          {new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(h.total_value)}
                        </Typography>
                      </Box>
                    </Box>
                    <ChevronRightIcon className="chevron" sx={{ color: '#475569', transition: 'all 0.3s ease' }} />
                  </Box>
                </motion.div>
              ))}
            </Stack>
          </Paper>
        </motion.div>
      )}
    </Box>
  )
}
