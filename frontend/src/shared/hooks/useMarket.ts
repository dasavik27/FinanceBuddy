import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

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
