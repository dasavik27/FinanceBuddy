import { AppBar, Toolbar, IconButton, Box, Stack, Chip, Typography, Tooltip, Divider, alpha } from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import WarningAmberIcon from '@mui/icons-material/WarningAmber'
import AccessTimeIcon from '@mui/icons-material/AccessTime'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import TrendingDownIcon from '@mui/icons-material/TrendingDown'
import SettingsIcon from '@mui/icons-material/Settings'
import SyncIcon from '@mui/icons-material/Sync'
import StorageIcon from '@mui/icons-material/Storage'
import BoltIcon from '@mui/icons-material/Bolt'
import SpeedIcon from '@mui/icons-material/Speed'
import CachedIcon from '@mui/icons-material/Cached'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import { useIsFetching, useQueryClient, useMutation } from '@tanstack/react-query'
import { useMarketSummary, useMarketConfig } from '../../hooks/useData'
import { useEffect, useState } from 'react'
import { useSessionId, useLastSynced, useRefreshTrigger } from '../../store/appStore'
import { apiClient } from '../../api/client'

interface TopbarProps {
  onMenuClick: () => void
  isPartial: boolean
}

export function Topbar({ onMenuClick, isPartial }: TopbarProps) {
  const isFetching = useIsFetching()
  const queryClient = useQueryClient()
  const sid = useSessionId()
  const lastSynced = useLastSynced()
  const triggerRefresh = useRefreshTrigger()

  const { data: market } = useMarketSummary()
  const { data: config } = useMarketConfig()
  const [time, setTime] = useState(new Date().toLocaleTimeString())

  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const updateConfig = useMutation({
    mutationFn: (ttl: number) => apiClient.updateMarketConfig(ttl),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['market-config'] })
  })

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date().toLocaleTimeString()), 1000)
    return () => clearInterval(timer)
  }, [])

  const handleRefresh = async () => {
    if (!sid) return
    try {
      await apiClient.syncPortfolio(sid)
      triggerRefresh()
      queryClient.invalidateQueries()
    } catch (e) {
      console.error('Sync failed', e)
    }
  }

  const handleConfigClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleConfigClose = (ttl?: number) => {
    setAnchorEl(null)
    if (ttl !== undefined) {
      updateConfig.mutate(ttl)
    }
  }

  const getSyncedText = () => {
    const diff = Math.floor((Date.now() - lastSynced) / 60000)
    if (diff < 1) return 'Live Prices Synced'
    if (diff < 60) return `Prices updated ${diff}m ago`
    const hours = Math.floor(diff / 60)
    return `Prices updated ${hours}h ago`
  }

  const currentTTL = config?.cache_ttl ?? 60
  const ttlText = currentTTL === 0 ? 'None' : `${currentTTL / 60}h`

  const nifty = market?.nifty
  const isUp = (nifty?.change ?? 0) >= 0

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

        {/* Market Widget */}
        <Stack direction="row" spacing={3} alignItems="center" sx={{ display: { xs: 'none', lg: 'flex' } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Typography variant="caption" sx={{ fontWeight: 800, color: 'primary.main', letterSpacing: '0.1em' }}>
              MARKET INDEX / NIFTY 50
            </Typography>
            <Typography variant="body2" className="num" sx={{ fontWeight: 700, color: '#fff', fontSize: '0.9375rem' }}>
              {nifty?.price?.toLocaleString('en-IN') ?? '---'}
            </Typography>
            {nifty && (
              <Stack direction="row" spacing={0.5} alignItems="center" sx={{ px: 1, py: 0.25, borderRadius: '6px', bgcolor: isUp ? alpha('#4EDE93', 0.1) : alpha('#FF516A', 0.1) }}>
                {isUp ? <TrendingUpIcon sx={{ fontSize: 14, color: '#4EDE93' }} /> : <TrendingDownIcon sx={{ fontSize: 14, color: '#FF516A' }} />}
                <Typography sx={{ fontSize: 11, fontWeight: 800, color: isUp ? '#4EDE93' : '#FF516A' }}>
                  {isUp ? '+' : ''}{nifty.change_pct}%
                </Typography>
              </Stack>
            )}
          </Box>

          <Divider orientation="vertical" flexItem sx={{ height: 16, my: 'auto', borderColor: 'rgba(255,255,255,0.1)' }} />

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <AccessTimeIcon sx={{ fontSize: 14, color: 'text.secondary' }} />
            <Typography variant="body2" className="num" sx={{ fontSize: '0.8125rem', fontWeight: 600, color: 'text.secondary' }}>
              {time}
            </Typography>
          </Box>
        </Stack>

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

          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1.5,
              p: '4px 6px 4px 14px',
              borderRadius: '100px',
              background: alpha('#1E293B', 0.6),
              border: '1px solid',
              borderColor: alpha('#334155', 0.8),
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.05)',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  bgcolor: isFetching > 0 ? '#38BDF8' : '#10B981',
                  boxShadow: isFetching > 0 ? '0 0 12px #38BDF8' : '0 0 12px #10B981',
                  animation: isFetching > 0 ? 'pulse 1.5s infinite' : 'none'
                }}
              />
              <Box sx={{ display: { xs: 'none', sm: 'block' }, textAlign: 'left' }}>
                <Typography variant="caption" sx={{ display: 'block', fontSize: '0.625rem', fontWeight: 800, color: '#94A3B8', letterSpacing: '0.1em', lineHeight: 1, mb: 0.25 }}>
                  MARKET DATA STATUS
                </Typography>
                <Typography variant="caption" sx={{ fontSize: '0.75rem', fontWeight: 600, color: '#F8FAFC', lineHeight: 1 }}>
                  {isFetching > 0 ? 'Fetching Live Prices...' : getSyncedText()}
                </Typography>
              </Box>
            </Box>

            <Tooltip title="Fetch live AMFI NAV prices and refresh portfolio valuations">
              <span>
                <IconButton
                  size="small"
                  onClick={handleRefresh}
                  disabled={isFetching > 0}
                  sx={{
                    width: 28,
                    height: 28,
                    color: isFetching > 0 ? '#38BDF8' : '#94A3B8',
                    bgcolor: isFetching > 0 ? alpha('#38BDF8', 0.1) : alpha('#334155', 0.5),
                    border: '1px solid',
                    borderColor: isFetching > 0 ? alpha('#38BDF8', 0.3) : 'transparent',
                    transition: 'all 0.2s ease',
                    '&:hover': {
                      color: '#F8FAFC',
                      bgcolor: alpha('#6366F1', 0.2),
                      borderColor: alpha('#6366F1', 0.4),
                      transform: 'rotate(30deg)'
                    }
                  }}
                >
                  <SyncIcon sx={{ fontSize: 16, animation: isFetching > 0 ? 'spin 1s linear infinite' : 'none' }} />
                  <style>{`
                    @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
                    @keyframes pulse { 0% { transform: scale(0.95); opacity: 0.8; } 50% { transform: scale(1.2); opacity: 1; } 100% { transform: scale(0.95); opacity: 0.8; } }
                  `}</style>
                </IconButton>
              </span>
            </Tooltip>

            <Divider orientation="vertical" flexItem sx={{ height: 18, my: 'auto', borderColor: alpha('#334155', 0.8) }} />

            <Tooltip title="Configure Feed Latency & Cache TTL">
              <Box
                onClick={handleConfigClick}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.75,
                  px: 1.25,
                  py: 0.5,
                  borderRadius: '100px',
                  cursor: 'pointer',
                  background: currentTTL === 0 
                    ? alpha('#38BDF8', 0.15) 
                    : alpha('#6366F1', 0.15),
                  border: '1px solid',
                  borderColor: currentTTL === 0 
                    ? alpha('#38BDF8', 0.3) 
                    : alpha('#6366F1', 0.3),
                  transition: 'all 0.2s',
                  '&:hover': {
                    background: currentTTL === 0 
                      ? alpha('#38BDF8', 0.25) 
                      : alpha('#6366F1', 0.25),
                    boxShadow: currentTTL === 0 
                      ? '0 0 12px rgba(56, 189, 248, 0.2)' 
                      : '0 0 12px rgba(99, 102, 241, 0.2)'
                  }
                }}
              >
                {currentTTL === 0 ? <BoltIcon sx={{ fontSize: 16, color: '#38BDF8' }} /> : <StorageIcon sx={{ fontSize: 14, color: '#818CF8' }} />}
                <Typography variant="caption" sx={{ fontWeight: 700, fontSize: '0.75rem', color: currentTTL === 0 ? '#38BDF8' : '#818CF8' }}>
                  {currentTTL === 0 ? 'LIVE' : `${currentTTL / 60}H CACHE`}
                </Typography>
              </Box>
            </Tooltip>
          </Box>

          <Menu
            anchorEl={anchorEl}
            open={Boolean(anchorEl)}
            onClose={() => handleConfigClose()}
            PaperProps={{
              sx: {
                background: alpha('#0F172A', 0.95),
                backdropFilter: 'blur(20px)',
                border: '1px solid',
                borderColor: alpha('#334155', 0.8),
                boxShadow: '0 20px 50px rgba(0,0,0,0.7)',
                borderRadius: '16px',
                minWidth: 280,
                mt: 1.5,
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
          >
            <Box sx={{ px: 2, py: 1, mb: 1 }}>
              <Typography variant="caption" sx={{ fontWeight: 800, color: '#818CF8', letterSpacing: '0.1em' }}>
                MARKET FEED UPDATE INTERVAL
              </Typography>
              <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: '0.75rem', mt: 0.5 }}>
                Configure how frequently live NAV prices are fetched from AMFI.
              </Typography>
            </Box>

            <MenuItem onClick={() => handleConfigClose(0)} selected={currentTTL === 0}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                <Box sx={{ p: 1, borderRadius: '8px', bgcolor: alpha('#38BDF8', 0.1), color: '#38BDF8', display: 'flex' }}>
                  <BoltIcon sx={{ fontSize: 20 }} />
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.875rem', color: '#F8FAFC' }}>Real-time Live Feed</Typography>
                  <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>Zero latency, bypass local cache</Typography>
                </Box>
              </Box>
            </MenuItem>

            <MenuItem onClick={() => handleConfigClose(60)} selected={currentTTL === 60}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                <Box sx={{ p: 1, borderRadius: '8px', bgcolor: alpha('#6366F1', 0.1), color: '#818CF8', display: 'flex' }}>
                  <SpeedIcon sx={{ fontSize: 20 }} />
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.875rem', color: '#F8FAFC' }}>1 Hour Cache (Default)</Typography>
                  <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>Optimal speed & update balance</Typography>
                </Box>
              </Box>
            </MenuItem>

            <MenuItem onClick={() => handleConfigClose(240)} selected={currentTTL === 240}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                <Box sx={{ p: 1, borderRadius: '8px', bgcolor: alpha('#10B981', 0.1), color: '#34D399', display: 'flex' }}>
                  <StorageIcon sx={{ fontSize: 20 }} />
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.875rem', color: '#F8FAFC' }}>4 Hours Cache</Typography>
                  <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>Best for intraday stability</Typography>
                </Box>
              </Box>
            </MenuItem>

            <MenuItem onClick={() => handleConfigClose(1440)} selected={currentTTL === 1440}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%' }}>
                <Box sx={{ p: 1, borderRadius: '8px', bgcolor: alpha('#64748B', 0.2), color: '#94A3B8', display: 'flex' }}>
                  <CachedIcon sx={{ fontSize: 20 }} />
                </Box>
                <Box sx={{ flex: 1 }}>
                  <Typography sx={{ fontWeight: 700, fontSize: '0.875rem', color: '#F8FAFC' }}>24 Hours Cache</Typography>
                  <Typography sx={{ fontSize: '0.75rem', color: 'text.secondary' }}>Maximum speed, end-of-day sync</Typography>
                </Box>
              </Box>
            </MenuItem>
          </Menu>
        </Stack>
      </Toolbar>
    </AppBar>
  )
}
