import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAppStore } from '../../../shared/store/appStore'
import { apiClient } from '../../../shared/api/client'
import {
  useFilterParams,
  useSummary,
  useOverview,
  useBenchmarkOverlay,
  useHoldings,
  useAllocation,
  usePerformance,
  useRebalancePlan,
  useTaxHarvest,
  useSipProjection,
  useXirrByFy,
  useSipAttribution,
  useWhatIf,
  useMandateOverlap,
  useInsights,
  useJourney,
  useFundInsights,
  useTransactions,
} from './useData'

vi.mock('../../../shared/api/client', () => ({
  apiClient: {
    getSummary: vi.fn(),
    getOverview: vi.fn(),
    getBenchmarkOverlay: vi.fn(),
    getHoldings: vi.fn(),
    getAllocation: vi.fn(),
    getPerformance: vi.fn(),
    getRebalancePlan: vi.fn(),
    getTaxHarvest: vi.fn(),
    getSipProjection: vi.fn(),
    getXirrByFy: vi.fn(),
    getSipAttribution: vi.fn(),
    getWhatIf: vi.fn(),
    getMandateOverlap: vi.fn(),
    getInsights: vi.fn(),
    getJourney: vi.fn(),
    getFundInsights: vi.fn(),
    getTransactions: vi.fn(),
  },
}))

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

describe('Mutual Funds useData Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAppStore.setState({
      mfSessionId: 'sid-test-123',
      activeModule: 'mutual_funds',
    })
    useAppStore.getState().setFilters({
      benchmark: 'Nifty 50',
      categories: ['Equity', 'ELSS'],
      amcs: ['HDFC', 'SBI'],
      plan: 'Direct',
      minAlloc: 5,
    })
  })

  it('builds filter params accurately from store', () => {
    const { result } = renderHook(() => useFilterParams(), { wrapper: createWrapper() })
    expect(result.current).toEqual({
      benchmark: 'Nifty 50',
      category: 'Equity,ELSS',
      amc: 'HDFC,SBI',
      plan: 'Direct',
      min_alloc: 5,
    })
  })

  it('fetches summary when session is present', async () => {
    vi.mocked(apiClient.getSummary).mockResolvedValueOnce({ total_value: 100000 } as any)
    const { result } = renderHook(() => useSummary('Nifty 500'), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.getSummary).toHaveBeenCalledWith('sid-test-123', { benchmark: 'Nifty 500' })
    expect(result.current.data).toEqual({ total_value: 100000 })
  })

  it('fetches overview with period and benchmark', async () => {
    vi.mocked(apiClient.getOverview).mockResolvedValueOnce({ chart: [] } as any)
    const { result } = renderHook(() => useOverview('1Y', 'Nifty Smallcap 100'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.getOverview).toHaveBeenCalledWith('sid-test-123', {
      period: '1Y',
      benchmark: 'Nifty Smallcap 100',
    })
  })

  it('fetches benchmark overlay for multiple benchmarks', async () => {
    vi.mocked(apiClient.getBenchmarkOverlay).mockResolvedValueOnce({ series: {} } as any)
    const { result } = renderHook(() => useBenchmarkOverlay('3Y', ['Nifty 50', 'Nifty Next 50']), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.getBenchmarkOverlay).toHaveBeenCalledWith('sid-test-123', {
      period: '3Y',
      benchmarks: 'Nifty 50,Nifty Next 50',
    })
  })

  it('fetches holdings passing extra params and filters', async () => {
    vi.mocked(apiClient.getHoldings).mockResolvedValueOnce({ holdings: [] } as any)
    const { result } = renderHook(() => useHoldings({ search: 'HDFC' }), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(apiClient.getHoldings).toHaveBeenCalledWith('sid-test-123', expect.objectContaining({
      search: 'HDFC',
      category: 'Equity,ELSS',
    }))
  })

  it('fetches allocation and performance', async () => {
    vi.mocked(apiClient.getAllocation).mockResolvedValueOnce({ categories: [] } as any)
    vi.mocked(apiClient.getPerformance).mockResolvedValueOnce({ returns: [] } as any)

    const wrapper = createWrapper()
    const { result: allocResult } = renderHook(() => useAllocation(), { wrapper })
    const { result: perfResult } = renderHook(() => usePerformance('ALL'), { wrapper })

    await waitFor(() => expect(allocResult.current.isSuccess).toBe(true))
    await waitFor(() => expect(perfResult.current.isSuccess).toBe(true))

    expect(apiClient.getAllocation).toHaveBeenCalled()
    expect(apiClient.getPerformance).toHaveBeenCalled()
  })

  it('fetches rebalance, tax-harvest, and projection', async () => {
    vi.mocked(apiClient.getRebalancePlan).mockResolvedValueOnce({ rebalance: [] } as any)
    vi.mocked(apiClient.getTaxHarvest).mockResolvedValueOnce({ harvest: [] } as any)
    vi.mocked(apiClient.getSipProjection).mockResolvedValueOnce({ projection: [] } as any)

    const wrapper = createWrapper()
    const { result: rebResult } = renderHook(() => useRebalancePlan('aggressive'), { wrapper })
    const { result: taxResult } = renderHook(() => useTaxHarvest(), { wrapper })
    const { result: sipResult } = renderHook(() => useSipProjection({ years: 10 }), { wrapper })

    await waitFor(() => expect(rebResult.current.isSuccess).toBe(true))
    await waitFor(() => expect(taxResult.current.isSuccess).toBe(true))
    await waitFor(() => expect(sipResult.current.isSuccess).toBe(true))
  })

  it('fetches xirrByFy, sipAttribution, whatIf, and mandateOverlap', async () => {
    vi.mocked(apiClient.getXirrByFy).mockResolvedValueOnce({ fy: [] } as any)
    vi.mocked(apiClient.getSipAttribution).mockResolvedValueOnce({ attribution: {} } as any)
    vi.mocked(apiClient.getWhatIf).mockResolvedValueOnce({ simulated: [] } as any)
    vi.mocked(apiClient.getMandateOverlap).mockResolvedValueOnce({ overlap: [] } as any)

    const wrapper = createWrapper()
    const { result: xirrRes } = renderHook(() => useXirrByFy(), { wrapper })
    const { result: sipAttrRes } = renderHook(() => useSipAttribution(), { wrapper })
    const { result: whatIfRes } = renderHook(() => useWhatIf({ isin: 'INF123' }, true), { wrapper })
    const { result: mandateRes } = renderHook(() => useMandateOverlap(), { wrapper })

    await waitFor(() => expect(xirrRes.current.isSuccess).toBe(true))
    await waitFor(() => expect(sipAttrRes.current.isSuccess).toBe(true))
    await waitFor(() => expect(whatIfRes.current.isSuccess).toBe(true))
    await waitFor(() => expect(mandateRes.current.isSuccess).toBe(true))
  })

  it('fetches insights, journey, fundInsights, and transactions', async () => {
    vi.mocked(apiClient.getInsights).mockResolvedValueOnce({ insights: [] } as any)
    vi.mocked(apiClient.getJourney).mockResolvedValueOnce({ milestones: [] } as any)
    vi.mocked(apiClient.getFundInsights).mockResolvedValueOnce({ fund: 'Mirae Asset' } as any)
    vi.mocked(apiClient.getTransactions).mockResolvedValueOnce({ transactions: [] } as any)

    const wrapper = createWrapper()
    const { result: insRes } = renderHook(() => useInsights(), { wrapper })
    const { result: jrnRes } = renderHook(() => useJourney(), { wrapper })
    const { result: fundInsRes } = renderHook(() => useFundInsights('INF209K01165', 'Mirae Large Cap'), { wrapper })
    const { result: txnRes } = renderHook(() => useTransactions('SBI Bluechip'), { wrapper })

    await waitFor(() => expect(insRes.current.isSuccess).toBe(true))
    await waitFor(() => expect(jrnRes.current.isSuccess).toBe(true))
    await waitFor(() => expect(fundInsRes.current.isSuccess).toBe(true))
    await waitFor(() => expect(txnRes.current.isSuccess).toBe(true))
  })
})
