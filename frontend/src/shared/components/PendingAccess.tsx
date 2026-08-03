import { Box, Typography, Button, Paper, alpha } from '@mui/material'
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty'
import LogoutIcon from '@mui/icons-material/Logout'
import { useAppStore } from '../store/appStore'

export default function PendingAccess() {
  const email = useAppStore((s) => s.email)
  const logout = useAppStore((s) => s.logout)

  return (
    <Box
      sx={{
        minHeight: '100vh',
        background: 'radial-gradient(circle at 50% 0%, #0F172A 0%, #020617 100%)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 3,
      }}
    >
      <Paper
        elevation={0}
        sx={{
          maxWidth: 480,
          width: '100%',
          p: 4,
          borderRadius: '24px',
          background: alpha('#0F172A', 0.8),
          border: '1px solid rgba(255,255,255,0.08)',
          textAlign: 'center',
        }}
      >
        <Box
          sx={{
            width: 64,
            height: 64,
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #6366F1 0%, #38BDF8 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mx: 'auto',
            mb: 3,
          }}
        >
          <HourglassEmptyIcon sx={{ color: '#fff', fontSize: 32 }} />
        </Box>

        <Typography variant="h5" sx={{ fontWeight: 800, color: '#F8FAFC', mb: 1 }}>
          Access pending
        </Typography>

        <Typography sx={{ color: '#94A3B8', mb: 3, lineHeight: 1.6 }}>
          Your account has been created, but an administrator still needs to approve your
          access request. We will notify you at{' '}
          <Box component="span" sx={{ color: '#38BDF8', fontWeight: 600 }}>
            {email || 'your email'}
          </Box>{' '}
          once you are approved.
        </Typography>

        <Button
          variant="outlined"
          startIcon={<LogoutIcon />}
          onClick={() => logout()}
          sx={{
            color: '#94A3B8',
            borderColor: 'rgba(255,255,255,0.12)',
            '&:hover': { borderColor: 'rgba(255,255,255,0.24)', bgcolor: alpha('#fff', 0.04) },
          }}
        >
          Sign out
        </Button>
      </Paper>
    </Box>
  )
}
