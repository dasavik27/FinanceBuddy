import { useState } from 'react'
import { api } from '../../../shared/api/client'

export interface BudgetFilters {
  bank?: string
  accountType?: string
  txnType?: string
  dateRange?: string
  fromDate?: string
  toDate?: string
  amountBracket?: string
  paymentMode?: string
  category?: string
  search?: string
  flow?: string
}

export function useBudget() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const buildQuery = (filters?: BudgetFilters): string => {
    if (!filters) return ''
    const params = new URLSearchParams()
    if (filters.bank && filters.bank.toLowerCase() !== 'all') params.append('bank', filters.bank)
    if (filters.accountType && filters.accountType.toLowerCase() !== 'all') params.append('account_type', filters.accountType)
    if (filters.txnType && filters.txnType.toLowerCase() !== 'all') params.append('txn_type', filters.txnType)
    if (filters.dateRange && filters.dateRange.toLowerCase() !== 'all') params.append('date_range', filters.dateRange)
    if (filters.fromDate) params.append('from_date', filters.fromDate)
    if (filters.toDate) params.append('to_date', filters.toDate)
    if (filters.amountBracket && filters.amountBracket.toLowerCase() !== 'all') params.append('amount_bracket', filters.amountBracket)
    if (filters.paymentMode && filters.paymentMode.toLowerCase() !== 'all') params.append('payment_mode', filters.paymentMode)
    if (filters.category && filters.category.toLowerCase() !== 'all') params.append('category', filters.category)
    if (filters.search && filters.search.trim()) params.append('search', filters.search.trim())
    if (filters.flow && filters.flow.toLowerCase() !== 'all') params.append('flow', filters.flow)
    const qs = params.toString()
    return qs ? `?${qs}` : ''
  }

  const uploadStatement = async (file: File, bank: string = 'auto', accountType: string = 'auto') => {
    setLoading(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('bank', bank)
      formData.append('account_type', accountType)
      const res = await api.post('/budget/portfolio/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      return res.data.session_id
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Upload failed')
      return null
    } finally {
      setLoading(false)
    }
  }

  const getOverview = async (sessionId: string, filters?: BudgetFilters) => {
    try {
      const qs = buildQuery(filters)
      const res = await api.get(`/budget/analytics/${sessionId}/overview${qs}`)
      return res.data
    } catch (err) {
      console.error(err)
      return null
    }
  }

  const getCategories = async (sessionId: string, filters?: BudgetFilters) => {
    try {
      const qs = buildQuery(filters)
      const res = await api.get(`/budget/analytics/${sessionId}/categories${qs}`)
      return res.data
    } catch (err) {
      console.error(err)
      return { categories: [], nature_summary: {} }
    }
  }

  const getTransactions = async (sessionId: string, filters?: BudgetFilters) => {
    try {
      const qs = buildQuery(filters)
      const res = await api.get(`/budget/analytics/${sessionId}/transactions${qs}`)
      return res.data.transactions
    } catch (err) {
      console.error(err)
      return []
    }
  }

  const listSessions = async () => {
    try {
      const res = await api.get('/budget/portfolio/sessions')
      return res.data.sessions || []
    } catch (err) {
      console.error(err)
      return []
    }
  }

  const deleteSession = async (sessionId: string) => {
    try {
      await api.delete(`/budget/portfolio/sessions/${sessionId}`)
      return true
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'Delete failed')
      return false
    }
  }

  return {
    uploadStatement,
    getOverview,
    getCategories,
    getTransactions,
    listSessions,
    deleteSession,
    loading,
    error
  }
}
