import { 
  Box, Drawer, Typography, List, ListItem, ListItemButton, 
  ListItemIcon, ListItemText, Divider, Tooltip, IconButton, alpha 
} from '@mui/material'
import { useNavigate, useLocation } from 'react-router-dom'
import DashboardIcon from '@mui/icons-material/Dashboard'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import TableChartIcon from '@mui/icons-material/TableChart'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ReceiptIcon from '@mui/icons-material/Receipt'
import LightbulbIcon from '@mui/icons-material/Lightbulb'
import TrendingUpIcon from '@mui/icons-material/TrendingUp'
import LogoutIcon from '@mui/icons-material/Logout'
import PersonIcon from '@mui/icons-material/Person'
import TimelineIcon from '@mui/icons-material/Timeline'
import SecurityIcon from '@mui/icons-material/Security'
import { useAppStore } from '../../store/appStore'

const DRAWER_W = 280

const NAV = [
  { label: 'Mutual Funds',          icon: <DashboardIcon />,     path: '/dashboard/mutual-funds' },
  { label: 'Indian Stocks',         icon: <ShowChartIcon />,     path: '/dashboard/equity' },
  { label: 'Tax Expert',            icon: <ReceiptIcon />,       path: '/dashboard/tax-expert' },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
  isPartial: boolean
  collapsed: boolean
  onToggle: () => void
  onExpand: () => void
}

export function Sidebar({ open, onClose, isPartial, collapsed, onToggle, onExpand }: SidebarProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const { clearSession } = useAppStore()

  return (
    <>
      <Drawer
        variant="permanent"
        sx={{
          display: { xs: 'none', md: 'block' },
          '& .MuiDrawer-paper': { 
            width: collapsed ? 80 : DRAWER_W, 
            boxSizing: 'border-box', 
            background: (theme) => alpha(theme.palette.background.paper, 0.95), 
            backdropFilter: 'blur(20px)',
            color: '#E2E8F0',
            borderRight: '1px solid rgba(255,255,255,0.05)',
            transition: 'all 300ms cubic-bezier(0.4, 0, 0.2, 1)',
            overflowX: 'hidden'
          }
        }}
      >
        <SidebarContent 
          location={location} 
          navigate={navigate} 
          isPartial={isPartial} 
          clearSession={clearSession} 
          onClose={() => {}} 
          collapsed={collapsed}
          onToggle={onToggle}
          onExpand={onExpand}
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
            borderRight: '1px solid rgba(255,255,255,0.05)'
          }
        }}
      >
        <SidebarContent 
          location={location} 
          navigate={navigate} 
          isPartial={isPartial} 
          clearSession={clearSession} 
          onClose={onClose} 
          collapsed={false}
          onToggle={() => {}}
          onExpand={() => {}}
        />
      </Drawer>
    </>
  )
}

function SidebarContent({ location, navigate, isPartial, clearSession, onClose, collapsed, onToggle, onExpand }: any) {
  const { pan } = useAppStore()
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', p: 2.5 }}>
      {/* Branding */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: collapsed ? 'center' : 'space-between', mb: 6, px: 0.5, mt: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Box sx={{
            width: 44, height: 44, borderRadius: '14px',
            background: (theme) => `linear-gradient(135deg, ${theme.palette.primary.main} 0%, #4F46E5 100%)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: (theme) => `0 8px 24px ${alpha(theme.palette.primary.main, 0.3)}`, 
            flexShrink: 0,
          }}>
            <TrendingUpIcon sx={{ fontSize: 24, color: '#fff' }} />
          </Box>
          {!collapsed && (
            <Box sx={{ whiteSpace: 'nowrap' }}>
              <Typography sx={{ fontSize: 18, fontWeight: 900, color: '#fff', letterSpacing: '-0.5px', lineHeight: 1 }}>
                Finance <span style={{ color: '#38BDF8' }}>Buddy</span>
              </Typography>
              <Typography sx={{ fontSize: 10, color: 'text.secondary', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.15em', mt: 0.5 }}>
                Smart Wealth Dashboard
              </Typography>
            </Box>
          )}
        </Box>
      </Box>

      {/* Nav List */}
      <List dense disablePadding>
        {NAV.map((item) => {
          const active = location.pathname === item.path ||
            (item.path !== '/dashboard' && location.pathname.startsWith(item.path))
          return (
            <ListItem key={item.path} disablePadding sx={{ mb: 1 }}>
              <Tooltip title={collapsed ? item.label : ""} placement="right">
                <ListItemButton
                  onClick={() => { 
                    navigate(item.path)
                    onClose() 
                    if (collapsed) onExpand()
                  }}
                  sx={{
                    borderRadius: '16px',
                    px: collapsed ? 0 : 2.5,
                    justifyContent: collapsed ? 'center' : 'flex-start',
                    py: 1.5,
                    background: active ? (theme) => alpha(theme.palette.primary.main, 0.1) : 'transparent',
                    border: active ? (theme) => `1px solid ${alpha(theme.palette.primary.main, 0.2)}` : '1px solid transparent',
                    '&:hover': { background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)' },
                    transition: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
                  }}
                >
                  <ListItemIcon sx={{ 
                    minWidth: collapsed ? 0 : 36, 
                    color: active ? 'primary.main' : 'text.secondary', 
                    '& svg': { fontSize: 22 },
                    justifyContent: 'center'
                  }}>
                    {item.icon}
                  </ListItemIcon>
                  {!collapsed && (
                    <ListItemText
                      primary={item.label}
                      primaryTypographyProps={{
                        fontSize: 14, 
                        fontWeight: active ? 700 : 500,
                        color: active ? '#fff' : 'text.secondary',
                        whiteSpace: 'nowrap'
                      }}
                    />
                  )}
                  {active && !collapsed && (
                    <Box sx={{ width: 6, height: 6, borderRadius: 'full', bgcolor: 'primary.main', ml: 1, boxShadow: (theme) => `0 0 10px ${theme.palette.primary.main}` }} />
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
          mt: 'auto', p: 2.5, borderRadius: '20px', 
          background: 'rgba(255,255,255,0.03)', 
          border: '1px solid rgba(255,255,255,0.05)',
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography sx={{ fontSize: 11, fontWeight: 800, color: 'text.secondary', letterSpacing: '0.1em' }}>ACCOUNT STATUS</Typography>
            <IconButton size="small" onClick={clearSession} sx={{ color: 'tertiary', '&:hover': { bgcolor: alpha('#FF516A', 0.1) } }}>
              <LogoutIcon sx={{ fontSize: 18, color: '#FF516A' }} />
            </IconButton>
          </Box>
          <Typography sx={{ fontSize: 10, color: 'text.secondary', lineHeight: 1.6, fontWeight: 500 }}>
            Signed in as<br />
            <span style={{ color: '#4EDE93' }}>{pan}</span>
          </Typography>
        </Box>
      ) : (
        <IconButton onClick={clearSession} sx={{ color: '#FF516A', mb: 1, '&:hover': { bgcolor: alpha('#FF516A', 0.1) } }}>
          <LogoutIcon sx={{ fontSize: 24 }} />
        </IconButton>
      )}
    </Box>
  )
}
