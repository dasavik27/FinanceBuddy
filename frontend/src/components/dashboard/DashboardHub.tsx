import { Box, Typography, Paper, alpha } from '@mui/material'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import TimelineIcon from '@mui/icons-material/Timeline'
import AccountBalanceIcon from '@mui/icons-material/AccountBalance'
import ShieldIcon from '@mui/icons-material/Shield'

const pillars = [
  {
    icon: <TimelineIcon sx={{ fontSize: 32, color: '#3B82F6' }} />,
    title: 'Indian Stocks',
    desc: 'Track your equity portfolio, analyze individual stocks in depth, and access real-time market data instantly.',
    color: '#3B82F6',
    glow: 'rgba(59, 130, 246, 0.15)',
    path: '/dashboard/indian-stocks'
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
]

export default function DashboardHub() {
  const navigate = useNavigate()

  return (
    <Box sx={{ width: '100%', maxWidth: 1100, mx: 'auto', mt: 4 }}>
      <Typography variant="h4" sx={{ color: '#F8FAFC', fontWeight: 900, mb: 1, textAlign: 'center' }}>
        Select Your Dashboard
      </Typography>
      <Typography variant="body1" sx={{ color: '#94A3B8', mb: 6, textAlign: 'center', maxWidth: 500, mx: 'auto' }}>
        Choose a module below to begin analyzing your portfolio and tracking your wealth journey.
      </Typography>
      
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(3, 1fr)' },
          gap: 3,
        }}
      >
        {pillars.map((pillar, i) => (
          <motion.div
            key={pillar.title}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 + i * 0.15, ease: [0.16, 1, 0.3, 1] }}
          >
            <Paper
              className="glass"
              onClick={() => navigate(pillar.path)}
              sx={{
                p: 4, borderRadius: '32px', height: '100%',
                background: 'rgba(15, 23, 42, 0.4)',
                border: '1px solid rgba(255, 255, 255, 0.05)',
                position: 'relative',
                overflow: 'hidden',
                cursor: 'pointer',
                transition: 'all 400ms cubic-bezier(0.16, 1, 0.3, 1)',
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
              <Box sx={{ position: 'absolute', top: 0, right: 0, width: 150, height: 150, background: `radial-gradient(circle at top right, ${pillar.glow} 0%, transparent 70%)`, pointerEvents: 'none' }} />

              <Box
                className="icon-wrapper"
                sx={{
                  width: 64, height: 64, borderRadius: '20px',
                  background: alpha(pillar.color, 0.1), display: 'flex',
                  alignItems: 'center', justifyContent: 'center', mb: 3,
                  border: `1px solid ${alpha(pillar.color, 0.2)}`,
                  transition: 'all 400ms cubic-bezier(0.16, 1, 0.3, 1)',
                }}
              >
                {pillar.icon}
              </Box>
              
              <Typography variant="h5" sx={{ mb: 1.5, fontWeight: 800, color: '#F8FAFC' }}>
                {pillar.title}
              </Typography>
              
              <Typography variant="body1" sx={{ color: '#94A3B8', lineHeight: 1.7, fontSize: '1rem' }}>
                {pillar.desc}
              </Typography>
            </Paper>
          </motion.div>
        ))}
      </Box>
    </Box>
  )
}
