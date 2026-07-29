import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../../../shared/api/client'
import { useTaxSessionId } from '../../../shared/store/appStore'

/**
 * Invalidate every session-derived query for one session.
 *
 * Scoped by `sid`. The previous version invalidated bare `['tax-expert-summary']`
 * with no session or regime, so a single deduction edit invalidated *both* regimes
 * plus capital-gains plus compare — refetching queries the user was not even
 * looking at, each of which is a round trip to a free-tier backend.
 *
 * Regime is intentionally NOT scoped: an override changes the computation for both
 * regimes, so both must refresh. Only the currently-mounted ones actually refetch.
 */
function invalidateSessionQueries(queryClient: ReturnType<typeof useQueryClient>, sid?: string | null) {
  if (!sid) return
  for (const key of ['tax-expert-summary', 'tax-expert-capital-gains', 'tax-expert-compare', 'tax-expert-income']) {
    queryClient.invalidateQueries({ queryKey: [key, sid] })
  }
}

export function useTaxExpertOverrides() {
  const sid = useTaxSessionId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (overrides: any) => apiClient.postTaxOverrides(sid!, overrides),
    onSuccess: () => invalidateSessionQueries(queryClient, sid),
  })
}

export function useUploadITR() {
  const sid = useTaxSessionId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => apiClient.uploadITR(sid!, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tax-expert-itr', sid] })
    }
  })
}

export function useITRData() {
  const sid = useTaxSessionId()
  return useQuery({
    queryKey: ['tax-expert-itr', sid],
    queryFn: () => apiClient.getITRData(sid!),
    enabled: !!sid,
    retry: false
  })
}

export function useTaxExpertTransactionCost() {
  const sid = useTaxSessionId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: { category: string, sr: number, new_cost: number }) =>
      apiClient.updateTransactionCost(sid!, params.category, params.sr, params.new_cost),
    onSuccess: () => invalidateSessionQueries(queryClient, sid),
  })
}

export function useTaxExpertSummary(regime: string = 'new') {
  const sid = useTaxSessionId()
  return useQuery({
    queryKey: ['tax-expert-summary', sid, regime],
    queryFn: () => apiClient.getTaxExpertSummary(sid!, regime),
    enabled: !!sid,
  })
}

export function useTaxExpertIncome() {
  const sid = useTaxSessionId()
  return useQuery({
    queryKey: ['tax-expert-income', sid],
    queryFn: () => apiClient.getTaxExpertIncome(sid!),
    enabled: !!sid,
  })
}

export function useTaxExpertCapitalGains() {
  const sid = useTaxSessionId()
  return useQuery({
    queryKey: ['tax-expert-capital-gains', sid],
    queryFn: () => apiClient.getTaxExpertCapitalGains(sid!),
    enabled: !!sid,
  })
}

export function useTaxRegimeComparison() {
  const sid = useTaxSessionId()
  return useQuery({
    queryKey: ['tax-expert-compare', sid],
    queryFn: () => apiClient.compareTaxRegimes(sid!),
    enabled: !!sid,
  })
}

/**
 * Display-only tax rules (limits, rates, tooltip copy) served by the backend.
 *
 * Session-independent and constant for a given deployment, so it never goes stale
 * and is never refetched. This replaces the bundled tax_rules.json duplicate.
 */
export function useTaxRules() {
  return useQuery({
    queryKey: ['tax-rules'],
    queryFn: () => apiClient.getTaxRules(),
    staleTime: Infinity,
    gcTime: Infinity,
  })
}
