import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Box } from '@mui/material'
import { useStocksSessionId, useAppStore } from '../../store/appStore'
import DocumentUpload from './DocumentUpload'
import StocksTab from '../tabs/StocksTab'
import { ErrorBoundary } from '../ui'

export default function IndianStocksDashboard() {
  const sid = useStocksSessionId()
  const setActiveModule = useAppStore((s) => s.setActiveModule)

  useEffect(() => {
    setActiveModule('indian_stocks')
  }, [setActiveModule])

  if (!sid) {
    return (
      <DocumentUpload 
        title="Import Your Indian Stocks"
        subtitle="Upload your NSDL/CDSL statement to analyze your equity portfolio."
        dropText="Drag & drop your statement"
        dropSubText="or click anywhere in this box to browse from your device"
        uploadType="indian_stocks"
      />
    )
  }

  return (
    <Box>
      <Routes>
        <Route index element={<ErrorBoundary fallbackMessage="Stocks tab encountered an error."><StocksTab /></ErrorBoundary>} />
        <Route path="*" element={<Navigate to="" replace />} />
      </Routes>
    </Box>
  )
}
