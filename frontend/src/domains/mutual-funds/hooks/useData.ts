import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useSessionId, useFilters } from '../store/appStore'

// ── Build filter params from store ────────────────────────────────────────────
export function useFilterParams() {
  const f = useFilters()
  return {
    benchmark: f.benchmark,
    category: f.categories.join(','),
    amc: f.amcs.join(','),
    plan: f.plan,
    min_alloc: f.minAlloc,
  }
}

// ── Summary ───────────────────────────────────────────────────────────────────
export function useSummary(benchmark: string = 'Nifty 50') {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['summary', sid, benchmark],
    queryFn: () => apiClient.getSummary(sid!, { benchmark }),
    enabled: !!sid,
    staleTime: 2 * 60 * 1000,
  })
}

// ── Overview ──────────────────────────────────────────────────────────────────
export function useOverview(period: string, benchmark: string = 'Nifty 50') {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['overview', sid, period, benchmark],
    queryFn: () => apiClient.getOverview(sid!, { period, benchmark }),
    enabled: !!sid,
  })
}

// ── Benchmark Overlay ───────────────────────────────────────────────────────────
export function useBenchmarkOverlay(period: string, benchmarks: string[]) {
  const sid = useSessionId()
  const bString = benchmarks.join(',')
  return useQuery({
    queryKey: ['benchmark-overlay', sid, period, bString],
    queryFn: () => apiClient.getBenchmarkOverlay(sid!, { period, benchmarks: bString }),
    enabled: !!sid && benchmarks.length > 0,
  })
}

// ── Holdings ──────────────────────────────────────────────────────────────────
export function useHoldings(extra: Record<string, any> = {}) {
  const sid = useSessionId()
  const p = useFilterParams()
  return useQuery({
    queryKey: ['holdings', sid, p, extra],
    queryFn: () => apiClient.getHoldings(sid!, { ...p, ...extra }),
    enabled: !!sid,
  })
}

// ── Allocation ────────────────────────────────────────────────────────────────
export function useAllocation() {
  const sid = useSessionId()
  const p = useFilterParams()
  return useQuery({
    queryKey: ['allocation', sid, p],
    queryFn: () => apiClient.getAllocation(sid!, p),
    enabled: !!sid,
  })
}

// ── Performance ───────────────────────────────────────────────────────────────
export function usePerformance(period: string, extra: Record<string, any> = {}) {
  const sid = useSessionId()
  const p = useFilterParams()
  return useQuery({
    queryKey: ['performance', sid, period, p, extra],
    queryFn: () => apiClient.getPerformance(sid!, { ...p, period, ...extra }),
    enabled: !!sid,
  })
}

export function useRebalancePlan(profile: string) {
  const sid = useSessionId()
  return useQuery({
    queryKey:  ['rebalance', sid, profile],
    queryFn:   () => apiClient.getRebalancePlan(sid!, { profile }),
    enabled:   !!sid,
  })
}

// ── Tax ───────────────────────────────────────────────────────────────────────
export function useTax(fy: string = 'Current Portfolio', debt_slab: number = 30.0) {
  const sid = useSessionId()
  const p = useFilterParams()
  return useQuery({
    queryKey: ['tax', sid, p, fy, debt_slab],
    queryFn: () => apiClient.getTax(sid!, { ...p, fy, debt_slab }),
    enabled: !!sid,
  })
}

export function useTaxYears() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['tax-years', sid],
    queryFn: () => apiClient.getTaxYears(sid!),
    enabled: !!sid,
  })
}

export function useTaxOptimize() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['tax-optimize', sid],
    queryFn: () => apiClient.getTaxOptimize(sid!),
    enabled: !!sid,
  })
}

// ── Insights ──────────────────────────────────────────────────────────────────
export function useInsights() {
  const sid = useSessionId()
  const p = useFilterParams()
  return useQuery({
    queryKey: ['insights', sid, p],
    queryFn: () => apiClient.getInsights(sid!, p),
    enabled: !!sid,
  })
}

export function useJourney() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['journey', sid],
    queryFn: () => apiClient.getJourney(sid!),
    enabled: !!sid,
  })
}

export function useFundInsights(isin: string, name: string = '') {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['fund-insights', sid, isin, name],
    queryFn: () => apiClient.getFundInsights(sid!, isin, { name }),
    enabled: !!sid && !!isin && isin !== 'N/A',
    staleTime: 1000, // Reduced for verification
  })
}
export function useTransactions(fund = '') {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['transactions', sid, fund],
    queryFn: () => apiClient.getTransactions(sid!, { fund }),
    enabled: !!sid,
  })
}

export function useMarketSummary() {
  return useQuery({
    queryKey: ['market-summary'],
    queryFn: () => apiClient.getMarketSummary(),
    refetchInterval: 60 * 1000, // Poll every minute
  })
}

export function useMarketConfig() {
  return useQuery({
    queryKey: ['market-config'],
    queryFn: () => apiClient.getMarketConfig(),
  })
}
