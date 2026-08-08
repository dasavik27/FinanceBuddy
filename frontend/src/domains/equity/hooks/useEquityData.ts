import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useEffect } from 'react'

import { apiClient } from '../../../shared/api/client'
import { useAppStore, useEquitySessionId as useStoreEquitySessionId } from '../../../shared/store/appStore'
import type {
  EquityAllocation, EquityHoldingsResponse, EquityInsights, EquityPerformance,
  EquityPnl, EquitySummary, EquitySortColumn, StockAnalysis, StockSearchResult,
} from '../types'

/**
 * Data hooks for the equity dashboard.
 *
 * The equity tabs each ran their own `useEffect` + `useState<any>` + `.catch(console.error)`,
 * which is why they had no cache (every tab visit refetched), no request dedup, and
 * three live race conditions: two fast clicks fired two GETs and `.then(setData)`
 * applied whichever *arrived* last, not whichever was *requested* last. react-query
 * keys by query key and discards superseded results, so those disappear here rather
 * than being individually patched.
 *
 * This mirrors domains/mutual-funds/hooks/useData.ts, which the equity module was
 * written alongside but did not use.
 */

// Tuned to what the data actually is. Holdings and valuations move with the market;
// sector allocation and the analyzer's fundamentals do not move intraday.
const LIVE = 60 * 1000
const SETTLED = 5 * 60 * 1000

/** Re-exported from the store so equity components have one import for data access. */
export function useEquitySessionId(): string | null {
  return useStoreEquitySessionId() ?? null
}

/**
 * Clear a stale equity session when the backend no longer knows it.
 *
 * Equity sessions live in a bounded in-process LRU, so on a free-tier host a dropped
 * session is the *expected* failure, not an exception. Without this the dashboard
 * showed a permanent "Failed to load" over a still-populated session id in
 * localStorage - a screen the user could not leave without clearing storage. Copied
 * from the tax-expert dashboard, which already handled it.
 */
export function useClearSessionOnMissing(error: unknown) {
  const clearSession = useAppStore((s) => s.clearSession)
  const status = (error as { response?: { status?: number } } | null)?.response?.status

  useEffect(() => {
    if (status === 404) {
      clearSession('equity')
    }
  }, [status, clearSession])

  return status
}

export function useEquitySummary(): UseQueryResult<EquitySummary> {
  const sid = useEquitySessionId()
  return useQuery({
    queryKey: ['equity', 'summary', sid],
    queryFn: () => apiClient.getEquitySummary(sid!),
    enabled: !!sid,
    staleTime: LIVE,
  })
}

export function useEquityAllocation(): UseQueryResult<EquityAllocation> {
  const sid = useEquitySessionId()
  return useQuery({
    queryKey: ['equity', 'allocation', sid],
    queryFn: () => apiClient.getEquityAllocation(sid!),
    enabled: !!sid,
    staleTime: SETTLED,
  })
}

export function useEquityHoldings(
  sortBy: EquitySortColumn = 'current_value',
  ascending = false,
): UseQueryResult<EquityHoldingsResponse> {
  const sid = useEquitySessionId()
  return useQuery({
    queryKey: ['equity', 'holdings', sid, sortBy, ascending],
    queryFn: () => apiClient.getEquityHoldings(sid!, { sort_by: sortBy, ascending }),
    enabled: !!sid,
    staleTime: LIVE,
    // Keep prior rows only when the session is unchanged (sort/filter). Never flash
    // another portfolio's holdings after upload / switch / delete.
    placeholderData: (prev, prevQuery) =>
      (prevQuery?.queryKey?.[2] === sid ? prev : undefined),
  })
}

export function useEquityPnl(): UseQueryResult<EquityPnl> {
  const sid = useEquitySessionId()
  return useQuery({
    queryKey: ['equity', 'pnl', sid],
    queryFn: () => apiClient.getEquityPnl(sid!),
    enabled: !!sid,
    staleTime: LIVE,
  })
}

export function useEquityPerformance(
  period: string,
  benchmark: string,
): UseQueryResult<EquityPerformance> {
  const sid = useEquitySessionId()
  return useQuery({
    queryKey: ['equity', 'performance', sid, period, benchmark],
    queryFn: () => apiClient.getEquityPerformance(sid!, { period, benchmark }),
    enabled: !!sid,
    staleTime: SETTLED,
    placeholderData: (prev, prevQuery) =>
      (prevQuery?.queryKey?.[2] === sid ? prev : undefined),
  })
}

export function useEquityInsights(): UseQueryResult<EquityInsights> {
  const sid = useEquitySessionId()
  return useQuery({
    queryKey: ['equity', 'insights', sid],
    queryFn: () => apiClient.getEquityInsights(sid!),
    enabled: !!sid,
    staleTime: LIVE,
  })
}

/**
 * Stock search. `query` must already be debounced by the caller - a key change is a
 * fetch, so passing a raw input value here reproduces the one-request-per-keystroke
 * behaviour this replaces.
 */
export function useStockSearch(query: string): UseQueryResult<{ results: StockSearchResult[] }> {
  const trimmed = query.trim()
  return useQuery({
    queryKey: ['equity', 'stock-search', trimmed],
    queryFn: () => apiClient.searchStocks(trimmed),
    enabled: trimmed.length >= 2,
    staleTime: SETTLED,
    placeholderData: keepPreviousData,
  })
}

export function useStockAnalysis(symbol: string | null): UseQueryResult<StockAnalysis> {
  return useQuery({
    queryKey: ['equity', 'stock-analysis', symbol],
    queryFn: () => apiClient.analyzeStock(symbol!),
    enabled: !!symbol,
    staleTime: SETTLED,
  })
}
