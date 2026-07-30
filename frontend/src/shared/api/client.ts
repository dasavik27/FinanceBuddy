import axios from 'axios'
import { useAppStore } from '../store/appStore'
import type {
  ParseResponse, Summary, OverviewData, Holding, FundResult,
  PerformanceData, AllocationData, InsightsData,
} from './types'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' })

api.interceptors.request.use((config) => {
  const pan = useAppStore.getState().pan
  if (pan) {
    config.headers['X-User-PAN'] = pan
  }
  return config
})

// ── API calls ────────────────────────────────────────────────────────────────
export const apiClient = {
  /** Parses CAS PDF statement and initializes a portfolio session. */
  parseFile: async (file: File, password: string, uploadType: string = 'mutual_funds'): Promise<ParseResponse> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', password)
    const { data } = await api.post<ParseResponse>('/mutual-funds/portfolio/parse', fd, {
      headers: {
        'X-Upload-Type': uploadType
      }
    })
    return data
  },

  getHistory: async (uploadType: string = 'mutual_funds'): Promise<any> => {
    const { data } = await api.get('/history/', {
      headers: {
        'X-Upload-Type': uploadType
      }
    })
    return data
  },

  /** Fetches high-level executive summary metrics (XIRR, Total Value). */
  getSummary: async (sid: string, params: Record<string, any> = {}): Promise<Summary> => {
    const { data } = await api.get<Summary>(`/mutual-funds/overview/${sid}/summary`, { params })
    return data
  },

  syncPortfolio: async (sid: string): Promise<any> => {
    const { data } = await api.post(`/mutual-funds/portfolio/${sid}/sync`)
    return data
  },

  /** Retrieves core time-series charting data for the overview dashboard. */
  getOverview: async (sid: string, params: Record<string, any> = {}): Promise<OverviewData> => {
    const { data } = await api.get<OverviewData>(`/mutual-funds/overview/${sid}/overview`, { params })
    return data
  },

  getBenchmarkOverlay: async (sid: string, params: { period: string; benchmarks: string }): Promise<{ dates: string[]; series: Record<string, number[]> }> => {
    const { data } = await api.get<{ dates: string[]; series: Record<string, number[]> }>(`/mutual-funds/overview/${sid}/benchmark-overlay`, { params })
    return data
  },

  getHoldings: async (sid: string, params: Record<string, any> = {}): Promise<{ holdings: Holding[]; total: number; cap_types: string[] }> => {
    const { data } = await api.get(`/mutual-funds/holdings/${sid}/holdings`, { params })
    return data
  },

  getAllocation: async (sid: string, params: Record<string, any> = {}): Promise<AllocationData> => {
    const { data } = await api.get<AllocationData>(`/mutual-funds/overview/${sid}/allocation`, { params })
    return data
  },

  /** Executes multi-metric peer comparison and calculates Portfolio Health Score. */
  getPerformance: async (sid: string, params: Record<string, any> = {}): Promise<PerformanceData> => {
    const { data } = await api.get<PerformanceData>(`/mutual-funds/performance/${sid}/performance`, { params })
    return data
  },

  getRebalancePlan: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/rebalance/${sid}/plan`, { params })
    return data
  },

  getTaxHarvest: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/tax-harvest`)
    return data
  },

  getSipProjection: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/sip-projection`, { params })
    return data
  },

  getXirrByFy: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/xirr-by-fy`)
    return data
  },

  getSipAttribution: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/sip-attribution`)
    return data
  },

  getWhatIf: async (sid: string, params: Record<string, any>): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/what-if`, { params })
    return data
  },

  getMandateOverlap: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/planning/${sid}/mandate-overlap`)
    return data
  },


  getInsights: async (sid: string, params: Record<string, any> = {}): Promise<InsightsData> => {
    const { data } = await api.get<InsightsData>(`/mutual-funds/insights/${sid}/insights`, { params })
    return data
  },

  getJourney: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/journey/${sid}`)
    return data
  },

  getFundInsights: async (sid: string, isin: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/holdings/${sid}/fund-insights/${isin}`, { params })
    return data
  },

  getTransactions: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/holdings/${sid}/transactions`, { params })
    return data
  },


  getCategoryPeers: async (category: string): Promise<{ peers: any[], fallback_triggered?: boolean }> => {
    const { data } = await api.get('/mutual-funds/compare/peers', { params: { category } })
    return data
  },

  searchTicker: async (q: string): Promise<any> => {
    const { data } = await api.get('/mutual-funds/compare/search', { params: { q } })
    return data
  },

  getBenchmarkHistory: async (ticker: string, days = 365): Promise<any> => {
    const { data } = await api.get('/mutual-funds/compare/history', { params: { ticker, days } })
    return data
  },

  getRollingReturns: async (sid: string, isin: string, window = 3): Promise<any> => {
    const { data } = await api.get(`/mutual-funds/performance/${sid}/rolling/${isin}`, { params: { window } })
    return data
  },

  getMarketSummary: async (): Promise<any> => {
    const { data } = await api.get('/market/summary')
    return data
  },

  getMarketConfig: async (): Promise<{ cache_ttl: number }> => {
    const { data } = await api.get('/market/config')
    return data
  },

  updateMarketConfig: async (ttl: number): Promise<any> => {
    const { data } = await api.post(`/market/config?ttl=${ttl}`)
    return data
  },

  // ── Tax Expert API ──────────────────────────────────────────────────────

  /** Parse AIS PDF and create a tax computation session. */
  parseAIS: async (file: File): Promise<any> => {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post('/tax-expert/parse-ais', fd)
    return data
  },

  reconcileBrokerFile: async (sessionId: string, file: File): Promise<any> => {
    const fd = new FormData()
    fd.append('broker_file', file)
    const res = await api.post(`/tax-expert/${sessionId}/tax/reconcile-broker`, fd)
    return res.data
  },
  
  // ── Accounts / Vault Manager ───────────────────────────────────────────────
  getAccountsSummary: async (): Promise<any> => {
    const res = await api.get('/accounts/summary')
    return res.data
  },
  
  purgeAccount: async (panId: string): Promise<any> => {
    const res = await api.delete(`/accounts/${panId}`)
    return res.data
  },

  clearSystemCaches: async (): Promise<any> => {
    const res = await api.post('/accounts/clear_caches')
    return res.data
  },

  uploadITR: async (sid: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    const { data } = await api.post(`/tax-expert/${sid}/tax/itr`, fd)
    return data
  },

  getITRData: async (sid: string) => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/itr`)
    return data.itr_data
  },

  /** Get complete tax computation summary for a given regime. */
  getTaxExpertSummary: async (sid: string, regime: string = 'new'): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/summary`, { params: { regime } })
    return data
  },

  /** Get detailed income breakdown from AIS data. */
  getTaxExpertIncome: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/income`)
    return data
  },

  /** Get detailed capital gains breakdown. */
  getTaxExpertCapitalGains: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/capital-gains`)
    return data
  },

  updateTransactionCost: async (sid: string, category: string, sr: number, new_cost: number): Promise<any> => {
    const { data } = await api.post(`/tax-expert/${sid}/tax/capital-gains/transaction`, { category, sr, new_cost })
    return data
  },

  postTaxOverrides: async (sid: string, overrides: any, regime?: string): Promise<any> => {
    const url = regime ? `/tax-expert/${sid}/tax/recalculate?regime=${regime}` : `/tax-expert/${sid}/tax/recalculate`
    const { data } = await api.post(url, overrides)
    return data
  },

  /** Compare Old vs New regime side-by-side. */
  compareTaxRegimes: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/compare-regimes`)
    return data
  },

  /**
   * Display-only tax rules and tooltip copy.
   *
   * Replaces the frontend's own copy of tax_rules.json, which was byte-identical
   * to the backend's with no sync mechanism. Session-independent and static per
   * deployment, so it is cached indefinitely.
   */
  getTaxRules: async (): Promise<any> => {
    const { data } = await api.get('/tax-expert/rules')
    return data
  },

  /** Paginated access to a detail list no longer inlined in /tax/summary. */
  getTaxDetails: async (sid: string, bucket: string, offset = 0, limit = 200): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/details/${bucket}`, {
      params: { offset, limit },
    })
    return data
  },
}

export default api
