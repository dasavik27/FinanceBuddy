import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ── Types ────────────────────────────────────────────────────────────────────
export interface ParseResponse {
  session_id:  string
  is_partial:  boolean
  fund_count:  number
  amc_count:   number
  categories:  string[]
  amcs:        string[]
  benchmarks:  string[]
}

export interface Summary {
  total_value:    number
  total_invested: number
  total_gain:     number
  gain_pct:       number
  portfolio_xirr: number
  bench_xirr:     number
  bench_cagr:     number
  alpha:          number
  port_score:     number
  expense_drag:   number
  sip_score:      number
  num_funds:      number
  num_amcs:       number
  is_partial:     boolean
}

export interface OverviewData {
  port_pct:        number
  bench_pct:       number
  port_value:      number
  bench_value:     number
  use_xirr:        boolean
  benchmark_name:  string
  period:          string
  chart: {
    dates:     string[]
    portfolio: number[]
    benchmark: number[]
  }
}

export interface Holding {
  Fund:         string
  AMC:          string
  Category:     string
  Plan:         string
  'Cap Type':   string
  Units:        number
  Invested:     number
  'Market Value': number
  Gain:         number
  'Gain%':      number
  'Weight%':    number
  color:        string
}

export interface FundResult {
  fund:         string
  category:     string
  cap_type:     string
  plan:         string
  bench_display:string
  fund_xi:      number
  bench_xi:     number
  alpha:        number
  bench_cur:    number
  cur_value:    number
  consistency:  number
  vol:          number
  beta:         number
  risk_label:   string
  sharpe:       number
  sortino:      number
  max_dd:       number
  er:           number
  cat_rank:     number
  cat_total:    number
  verdict:      'Strong' | 'Average' | 'Weak'
  verdict_cls:  string
  action:       string
  roll_labels:  string[]
  fund_rolls:   number[]
  bench_rolls:  number[]
  color:        string
}

export interface PerformanceData {
  portfolio_return: number
  benchmark_return: number
  alpha:            number
  use_xirr:         boolean
  n_strong:         number
  n_average:        number
  n_weak:           number
  avg_alpha:        number
  funds:            FundResult[]
}

export interface AllocationData {
  broad:       { label: string; value: number; pct: number; color: string }[]
  by_category: any[]
  by_cap:      any[]
  by_plan:     any[]
  heatmap:     any[]
  reg_pct:     number
}

export interface TaxData {
  elss_value:    number
  elss_invested: number
  elss_count:    number
  equity_gain:   number
  debt_gain:     number
  ltcg_equity:   number
  stcg_debt:     number
  elss_lockin:   any[]
}

export interface InsightsData {
  nudges:          { type: string; message: string }[]
  goal_timeline:   any[]
  score:           number
  score_breakdown: { label: string; max: number }[]
  sip_score:       number
  liquid_pct:      number
  liquid_val:      number
  expense_drag:    number
  expense_pct:     number
  elss_val:        number
}

export interface SipProjection {
  flat_fv:      number
  flat_inv:     number
  flat_gain:    number
  stepup_fv:    number
  stepup_inv:   number
  stepup_gain:  number
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

  getSummary: async (sid: string, params: Record<string, any> = {}): Promise<Summary> => {
    const { data } = await api.get<Summary>(`/portfolio/${sid}/summary`, { params })
    return data
  },

  getOverview: async (sid: string, params: Record<string, any> = {}): Promise<OverviewData> => {
    const { data } = await api.get<OverviewData>(`/portfolio/${sid}/overview`, { params })
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

  getTax: async (sid: string, params: Record<string, any> = {}): Promise<TaxData> => {
    const { data } = await api.get<TaxData>(`/portfolio/${sid}/tax`, { params })
    return data
  },

  getInsights: async (sid: string, params: Record<string, any> = {}): Promise<InsightsData> => {
    const { data } = await api.get<InsightsData>(`/portfolio/${sid}/insights`, { params })
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

  searchTicker: async (q: string): Promise<any> => {
    const { data } = await api.get('/benchmark/search', { params: { q } })
    return data
  },

  getBenchmarkHistory: async (ticker: string, days = 365): Promise<any> => {
    const { data } = await api.get('/benchmark/history', { params: { ticker, days } })
    return data
  },
}

export default api
