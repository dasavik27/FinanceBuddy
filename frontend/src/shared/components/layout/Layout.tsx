import { useState, ReactNode } from 'react'
import { Box } from '@mui/material'
import { motion } from 'framer-motion'
import { useIsPartial } from '../../store/appStore'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

interface Props { children: ReactNode }

export default function Layout({ children }: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem('finance_buddy_sidebar_collapsed')
      return stored !== null ? stored === 'true' : true
    } catch {
      return true
    }
  })
  const isPartial = useIsPartial()

  const handleToggle = () => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem('finance_buddy_sidebar_collapsed', String(next))
      } catch {}
      return next
    })
  }

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', background: (theme) => theme.palette.background.default }}>
      <Sidebar 
        open={sidebarOpen} 
        onClose={() => setSidebarOpen(false)} 
        collapsed={collapsed}
        onToggle={handleToggle}
        onExpand={() => {
          setCollapsed(false)
          try {
            localStorage.setItem('finance_buddy_sidebar_collapsed', 'false')
          } catch {}
        }}
        isPartial={isPartial} 
      />

      <Box sx={{ 
        flex: 1, 
        display: 'flex', 
        flexDirection: 'column', 
        minWidth: 0,
        ml: { md: collapsed ? '72px' : '280px' },
        transition: 'margin 240ms cubic-bezier(0.4, 0, 0.2, 1)'
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
