import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useSessionId, useFilters } from '../store/appStore'

// ── Build filter params from store ────────────────────────────────────────────
function useFilterParams() {
  const f = useFilters()
  return {
    benchmark: f.benchmark,
    category:  f.categories.join(','),
    amc:       f.amcs.join(','),
    plan:      f.plan,
    min_alloc: f.minAlloc,
  }
}

// ── Summary ───────────────────────────────────────────────────────────────────
export function useSummary() {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey:  ['summary', sid, p],
    queryFn:   () => apiClient.getSummary(sid!, p),
    enabled:   !!sid,
    staleTime: 2 * 60 * 1000,
  })
}

// ── Overview ──────────────────────────────────────────────────────────────────
export function useOverview(period: string) {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey:  ['overview', sid, period, p],
    queryFn:   () => apiClient.getOverview(sid!, { ...p, period }),
    enabled:   !!sid,
  })
}

// ── Holdings ──────────────────────────────────────────────────────────────────
export function useHoldings(extra: Record<string, any> = {}) {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey:  ['holdings', sid, p, extra],
    queryFn:   () => apiClient.getHoldings(sid!, { ...p, ...extra }),
    enabled:   !!sid,
  })
}

// ── Allocation ────────────────────────────────────────────────────────────────
export function useAllocation() {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey:  ['allocation', sid, p],
    queryFn:   () => apiClient.getAllocation(sid!, p),
    enabled:   !!sid,
  })
}

// ── Performance ───────────────────────────────────────────────────────────────
export function usePerformance(period: string, extra: Record<string, any> = {}) {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey:  ['performance', sid, period, p, extra],
    queryFn:   () => apiClient.getPerformance(sid!, { ...p, period, ...extra }),
    enabled:   !!sid,
  })
}

// ── Tax ───────────────────────────────────────────────────────────────────────
export function useTax() {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey: ['tax', sid, p],
    queryFn:  () => apiClient.getTax(sid!, p),
    enabled:  !!sid,
  })
}

// ── Insights ──────────────────────────────────────────────────────────────────
export function useInsights() {
  const sid = useSessionId()
  const p   = useFilterParams()
  return useQuery({
    queryKey: ['insights', sid, p],
    queryFn:  () => apiClient.getInsights(sid!, p),
    enabled:  !!sid,
  })
}

// ── Transactions ──────────────────────────────────────────────────────────────
export function useTransactions(fund = '') {
  const sid = useSessionId()
  return useQuery({
    queryKey: ['transactions', sid, fund],
    queryFn:  () => apiClient.getTransactions(sid!, { fund }),
    enabled:  !!sid,
  })
}
