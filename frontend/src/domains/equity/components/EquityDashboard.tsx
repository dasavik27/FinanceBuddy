import { useState } from 'react'
import { Box, Typography, Tabs, Tab } from '@mui/material'
import { motion, AnimatePresence } from 'framer-motion'
import { SwitchEquityStatementButton } from './EquityUploadPanel'
import { useEquitySessionId } from '../../../shared/store/appStore'

import OverviewTab from './tabs/OverviewTab'
import HoldingsTab from './tabs/HoldingsTab'
import PLTab from './tabs/PLTab'
import SectorTab from './tabs/SectorTab'
import PerformanceTab from './tabs/PerformanceTab'
import StockAnalyzerTab from './tabs/StockAnalyzerTab'
import InsightsTab from './tabs/InsightsTab'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'holdings', label: 'Holdings' },
  { id: 'pnl', label: 'P&L Analysis' },
  { id: 'sectors', label: 'Sector Allocation' },
  { id: 'performance', label: 'Performance' },
  { id: 'analyzer', label: 'Stock Analyzer', chip: 'New' },
  { id: 'insights', label: 'Insights' },
]

export default function EquityDashboard() {
  const [activeTabId, setActiveTabId] = useState('overview')
  const sessionId = useEquitySessionId()

  const handleTabChange = (_event: React.SyntheticEvent, newValue: string) => {
    setActiveTabId(newValue)
  }

  return (
    <Box sx={{ pb: 10 }}>
      {/* Header */}
      <Box sx={{
        display: 'flex', flexDirection: { xs: 'column', md: 'row' },
        justifyContent: 'space-between', alignItems: { xs: 'flex-start', md: 'center' },
        mb: 4, gap: 2, px: { xs: 2, md: 0 }
      }}>
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800, color: '#F8FAFC', mb: 0.5, letterSpacing: '-0.02em' }}>
            Equity Dashboard
          </Typography>
          <Typography sx={{ color: '#94A3B8', fontSize: '0.9rem' }}>
            Direct stock investments and analytics
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <SwitchEquityStatementButton sessionId={sessionId} />
        </Box>
      </Box>

      {/* Tabs */}
      <Tabs 
          value={activeTabId} 
          onChange={handleTabChange} 
          variant="scrollable" 
          scrollButtons="auto"
          sx={{ 
              mb: 4,
              borderBottom: '1px solid rgba(255,255,255,0.1)',
              '& .MuiTab-root': { py: 2.5, fontWeight: 700, color: '#94A3B8', textTransform: 'none', fontSize: '0.95rem' },
              '& .Mui-selected': { color: '#10B981 !important' },
              '& .MuiTabs-indicator': { backgroundColor: '#10B981', height: 3 }
          }}
      >
        {TABS.map((tab) => (
          <Tab 
              key={tab.id} 
              label={tab.label} 
              value={tab.id} 
          />
        ))}
      </Tabs>

      {/* Content Area */}
      <Box sx={{ mt: 4, position: 'relative' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTabId}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
          >
            {activeTabId === 'overview' && <OverviewTab />}
            {activeTabId === 'holdings' && <HoldingsTab />}
            {activeTabId === 'pnl' && <PLTab />}
            {activeTabId === 'sectors' && <SectorTab />}
            {activeTabId === 'performance' && <PerformanceTab />}
            {activeTabId === 'analyzer' && <StockAnalyzerTab />}
            {activeTabId === 'insights' && <InsightsTab />}
          </motion.div>
        </AnimatePresence>
      </Box>
    </Box>
  )
}
