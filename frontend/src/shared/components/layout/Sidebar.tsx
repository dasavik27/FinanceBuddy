import { 
  Box, Drawer, Typography, List, ListItem, ListItemButton, 
  ListItemIcon, ListItemText, Divider, Tooltip, IconButton, alpha 
} from '@mui/material'
import { useNavigate, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import DashboardIcon from '@mui/icons-material/Dashboard'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import TableChartIcon from '@mui/icons-material/TableChart'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ReceiptIcon from '@mui/icons-material/Receipt'
import LightbulbIcon from '@mui/icons-material/Lightbulb'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import LogoutIcon from '@mui/icons-material/Logout'
import HomeIcon from '@mui/icons-material/GridView'
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft'
import ChevronRightIcon from '@mui/icons-material/ChevronRight'
import AccountCircleIcon from '@mui/icons-material/AccountCircle'
import { useAppStore } from '../../store/appStore'

const DRAWER_W = 280
const COLLAPSED_W = 72

// The hub is separated from the domains below it: it is the way back out, not a
// fifth domain. Without an entry for it there was no route to the hub from inside a
// domain at all - the only way back was editing the URL or the browser back button.
const HOME = { label: 'Dashboard', icon: <HomeIcon />, path: '/dashboard' }

const NAV = [
  { label: 'Mutual Funds',          icon: <DashboardIcon />,          path: '/mutual-funds' },
  { label: 'Indian Stocks',         icon: <ShowChartIcon />,          path: '/equity' },
  { label: 'Tax Expert',            icon: <ReceiptIcon />,            path: '/tax-expert' },
  { label: 'Budget Analyzer',       icon: <LightbulbIcon />,          path: '/budget' },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
  isPartial: boolean
  collapsed: boolean
  onToggle: () => void
  onExpand: () => void
}

export function Sidebar({ open, onClose, isPartial: _isPartial, collapsed, onToggle, onExpand: _onExpand }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()

  // Keyboard shortcut: Cmd+B (Mac) or Ctrl+B (Windows/Linux) to toggle sidebar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        onToggle()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onToggle])

  return (
    <>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          '& .MuiDrawer-paper': { 
            width: collapsed ? COLLAPSED_W : DRAWER_W, 
            boxSizing: 'border-box', 
            background: (theme) => alpha(theme.palette.background.paper, 0.95), 
            backdropFilter: 'blur(20px)',
            color: '#E2E8F0',
            borderRight: '1px solid rgba(255,255,255,0.06)',
            transition: 'width 240ms cubic-bezier(0.4, 0, 0.2, 1)',
            overflowX: 'hidden'
          }
        }}
      >
        <SidebarContent 
          location={location} 
          navigate={navigate} 
          onClose={onClose} 
          collapsed={collapsed}
          onToggle={onToggle}
        />
      </Drawer>

      <Drawer
        variant="temporary"
        open={open}
        onClose={onClose}
        sx={{
          display: { xs: 'block', md: 'none' },
          '& .MuiDrawer-paper': { 
            width: DRAWER_W, 
            boxSizing: 'border-box', 
            background: '#0B1326', 
            color: '#E2E8F0',
            borderRight: '1px solid rgba(255,255,255,0.06)'
          }
        }}
      >
        <SidebarContent 
          location={location} 
          navigate={navigate} 
          onClose={onClose} 
          collapsed={false}
          onToggle={onToggle}
        />
      </Drawer>
    </>
  )
}

function SidebarContent({ location, navigate, onClose, collapsed, onToggle }: any) {
  const pan = useAppStore((s) => s.pan)
  const logout = useAppStore((s) => s.logout)

  const handleSignOut = () => {
    void logout().then(() => navigate('/'))
  }

  return (
    <Box sx={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%', 
      p: collapsed ? 1.5 : 2.5,
      alignItems: collapsed ? 'center' : 'stretch',
      transition: 'padding 240ms cubic-bezier(0.4, 0, 0.2, 1)'
    }}>
      {/* Branding & Toggle Header */}
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: collapsed ? 'center' : 'space-between', 
        mb: collapsed ? 3 : 4.5, 
        px: collapsed ? 0 : 0.5, 
        mt: 0.5,
        width: '100%'
      }}>
        {/* Brand Link */}
        <Box
          onClick={() => { navigate(HOME.path); onClose() }}
          role="link"
          aria-label="Go to dashboard"
          sx={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 1.8, 
            cursor: 'pointer',
            overflow: 'hidden',
            flex: collapsed ? '0 0 auto' : '1 1 auto'
          }}
        >
          <Box sx={{
            width: 42, 
            height: 42, 
            borderRadius: '13px',
            background: (theme) => `linear-gradient(135deg, ${theme.palette.primary.main} 0%, #4F46E5 100%)`,
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            boxShadow: (theme) => `0 6px 20px ${alpha(theme.palette.primary.main, 0.35)}`, 
            flexShrink: 0,
            transition: 'transform 0.2s ease',
            '&:hover': { transform: 'scale(1.05)' }
          }}>
            <TrendingUpIcon sx={{ fontSize: 22, color: '#fff' }} />
          </Box>
          {!collapsed && (
            <Box sx={{ whiteSpace: 'nowrap', overflow: 'hidden' }}>
              <Typography sx={{ fontSize: 17, fontWeight: 900, color: '#fff', letterSpacing: '-0.5px', lineHeight: 1 }}>
                Finance <span style={{ color: '#38BDF8' }}>Buddy</span>
              </Typography>
              <Typography sx={{ fontSize: 9.5, color: 'text.secondary', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.12em', mt: 0.5 }}>
                Smart Wealth Dashboard
              </Typography>
            </Box>
          )}
        </Box>

        {/* Expand / Collapse Header Toggle Button */}
        {!collapsed && (
          <Tooltip title="Collapse sidebar (⌘B)" placement="right" arrow>
            <IconButton 
              size="small" 
              onClick={onToggle}
              sx={{ 
                color: '#94a3b8', 
                p: 0.6,
                borderRadius: '10px',
                border: '1px solid rgba(255,255,255,0.06)',
                backgroundColor: 'rgba(255,255,255,0.03)',
                '&:hover': { 
                  color: '#fff', 
                  backgroundColor: 'rgba(255,255,255,0.08)',
                  borderColor: 'rgba(255,255,255,0.15)'
                } 
              }}
            >
              <ChevronLeftIcon sx={{ fontSize: 18 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* When collapsed, display the expand button directly below logo */}
      {collapsed && (
        <Tooltip title="Expand sidebar (⌘B)" placement="right" arrow>
          <IconButton 
            size="small" 
            onClick={onToggle}
            sx={{ 
              mb: 3,
              color: '#94a3b8', 
              p: 0.6,
              borderRadius: '10px',
              border: '1px solid rgba(255,255,255,0.06)',
              backgroundColor: 'rgba(255,255,255,0.03)',
              '&:hover': { 
                color: '#38BDF8', 
                backgroundColor: 'rgba(56, 189, 248, 0.12)',
                borderColor: 'rgba(56, 189, 248, 0.3)'
              } 
            }}
          >
            <ChevronRightIcon sx={{ fontSize: 18 }} />
          </IconButton>
        </Tooltip>
      )}

      {/* Nav List */}
      <List dense disablePadding sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 0.8 }}>
        {[HOME, ...NAV].map((item) => {
          const active = item.path === HOME.path
            ? location.pathname === HOME.path
            : location.pathname === item.path || location.pathname.startsWith(item.path + '/')

          return (
            <ListItem key={item.path} disablePadding sx={{ display: 'flex', justifyContent: 'center' }}>
              <Tooltip 
                title={collapsed ? item.label : ''} 
                placement="right" 
                arrow 
                slotProps={{
                  popper: {
                    sx: {
                      '& .MuiTooltip-tooltip': {
                        backgroundColor: '#0f172a',
                        border: '1px solid rgba(255,255,255,0.15)',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        fontSize: '0.78rem',
                        fontWeight: 700,
                        color: '#f8fafc',
                        px: 1.5,
                        py: 0.8
                      },
                      '& .MuiTooltip-arrow': {
                        color: '#0f172a',
                        '&::before': {
                          border: '1px solid rgba(255,255,255,0.15)'
                        }
                      }
                    }
                  }
                }}
              >
                <ListItemButton
                  onClick={() => { 
                    navigate(item.path)
                    onClose() 
                  }}
                  sx={{
                    width: collapsed ? 44 : '100%',
                    height: collapsed ? 44 : 46,
                    borderRadius: '14px',
                    px: collapsed ? 0 : 2,
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    background: active 
                      ? (theme) => alpha(theme.palette.primary.main, collapsed ? 0.18 : 0.12) 
                      : 'transparent',
                    border: active 
                      ? (theme) => `1px solid ${alpha(theme.palette.primary.main, 0.3)}` 
                      : '1px solid transparent',
                    boxShadow: active && collapsed ? (theme) => `0 0 16px ${alpha(theme.palette.primary.main, 0.25)}` : 'none',
                    '&:hover': { 
                      background: 'rgba(255,255,255,0.06)', 
                      borderColor: active ? (theme) => alpha(theme.palette.primary.main, 0.4) : 'rgba(255,255,255,0.12)',
                      transform: collapsed ? 'scale(1.06)' : 'none'
                    },
                    transition: 'all 200ms cubic-bezier(0.4, 0, 0.2, 1)',
                  }}
                >
                  <ListItemIcon sx={{ 
                    minWidth: collapsed ? 0 : 34, 
                    color: active ? '#38BDF8' : '#94a3b8', 
                    '& svg': { fontSize: 21 },
                    justifyContent: 'center',
                    alignItems: 'center'
                  }}>
                    {item.icon}
                  </ListItemIcon>
                  {!collapsed && (
                    <ListItemText
                      primary={item.label}
                      primaryTypographyProps={{
                        fontSize: 13.5, 
                        fontWeight: active ? 700 : 500,
                        color: active ? '#fff' : '#cbd5e1',
                        whiteSpace: 'nowrap'
                      }}
                    />
                  )}
                  {active && !collapsed && (
                    <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#38BDF8', ml: 1, boxShadow: '0 0 8px #38BDF8' }} />
                  )}
                </ListItemButton>
              </Tooltip>
            </ListItem>
          )
        })}
      </List>

      <Box sx={{ flex: 1 }} />
      
      {/* Session Footer */}
      {!collapsed ? (
        <Box sx={{ 
          mt: 'auto', 
          p: 2, 
          borderRadius: '16px', 
          background: 'rgba(255,255,255,0.025)', 
          border: '1px solid rgba(255,255,255,0.06)',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.2
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography sx={{ fontSize: 10, fontWeight: 800, color: '#94a3b8', letterSpacing: '0.1em' }}>ACCOUNT STATUS</Typography>
            <Tooltip title="Sign Out" arrow>
              <IconButton size="small" onClick={handleSignOut} sx={{ color: '#FF516A', p: 0.5, '&:hover': { bgcolor: alpha('#FF516A', 0.12) } }}>
                <LogoutIcon sx={{ fontSize: 16 }} />
              </IconButton>
            </Tooltip>
          </Box>
          <Typography sx={{ fontSize: 10, color: '#94a3b8', lineHeight: 1.5, fontWeight: 500 }}>
            Signed in as<br />
            <span style={{ color: '#4EDE93', fontWeight: 700 }}>{pan || 'Guest'}</span>
          </Typography>
        </Box>
      ) : (
        <Tooltip title={`Account: ${pan || 'Guest'} (Click to sign out)`} placement="right" arrow>
          <IconButton 
            onClick={handleSignOut} 
            sx={{ 
              color: '#FF516A', 
              width: 42,
              height: 42,
              borderRadius: '12px',
              border: '1px solid rgba(255, 81, 106, 0.2)',
              backgroundColor: 'rgba(255, 81, 106, 0.08)',
              mb: 1, 
              '&:hover': { 
                bgcolor: 'rgba(255, 81, 106, 0.2)',
                borderColor: '#FF516A'
              } 
            }}
          >
            <LogoutIcon sx={{ fontSize: 20 }} />
          </IconButton>
        </Tooltip>
      )}
    </Box>
  )
}
