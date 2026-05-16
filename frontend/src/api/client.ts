import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

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
  num_funds: number
  num_amcs: number
  is_partial: boolean
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
}

export interface AllocationData {
  broad: { label: string; value: number; pct: number; color: string }[]
  by_category: any[]
  by_cap: any[]
  by_plan: any[]
  heatmap: any[]
  reg_pct: number
}

export interface TaxData {
  elss_value: number
  elss_invested: number
  elss_count: number
  equity_gain: number
  debt_gain: number
  ltcg_gain: number
  stcg_gain: number
  ltcg_equity_tax: number
  ltcg_debt_tax: number
  stcg_equity_tax: number
  stcg_debt_tax: number
  total_tax: number
  equity_ltcg: number
  debt_ltcg: number
  equity_stcg: number
  debt_stcg: number
  ltcl: number
  stcl: number
  total_withdrawals: number
  fund_breakdown: any[]
  elss_lockin: any[]
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

export interface SipProjection {
  flat_fv: number
  flat_inv: number
  flat_gain: number
  stepup_fv: number
  stepup_inv: number
  stepup_gain: number
  extra_wealth: number
}

// ── API calls ────────────────────────────────────────────────────────────────
export const apiClient = {
  parseFile: async (file: File, password: string): Promise<ParseResponse> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('password', password)
    const { data } = await api.post<ParseResponse>('/portfolio/parse', fd)
    return data
  },

  connectAA: async (phone: string, pan: string): Promise<ParseResponse> => {
    const { data } = await api.post<ParseResponse>('/portfolio/connect-aa', { phone, pan })
    return data
  },

  getSummary: async (sid: string, params: Record<string, any> = {}): Promise<Summary> => {
    const { data } = await api.get<Summary>(`/portfolio/${sid}/summary`, { params })
    return data
  },

  syncPortfolio: async (sid: string): Promise<any> => {
    const { data } = await api.post(`/portfolio/${sid}/sync`)
    return data
  },

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

  getPerformance: async (sid: string, params: Record<string, any> = {}): Promise<PerformanceData> => {
    const { data } = await api.get<PerformanceData>(`/portfolio/${sid}/performance`, { params })
    return data
  },

  getRebalancePlan: async (sid: string, params: Record<string, any> = {}): Promise<any> => {
    const { data } = await api.get(`/rebalance/${sid}/plan`, { params })
    return data
  },

  getTax: async (sid: string, params: Record<string, any> = {}): Promise<TaxData> => {
    const { data } = await api.get<TaxData>(`/portfolio/${sid}/tax`, { params })
    return data
  },
  
  getTaxYears: async (sid: string): Promise<{ years: string[] }> => {
    const { data } = await api.get<{ years: string[] }>(`/portfolio/${sid}/tax/years`)
    return data
  },

  getTaxHarvest: async (sid: string): Promise<any> => {
    const { data } = await api.get(`/portfolio/${sid}/tax/harvest`)
    return data
  },

  simulateTax: async (sid: string, fund: string, units_to_sell: number): Promise<any> => {
    const { data } = await api.get(`/portfolio/${sid}/tax/simulate`, { params: { fund, units_to_sell } })
    return data
  },

  getInsights: async (sid: string, params: Record<string, any> = {}): Promise<InsightsData> => {
    const { data } = await api.get<InsightsData>(`/portfolio/${sid}/insights`, { params })
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

  sipProjection: async (body: any): Promise<SipProjection> => {
    const { data } = await api.post<SipProjection>('/sip/projection', body)
    return data
  },

  getCategoryPeers: async (category: string): Promise<{ peers: any[] }> => {
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
}

export default api
