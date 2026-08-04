import { AppBar, Toolbar, IconButton, Box, Stack, Chip, Typography, Tooltip, Divider, alpha } from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import SyncIcon from '@mui/icons-material/Sync'
import SecurityIcon from '@mui/icons-material/Security'
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings'
import LogoutIcon from '@mui/icons-material/Logout'
import PersonOutlineIcon from '@mui/icons-material/PersonOutline'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import { useNavigate, useLocation } from 'react-router-dom'
import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useLastSynced, useRefreshTrigger, usePan, useLogout, useIsAuthenticated, useAppStore, useUserRole } from '../../store/appStore'
import { apiClient } from '../../api/client'

interface TopbarProps {
  onMenuClick: () => void
  isPartial: boolean
}

export function Topbar({ onMenuClick, isPartial }: TopbarProps) {
  const isFetching = useIsFetching()
  const queryClient = useQueryClient()
  const pan = usePan()
  const email = useAppStore((s) => s.email)
  const displayName = useAppStore((s) => s.displayName)
  const role = useUserRole()
  const isAuthenticated = useIsAuthenticated()
  const [isSyncing, setIsSyncing] = useState(false)
  const logout = useLogout()

  const accountLabel = displayName || pan || email || 'Account'
  const avatarInitials = (displayName || pan || email || '?').substring(0, 2).toUpperCase()
  const navigate = useNavigate()
  const location = useLocation()
  const lastSynced = useLastSynced()
  const triggerRefresh = useRefreshTrigger()

  const isEquity = location.pathname.startsWith('/equity')
  const isMutualFunds = location.pathname.startsWith('/mutual-funds')

  const mfSessionId = useAppStore((s) => s.mfSessionId)
  const equitySessionId = useAppStore((s) => s.equitySessionId)
  const currentSid = isEquity ? equitySessionId : isMutualFunds ? mfSessionId : null

  const [profileAnchor, setProfileAnchor] = useState<null | HTMLElement>(null)

  const handleRefresh = async (e?: React.MouseEvent) => {
    if (e) e.stopPropagation()
    if (isSyncing) return
    setIsSyncing(true)
    try {
      if (isEquity && currentSid) {
        await apiClient.syncEquity(currentSid)
      } else if (isMutualFunds && currentSid) {
        await apiClient.syncPortfolio(currentSid)
      }
      triggerRefresh()
      await queryClient.invalidateQueries()
    } catch (e) {
      console.error('Sync failed', e)
    } finally {
      setIsSyncing(false)
    }
  }

  const getSyncedText = () => {
    const timeStr = new Date(lastSynced).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    const diff = Math.floor((Date.now() - lastSynced) / 60000)
    if (diff < 1) return `Synced at ${timeStr}`
    if (diff < 60) return `Synced at ${timeStr} (${diff}m ago)`
    const hours = Math.floor(diff / 60)
    return `Synced at ${timeStr} (${hours}h ago)`
  }

  const isSyncActive = isFetching > 0 || isSyncing

  return (
    <AppBar
      position="sticky"
      elevation={0}
      sx={{
        background: (theme) => alpha(theme.palette.background.default, 0.8),
        backdropFilter: 'blur(20px)',
        borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
        zIndex: (theme) => theme.zIndex.drawer + 1
      }}
    >
      <Toolbar variant="dense" sx={{ minHeight: 64, px: 4 }}>
        <IconButton
          edge="start"
          onClick={onMenuClick}
          sx={{ mr: 2, color: 'text.secondary', display: { md: 'none' } }}
        >
          <MenuIcon />
        </IconButton>

        <Box sx={{ flex: 1 }} />

        <Stack direction="row" spacing={2} alignItems="center">
          {isPartial && (
            <Tooltip title="XIRR data might be incomplete due to partial CAS upload">
              <Chip
                size="small"
                icon={<WarningAmberIcon sx={{ fontSize: 14 }} />}
                label="PARTIAL DATA"
                sx={{
                  fontWeight: 800,
                  fontSize: 10,
                  height: 24,
                  bgcolor: alpha('#EAB308', 0.1),
                  color: '#FCD34D',
                  borderColor: alpha('#EAB308', 0.2),
                  '& .MuiChip-icon': { color: '#FCD34D' }
                }}
              />
            </Tooltip>
          )}

          <Divider orientation="vertical" flexItem sx={{ height: 24, my: 'auto', borderColor: 'rgba(255,255,255,0.1)' }} />

          {/* Universal Live Sync Status Widget - For Mutual Funds & Equity */}
          {(isEquity || isMutualFunds) && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 1.5,
                p: '4px 6px 4px 14px',
                borderRadius: '100px',
                background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.7) 100%)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                boxShadow: '0 4px 20px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
                transition: 'all 0.3s ease',
                '&:hover': {
                  borderColor: 'rgba(99, 102, 241, 0.3)',
                  boxShadow: '0 4px 20px rgba(99, 102, 241, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.05)',
                }
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
                <Box
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    bgcolor: isSyncActive ? '#38BDF8' : '#10B981',
                    boxShadow: isSyncActive ? '0 0 12px #38BDF8' : '0 0 12px #10B981',
                    animation: isSyncActive ? 'pulse 1.5s infinite' : 'none'
                  }}
                />
                <Box sx={{ display: { xs: 'none', sm: 'block' }, textAlign: 'left' }}>
                  <Typography
                    variant="caption"
                    sx={{
                      display: 'block',
                      fontSize: '0.625rem',
                      fontWeight: 800,
                      color: '#94A3B8',
                      letterSpacing: '0.1em',
                      lineHeight: 1,
                      mb: 0.25,
                    }}
                  >
                    {isEquity ? 'LIVE EQUITY PRICES' : 'AMFI NAV STATUS'}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: '#F8FAFC',
                      lineHeight: 1,
                    }}
                  >
                    {isSyncActive ? 'Syncing Live Data...' : getSyncedText()}
                  </Typography>
                </Box>
              </Box>

              <Tooltip
                title={
                  isEquity
                    ? (currentSid ? 'Fetch live NSE quotes and refresh stock valuations' : 'Refresh live market quotes and analyzer data')
                    : (currentSid ? 'Fetch latest AMFI NAVs and refresh portfolio valuations' : 'Refresh live AMFI NAVs and fund data')
                }
              >
                <span>
                  <IconButton
                    size="small"
                    onClick={handleRefresh}
                    disabled={isSyncActive}
                    sx={{
                      width: 28,
                      height: 28,
                      color: isSyncActive ? '#38BDF8' : '#94A3B8',
                      bgcolor: isSyncActive ? alpha('#38BDF8', 0.1) : alpha('#334155', 0.5),
                      border: '1px solid',
                      borderColor: isSyncActive ? alpha('#38BDF8', 0.3) : 'transparent',
                      transition: 'all 0.2s ease',
                      '&:hover': {
                        color: '#F8FAFC',
                        bgcolor: alpha('#6366F1', 0.2),
                        borderColor: alpha('#6366F1', 0.4),
                        transform: 'rotate(30deg)'
                      }
                    }}
                  >
                    <SyncIcon
                      sx={{
                        fontSize: 16,
                        animation: isSyncActive ? 'spin 1s linear infinite' : 'none'
                      }}
                    />
                    <style>{`
                      @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
                      @keyframes pulse { 0% { transform: scale(0.95); opacity: 0.8; } 50% { transform: scale(1.2); opacity: 1; } 100% { transform: scale(0.95); opacity: 0.8; } }
                    `}</style>
                  </IconButton>
                </span>
              </Tooltip>
            </Box>
          )}

          {isAuthenticated && (
            <>
              <Box 
                onClick={(e) => setProfileAnchor(e.currentTarget)}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.8) 0%, rgba(15, 23, 42, 0.8) 100%)',
                  borderRadius: '100px',
                  p: 0.5,
                  pr: 1.5,
                  cursor: 'pointer',
                  border: '1px solid rgba(255,255,255,0.1)',
                  transition: 'all 0.3s ease',
                  '&:hover': {
                    borderColor: 'rgba(99,102,241,0.4)',
                    background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(30, 41, 59, 0.8) 100%)'
                  }
                }}
              >
                <Box sx={{ width: 28, height: 28, borderRadius: '50%', bgcolor: alpha('#6366F1', 0.2), color: '#818CF8', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.7rem', fontWeight: 800, border: '1px solid rgba(99,102,241,0.3)' }}>
                  {avatarInitials}
                </Box>
                <Typography variant="body2" sx={{ color: '#F8FAFC', fontWeight: 800, fontSize: '0.75rem', letterSpacing: 0.5 }}>{accountLabel}</Typography>
              </Box>

              <Menu
                anchorEl={profileAnchor}
                open={Boolean(profileAnchor)}
                onClose={() => setProfileAnchor(null)}
                PaperProps={{
                  sx: {
                    background: alpha('#0F172A', 0.95),
                    backdropFilter: 'blur(20px)',
                    border: '1px solid',
                    borderColor: alpha('#334155', 0.8),
                    boxShadow: '0 20px 50px rgba(0,0,0,0.7)',
                    borderRadius: '16px',
                    mt: 1,
                    minWidth: 220,
                    p: 1,
                    '& .MuiMenuItem-root': {
                      borderRadius: '10px',
                      px: 2,
                      py: 1.25,
                      mb: 0.5,
                      transition: 'all 0.2s',
                      '&:hover': { bgcolor: alpha('#1E293B', 0.8) }
                    },
                    '& .Mui-selected': { 
                      background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.15), rgba(56, 189, 248, 0.15)) !important',
                      borderColor: alpha('#6366F1', 0.5),
                      border: '1px solid',
                    }
                  }
                }}
                transformOrigin={{ horizontal: 'right', vertical: 'top' }}
                anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
              >
                <Box sx={{ px: 1, py: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                  <Box sx={{ width: 36, height: 36, borderRadius: '10px', background: 'linear-gradient(135deg, #6366F1 0%, #38BDF8 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 800, fontSize: '0.8rem', boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)' }}>
                    {avatarInitials}
                  </Box>
                  <Box>
                    <Typography sx={{ fontWeight: 800, fontSize: '0.875rem', color: '#F8FAFC', lineHeight: 1.2 }}>{accountLabel}</Typography>
                    <Typography sx={{ fontSize: '0.65rem', color: '#38BDF8', fontWeight: 800, letterSpacing: '0.1em', mt: 0.5 }}>
                      {role === 'admin' ? 'ADMIN' : 'ACTIVE ACCOUNT'}
                    </Typography>
                  </Box>
                </Box>

                <MenuItem
                  onClick={() => { setProfileAnchor(null); navigate('/profile'); }}
                  sx={{ color: '#F8FAFC' }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                    <PersonOutlineIcon sx={{ fontSize: 18, color: '#38BDF8' }} />
                    <Typography sx={{ fontWeight: 700, fontSize: '0.875rem' }}>Profile</Typography>
                  </Box>
                </MenuItem>

                <MenuItem 
                  onClick={() => { setProfileAnchor(null); navigate('/accounts'); }}
                  sx={{ color: '#F8FAFC' }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                    <SecurityIcon sx={{ fontSize: 18, color: '#4EDE93' }} />
                    <Typography sx={{ fontWeight: 700, fontSize: '0.875rem' }}>Data vault</Typography>
                  </Box>
                </MenuItem>

                {role === 'admin' && (
                <MenuItem 
                  onClick={() => { setProfileAnchor(null); navigate('/admin'); }}
                  sx={{ color: '#F8FAFC' }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                    <AdminPanelSettingsIcon sx={{ fontSize: 18, color: '#38BDF8' }} />
                    <Typography sx={{ fontWeight: 700, fontSize: '0.875rem' }}>Admin Console</Typography>
                  </Box>
                </MenuItem>
                )}

                <MenuItem 
                  onClick={() => { 
                    setProfileAnchor(null); 
                    queryClient.clear(); 
                    void logout().then(() => navigate('/'));
                  }}
                  sx={{ 
                    color: '#FF516A !important',
                    '&:hover': { bgcolor: alpha('#FF516A', 0.1) + ' !important' } 
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                    <LogoutIcon sx={{ fontSize: 18, color: '#FF516A' }} />
                    <Typography sx={{ fontWeight: 700, fontSize: '0.875rem' }}>Sign Out</Typography>
                  </Box>
                </MenuItem>
              </Menu>
            </>
          )}
        </Stack>
      </Toolbar>
    </AppBar>
  )
}
