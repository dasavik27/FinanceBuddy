import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api/client'
import { useTaxSessionId } from '../store/appStore'

export function useTaxExpertOverrides() {
  const sid = useTaxSessionId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (overrides: any) => apiClient.postTaxOverrides(sid!, overrides),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tax-expert-summary'] })
      queryClient.invalidateQueries({ queryKey: ['tax-expert-capital-gains'] })
      queryClient.invalidateQueries({ queryKey: ['tax-expert-compare'] })
    }
  })
}

export function useParseForm16() {
  const sid = useTaxSessionId()
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => apiClient.parseForm16(sid!, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tax-expert-summary'] })
      queryClient.invalidateQueries({ queryKey: ['tax-expert-compare'] })
    }
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tax-expert-summary'] })
      queryClient.invalidateQueries({ queryKey: ['tax-expert-capital-gains'] })
      queryClient.invalidateQueries({ queryKey: ['tax-expert-compare'] })
    }
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
