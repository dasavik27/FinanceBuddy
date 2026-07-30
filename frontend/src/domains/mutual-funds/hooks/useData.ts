import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { apiClient } from '../../../shared/api/client'
import { useSessionId, useFilters } from '../../../shared/store/appStore'

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
    // The search box is debounced, so a settled keystroke still changes this key.
    // Without keepPreviousData the grid unmounts to a loading state on every change;
    // with it, the previous rows stay visible until the new ones arrive.
    placeholderData: keepPreviousData,
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

// ── Tax Harvest ───────────────────────────────────────────────────────────────
export function useTaxHarvest() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['tax-harvest', sid],
    queryFn:  () => apiClient.getTaxHarvest(sid!),
    enabled:  !!sid,
    staleTime: 5 * 60 * 1000,
  })
}

// ── SIP Step-Up Projection ────────────────────────────────────────────────────
export function useSipProjection(params: Record<string, any> = {}) {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['sip-projection', sid, params],
    queryFn:  () => apiClient.getSipProjection(sid!, params),
    enabled:  !!sid,
    staleTime: 5 * 60 * 1000,
  })
}

// ── XIRR by Financial Year ─────────────────────────────────────────────────────
export function useXirrByFy() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['xirr-by-fy', sid],
    queryFn:  () => apiClient.getXirrByFy(sid!),
    enabled:  !!sid,
    staleTime: 5 * 60 * 1000,
  })
}

// ── SIP vs Lumpsum Attribution ────────────────────────────────────────────────
export function useSipAttribution() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['sip-attribution', sid],
    queryFn:  () => apiClient.getSipAttribution(sid!),
    enabled:  !!sid,
    staleTime: 5 * 60 * 1000,
  })
}

// ── What-If SIP Simulator (candidate fund, not yet held) ──────────────────────
export function useWhatIf(params: Record<string, any>, enabled: boolean) {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['what-if', sid, params],
    queryFn:  () => apiClient.getWhatIf(sid!, params),
    enabled:  !!sid && enabled,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Mandate Overlap (category/AMC-level proxy for stock overlap) ─────────────
export function useMandateOverlap() {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['mandate-overlap', sid],
    queryFn:  () => apiClient.getMandateOverlap(sid!),
    enabled:  !!sid,
    staleTime: 5 * 60 * 1000,
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
    // Was 1s ("Reduced for verification"), which meant reopening the same fund's
    // drawer refetched every time. The underlying NAV data is end-of-day.
    staleTime: 10 * 60 * 1000,
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
