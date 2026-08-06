import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { createWrapper } from '../../../test/utils'
import {
  useEquitySessionId,
  useClearSessionOnMissing,
  useEquitySummary,
  useEquityAllocation,
  useEquityHoldings,
  useEquityPnl,
  useEquityPerformance,
  useEquityInsights,
  useStockSearch,
  useStockAnalysis,
} from './useEquityData'
import { apiClient } from '../../../shared/api/client'
import { useAppStore } from '../../../shared/store/appStore'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getEquitySummary: vi.fn(),
    getEquityAllocation: vi.fn(),
    getEquityHoldings: vi.fn(),
    getEquityPnl: vi.fn(),
    getEquityPerformance: vi.fn(),
    getEquityInsights: vi.fn(),
    searchStocks: vi.fn(),
    analyzeStock: vi.fn(),
  },
}))

describe('useEquityData hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({ equitySessionId: 'eq-sess-123' })
  })

  it('useEquitySessionId returns current equity session id', () => {
    const { result } = renderHook(() => useEquitySessionId())
    expect(result.current).toBe('eq-sess-123')
  })

  it('useClearSessionOnMissing clears session on 404', () => {
    const { result } = renderHook(() =>
      useClearSessionOnMissing({ response: { status: 404 } }),
    )
    expect(result.current).toBe(404)
    expect(useAppStore.getState().equitySessionId).toBeNull()
  })

  it('useEquitySummary fetches data when session id is available', async () => {
    vi.mocked(apiClient.getEquitySummary).mockResolvedValue({
      total_portfolio_value: 1200000,
      total_invested: 1000000,
      total_unrealized_pnl: 200000,
      total_unrealized_pnl_pct: 20.0,
      total_realized_pnl: 50000,
      total_pnl: 250000,
      total_pnl_pct: 25.0,
      day_change: 15000,
      day_change_pct: 1.25,
      holdings_count: 12,
    } as any)

    const { result } = renderHook(() => useEquitySummary(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect((result.current.data as any)?.total_portfolio_value).toBe(1200000)
    expect(apiClient.getEquitySummary).toHaveBeenCalledWith('eq-sess-123')
  })

  it('useEquityHoldings fetches sorted holdings', async () => {
    vi.mocked(apiClient.getEquityHoldings).mockResolvedValue({
      holdings: [{ symbol: 'TCS', company_name: 'Tata Consultancy Services', current_value: 500000 }],
      total_count: 1,
    } as any)

    const { result } = renderHook(() => useEquityHoldings('unrealized_pnl', true), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.getEquityHoldings).toHaveBeenCalledWith('eq-sess-123', {
      sort_by: 'unrealized_pnl',
      ascending: true,
    })
  })

  it('useStockSearch performs search only when length >= 2', async () => {
    vi.mocked(apiClient.searchStocks).mockResolvedValue({
      results: [{ symbol: 'INFY', name: 'Infosys Ltd', exchange: 'NSE' }],
    } as any)

    const { result: emptyResult } = renderHook(() => useStockSearch('I'), {
      wrapper: createWrapper(),
    })
    expect(emptyResult.current.fetchStatus).toBe('idle')

    const { result: validResult } = renderHook(() => useStockSearch('INFY'), {
      wrapper: createWrapper(),
    })
    await waitFor(() => expect(validResult.current.isSuccess).toBe(true))
    expect(apiClient.searchStocks).toHaveBeenCalledWith('INFY')
  })

  it('useStockAnalysis fetches analysis for a symbol', async () => {
    vi.mocked(apiClient.analyzeStock).mockResolvedValue({
      symbol: 'INFY',
      name: 'Infosys Ltd',
      cmp: 1500,
    } as any)

    const { result } = renderHook(() => useStockAnalysis('INFY'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.analyzeStock).toHaveBeenCalledWith('INFY')
  })
})
