import { Suspense, lazy, useState } from 'react'
import { Box, Tabs, Tab, alpha } from '@mui/material'
import SummarizeIcon from '@mui/icons-material/Summarize'
import AccountBalanceWalletIcon from '@mui/icons-material/AccountBalanceWallet'
import SavingsIcon from '@mui/icons-material/Savings'
import ShowChartIcon from '@mui/icons-material/ShowChart'
import BalanceIcon from '@mui/icons-material/Balance'
import { TabFallback } from '../../../shared/components/ui'

// Lazy for the same reason as the mutual-fund tabs: these five were statically
// imported, so viewing the Tax Summary also downloaded Capital Gains (the second
// largest component in the app) and everything else.
const TaxOverviewTab     = lazy(() => import('./tax/TaxOverviewTab'))
const TaxIncomeTab       = lazy(() => import('./tax/TaxIncomeTab'))
const TaxSavingsTab      = lazy(() => import('./tax/TaxSavingsTab'))
const TaxCapitalGainsTab = lazy(() => import('./tax/TaxCapitalGainsTab'))
const TaxITRCompareTab   = lazy(() => import('./tax/TaxITRCompareTab'))

const TAX_TABS = [
  { label: 'Tax Summary', icon: <SummarizeIcon /> },
  { label: 'Income Sources', icon: <AccountBalanceWalletIcon /> },
  { label: 'Tax Savings', icon: <SavingsIcon /> },
  { label: 'Capital Gains', icon: <ShowChartIcon /> },
  { label: 'Compare ITR', icon: <BalanceIcon /> },
]

export default function TaxStrategyTab() {
  const [tab, setTab] = useState(0)

  return (
    <Box sx={{ pb: 4 }}>
      <Box sx={{
        mb: 4,
        borderBottom: '1px solid rgba(255,255,255,0.05)',
      }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            '& .MuiTabs-indicator': {
              height: 3,
              borderRadius: '3px 3px 0 0',
              background: 'linear-gradient(90deg, #6366F1 0%, #38BDF8 100%)',
            },
            '& .MuiTab-root': {
              color: '#64748B',
              fontWeight: 800,
              textTransform: 'none',
              fontSize: '0.9rem',
              minHeight: 56,
              transition: 'all 0.2s',
              '&.Mui-selected': { color: '#F8FAFC' },
              '&:hover': { color: '#94A3B8', bgcolor: 'rgba(255,255,255,0.02)' },
            },
          }}
        >
          {TAX_TABS.map((t, i) => (
            <Tab key={i} label={t.label} icon={t.icon} iconPosition="start" />
          ))}
        </Tabs>
      </Box>

      <Suspense fallback={<TabFallback />}>
        {tab === 0 && <TaxOverviewTab />}
        {tab === 1 && <TaxIncomeTab />}
        {tab === 2 && <TaxSavingsTab />}
        {tab === 3 && <TaxCapitalGainsTab />}
        {tab === 4 && <TaxITRCompareTab />}
      </Suspense>
    </Box>
  )
}
