import { useCallback } from 'react'
import { useQueryClient, type QueryClient } from '@tanstack/react-query'

/** Root query keys used by Mutual Funds tab hooks (useData.ts + Compare). */
const MF_ROOT_KEYS = new Set([
  'summary',
  'overview',
  'benchmark-overlay',
  'holdings',
  'allocation',
  'performance',
  'rebalance',
  'tax-harvest',
  'sip-projection',
  'xirr-by-fy',
  'sip-attribution',
  'what-if',
  'mandate-overlap',
  'insights',
  'journey',
  'fund-insights',
  'transactions',
  'rollingReturns',
  'assetHistory',
  'tickerSearch',
  'whatIfSearch',
])

export function invalidateMutualFundQueries(qc: QueryClient) {
  return qc.invalidateQueries({
    predicate: (q) => typeof q.queryKey[0] === 'string' && MF_ROOT_KEYS.has(q.queryKey[0] as string),
  })
}

export function invalidateEquityQueries(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: ['equity'] })
}

export function invalidateTaxQueries(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: ['tax-expert-summary'] }),
    qc.invalidateQueries({ queryKey: ['tax-expert-income'] }),
    qc.invalidateQueries({ queryKey: ['tax-expert-capital-gains'] }),
    qc.invalidateQueries({ queryKey: ['tax-expert-compare'] }),
    qc.invalidateQueries({ queryKey: ['tax-expert-itr'] }),
    qc.invalidateQueries({ queryKey: ['tax-history'] }),
    qc.invalidateQueries({ queryKey: ['tax-sessions'] }),
    qc.invalidateQueries({ queryKey: ['accounts-summary'] }),
  ])
}

export function invalidateBudgetQueries(qc: QueryClient) {
  return qc.invalidateQueries({ queryKey: ['budget'] })
}

/** Invalidate every tab cache for the active domain after upload / delete / restore. */
export function invalidateModuleQueries(qc: QueryClient, module: string) {
  switch (module) {
    case 'mutual_funds':
      return invalidateMutualFundQueries(qc)
    case 'equity':
    case 'indian_stocks':
      return invalidateEquityQueries(qc)
    case 'tax_expert':
      return invalidateTaxQueries(qc)
    case 'budget':
      return invalidateBudgetQueries(qc)
    default:
      return qc.invalidateQueries()
  }
}

export function useInvalidateModuleQueries(module: string) {
  const qc = useQueryClient()
  return useCallback(() => invalidateModuleQueries(qc, module), [qc, module])
}
