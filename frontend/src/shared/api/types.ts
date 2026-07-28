// types.ts — data contracts for the mutual-funds API surface

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
