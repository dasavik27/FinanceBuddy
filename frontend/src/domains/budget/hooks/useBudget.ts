import {
  keepPreviousData, useMutation, useQuery, useQueryClient, type UseQueryResult,
} from '@tanstack/react-query'
import { useCallback, useEffect } from 'react'

import { apiClient } from '../../../shared/api/client'
import type {
  BudgetCategoriesResponse, BudgetFilters, BudgetOverview, BudgetSessionMeta,
  BudgetTransaction, BudgetTransactionsPage, BudgetUploadResult,
  BudgetAccountsResponse, BudgetAccountMetaUpdate, BudgetTransfersResponse,
  BudgetRecurringResponse, BudgetForecast, BudgetAnomaliesResponse,
  BudgetReconciliationResponse, BudgetCoverageResponse, BudgetSankey,
  BudgetEnvelope,
} from '../types'

/**
 * Data hooks for the budget dashboard.
 *
 * This module used to be a `useState` + hand-rolled `Promise.all` fetcher whose three
 * getters ended in `catch { console.error; return null }`. Two consequences, both
 * user-visible: a 500 from the analytics API rendered the "No accounts uploaded yet"
 * empty state with an Upload CTA, and - because the dashboard applied whichever
 * response *arrived* last rather than whichever was *requested* last - typing "a" then
 * "b" in the search box could leave the results for "a" on screen. react-query keys by
 * query key and discards superseded results, so the race disappears here rather than
 * being patched with an AbortController.
 *
 * This mirrors domains/equity/hooks/useEquityData.ts and
 * domains/mutual-funds/hooks/useData.ts, which the budget module was written alongside
 * but did not use.
 */

// Budget data is derived from uploaded statements: it does not move on its own, it
// moves when the user uploads, edits a category, or re-runs the rules. Those paths
// invalidate explicitly, so the staleTime only has to cover tab switches.
const ANALYTICS = 2 * 60 * 1000
const SESSIONS = 5 * 60 * 1000

export type { BudgetFilters } from '../types'

/**
 * Filters as query params, dropping the ones that are "all" or blank.
 *
 * Returned as an object rather than a query string so the same value can be both the
 * axios `params` and part of the react-query key - two representations of the same
 * filter set would be two ways to miss the cache.
 */
export function toQueryParams(filters?: BudgetFilters): Record<string, string> {
  const params: Record<string, string> = {}
  if (!filters) return params

  const put = (key: string, value?: string) => {
    if (value && value.toLowerCase() !== 'all') params[key] = value
  }

  put('bank', filters.bank)
  put('account_type', filters.accountType)
  put('txn_type', filters.txnType)
  put('date_range', filters.dateRange)
  put('amount_bracket', filters.amountBracket)
  put('payment_mode', filters.paymentMode)
  put('category', filters.category)
  put('flow', filters.flow)
  if (filters.fromDate) params.from_date = filters.fromDate
  if (filters.toDate) params.to_date = filters.toDate
  if (filters.search && filters.search.trim()) params.search = filters.search.trim()

  return params
}

/** The server's `detail` string if there is one, else something usable. */
export function budgetErrorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)
    ?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  const message = (error as { message?: string } | null)?.message
  return message || fallback
}

/** HTTP status of a failed query, or undefined. */
export function budgetErrorStatus(error: unknown): number | undefined {
  return (error as { response?: { status?: number } } | null)?.response?.status
}

/**
 * Fall back to the consolidated view when the selected session is gone.
 *
 * A session id that is not the caller's now answers 404 rather than leaking rows, so
 * a stale id in component state - a deleted upload, or one copied from elsewhere -
 * is an expected state, not an exception. Without this the dashboard sat on a
 * permanent error over a session the user could not deselect.
 */
export function useResetSessionOnMissing(
  error: unknown,
  sessionId: string,
  onReset: (sid: string) => void,
) {
  const status = budgetErrorStatus(error)

  useEffect(() => {
    if (status === 404 && sessionId !== 'overall') {
      onReset('overall')
    }
  }, [status, sessionId, onReset])

  return status
}

export function useBudgetSessions(): UseQueryResult<BudgetSessionMeta[]> {
  return useQuery({
    queryKey: ['budget', 'sessions'],
    queryFn: () => apiClient.getBudgetSessions(),
    staleTime: SESSIONS,
  })
}

export function useBudgetOverview(
  sessionId: string,
  filters: BudgetFilters,
): UseQueryResult<BudgetOverview> {
  const params = toQueryParams(filters)
  return useQuery({
    queryKey: ['budget', 'overview', sessionId, params],
    queryFn: () => apiClient.getBudgetOverview(sessionId, params),
    enabled: !!sessionId,
    staleTime: ANALYTICS,
    // A filter change changes the key. Without this the whole dashboard unmounts to a
    // spinner between keystrokes of a settled search term.
    placeholderData: keepPreviousData,
    // A 404 here means "no rows for this session", which is a state, not a transient
    // failure - retrying it just delays the empty state by a round trip.
    retry: (count, error) => budgetErrorStatus(error) !== 404 && count < 1,
  })
}

export function useBudgetCategories(
  sessionId: string,
  filters: BudgetFilters,
): UseQueryResult<BudgetCategoriesResponse> {
  const params = toQueryParams(filters)
  return useQuery({
    queryKey: ['budget', 'categories', sessionId, params],
    queryFn: () => apiClient.getBudgetCategories(sessionId, params),
    enabled: !!sessionId,
    staleTime: ANALYTICS,
    placeholderData: keepPreviousData,
    retry: (count, error) => budgetErrorStatus(error) !== 404 && count < 1,
  })
}

/**
 * How many transactions to pull in one request.
 *
 * The endpoint pages, and the table applies further filters of its own on the client,
 * so the fetch has to be generous enough that local filtering still has something to
 * work with. 1,000 covers a year across three accounts; past that the UI tells the
 * user it is truncated and offers to fetch more, rather than quietly showing a subset.
 */
export const TRANSACTIONS_PAGE_SIZE = 1000

export function useBudgetTransactions(
  sessionId: string,
  filters: BudgetFilters,
  limit: number = TRANSACTIONS_PAGE_SIZE,
): UseQueryResult<BudgetTransactionsPage> {
  const params = { ...toQueryParams(filters), limit }
  return useQuery({
    queryKey: ['budget', 'transactions', sessionId, params],
    queryFn: () => apiClient.getBudgetTransactions(sessionId, params),
    enabled: !!sessionId,
    staleTime: ANALYTICS,
    placeholderData: keepPreviousData,
    retry: (count, error) => budgetErrorStatus(error) !== 404 && count < 1,
  })
}

/**
 * Invalidate every budget query.
 *
 * The three callers that need this - upload, delete, and any transaction or rule
 * re-categorization - each used to both mutate a piece of filter state (which
 * re-triggered the fetch effect) *and* call the fetcher directly, so one inline
 * category edit cost seven to eight requests. Invalidation refetches only what is
 * currently mounted, once.
 */
export function useInvalidateBudget() {
  const qc = useQueryClient()
  // Stable identity: it is passed to memoised children as a refresh callback.
  return useCallback(() => { qc.invalidateQueries({ queryKey: ['budget'] }) }, [qc])
}

/** The three analytics queries only - the session list and the rules are untouched. */
const ANALYTICS_KEYS = new Set(['overview', 'categories', 'transactions'])

/**
 * Invalidate just the analytics.
 *
 * Re-categorizing one transaction changes the KPIs, the category breakdown and the
 * row itself, and nothing else. The blanket refresh this replaces also re-listed the
 * sessions, so an inline edit cost four requests where three are the correct number.
 */
export function useInvalidateBudgetAnalytics() {
  const qc = useQueryClient()
  return useCallback(() => {
    qc.invalidateQueries({
      predicate: (query) => {
        const key = query.queryKey
        return Array.isArray(key) && key[0] === 'budget' && ANALYTICS_KEYS.has(key[1] as string)
      },
    })
  }, [qc])
}

export function useUploadStatement() {
  const invalidate = useInvalidateBudget()
  return useMutation<BudgetUploadResult, unknown, { file: File; bank: string; accountType: string }>({
    mutationFn: ({ file, bank, accountType }) =>
      apiClient.uploadBudgetStatement(file, bank, accountType),
    onSuccess: invalidate,
  })
}

export function useDeleteBudgetSession() {
  const invalidate = useInvalidateBudget()
  return useMutation<any, unknown, string>({
    mutationFn: (sessionId) => apiClient.deleteBudgetSession(sessionId),
    onSuccess: invalidate,
  })
}

// ── Accounts, insights and planning ──────────────────────────────────────────
//
// These all derive from the same uploaded statements as the analytics queries and are
// memoized server-side on a content hash, so they share the ANALYTICS staleTime. Each
// is a separate query rather than one aggregate call: the Accounts tab does not need
// the Sankey, and a tab the user never opens should cost nothing.

/**
 * Shared options. 404 means "no data for this session", which is not worth retrying.
 *
 * `error` is typed as Error rather than unknown: react-query infers the query's error
 * type from this callback, and `unknown` widens every hook's result to
 * UseQueryResult<T, unknown>, which no longer matches the declared return type.
 */
const notFoundAware = (count: number, error: Error) =>
  budgetErrorStatus(error) !== 404 && count < 1

const insightQuery = { staleTime: ANALYTICS, retry: notFoundAware }

export function useBudgetAccounts(sessionId: string): UseQueryResult<BudgetAccountsResponse> {
  return useQuery({
    queryKey: ['budget', 'accounts', sessionId],
    queryFn: () => apiClient.getBudgetAccounts(sessionId),
    enabled: !!sessionId,
    ...insightQuery,
  })
}

export function useUpdateBudgetAccount() {
  const qc = useQueryClient()
  return useMutation<any, unknown, { accountKey: string; patch: BudgetAccountMetaUpdate }>({
    mutationFn: ({ accountKey, patch }) => apiClient.updateBudgetAccount(accountKey, patch),
    // A credit limit changes utilisation, and an opening balance changes every balance
    // and the net worth built on it - so this invalidates more than the accounts list.
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['budget'] }) },
  })
}

export function useBudgetTransfers(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetTransfersResponse> {
  return useQuery({
    queryKey: ['budget', 'transfers', sessionId],
    queryFn: () => apiClient.getBudgetTransfers(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetRecurring(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetRecurringResponse> {
  return useQuery({
    queryKey: ['budget', 'recurring', sessionId],
    queryFn: () => apiClient.getBudgetRecurring(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetForecast(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetForecast> {
  return useQuery({
    queryKey: ['budget', 'forecast', sessionId],
    queryFn: () => apiClient.getBudgetForecast(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetAnomalies(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetAnomaliesResponse> {
  return useQuery({
    queryKey: ['budget', 'anomalies', sessionId],
    queryFn: () => apiClient.getBudgetAnomalies(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetReconciliation(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetReconciliationResponse> {
  return useQuery({
    queryKey: ['budget', 'reconciliation', sessionId],
    queryFn: () => apiClient.getBudgetReconciliation(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetCoverage(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetCoverageResponse> {
  return useQuery({
    queryKey: ['budget', 'coverage', sessionId],
    queryFn: () => apiClient.getBudgetCoverage(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetSankey(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetSankey> {
  return useQuery({
    queryKey: ['budget', 'sankey', sessionId],
    queryFn: () => apiClient.getBudgetSankey(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useBudgetEnvelopes(
  sessionId: string, enabled = true,
): UseQueryResult<BudgetEnvelope[]> {
  return useQuery({
    queryKey: ['budget', 'envelopes', sessionId],
    queryFn: () => apiClient.getBudgetEnvelopes(sessionId),
    enabled: enabled && !!sessionId,
    ...insightQuery,
  })
}

export function useSetBudgetEnvelope() {
  const qc = useQueryClient()
  return useMutation<any, unknown, { category: string; monthlyCap: number | null }>({
    mutationFn: ({ category, monthlyCap }) => apiClient.setBudgetEnvelope(category, monthlyCap),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['budget', 'envelopes'] }) },
  })
}
