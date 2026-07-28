import { useState, ReactNode } from 'react'
import { Box } from '@mui/material'
import { motion } from 'framer-motion'
import { useIsPartial } from '../../store/appStore'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

interface Props { children: ReactNode }

export default function Layout({ children }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const isPartial = useIsPartial()

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', background: (theme) => theme.palette.background.default }}>
      <Sidebar 
        open={sidebarOpen} 
        onClose={() => setSidebarOpen(false)} 
        collapsed={collapsed}
        onToggle={() => setCollapsed(!collapsed)}
        onExpand={() => setCollapsed(false)}
        isPartial={isPartial} 
      />

      <Box sx={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column', 
        minWidth: 0,
        ml: { md: collapsed ? '80px' : '280px' }, // Match new theme width
        transition: 'margin 300ms cubic-bezier(0.4, 0, 0.2, 1)'
      }}>
        <Topbar 
          onMenuClick={() => setSidebarOpen(true)} 
          isPartial={isPartial}
        />

        <Box
          component={motion.div}
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: [0.23, 1, 0.32, 1] }}
          sx={{ flex: 1, p: { xs: 2, md: 5 }, overflowY: 'auto' }}
        >
          {children}
        </Box>
      </Box>
    </Box>
  )
}
