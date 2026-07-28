import axios from 'axios'
import { useAppStore } from '../store/appStore'

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((config) => {
  const pan = useAppStore.getState().pan
  if (pan) {
    config.headers['X-User-PAN'] = pan
  }
  return config
})

// ── Types ────────────────────────────────────────────────────────────────────
export interface ParseResponse {
  session_id: string
  is_partial: boolean
  fund_count: number
  amc_count: number
  categories: string[]
  amcs: string[]
  benchmarks: string[]
}

export interface Summary {
  total_value: number
  total_invested: number
  total_gain: number
  gain_pct: number
  portfolio_xirr: number
  bench_xirr: number
  bench_cagr: number
  alpha: number
  port_score: number
  expense_drag: number
  sip_score: number
  returns: number
  annualized: number
  num_funds: number
  num_amcs: number
  is_partial: boolean
  is_absolute?: boolean
}

export interface OverviewData {
  port_pct: number
  bench_pct: number
  port_value: number
  bench_value: number
  use_xirr: boolean
  benchmark_name: string
  period: string
  chart: {
    dates: string[]
    portfolio: number[]
    benchmark: number[]
  }
}

export interface Holding {
  Fund: string
  AMC: string
  Category: string
  Plan: string
  'Cap Type': string
  Units: number
  Invested: number
  'Market Value': number
  Gain: number
  'Gain%': number
  'Weight%': number
  color: string
}

export interface FundResult {
  fund: string
  isin: string
  category: string
  plan: string
  amc: string
  cap_type: string
  fund_xi: number
  alpha: number
  sharpe: number | null
  sortino: number | null
  vol: number | null
  beta: number | null
  consistency: number | null
  cur_value: number
  risk_label: string
  bench_display: string
  max_dd: number
  er: number
  pe_ratio: number | null
  pb_ratio?: number | null
  info_ratio?: number | null
  tracking_error?: number | null
  up_capture?: number | null
  down_capture?: number | null
  calmar?: number | null
  treynor?: number | null
  is_debt: boolean
  is_hybrid: boolean
  ytm_proxy: number | null
  modified_duration: number | null
  credit_quality: string | null
  verdict: 'Strong' | 'Average' | 'Weak'
  verdict_cls: string
  action: string
  roll_labels: string[]
  fund_rolls: number[]
  bench_rolls: number[]
  rolling?: {
    fund: Record<string, number>
    bench: Record<string, number>
  }
  color: string
}

export interface PerformanceData {
  portfolio_return: number
  benchmark_return: number
  alpha: number
  dates: string[]
  portfolio: number[]
  benchmark: number[]
  benchmark_label: string
  period: string
  n_strong: number
  n_average: number
  n_weak: number
  funds: FundResult[]
  is_absolute?: boolean
  portfolio_score?: number
}

export interface AllocationData {
  broad: { label: string; value: number; pct: number; color: string }[]
  by_category: any[]
  by_cap: any[]
  by_plan: any[]
  heatmap: any[]
  reg_pct: number
}

export interface InsightsData {
  nudges: { type: string; message: string }[]
  goal_timeline: any[]
  score: number
  score_breakdown: { label: string; max: number }[]
  sip_score: number
  liquid_pct: number
  liquid_val: number
  expense_drag: number
  expense_pct: number
  elss_val: number
}

// ── API calls ────────────────────────────────────────────────────────────────
export const apiClient = {
  /** Parses CAS PDF statement and initializes a portfolio session. */
  parseFile: async (file: File, password: string, uploadType: string = 'mutual_funds'): Promise<ParseResponse> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', password)
    const { data } = await api.post<ParseResponse>('/portfolio/parse', fd, {
      headers: {
        'X-Upload-Type': uploadType
      }
    })
    return data
  },

  connectAA: async (phone: string, pan: string): Promise<ParseResponse> => {
    const { data } = await api.post<ParseResponse>('/portfolio/connect-aa', { phone, pan })
    return data
  },

  getHistory: async (uploadType: string = 'mutual_funds'): Promise<any> => {
    const { data } = await api.get('/history', {
      headers: {
        'X-Upload-Type': uploadType
      }
    })
    return data
  },

  /** Fetches high-level executive summary metrics (XIRR, Total Value). */
  getSummary: async (sid: string, params: Record<string, any> = {}): Promise<Summary> => {
    const { data } = await api.get<Summary>(`/portfolio/${sid}/summary`, { params })
    return data
  },

  syncPortfolio: async (sid: string): Promise<any> => {
    const { data } = await api.post(`/portfolio/${sid}/sync`)
    return data
  },

  /** Retrieves core time-series charting data for the overview dashboard. */
  getOverview: async (sid: string, params: Record<string, any> = {}): Promise<OverviewData> => {
    const { data } = await api.get<OverviewData>(`/portfolio/${sid}/overview`, { params })
    return data
  },

  getBenchmarkOverlay: async (sid: string, params: { period: string; benchmarks: string }): Promise<{ dates: string[]; series: Record<string, number[]> }> => {
    const { data } = await api.get<{ dates: string[]; series: Record<string, number[]> }>(`/portfolio/${sid}/benchmark-overlay`, { params })
    return data
  },

  getHoldings: async (sid: string, params: Record<string, any> = {}): Promise<{ holdings: Holding[]; total: number; cap_types: string[] }> => {
    const { data } = await api.get(`/portfolio/${sid}/holdings`, { params })
    return data
  },

  getAllocation: async (sid: string, params: Record<string, any> = {}): Promise<AllocationData> => {
    const { data } = await api.get<AllocationData>(`/portfolio/${sid}/allocation`, { params })
    return data
  },

  /** Executes multi-metric peer comparison and calculates Portfolio Health Score. */
  getPerformance: async (sid: string, params: Record<string, any> = {}): Promise<PerformanceData> => {
    const { data } = await api.get<PerformanceData>(`/portfolio/${sid}/performance`, { params })
    return data
  },

  getRebalancePlan: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/rebalance/${sid}/plan`, { params })
    return data
  },


  getInsights: async (sid: string, params: Record<string, any> = {}): Promise<InsightsData> => {
    const { data } = await api.get<InsightsData>(`/portfolio/${sid}/insights`, { params })
    return data
  },

  getJourney: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/journey/${sid}`)
    return data
  },

  getFundInsights: async (sid: string, isin: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/portfolio/${sid}/fund-insights/${isin}`, { params })
    return data
  },

  getTransactions: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/portfolio/${sid}/transactions`, { params })
    return data
  },


  getCategoryPeers: async (category: string): Promise<{ peers: any[], fallback_triggered?: boolean }> => {
    const { data } = await api.get('/compare/peers', { params: { category } })
    return data
  },

  searchTicker: async (q: string): Promise<any> => {
    const { data } = await api.get('/compare/search', { params: { q } })
    return data
  },

  getBenchmarkHistory: async (ticker: string, days = 365): Promise<any> => {
    const { data } = await api.get('/compare/history', { params: { ticker, days } })
    return data
  },

  getRollingReturns: async (sid: string, isin: string, window = 3): Promise<any> => {
    const { data } = await api.get(`/portfolio/${sid}/rolling/${isin}`, { params: { window } })
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

  postTaxOverrides: async (sid: string, overrides: any): Promise<any> => {
    const { data } = await api.post(`/tax-expert/${sid}/tax/recalculate`, overrides)
    return data
  },

  /** Compare Old vs New regime side-by-side. */
  compareTaxRegimes: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/tax-expert/${sid}/tax/compare-regimes`)
    return data
  },
}

export default api
