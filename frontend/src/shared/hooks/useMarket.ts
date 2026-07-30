import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api/client'

/**
 * Live market indices.
 *
 * `enabled` matters here. Topbar is mounted for the whole authenticated session, but
 * the widget this feeds is only rendered when activeModule === 'indian_stocks'. So
 * every user was burning one /market/summary request per minute, forever, for pixels
 * they never saw — against an upstream (yfinance) whose worst-case timeouts sum to
 * roughly 90 seconds.
 */
export function useMarketSummary(enabled = true) {
  return useQuery({
    queryKey: ['market-summary'],
    queryFn: () => apiClient.getMarketSummary(),
    enabled,
    refetchInterval: 60 * 1000, // Poll every minute
    refetchIntervalInBackground: false,
  })
}

export function useMarketConfig() {
  return useQuery({
    queryKey: ['market-config'],
    queryFn: () => apiClient.getMarketConfig(),
  })
}
