import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box } from '@mui/material'
import { useAppStore } from '../../../shared/store/appStore'
import IndianStocksTab from './IndianStocksTab'
import { ErrorBoundary } from '../../../shared/components/ui'

export default function IndianStocksDashboard() {
  const setActiveModule = useAppStore((s) => s.setActiveModule)

  useEffect(() => {
    setActiveModule('indian_stocks')
  }, [setActiveModule])

  return (
    <Box>
      <Routes>
        <Route index element={<ErrorBoundary fallbackMessage="Stocks tab encountered an error."><IndianStocksTab /></ErrorBoundary>} />
        <Route path="*" element={<Navigate to="/dashboard/equity" replace />} />
      </Routes>
    </Box>
  )
}
